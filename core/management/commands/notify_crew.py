"""Benachrichtigt Besatzungen, sobald Desinfektions-Einwirkzeiten ablaufen.

Läuft als eigener Dienst (``notify-worker``) mit der App-Datenbankrolle. Der
Push-Worker behält seine eingeschränkten Rechte und versendet nur die hier
geschriebenen Outbox-Zeilen.
"""
from __future__ import annotations

import logging
import signal
import time

from django.core.management.base import BaseCommand

from core.crew_notifications import notify_ready_vehicles

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Prüft abgelaufene Einwirkzeiten und benachrichtigt die Besatzung."

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--interval", type=int, default=30)

    def handle(self, *args, **options):
        interval = max(int(options["interval"]), 5)
        stop = {"flag": False}

        def _handle_signal(signum, _frame):  # pragma: no cover - signal path
            stop["flag"] = True

        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)

        while True:
            try:
                count = notify_ready_vehicles()
                if count:
                    self.stdout.write(f"notify_crew: {count} Benachrichtigungen angelegt")
            except Exception as exc:  # pragma: no cover - loop guard
                logger.exception("notify_crew Loop-Fehler: %s", exc)
            if not options["watch"] or stop["flag"]:
                return
            time.sleep(interval)
