"""Benachrichtigungen per Signal über signal-cli-rest-api (docs/SIGNAL.md).

Signal hat keine offizielle Bot-Schnittstelle. Wachwerk spricht deshalb mit
einem ``signal-cli-rest-api``-Container im internen Docker-Netz, der als
verknüpftes Gerät eines Signal-Kontos der Wache läuft (wie Signal Desktop).

- Persönliche Nachrichten gehen nur an Personen, die ihre Nummer selbst
  hinterlegt und per Code bestätigt haben.
- Gruppennachrichten enthalten keine Namen oder Beträge einzelner Personen.
- Versand läuft über ``SignalOutbox`` im notify-worker (Wiederholung bei
  Fehlern); gesendete Zeilen werden nach ``OUTBOX_RETENTION_DAYS`` gelöscht.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 15
MAX_ATTEMPTS = 6
OUTBOX_RETENTION_DAYS = 30
CODE_TTL = timedelta(minutes=15)
_E164 = re.compile(r"^\+[1-9]\d{6,14}$")


class SignalError(Exception):
    pass


def signal_enabled() -> bool:
    return bool(getattr(settings, "SIGNAL_API_URL", "") and getattr(settings, "SIGNAL_NUMBER", ""))


def normalize_number(raw: str) -> str:
    """Telefonnummer im Format +49…; deutsche Nummern mit führender 0 werden ergänzt."""
    number = re.sub(r"[\s\-/().]", "", raw or "")
    if number.startswith("00"):
        number = "+" + number[2:]
    elif number.startswith("0"):
        number = "+49" + number[1:]
    if not _E164.match(number):
        raise ValueError("Ungültige Telefonnummer")
    return number


def _request(method: str, path: str, payload=None, *, raw=False):
    url = settings.SIGNAL_API_URL + path
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 (interne Adresse)
            body = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:300].decode("utf-8", "replace")
        raise SignalError(f"HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SignalError(f"Signal-Dienst nicht erreichbar: {exc}") from exc
    if raw:
        return body
    return json.loads(body) if body else None


def send(recipients: list[str], message: str) -> None:
    if not signal_enabled():
        raise SignalError("Signal ist nicht eingerichtet.")
    _request("POST", "/v2/send", {
        "message": message, "number": settings.SIGNAL_NUMBER, "recipients": recipients,
    })


def linked_accounts() -> list[str]:
    return list(_request("GET", "/v1/accounts") or [])


def is_linked() -> bool:
    try:
        return settings.SIGNAL_NUMBER in linked_accounts()
    except SignalError:
        return False


def groups() -> list[dict]:
    number = urllib.parse.quote(settings.SIGNAL_NUMBER, safe="")
    result = []
    for group in _request("GET", f"/v1/groups/{number}") or []:
        if group.get("id") and not group.get("blocked"):
            result.append({
                "id": group["id"], "name": group.get("name") or group["id"],
                "invite_link": group.get("invite_link") or "", "members": len(group.get("members") or []),
            })
    return sorted(result, key=lambda g: g["name"].casefold())


def link_qr_png(device_name: str = "Wachwerk") -> bytes:
    query = urllib.parse.urlencode({"device_name": device_name})
    return _request("GET", f"/v1/qrcodelink?{query}", raw=True)


# --- Postausgang -----------------------------------------------------------

def message_text(title: str, body: str = "", url: str = "") -> str:
    lines = [title.strip()]
    if body:
        lines.append(body.strip())
    site = getattr(settings, "SITE_URL", "")
    if url and site:
        lines.append(site + url)
    return "\n".join(lines)[:2000]


def enqueue(station, recipient: str, message: str, dedupe_key: str = "") -> bool:
    """Reiht eine Nachricht ein; mit ``dedupe_key`` höchstens einmal."""
    from .notification_models import SignalOutbox

    if not signal_enabled() or not recipient:
        return False
    try:
        with transaction.atomic():
            SignalOutbox.objects.create(station=station, recipient=recipient, message=message[:2000],
                                        dedupe_key=dedupe_key)
    except IntegrityError:
        return False
    return True


def enqueue_for_user(notification, payload: dict) -> bool:
    from .notification_models import SignalContact

    contact = SignalContact.objects.filter(user=notification.user, verified_at__isnull=False).first()
    if not contact:
        return False
    return enqueue(notification.station, contact.number,
                   message_text(payload.get("title", ""), payload.get("body", ""), payload.get("url", "")))


def enqueue_for_group(station, message: str, dedupe_key: str = "") -> bool:
    if not station.signal_group_id:
        return False
    return enqueue(station, station.signal_group_id, message, dedupe_key)


def deliver_outbox(limit: int = 20, now=None) -> int:
    """Versendet fällige Nachrichten (notify-worker). Gibt die Anzahl gesendeter zurück."""
    from .notification_models import SignalOutbox

    if not signal_enabled():
        return 0
    now = now or timezone.now()
    SignalOutbox.objects.filter(sent_at__lt=now - timedelta(days=OUTBOX_RETENTION_DAYS)).delete()
    due = SignalOutbox.objects.filter(sent_at__isnull=True, attempts__lt=MAX_ATTEMPTS, next_attempt_at__lte=now)
    sent = 0
    for item in due.order_by("created_at")[:limit]:
        try:
            send([item.recipient], item.message)
        except SignalError as exc:
            item.attempts += 1
            item.last_error = str(exc)[:300]
            item.next_attempt_at = now + timedelta(minutes=2 ** item.attempts)
            item.save(update_fields=["attempts", "last_error", "next_attempt_at"])
            logger.warning("Signal-Versand fehlgeschlagen (%s/%s): %s", item.attempts, MAX_ATTEMPTS, exc)
            continue
        item.sent_at = now
        item.attempts += 1
        item.last_error = ""
        item.save(update_fields=["sent_at", "attempts", "last_error"])
        sent += 1
    return sent


# --- Bestätigungscode für die eigene Nummer --------------------------------

def _code_hash(user_id: int, number: str, code: str) -> str:
    key = settings.SECRET_KEY.encode("utf-8")
    return hmac.new(key, f"signal:{user_id}:{number}:{code}".encode(), hashlib.sha256).hexdigest()


def start_verification(user, number: str):
    """Speichert die Nummer unbestätigt und schickt einen sechsstelligen Code (sofort, nicht über den Postausgang)."""
    from .notification_models import SignalContact

    code = f"{secrets.randbelow(10 ** 6):06d}"
    send([number], f"Wachwerk: Dein Bestätigungscode für Signal-Benachrichtigungen lautet {code}. "
                   "Hast du das nicht angefordert, ignoriere diese Nachricht.")
    contact, _ = SignalContact.objects.update_or_create(user=user, defaults={
        "number": number, "verified_at": None, "code_hash": _code_hash(user.pk, number, code),
        "code_expires_at": timezone.now() + CODE_TTL, "code_attempts": 0,
    })
    return contact


def confirm_verification(contact, code: str) -> bool:
    if contact.verified_at or not contact.code_hash or not contact.code_expires_at:
        return False
    if contact.code_expires_at < timezone.now() or contact.code_attempts >= 5:
        return False
    contact.code_attempts += 1
    ok = hmac.compare_digest(contact.code_hash, _code_hash(contact.user_id, contact.number, (code or "").strip()))
    if ok:
        contact.verified_at = timezone.now()
        contact.code_hash = ""
        contact.code_expires_at = None
    contact.save(update_fields=["code_attempts", "verified_at", "code_hash", "code_expires_at"])
    return ok
