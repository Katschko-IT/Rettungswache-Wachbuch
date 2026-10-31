"""Datenkatalog als Markdown ausgeben (core/data_catalog.py).

Referenzkatalog aller Module (committet als docs/DATENKATALOG.md)::

    python manage.py data_catalog --write
    python manage.py data_catalog --check

Katalog einer Wache mit den dort aktiven Modulen und eingestellten Fristen
(Anlage 1 der Vereinbarung)::

    docker compose exec -T web python manage.py data_catalog --station auto > datenkatalog.md

Der Befehl liest nur Metadaten und Einstellungen und schreibt nichts in die
Datenbank; er ist deshalb auch im laufenden Betrieb unbedenklich.
"""
from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import translation

from core import data_catalog

STALE_MESSAGE = "Datenkatalog veraltet: python manage.py data_catalog --write"


def resolve_station(value: str):
    """Wache per Kurzname; ``auto`` nur bei genau einer aktiven echten Wache.

    Legt nie eine Wache an (anders als ``Station.get_default``).
    """
    from core.models import Station

    stations = Station.objects.filter(is_active=True, demo_sandbox__isnull=True)
    if value == "auto":
        found = list(stations.order_by("pk")[:2])
        if len(found) != 1:
            raise CommandError(
                "Keine eindeutige Wache gefunden. Bitte den Kurznamen angeben: --station <kurzname>"
            )
        return found[0]
    station = stations.filter(slug=value).first()
    if station is None:
        raise CommandError(f"Keine aktive Wache mit dem Kurznamen „{value}“.")
    return station


class Command(BaseCommand):
    help = "Datenkatalog (Felder, Rollen, Zugriffe, Auswertungen, Fristen) als Markdown ausgeben."

    def add_arguments(self, parser):
        parser.add_argument(
            "--station",
            metavar="KURZNAME",
            help="Katalog einer Wache (Kurzname oder auto) mit aktiven Modulen und eingestellten Fristen.",
        )
        parser.add_argument("--write", action="store_true", help="Referenzkatalog nach docs/DATENKATALOG.md schreiben.")
        parser.add_argument("--check", action="store_true", help="Fehler, wenn docs/DATENKATALOG.md veraltet ist.")
        parser.add_argument("--output", metavar="DATEI", help="In diese Datei schreiben statt auf die Standardausgabe.")

    def handle(self, *args, **options):
        station_value = options.get("station")
        if station_value and (options["write"] or options["check"]):
            raise CommandError("--station lässt sich nicht mit --write oder --check verbinden.")
        if options["write"] and options["check"]:
            raise CommandError("Bitte entweder --write oder --check angeben.")

        with translation.override("de"):
            if station_value:
                text = data_catalog.station_markdown(resolve_station(station_value))
            else:
                text = data_catalog.reference_markdown()

        reference = Path(data_catalog.REFERENCE_PATH)
        if options["check"]:
            current = reference.read_text(encoding="utf-8") if reference.exists() else None
            if current != text:
                raise CommandError(STALE_MESSAGE)
            self.stdout.write("Datenkatalog ist aktuell.")
            return
        if options["write"]:
            reference.write_text(text, encoding="utf-8")
            self.stdout.write(f"Geschrieben: {reference}")
            return
        if options.get("output"):
            Path(options["output"]).write_text(text, encoding="utf-8")
            self.stdout.write(f"Geschrieben: {options['output']}")
            return
        self.stdout.write(text, ending="")
