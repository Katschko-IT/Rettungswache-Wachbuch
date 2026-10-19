"""Server-rendered Wachalltag UI matching the mobile API.

The browser UI intentionally stays task-first and does not introduce patient,
incident or alarm data. All mutations remain station scoped and audited.
"""

from __future__ import annotations

from datetime import datetime

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify
from django.views.decorators.http import require_http_methods

from .access import CONTENT_ROLES, membership_required
from .api.wachalltag import ALLOWED_ATTACHMENT_TYPES, MAX_ATTACHMENT_BYTES, attachment_is_valid
from .attachments import read_uploads
from .models import Checklist, Membership
from .services import audit
from .wachalltag_models import (
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
    parsed = parse_datetime(value)
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


@membership_required(allowed_roles=CONTENT_ROLES)
@require_http_methods(["GET", "POST"])
def defect_create(request):
    station = request.membership.station
    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        if not title:
            messages.error(request, "Bitte einen Titel angeben.")
        else:
            priority = request.POST.get("priority") or Defect.Priority.NORMAL
            category = request.POST.get("category") or Defect.Category.TASK
            if priority not in Defect.Priority.values or category not in Defect.Category.values:
                messages.error(request, "Priorität oder Kategorie ist ungültig.")
            else:
                owner = request.user if request.POST.get("owner_self") == "1" else None
                due_at = _parse_local_datetime(request.POST.get("due_at"))
                uploads, upload_error = read_uploads(request.FILES.getlist("attachments"))
                if upload_error:
                    messages.error(request, upload_error)
                    return redirect("defect_create_web")
                with transaction.atomic():
                    item = Defect.objects.create(
                        station=station,
                        title=title[:160],
                        description=(request.POST.get("description") or "")[:3000],
                        asset_ref=(request.POST.get("asset_ref") or "")[:160],
                        priority=priority,
                        status=Defect.Status.OPEN,
                        owner=owner,
                        due_at=due_at,
                        category=category,
                        created_by=request.user,
                    )
                    DefectEvent.objects.create(
                        defect=item,
                        station=station,
                        kind=DefectEvent.Kind.CREATED,
                        to_status=item.status,
                        actor=request.user,
                    )
                    for upload, raw in uploads:
                        attachment = DefectAttachment.objects.create(
                            defect=item,
                            station=station,
                            filename=upload.name[:180],
                            content_type=upload.content_type,
                            data=raw,
                            size=len(raw),
                            uploaded_by=request.user,
                        )
                        DefectEvent.objects.create(
                            defect=item,
                            station=station,
                            kind=DefectEvent.Kind.ATTACHMENT,
                            actor=request.user,
                            metadata={"attachment_id": attachment.pk, "size": len(raw)},
                        )
                    audit(request.user, station, "defect.created", item, {"via": "web"})
                messages.success(request, "Mangel wurde angelegt.")
                return redirect("defect_detail_web", pk=item.pk)
    return render(
        request,
        "core/defect_form.html",
        {
            "priorities": Defect.Priority.choices,
            "categories": Defect.Category.choices,
        },
    )


@membership_required(allowed_roles=CONTENT_ROLES)
@require_http_methods(["GET", "POST"])
def defect_detail(request, pk):
    station = request.membership.station
    item = get_object_or_404(Defect.objects.select_related("owner", "created_by"), pk=pk, station=station)
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
                return redirect("defect_detail_web", pk=item.pk)
        elif action == "upload":
            upload = request.FILES.get("attachment")
            if upload is None:
                messages.error(request, "Bitte ein Bild auswählen.")
            elif upload.content_type not in ALLOWED_ATTACHMENT_TYPES:
                messages.error(request, "Erlaubt sind JPEG, PNG, WebP und PDF.")
            elif upload.size > MAX_ATTACHMENT_BYTES:
                messages.error(request, "Datei darf maximal 5 MiB groß sein.")
            else:
                raw = upload.read()
                if not attachment_is_valid(raw, upload.content_type):
                    messages.error(request, "Datei ist kein gültiges Bild und kein lesbares PDF.")
                else:
                    with transaction.atomic():
                        attachment = DefectAttachment.objects.create(
                            defect=item,
                            station=station,
                            filename=upload.name[:180],
                            content_type=upload.content_type,
                            data=raw,
                            size=len(raw),
                            uploaded_by=request.user,
                        )
                        DefectEvent.objects.create(
                            defect=item,
                            station=station,
                            kind=DefectEvent.Kind.ATTACHMENT,
                            actor=request.user,
                            metadata={"attachment_id": attachment.pk, "size": len(raw)},
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
            "attachments": item.attachments.select_related("uploaded_by").all(),
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
            if status not in StationAsset.Status.values:
                messages.error(request, "Ungültiger Asset-Status.")
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
                inv = get_object_or_404(InventoryItem.objects.select_for_update().select_related("holder"), station=station, item_id=item_id)
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
