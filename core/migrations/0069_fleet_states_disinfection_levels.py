"""0.27 „Pilotfähig“: fünf Fahrzeugzustände, Desinfektionsstufen statt Erregerarten.

Läuft unbeaufsichtigt mit ``./wachbuch update`` und dem Auto-Update; deshalb
nur feste, verlustfreie Zuordnungen. Was einen Trockenlauf braucht (Audit,
Lesebestätigungen, alte Bemerkungen), erledigt der Befehl
``cleanup_legacy_data`` – nicht diese Migration.

- Fahrzeugzustand mit neutralen Werten: „1“/„2“/„3“/„4“ → ``ready``,
  „6“ → ``out_of_service``; ``disinfection`` und ``workshop`` bleiben. Neu ist
  ``limited`` (Eingeschränkt).
- Neue Tabelle der Desinfektionsstufen je Wache (Plan: Stufe → Mittel →
  Freigaberegel, mit Bestätigung). Jede bestehende Wache erhält fünf Stufen,
  benannt nach Umfang bzw. Wirkbereich statt nach Erreger, unbestätigt und
  „Nach Einwirkzeit“ – das bisherige Verhalten bleibt also unverändert. Mittel
  und Minuten kommen vom ersten Mittel der Wache (sonst leer).
- Protokolle: Jede frühere Art bekommt ihre eigene Stufe (keine
  Zusammenlegung, kein Datenverlust): routine → Routine-Wischdesinfektion,
  mrsa → Schlussdesinfektion (begrenzt viruzid/bakterizid), noro →
  Schlussdesinfektion (viruzid), c_diff → Schlussdesinfektion (sporizid),
  base → Grunddesinfektion; Unbekanntes → Routine. Danach entfällt die Spalte
  ``kind``.

Rückweg (``migrate core 0067``): Die Spalte ``kind`` entsteht neu und wird über
die Standardnamen der Stufen zurückgefüllt; umbenannte oder neue Stufen werden
zu ``routine``. Fahrzeuge: ``ready``/``limited`` → „1“, ``out_of_service`` →
„6“. Der vorgesehene Rückweg eines Updates bleibt das Backup vor dem Update
(docs/OPERATIONS.md, „Rollback“).

PostgreSQL: Den Fremdschlüssel der neuen Spalte ``level`` legt Django in
AddField direkt an und setzt ihn sofort wirksam; nur die Fremdschlüssel der
neuen Tabelle entstehen erst am Ende der Migration. ``SET CONSTRAINTS ALL
IMMEDIATE`` um den Datenschritt ist nur eine Absicherung, damit vor dem
Entfernen der Spalte ``kind`` keine Prüfungen ausstehen (geprüft mit
PostgreSQL 16 und SQLite, vorwärts und rückwärts).
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

STATUS_FORWARD = {"1": "ready", "2": "ready", "3": "ready", "4": "ready", "6": "out_of_service"}
STATUS_BACKWARD = {"ready": "1", "limited": "1", "out_of_service": "6"}
# Frühere Art → Stufe (Name nach Wirkbereich, Betreiberentscheid 0.27).
KIND_LEVELS = (
    ("routine", "Routine-Wischdesinfektion"),
    ("mrsa", "Schlussdesinfektion (begrenzt viruzid/bakterizid)"),
    ("noro", "Schlussdesinfektion (viruzid)"),
    ("c_diff", "Schlussdesinfektion (sporizid)"),
    ("base", "Grunddesinfektion"),
)
FALLBACK_KIND = "routine"


def _constraints(schema_editor, mode):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(f"SET CONSTRAINTS ALL {mode}")


def forwards(apps, schema_editor):
    _constraints(schema_editor, "IMMEDIATE")
    Vehicle = apps.get_model("core", "Vehicle")
    Station = apps.get_model("core", "Station")
    Agent = apps.get_model("core", "DisinfectantMaster")
    Level = apps.get_model("core", "DisinfectionLevel")
    Protocol = apps.get_model("core", "DisinfectionProtocol")

    for old, new in STATUS_FORWARD.items():
        Vehicle.objects.filter(tactical_status=old).update(tactical_status=new)

    for station in Station.objects.only("pk").order_by("pk"):
        agent = Agent.objects.filter(station=station).order_by("name", "pk").first()
        minutes = (agent.default_exposure_minutes or None) if agent else None
        levels = {}
        for kind, name in KIND_LEVELS:
            levels[kind], _created = Level.objects.get_or_create(
                station=station,
                name=name,
                defaults={"disinfectant": agent, "release_rule": "exposure", "exposure_minutes": minutes},
            )
        for kind, _name in KIND_LEVELS:
            Protocol.objects.filter(station=station, kind=kind, level__isnull=True).update(level=levels[kind])
        Protocol.objects.filter(station=station, level__isnull=True).update(level=levels[FALLBACK_KIND])
    _constraints(schema_editor, "DEFERRED")


def backwards(apps, schema_editor):
    _constraints(schema_editor, "IMMEDIATE")
    Vehicle = apps.get_model("core", "Vehicle")
    Protocol = apps.get_model("core", "DisinfectionProtocol")
    for new, old in STATUS_BACKWARD.items():
        Vehicle.objects.filter(tactical_status=new).update(tactical_status=old)
    for kind, name in KIND_LEVELS:
        Protocol.objects.filter(level__name=name).update(kind=kind)
    _constraints(schema_editor, "DEFERRED")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0067_fleet_neutral_status"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="vehicle",
            name="tactical_status",
            field=models.CharField(
                choices=[
                    ("ready", "Einsatzbereit"),
                    ("limited", "Eingeschränkt"),
                    ("disinfection", "Desinfektion"),
                    ("workshop", "Werkstatt"),
                    ("out_of_service", "Außer Dienst"),
                ],
                default="ready",
                max_length=20,
                verbose_name="Fahrzeugzustand",
            ),
        ),
        migrations.CreateModel(
            name="DisinfectionLevel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80, verbose_name="Stufe")),
                (
                    "release_rule",
                    models.CharField(
                        choices=[("dry", "Nach Antrocknen"), ("exposure", "Nach Einwirkzeit")],
                        default="exposure",
                        max_length=12,
                        verbose_name="Freigabe",
                    ),
                ),
                (
                    "exposure_minutes",
                    models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="Einwirkzeit (Minuten)"),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="In Verwendung")),
                ("rule_confirmed_at", models.DateTimeField(blank=True, null=True, verbose_name="Bestätigt am")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "disinfectant",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="levels",
                        to="core.disinfectantmaster",
                        verbose_name="Desinfektionsmittel",
                    ),
                ),
                (
                    "rule_confirmed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Bestätigt von",
                    ),
                ),
                (
                    "station",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="disinfection_levels",
                        to="core.station",
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.AddConstraint(
            model_name="disinfectionlevel",
            constraint=models.UniqueConstraint(fields=("station", "name"), name="unique_station_disinfection_level"),
        ),
        migrations.AddConstraint(
            model_name="disinfectionlevel",
            constraint=models.CheckConstraint(
                condition=models.Q(("exposure_minutes__isnull", True), ("exposure_minutes__gte", 1), _connector="OR"),
                name="disinf_level_minutes_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="disinfectionlevel",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("rule_confirmed_at__isnull", True),
                    models.Q(
                        ("disinfectant__isnull", False),
                        models.Q(("release_rule", "dry"), ("exposure_minutes__isnull", False), _connector="OR"),
                    ),
                    _connector="OR",
                ),
                name="disinf_level_confirmed_complete",
            ),
        ),
        migrations.AddField(
            model_name="disinfectionprotocol",
            name="level",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="protocols",
                to="core.disinfectionlevel",
                verbose_name="Stufe",
            ),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(
            model_name="disinfectionprotocol",
            name="kind",
        ),
    ]
