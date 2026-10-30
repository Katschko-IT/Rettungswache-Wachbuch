"""0.27 „Nachweise geschützt“: Nachweise hängen nur per PROTECT an ihren Objekten.

- Prüfungen, Funktionskontrollen, Einweisungen, Übernahmen, Desinfektionen,
  Versionen und Quittierungen von Dienstanweisungen, Übergabe- und
  Wiki-Revisionen sowie gerätebezogene Mängel: on_delete CASCADE/SET_NULL →
  PROTECT (core/evidence.py). Ohne SQL: on_delete wirkt nur im ORM.
- Desinfektionsmittel bekommen „In Gebrauch“ (Standard: ja), statt gelöscht
  zu werden.
- Medizingeräte: Auswahltext „Außer Betrieb genommen“ statt „Ausgemustert“
  (gespeicherter Wert bleibt ``decommissioned``).

Keine Datenänderung; sicher für das unbeaufsichtigte Update. Rückweg: die
Migration rückgängig machen entfernt nur die Spalte ``is_active``.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0067_fleet_neutral_status"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="disinfectantmaster",
            name="is_active",
            field=models.BooleanField(
                default=True,
                help_text="Mittel, die nicht mehr in Gebrauch sind, stehen im Desinfektionsprotokoll nicht mehr zur Wahl. Bestehende Nachweise bleiben erhalten.",
                verbose_name="In Gebrauch",
            ),
        ),
        migrations.AlterField(
            model_name="defect",
            name="medical_device",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="defects",
                to="core.medicaldevice",
            ),
        ),
        migrations.AlterField(
            model_name="deviceroutinecheck",
            name="device",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="routine_checks",
                to="core.medicaldevice",
            ),
        ),
        migrations.AlterField(
            model_name="devicetrainingrecord",
            name="device",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="trainings",
                to="core.medicaldevice",
            ),
        ),
        migrations.AlterField(
            model_name="devicetrainingrecord",
            name="trainee",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="device_trainings",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="disinfectionprotocol",
            name="vehicle",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="disinfections",
                to="core.vehicle",
            ),
        ),
        migrations.AlterField(
            model_name="handoverrevision",
            name="handover",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="revisions",
                to="core.handoverentry",
            ),
        ),
        migrations.AlterField(
            model_name="maintenancelog",
            name="device",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="maintenance_logs",
                to="core.medicaldevice",
            ),
        ),
        migrations.AlterField(
            model_name="medicaldevice",
            name="current_status",
            field=models.CharField(
                choices=[
                    ("ready", "Einsatzklar"),
                    ("limited", "Eingeschränkt"),
                    ("maintenance", "In Wartung / STK"),
                    ("oob", "Außer Betrieb (Gesperrt)"),
                    ("decommissioned", "Außer Betrieb genommen"),
                ],
                default="ready",
                max_length=20,
                verbose_name="Betriebsstatus",
            ),
        ),
        migrations.AlterField(
            model_name="sopreceipt",
            name="revision",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="receipts",
                to="core.soprevision",
            ),
        ),
        migrations.AlterField(
            model_name="sopreceipt",
            name="sop",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="receipts",
                to="core.sopdocument",
            ),
        ),
        migrations.AlterField(
            model_name="soprevision",
            name="sop",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="revisions",
                to="core.sopdocument",
            ),
        ),
        migrations.AlterField(
            model_name="vehiclehandover",
            name="vehicle",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="handovers",
                to="core.vehicle",
            ),
        ),
        migrations.AlterField(
            model_name="wikirevision",
            name="article",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="revisions",
                to="core.wikiarticle",
                verbose_name="Artikel",
            ),
        ),
    ]
