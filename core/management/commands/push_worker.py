"""Push outbox worker.

Polls the ``PushOutbox`` table and delivers pending pushes via ``pywebpush``.
The worker never blocks the request that wrote the outbox row; it owns the
external network call, retry/backoff, and cleanup of dead subscriptions.

Design:

- One claim per loop iteration via ``SELECT ... FOR UPDATE SKIP LOCKED`` so
  multiple workers (or restarts) never deliver the same row twice.
- The outbox id is sent as the ``X-Idempotency-Key`` header so push providers
  (FCM/Mozilla/Apple) can deduplicate retries.
- Hard 404/410 responses drop the underlying subscription permanently.
- Network and 5xx errors keep the row pending and schedule the next attempt
  with exponential backoff (1m, 5m, 15m, 1h, 6h). After ``MAX_ATTEMPTS``
  attempts the row is marked ``discarded`` and a final failure audit is
  written. Use ``cleanup_pushoutbox`` to remove old sent/discarded rows.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections, connection, transaction
from django.utils import timezone

from core.management.commands.notify_crew import write_heartbeat
from core.models import PushOutbox, PushSubscription
from core.services import audit

try:
    from pywebpush import WebPushException, webpush
except Exception:  # pragma: no cover - import guard
    WebPushException = Exception
    webpush = None

logger = logging.getLogger(__name__)


def _claim_batch(now, batch_size: int):
    """Atomically claim up to ``batch_size`` due outbox rows.

    Uses ``SELECT ... FOR UPDATE SKIP LOCKED`` on PostgreSQL so parallel
    workers (or restarts) never deliver the same row twice. Other engines
    fall back to a plain row lock, which is sufficient for the test suite.
    """
    vendor = connection.vendor
    qs = (
        PushOutbox.objects.filter(
            status=PushOutbox.Status.PENDING,
            next_attempt_at__lte=now,
        )
        .order_by("next_attempt_at")
    )
    if vendor == "postgresql":
        return list(
            qs.select_for_update(skip_locked=True)[:batch_size]
        )
    return list(qs.select_for_update()[:batch_size])


def _mark_sent(outbox: PushOutbox) -> None:
    outbox.status = PushOutbox.Status.SENT
    outbox.sent_at = timezone.now()
    outbox.error_message = ""
    outbox.save(update_fields=["status", "sent_at", "error_message"])


def _schedule_retry(outbox: PushOutbox, error_message: str) -> None:
    delay = outbox.next_backoff_seconds
    outbox.attempts += 1
    outbox.last_attempt_at = timezone.now()
    outbox.error_message = error_message[:2000]
    if outbox.attempts >= PushOutbox.MAX_ATTEMPTS:
        outbox.status = PushOutbox.Status.DISCARDED
        outbox.next_attempt_at = timezone.now()
    else:
        outbox.status = PushOutbox.Status.PENDING
        outbox.next_attempt_at = timezone.now() + timezone.timedelta(seconds=delay)
    outbox.save(update_fields=[
        "attempts", "last_attempt_at", "error_message", "status", "next_attempt_at",
    ])
    if outbox.status == PushOutbox.Status.DISCARDED:
        _write_discard_audit(outbox)


def _write_discard_audit(outbox: PushOutbox) -> None:
    """Emit a push.outbox_failed audit when a row is given up."""
    try:
        audit(
            actor=None,
            station=outbox.station,
            action="push.outbox_failed",
            obj=outbox,
            metadata={
                "attempts": outbox.attempts,
                "user_id": outbox.user_id,
            },
        )
    except Exception:  # pragma: no cover - audit is best effort
        logger.exception("Audit fuer PushOutbox fehlgeschlagen")


def _mark_failed(outbox: PushOutbox, error_message: str) -> None:
    """Mark the row as failed (no retry) and write an audit event."""
    outbox.attempts += 1
    outbox.last_attempt_at = timezone.now()
    outbox.error_message = error_message[:2000]
    outbox.status = PushOutbox.Status.FAILED
    outbox.save(update_fields=[
        "attempts", "last_attempt_at", "error_message", "status",
    ])
    try:
        audit(
            actor=None,
            station=outbox.station,
            action="push.outbox_failed",
            obj=outbox,
            metadata={
                "attempts": outbox.attempts,
                "user_id": outbox.user_id,
            },
        )
    except Exception:  # pragma: no cover - audit is best effort
        logger.exception("Audit fuer PushOutbox fehlgeschlagen")


def _deliver_relay(outbox: PushOutbox) -> None:
    """Native App-Push über das konfigurierte Push-Relay (APNs/FCM beim Relay).

    Vertrag: docs/PUSH-RELAY.md. Übertragen werden nur Plattform, Geräte-Token
    und der kurze organisatorische Nachrichtentext.
    """
    import urllib.error
    import urllib.request

    from core.notification_models import MobilePushDevice

    relay_url = getattr(settings, "PUSH_RELAY_URL", "")
    relay_token = getattr(settings, "PUSH_RELAY_TOKEN", "")
    device = MobilePushDevice.objects.filter(pk=outbox.device_id).first() if outbox.device_id else None
    if device is None:
        outbox.status = PushOutbox.Status.DISCARDED
        outbox.error_message = "device vanished"
        outbox.save(update_fields=["status", "error_message"])
        return
    if not relay_url or not relay_token:
        _schedule_retry(outbox, "push relay not configured")
        return
    payload = outbox.payload if isinstance(outbox.payload, dict) else json.loads(outbox.payload)
    body = json.dumps({
        "platform": device.platform,
        "token": device.token,
        "title": str(payload.get("title", ""))[:120],
        "body": str(payload.get("body", ""))[:300],
        "url": str(payload.get("url", ""))[:200],
    }).encode("utf-8")
    request = urllib.request.Request(
        relay_url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {relay_token}",
            "X-Idempotency-Key": str(outbox.id),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 - https enforced in settings
            status_code = getattr(response, "status", 200)
    except urllib.error.HTTPError as exc:
        if exc.code in {404, 410}:
            # Token beim Anbieter ungültig: Gerät entfernen, Zeile behalten.
            outbox.status = PushOutbox.Status.DISCARDED
            outbox.error_message = f"device token gone ({exc.code})"
            outbox.device = None
            outbox.save(update_fields=["status", "error_message", "device"])
            device.delete()
            return
        _schedule_retry(outbox, f"relay HTTP {exc.code}")
        return
    except Exception as exc:  # network or unexpected
        _schedule_retry(outbox, f"{type(exc).__name__}: {exc}"[:2000])
        return
    if 200 <= status_code < 300:
        _mark_sent(outbox)
    else:
        _schedule_retry(outbox, f"relay HTTP {status_code}")


def _deliver(outbox: PushOutbox) -> None:
    """Send one outbox row. Runs inside a transaction opened by the caller."""
    if outbox.device_id:
        _deliver_relay(outbox)
        return
    if webpush is None:
        logger.warning("pywebpush nicht verfuegbar")
        _mark_failed(outbox, "pywebpush not installed")
        return

    subscription = (
        PushSubscription.objects.filter(pk=outbox.subscription_id).first()
        if outbox.subscription_id else None
    )
    if subscription is None:
        outbox.status = PushOutbox.Status.DISCARDED
        outbox.error_message = "subscription vanished"
        outbox.save(update_fields=["status", "error_message"])
        return

    subscription_info = {
        "endpoint": subscription.endpoint,
        "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
    }
    vapid_claims = {
        "sub": f"mailto:{getattr(settings, 'VAPID_ADMIN_EMAIL', 'ops@localhost')}",
    }
    headers = {"X-Idempotency-Key": str(outbox.id)}
    payload = (
        outbox.payload
        if isinstance(outbox.payload, str)
        else json.dumps(outbox.payload)
    )
    try:
        webpush(
            subscription_info=subscription_info,
            data=payload,
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims=vapid_claims,
            headers=headers,
            timeout=10,
        )
    except WebPushException as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        if status_code in {404, 410}:
            # Mark the outbox first so the subscription cascade does not
            # silently drop the forensic row.
            outbox.status = PushOutbox.Status.DISCARDED
            outbox.error_message = f"subscription gone ({status_code})"
            outbox.subscription = None
            outbox.save(update_fields=["status", "error_message", "subscription"])
            subscription.delete()
            return
        _schedule_retry(outbox, str(exc) or "WebPushException")
        return
    except Exception as exc:  # network or unexpected
        _schedule_retry(outbox, f"{type(exc).__name__}: {exc}"[:2000])
        return

    _mark_sent(outbox)


@transaction.atomic
def process_once(batch_size: int = 25) -> int:
    """Claim and process one batch while keeping row locks until delivery."""
    now = timezone.now()
    claimed = _claim_batch(now, batch_size)
    if not claimed:
        return 0
    processed = 0
    for outbox in claimed:
        try:
            with transaction.atomic():
                _deliver(outbox)
            processed += 1
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("PushOutbox %s crashed: %s", outbox.id, exc)
            _mark_failed(outbox, f"worker crash: {exc}")
            processed += 1
    return processed


class Command(BaseCommand):
    help = "Verarbeitet die PushOutbox und sendet Web-Push asynchron."

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--interval", type=int, default=15)
        parser.add_argument("--batch-size", type=int, default=25)
        parser.add_argument(
            "--once", action="store_true",
            help="Nur einen Durchlauf ausfuehren und dann beenden.",
        )
        parser.add_argument(
            "--heartbeat-file",
            default=os.getenv("PUSH_HEARTBEAT_FILE", ""),
            help="Datei, die nach jedem erfolgreichen Durchlauf aktualisiert wird (Healthcheck).",
        )

    def handle(self, *args, **options):
        interval = max(int(options["interval"]), 1)
        batch_size = max(int(options["batch_size"]), 1)
        once = bool(options["once"]) or not options["watch"]

        stop = {"flag": False}

        def _handle_signal(signum, _frame):  # pragma: no cover - signal path
            logger.info("push_worker: Signal %s erhalten, beende nach aktuellem Loop", signum)
            stop["flag"] = True

        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)

        heartbeat_file = options["heartbeat_file"]
        while True:
            # Nach einem Neustart der Datenbank die tote Verbindung verwerfen,
            # sonst scheitert jeder weitere Durchlauf.
            close_old_connections()
            try:
                count = process_once(batch_size=batch_size)
                # Lebenszeichen nur nach Erfolg: Ein Worker, der die Datenbank
                # nicht erreicht, wird "unhealthy" statt still weiterzulaufen.
                if heartbeat_file:
                    write_heartbeat(heartbeat_file)
                if count:
                    self.stdout.write(f"push_worker: {count} Eintraege verarbeitet")
            except Exception as exc:
                logger.exception("push_worker Loop-Fehler: %s", exc)
            if once or stop["flag"]:
                return
            # In Sekundenschritten warten, damit SIGTERM sofort wirkt.
            for _second in range(interval):
                if stop["flag"]:
                    return
                time.sleep(1)
