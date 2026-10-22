"""Versioned JSON API for future open-source iOS/Android clients.

Auth style follows Paperless-ngx / Nextcloud app passwords:
Authorization: Token <secret>
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.contrib.auth import authenticate
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from ..rate_limit import consume


from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Sum

from ..access import CONTENT_ROLES, get_membership
from ..errors import (
    ERROR_CODE_AUTH_REQUIRED,
    ERROR_CODE_CONFLICT,
    ERROR_CODE_FORBIDDEN,
    ERROR_CODE_NOT_FOUND,
    ERROR_CODE_PAYLOAD_TOO_LARGE,
    ERROR_CODE_RATE_LIMIT,
    ERROR_CODE_SERVER_ERROR,
    ERROR_CODE_UNSUPPORTED_MEDIA_TYPE,
    ERROR_CODE_VALIDATION,
    json_error,
    log_exception,
)
from ..forms import CalendarEventForm, CoffeeEntryForm, HandoverForm, HandoverStatusForm, PinboardNoteForm
from ..models import (
    ApiToken,
    CalendarEvent,
    Checklist,
    ChecklistCompletion,
    CoffeeEntry,
    HandoverEntry,
    Membership,
    PinboardNote,
)
from ..services import audit, change_handover_status, create_handover, create_pinboard_note
from ..version import APP_VERSION

API_VERSION = "v1"
TOKEN_PREFIX = "wb_"


# Rate Limiting Configuration for API Endpoints
API_RATE_LIMITS = {
    "token": {"limit": 10, "window_seconds": 60},  # 10 requests per minute
    "handovers_list": {"limit": 100, "window_seconds": 60},  # 100 requests per minute
    "handovers_create": {"limit": 30, "window_seconds": 60},  # 30 requests per minute
    "overview": {"limit": 60, "window_seconds": 60},  # 60 requests per minute
    "me": {"limit": 60, "window_seconds": 60},  # 60 requests per minute
    "default": {"limit": 120, "window_seconds": 60},  # 120 requests per minute
}


def api_rate_limit(bucket: str, get_key: callable = None):
    """Decorator to apply rate limiting to API endpoints.
    
    Args:
        bucket: The rate limit bucket name
        get_key: Function to extract rate limit key from request (default: IP address)
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            # Get rate limit configuration
            config = API_RATE_LIMITS.get(bucket, API_RATE_LIMITS["default"])
            limit = config["limit"]
            window_seconds = config["window_seconds"]
            
            # Extract key from request
            if get_key:
                raw_key = get_key(request)
            else:
                raw_key = getattr(request, "client_ip", None) or "unknown"
            
            # Check rate limit
            if not consume(bucket, raw_key, limit=limit, window_seconds=window_seconds):
                return _json_error(
                    request,
                    "Zu viele Anfragen. Bitte später erneut versuchen.",
                    status=429,
                    code=ERROR_CODE_RATE_LIMIT,
                )
            
            return view_func(request, *args, **kwargs)
        return wrapped_view
    return decorator
DEFAULT_TOKEN_TTL_DAYS = 90
WRITE_ROLES = {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN}
CASHIER_ROLES = {Membership.Role.CASHIER, Membership.Role.ADMIN}
DEFAULT_MOBILE_SCOPES = [
    "read:me",
    "read:handovers",
    "write:handovers",
    "read:calendar",
    "write:calendar",
    "read:coffee",
    "write:coffee",
    "read:checklists",
    "write:checklists",
    "read:chat",
    "write:chat",
    "read:pinboard",
    "write:pinboard",
]


def hash_api_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_api_token() -> tuple[str, str, str]:
    """Return (raw_token, token_hash, display_prefix)."""
    raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
    return raw, hash_api_token(raw), raw[:11]


def default_token_expiry():
    return timezone.now() + timedelta(days=DEFAULT_TOKEN_TTL_DAYS)


def _json_error(request, message, status=400, code=None, **extra):
    """Liefert eine kanonische JSON-Fehlerantwort mit Korrelations-ID.

    Bestehende Aufrufer verwenden ``message`` als Klartext. Der ``code``
    wird aus dem HTTP-Statuscode abgeleitet, wenn er fehlt.
    """
    status_to_code = {
        400: ERROR_CODE_VALIDATION,
        401: ERROR_CODE_AUTH_REQUIRED,
        403: ERROR_CODE_FORBIDDEN,
        404: ERROR_CODE_NOT_FOUND,
        409: ERROR_CODE_CONFLICT,
        413: ERROR_CODE_PAYLOAD_TOO_LARGE,
        415: ERROR_CODE_UNSUPPORTED_MEDIA_TYPE,
        422: ERROR_CODE_VALIDATION,
        429: ERROR_CODE_RATE_LIMIT,
    }
    resolved_code = code or status_to_code.get(status, "server_error")
    return json_error(
        request,
        resolved_code,
        message=message,
        status=status,
        extra=extra or None,
    )


def _api_get_or_404(request, model, **kwargs):
    """Return (obj, None) or (None, JsonResponse 404) for API clients."""
    obj = model.objects.filter(**kwargs).first()
    if obj is None:
        return None, _json_error(request, "Nicht gefunden.", status=404)
    return obj, None


def _parse_json(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _token_rate_limit_key(request):
    """Rate-limit key for the /token/ endpoint: client IP plus attempted username.

    openapi_v1.yaml documents /token/ as an ``application/json`` POST, in which
    case ``request.POST`` is empty and the username only exists in the JSON
    body. Read the JSON body too so the per-account bucket is honoured for both
    JSON and form-encoded clients; otherwise the key collapses to IP-only and
    the documented per-username limiting silently disappears.
    """
    username = (request.POST.get("username") or "").strip()
    if not username:
        body = _parse_json(request)
        if isinstance(body, dict):
            username = str(body.get("username") or "").strip()
    client_ip = getattr(request, "client_ip", None) or "unknown"
    return f"{client_ip}|{username}"


def _extract_bearer_token(request):
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if not header:
        return None
    parts = header.split(None, 1)
    if len(parts) != 2:
        return None
    scheme, value = parts[0].lower(), parts[1].strip()
    if scheme in {"token", "bearer"} and value:
        return value
    return None


def resolve_api_token(raw_token: str):
    if not raw_token or len(raw_token) > 200:
        return None
    digest = hash_api_token(raw_token)
    token = (
        ApiToken.objects.select_related("user")
        .filter(token_hash=digest, is_active=True, user__is_active=True)
        .first()
    )
    if token is None:
        # Constant-time-ish miss path
        hmac.compare_digest(digest, "0" * 64)
        return None
    if token.expires_at and token.expires_at <= timezone.now():
        return None
    return token


def api_token_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        raw = _extract_bearer_token(request)
        if not raw:
            return _json_error(request, "Authentifizierung erforderlich.", status=401)
        token = resolve_api_token(raw)
        if token is None:
            return _json_error(request, "Ungültiges oder widerrufenes API-Token.", status=401)
        membership = get_membership(token.user)
        if membership is None:
            return _json_error(request, "Kein aktiver Wachenzugang.", status=403)
        ApiToken.objects.filter(pk=token.pk).update(last_used_at=timezone.now())
        request.user = token.user
        request.membership = membership
        request.api_token = token
        return view(request, *args, **kwargs)

    return wrapped


def _scope_allowed(token: ApiToken, scope: str) -> bool:
    scopes = token.scopes or []
    return scope in scopes


@csrf_exempt
@require_GET
def api_root(request):
    return JsonResponse({
        "ok": True,
        "name": getattr(settings, "APP_NAME", "Wachbuch"),
        "app_version": APP_VERSION,
        "api_version": API_VERSION,
        "authentication": ["Token", "Bearer"],
        "docs": "/api/v1/openapi.yaml",
        "endpoints": {
            "token": "/api/v1/token/",
            "token_revoke": "/api/v1/token/",
            "anmeldung": "/api/v1/anmeldung/",
            "me": "/api/v1/me/",
            "status": "/api/v1/status/",
            "uebersicht": "/api/v1/uebersicht/",
            "handovers": "/api/v1/handovers/",
            "uebergaben": "/api/v1/uebergaben/",
            "kalender": "/api/v1/kalender/",
            "kaffeekasse": "/api/v1/kaffeekasse/",
            "checklisten": "/api/v1/checklisten/",
            "chat": "/api/v1/chat/",
            "chat_identity": "/api/v1/chat/identity/",
            "post": "/api/v1/post/",
            "pinnwand": "/api/v1/pinnwand/",
            "openapi": "/api/v1/openapi.yaml",
        },
        "mobile_clients": {
            "status": "unified",
            "repo": "https://github.com/Katschko-IT/Wachbuch-Client",
            "notes": "Widerrufbare App-Tokens (wb_…) plus deutsche Alias-Pfade aus PR#12.",
        },
    })


@csrf_exempt
@require_GET
def openapi_spec(request):
    from pathlib import Path

    path = Path(__file__).resolve().parent / "openapi_v1.yaml"
    return HttpResponse(path.read_text(encoding="utf-8"), content_type="application/yaml; charset=utf-8")


@csrf_exempt
@require_http_methods(["POST", "DELETE"])
def token_endpoint(request):
    """POST mints a token; DELETE revokes the token presented in Authorization."""
    if request.method == "DELETE":
        return revoke_current_token(request)
    return obtain_token(request)


@csrf_exempt
@require_POST
@api_rate_limit("token", get_key=_token_rate_limit_key)
def obtain_token(request):
    """Paperless-style token exchange: username + password → API token."""
    body = _parse_json(request)
    if body is None:
        # also accept form-encoded like Paperless
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        label = (request.POST.get("label") or "Mobile App").strip()[:120]
    else:
        username = str(body.get("username") or "").strip()
        password = str(body.get("password") or "")
        label = str(body.get("label") or "Mobile App").strip()[:120]
    if not username or not password:
        return _json_error(request, "Benutzername und Passwort erforderlich.")
    user = authenticate(request, username=username, password=password)
    if user is None or not user.is_active:
        return _json_error(request, "Anmeldung fehlgeschlagen.", status=401)
    membership = get_membership(user)
    if membership is None:
        return _json_error(request, "Kein aktiver Wachenzugang.", status=403)
    from ..mfa import mfa_required, user_has_confirmed_mfa

    if user_has_confirmed_mfa(user):
        return _json_error(request, 
            "Für dieses Konto ist MFA aktiv. Bitte ein App-Token unter /konto/api/ erzeugen.",
            status=403,
            code="mfa_required",
        )
    if mfa_required():
        return _json_error(request,
            "MFA ist verpflichtend. Bitte zuerst die Zwei-Faktor-Anmeldung unter /konto/mfa/ einrichten.",
            status=403,
            code="mfa_setup_required",
        )
    from axes.utils import reset as axes_reset

    axes_reset(username=username)
    expires_at = default_token_expiry()
    raw, token_hash, prefix = generate_api_token()
    token = ApiToken.objects.create(
        user=user,
        label=label or "Mobile App",
        token_prefix=prefix,
        token_hash=token_hash,
        scopes=list(DEFAULT_MOBILE_SCOPES),
        expires_at=expires_at,
    )
    audit(user, membership.station, "api.token_created", token, {
        "fields": ["label", "scopes", "expires_at"],
        "via": "api.token",
    })
    return JsonResponse({
        "ok": True,
        "token": raw,
        "token_prefix": prefix,
        "api_version": API_VERSION,
        "expires_in": DEFAULT_TOKEN_TTL_DAYS * 24 * 3600,
        "expires_at": expires_at.isoformat(),
        "has_membership": True,
        "station": membership.station.name,
        "role": membership.role,
    })


def revoke_current_token(request):
    """Deactivate only the presented app token. Logout remains possible offline.

    Bewusst ohne Mitgliedschaftsprüfung: Auch wer keinen aktiven Wachenzugang
    mehr hat, muss sein eigenes Token beim Abmelden widerrufen können.
    """
    raw = _extract_bearer_token(request)
    if not raw:
        return _json_error(request, "Authentifizierung erforderlich.", status=401)
    token = resolve_api_token(raw)
    if token is None:
        return _json_error(request, "Ungültiges oder widerrufenes API-Token.", status=401)
    membership = get_membership(token.user)
    updated = ApiToken.objects.filter(pk=token.pk, is_active=True).update(is_active=False)
    if updated:
        audit(token.user, membership.station if membership else None, "api.token_revoked", token.user, {
            "fields": ["is_active"],
            "via": "api.token",
            "token_prefix": token.token_prefix,
        })
    return JsonResponse({"ok": True, "revoked": True})


@csrf_exempt
@require_GET
@api_token_required
@api_rate_limit("me")
def me(request):
    if not _scope_allowed(request.api_token, "read:me"):
        return _json_error(request, "Scope read:me fehlt.", status=403)
    membership = request.membership
    station = membership.station
    return JsonResponse({
        "ok": True,
        "api_version": API_VERSION,
        "user": {
            "id": request.user.id,
            "username": request.user.username,
            "first_name": request.user.first_name,
            "last_name": request.user.last_name,
        },
        "membership": {
            "role": membership.role,
            "role_label": membership.get_role_display(),
            "station": {
                "id": station.id,
                "name": station.name,
                "slug": station.slug,
                "modules": {
                    "calendar": station.calendar_enabled,
                    "chat": station.chat_enabled,
                    "tasks": station.tasks_enabled,
                    "coffee": station.coffee_enabled,
                    "feeds": station.feeds_enabled,
                    "birthdays": station.birthdays_enabled,
                    "holidays": station.holidays_enabled,
                    "holiday_state": station.holiday_state,
                    "weather": station.weather_enabled,
                    "checklists": station.checklists_enabled,
                    "pinboard": station.pinboard_enabled,
                },
            },
        },
        "token": {
            "id": request.api_token.id,
            "label": request.api_token.label,
            "prefix": request.api_token.token_prefix,
            "scopes": request.api_token.scopes,
        },
    })


def _person(user):
    return {
        "id": user.pk,
        "username": user.username,
        "display_name": user.get_full_name() or user.username,
    }


def _handover_json(item, *, detail=False):
    data = {
        "id": item.pk,
        "title": item.title,
        "category": item.category,
        "priority": item.priority,
        "status": item.status,
        "updated_at": item.updated_at.isoformat(),
    }
    if detail:
        data["details"] = item.details
        data["created_at"] = item.created_at.isoformat()
        data["author"] = _person(item.author) if item.author_id else None
        data["version"] = item.version
    return data


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_token_required
@api_rate_limit("handovers_list")
def handovers_list(request):
    if request.method == "POST":
        return handover_create(request)
    if not _scope_allowed(request.api_token, "read:handovers"):
        return _json_error(request, "Scope read:handovers fehlt.", status=403)
    if request.membership.role not in CONTENT_ROLES:
        return _json_error(request, "Rolle hat keinen Zugriff auf Übergaben.", status=403)
    qs = (
        HandoverEntry.objects.filter(station=request.membership.station)
        .exclude(status=HandoverEntry.Status.DONE)
        .order_by("-updated_at")[:50]
    )
    results = [_handover_json(item) for item in qs]
    return JsonResponse({
        "ok": True,
        "api_version": API_VERSION,
        "count": len(results),
        "results": results,
        "next": None,
        "previous": None,
    })


@csrf_exempt
@require_GET
def api_status(request):
    """Auth-optional status for clients (German alias: /status/)."""
    raw = _extract_bearer_token(request)
    authenticated = False
    has_membership = False
    station_name = None
    role = None
    if raw:
        token = resolve_api_token(raw)
        if token is not None:
            authenticated = True
            membership = get_membership(token.user)
            if membership is not None:
                has_membership = True
                station_name = membership.station.name
                role = membership.role
    elif request.user.is_authenticated:
        authenticated = True
        membership = get_membership(request.user)
        if membership is not None:
            has_membership = True
            station_name = membership.station.name
            role = membership.role
    payload = {
        "ok": True,
        "api_version": API_VERSION,
        "app_version": APP_VERSION,
        "authenticated": authenticated,
        "has_membership": has_membership,
    }
    if station_name is not None:
        payload["station"] = station_name
        payload["role"] = role
    return JsonResponse(payload)


@csrf_exempt
@require_GET
@api_token_required
@api_rate_limit("overview")
def overview(request):
    """Dashboard summary (German alias: /uebersicht/)."""
    if not _scope_allowed(request.api_token, "read:me"):
        return _json_error(request, "Scope read:me fehlt.", status=403)
    if request.membership.role not in CONTENT_ROLES:
        return _json_error(request, "Rolle hat keinen Zugriff auf die Übersicht.", status=403)
    station = request.membership.station
    handovers = {"open_count": 0, "urgent_count": 0, "items": []}
    if _scope_allowed(request.api_token, "read:handovers"):
        open_qs = HandoverEntry.objects.filter(station=station).exclude(
            status=HandoverEntry.Status.DONE
        )
        handovers = {
            "open_count": open_qs.count(),
            "urgent_count": open_qs.filter(priority=HandoverEntry.Priority.URGENT).count(),
            "items": [_handover_json(item) for item in open_qs.order_by("-updated_at")[:5]],
        }
    return JsonResponse({
        "ok": True,
        "api_version": API_VERSION,
        "station": {"id": station.id, "name": station.name, "slug": station.slug},
        "role": request.membership.role,
        "role_label": request.membership.get_role_display(),
        "modules": {
            "calendar": station.calendar_enabled,
            "chat": station.chat_enabled,
            "tasks": station.tasks_enabled,
            "coffee": station.coffee_enabled,
            "feeds": station.feeds_enabled,
            "birthdays": station.birthdays_enabled,
            "holidays": station.holidays_enabled,
            "holiday_state": station.holiday_state,
            "weather": station.weather_enabled,
            "checklists": station.checklists_enabled,
            "pinboard": station.pinboard_enabled,
        },
        "handovers": handovers,
    })


def handover_create(request):
    if not _scope_allowed(request.api_token, "write:handovers"):
        return _json_error(request, "Scope write:handovers fehlt.", status=403)
    if request.membership.role not in CONTENT_ROLES:
        return _json_error(request, "Rolle darf keine Übergaben anlegen.", status=403)
    body = _parse_json(request)
    if body is None:
        return _json_error(request, "JSON-Körper erwartet.")
    form = HandoverForm(body)
    if not form.is_valid():
        return _json_error(
            request,
            "Eingaben sind ungültig.",
            status=422,
            fields=form.errors,
        )
    handover = create_handover(form, request.membership)
    return JsonResponse({"ok": True, **_handover_json(handover, detail=True)}, status=201)


@csrf_exempt
@require_GET
@api_token_required
def handover_detail(request, pk):
    if not _scope_allowed(request.api_token, "read:handovers"):
        return _json_error(request, "Scope read:handovers fehlt.", status=403)
    if request.membership.role not in CONTENT_ROLES:
        return _json_error(request, "Rolle hat keinen Zugriff auf Übergaben.", status=403)
    handover, err = _api_get_or_404(request, HandoverEntry, pk=pk, station=request.membership.station)
    if err:
        return err
    return JsonResponse({"ok": True, **_handover_json(handover, detail=True)})


@csrf_exempt
@require_POST
@api_token_required
def handover_set_status(request, pk):
    if not _scope_allowed(request.api_token, "write:handovers"):
        return _json_error(request, "Scope write:handovers fehlt.", status=403)
    if request.membership.role not in WRITE_ROLES:
        return _json_error(request, "Rolle darf den Status nicht ändern.", status=403)
    handover, err = _api_get_or_404(request, HandoverEntry, pk=pk, station=request.membership.station)
    if err:
        return err
    body = _parse_json(request) or {}
    form = HandoverStatusForm(body, instance=handover)
    if not form.is_valid():
        return _json_error(
            request,
            "Status ungültig.",
            status=422,
            fields=form.errors,
        )
    updated = change_handover_status(handover, form.cleaned_data["status"], request.membership)
    return JsonResponse({"ok": True, **_handover_json(updated, detail=True)})


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_token_required
def calendar_api(request):
    station = request.membership.station
    if not station.calendar_enabled:
        return _json_error(request, "Modul ist nicht aktiviert.", status=404)
    if request.method == "POST":
        if not _scope_allowed(request.api_token, "write:calendar"):
            return _json_error(request, "Scope write:calendar fehlt.", status=403)
        if request.membership.role not in WRITE_ROLES:
            return _json_error(request, "Rolle darf keine Termine anlegen.", status=403)
        body = _parse_json(request)
        if body is None:
            return _json_error(request, "JSON-Körper erwartet.")
        form = CalendarEventForm(body)
        if not form.is_valid():
            return _json_error(
                request,
                "Termin ist ungültig.",
                status=422,
                fields=form.errors,
            )
        try:
            with transaction.atomic():
                event = form.save(commit=False)
                event.station = station
                event.created_by = request.user
                event.full_clean()
                event.save()
                audit(request.user, station, "calendar.created", event, {
                    "fields": ["title", "description", "starts_at", "ends_at"],
                })
        except DjangoValidationError as exc:
            return _json_error(
                request,
                "Termin ist ungültig.",
                status=422,
                fields=getattr(exc, "message_dict", {"__all__": exc.messages}),
            )
        return JsonResponse({
            "ok": True,
            "id": event.pk,
            "title": event.title,
            "starts_at": event.starts_at.isoformat(),
            "ends_at": event.ends_at.isoformat() if event.ends_at else None,
        }, status=201)

    if not _scope_allowed(request.api_token, "read:calendar"):
        return _json_error(request, "Scope read:calendar fehlt.", status=403)
    if request.membership.role not in CONTENT_ROLES:
        return _json_error(request, "Rolle hat keinen Zugriff auf den Kalender.", status=403)
    events = (
        CalendarEvent.objects.filter(station=station, starts_at__gte=timezone.now())
        .order_by("starts_at")[:30]
    )
    return JsonResponse({
        "ok": True,
        "results": [
            {
                "id": event.pk,
                "title": event.title,
                "starts_at": event.starts_at.isoformat(),
                "ends_at": event.ends_at.isoformat() if event.ends_at else None,
            }
            for event in events
        ],
    })


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_token_required
def coffee_api(request):
    station = request.membership.station
    if not station.coffee_enabled:
        return _json_error(request, "Modul ist nicht aktiviert.", status=404)
    if request.method == "POST":
        if not _scope_allowed(request.api_token, "write:coffee"):
            return _json_error(request, "Scope write:coffee fehlt.", status=403)
        if request.membership.role not in CASHIER_ROLES:
            return _json_error(request, "Rolle darf die Kasse nicht buchen.", status=403)
        body = _parse_json(request)
        if body is None:
            return _json_error(request, "JSON-Körper erwartet.")
        form = CoffeeEntryForm(body, station=station)
        if not form.is_valid():
            return _json_error(
                request,
                "Buchung ist ungültig.",
                status=422,
                fields=form.errors,
            )
        with transaction.atomic():
            entry = CoffeeEntry.objects.create(
                station=station,
                member=form.cleaned_data["member"],
                amount_cents=form.amount_cents(),
                reason=form.cleaned_data["reason"],
                created_by=request.user,
            )
            audit(request.user, station, "coffee.entry_created", entry, {
                "fields": ["member", "amount_cents", "reason"],
            })
        return JsonResponse({
            "ok": True,
            "id": entry.pk,
            "member": _person(entry.member),
            "amount_euros": entry.amount_euros,
            "reason": entry.reason,
            "created_at": entry.created_at.isoformat(),
        }, status=201)

    if not _scope_allowed(request.api_token, "read:coffee"):
        return _json_error(request, "Scope read:coffee fehlt.", status=403)
    if request.membership.role not in CONTENT_ROLES:
        return _json_error(request, "Rolle hat keinen Zugriff auf die Kaffeekasse.", status=403)
    qs = CoffeeEntry.objects.filter(station=station).select_related("member")
    if request.membership.role not in CASHIER_ROLES:
        qs = qs.filter(member=request.user)
    total = qs.aggregate(total=Sum("amount_cents"))["total"] or 0
    results = [
        {
            "id": entry.pk,
            "member": _person(entry.member),
            "amount_euros": entry.amount_euros,
            "reason": entry.reason,
            "created_at": entry.created_at.isoformat(),
        }
        for entry in qs.order_by("-created_at")[:50]
    ]
    return JsonResponse({"ok": True, "balance_euros": total / 100, "results": results})


@csrf_exempt
@require_GET
@api_token_required
def checklists_api(request):
    station = request.membership.station
    if not station.checklists_enabled:
        return _json_error(request, "Modul ist nicht aktiviert.", status=404)
    if not _scope_allowed(request.api_token, "read:checklists"):
        return _json_error(request, "Scope read:checklists fehlt.", status=403)
    if request.membership.role not in CONTENT_ROLES:
        return _json_error(request, "Rolle hat keinen Zugriff auf Checklisten.", status=403)
    lists = Checklist.objects.filter(station=station, is_active=True).prefetch_related("items")
    latest = {}
    for completion in (
        ChecklistCompletion.objects.filter(station=station)
        .select_related("completed_by")
        .order_by("checklist_id", "-created_at")
    ):
        latest.setdefault(completion.checklist_id, completion)
    results = []
    for checklist in lists:
        last = latest.get(checklist.id)
        results.append({
            "id": checklist.id,
            "title": checklist.title,
            "description": checklist.description,
            "items": [item.text for item in checklist.items.all()],
            "last_completed_at": last.created_at.isoformat() if last else None,
            "last_completed_by": _person(last.completed_by)["display_name"] if last else None,
        })
    return JsonResponse({"ok": True, "results": results})


@csrf_exempt
@require_POST
@api_token_required
def checklist_complete_api(request, pk):
    station = request.membership.station
    if not station.checklists_enabled:
        return _json_error(request, "Modul ist nicht aktiviert.", status=404)
    if not _scope_allowed(request.api_token, "write:checklists"):
        return _json_error(request, "Scope write:checklists fehlt.", status=403)
    if request.membership.role not in CONTENT_ROLES:
        return _json_error(request, "Rolle darf Checklisten nicht abschließen.", status=403)
    checklist, err = _api_get_or_404(request, Checklist, pk=pk, station=station, is_active=True)
    if err:
        return err
    body = _parse_json(request) or {}
    note = str(body.get("note") or "")[:300]
    with transaction.atomic():
        completion = ChecklistCompletion.objects.create(
            station=station,
            checklist=checklist,
            completed_by=request.user,
            note=note,
        )
        audit(request.user, station, "checklist.completed", completion, {
            "fields": ["checklist", "note"],
        })
    return JsonResponse({
        "ok": True,
        "id": completion.pk,
        "checklist": checklist.id,
        "completed_by": _person(request.user),
        "created_at": completion.created_at.isoformat(),
    }, status=201)


def _pinboard_json(note):
    return {
        "id": note.pk,
        "title": note.title,
        "body": note.body,
        "category": note.category,
        "is_pinned": note.is_pinned,
        "author": _person(note.author) if note.author_id else None,
        "created_at": note.created_at.isoformat(),
        "updated_at": note.updated_at.isoformat(),
    }


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_token_required
def pinboard_api(request):
    station = request.membership.station
    if not station.pinboard_enabled:
        return _json_error(request, "Modul ist nicht aktiviert.", status=404)
    if request.method == "POST":
        if not _scope_allowed(request.api_token, "write:pinboard"):
            return _json_error(request, "Scope write:pinboard fehlt.", status=403)
        if request.membership.role not in CONTENT_ROLES:
            return _json_error(request, "Rolle darf keine Aushänge anlegen.", status=403)
        body = _parse_json(request)
        if body is None:
            return _json_error(request, "JSON-Körper erwartet.")
        form = PinboardNoteForm(body)
        if not form.is_valid():
            return _json_error(request, "Aushang ist ungültig.", status=422, fields=form.errors)
        note = create_pinboard_note(
            station=station,
            author=request.user,
            title=form.cleaned_data["title"],
            body=form.cleaned_data["body"],
            category=form.cleaned_data["category"],
        )
        return JsonResponse({"ok": True, **_pinboard_json(note)}, status=201)

    if not _scope_allowed(request.api_token, "read:pinboard"):
        return _json_error(request, "Scope read:pinboard fehlt.", status=403)
    if request.membership.role not in CONTENT_ROLES:
        return _json_error(request, "Rolle hat keinen Zugriff auf die Pinnwand.", status=403)
    qs = (
        PinboardNote.objects.filter(station=station, is_archived=False)
        .select_related("author")
        .order_by("-is_pinned", "-updated_at")[:100]
    )
    results = [_pinboard_json(note) for note in qs]
    return JsonResponse({
        "ok": True,
        "api_version": API_VERSION,
        "count": len(results),
        "results": results,
    })
@csrf_exempt
@require_GET
@api_rate_limit("default")
def check_update(request):
    """Check if a new version is available for the client.
    
    This endpoint allows clients to check if there's a newer version available.
    It returns version information, changelog, and download URL if applicable.
    
    Query Parameters:
    - current_version: The current version of the client
    - platform: The platform (web, android, ios)
    
    Returns:
    - has_update: Whether a newer version is available
    - latest_version: The latest version available
    - changelog: List of changes since the current version
    - download_url: URL to download the latest version (if applicable)
    - force_update: Whether the update is mandatory
    """
    from ..models import AppVersion

    current_version = request.GET.get("current_version", "")
    platform = request.GET.get("platform", "web")

    try:
        # Get the latest active version for this platform. Order by release_date
        # and break ties by id so the "latest" row is deterministic instead of
        # depending on undefined database row order.
        latest_version_obj = AppVersion.objects.filter(
            platform=platform,
            is_active=True
        ).order_by("-release_date", "-id").first()

        if latest_version_obj is None:
            return JsonResponse({
                "ok": True,
                "has_update": False,
                "message": "No version information available for this platform",
                "current_version": current_version,
                "platform": platform,
            })

        # A client only needs an update when the published latest version is
        # strictly newer. Comparing version order (not text) prevents telling a
        # client that is already newer than the published build to "update",
        # i.e. downgrade (release-109 regression).
        has_update = _compare_versions(current_version, latest_version_obj.version) < 0
        
        # Check if this is a forced update
        force_update = latest_version_obj.is_forced
        
        # Check if current version is below minimum required
        if latest_version_obj.min_required_version:
            if _compare_versions(current_version, latest_version_obj.min_required_version) < 0:
                force_update = True

        return JsonResponse({
            "ok": True,
            "has_update": has_update,
            "current_version": current_version,
            "latest_version": latest_version_obj.version,
            "version_code": latest_version_obj.version_code,
            "platform": platform,
            "release_date": latest_version_obj.release_date.isoformat(),
            "changelog": latest_version_obj.parsed_changelog,
            "download_url": latest_version_obj.download_url,
            "force_update": force_update,
            "min_required_version": latest_version_obj.min_required_version,
        })
    except Exception:
        log_exception(request, message="check_update_failed")
        return _json_error(
            request,
            "Update-Check fehlgeschlagen.",
            status=500,
            code=ERROR_CODE_SERVER_ERROR,
        )


def _compare_versions(v1: str, v2: str) -> int:
    """Compare two version strings.
    
    Returns:
    - 1 if v1 > v2
    - 0 if v1 == v2
    - -1 if v1 < v2
    """
    def parse_version(v: str) -> tuple:
        # Split version string and convert to integers
        parts = []
        for part in v.split('.'):
            try:
                parts.append(int(part))
            except ValueError:
                parts.append(0)
        return tuple(parts)
    
    v1_parts = parse_version(v1)
    v2_parts = parse_version(v2)
    
    # Pad with zeros to make equal length
    max_len = max(len(v1_parts), len(v2_parts))
    v1_parts = v1_parts + (0,) * (max_len - len(v1_parts))
    v2_parts = v2_parts + (0,) * (max_len - len(v2_parts))
    
    if v1_parts > v2_parts:
        return 1
    elif v1_parts < v2_parts:
        return -1
    else:
        return 0
