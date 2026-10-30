"""API v1 fuer den Wachalltag-Vertrag aus Wachbuch-Client.

Diese Endpunkte machen die bisherige Behoerden-Demo produktiv nutzbar. Sie
verwenden die bestehende Token-/Stationsisolation und dieselben Rollen wie die
Uebergaben. Patienten-, Einsatz-, Alarmierungs- und Vorgangsdaten sind bewusst
nicht Teil des Schemas.
"""

from __future__ import annotations

import base64
import binascii
import calendar
import json
from datetime import timedelta
from io import BytesIO
from urllib.parse import quote

from PIL import Image, UnidentifiedImageError
from django.db import IntegrityError, transaction
from django.db.models import Count, Sum
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import get_valid_filename, slugify
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from core.access import CONTENT_ROLES
from core.device_status import IN_SERVICE, asset_locked_by_device, asset_release_blockers
from core.models import Checklist, HandoverEntry, Membership
from core.services import acknowledge_handover, audit
from core.wachalltag_models import (
    AssetEvent,
    ChecklistSchedule,
    DEFECT_WORKFLOW_ORDERING,
    Defect,
    DefectAttachment,
    DefectEvent,
    HandoverAck,
    InventoryEvent,
    InventoryItem,
    StationAsset,
)

from . import views as base

MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
MAX_ATTACHMENTS_PER_DEFECT = 8
MAX_ATTACHMENTS_PER_HANDOVER = 8
MAX_ATTACHMENT_TOTAL_BYTES = 12 * 1024 * 1024
MAX_ATTACHMENT_PIXELS = 25_000_000
ALLOWED_ATTACHMENT_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
ATTACHMENT_SUFFIX = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}
EXPECTED_IMAGE_FORMAT = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}


def _payload(response):
    if not response.content:
        return {}
    try:
        decoded = json.loads(response.content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _json_response_from(response, payload):
    outgoing = JsonResponse(payload, status=response.status_code)
    for key, value in response.items():
        if key.lower() not in {"content-type", "content-length"}:
            outgoing[key] = value
    return outgoing


def _scope(request, name):
    if not base._scope_allowed(request.api_token, name):
        return base._json_error(request, f"Scope {name} fehlt.", status=403)
    return None


def _content_role(request):
    if request.membership.role not in CONTENT_ROLES:
        return base._json_error(request, "Rolle hat keinen Zugriff auf den Wachalltag.", status=403)
    return None


def _write_role(request):
    if request.membership.role not in base.WRITE_ROLES:
        return base._json_error(request, "Rolle darf diese Einstellung nicht aendern.", status=403)
    return None


def _body(request):
    parsed = base._parse_json(request)
    if parsed is None or not isinstance(parsed, dict):
        return None
    return parsed


def _parse_due(value):
    if value in (None, ""):
        return None
    parsed = parse_datetime(str(value))
    if parsed is None:
        raise ValueError("Ungueltige ISO-8601-Frist.")
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _member_user(station, value):
    if value in (None, ""):
        return None
    username = str(value).strip()
    membership = (
        Membership.objects.filter(
            station=station,
            user__username=username,
            user__is_active=True,
            is_active=True,
        )
        .select_related("user")
        .first()
    )
    if membership is None:
        raise ValueError("Owner ist kein aktives Mitglied dieser Wache.")
    return membership.user


def _defect_json(item):
    attachment_count = getattr(item, "attachment_total", None)
    if attachment_count is None:
        attachment_count = item.attachments.count() if item.pk else 0
    return {
        "id": item.pk,
        "title": item.title,
        "description": item.description,
        "asset_ref": item.asset_ref,
        "priority": item.priority,
        "status": item.status,
        "owner": item.owner.username if item.owner_id else "",
        "due_at": item.due_at.isoformat() if item.due_at else None,
        "category": item.category,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
        "attachment_count": attachment_count,
    }


def _asset_json(item):
    return {
        "id": item.asset_id,
        "label": item.label,
        "kind": item.kind,
        "status": item.status,
        "note": item.note,
        "updated_at": item.updated_at.isoformat(),
    }


def _inventory_json(item):
    return {
        "id": item.item_id,
        "label": item.label,
        "kind": item.kind,
        "holder": item.holder.username if item.holder_id else None,
        "since": item.checked_out_at.isoformat() if item.checked_out_at else None,
        "note": item.note,
        "updated_at": item.updated_at.isoformat(),
    }


def _ack_json(item):
    return {
        "handover_id": item.handover_id,
        "by": item.user.username,
        "at": item.created_at.isoformat(),
    }


def _attachment_json(item):
    return {
        "id": item.pk,
        "defect_id": item.defect_id,
        "filename": item.filename,
        "content_type": item.content_type,
        "size": item.size,
        "created_at": item.created_at.isoformat(),
        "uploaded_by": item.uploaded_by.username,
        "download_url": f"/api/v1/attachments/{item.pk}/",
    }


def _image_matches(data, content_type):
    if content_type == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


def _pdf_is_readable(data):
    """Grobe Prüfung: echtes PDF-Signatur und ein EOF-Marker."""
    return data.startswith(b"%PDF-") and b"%%EOF" in data[-2048:]


def attachment_is_valid(data, content_type):
    """Prüft Bild- und PDF-Anhänge vor dem Speichern."""
    if content_type == "application/pdf":
        return _pdf_is_readable(data)
    if content_type in EXPECTED_IMAGE_FORMAT:
        return _image_is_decodable(data, content_type)
    return False


def _image_is_decodable(data, content_type):
    """Reject spoofed/corrupt or unreasonably large images before persistence."""
    if not _image_matches(data, content_type):
        return False
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format != EXPECTED_IMAGE_FORMAT.get(content_type):
                return False
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > MAX_ATTACHMENT_PIXELS:
                return False
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return False
    return True


# ---- Existing API wrappers -------------------------------------------------


@csrf_exempt
@require_GET
def api_root(request):
    response = base.api_root(request)
    if response.status_code != 200:
        return response
    data = _payload(response)
    endpoints = data.setdefault("endpoints", {})
    endpoints.update(
        {
            "defects": "/api/v1/defects/",
            "assets": "/api/v1/assets/",
            "inventory": "/api/v1/inventory/",
            "reports": "/api/v1/reports/",
            "attachments": "/api/v1/attachments/{id}/",
        }
    )
    data["capabilities"] = {
        "defects": True,
        "assets": True,
        "inventory": True,
        "handover_ack": True,
        "defect_attachments": True,
        "checklist_schedules": True,
        "reports": True,
        "offline_safe_reads": True,
    }
    return _json_response_from(response, data)


@csrf_exempt
@require_GET
def me(request):
    response = base.me(request)
    if response.status_code != 200:
        return response
    data = _payload(response)
    membership = data.get("membership")
    if isinstance(membership, dict):
        station = membership.get("station")
        if isinstance(station, dict):
            modules = station.setdefault("modules", {})
            modules.update(
                {
                    "defects": True,
                    "assets": True,
                    "inventory": True,
                    "reports": True,
                    "attachments": True,
                }
            )
    return _json_response_from(response, data)


@csrf_exempt
@require_GET
def overview(request):
    response = base.overview(request)
    if response.status_code != 200:
        return response
    data = _payload(response)
    modules = data.setdefault("modules", {})
    modules.update(
        {
            "defects": True,
            "assets": True,
            "inventory": True,
            "reports": True,
            "attachments": True,
        }
    )
    station_id = data.get("station", {}).get("id") if isinstance(data.get("station"), dict) else None
    if station_id:
        now = timezone.now()
        data["wachalltag"] = {
            "open_defects": Defect.objects.filter(station_id=station_id).exclude(status=Defect.Status.DONE).count(),
            "overdue_defects": Defect.objects.filter(station_id=station_id, due_at__lt=now).exclude(status=Defect.Status.DONE).count(),
            "assets_not_ready": StationAsset.objects.filter(station_id=station_id).exclude(status=StationAsset.Status.READY).count(),
        }
    return _json_response_from(response, data)


@csrf_exempt
@require_GET
def checklists_api(request):
    response = base.checklists_api(request)
    if response.status_code != 200:
        return response
    data = _payload(response)
    results = data.get("results")
    if not isinstance(results, list):
        return _json_response_from(response, data)
    ids = [item.get("id") for item in results if isinstance(item, dict) and isinstance(item.get("id"), int)]
    schedules = {
        schedule.checklist_id: schedule
        for schedule in ChecklistSchedule.objects.filter(checklist_id__in=ids)
    }
    now = timezone.now()
    for item in results:
        if not isinstance(item, dict):
            continue
        schedule = schedules.get(item.get("id"))
        item["interval"] = schedule.interval if schedule else ""
        item["due_next"] = schedule.due_next.isoformat() if schedule and schedule.due_next else None
        item["overdue"] = bool(schedule and schedule.due_next and schedule.due_next < now)
    return _json_response_from(response, data)


def _next_month(value):
    month = value.month + 1
    year = value.year
    if month == 13:
        month = 1
        year += 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _step_schedule(value, interval):
    if interval == ChecklistSchedule.Interval.DAILY:
        return value + timedelta(days=1)
    if interval == ChecklistSchedule.Interval.WEEKLY:
        return value + timedelta(days=7)
    return _next_month(value)


def _advance_schedule(schedule):
    """Advance exactly along the configured cadence to the first future due."""
    now = timezone.now()
    next_due = _step_schedule(schedule.due_next or now, schedule.interval)
    while next_due <= now:
        next_due = _step_schedule(next_due, schedule.interval)
    schedule.due_next = next_due
    schedule.save(update_fields=["due_next", "updated_at"])


def advance_checklist_schedule(checklist_id):
    """Nach einem Abschluss das Prüfintervall weiterschalten (Web und API)."""
    schedule = ChecklistSchedule.objects.select_for_update().filter(checklist_id=checklist_id).first()
    if schedule is not None:
        _advance_schedule(schedule)
    return schedule


def defect_attachment_limit_error(locked_defect, size):
    """Prüft Anzahl und Gesamtgröße der Anhänge eines (gesperrten) Mangels.

    Liefert ``(Meldung, HTTP-Status)`` oder ``None``. Aufrufer halten die
    Zeilensperre auf ``locked_defect`` bis zum Anlegen des Anhangs.
    """
    stats = DefectAttachment.objects.filter(defect=locked_defect).aggregate(
        count=Count("id"),
        total=Sum("size"),
    )
    if int(stats["count"] or 0) >= MAX_ATTACHMENTS_PER_DEFECT:
        return f"Maximal {MAX_ATTACHMENTS_PER_DEFECT} Fotos pro Mangel sind erlaubt.", 409
    if int(stats["total"] or 0) + size > MAX_ATTACHMENT_TOTAL_BYTES:
        return "Gesamtgroesse der Fotos pro Mangel darf 12 MiB nicht ueberschreiten.", 413
    return None


@csrf_exempt
@require_POST
def checklist_complete_api(request, pk):
    response = base.checklist_complete_api(request, pk)
    if response.status_code in {200, 201}:
        with transaction.atomic():
            schedule = advance_checklist_schedule(pk)
        data = _payload(response)
        if schedule is not None:
            data["interval"] = schedule.interval
            data["due_next"] = schedule.due_next.isoformat() if schedule.due_next else None
            data["overdue"] = False
            response = _json_response_from(response, data)
    return response


# ---- Defects ---------------------------------------------------------------


def _int_param(request, name, *, default, minimum, maximum):
    try:
        value = int(request.GET.get(name, default))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def _page_link(request, offset, limit):
    """Relativer Link auf eine andere Seite derselben Liste (Filter bleiben erhalten)."""
    query = request.GET.copy()
    query["offset"] = str(offset)
    query["limit"] = str(limit)
    return f"{request.path}?{query.urlencode()}"


@csrf_exempt
@require_http_methods(["GET", "POST"])
@base.api_token_required
def defects_list(request):
    station = request.membership.station
    if request.method == "GET":
        if (error := _scope(request, "read:handovers")) or (error := _content_role(request)):
            return error
        qs = (
            Defect.objects.filter(station=station)
            .select_related("owner")
            .annotate(attachment_total=Count("attachments"))
            .order_by(*DEFECT_WORKFLOW_ORDERING)
        )
        status = request.GET.get("status")
        priority = request.GET.get("priority")
        if status in Defect.Status.values:
            qs = qs.filter(status=status)
        if priority in Defect.Priority.values:
            qs = qs.filter(priority=priority)
        if request.GET.get("overdue") in {"1", "true", "yes"}:
            qs = qs.filter(due_at__lt=timezone.now()).exclude(status=Defect.Status.DONE)
        if request.GET.get("active") in {"1", "true", "yes"}:
            qs = qs.exclude(status=Defect.Status.DONE)
        limit = _int_param(request, "limit", default=100, minimum=1, maximum=200)
        offset = _int_param(request, "offset", default=0, minimum=0, maximum=10**6)
        total = qs.count()
        results = [_defect_json(item) for item in qs[offset:offset + limit]]
        return JsonResponse({
            "ok": True,
            "count": total,
            "results": results,
            "next": _page_link(request, offset + limit, limit) if offset + limit < total else None,
            "previous": _page_link(request, max(0, offset - limit), limit) if offset > 0 else None,
        })

    if (error := _scope(request, "write:handovers")) or (error := _content_role(request)):
        return error
    body = _body(request)
    if body is None:
        return base._json_error(request, "JSON-Koerper erwartet.", status=400)
    title = str(body.get("title") or "").strip()
    if not title or len(title) > 160:
        return base._json_error(request, "Titel ist erforderlich (max. 160 Zeichen).", status=422)
    priority = str(body.get("priority") or Defect.Priority.NORMAL)
    category = str(body.get("category") or Defect.Category.TASK)
    if priority not in Defect.Priority.values or category not in Defect.Category.values:
        return base._json_error(request, "Prioritaet oder Kategorie ist ungueltig.", status=422)
    try:
        due_at = _parse_due(body.get("due_at"))
        owner = _member_user(station, body.get("owner"))
    except ValueError as exc:
        return base._json_error(request, str(exc), status=422)
    description = str(body.get("description") or "")[:3000]
    asset_ref = str(body.get("asset_ref") or "")[:160]
    with transaction.atomic():
        item = Defect.objects.create(
            station=station,
            title=title,
            description=description,
            asset_ref=asset_ref,
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
            metadata={"fields": ["title", "description", "asset_ref", "priority", "owner", "due_at", "category"]},
        )
        audit(request.user, station, "defect.created", item, {"fields": ["title", "priority", "category", "owner", "due_at"]})
    return JsonResponse({"ok": True, **_defect_json(item)}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PATCH"])
@base.api_token_required
def defect_detail(request, pk):
    station = request.membership.station
    if request.method == "GET":
        if (error := _scope(request, "read:handovers")) or (error := _content_role(request)):
            return error
        item = Defect.objects.filter(pk=pk, station=station).select_related("owner").first()
        if item is None:
            return base._json_error(request, "Mangel nicht gefunden.", status=404)
        data = _defect_json(item)
        data["events"] = [
            {
                "kind": event.kind,
                "from_status": event.from_status,
                "to_status": event.to_status,
                "by": event.actor.username,
                "at": event.created_at.isoformat(),
            }
            for event in item.events.select_related("actor").all()[:100]
        ]
        data["attachments"] = [_attachment_json(a) for a in item.attachments.select_related("uploaded_by").defer("data")]
        return JsonResponse({"ok": True, **data})

    if (error := _scope(request, "write:handovers")) or (error := _content_role(request)):
        return error
    body = _body(request)
    if body is None:
        return base._json_error(request, "JSON-Koerper erwartet.", status=400)
    with transaction.atomic():
        item = Defect.objects.select_for_update().filter(pk=pk, station=station).first()
        if item is None:
            return base._json_error(request, "Mangel nicht gefunden.", status=404)
        changed = []
        if "description" in body:
            item.description = str(body.get("description") or "")[:3000]
            changed.append("description")
        if "asset_ref" in body:
            item.asset_ref = str(body.get("asset_ref") or "")[:160]
            changed.append("asset_ref")
        if "owner" in body:
            try:
                item.owner = _member_user(station, body.get("owner"))
            except ValueError as exc:
                return base._json_error(request, str(exc), status=422)
            changed.append("owner")
        if "due_at" in body:
            try:
                item.due_at = _parse_due(body.get("due_at"))
            except ValueError as exc:
                return base._json_error(request, str(exc), status=422)
            changed.append("due_at")
        if "priority" in body:
            priority = str(body.get("priority") or "")
            if priority not in Defect.Priority.values:
                return base._json_error(request, "Prioritaet ist ungueltig.", status=422)
            item.priority = priority
            changed.append("priority")
        if not changed:
            return base._json_error(request, "Keine aenderbaren Felder angegeben.", status=422)
        item.save()
        DefectEvent.objects.create(
            defect=item,
            station=station,
            kind=DefectEvent.Kind.UPDATED,
            actor=request.user,
            metadata={"fields": changed},
        )
        audit(request.user, station, "defect.updated", item, {"fields": changed})
    return JsonResponse({"ok": True, **_defect_json(item)})


@csrf_exempt
@require_POST
@base.api_token_required
def defect_status(request, pk):
    station = request.membership.station
    if (error := _scope(request, "write:handovers")) or (error := _content_role(request)):
        return error
    body = _body(request) or {}
    status = str(body.get("status") or "")
    if status not in Defect.Status.values:
        return base._json_error(request, "Status ist ungueltig.", status=422)
    if status == Defect.Status.DONE and request.membership.role not in base.WRITE_ROLES:
        return base._json_error(request, "Nur Schichtleitung oder Admin darf Maengel abschliessen.", status=403)
    with transaction.atomic():
        item = (
            Defect.objects.select_for_update(of=("self",))
            .filter(pk=pk, station=station)
            .select_related("owner")
            .first()
        )
        if item is None:
            return base._json_error(request, "Mangel nicht gefunden.", status=404)
        previous = item.status
        if previous != status:
            item.status = status
            item.closed_at = timezone.now() if status == Defect.Status.DONE else None
            item.save(update_fields=["status", "closed_at", "updated_at"])
            DefectEvent.objects.create(
                defect=item,
                station=station,
                kind=DefectEvent.Kind.STATUS,
                from_status=previous,
                to_status=status,
                actor=request.user,
            )
            audit(request.user, station, "defect.status_changed", item, {"from": previous, "to": status})
    return JsonResponse({"ok": True, **_defect_json(item)})


# ---- Assets ----------------------------------------------------------------


@csrf_exempt
@require_http_methods(["GET", "POST"])
@base.api_token_required
def assets_list(request):
    station = request.membership.station
    if request.method == "GET":
        if (error := _scope(request, "read:handovers")) or (error := _content_role(request)):
            return error
        items = StationAsset.objects.filter(station=station)
        return JsonResponse({"ok": True, "results": [_asset_json(item) for item in items]})
    if (error := _scope(request, "write:handovers")) or (error := _write_role(request)):
        return error
    body = _body(request) or {}
    label = str(body.get("label") or "").strip()
    asset_id = slugify(str(body.get("id") or body.get("asset_id") or label))[:64]
    kind = str(body.get("kind") or StationAsset.Kind.DEVICE)
    status = str(body.get("status") or StationAsset.Status.READY)
    if not label or not asset_id or kind not in StationAsset.Kind.values or status not in StationAsset.Status.values:
        return base._json_error(request, "Asset-Daten sind ungueltig.", status=422)
    try:
        item = StationAsset.objects.create(
            station=station,
            asset_id=asset_id,
            label=label[:160],
            kind=kind,
            status=status,
            note=str(body.get("note") or "")[:300],
            updated_by=request.user,
        )
    except IntegrityError:
        return base._json_error(request, "Asset-ID existiert bereits.", status=409)
    AssetEvent.objects.create(asset=item, station=station, to_status=item.status, note=item.note, actor=request.user)
    audit(request.user, station, "asset.created", item, {"asset_id": asset_id, "status": status})
    return JsonResponse({"ok": True, **_asset_json(item)}, status=201)


@csrf_exempt
@require_POST
@base.api_token_required
def asset_status(request, asset_id):
    station = request.membership.station
    if (error := _scope(request, "write:handovers")) or (error := _write_role(request)):
        return error
    body = _body(request) or {}
    status = str(body.get("status") or "")
    if status not in StationAsset.Status.values:
        return base._json_error(request, "Asset-Status ist ungueltig.", status=422)
    note = str(body.get("note") or "")[:300]
    with transaction.atomic():
        item = StationAsset.objects.select_for_update().filter(station=station, asset_id=asset_id).first()
        if item is None:
            return base._json_error(request, "Asset nicht gefunden.", status=404)
        if status in IN_SERVICE and (blockers := asset_release_blockers(item)):
            numbers = ", ".join(f"#{defect.pk}" for defect in blockers)
            return base._json_error(request, f"Geraet bleibt gesperrt: offene Maengel {numbers}.", status=409)
        if status != StationAsset.Status.OOB and asset_locked_by_device(item):
            return base._json_error(
                request, "Geraet ist im Medizinproduktebuch gesperrt. Freigabe nur dort mit Funktionskontrolle.",
                status=409,
            )
        previous = item.status
        item.status = status
        item.note = note
        item.updated_by = request.user
        item.save(update_fields=["status", "note", "updated_by", "updated_at"])
        if previous != status or note:
            AssetEvent.objects.create(asset=item, station=station, from_status=previous, to_status=status, note=note, actor=request.user)
            audit(request.user, station, "asset.status_changed", item, {"from": previous, "to": status, "note": bool(note)})
    return JsonResponse({"ok": True, **_asset_json(item)})


# ---- Inventory -------------------------------------------------------------


@csrf_exempt
@require_http_methods(["GET", "POST"])
@base.api_token_required
def inventory_list(request):
    station = request.membership.station
    if request.method == "GET":
        if (error := _scope(request, "read:handovers")) or (error := _content_role(request)):
            return error
        items = InventoryItem.objects.filter(station=station).select_related("holder")
        return JsonResponse({"ok": True, "results": [_inventory_json(item) for item in items]})
    if (error := _scope(request, "write:handovers")) or (error := _write_role(request)):
        return error
    body = _body(request) or {}
    label = str(body.get("label") or "").strip()
    item_id = slugify(str(body.get("id") or body.get("item_id") or label))[:64]
    kind = str(body.get("kind") or InventoryItem.Kind.DEVICE)
    if not label or not item_id or kind not in InventoryItem.Kind.values:
        return base._json_error(request, "Inventar-Daten sind ungueltig.", status=422)
    try:
        item = InventoryItem.objects.create(
            station=station,
            item_id=item_id,
            label=label[:160],
            kind=kind,
            note=str(body.get("note") or "")[:300],
            updated_by=request.user,
        )
    except IntegrityError:
        return base._json_error(request, "Inventar-ID existiert bereits.", status=409)
    audit(request.user, station, "inventory.created", item, {"item_id": item_id, "kind": kind})
    return JsonResponse({"ok": True, **_inventory_json(item)}, status=201)


@csrf_exempt
@require_POST
@base.api_token_required
def inventory_checkout(request, item_id):
    station = request.membership.station
    if (error := _scope(request, "write:handovers")) or (error := _content_role(request)):
        return error
    with transaction.atomic():
        item = (
            InventoryItem.objects.select_for_update(of=("self",))
            .filter(station=station, item_id=item_id)
            .select_related("holder")
            .first()
        )
        if item is None:
            return base._json_error(request, "Inventar nicht gefunden.", status=404)
        if item.holder_id and item.holder_id != request.user.id:
            return base._json_error(request, f"Bereits ausgegeben an {item.holder.username}.", status=409)
        if not item.holder_id:
            item.holder = request.user
            item.checked_out_at = timezone.now()
            item.updated_by = request.user
            item.save(update_fields=["holder", "checked_out_at", "updated_by", "updated_at"])
            InventoryEvent.objects.create(item=item, station=station, action=InventoryEvent.Action.CHECKOUT, actor=request.user, holder=request.user)
            audit(request.user, station, "inventory.checkout", item, {"item_id": item.item_id})
    return JsonResponse({"ok": True, **_inventory_json(item)})


@csrf_exempt
@require_POST
@base.api_token_required
def inventory_checkin(request, item_id):
    station = request.membership.station
    if (error := _scope(request, "write:handovers")) or (error := _content_role(request)):
        return error
    with transaction.atomic():
        item = (
            InventoryItem.objects.select_for_update(of=("self",))
            .filter(station=station, item_id=item_id)
            .select_related("holder")
            .first()
        )
        if item is None:
            return base._json_error(request, "Inventar nicht gefunden.", status=404)
        previous_holder = item.holder
        if previous_holder and previous_holder.id != request.user.id and request.membership.role not in base.WRITE_ROLES:
            return base._json_error(request, "Nur Ausleiher, Schichtleitung oder Admin darf zurueckgeben.", status=403)
        if previous_holder:
            item.holder = None
            item.checked_out_at = None
            item.updated_by = request.user
            item.save(update_fields=["holder", "checked_out_at", "updated_by", "updated_at"])
            InventoryEvent.objects.create(item=item, station=station, action=InventoryEvent.Action.CHECKIN, actor=request.user, holder=previous_holder)
            audit(request.user, station, "inventory.checkin", item, {"item_id": item.item_id, "previous_holder": previous_holder.username})
    return JsonResponse({"ok": True, **_inventory_json(item)})


# ---- Handover acknowledgements --------------------------------------------


@csrf_exempt
@require_GET
@base.api_token_required
def handover_acks(request, pk):
    station = request.membership.station
    if (error := _scope(request, "read:handovers")) or (error := _content_role(request)):
        return error
    handover = HandoverEntry.objects.filter(pk=pk, station=station).first()
    if handover is None:
        return base._json_error(request, "Uebergabe nicht gefunden.", status=404)
    acks = HandoverAck.objects.filter(handover=handover).select_related("user")
    return JsonResponse({"ok": True, "results": [_ack_json(item) for item in acks]})


@csrf_exempt
@require_POST
@base.api_token_required
def handover_ack(request, pk):
    station = request.membership.station
    if (error := _scope(request, "write:handovers")) or (error := _content_role(request)):
        return error
    handover = HandoverEntry.objects.filter(pk=pk, station=station).first()
    if handover is None:
        return base._json_error(request, "Uebergabe nicht gefunden.", status=404)
    item, created = acknowledge_handover(handover, request.user)
    return JsonResponse({"ok": True, **_ack_json(item)}, status=201 if created else 200)


# ---- Attachments -----------------------------------------------------------


@csrf_exempt
@require_http_methods(["GET", "POST"])
@base.api_token_required
def defect_attachments(request, pk):
    station = request.membership.station
    defect = Defect.objects.filter(pk=pk, station=station).first()
    if defect is None:
        return base._json_error(request, "Mangel nicht gefunden.", status=404)
    if request.method == "GET":
        if (error := _scope(request, "read:handovers")) or (error := _content_role(request)):
            return error
        items = defect.attachments.select_related("uploaded_by").defer("data")
        return JsonResponse({"ok": True, "results": [_attachment_json(item) for item in items]})
    if (error := _scope(request, "write:handovers")) or (error := _content_role(request)):
        return error
    body = _body(request) or {}
    filename = get_valid_filename(str(body.get("filename") or "foto"))[:180]
    content_type = str(body.get("content_type") or "").lower()
    if content_type == "image/jpg":
        content_type = "image/jpeg"
    if content_type not in ALLOWED_ATTACHMENT_TYPES:
        return base._json_error(request, "Nur JPEG, PNG, WebP oder PDF sind erlaubt.", status=415)
    encoded = body.get("data_base64")
    if not isinstance(encoded, str) or not encoded:
        return base._json_error(request, "Bilddaten fehlen.", status=422)
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return base._json_error(request, "Bilddaten sind kein gueltiges Base64.", status=422)
    if not raw or len(raw) > MAX_ATTACHMENT_BYTES:
        return base._json_error(request, "Bild darf maximal 5 MiB gross sein.", status=413)
    if not attachment_is_valid(raw, content_type):
        return base._json_error(request, "Datei ist kein gueltiges Bild oder PDF.", status=415)
    with transaction.atomic():
        locked_defect = Defect.objects.select_for_update().filter(pk=pk, station=station).first()
        if locked_defect is None:
            return base._json_error(request, "Mangel nicht gefunden.", status=404)
        if limit := defect_attachment_limit_error(locked_defect, len(raw)):
            message, status = limit
            return base._json_error(request, message, status=status)
        item = DefectAttachment.objects.create(
            defect=locked_defect,
            station=station,
            filename=filename,
            content_type=content_type,
            data=raw,
            size=len(raw),
            uploaded_by=request.user,
        )
        DefectEvent.objects.create(
            defect=locked_defect,
            station=station,
            kind=DefectEvent.Kind.ATTACHMENT,
            actor=request.user,
            metadata={"attachment_id": item.pk, "content_type": content_type, "size": len(raw)},
        )
        audit(
            request.user,
            station,
            "defect.attachment_added",
            locked_defect,
            {"attachment_id": item.pk, "size": len(raw)},
        )
    return JsonResponse({"ok": True, **_attachment_json(item)}, status=201)


@csrf_exempt
@require_GET
@base.api_token_required
def attachment_download(request, pk):
    if (error := _scope(request, "read:handovers")) or (error := _content_role(request)):
        return error
    item = DefectAttachment.objects.filter(pk=pk, station=request.membership.station).first()
    if item is None:
        return base._json_error(request, "Anhang nicht gefunden.", status=404)
    response = HttpResponse(bytes(item.data), content_type=item.content_type)
    response["Content-Length"] = str(item.size)
    response["Content-Disposition"] = f"inline; filename*=UTF-8''{quote(item.filename)}"
    response["Cache-Control"] = "private, no-store"
    return response


# ---- Checklist schedules and reports --------------------------------------


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
@base.api_token_required
def checklist_schedule(request, pk):
    station = request.membership.station
    checklist = Checklist.objects.filter(pk=pk, station=station, is_active=True).first()
    if checklist is None:
        return base._json_error(request, "Checkliste nicht gefunden.", status=404)
    if request.method == "GET":
        if (error := _scope(request, "read:checklists")) or (error := _content_role(request)):
            return error
        schedule = ChecklistSchedule.objects.filter(checklist=checklist).first()
        return JsonResponse(
            {
                "ok": True,
                "interval": schedule.interval if schedule else "",
                "due_next": schedule.due_next.isoformat() if schedule and schedule.due_next else None,
                "overdue": bool(schedule and schedule.due_next and schedule.due_next < timezone.now()),
            }
        )
    if (error := _scope(request, "write:checklists")) or (error := _write_role(request)):
        return error
    if request.method == "DELETE":
        ChecklistSchedule.objects.filter(checklist=checklist).delete()
        audit(request.user, station, "checklist.schedule_removed", checklist, {})
        return JsonResponse({"ok": True})
    body = _body(request) or {}
    interval = str(body.get("interval") or "")
    if interval not in ChecklistSchedule.Interval.values:
        return base._json_error(request, "Intervall ist ungueltig.", status=422)
    try:
        due_next = _parse_due(body.get("due_next"))
    except ValueError as exc:
        return base._json_error(request, str(exc), status=422)
    schedule, _ = ChecklistSchedule.objects.update_or_create(
        checklist=checklist,
        defaults={"station": station, "interval": interval, "due_next": due_next},
    )
    audit(request.user, station, "checklist.schedule_updated", checklist, {"interval": interval, "due_next": bool(due_next)})
    return JsonResponse({"ok": True, "interval": schedule.interval, "due_next": schedule.due_next.isoformat() if schedule.due_next else None})


@csrf_exempt
@require_GET
@base.api_token_required
def reports(request):
    station = request.membership.station
    if (error := _scope(request, "read:handovers")) or (error := _content_role(request)):
        return error
    now = timezone.now()
    open_qs = Defect.objects.filter(station=station).exclude(status=Defect.Status.DONE)
    assets = StationAsset.objects.filter(station=station)
    asset_total = assets.count()
    asset_ready = assets.filter(status=StationAsset.Status.READY).count()
    overdue_checks = ChecklistSchedule.objects.filter(station=station, due_next__lt=now).count()
    overdue_defects = open_qs.filter(due_at__lt=now).count()
    oldest = open_qs.order_by("created_at").first()
    oldest_days = (now - oldest.created_at).days if oldest else 0
    return JsonResponse(
        {
            "ok": True,
            "open_defects": open_qs.count(),
            "overdue_defects": overdue_defects,
            # Veraltet seit 0.26.1: offene Mängel je Person sind Leistungsdaten
            # (AGENTS.md § 1). Das Feld bleibt für ältere Clients als leere
            # Liste erhalten und entfällt in einer späteren API-Version.
            "defects_by_owner": [],
            "oldest_open_days": oldest_days,
            "overdue_checks": overdue_checks,
            "assets_total": asset_total,
            "assets_ready": asset_ready,
            "asset_ready_percent": round((asset_ready / asset_total) * 100) if asset_total else 0,
            "inventory_out": InventoryItem.objects.filter(station=station, holder__isnull=False).count(),
            "unacknowledged_active_handovers": max(
                0,
                HandoverEntry.objects.filter(station=station).exclude(status=HandoverEntry.Status.DONE).count()
                - HandoverAck.objects.filter(station=station, user=request.user, handover__status__in=[HandoverEntry.Status.OPEN, HandoverEntry.Status.IN_PROGRESS]).count(),
            ),
        }
    )
