"""Wachen-Display: tokenbasierte Leseansicht für Wandmonitor und Fernseher."""
from __future__ import annotations

import hashlib
import secrets
from functools import wraps

from django.contrib import messages
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from .access import get_membership, membership_required
from .models import Membership
from .display import display_payload
from .display_models import DEFAULT_DISPLAY_CONFIG, DisplayToken

COOKIE_NAME = "rwsth_display"
COOKIE_PATH = "/display/"
MAX_FAILURES_PER_MINUTE = 10
# Ein SSE-Stream belegt einen Worker-Thread. Nach dieser Laufzeit endet er,
# EventSource verbindet sich selbst neu und Zugang wird dabei neu geprüft.
STREAM_MAX_SECONDS = 300
STREAM_RETRY_MS = 5000


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


def notify_station_display(station_id: int):
    """Signalisiert dem Wachen-Display via Redis Pub/Sub eine sofortige Aktualisierung."""
    try:
        from django.conf import settings

        redis_url = getattr(settings, "REDIS_URL", None)
        if redis_url:
            import redis

            r = redis.from_url(redis_url)
            r.publish(f"station_display_{station_id}", "refresh")
    except Exception:
        pass


@require_GET
@never_cache
def display_stream(request):
    """Server-Sent Events (SSE) Live-Stream für Wandmonitore (< 100ms Latenz)."""
    import json
    import time
    from django.conf import settings

    station, token_record = _station_and_token_for_request(request)
    if station is None:
        return _harden(HttpResponse("kein Zugang", status=403, content_type="text/plain"))

    def stream_generator():
        payload = display_payload(station)
        payload["app_version"] = _app_version()
        if token_record and getattr(token_record, "layout_config", None):
            payload["layout_config"] = token_record.layout_config
        else:
            payload["layout_config"] = DEFAULT_DISPLAY_CONFIG

        yield f"event: update\ndata: {json.dumps(payload)}\n\n"

        sub = None
        redis_url = getattr(settings, "REDIS_URL", None)
        if redis_url:
            try:
                import redis

                r = redis.from_url(redis_url)
                sub = r.pubsub(ignore_subscribe_messages=True)
                sub.subscribe(f"station_display_{station.id}")
            except Exception:
                sub = None

        last_ping = time.time()
        last_poll = time.time()
        last_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

        started = time.time()
        yield f"retry: {STREAM_RETRY_MS}\n\n"
        while time.time() - started < STREAM_MAX_SECONDS:
            got_redis_msg = False
            if sub:
                try:
                    msg = sub.get_message(timeout=1.0)
                    if msg and msg.get("type") == "message":
                        got_redis_msg = True
                except Exception:
                    time.sleep(1.0)
            else:
                time.sleep(1.0)

            now = time.time()
            if now - last_ping >= 15.0:
                yield f'event: ping\ndata: {{"time": {int(now)}}}\n\n'
                last_ping = now

            if got_redis_msg or (now - last_poll >= 30.0):
                # Widerruf/Ablauf des Tokens bzw. Entzug der Mitgliedschaft
                # beendet einen laufenden Stream, statt ihn weiterzubedienen.
                if not _stream_still_authorized(request, station, token_record):
                    yield "event: revoked\ndata: {}\n\n"
                    return
                payload = display_payload(station)
                payload["app_version"] = _app_version()
                payload["layout_config"] = (
                    token_record.layout_config
                    if (token_record and getattr(token_record, "layout_config", None))
                    else DEFAULT_DISPLAY_CONFIG
                )
                current_h = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
                if got_redis_msg or current_h != last_hash:
                    last_hash = current_h
                    yield f"event: update\ndata: {json.dumps(payload)}\n\n"
                last_poll = now

    response = StreamingHttpResponse(stream_generator(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache, no-transform"
    response["X-Accel-Buffering"] = "no"
    return response


def _stream_still_authorized(request, station, token_record) -> bool:
    if token_record is not None:
        fresh = DisplayToken.objects.filter(pk=token_record.pk).first()
        return fresh is not None and fresh.is_active and fresh.station_id == station.id
    membership = get_membership(request.user) if request.user.is_authenticated else None
    return membership is not None and membership.station_id == station.id


def _app_version() -> str:
    try:
        from .version import APP_VERSION

        return APP_VERSION
    except Exception:  # noqa: BLE001
        return ""


# --- Verwaltung in den Einstellungen -------------------------------------

AVAILABLE_MODULES = [
    {
        "id": "clock",
        "name": _("Uhrzeit & Datum"),
        "icon": "⏰",
        "default_pos": "top_left",
        "desc": _("Große Digitaluhr, Wochentag, formatiertes Datum und Stationsname."),
    },
    {
        "id": "weather",
        "name": _("Wettervorhersage"),
        "icon": "🌤️",
        "default_pos": "top_right",
        "desc": _("5-Tage-Wetter via Open-Meteo & OpenStreetMap mit Piktogramm, Min/Max und Regenmenge."),
    },
    {
        "id": "events",
        "name": _("Heutige Termine"),
        "icon": "📅",
        "default_pos": "middle_left",
        "desc": _("Kalendertermine, Schichtbeginn und Einsätze des aktuellen Tages."),
    },
    {
        "id": "waste",
        "name": _("Müllabfuhr"),
        "icon": "🗑️",
        "default_pos": "middle_left",
        "desc": _("Anstehende kommunale Entleerungen (Restmüll, Papier, Bio, Wertstoff)."),
    },
    {
        "id": "tasks",
        "name": _("Tagesaufgaben & Fortschritt"),
        "icon": "✅",
        "default_pos": "middle_center",
        "desc": _("Offene Aufgaben mit Erledigungsquote und grafischem Fortschrittsbalken."),
    },
    {
        "id": "traffic",
        "name": _("Verkehrslage & Sperrungen"),
        "icon": "🚦",
        "default_pos": "middle_right",
        "desc": _("Lokale Baustellen, Sperrungen und Verkehrseinschränkungen im Wachbereich."),
    },
    {
        "id": "birthdays",
        "name": _("Geburtstage"),
        "icon": "🎂",
        "default_pos": "middle_right",
        "desc": _("Datenschutzkonforme Geburtstagsanzeige von Teammitgliedern (nur mit Einwilligung)."),
    },
    {
        "id": "pinboard_news",
        "name": _("Wachen-Ticker & Pinnwand"),
        "icon": "📌",
        "default_pos": "bottom_bar",
        "desc": _("Laufband im Fußbereich für aktuelle Wachenaushänge und Neuigkeiten."),
    },
    {
        "id": "urgent_handovers",
        "name": _("Dringende Übergaben"),
        "icon": "🚨",
        "default_pos": "bottom_bar",
        "desc": _("Akute Alarmierungshinweise und Übergaben im Fußbereich."),
    },
]

ALL_POSITIONS = [
    ("top_left", _("Oben links")),
    ("top_center", _("Oben Mitte")),
    ("top_right", _("Oben rechts")),
    ("middle_left", _("Mitte links")),
    ("middle_center", _("Mitte Zentrum")),
    ("middle_right", _("Mitte rechts")),
    ("bottom_left", _("Unten links")),
    ("bottom_center", _("Unten Mitte")),
    ("bottom_right", _("Unten rechts")),
    ("bottom_bar", _("Fußzeile / Ticker")),
]


@membership_required({Membership.Role.ADMIN})
@require_http_methods(["GET", "POST"])
def configure_display_token(request, pk: int):
    """Erlaubt Admins, Module und Positionen eines Bildschirms frei einzustellen."""
    membership = get_membership(request.user)
    token = get_object_or_404(DisplayToken, pk=pk, station=membership.station)

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
        messages.success(request, _("Konfiguration für '%(label)s' gespeichert.") % {"label": token.label})
        return redirect("display_tokens")

    module_rows = []
    for mod in AVAILABLE_MODULES:
        current = modules_map.get(mod["id"])
        module_rows.append({
            "id": mod["id"],
            "name": mod["name"],
            "icon": mod.get("icon", "📦"),
            "desc": mod.get("desc", ""),
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
    cached_config = cache.get(f"station_display_config:{membership.station_id}")
    DisplayToken.objects.create(
        station=membership.station,
        label=(request.POST.get("label") or "Wandmonitor")[:80],
        token_hash=_hash(raw),
        layout_config=cached_config or DEFAULT_DISPLAY_CONFIG,
        created_by=request.user,
    )
    url = request.build_absolute_uri(reverse("display_start", args=[raw]))
    request.session["display_new_url"] = url
    return redirect("display_tokens")


@membership_required({Membership.Role.ADMIN})
@require_http_methods(["GET", "POST"])
def display_tokens(request):
    """Zentrale Übersicht für Wandmonitore und modulare MagicMirror-Bausteine."""
    membership = get_membership(request.user)
    tokens = DisplayToken.objects.filter(station=membership.station).select_related("created_by")
    new_url = request.session.pop("display_new_url", "")

    # Ermitteln der aktuellen Standard-Konfiguration
    first_active_token = tokens.filter(revoked_at__isnull=True).first()
    cached_config = cache.get(f"station_display_config:{membership.station_id}")
    config = (
        (first_active_token.layout_config if first_active_token and first_active_token.layout_config else None)
        or cached_config
        or DEFAULT_DISPLAY_CONFIG
    )
    modules_map = {m["id"]: m for m in config.get("modules", [])}

    if request.method == "POST" and request.POST.get("action") == "save_modules":
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
        new_config = {"version": 1, "theme": "dark", "modules": updated_modules}
        # Auf alle aktiven Tokens der Station anwenden
        DisplayToken.objects.filter(station=membership.station, revoked_at__isnull=True).update(
            layout_config=new_config
        )
        cache.set(f"station_display_config:{membership.station_id}", new_config, 86400 * 30)
        messages.success(request, _("Modul- und Baustein-Konfiguration für Wachen-Display erfolgreich gespeichert."))
        return redirect("display_tokens")

    module_rows = []
    for mod in AVAILABLE_MODULES:
        current = modules_map.get(mod["id"])
        module_rows.append({
            "id": mod["id"],
            "name": mod["name"],
            "icon": mod.get("icon", "📦"),
            "desc": mod.get("desc", ""),
            "enabled": current.get("enabled", True) if current else (mod["id"] != "pinboard_news"),
            "position": current.get("position", mod["default_pos"]) if current else mod["default_pos"],
            "header": current.get("header", "") if current else "",
        })

    return render(request, "core/display_tokens.html", {
        "tokens": tokens,
        "new_url": new_url,
        "positions": ALL_POSITIONS,
        "module_rows": module_rows,
        "active_modules_count": sum(1 for r in module_rows if r["enabled"]),
    })


@membership_required({Membership.Role.ADMIN})
@require_http_methods(["POST"])
def revoke_display_token(request, pk: int):
    membership = get_membership(request.user)
    DisplayToken.objects.filter(pk=pk, station=membership.station).update(
        revoked_at=timezone.now()
    )
    return redirect("display_tokens")
