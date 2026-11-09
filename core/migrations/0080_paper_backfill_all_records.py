"""Nachtrag vom Papierbogen für Fahrzeugübernahme, Desinfektion und Funktionskontrolle (0.28, P4).

Vorwärts:

1. Neue Felder ``is_paper_backfill`` (Standard ``False``) und ``occurred_at``
   (leer) an ``VehicleHandover``, ``DisinfectionProtocol`` und
   ``DeviceRoutineCheck``. Bestehende Zeilen sind damit gewöhnliche Einträge;
   PostgreSQL schreibt dafür keine Zeile um.
2. Übergaben: Eine Ereigniszeit ohne Häkchen „Nachtrag vom Papierbogen“ wurde
   bisher gespeichert, aber nie angezeigt. Sie wird geleert (eine
   UPDATE-Anweisung über die Zeilen mit diesem Zustand). Der Wert bleibt im
   Schnappschuss der Übergabe-Version (``HandoverRevision``) erhalten.
3. Datenbank-Bedingungen: Ereigniszeit nur mit Häkchen (alle vier Tabellen),
   bei den drei neuen Feldpaaren außerdem immer mit Häkchen.

Rückwärts: Bedingungen und neue Felder werden entfernt; geleerte
Ereigniszeiten der Übergaben bleiben leer (die Werte stehen weiterhin in den
Übergabe-Versionen).
"""
from django.db import migrations, models


def clear_stray_occurred_at(apps, schema_editor):
    HandoverEntry = apps.get_model("core", "HandoverEntry")
    HandoverEntry.objects.filter(is_paper_backfill=False, occurred_at__isnull=False).update(occurred_at=None)


STRICT = models.Q(models.Q(("is_paper_backfill", False), ("occurred_at__isnull", True)), models.Q(("is_paper_backfill", True), ("occurred_at__isnull", False)), _connector="OR")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0079_defect_vehicle"),
    ]

    operations = [
        migrations.AddField(
            model_name="deviceroutinecheck",
            name="is_paper_backfill",
            field=models.BooleanField(default=False, verbose_name="Nachtrag vom Papierbogen"),
        ),
        migrations.AddField(
            model_name="deviceroutinecheck",
            name="occurred_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Ereigniszeitpunkt (Papierbogen)"),
        ),
        migrations.AddField(
            model_name="disinfectionprotocol",
            name="is_paper_backfill",
            field=models.BooleanField(default=False, verbose_name="Nachtrag vom Papierbogen"),
        ),
        migrations.AddField(
            model_name="disinfectionprotocol",
            name="occurred_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Ereigniszeitpunkt (Papierbogen)"),
        ),
        migrations.AddField(
            model_name="vehiclehandover",
            name="is_paper_backfill",
            field=models.BooleanField(default=False, verbose_name="Nachtrag vom Papierbogen"),
        ),
        migrations.AddField(
            model_name="vehiclehandover",
            name="occurred_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Ereigniszeitpunkt (Papierbogen)"),
        ),
        migrations.RunPython(clear_stray_occurred_at, migrations.RunPython.noop, elidable=False),
        migrations.AddConstraint(
            model_name="deviceroutinecheck",
            constraint=models.CheckConstraint(condition=STRICT, name="deviceroutinecheck_backfill_time"),
        ),
        migrations.AddConstraint(
            model_name="disinfectionprotocol",
            constraint=models.CheckConstraint(condition=STRICT, name="disinfectionprotocol_backfill_time"),
        ),
        migrations.AddConstraint(
            model_name="handoverentry",
            constraint=models.CheckConstraint(
                condition=models.Q(("is_paper_backfill", True), ("occurred_at__isnull", True), _connector="OR"),
                name="handoverentry_backfill_time",
            ),
        ),
        migrations.AddConstraint(
            model_name="vehiclehandover",
            constraint=models.CheckConstraint(condition=STRICT, name="vehiclehandover_backfill_time"),
        ),
    ]
