"""Views für Organisation, SOPs & Dienstanweisungen und Stations-Telefonbuch."""
from __future__ import annotations

import csv
import hashlib
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .access import CONTENT_ROLES, membership_required, station_module_required
from .models import CalendarEvent, Membership, Station
from .orga_forms import SOPDocumentForm, SOPRevisionForm, StationContactForm
from .orga_models import SOPDocument, SOPReceipt, SOPRevision, StationContact
from .wiki_models import WikiArticle


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("orga_enabled")
@require_GET
def orga_dashboard(request):
    """Zentrale für QM-Dienstanweisungen (SOPs), Notfall-Telefonbuch und Schreibtisch."""
    station = request.membership.station
    user = request.user

    # Bewusst keine automatisch angelegten Muster-SOPs oder Notrufnummern:
    # medizinische Inhalte und Telefonnummern muss jede Wache selbst
    # freigeben bzw. für ihre Region pflegen (Demo-Daten siehe demo_modules).

    can_manage = request.membership.role in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN}

    sops_qs = SOPDocument.objects.filter(station=station)

    query = request.GET.get("q", "").strip()
    if query:
        sops_qs = sops_qs.filter(
            Q(title__icontains=query)
            | Q(doc_number__icontains=query)
            | Q(revisions__content_markdown__icontains=query)
        ).distinct()

    cat = request.GET.get("cat", "").strip()
    if cat:
        sops_qs = sops_qs.filter(category=cat)

    sops_list = SOPDocument.list_with_ack_state(sops_qs, user)
    filter_mode = request.GET.get("filter", "all").strip()

    # Berechne Quittierungsstatus
    unack_sops = []
    ack_sops = []
    for s in sops_list:
        if (
            s.status == SOPDocument.Status.ACTIVE
            and s.requires_acknowledgment
            and not s.user_has_acknowledged(user)
        ):
            unack_sops.append(s)
        else:
            ack_sops.append(s)

    if filter_mode == "pending":
        display_sops = unack_sops
    elif filter_mode == "acknowledged":
        display_sops = ack_sops
    else:
        display_sops = sops_list

    # Telefonbuch
    speed_dials = StationContact.objects.filter(station=station, is_speed_dial=True).order_by("order_rank", "name")
    all_contacts = StationContact.objects.filter(station=station).order_by("category", "name")

    # Rückwärtskompatibilität: Termine & Wiki
    now = timezone.now()
    events = CalendarEvent.objects.filter(station=station, ends_at__gte=now).order_by("starts_at")[:5]
    articles = WikiArticle.objects.filter(station=station, is_archived=False).order_by("-updated_at")[:5]

    return render(
        request,
        "core/orga_dashboard.html",
        {
            "sops": display_sops,
            "all_sops_count": len(sops_list),
            "unack_count": len(unack_sops),
            "unack_ids": {s.id for s in unack_sops},
            "ack_count": len(ack_sops),
            "filter_mode": filter_mode,
            "query": query,
            "cat": cat,
            "categories": SOPDocument.Category.choices,
            "speed_dials": speed_dials,
            "all_contacts": all_contacts,
            "events": events,
            "articles": articles,
            "can_manage": can_manage,
        },
    )


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("orga_enabled")
@require_GET
def sop_detail(request, slug: str):
    """Detailansicht einer SOP mit Volltext, Prüfsumme und Revisionshistorie."""
    station = request.membership.station
    sop = get_object_or_404(SOPDocument, station=station, slug=slug)

    latest_revision = sop.latest_revision
    has_acknowledged = sop.user_has_acknowledged(request.user)

    all_revisions = sop.revisions.select_related("approved_by").order_by("-created_at")
    can_manage = request.membership.role in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN}
    # Wer wann quittiert hat, sieht nur die Wachleitung (Nachweispflicht).
    # Mitglieder sehen ihren eigenen Stand, nicht den der Kolleginnen.
    recent_receipts = (
        sop.receipts.select_related("user", "revision").order_by("-acknowledged_at")[:20] if can_manage else []
    )

    return render(
        request,
        "core/sop_detail.html",
        {
            "sop": sop,
            "latest_revision": latest_revision,
            "has_acknowledged": has_acknowledged,
            "all_revisions": all_revisions,
            "recent_receipts": recent_receipts,
            "can_manage": can_manage,
        },
    )


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("orga_enabled")
@require_POST
def sop_acknowledge(request, slug: str):
    """Mitarbeiter quittiert Kenntnisnahme der aktuellen SOP-Version."""
    station = request.membership.station
    sop = get_object_or_404(SOPDocument, station=station, slug=slug)
    latest_revision = sop.latest_revision

    if not latest_revision:
        messages.error(request, "Diese SOP hat noch keinen freigegebenen Textstand.")
        return redirect("sop_detail", slug=sop.slug)

    # Datensparsam (ab 0.26.1): Für die Kenntnisnahme genügen Person, Version
    # und Zeitpunkt. IP-Adresse und Browser werden nicht mehr gespeichert;
    # Altbestände bleiben unverändert (append-only), werden aber nirgends
    # mehr angezeigt oder exportiert.
    receipt, created = SOPReceipt.objects.get_or_create(
        station=station,
        sop=sop,
        revision=latest_revision,
        user=request.user,
        defaults={"ip_address": None, "user_agent": "", "acknowledged_at": timezone.now()},
    )

    if created:
        messages.success(request, f"Kenntnisnahme für '{sop.doc_number} (v{latest_revision.version_label})' quittiert.")
    else:
        messages.info(request, "Sie haben diese Version der Dienstanweisung bereits quittiert.")

    return redirect("sop_detail", slug=sop.slug)


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("orga_enabled")
@require_http_methods(["GET", "POST"])
def sop_create(request):
    """Neue SOP / Dienstanweisung im QM-System anlegen."""
    station = request.membership.station
    can_manage = request.membership.role in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN}
    if not can_manage:
        messages.error(request, "Nur Wachleiter und Administratoren dürfen Dienstanweisungen anlegen.")
        return redirect("orga_dashboard")

    if request.method == "POST":
        form = SOPDocumentForm(request.POST, station=station)
        if form.is_valid():
            sop = form.save(commit=False)
            sop.station = station
            sop.created_by = request.user
            sop.save()

            content = form.cleaned_data.get("initial_content", "").strip()
            version = form.cleaned_data.get("initial_version", "1.0").strip() or "1.0"
            if content:
                hash_val = hashlib.sha256(content.encode("utf-8")).hexdigest()
                SOPRevision.objects.create(
                    sop=sop,
                    version_label=version,
                    content_markdown=content,
                    content_hash=hash_val,
                    change_summary="Erstfassung der Dienstanweisung",
                    approved_by=request.user,
                    effective_date=sop.valid_from,
                )

            messages.success(request, f"Dienstanweisung '{sop.doc_number}: {sop.title}' erstellt.")
            return redirect("sop_detail", slug=sop.slug)
    else:
        form = SOPDocumentForm(station=station)

    return render(
        request,
        "core/sop_form.html",
        {"form": form, "title": "Neue SOP / Dienstanweisung erstellen", "action_label": "SOP speichern"},
    )


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("orga_enabled")
@require_http_methods(["GET", "POST"])
def sop_edit(request, slug: str):
    """Metadaten einer bestehenden SOP bearbeiten."""
    station = request.membership.station
    sop = get_object_or_404(SOPDocument, station=station, slug=slug)
    can_manage = request.membership.role in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN}
    if not can_manage:
        messages.error(request, "Keine Berechtigung zum Bearbeiten dieser Dienstanweisung.")
        return redirect("sop_detail", slug=sop.slug)

    if request.method == "POST":
        form = SOPDocumentForm(request.POST, instance=sop, station=station)
        if form.is_valid():
            form.save()
            messages.success(request, f"Änderungen an '{sop.doc_number}' gespeichert.")
            return redirect("sop_detail", slug=sop.slug)
    else:
        form = SOPDocumentForm(instance=sop, station=station)

    return render(
        request,
        "core/sop_form.html",
        {"form": form, "sop": sop, "title": f"SOP bearbeiten: {sop.doc_number}", "action_label": "Aktualisieren"},
    )


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("orga_enabled")
@require_http_methods(["GET", "POST"])
def sop_revision_create(request, slug: str):
    """Neue Version/Revision einer SOP publizieren (mit SHA-256 Hash)."""
    station = request.membership.station
    sop = get_object_or_404(SOPDocument, station=station, slug=slug)
    can_manage = request.membership.role in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN}
    if not can_manage:
        messages.error(request, "Keine Berechtigung zur Veröffentlichung neuer Versionen.")
        return redirect("sop_detail", slug=sop.slug)

    if request.method == "POST":
        form = SOPRevisionForm(request.POST)
        if form.is_valid():
            rev = form.save(commit=False)
            rev.sop = sop
            rev.approved_by = request.user
            rev.save()
            messages.success(request, f"Neue Version v{rev.version_label} für '{sop.doc_number}' veröffentlicht (Hash: {rev.content_hash[:12]}...).")
            return redirect("sop_detail", slug=sop.slug)
    else:
        last = sop.latest_revision
        initial = {
            "content_markdown": last.content_markdown if last else "",
            "version_label": f"{float(sop.current_version or 1.0) + 0.1:.1f}",
        }
        form = SOPRevisionForm(initial=initial)

    return render(
        request,
        "core/sop_revision_form.html",
        {"form": form, "sop": sop, "title": f"Neue Revision veröffentlichen: {sop.doc_number}"},
    )


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("orga_enabled")
@require_POST
def contact_create(request):
    """Neuen Wachenkontakt zum Telefonbuch hinzufügen."""
    station = request.membership.station
    can_manage = request.membership.role in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN}
    if not can_manage:
        messages.error(request, "Keine Berechtigung zur Kontaktverwaltung.")
        return redirect("orga_dashboard")

    form = StationContactForm(request.POST)
    if form.is_valid():
        contact = form.save(commit=False)
        contact.station = station
        contact.save()
        messages.success(request, f"Kontakt '{contact.name}' gespeichert.")
    else:
        messages.error(request, "Fehlerhafte Angaben beim Kontakt.")

    return redirect("orga_dashboard")


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("orga_enabled")
@require_POST
def contact_delete(request, pk: int):
    """Wachenkontakt entfernen."""
    station = request.membership.station
    can_manage = request.membership.role in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN}
    if not can_manage:
        messages.error(request, "Keine Berechtigung zum Löschen von Kontakten.")
        return redirect("orga_dashboard")

    contact = get_object_or_404(StationContact, pk=pk, station=station)
    name = contact.name
    contact.delete()
    messages.success(request, f"Kontakt '{name}' gelöscht.")
    return redirect("orga_dashboard")


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("orga_enabled")
@require_GET
def export_sop_receipts_csv(request, slug: str):
    """Revisionssicherer Quittierungs-Nachweis für QM-Audits als CSV."""
    station = request.membership.station
    sop = get_object_or_404(SOPDocument, station=station, slug=slug)
    if request.membership.role not in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN}:
        messages.error(request, _("Den Quittierungsnachweis exportiert die Wachleitung."))
        return redirect("sop_detail", slug=sop.slug)

    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = f'attachment; filename="QM_Audit_{sop.doc_number}_{timezone.localdate().isoformat()}.csv"'

    writer = csv.writer(response, delimiter=";")
    writer.writerow([
        _("SOP-Nummer"),
        _("Titel"),
        _("Version"),
        _("SHA-256-Prüfsumme"),
        _("Benutzername"),
        _("Name"),
        _("Quittiert am (Ortszeit)"),
    ])

    for r in sop.receipts.select_related("user", "revision").order_by("-acknowledged_at"):
        writer.writerow([
            sop.doc_number,
            sop.title,
            r.revision.version_label if r.revision else "",
            r.revision.content_hash if r.revision else "",
            r.user.username,
            r.user.get_full_name(),
            timezone.localtime(r.acknowledged_at).strftime("%Y-%m-%d %H:%M:%S"),
        ])

    return response
