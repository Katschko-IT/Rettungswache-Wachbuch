"""0.26.1 „Schaden begrenzen“: Fuhrpark ohne Einsatz- und Erregerangaben.

- Fahrzeugstatus nur noch als Verfügbarkeit; Einsatzphasen (2/3/4) sind
  Altwerte und werden auf „Einsatzbereit“ (1) gesetzt. Nur der aktuelle Wert
  wird umgestellt; Audit-Einträge bleiben unberührt (Bereinigung in 0.27).
- Statusbemerkungen „Desinfektion läuft (<Art>): Gesperrt bis HH:MM Uhr“
  verraten den Erreger. Sie werden neutral: „Desinfektion bis HH:MM Uhr“.
- Bemerkungsfeld des Desinfektionsprotokolls mit Hinweis statt „Transportgrund“.

Keine Schemaänderung: Die AlterField-Operationen ändern nur Auswahltexte und
Beschriftungen. Die Datenschritte sind nicht umkehrbar (Rückweg ohne Wirkung).
"""
import re

from django.db import migrations, models

LEGACY_STATUSES = ("2", "3", "4")
READY = "1"
OLD_NOTE_PREFIX = "Desinfektion läuft ("
TIME_AT_END = re.compile(r"(\d{1,2}:\d{2})\s*Uhr\s*$")


def neutral_note(note: str) -> str:
    match = TIME_AT_END.search(note)
    if match:
        return f"Desinfektion bis {match.group(1)} Uhr"
    return "Desinfektion läuft"


def neutralize_vehicles(apps, schema_editor):
    Vehicle = apps.get_model("core", "Vehicle")
    Vehicle.objects.filter(tactical_status__in=LEGACY_STATUSES).update(tactical_status=READY)
    for vehicle in Vehicle.objects.filter(status_note__startswith=OLD_NOTE_PREFIX).only("pk", "status_note"):
        Vehicle.objects.filter(pk=vehicle.pk).update(status_note=neutral_note(vehicle.status_note))


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0066_remove_inventory_mirrors"),
    ]

    operations = [
        migrations.AlterField(
            model_name="disinfectionprotocol",
            name="notes",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Nur Angaben zur Desinfektion. Keine Namen, Diagnosen, Transportziele oder Einsatzdaten eintragen.",
                max_length=255,
                verbose_name="Bemerkung (keine Patienten- oder Einsatzangaben)",
            ),
        ),
        migrations.AlterField(
            model_name="vehicle",
            name="tactical_status",
            field=models.CharField(
                choices=[
                    ("1", "Einsatzbereit"),
                    ("2", "Einsatzbereit (alter Status)"),
                    ("3", "Einsatzbereit (alter Status)"),
                    ("4", "Einsatzbereit (alter Status)"),
                    ("6", "Außer Dienst / nicht einsatzklar"),
                    ("disinfection", "Desinfektion (gesperrt)"),
                    ("workshop", "Werkstatt"),
                ],
                default="1",
                max_length=20,
            ),
        ),
        migrations.RunPython(neutralize_vehicles, migrations.RunPython.noop),
    ]
