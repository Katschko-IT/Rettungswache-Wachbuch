import os
import time

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from core.feed_sync import sync_source
from core.management.commands.notify_crew import write_heartbeat
from core.models import FeedSource

HEARTBEAT_STEP_SECONDS = 60
# Müllkalender ändern sich selten: alle sechs Stunden alle Wachen abrufen,
# dazwischen nur Wachen mit frisch eingetragener URL (sync_waste_calendar).
WASTE_SYNC_SECONDS = 6 * 3600


def wait_with_heartbeat(seconds, heartbeat_file, *, sleep=time.sleep, beat=None):
    """Wartet in Minutenschritten und meldet dabei Lebenszeichen.

    Der Healthcheck im Container prüft das Alter der Datei; so fällt auch ein
    hängender Worker auf, obwohl zwischen zwei Abrufen 15 Minuten liegen.
    """
    beat = beat or write_heartbeat
    remaining = seconds
    while remaining > 0:
        if heartbeat_file:
            beat(heartbeat_file)
        step = min(HEARTBEAT_STEP_SECONDS, remaining)
        sleep(step)
        remaining -= step


class Command(BaseCommand):
    help = "Importiert erlaubte offizielle RSS- und CSV-Quellen und die Müllkalender der Wachen."

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--interval", type=int, default=900)
        parser.add_argument(
            "--heartbeat-file",
            default=os.getenv("FEED_HEARTBEAT_FILE", ""),
            help="Datei für das Lebenszeichen (Healthcheck im Container).",
        )

    def handle(self, *args, **options):
        heartbeat_file = options["heartbeat_file"]
        waste_due_at = 0.0
        while True:
            # Nach einem Neustart der Datenbank nicht die tote Verbindung nutzen.
            close_old_connections()
            if heartbeat_file:
                write_heartbeat(heartbeat_file)
            for source in FeedSource.objects.filter(is_enabled=True):
                try:
                    count = sync_source(source)
                    self.stdout.write(f"{source.name}: {count} Eintraege")
                except Exception as exc:
                    self.stderr.write(f"{source.name}: {exc}")
            waste_due_at = self.sync_waste_calendars(waste_due_at)
            if not options["watch"]:
                break
            wait_with_heartbeat(max(options["interval"], 60), heartbeat_file)

    def sync_waste_calendars(self, due_at):
        """Ruft die Müllkalender ab; ein Fehler hält den Feed-Abruf nie an."""
        full = time.monotonic() >= due_at
        try:
            call_command(
                "sync_waste_calendar", new_only=not full, stdout=self.stdout, stderr=self.stderr
            )
        except Exception as exc:
            self.stderr.write(f"Muellkalender: {exc}")
        return time.monotonic() + WASTE_SYNC_SECONDS if full else due_at
