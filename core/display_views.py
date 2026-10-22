"""Wachen-Display: tokenbasierte Leseansicht für Wandmonitor und Fernseher."""
from __future__ import annotations

import hashlib
import secrets
from functools import wraps

from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from .access import get_membership, membership_required
from .models import Membership
from .display import display_payload
from .display_models import DEFAULT_DISPLAY_CONFIG, DisplayToken

COOKIE_NAME = "rwsth_display"
COOKIE_PATH = "/display/"
MAX_FAILURES_PER_MINUTE = 10


def _harden(response: HttpResponse) -> HttpResponse:
    """Kein Caching, kein Referrer, keine Indexierung."""
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, private, max-age=0"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _station_and_token_for_request(request):
    """Station und optionaler DisplayToken über Sitzung oder Display-Cookie, sonst (None, None)."""
    membership = get_membership(request.user) if request.user.is_authenticated else None
    if membership is not None:
        return membership.station, None
    raw = request.COOKIES.get(COOKIE_NAME, "")
    if not raw:
        return None, None
    token = DisplayToken.objects.filter(token_hash=_hash(raw)).select_related("station").first()
    if token is None or not token.is_active:
        return None, None
    return token.station, token


def _station_for_request(request):
    """Station über Sitzung oder Display-Cookie, sonst None."""
    station, _ = _station_and_token_for_request(request)
    return station


def _rate_limited(ip: str) -> bool:
    key = f"display-start:{ip}"
    count = cache.get(key, 0)
    if count >= MAX_FAILURES_PER_MINUTE:
        return True
    cache.set(key, count + 1, 60)
    return False


@require_GET
def display_start(request, token: str):
    """Nimmt den Token aus der Adresse, setzt ein Cookie und leitet weiter.

    Dadurch steht das Geheimnis nicht dauerhaft in der Adresszeile und taucht
    bei späteren Abrufen nicht in Proxy-Protokollen auf.
    """
    ip = request.META.get("REMOTE_ADDR", "")
    if _rate_limited(ip):
        return _harden(HttpResponse("Zu viele Versuche.", status=429, content_type="text/plain"))

    record = DisplayToken.objects.filter(token_hash=_hash(token)).select_related("station").first()
    if record is None or not record.is_active:
        return _harden(
            HttpResponse(
                "Dieser Display-Link ist ungültig oder wurde widerrufen.",
                status=403,
                content_type="text/plain; charset=utf-8",
            )
        )

    DisplayToken.objects.filter(pk=record.pk).update(last_used_at=timezone.now())
    response = redirect("display_home")
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=60 * 60 * 24 * 365,
        path=COOKIE_PATH,
        httponly=True,
        samesite="Lax",
        secure=request.is_secure(),
    )
    return _harden(response)


@require_GET
@never_cache
def display_home(request):
    station = _station_for_request(request)
    if station is None:
        return _harden(
            HttpResponse(
                "Für diese Anzeige fehlt ein gültiger Display-Link.",
                status=403,
                content_type="text/plain; charset=utf-8",
            )
        )
    return _harden(
        render(request, "core/display.html", {"display_station": station})
    )


@require_GET
@never_cache
def display_data(request):
    station, token_record = _station_and_token_for_request(request)
    if station is None:
        return _harden(
            JsonResponse({"detail": "kein Zugang"}, status=403)
        )
    payload = display_payload(station)
    payload["app_version"] = _app_version()
    if token_record and getattr(token_record, "layout_config", None):
        payload["layout_config"] = token_record.layout_config
    else:
        payload["layout_config"] = DEFAULT_DISPLAY_CONFIG
    return _harden(JsonResponse(payload))


def _app_version() -> str:
    try:
        from .version import APP_VERSION

        return APP_VERSION
    except Exception:  # noqa: BLE001
        return ""


# --- Verwaltung in den Einstellungen -------------------------------------


@membership_required({Membership.Role.ADMIN})
@require_http_methods(["GET", "POST"])
def configure_display_token(request, pk: int):
    """Erlaubt Admins, Module und Positionen eines Bildschirms frei einzustellen."""
    membership = get_membership(request.user)
    token = get_object_or_404(DisplayToken, pk=pk, station=membership.station)

    AVAILABLE_MODULES = [
        {"id": "clock", "name": "Uhrzeit & Datum", "default_pos": "top_left"},
        {"id": "weather", "name": "Wettervorhersage", "default_pos": "top_right"},
        {"id": "events", "name": "Heutige Termine", "default_pos": "middle_left"},
        {"id": "waste", "name": "Müllabfuhr", "default_pos": "middle_left"},
        {"id": "tasks", "name": "Tagesaufgaben & Fortschritt", "default_pos": "middle_center"},
        {"id": "traffic", "name": "Verkehrslage & Sperrungen", "default_pos": "middle_right"},
        {"id": "birthdays", "name": "Geburtstage", "default_pos": "middle_right"},
        {"id": "pinboard_news", "name": "Pinnwand & Wachen-Ticker", "default_pos": "bottom_bar"},
        {"id": "urgent_handovers", "name": "Dringende Übergaben / Warnungen", "default_pos": "bottom_bar"},
    ]

    ALL_POSITIONS = [
        ("top_left", "Oben links"),
        ("top_center", "Oben Mitte"),
        ("top_right", "Oben rechts"),
        ("middle_left", "Mitte links"),
        ("middle_center", "Mitte Zentrum"),
        ("middle_right", "Mitte rechts"),
        ("bottom_left", "Unten links"),
        ("bottom_center", "Unten Mitte"),
        ("bottom_right", "Unten rechts"),
        ("bottom_bar", "Fußzeile / Ticker"),
    ]

    config = token.layout_config or DEFAULT_DISPLAY_CONFIG
    modules_map = {m["id"]: m for m in config.get("modules", [])}

    if request.method == "POST":
        current_config = dict(token.layout_config or DEFAULT_DISPLAY_CONFIG)
        updated_modules = []
        for mod in AVAILABLE_MODULES:
            mod_id = mod["id"]
            enabled = request.POST.get(f"mod_{mod_id}_enabled") == "1"
            position = request.POST.get(f"mod_{mod_id}_pos", mod["default_pos"])
            header = (request.POST.get(f"mod_{mod_id}_header") or "").strip()[:80]
            updated_modules.append({
                "id": mod_id,
                "module": mod_id,
                "position": position,
                "enabled": enabled,
                "header": header,
                "config": {},
            })
        current_config["modules"] = updated_modules
        token.layout_config = current_config
        token.save(update_fields=["layout_config"])
        return redirect("display_tokens")

    module_rows = []
    for mod in AVAILABLE_MODULES:
        current = modules_map.get(mod["id"])
        module_rows.append({
            "id": mod["id"],
            "name": mod["name"],
            "enabled": current.get("enabled", True) if current else (mod["id"] != "pinboard_news"),
            "position": current.get("position", mod["default_pos"]) if current else mod["default_pos"],
            "header": current.get("header", "") if current else "",
        })

    return render(
        request,
        "core/display_token_config.html",
        {
            "token": token,
            "positions": ALL_POSITIONS,
            "module_rows": module_rows,
        },
    )


@membership_required({Membership.Role.ADMIN})
@require_http_methods(["POST"])
def create_display_token(request):
    """Erzeugt einen neuen Display-Link; das Klartext-Token wird einmalig gezeigt."""
    membership = get_membership(request.user)
    raw = secrets.token_urlsafe(32)
    DisplayToken.objects.create(
        station=membership.station,
        label=(request.POST.get("label") or "Wandmonitor")[:80],
        token_hash=_hash(raw),
        created_by=request.user,
    )
    url = request.build_absolute_uri(reverse("display_start", args=[raw]))
    request.session["display_new_url"] = url
    return redirect("display_tokens")


@membership_required({Membership.Role.ADMIN})
@require_GET
def display_tokens(request):
    membership = get_membership(request.user)
    tokens = DisplayToken.objects.filter(station=membership.station).select_related("created_by")
    new_url = request.session.pop("display_new_url", "")
    return render(request, "core/display_tokens.html", {
        "tokens": tokens,
        "new_url": new_url,
    })


@membership_required({Membership.Role.ADMIN})
@require_http_methods(["POST"])
def revoke_display_token(request, pk: int):
    membership = get_membership(request.user)
    DisplayToken.objects.filter(pk=pk, station=membership.station).update(
        revoked_at=timezone.now()
    )
    return redirect("display_tokens")
