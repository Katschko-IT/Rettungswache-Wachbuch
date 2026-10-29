"""Beendete und abgelaufene Demo-Wachen der öffentlichen Demo löschen.

Braucht die Rechte des Datenbank-Eigentümers, weil auch append-only Zeilen
(Kaffeekasse, Audit) der Demo-Wachen gelöscht werden. In Compose läuft das
im Dienst ``demo-cleaner`` (Profil ``demo``), siehe docs/DEMO.md.
"""
from django.core.management.base import BaseCommand

from core.demo_models import DemoSandbox
from core.demo_sandbox import purge_expired, purge_sandbox


class Command(BaseCommand):
    help = "Löscht beendete und abgelaufene Demo-Wachen samt Konten und Einträgen."

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="Alle Demo-Wachen löschen, auch laufende.")

    def handle(self, *args, **options):
        if options["all"]:
            sandboxes = list(DemoSandbox.objects.all())
            for sandbox in sandboxes:
                purge_sandbox(sandbox)
            purged = len(sandboxes)
        else:
            purged = purge_expired()
        if (purged and options["verbosity"] >= 1) or options["verbosity"] > 1:
            self.stdout.write(f"{purged} Demo-Wache(n) gelöscht.")
