"""Müllkalender-ICS-URLs der Wachen abrufen.

Läuft im feed-worker (``sync_feeds --watch``): alle sechs Stunden für alle
Wachen, in jedem 15-Minuten-Durchlauf zusätzlich für Wachen, deren URL gerade
eingetragen wurde (``--new-only``). Der feed-worker darf ``core_station`` nur
spaltenweise lesen (``grant_database_access``) – deshalb ``.only()``: ohne
fragt das ORM jede Spalte ab, auch IBAN und Signal-Gruppe.
"""
from django.core.management.base import BaseCommand

from core.models import Station
from core.waste_sync import sync_station_waste

STATION_COLUMNS = ("id", "name", "waste_calendar_url")


class Command(BaseCommand):
    help = "Importiert die stationsspezifischen Muellkalender-ICS-Quellen."

    def add_arguments(self, parser):
        parser.add_argument(
            "--new-only", action="store_true",
            help="Nur Wachen, für die noch keine Abfuhrtermine gespeichert sind.",
        )

    def handle(self, *args, **options):
        stations = Station.objects.filter(
            waste_calendar_enabled=True, is_active=True
        ).exclude(waste_calendar_url="").only(*STATION_COLUMNS)
        if options["new_only"]:
            stations = stations.filter(waste_collections__isnull=True)
        stations = list(stations)
        if not stations:
            if not options["new_only"]:
                self.stdout.write("Keine aktiven Muellkalender-Quellen konfiguriert.")
            return
        for station in stations:
            try:
                count = sync_station_waste(station)
                self.stdout.write(f"{station.name}: {count} Abfuhrtermine")
            except Exception as exc:
                self.stderr.write(f"{station.name}: {exc}")
