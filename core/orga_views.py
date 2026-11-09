"""Views für Organisation, SOPs & Dienstanweisungen und Stations-Telefonbuch."""
from __future__ import annotations

import csv
import hashlib
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .access import CONTENT_ROLES, membership_required, station_module_required
from .models import CalendarEvent, Membership, Station
from .orga_forms import SOPDocumentForm, SOPRevisionForm, StationContactForm
from .orga_models import (
    SOPDocument,
    SOPRevision,
    StationContact,
    acknowledgement_refusal,
    in_reading_audience,
    record_acknowledgement,
)
from .services import audit
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

    # Berechne Quittierungsstatus: offen nur für die Zielgruppe (Rolle und
    # Funktion), nie für Auditor oder Wachenterminal.
    in_audience = in_reading_audience(request.membership)
    unack_sops = []
    ack_sops = []
    for s in sops_list:
        if (
            s.status == SOPDocument.Status.ACTIVE
            and s.requires_acknowledgment
            and in_audience
            and s.matches_target(request.membership)
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
            # Nur wirklich bestätigte zeigen „Quittiert“; Dienstanweisungen außerhalb
            # der eigenen Zielgruppe bekommen kein Etikett.
            "acked_ids": {s.id for s in sops_list if s.latest_revision and s.user_has_acknowledged(user)},
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
    # Wer wann quittiert hat, sieht nur die Wachleitung (Nachweispflicht), und
    # nur, wenn die Wache eine Vereinbarung dazu hat („Namen nur nach
    # Vereinbarung“, Station.sop_receipt_names_agreed). Sonst Anzahl und Quote.
    # Mitglieder sehen ihren eigenen Stand, nicht den der Kolleginnen.
    show_names = can_manage and station.sop_receipt_names_agreed
    recent_receipts = (
        sop.receipts.select_related("user", "revision").order_by("-acknowledged_at")[:20] if show_names else []
    )
    # Nur die Zielgruppe wird zur Bestätigung aufgefordert; andere dürfen
    # freiwillig bestätigen, das zählt aber nicht zur Quote.
    is_target = sop.is_target_member(request.membership)
    can_acknowledge = acknowledgement_refusal(sop, request.membership) is None

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
            "show_names": show_names,
            "is_target": is_target,
            "can_acknowledge": can_acknowledge,
            "ack_progress": sop.ack_progress(),
        },
    )


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("orga_enabled")
@require_POST
def sop_acknowledge(request, slug: str):
    """Mitarbeiter quittiert Kenntnisnahme der aktuellen SOP-Version."""
    station = request.membership.station
    sop = get_object_or_404(SOPDocument, station=station, slug=slug)

    # Dieselben Regeln wie in der App (core/api/sop.py): nur „In Kraft“, nur
    # mit Textstand, nie mit dem Dienstkonto des Wachenterminals. Außer Kraft
    # bleiben Versionen und Quittierungen, neue gibt es nicht.
    refusal = acknowledgement_refusal(sop, request.membership)
    if refusal:
        code, text = refusal
        if code == "forbidden":
            raise PermissionDenied(text)
        messages.error(request, text)
        return redirect("sop_detail", slug=sop.slug)

    # Datensparsam (ab 0.26.1): Für die Kenntnisnahme genügen Person, Version
    # und Zeitpunkt. IP-Adresse und Browser werden nicht mehr gespeichert;
    # Altbestände bleiben unverändert (append-only), werden aber nirgends
    # mehr angezeigt oder exportiert.
    latest_revision = sop.latest_revision
    receipt, created = record_acknowledgement(sop, request.user)

    if created:
        messages.success(request, _("Kenntnisnahme für „%(doc)s“ (v%(version)s) bestätigt.") % {
            "doc": sop.doc_number, "version": latest_revision.version_label,
        })
    else:
        messages.info(request, _("Du hast diese Version der Dienstanweisung bereits bestätigt."))

    return redirect("sop_detail", slug=sop.slug)


@membership_required(allowed_roles={Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN})
@station_module_required("orga_enabled")
@require_POST
def sop_remind(request, slug: str):
    """Versendet gezielt eine Erinnerung ausschließlich an noch offene Zielpersonen.

    Schützt die Beschäftigtendaten: Wer noch nicht gelesen hat, erfährt niemand;
    die Leitung sieht nur die aggregierte Quote und die Anzahl der versendeten Erinnerungen.
    """
    station = request.membership.station
    sop = get_object_or_404(SOPDocument, station=station, slug=slug)

    if sop.status == SOPDocument.Status.ARCHIVED:
        messages.error(request, _("Diese Dienstanweisung ist außer Kraft."))
        return redirect("sop_detail", slug=sop.slug)
    if sop.status != SOPDocument.Status.ACTIVE:
        # Ein Entwurf gilt noch nicht; niemand wird an ihn erinnert.
        messages.error(request, _("Erinnerungen gibt es nur für Dienstanweisungen in Kraft."))
        return redirect("sop_detail", slug=sop.slug)

    if not sop.requires_acknowledgment or not sop.latest_revision:
        messages.info(request, _("Für diese Dienstanweisung ist keine Pflichtquittierung aktiv."))
        return redirect("sop_detail", slug=sop.slug)

    unacknowledged = list(sop.unacknowledged_users())
    if not unacknowledged:
        messages.info(request, _("Alle Zielpersonen haben diese Version bereits quittiert."))
        return redirect("sop_detail", slug=sop.slug)

    from .deadline_reminders import create_notification, send_reminder_emails
    from .notification_models import UserNotification

    today = timezone.localdate()
    sent_count = 0
    created_notes: dict = {}
    url = reverse("sop_detail", args=[sop.slug])

    title = _("Dienstanweisung lesen: %(doc)s") % {"doc": sop.doc_number}
    if sop.ack_due_date:
        body = _("Bitte nimm die Dienstanweisung „%(title)s“ (Frist bis %(date)s) zur Kenntnis und bestätige sie.") % {
            "title": sop.title,
            "date": sop.ack_due_date.strftime("%d.%m.%Y"),
        }
    else:
        body = _("Bitte nimm die Dienstanweisung „%(title)s“ zur Kenntnis und bestätige sie.") % {
            "title": sop.title,
        }

    for user in unacknowledged:
        dedupe_key = f"sop_manual_remind:{sop.pk}:{sop.latest_revision.pk}:{user.pk}:{today.isoformat()}"
        note = create_notification(user, station, dedupe_key, UserNotification.Kind.SOP_DUE, title, body, url)
        if note is not None:
            created_notes.setdefault(user.pk, []).append(note)
            sent_count += 1
    # E-Mail nur an Personen, die Erinnerungen per E-Mail selbst eingeschaltet haben.
    send_reminder_emails(created_notes)

    if sent_count > 0:
        messages.success(
            request,
            _("Erinnerung an %(count)d offene Person(en) versendet.") % {"count": sent_count},
        )
    else:
        messages.info(
            request,
            _("Die offenen Personen wurden heute bereits an diese Version erinnert."),
        )

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
        # Vor is_valid() merken: Die Prüfung schreibt die Eingaben schon in die Instanz.
        previous_status = sop.status
        form = SOPDocumentForm(request.POST, instance=sop, station=station)
        if form.is_valid():
            form.save()
            if sop.status != previous_status:
                # „Außer Kraft“ ersetzt das Löschen; jeder Wechsel steht im Audit.
                audit(request.user, station, "orga.sop_status_changed", sop, {
                    "fields": ["status"], "from": previous_status, "to": sop.status,
                })
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
    if not station.sop_receipt_names_agreed:
        # „Namen nur nach Vereinbarung“: ohne Vereinbarung nur Anzahlen je
        # Version, keine Personen (Station.sop_receipt_names_agreed).
        target_ids = sop.target_user_ids()
        writer.writerow([
            _("SOP-Nummer"),
            _("Titel"),
            _("Version"),
            _("SHA-256-Prüfsumme"),
            _("Lesebestätigungen"),
            _("davon aus der heutigen Zielgruppe"),
            _("Zielgruppe (Personen)"),
        ])
        for revision in sop.revisions.order_by("-created_at", "-pk"):
            user_ids = set(revision.receipts.values_list("user_id", flat=True))
            writer.writerow([
                sop.doc_number,
                sop.title,
                revision.version_label,
                revision.content_hash,
                len(user_ids),
                len(user_ids & target_ids),
                len(target_ids),
            ])
        return response

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
