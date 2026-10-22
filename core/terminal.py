"""Wachenterminal: Gerätebindung, PIN-Prüfung und Sitzungsregeln.

Sicherheitsmodell (docs/PI-WACHENTERMINAL.md):

- Ein Terminal wird von Admins registriert. Der Browser des Terminals erhält
  ein zufälliges Gerätegeheimnis als HttpOnly-Cookie; gespeichert ist nur der
  SHA-256-Hash.
- Die Anmeldung braucht Terminal **und** persönliche PIN. Ohne registriertes
  Terminal ist die PIN wertlos; über die App oder das Internet gibt es keine
  PIN-Anmeldung.
- Fünf Fehlversuche sperren die PIN für 15 Minuten; zusätzlich begrenzt ein
  Zähler je Terminal das Durchprobieren verschiedener Personen.
- PIN-Sitzungen enden nach ``TERMINAL_IDLE_SECONDS`` ohne Eingabe und sind auf
  Alltagsbereiche beschränkt (keine Konto-, Team-, Einstellungs- oder
  Chat-Seiten). Auf einem Terminal gilt die Leerlauf-Abmeldung für jede Sitzung.
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
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import timezone

COOKIE_NAME = "rwsth_terminal"
SESSION_TERMINAL = "terminal_id"
SESSION_LAST_SEEN = "terminal_last_seen"
PIN_LENGTH = 6
MAX_PIN_FAILURES = 5
PIN_LOCK_MINUTES = 15
TERMINAL_FAILURES_PER_10_MIN = 20
PAIRING_TTL_SECONDS = 120

# Bereiche, die eine PIN-Sitzung erreichen darf (Pfadpräfixe).
PIN_SESSION_PATHS = (
    "/terminal/",
    "/uebersicht/",
    "/hinweise/",
    "/uebergaben/",
    "/maengel/",
    "/fuhrpark/",
    "/mpg/",
    "/lager/",
    "/orga/",
    "/aufgaben/",
    "/checklisten/",
    "/kalender/",
    "/pinnwand/",
    "/neuigkeiten/",
    "/geraete/",
    "/kaffeekasse/",
    "/hilfe/",
    "/wiki/",
    "/sprache/",
    "/konto/avatar/",
    "/abmelden/",
    "/offline/",
    "/favicon.ico",
    "/manifest.webmanifest",
)
# Innerhalb erlaubter Bereiche trotzdem gesperrt: persönliche Geheimnisse
# (Kalender-Abo-Links) gehören nicht auf einen gemeinsamen Bildschirm.
PIN_SESSION_BLOCKED = ("/kalender/abo/", "/kalender/feed.ics")
# Auf einem Terminal nie: Offline-Seitencache im Service Worker.
TERMINAL_BLOCKED_PATHS = ("/service-worker.js",)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def hash_secret(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def terminal_enabled() -> bool:
    return bool(getattr(settings, "TERMINAL_ENABLED", False))


def idle_seconds() -> int:
    return int(getattr(settings, "TERMINAL_IDLE_SECONDS", 120))


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


def is_pin_session(request) -> bool:
    return bool(getattr(request, "session", None) and request.session.get(SESSION_TERMINAL))


# ---- PIN -----------------------------------------------------------------


def pin_problem(pin: str) -> str:
    """Leerer Text = PIN zulässig, sonst der Grund."""
    if not re.fullmatch(rf"\d{{{PIN_LENGTH}}}", pin or ""):
        return f"Die PIN besteht aus genau {PIN_LENGTH} Ziffern."
    if len(set(pin)) == 1:
        return "Bitte nicht nur eine Ziffer wiederholen."
    digits = [int(char) for char in pin]
    steps = {b - a for a, b in zip(digits, digits[1:])}
    if steps in ({1}, {-1}):
        return "Bitte keine aufsteigende oder absteigende Zahlenfolge."
    return ""


def generate_pin() -> str:
    while True:
        pin = "".join(secrets.choice("0123456789") for _ in range(PIN_LENGTH))
        if not pin_problem(pin):
            return pin


def set_pin(membership, pin: str, *, set_by, must_change: bool):
    from .terminal_models import TerminalPin

    record, _created = TerminalPin.objects.update_or_create(
        membership=membership,
        defaults={
            "pin_hash": make_password(pin),
            "must_change": must_change,
            "failed_attempts": 0,
            "locked_until": None,
            "set_by": set_by,
        },
    )
    return record


def pin_locked(record) -> bool:
    return bool(record.locked_until and record.locked_until > timezone.now())


def verify_pin(record, pin: str) -> bool:
    """Prüft die PIN und zählt Fehlversuche (Sperre nach ``MAX_PIN_FAILURES``)."""
    from .terminal_models import TerminalPin

    if pin_locked(record):
        return False
    if check_password(pin, record.pin_hash):
        TerminalPin.objects.filter(pk=record.pk).update(failed_attempts=0, locked_until=None)
        return True
    failures = record.failed_attempts + 1
    locked_until = None
    if failures >= MAX_PIN_FAILURES:
        locked_until = timezone.now() + timedelta(minutes=PIN_LOCK_MINUTES)
        failures = 0
    TerminalPin.objects.filter(pk=record.pk).update(failed_attempts=failures, locked_until=locked_until)
    record.failed_attempts, record.locked_until = failures, locked_until
    return False


# ---- Kopplung Handy ↔ Terminal --------------------------------------------


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
    return membership


# ---- Middleware und Template-Kontext --------------------------------------


def _path_allowed(path: str) -> bool:
    if any(path.startswith(prefix) for prefix in PIN_SESSION_BLOCKED):
        return False
    return path == "/" or path.startswith("/static/") or any(path.startswith(prefix) for prefix in PIN_SESSION_PATHS)


def end_terminal_session(request, message: str = ""):
    logout(request)
    if message:
        messages.info(request, message)
    response = redirect("terminal_home")
    # Seitencache, lokaler Speicher und Service Worker der vorigen Person weg;
    # das Terminal-Cookie bleibt erhalten.
    response["Clear-Site-Data"] = '"cache", "storage"'
    return response


class TerminalMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        early = self._check(request)
        response = early if early is not None else self.get_response(request)
        if terminal_for_request(request) is not None and not request.path.startswith("/static/"):
            # Kein Zurückblättern in Seiten der vorigen Person (bfcache/HTTP-Cache).
            response["Cache-Control"] = "no-store"
        return response

    def _check(self, request):
        terminal = terminal_for_request(request)
        pin_session = is_pin_session(request)
        if terminal is None:
            if pin_session:
                # PIN-Sitzung ohne (gültiges) Terminal-Cookie: sofort beenden.
                logout(request)
                return redirect("login")
            return None
        if request.path in TERMINAL_BLOCKED_PATHS:
            return HttpResponse(status=404)
        if not request.user.is_authenticated:
            return None
        if pin_session and request.session.get(SESSION_TERMINAL) != terminal.pk:
            return end_terminal_session(request)
        now = timezone.now().timestamp()
        last_seen = request.session.get(SESSION_LAST_SEEN)
        if last_seen is not None and now - float(last_seen) > idle_seconds():
            return end_terminal_session(request, "Wegen Inaktivität abgemeldet.")
        if pin_session and not _path_allowed(request.path):
            messages.warning(request, "Dieser Bereich ist am Wachenterminal nicht verfügbar. Bitte am eigenen Gerät öffnen.")
            return redirect("terminal_menu")
        request.session[SESSION_LAST_SEEN] = now
        request.session.set_expiry(idle_seconds() + 60)
        return None


def terminal_context(request):
    terminal = terminal_for_request(request) if hasattr(request, "COOKIES") else None
    feature = terminal_enabled()
    device = terminal is not None
    if not device or not getattr(request, "user", None) or not request.user.is_authenticated:
        return {"terminal_session": False, "terminal_device": device, "terminal_feature": feature}
    return {
        "terminal_session": True,
        "terminal_device": True,
        "terminal_feature": feature,
        "terminal_idle_seconds": idle_seconds(),
    }
