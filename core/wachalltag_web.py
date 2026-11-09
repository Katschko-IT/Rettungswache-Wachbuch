"""Server-rendered Wachalltag UI matching the mobile API.

The browser UI intentionally stays task-first and does not introduce patient,
incident or alarm data. All mutations remain station scoped and audited.
"""

from __future__ import annotations

from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone, translation
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from .access import CONTENT_ROLES, membership_required
from .api.wachalltag import (
    MAX_ATTACHMENT_BYTES,
    MAX_ATTACHMENT_TOTAL_BYTES,
    MAX_ATTACHMENTS_PER_DEFECT,
    defect_attachment_limit_error,
)
from .attachments import read_upload, read_uploads
from .defect_refs import (
    ASSET_PREFIX,
    CUSTOM_VALUE,
    DEVICE_PREFIX,
    VEHICLE_PREFIX,
    build_reference_options,
    duplicate_hint_data,
    duplicates_for,
    grouped_options,
    resolve_reference,
)
from .device_status import IN_SERVICE, LOCKED_DEVICE_STATUSES, asset_locked_by_device, asset_release_blockers
from .models import Checklist, Membership
from .services import audit
from .wachalltag_models import (
    DEFECT_WORKFLOW_ORDERING,
    AssetEvent,
    ChecklistSchedule,
    Defect,
    DefectAttachment,
    DefectEvent,
    HandoverAck,
    InventoryEvent,
    InventoryItem,
    StationAsset,
)


def _parse_local_datetime(value):
    if not value:
        return None
    try:
        parsed = parse_datetime(value)
    except ValueError:  # formal korrekt, aber unmöglich (z. B. 30. Februar)
        return None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _is_adminish(membership):
    return membership.role in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN}


@membership_required(allowed_roles=CONTENT_ROLES)
def defects(request):
    station = request.membership.station
    qs = Defect.objects.filter(station=station).select_related("owner", "created_by")
    scope = request.GET.get("status", "active")
    if scope == "done":
        qs = qs.filter(status=Defect.Status.DONE)
    elif scope in Defect.Status.values:
        qs = qs.filter(status=scope)
    else:
        scope = "active"
        qs = qs.exclude(status=Defect.Status.DONE)
    return render(
        request,
        "core/defects.html",
        {
            "defects": qs[:200],
            "scope": scope,
            "now": timezone.now(),
        },
    )


DEFECT_FALLBACK_CATEGORY = Defect.Category.MATERIAL


def _auto_defect_title(category, reference):
    """Titel, wenn das Feld leer bleibt: „<Kategorie>: <Bezug>“ in Wachensprache."""
    with translation.override(settings.LANGUAGE_CODE):
        category_label = str(Defect.Category(category).label)
        if reference:
            return (_("%(category)s: %(reference)s") % {"category": category_label, "reference": reference})[:160]
        return (_("%(category)s: ohne Bezug") % {"category": category_label})[:160]


def _lock_device_for_defect(device, defect, actor, station):
    """Wie die Meldung im Medizinproduktebuch: Ein gemeldeter Mangel sperrt das Gerät.

    Freigeben darf danach nur Schichtleitung oder Admin im Medizinproduktebuch
    (core/device_status.py). Ein bereits gesperrtes Gerät bleibt gesperrt.
    """
    from .mpg_models import MedicalDevice

    locked = MedicalDevice.objects.select_for_update().get(pk=device.pk, station=station)
    if locked.current_status in LOCKED_DEVICE_STATUSES:
        return locked, False
    previous = locked.current_status
    locked.current_status = MedicalDevice.Status.OOB
    with translation.override(settings.LANGUAGE_CODE):
        locked.status_note = (_("Mangel #%(id)s gemeldet: %(title)s") % {"id": defect.pk, "title": defect.title})[:300]
    locked.save(update_fields=["current_status", "status_note", "updated_at"])
    audit(actor, station, "mpg.device_locked", locked, {"defect_id": defect.pk, "from": previous, "via": "defect_form"})
    return locked, True


@membership_required(allowed_roles=CONTENT_ROLES)
@require_http_methods(["GET", "POST"])
def defect_create(request):
    """Mangel in drei Tipps.

    Mit vorgewähltem Bezug (``?asset=`` von Fahrzeug, Gerät oder QR-Code)
    genügen Foto, Auslösen und Speichern; Titel, Kategorie und Priorität sind
    vorbelegt bzw. werden aus Kategorie und Bezug gebildet. Alle Bezüge werden
    nur innerhalb der eigenen Wache aufgelöst (core/defect_refs.py).
    """
    from .demo_sandbox import tour_form_initial
    from .terminal import is_service_user

    station = request.membership.station
    # Das Wachenterminal meldet keine Gerätemängel: Ein Gerätemangel sperrt das
    # Medizinprodukt, und Medizingeräte bleiben persönlichen Konten vorbehalten.
    options = build_reference_options(station, include_devices=not is_service_user(request.user))
    open_defects = list(
        Defect.objects.filter(station=station)
        .exclude(status=Defect.Status.DONE)
        .select_related("owner", "created_by")
        .order_by(*DEFECT_WORKFLOW_ORDERING)
    )
    initial = tour_form_initial(request, "defect")
    errors = {}

    if request.method == "POST":
        posted_ref = (request.POST.get("asset_ref") or "").strip()
        custom_text = (request.POST.get("asset_ref_custom") or "").strip()
        selected = None
        if posted_ref and posted_ref != CUSTOM_VALUE:
            selected = resolve_reference(options, posted_ref)
            if selected is None and posted_ref.startswith((VEHICLE_PREFIX, DEVICE_PREFIX, ASSET_PREFIX)):
                errors["asset_ref"] = _("Dieser Bezug steht nicht zur Auswahl. Bitte neu wählen.")
            elif selected is None:
                # Älterer Client oder Vorlage: unbekannter Text bleibt freier Text.
                custom_text, posted_ref = posted_ref, CUSTOM_VALUE
        elif not posted_ref and custom_text:
            # Ohne JavaScript: Freitext eingetragen, Auswahl nicht umgestellt.
            posted_ref = CUSTOM_VALUE
        selected_key = selected.key if selected else posted_ref
        values = {
            "title": (request.POST.get("title") or "").strip(),
            "description": (request.POST.get("description") or "").strip(),
            "due_at": request.POST.get("due_at") or "",
            "priority": request.POST.get("priority") or request.POST.get("priority_select") or Defect.Priority.NORMAL,
            "category": request.POST.get("category") or request.POST.get("category_select")
            or (selected.category if selected else DEFECT_FALLBACK_CATEGORY),
            "owner_self": request.POST.get("owner_self") == "1",
        }
    else:
        requested = (
            request.GET.get("asset") or request.GET.get("asset_ref")
            or initial.get("asset_ref") or initial.get("asset") or ""
        ).strip()
        selected = resolve_reference(options, requested)
        custom_text = "" if selected else requested
        selected_key = selected.key if selected else (CUSTOM_VALUE if requested else "")
        values = {
            "title": initial.get("title", ""),
            "description": initial.get("description", ""),
            "due_at": initial.get("due_at", ""),
            "priority": initial.get("priority") or Defect.Priority.NORMAL,
            "category": initial.get("category") or (selected.category if selected else DEFECT_FALLBACK_CATEGORY),
            "owner_self": True,
        }

    if request.method == "POST":
        if values["priority"] not in Defect.Priority.values or values["category"] not in Defect.Category.values:
            errors["form"] = _("Priorität oder Kategorie ist ungültig.")
        raw_files = (
            request.FILES.getlist("attachments")
            + request.FILES.getlist("photo")
            + request.FILES.getlist("camera")
        )
        uploads, upload_error = read_uploads(raw_files, limit=MAX_ATTACHMENTS_PER_DEFECT)
        if not upload_error and sum(upload.size for upload in uploads) > MAX_ATTACHMENT_TOTAL_BYTES:
            upload_error = _("Alle Fotos zusammen dürfen höchstens 12 MiB groß sein.")
        if upload_error:
            errors["attachments"] = upload_error
        reference_text = selected.label if selected else (custom_text if selected_key == CUSTOM_VALUE else "")
        if not (values["title"] or reference_text or values["description"] or uploads or upload_error):
            errors["title"] = _("Bitte einen Titel, einen Bezug, eine Beschreibung oder ein Foto angeben.")
        if raw_files and errors and "attachments" not in errors:
            errors["attachments"] = _("Das Foto wurde noch nicht gespeichert. Bitte erneut auswählen.")

        if not errors:
            title = values["title"][:160] or _auto_defect_title(values["category"], reference_text)
            device = None
            with transaction.atomic():
                item = Defect.objects.create(
                    station=station,
                    title=title,
                    description=values["description"][:3000],
                    asset_ref=reference_text[:160],
                    vehicle_id=selected.vehicle_id if selected else None,
                    medical_device_id=selected.device_id if selected else None,
                    priority=values["priority"],
                    status=Defect.Status.OPEN,
                    owner=request.user if values["owner_self"] else None,
                    due_at=_parse_local_datetime(values["due_at"]),
                    category=values["category"],
                    created_by=request.user,
                )
                DefectEvent.objects.create(
                    defect=item,
                    station=station,
                    kind=DefectEvent.Kind.CREATED,
                    to_status=item.status,
                    actor=request.user,
                )
                for upload in uploads:
                    attachment = DefectAttachment.objects.create(
                        defect=item,
                        station=station,
                        filename=upload.name,
                        content_type=upload.content_type,
                        data=upload.data,
                        size=upload.size,
                        uploaded_by=request.user,
                    )
                    DefectEvent.objects.create(
                        defect=item,
                        station=station,
                        kind=DefectEvent.Kind.ATTACHMENT,
                        actor=request.user,
                        metadata={"attachment_id": attachment.pk, "size": attachment.size, "size_bytes": attachment.size},
                    )
                if item.medical_device_id:
                    device, newly_locked = _lock_device_for_defect(item.medical_device, item, request.user, station)
                audit(request.user, station, "defect.created", item, {
                    "via": "web",
                    "reference": selected.kind if selected else ("text" if reference_text else ""),
                })
            messages.success(request, _("Mangel wurde angelegt."))
            if device is not None:
                messages.warning(request, _(
                    "„%(device)s“ ist gesperrt, bis der Mangel erledigt ist und die Schichtleitung "
                    "das Gerät im Medizinproduktebuch freigibt."
                ) % {"device": device.name})
            return redirect("defect_detail_web", pk=item.pk)

    already_reported = duplicates_for(selected, open_defects, text=custom_text, options=options)
    return render(
        request,
        "core/defect_form.html",
        {
            "priorities": Defect.Priority.choices,
            "categories": Defect.Category.choices,
            "reference_groups": grouped_options(options),
            "selected_key": selected_key,
            "selected_option": selected,
            "custom_value": CUSTOM_VALUE,
            "custom_text": custom_text,
            "values": values,
            "errors": errors,
            "already_reported_defects": already_reported,
            "already_reported_count": len(already_reported),
            "defects_by_asset_data": duplicate_hint_data(options, open_defects),
            "initial": initial,
            "max_upload_mb": MAX_ATTACHMENT_BYTES // (1024 * 1024),
        },
        status=200,
    )


@membership_required(allowed_roles=CONTENT_ROLES)
@require_http_methods(["GET", "POST"])
def defect_detail(request, pk):
    station = request.membership.station
    item = get_object_or_404(
        Defect.objects.select_related("owner", "created_by", "source_checklist_run__checklist"), pk=pk, station=station,
    )
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "status":
            status = request.POST.get("status") or ""
            if status not in Defect.Status.values:
                messages.error(request, "Ungültiger Status.")
            elif status == Defect.Status.DONE and not _is_adminish(request.membership):
                messages.error(request, "Nur Schichtleitung oder Admin darf Mängel abschließen.")
            else:
                with transaction.atomic():
                    locked = Defect.objects.select_for_update().get(pk=item.pk)
                    previous = locked.status
                    if previous != status:
                        locked.status = status
                        locked.closed_at = timezone.now() if status == Defect.Status.DONE else None
                        locked.save(update_fields=["status", "closed_at", "updated_at"])
                        DefectEvent.objects.create(
                            defect=locked,
                            station=station,
                            kind=DefectEvent.Kind.STATUS,
                            from_status=previous,
                            to_status=status,
                            actor=request.user,
                        )
                        audit(request.user, station, "defect.status_changed", locked, {"from": previous, "to": status, "via": "web"})
                messages.success(request, "Status aktualisiert.")
                device = item.medical_device
                if status == Defect.Status.DONE and device is not None and device.current_status == "oob":
                    messages.info(
                        request,
                        f"'{device.name}' bleibt gesperrt, bis die Schichtleitung es im Medizinproduktebuch freigibt.",
                    )
                return redirect("defect_detail_web", pk=item.pk)
        elif action == "upload":
            # Prüft Typ, Größe und Inhalt; Bilder ohne Metadaten oder gar nicht.
            upload, upload_error = read_upload(request.FILES.get("attachment"))
            if upload_error:
                messages.error(request, upload_error)
            else:
                with transaction.atomic():
                    locked = Defect.objects.select_for_update().get(pk=item.pk)
                    if limit := defect_attachment_limit_error(locked, upload.size):
                        messages.error(request, limit[0])
                        return redirect("defect_detail_web", pk=item.pk)
                    attachment = DefectAttachment.objects.create(
                        defect=item,
                        station=station,
                        filename=upload.name,
                        content_type=upload.content_type,
                        data=upload.data,
                        size=upload.size,
                        uploaded_by=request.user,
                    )
                    DefectEvent.objects.create(
                        defect=item,
                        station=station,
                        kind=DefectEvent.Kind.ATTACHMENT,
                        actor=request.user,
                        metadata={"attachment_id": attachment.pk, "size": attachment.size, "size_bytes": attachment.size},
                    )
                    audit(request.user, station, "defect.attachment_added", item, {"attachment_id": attachment.pk, "via": "web"})
                messages.success(request, "Foto wurde angehängt.")
                return redirect("defect_detail_web", pk=item.pk)
    return render(
        request,
        "core/defect_detail.html",
        {
            "item": item,
            "events": item.events.select_related("actor").all()[:100],
            "attachments": item.attachments.select_related("uploaded_by").defer("data"),
            "statuses": Defect.Status.choices,
            "can_close": _is_adminish(request.membership),
        },
    )


@membership_required(allowed_roles=CONTENT_ROLES)
@require_http_methods(["GET", "POST"])
def assets_inventory(request):
    station = request.membership.station
    if request.method == "POST":
        action = request.POST.get("action") or ""
        if action in {"asset-create", "asset-status", "inventory-create"} and not _is_adminish(request.membership):
            messages.error(request, "Nur Schichtleitung oder Admin darf Stammdaten ändern.")
            return redirect("assets_inventory_web")
        if action == "asset-create":
            label = (request.POST.get("label") or "").strip()
            asset_id = slugify(request.POST.get("asset_id") or label)[:64]
            kind = request.POST.get("kind") or StationAsset.Kind.DEVICE
            if not label or not asset_id or kind not in StationAsset.Kind.values:
                messages.error(request, "Asset-Daten sind unvollständig.")
            else:
                try:
                    asset = StationAsset.objects.create(
                        station=station,
                        asset_id=asset_id,
                        label=label[:160],
                        kind=kind,
                        updated_by=request.user,
                    )
                    AssetEvent.objects.create(asset=asset, station=station, to_status=asset.status, actor=request.user)
                    audit(request.user, station, "asset.created", asset, {"via": "web"})
                    messages.success(request, "Gerät/Fahrzeug wurde angelegt.")
                except IntegrityError:
                    messages.error(request, "Diese Asset-ID existiert bereits.")
        elif action == "asset-status":
            asset = get_object_or_404(StationAsset, station=station, asset_id=request.POST.get("asset_id"))
            status = request.POST.get("status") or ""
            blockers = asset_release_blockers(asset) if status in IN_SERVICE else []
            if status not in StationAsset.Status.values:
                messages.error(request, "Ungültiger Asset-Status.")
            elif blockers:
                numbers = ", ".join(f"#{item.pk}" for item in blockers)
                messages.error(request, f"Gerät bleibt gesperrt: offene Mängel {numbers}.")
            elif status != StationAsset.Status.OOB and asset_locked_by_device(asset):
                messages.error(request, _(
                    "Das Gerät ist im Medizinproduktebuch gesperrt oder außer Betrieb genommen. "
                    "Freigeben kann die Schichtleitung es nur dort, mit einer Funktionskontrolle."
                ))
            else:
                previous = asset.status
                asset.status = status
                asset.note = (request.POST.get("note") or "")[:300]
                asset.updated_by = request.user
                asset.save()
                AssetEvent.objects.create(asset=asset, station=station, from_status=previous, to_status=status, note=asset.note, actor=request.user)
                audit(request.user, station, "asset.status_changed", asset, {"from": previous, "to": status, "via": "web"})
                messages.success(request, "Asset-Status aktualisiert.")
        elif action == "inventory-create":
            label = (request.POST.get("label") or "").strip()
            item_id = slugify(request.POST.get("item_id") or label)[:64]
            kind = request.POST.get("kind") or InventoryItem.Kind.DEVICE
            if not label or not item_id or kind not in InventoryItem.Kind.values:
                messages.error(request, "Inventar-Daten sind unvollständig.")
            else:
                try:
                    inv = InventoryItem.objects.create(
                        station=station,
                        item_id=item_id,
                        label=label[:160],
                        kind=kind,
                        updated_by=request.user,
                    )
                    audit(request.user, station, "inventory.created", inv, {"via": "web"})
                    messages.success(request, "Pool-/Schlüsselobjekt wurde angelegt.")
                except IntegrityError:
                    messages.error(request, "Diese Inventar-ID existiert bereits.")
        elif action in {"checkout", "checkin"}:
            item_id = request.POST.get("item_id") or ""
            with transaction.atomic():
                # of=("self",): holder ist nullable (LEFT OUTER JOIN); PostgreSQL
                # verweigert FOR UPDATE auf der nullbaren Seite (wie in der API).
                inv = get_object_or_404(
                    InventoryItem.objects.select_for_update(of=("self",)).select_related("holder"),
                    station=station, item_id=item_id,
                )
                if action == "checkout":
                    if inv.holder_id and inv.holder_id != request.user.id:
                        messages.error(request, f"Bereits ausgegeben an {inv.holder.username}.")
                    elif not inv.holder_id:
                        inv.holder = request.user
                        inv.checked_out_at = timezone.now()
                        inv.updated_by = request.user
                        inv.save()
                        InventoryEvent.objects.create(item=inv, station=station, action=InventoryEvent.Action.CHECKOUT, actor=request.user, holder=request.user)
                        audit(request.user, station, "inventory.checkout", inv, {"via": "web"})
                        messages.success(request, "Ausgabe gebucht.")
                else:
                    previous = inv.holder
                    if previous and previous.id != request.user.id and not _is_adminish(request.membership):
                        messages.error(request, "Nur Ausleiher, Schichtleitung oder Admin darf zurückgeben.")
                    elif previous:
                        inv.holder = None
                        inv.checked_out_at = None
                        inv.updated_by = request.user
                        inv.save()
                        InventoryEvent.objects.create(item=inv, station=station, action=InventoryEvent.Action.CHECKIN, actor=request.user, holder=previous)
                        audit(request.user, station, "inventory.checkin", inv, {"via": "web"})
                        messages.success(request, "Rückgabe gebucht.")
        return redirect("assets_inventory_web")

    return render(
        request,
        "core/assets_inventory.html",
        {
            "assets": StationAsset.objects.filter(station=station),
            "inventory": InventoryItem.objects.filter(station=station).select_related("holder"),
            "asset_statuses": StationAsset.Status.choices,
            "asset_kinds": StationAsset.Kind.choices,
            "inventory_kinds": InventoryItem.Kind.choices,
            "can_manage": _is_adminish(request.membership),
        },
    )


@membership_required(allowed_roles=CONTENT_ROLES)
@require_http_methods(["GET", "POST"])
def checklist_schedules(request):
    station = request.membership.station
    if not station.checklists_enabled:
        return redirect("more")
    if request.method == "POST":
        if not _is_adminish(request.membership):
            messages.error(request, "Nur Schichtleitung oder Admin darf Intervalle ändern.")
            return redirect("checklist_schedules_web")
        checklist = get_object_or_404(Checklist, pk=request.POST.get("checklist_id"), station=station, is_active=True)
        interval = request.POST.get("interval") or ""
        if not interval:
            ChecklistSchedule.objects.filter(checklist=checklist).delete()
            audit(request.user, station, "checklist.schedule_removed", checklist, {"via": "web"})
        elif interval not in ChecklistSchedule.Interval.values:
            messages.error(request, "Ungültiges Intervall.")
            return redirect("checklist_schedules_web")
        else:
            due_next = _parse_local_datetime(request.POST.get("due_next"))
            ChecklistSchedule.objects.update_or_create(
                checklist=checklist,
                defaults={"station": station, "interval": interval, "due_next": due_next},
            )
            audit(request.user, station, "checklist.schedule_updated", checklist, {"interval": interval, "via": "web"})
        messages.success(request, "Prüfintervall aktualisiert.")
        return redirect("checklist_schedules_web")
    schedules = {s.checklist_id: s for s in ChecklistSchedule.objects.filter(station=station)}
    rows = [(checklist, schedules.get(checklist.pk)) for checklist in Checklist.objects.filter(station=station, is_active=True)]
    return render(
        request,
        "core/checklist_schedules.html",
        {"rows": rows, "intervals": ChecklistSchedule.Interval.choices, "can_manage": _is_adminish(request.membership), "now": timezone.now()},
    )


@membership_required(allowed_roles=CONTENT_ROLES)
def reports(request):
    station = request.membership.station
    now = timezone.now()
    open_defects = Defect.objects.filter(station=station).exclude(status=Defect.Status.DONE)
    assets = StationAsset.objects.filter(station=station)
    total_assets = assets.count()
    ready_assets = assets.filter(status=StationAsset.Status.READY).count()
    return render(
        request,
        "core/wachalltag_reports.html",
        {
            "open_defects": open_defects.count(),
            "overdue_defects": open_defects.filter(due_at__lt=now).count(),
            "overdue_checks": ChecklistSchedule.objects.filter(station=station, due_next__lt=now).count(),
            "assets_total": total_assets,
            "assets_ready": ready_assets,
            "asset_ready_percent": round((ready_assets / total_assets) * 100) if total_assets else 0,
            "inventory_out": InventoryItem.objects.filter(station=station, holder__isnull=False).count(),
            "acks_by_me": HandoverAck.objects.filter(station=station, user=request.user).count(),
        },
    )
