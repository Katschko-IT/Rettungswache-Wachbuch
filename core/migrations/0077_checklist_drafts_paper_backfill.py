"""0.28 Checklisten: Zwischenstände in eigener Tabelle, Nachtrag vom Papierbogen, Rückverweis am Mangel.

- ``ChecklistDraft`` (neu, veränderbar, kein Nachweis): höchstens ein
  Zwischenstand je Wache und Checkliste, von der Besatzung geteilt.
- ``ChecklistCompletion`` ist wieder strikt append-only. Bisherige
  Zwischenstände (``is_draft=True``, eingeführt mit 0075) wandern in
  ``ChecklistDraft``: je Wache und Checkliste nur der neueste, mit seiner
  Zeit, Person, Notiz und den Ergebnissen. Danach werden die Zwischenstands-
  Zeilen aus ``core_checklistcompletion`` gelöscht und die Spalte
  ``is_draft`` entfällt. Endgültige Abschlüsse bleiben unverändert.
- ``ChecklistCompletion.is_paper_backfill``/``occurred_at``: Nachtrag vom
  Papierbogen mit Ereigniszeit (Standard: kein Nachtrag, leer).
- ``Defect.source_checklist_run`` (PROTECT, leer für bestehende Mängel) und
  eine Kopie von Kennung und Text des Prüfpunkts.

Die Migration läuft mit den Rechten des Datenbank-Eigentümers vor
``grant_database_access`` (scripts/migrate.sh); nur deshalb darf sie die
Zwischenstands-Zeilen der append-only Tabelle löschen. Der Datenschritt ist
deterministisch (neuester Zwischenstand nach Zeit, dann Kennung) und
berührt nur Zeilen mit ``is_draft=True``.

Rückweg: Die Spalte ``is_draft`` kommt zurück (Standard „nein“), jeder
Zwischenstand wird wieder eine Zeile mit ``is_draft=True`` (Zeit = letzte
Änderung, Person = zuletzt bearbeitet von), danach entfallen die neue Tabelle
und die neuen Felder. Angaben zum Papier-Nachtrag und der Rückverweis am
Mangel gehen beim Rückweg verloren.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

BATCH = 500


def _fire_deferred_constraints(schema_editor):
    """PostgreSQL: ausstehende Fremdschlüssel-Prüfungen jetzt ausführen.

    Gelöschte oder angelegte Zeilen hinterlassen verzögerte Prüfungen; ohne
    diesen Schritt lehnt PostgreSQL das folgende ALTER TABLE derselben
    Migration ab („pending trigger events“). SQLite braucht das nicht.
    """
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            cursor.execute("SET CONSTRAINTS ALL DEFERRED")


def move_legacy_drafts(apps, schema_editor):
    ChecklistCompletion = apps.get_model("core", "ChecklistCompletion")
    ChecklistDraft = apps.get_model("core", "ChecklistDraft")
    drafts = ChecklistCompletion.objects.filter(is_draft=True).order_by(
        "station_id", "checklist_id", "-created_at", "-id"
    )
    seen = set()
    for row in drafts.iterator(chunk_size=BATCH):
        key = (row.station_id, row.checklist_id)
        if key in seen:
            continue
        seen.add(key)
        draft = ChecklistDraft.objects.create(
            station_id=row.station_id,
            checklist_id=row.checklist_id,
            created_by_id=row.completed_by_id,
            updated_by_id=row.completed_by_id,
            item_results=row.item_results if isinstance(row.item_results, dict) else {},
            note=row.note or "",
        )
        # Alter des Zwischenstands behalten (housekeeping löscht nach 30 Tagen).
        ChecklistDraft.objects.filter(pk=draft.pk).update(created_at=row.created_at, updated_at=row.created_at)
    while True:
        ids = list(ChecklistCompletion.objects.filter(is_draft=True).order_by("id").values_list("id", flat=True)[:BATCH])
        if not ids:
            break
        ChecklistCompletion.objects.filter(id__in=ids).delete()
    _fire_deferred_constraints(schema_editor)


def restore_legacy_drafts(apps, schema_editor):
    ChecklistCompletion = apps.get_model("core", "ChecklistCompletion")
    ChecklistDraft = apps.get_model("core", "ChecklistDraft")
    for draft in ChecklistDraft.objects.order_by("id").iterator(chunk_size=BATCH):
        row = ChecklistCompletion.objects.create(
            station_id=draft.station_id,
            checklist_id=draft.checklist_id,
            completed_by_id=draft.updated_by_id,
            note=draft.note,
            item_results=draft.item_results,
            is_draft=True,
        )
        ChecklistCompletion.objects.filter(pk=row.pk).update(created_at=draft.updated_at)
    _fire_deferred_constraints(schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0076_sop_deadlines_and_reminders"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ChecklistDraft",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("item_results", models.JSONField(blank=True, default=dict, verbose_name="Ergebnisse je Prüfpunkt")),
                ("note", models.CharField(blank=True, max_length=300)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "checklist",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="drafts", to="core.checklist"
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL
                    ),
                ),
                (
                    "station",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="checklist_drafts", to="core.station"
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL
                    ),
                ),
            ],
            options={
                "ordering": ["-updated_at"],
                "indexes": [models.Index(fields=["updated_at"], name="checklist_draft_updated_idx")],
                "constraints": [
                    models.UniqueConstraint(fields=("station", "checklist"), name="checklist_draft_one_per_station")
                ],
            },
        ),
        migrations.AddField(
            model_name="checklistcompletion",
            name="is_paper_backfill",
            field=models.BooleanField(default=False, verbose_name="Nachtrag vom Papierbogen"),
        ),
        migrations.AddField(
            model_name="checklistcompletion",
            name="occurred_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Ereigniszeitpunkt (Papierbogen)"),
        ),
        migrations.AddField(
            model_name="defect",
            name="source_checklist_run",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="source_defects",
                to="core.checklistcompletion",
                verbose_name="Aus Checklisten-Lauf",
            ),
        ),
        migrations.AddField(
            model_name="defect",
            name="source_item_id",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="Prüfpunkt (Kennung)"),
        ),
        migrations.AddField(
            model_name="defect",
            name="source_item_text",
            field=models.CharField(
                blank=True, default="", max_length=200, verbose_name="Prüfpunkt (Text zum Zeitpunkt des Laufs)"
            ),
        ),
        migrations.AddIndex(
            model_name="defect",
            index=models.Index(fields=["station", "source_item_id"], name="defect_station_source_idx"),
        ),
        migrations.RunPython(move_legacy_drafts, restore_legacy_drafts),
        migrations.RemoveField(
            model_name="checklistcompletion",
            name="is_draft",
        ),
    ]
