"""Bereitet die a11y-Prüfung vor: Wachenterminal, Wachen-Code, Display-Link.

Läuft nach ``migrate`` und ``load_demo_data`` gegen dieselbe Datenbank wie der
Server der CI. Gibt JSON mit den Rohgeheimnissen und den IDs der Musterobjekte
auf stdout aus; der Workflow legt sie als Job-Umgebung ab (nur Musterdaten,
die Datenbank wird mit dem Runner verworfen).

    python tests/a11y/seed.py > "$RUNNER_TEMP/a11y-seed.json"
"""
from __future__ import annotations

import json
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth.models import User  # noqa: E402

from core.display_views import DEFAULT_DISPLAY_CONFIG, _hash  # noqa: E402
from core.fleet_models import Vehicle  # noqa: E402
from core.models import Checklist, ChecklistCompletion, DisplayToken, HandoverEntry, Station  # noqa: E402
from core.mpg_models import MedicalDevice  # noqa: E402
from core.orga_models import SOPDocument  # noqa: E402
from core.terminal import create_terminal_device, set_station_code  # noqa: E402
from core.wachalltag_models import Defect  # noqa: E402


def main() -> None:
    admin = User.objects.get(username="demo-admin")
    station = Station.objects.get(memberships__user=admin, memberships__is_active=True)
    _terminal, raw_terminal = create_terminal_device(station, label="CI a11y", created_by=admin)
    code = os.environ.get("TERMINAL_CODE", "1234")
    set_station_code(station, code, set_by=admin)
    raw_display = secrets.token_urlsafe(32)
    DisplayToken.objects.create(
        station=station,
        label="CI a11y",
        token_hash=_hash(raw_display),
        layout_config=DEFAULT_DISPLAY_CONFIG,
        created_by=admin,
    )

    def first(queryset, field):
        return queryset.filter(station=station).order_by("pk").values_list(field, flat=True).first()

    ids = {
        "handover": first(HandoverEntry.objects, "pk"),
        "defect": first(Defect.objects, "pk"),
        "checklist": first(Checklist.objects, "pk"),
        "run": first(ChecklistCompletion.objects, "pk"),
        "vehicle": first(Vehicle.objects, "slug"),
        "device": first(MedicalDevice.objects, "slug"),
        "sop": first(SOPDocument.objects, "slug"),
    }
    json.dump({"terminal": raw_terminal, "display": raw_display, "ids": ids}, sys.stdout)


if __name__ == "__main__":
    main()
