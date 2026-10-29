"""Aufräumen nach den Aufbewahrungsfristen (Compose-Dienst ``housekeeping``).

Der Dienst läuft in jedem Compose-Profil mit ``--watch``: gleich beim Start,
danach stündlich – ohne Cron auf dem Host. Von Hand::

    docker compose exec -T housekeeping python manage.py housekeeping

Gelöscht werden:

- abgelaufene Sitzungen (wie ``clearsessions``)
- Anmeldeprotokolle von django-axes (Benutzername, IP-Adresse, Browser)
  nach ``LOGIN_LOG_RETENTION_DAYS`` Tagen (Standard 30, 0 = nie)
- Fehlerereignisse nach ``ERROR_EVENT_RETENTION_DAYS`` (wie ``purge_error_events``)
- abgeschlossene QR-Anmeldungen und TOTP-Schritte nach 24 Stunden
  (wie ``qr_login_cleanup``)
- versendete oder verworfene Push-Nachrichten nach 30 Tagen
  (wie ``cleanup_pushoutbox``)
- Feed-Einträge nach ``RETENTION_FEED_DAYS`` und Rückmeldungen nach
  ``FEEDBACK_RETENTION_DAYS`` (wie ``apply_retention``)
- abgelaufene Zähler der Rate-Limits

Der Dienst nutzt die App-Datenbankrolle: Sie darf all das löschen, aber
nichts aus den append-only Tabellen (Audit, Kaffeekasse, Checklisten-
Abschlüsse, Übergaberevisionen). Die optionale Audit-Frist
``RETENTION_AUDIT_DAYS`` gehört deshalb nicht hierher, sondern zu
``apply_retention`` mit den Rechten des Datenbank-Eigentümers.
"""
from __future__ import annotations

import logging
import os
from datetime import timedelta
from importlib import import_module

from axes.handlers.proxy import AxesProxyHandler
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, connections, transaction
from django.utils import timezone

from core.diagnostics_models import ErrorEvent
from core.feedback import apply_feedback_retention
from core.management.commands._watch import run_watch_loop
from core.management.commands.qr_login_cleanup import expired_rows
from core.rate_limit import cleanup_expired
from core.services import apply_feed_retention, apply_pushoutbox_retention

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


def _sessions(now):
    store = import_module(settings.SESSION_ENGINE).SessionStore
    if not hasattr(store, "get_model_class"):
        store.clear_expired()
        return 0
    deleted, _ = store.get_model_class().objects.filter(expire_date__lt=now).delete()
    return deleted


def _login_logs(now):
    days = _env_int("LOGIN_LOG_RETENTION_DAYS", 30)
    if days <= 0:
        return 0
    return AxesProxyHandler.reset_logs(age_days=days) + AxesProxyHandler.reset_failure_logs(age_days=days)


def _error_events(now):
    # Wie purge_error_events: 0 oder leer bedeutet die Standardfrist.
    days = max(int(getattr(settings, "ERROR_EVENT_RETENTION_DAYS", 30) or 30), 1)
    deleted, _ = ErrorEvent.objects.filter(occurred_at__lt=now - timedelta(days=days)).delete()
    return deleted


def _qr_logins(now):
    requests, totp_steps = expired_rows(now - timedelta(hours=24))
    return requests.delete()[0] + totp_steps.delete()[0]


STEPS = (
    ("Sitzungen", _sessions),
    ("Anmeldeprotokolle", _login_logs),
    ("Fehlerereignisse", _error_events),
    ("QR-Anmeldungen", _qr_logins),
    ("Push-Nachrichten", lambda now: apply_pushoutbox_retention(now=now)),
    ("Feed-Einträge", lambda now: apply_feed_retention(now=now)),
    ("Rückmeldungen", lambda now: apply_feedback_retention(now=now)),
    ("Rate-Limit-Zähler", lambda now: cleanup_expired()),
)


def run_housekeeping(now=None):
    """Alle Schritte einmal ausführen: (gelöschte Zeilen je Schritt, fehlgeschlagene Schritte).

    Ein fehlschlagender Schritt hält die übrigen nicht auf. Ist die Datenbank
    nicht erreichbar, bricht der Durchlauf sofort mit der Ausnahme ab.
    """
    connection.ensure_connection()
    now = now or timezone.now()
    counts, failed = {}, []
    for name, step in STEPS:
        try:
            with transaction.atomic():
                counts[name] = step(now)
        except Exception:
            logger.exception("housekeeping: %s konnten nicht aufgeräumt werden", name)
            failed.append(name)
    return counts, failed


def summary(counts) -> str:
    return ", ".join(f"{name}: {count}" for name, count in counts.items() if count)


class Command(BaseCommand):
    help = "Löscht abgelaufene Sitzungen, Protokolle und Einträge nach den Aufbewahrungsfristen."

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true", help="Dauerbetrieb: sofort, dann alle --interval Sekunden.")
        parser.add_argument("--interval", type=int, default=3600)
        parser.add_argument(
            "--heartbeat-file",
            default=os.getenv("HOUSEKEEPING_HEARTBEAT_FILE", ""),
            help="Datei, die nach jedem erfolgreichen Durchlauf aktualisiert wird.",
        )
        parser.add_argument(
            "--max-failures",
            type=int,
            default=_env_int("HOUSEKEEPING_MAX_FAILURES", 10),
            help="Fehlversuche in Folge, nach denen sich der Befehl mit Fehler beendet.",
        )

    def handle(self, *args, **options):
        if not options["watch"]:
            counts, failed = run_housekeeping()
            self.stdout.write(f"housekeeping: {summary(counts) or 'nichts zu löschen'}")
            if failed:
                raise CommandError(f"housekeeping: fehlgeschlagen: {', '.join(failed)}")
            return

        interval = max(int(options["interval"]), 60)
        started = {"flag": False}

        def run_once():
            try:
                counts, failed = run_housekeeping()
            finally:
                # Bis zum nächsten Durchlauf vergeht eine Stunde; keine
                # Datenbankverbindung so lange offen halten.
                connections.close_all()
            if len(failed) == len(STEPS):
                raise CommandError("alle Schritte fehlgeschlagen")
            if not started["flag"]:
                self.stdout.write(f"housekeeping: Datenbank erreichbar, Aufräumen läuft (Intervall {interval} s)")
                started["flag"] = True
            if summary(counts):
                self.stdout.write(f"housekeeping: gelöscht – {summary(counts)}")

        run_watch_loop(
            run_once,
            label="housekeeping",
            interval=interval,
            heartbeat_file=options["heartbeat_file"],
            max_failures=options["max_failures"],
        )
