import os
import time

from django.core.management.base import BaseCommand

from core.feed_sync import sync_source
from core.management.commands.notify_crew import write_heartbeat
from core.models import FeedSource

HEARTBEAT_STEP_SECONDS = 60


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
    help = "Importiert erlaubte offizielle RSS- und CSV-Quellen."

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
        while True:
            if heartbeat_file:
                write_heartbeat(heartbeat_file)
            for source in FeedSource.objects.filter(is_enabled=True):
                try:
                    count = sync_source(source)
                    self.stdout.write(f"{source.name}: {count} Eintraege")
                except Exception as exc:
                    self.stderr.write(f"{source.name}: {exc}")
            if not options["watch"]:
                break
            wait_with_heartbeat(max(options["interval"], 60), heartbeat_file)
