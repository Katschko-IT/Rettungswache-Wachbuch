"""Persönliche Benachrichtigungen und Push-Geräte für die Mobile-App.

- ``GET  /api/v1/benachrichtigungen/``                 Posteingang (ungelesen zuerst);
  ``?kinds=vehicle_ready,coffee_due`` liefert nur diese Arten, damit die App
  nur abfragt, was sie anzeigt
- ``POST /api/v1/benachrichtigungen/<id>/gelesen/``    als gelesen markieren
- ``POST /api/v1/benachrichtigungen/gelesen/``         alle ungelesenen der
  angegebenen Arten (``kinds`` als Liste im JSON oder kommagetrennt) als gelesen
  markieren
- ``GET  /api/v1/fahrzeuge/sperren/``                  laufende Sperren der eigenen
  Fahrzeuge; die App plant damit eine lokale Erinnerung zur Sperrzeit
- ``POST|DELETE /api/v1/push/geraete/``                APNs-/FCM-Token an- und abmelden
"""
from __future__ import annotations

from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import views as base
from .wachalltag import _body

MAX_TOKEN_LENGTH = 512


def _notification_json(item):
    return {
        "id": item.pk,
        "kind": item.kind,
        # Gleicher Schlüssel wie bei /fahrzeuge/sperren/: die App zeigt eine
        # bereits lokal geplante Erinnerung nicht ein zweites Mal.
        "key": item.dedupe_key,
        "title": item.title,
        "body": item.body,
        "url": item.url,
        "created_at": item.created_at.isoformat(),
        "read": item.read_at is not None,
    }


def parse_kinds(raw) -> list[str] | None:
    """Arten aus ``kinds`` (kommagetrennt oder Liste); ``None`` ohne Angabe.

    Unbekannte Arten werden ignoriert (ältere Server, neuere App).
    """
    from ..notification_models import UserNotification

    if raw in (None, ""):
        return None
    values = raw if isinstance(raw, (list, tuple)) else str(raw).split(",")
    known = set(UserNotification.Kind.values)
    return [value for value in dict.fromkeys(str(item).strip() for item in values) if value in known]


@csrf_exempt
@require_GET
@base.api_token_required
def notifications(request):
    if not base._scope_allowed(request.api_token, "read:me"):
        return base._json_error(request, "Scope read:me fehlt.", status=403)
    from ..notification_models import UserNotification

    qs = UserNotification.objects.filter(user=request.user, station=request.membership.station)
    kinds = parse_kinds(request.GET.get("kinds"))
    if kinds is not None:
        qs = qs.filter(kind__in=kinds)
    unread = list(qs.filter(read_at__isnull=True)[:50])
    recent = list(qs.filter(read_at__isnull=False)[:20])
    return base.JsonResponse({
        "ok": True,
        "unread_count": len(unread),
        "results": [_notification_json(item) for item in unread + recent],
    })


@csrf_exempt
@require_POST
@base.api_token_required
def notifications_read_kinds(request):
    """Alle ungelesenen Hinweise der genannten Arten als gelesen markieren."""
    if not base._scope_allowed(request.api_token, "read:me"):
        return base._json_error(request, "Scope read:me fehlt.", status=403)
    from ..notification_models import UserNotification

    body = _body(request) or {}
    kinds = parse_kinds(body.get("kinds") if "kinds" in body else request.GET.get("kinds"))
    if not kinds:
        return base._json_error(request, "kinds (bekannte Arten) ist erforderlich.", status=400)
    marked = UserNotification.objects.filter(
        user=request.user, station=request.membership.station, kind__in=kinds, read_at__isnull=True,
    ).update(read_at=timezone.now())
    return base.JsonResponse({"ok": True, "kinds": kinds, "marked": marked})


@csrf_exempt
@require_POST
@base.api_token_required
def notification_read(request, pk):
    if not base._scope_allowed(request.api_token, "read:me"):
        return base._json_error(request, "Scope read:me fehlt.", status=403)
    from ..notification_models import UserNotification

    item = UserNotification.objects.filter(
        pk=pk, user=request.user, station=request.membership.station,
    ).first()
    if item is None:
        return base._json_error(request, "Benachrichtigung nicht gefunden.", status=404)
    if item.read_at is None:
        item.read_at = timezone.now()
        item.save(update_fields=["read_at"])
    return base.JsonResponse({"ok": True, **_notification_json(item)})


@csrf_exempt
@require_GET
@base.api_token_required
def vehicle_locks(request):
    if not base._scope_allowed(request.api_token, "read:me"):
        return base._json_error(request, "Scope read:me fehlt.", status=403)
    station = request.membership.station
    if not station.fleet_enabled:
        return base.JsonResponse({"ok": True, "results": []})
    from ..crew_notifications import upcoming_locks_for_user

    return base.JsonResponse({"ok": True, "results": upcoming_locks_for_user(request.user, station)})


@csrf_exempt
@require_http_methods(["POST", "DELETE"])
@base.api_token_required
def push_devices(request):
    from ..notification_models import MobilePushDevice

    body = _body(request) or {}
    platform = str(body.get("platform") or "").lower()
    token = str(body.get("token") or "").strip()
    if platform not in MobilePushDevice.Platform.values or not token or len(token) > MAX_TOKEN_LENGTH:
        return base._json_error(request, "platform (ios/android) und token sind erforderlich.", status=400)
    if request.method == "DELETE":
        MobilePushDevice.objects.filter(user=request.user, platform=platform, token=token).delete()
        return base.JsonResponse({"ok": True, "registered": False})
    device, _created = MobilePushDevice.objects.update_or_create(
        platform=platform,
        token=token,
        defaults={
            # Ein Token gehört immer dem zuletzt angemeldeten Konto des Geräts.
            "user": request.user,
            "station": request.membership.station,
            "app_version": str(body.get("app_version") or "")[:40],
        },
    )
    return base.JsonResponse({"ok": True, "registered": True, "id": device.pk}, status=201)
