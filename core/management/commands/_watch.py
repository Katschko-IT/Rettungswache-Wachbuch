"""Dauerschleife für Hintergrunddienste ohne HTTP-Listener.

Genutzt von ``housekeeping`` und ``purge_demo_sandboxes`` (Dienste
``housekeeping`` und ``demo-cleaner``). Gleiches Muster wie ``notify_crew``:

- Nach jedem erfolgreichen Durchlauf und danach jede Minute der Wartezeit
  wird die Heartbeat-Datei erneuert; der Compose-Healthcheck prüft ihr Alter.
- Nach einem Fehler gibt es kein Lebenszeichen und nach spätestens einer
  Minute einen neuen Versuch. Nach ``max_failures`` Fehlversuchen in Folge
  endet der Befehl mit Fehler, damit Docker ihn neu startet.
- SIGTERM beendet die Wartezeit binnen einer Sekunde; sonst wartet
  ``docker compose stop`` zehn Sekunden und schickt SIGKILL.
"""
from __future__ import annotations

import logging
import signal
import time

from django.core.management.base import CommandError
from django.db import close_old_connections

from core.management.commands.notify_crew import write_heartbeat

logger = logging.getLogger(__name__)

HEARTBEAT_STEP_SECONDS = 60
RETRY_SECONDS = 60


def run_watch_loop(run_once, *, label, interval, heartbeat_file="", max_failures=10):
    """Ruft ``run_once()`` wiederholt auf, bis SIGTERM/SIGINT kommt."""
    stop = {"flag": False}

    def _handle_signal(signum, _frame):
        stop["flag"] = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    max_failures = max(int(max_failures), 1)
    failures = 0
    while not stop["flag"]:
        # Verbindungen, die die Datenbank inzwischen getrennt hat (Neustart,
        # Update), nicht wiederverwenden: lang laufender Prozess ohne Requests.
        close_old_connections()
        try:
            run_once()
        except Exception as exc:
            failures += 1
            logger.exception("%s fehlgeschlagen (%s/%s): %s", label, failures, max_failures, exc)
            close_old_connections()
            if failures >= max_failures:
                raise CommandError(f"{label}: {failures} Fehlversuch(e) in Folge, zuletzt: {exc}") from exc
            _pause(min(interval, RETRY_SECONDS), stop, "")
            continue
        if failures:
            logger.warning("%s wieder erfolgreich nach %s Fehlversuch(en)", label, failures)
        failures = 0
        _pause(interval, stop, heartbeat_file)


def _pause(seconds, stop, heartbeat_file):
    """Wartet in Sekundenschritten und erneuert dabei jede Minute das Lebenszeichen."""
    waited = 0
    while waited < seconds and not stop["flag"]:
        if heartbeat_file and waited % HEARTBEAT_STEP_SECONDS == 0:
            write_heartbeat(heartbeat_file)
        time.sleep(1)
        waited += 1
