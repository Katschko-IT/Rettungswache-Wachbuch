"""Wachenterminal: Gerätebindung, Wachen-Code und Sitzungsregeln.

Sicherheitsmodell (docs/PI-WACHENTERMINAL.md):

- Ein Terminal wird von Admins registriert. Der Browser des Terminals erhält
  ein zufälliges Gerätegeheimnis als HttpOnly-Cookie; gespeichert ist nur der
  SHA-256-Hash.
- Entsperrt wird mit dem gemeinsamen vierstelligen Wachen-Code. Er gilt nur
  zusammen mit einem registrierten Terminal; über die App oder das Internet
  gibt es keinen Code-Zugang.
- Fehlversuche sperren das Terminal stufenweise (1 min, 5 min, 30 min, 24 h).
  Durchprobieren aller 10.000 Codes dauert damit Monate.
- Der Alltagsmodus arbeitet unter dem Dienstkonto „Wachenterminal“ (ohne
  Passwort, ohne App-Token), endet nach ``TERMINAL_IDLE_SECONDS`` ohne Eingabe
  und erreicht nur Alltagsbereiche (Übergaben, Kalender, Aufgaben, Mängel,
  Checklisten, Pinnwand, Neuigkeiten). Auf einem Terminal gilt die
  Leerlauf-Abmeldung für jede Sitzung.
"""
from __future__ import annotations

import hashlib
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import timezone

COOKIE_NAME = "rwsth_terminal"
SESSION_TERMINAL = "terminal_id"
SESSION_LAST_SEEN = "terminal_last_seen"
CODE_LENGTH = 4
PAIRING_TTL_SECONDS = 120
# Sperrstufen nach aufeinanderfolgenden Fehlversuchen an einem Terminal.
LOCK_STEPS = (
    (20, timedelta(hours=24)),
    (15, timedelta(minutes=30)),
    (10, timedelta(minutes=5)),
    (5, timedelta(minutes=1)),
)

# Alltagsmodus: erreichbare Bereiche (Pfadpräfixe).
OPEN_MODE_PATHS = (
    "/terminal/",
    "/uebergaben/",
    "/kalender/",
    "/aufgaben/",
    "/maengel/",
    "/checklisten/",
    "/pinnwand/",
    "/neuigkeiten/",
    "/hilfe/",
    "/sprache/",
    "/konto/avatar/",
    "/abmelden/",
    "/offline/",
    "/datenschutz/",
    "/favicon.ico",
    "/manifest.webmanifest",
)
# Innerhalb erlaubter Bereiche trotzdem gesperrt: Verwaltung und persönliche
# Links gehören nicht auf einen gemeinsamen Bildschirm.
OPEN_MODE_BLOCKED = (
    "/kalender/abo/",
    "/kalender/feed.ics",
    "/aufgaben/verwaltung/",
    "/aufgaben/neu/",
    "/terminal/handy/",
)
# Auf einem Terminal nie: Offline-Seitencache im Service Worker.
TERMINAL_BLOCKED_PATHS = ("/service-worker.js",)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def hash_secret(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


COOKIE_MAX_AGE = 60 * 60 * 24 * 365 * 5


def create_terminal_device(station, *, label: str, created_by):
    """Legt ein Terminal an; gibt ``(terminal, geheimnis)`` zurück. Gespeichert wird nur der Hash."""
    from .terminal_models import StationTerminal

    raw = secrets.token_urlsafe(32)
    terminal = StationTerminal.objects.create(
        station=station,
        label=(label or "Wachenterminal").strip()[:80],
        token_hash=hash_secret(raw),
        created_by=created_by,
    )
    return terminal, raw


def set_terminal_cookie(response, request, raw: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        raw,
        max_age=COOKIE_MAX_AGE,
        path="/",
        httponly=True,
        samesite="Strict",
        secure=request.is_secure(),
    )


def terminal_enabled() -> bool:
    return bool(getattr(settings, "TERMINAL_ENABLED", False))


def idle_seconds() -> int:
    return int(getattr(settings, "TERMINAL_IDLE_SECONDS", 120))


def wifi_qr_payload() -> str:
    """WLAN-Beitritt per Kamera (Format ``WIFI:``, Android und iOS); leer ohne Konfiguration."""
    ssid = getattr(settings, "TERMINAL_WIFI_SSID", "") or ""
    password = getattr(settings, "TERMINAL_WIFI_PASSWORD", "") or ""
    if not ssid:
        return ""

    def escape(value: str) -> str:
        for char in ("\\", ";", ",", ":", '"'):
            value = value.replace(char, "\\" + char)
        return value

    if not password:
        return f"WIFI:T:nopass;S:{escape(ssid)};;"
    return f"WIFI:T:WPA;S:{escape(ssid)};P:{escape(password)};;"


def local_cert_fingerprint() -> str:
    value = getattr(settings, "LOCAL_TLS_CERT_SHA256", "") or ""
    return value if _SHA256.match(value) else ""


def terminal_for_request(request):
    """Aktives Terminal dieses Browsers oder None (Ergebnis je Request gemerkt)."""
    if hasattr(request, "_terminal"):
        return request._terminal
    from .terminal_models import StationTerminal

    terminal = None
    raw = request.COOKIES.get(COOKIE_NAME, "")
    if raw and terminal_enabled():
        terminal = (
            StationTerminal.objects.select_related("station")
            .filter(token_hash=hash_secret(raw))
            .first()
        )
        if terminal is not None and not terminal.is_active:
            terminal = None
    request._terminal = terminal
    return terminal


def is_open_mode(request) -> bool:
    return bool(getattr(request, "session", None) and request.session.get(SESSION_TERMINAL))


# ---- Wachen-Code -----------------------------------------------------------


def code_problem(code: str) -> str:
    """Leerer Text = Code zulässig, sonst der Grund."""
    if not re.fullmatch(rf"\d{{{CODE_LENGTH}}}", code or ""):
        return f"Der Wachen-Code besteht aus genau {CODE_LENGTH} Ziffern."
    if len(set(code)) == 1:
        return "Bitte nicht viermal dieselbe Ziffer."
    digits = [int(char) for char in code]
    steps = {b - a for a, b in zip(digits, digits[1:])}
    if steps in ({1}, {-1}):
        return "Bitte keine aufsteigende oder absteigende Zahlenfolge."
    return ""


def generate_code() -> str:
    while True:
        code = "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))
        if not code_problem(code):
            return code


def set_station_code(station, code: str, *, set_by):
    """Setzt den Wachen-Code; legt beim ersten Mal das Dienstkonto an."""
    from django.contrib.auth.models import User

    from .models import Membership, UserProfile
    from .terminal_models import StationTerminalCode

    with transaction.atomic():
        record = StationTerminalCode.objects.select_for_update().filter(station=station).first()
        if record is None:
            user = User(username=f"wachenterminal-{station.pk}", first_name="Wachenterminal")
            user.set_unusable_password()
            user.save()
            UserProfile.for_user(user)
            Membership.objects.create(user=user, station=station, role=Membership.Role.MEMBER)
            record = StationTerminalCode(station=station, service_user=user)
        record.code_hash = make_password(code)
        record.set_by = set_by
        record.save()
    return record


def is_service_user(user) -> bool:
    from .terminal_models import StationTerminalCode

    return bool(getattr(user, "pk", None)) and StationTerminalCode.objects.filter(service_user=user).exists()


def terminal_locked(terminal) -> bool:
    return bool(terminal.locked_until and terminal.locked_until > timezone.now())


def verify_code(terminal, code: str) -> bool:
    """Prüft den Wachen-Code und sperrt das Terminal stufenweise bei Fehlversuchen."""
    from .terminal_models import StationTerminal, StationTerminalCode

    if terminal_locked(terminal):
        return False
    record = StationTerminalCode.objects.filter(station=terminal.station).first()
    if record is not None and check_password(code or "", record.code_hash):
        StationTerminal.objects.filter(pk=terminal.pk).update(failed_attempts=0, locked_until=None)
        terminal.failed_attempts, terminal.locked_until = 0, None
        return True
    failures = terminal.failed_attempts + 1
    locked_until = None
    if failures % 5 == 0:
        for threshold, duration in LOCK_STEPS:
            if failures >= threshold:
                locked_until = timezone.now() + duration
                break
    StationTerminal.objects.filter(pk=terminal.pk).update(failed_attempts=failures, locked_until=locked_until)
    terminal.failed_attempts, terminal.locked_until = failures, locked_until
    return False


# ---- Kopplung Handy ↔ persönliches Konto ----------------------------------


def create_pairing(membership) -> str:
    from .terminal_models import TerminalPairing

    TerminalPairing.objects.filter(expires_at__lt=timezone.now() - timedelta(days=1)).delete()
    raw = secrets.token_urlsafe(24)
    TerminalPairing.objects.create(
        membership=membership,
        code_hash=hash_secret(raw),
        expires_at=timezone.now() + timedelta(seconds=PAIRING_TTL_SECONDS),
    )
    return raw


def consume_pairing(raw: str):
    """Löst einen Kopplungscode genau einmal ein; liefert die Mitgliedschaft."""
    from .terminal_models import TerminalPairing

    now = timezone.now()
    record = TerminalPairing.objects.select_related("membership__user", "membership__station").filter(
        code_hash=hash_secret(raw or "")
    ).first()
    if record is None:
        return None
    consumed = TerminalPairing.objects.filter(pk=record.pk, used_at__isnull=True, expires_at__gt=now).update(
        used_at=now
    )
    if not consumed:
        return None
    membership = record.membership
    if not (membership.is_active and membership.user.is_active and membership.station.is_active):
        return None
    if is_service_user(membership.user):
        return None
    return membership


# ---- Middleware und Template-Kontext --------------------------------------


def _path_allowed(path: str) -> bool:
    if any(path.startswith(prefix) for prefix in OPEN_MODE_BLOCKED):
        return False
    return path.startswith("/static/") or any(path.startswith(prefix) for prefix in OPEN_MODE_PATHS)


def end_terminal_session(request, message: str = ""):
    logout(request)
    if message:
        messages.info(request, message)
    response = redirect("terminal_home")
    # Seitencache, lokaler Speicher und Service Worker weg; das
    # Terminal-Cookie bleibt erhalten.
    response["Clear-Site-Data"] = '"cache", "storage"'
    return response


class TerminalMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        early = self._check(request)
        response = early if early is not None else self.get_response(request)
        if terminal_for_request(request) is not None and not request.path.startswith("/static/"):
            # Kein Zurückblättern in frühere Seiten (bfcache/HTTP-Cache).
            response["Cache-Control"] = "no-store"
        return response

    def _check(self, request):
        terminal = terminal_for_request(request)
        open_mode = is_open_mode(request)
        if terminal is None:
            user = request.user
            service = user.is_authenticated and user.username.startswith("wachenterminal-") and is_service_user(user)
            if open_mode or service:
                # Alltagsmodus ohne (gültiges) Terminal-Cookie: sofort beenden.
                logout(request)
                return redirect("login")
            return None
        if request.path in TERMINAL_BLOCKED_PATHS:
            return HttpResponse(status=404)
        if not request.user.is_authenticated:
            return None
        if open_mode and request.session.get(SESSION_TERMINAL) != terminal.pk:
            return end_terminal_session(request)
        now = timezone.now().timestamp()
        last_seen = request.session.get(SESSION_LAST_SEEN)
        if last_seen is not None and now - float(last_seen) > idle_seconds():
            return end_terminal_session(request)
        if open_mode and not _path_allowed(request.path):
            messages.warning(request, "Dieser Bereich ist am Wachenterminal nicht verfügbar.")
            return redirect("terminal_menu")
        request.session[SESSION_LAST_SEEN] = now
        request.session.set_expiry(idle_seconds() + 60)
        return None


def is_local_request(request) -> bool:
    """Der Browser läuft auf dem Server selbst (Kiosk des Pi, Adresse localhost)."""
    try:
        host = request.get_host()
    except Exception:  # DisallowedHost o. Ä.: nie als lokal werten
        return False
    return host.rsplit(":", 1)[0].strip("[]") in {"localhost", "127.0.0.1", "::1"}


def terminal_context(request):
    terminal = terminal_for_request(request) if hasattr(request, "COOKIES") else None
    feature = terminal_enabled()
    device = terminal is not None
    # Bildschirmtastatur nur am Terminal bzw. am Bildschirm des Servers selbst.
    osk = feature and (device or is_local_request(request))
    if not device or not getattr(request, "user", None) or not request.user.is_authenticated:
        return {"terminal_session": False, "terminal_device": device, "terminal_feature": feature, "osk_enabled": osk}
    return {
        "terminal_session": True,
        "terminal_open_mode": is_open_mode(request),
        "terminal_device": True,
        "terminal_feature": feature,
        "terminal_idle_seconds": idle_seconds(),
        "osk_enabled": osk,
    }
