"""Beendete und abgelaufene Demo-Wachen der öffentlichen Demo löschen.

Braucht die Rechte des Datenbank-Eigentümers, weil auch append-only Zeilen
(Kaffeekasse, Audit) der Demo-Wachen gelöscht werden. In Compose läuft das
im Dienst ``demo-cleaner`` (Profil ``demo``) mit ``--watch``: ein Prozess,
der jede Minute prüft und ein Lebenszeichen für den Healthcheck schreibt,
siehe docs/DEMO.md.
"""
import os

from django.core.management.base import BaseCommand, CommandError

from core.demo_sandbox import purge_all, purge_expired
from core.management.commands._watch import run_watch_loop


class Command(BaseCommand):
    help = "Löscht beendete und abgelaufene Demo-Wachen samt Konten und Einträgen."

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="Alle Demo-Wachen löschen, auch laufende.")
        parser.add_argument("--watch", action="store_true", help="Dauerbetrieb: alle --interval Sekunden prüfen.")
        parser.add_argument("--interval", type=int, default=60)
        parser.add_argument(
            "--heartbeat-file",
            default=os.getenv("DEMO_CLEANER_HEARTBEAT_FILE", ""),
            help="Datei, die nach jedem erfolgreichen Durchlauf aktualisiert wird.",
        )
        parser.add_argument("--max-failures", type=int, default=10)

    def handle(self, *args, **options):
        if options["watch"]:
            if options["all"]:
                raise CommandError("--all löscht auch laufende Demos und ist mit --watch nicht erlaubt.")
            run_watch_loop(
                lambda: self.report(purge_expired(), options),
                label="purge_demo_sandboxes",
                interval=max(int(options["interval"]), 10),
                heartbeat_file=options["heartbeat_file"],
                max_failures=options["max_failures"],
            )
            return
        purged = purge_all() if options["all"] else purge_expired()
        self.report(purged, options)

    def report(self, purged, options):
        if (purged and options["verbosity"] >= 1) or options["verbosity"] > 1:
            self.stdout.write(f"{purged} Demo-Wache(n) gelöscht.")
