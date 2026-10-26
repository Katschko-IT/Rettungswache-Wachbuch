"""Benachrichtigt Besatzungen, sobald Desinfektions-Einwirkzeiten ablaufen.

Läuft als eigener Dienst (``notify-worker``) mit der App-Datenbankrolle. Der
Push-Worker behält seine eingeschränkten Rechte und versendet nur die hier
geschriebenen Outbox-Zeilen.

Betrieb im Container:

- Nach jedem erfolgreichen Durchlauf schreibt der Befehl einen Zeitstempel in
  die Heartbeat-Datei (``--heartbeat-file`` bzw. ``NOTIFY_HEARTBEAT_FILE``).
  Der Compose-Healthcheck prüft das Alter dieser Datei.
- Schlägt der Durchlauf mehrfach hintereinander fehl (z. B. Datenbank nicht
  erreichbar), beendet sich der Befehl mit einem Fehlercode, damit Docker ihn
  neu startet und der Fehler sichtbar wird, statt still weiterzulaufen.
"""
from __future__ import annotations

import logging
import os
import signal
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from django.utils import timezone

from core.coffee import remind_open_fees
from core.crew_notifications import notify_ready_vehicles
from core.signal_messenger import deliver_outbox as deliver_signal

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


def write_heartbeat(path: str) -> None:
    """Schreibt den Zeitstempel atomar, damit der Healthcheck nie halbe Dateien liest."""
    target = Path(path)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(timezone.now().isoformat() + "\n", encoding="utf-8")
    os.replace(temporary, target)


class Command(BaseCommand):
    help = "Prüft abgelaufene Einwirkzeiten und benachrichtigt die Besatzung."

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--interval", type=int, default=30)
        parser.add_argument(
            "--heartbeat-file",
            default=os.getenv("NOTIFY_HEARTBEAT_FILE", ""),
            help="Datei, die nach jedem erfolgreichen Durchlauf aktualisiert wird.",
        )
        parser.add_argument(
            "--max-failures",
            type=int,
            default=_env_int("NOTIFY_MAX_FAILURES", 10),
            help="Fehlversuche in Folge, nach denen sich der Befehl mit Fehler beendet.",
        )

    def handle(self, *args, **options):
        interval = max(int(options["interval"]), 5)
        max_failures = max(int(options["max_failures"]), 1)
        heartbeat_file = options["heartbeat_file"]
        stop = {"flag": False}
        failures = 0
        started = False
        # Kaffeekasse: Monatsbeiträge buchen und einmal im Monat erinnern –
        # das genügt alle 15 Minuten.
        coffee_due_at = 0.0

        def _handle_signal(signum, _frame):  # pragma: no cover - signal path
            stop["flag"] = True

        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)

        while True:
            # Verbindungen, die die Datenbank inzwischen getrennt hat, nicht
            # wiederverwenden (lang laufender Prozess ohne Request-Zyklus).
            close_old_connections()
            try:
                count = notify_ready_vehicles()
                if time.monotonic() >= coffee_due_at:
                    count += remind_open_fees()
                    coffee_due_at = time.monotonic() + 15 * 60
                # Signal-Postausgang (nur wenn SIGNAL_API_URL gesetzt ist).
                deliver_signal()
            except Exception as exc:
                failures += 1
                logger.exception(
                    "notify_crew Durchlauf fehlgeschlagen (%s/%s): %s", failures, max_failures, exc
                )
                close_old_connections()
                if failures >= max_failures or not options["watch"]:
                    raise CommandError(
                        f"notify_crew: {failures} Fehlversuch(e) in Folge, zuletzt: {exc}"
                    ) from exc
            else:
                if failures:
                    logger.warning("notify_crew wieder erfolgreich nach %s Fehlversuch(en)", failures)
                if options["watch"] and (failures or not started):
                    self.stdout.write(
                        f"notify_crew: Datenbank erreichbar, Prüfung läuft (Intervall {interval} s)"
                    )
                started = True
                failures = 0
                if heartbeat_file:
                    write_heartbeat(heartbeat_file)
                if count:
                    self.stdout.write(f"notify_crew: {count} Benachrichtigungen angelegt")
            if not options["watch"] or stop["flag"]:
                return
            time.sleep(interval)
