#!/usr/bin/env python3
"""Synthetische Daten für Screenshots der öffentlichen Seiten vorbereiten.

Lädt die Demodaten in eine *Wegwerf*-Datenbank und gibt ihnen ein ruhiges,
realistisches Erscheinungsbild (Wache „Rettungswache Nord“, ohne
„[Demo]“-Marker). Alle Inhalte bleiben erfunden. Läuft nur mit
DEMO_MODE=true und DJANGO_DEBUG=true, damit es nie eine echte Datenbank trifft.

    DATABASE_URL=sqlite:////tmp/screens.sqlite3 DEMO_MODE=true DJANGO_DEBUG=true \
        DJANGO_SECRET_KEY=screens python scripts/screenshot_data.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.core.exceptions import ValidationError  # noqa: E402
from django.core.management import call_command  # noqa: E402

STATION_NAME = "Rettungswache Nord"
MARKER = "[Demo] "


def main() -> None:
    if not (settings.DEBUG and os.environ.get("DEMO_MODE", "").lower() == "true"):
        sys.exit("Nur mit DEMO_MODE=true und DJANGO_DEBUG=true (Wegwerf-Datenbank).")
    call_command("migrate", verbosity=0)
    call_command("load_demo_data", "--reset", verbosity=0)

    from django.apps import apps

    from core.models import Station

    station = Station.objects.get(memberships__user__username="demo-admin")
    station.name = STATION_NAME
    station.save(update_fields=["name"])
    changed = skipped = 0
    for model in apps.get_app_config("core").get_models():
        for field in ("title", "name"):
            if field not in {f.name for f in model._meta.get_fields()}:
                continue
            for obj in model.objects.filter(**{f"{field}__startswith": MARKER}):
                setattr(obj, field, getattr(obj, field)[len(MARKER):])
                try:
                    obj.save(update_fields=[field])
                except ValidationError:
                    # Append-only (z. B. Wiki-Revisionen): Eintrag bleibt, wie er ist.
                    skipped += 1
                    continue
                changed += 1
    print(f"{STATION_NAME}: {changed} Einträge ohne Marker, {skipped} unveränderlich übersprungen")


if __name__ == "__main__":
    main()
