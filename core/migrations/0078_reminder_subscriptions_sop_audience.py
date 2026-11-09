"""Fristen-Erinnerungen und Lesepflicht (Roadmap 0.28, Paket P2).

- Membership: Bereiche der Fristen-Erinnerungen je Person (leer = Standard nach
  Funktion und Rolle) und E-Mail-Zustellung (Standard aus).
- Station: „Namen bei Lesebestätigungen anzeigen“ (Standard aus; nur mit
  Vereinbarung der Beschäftigtenvertretung einschalten).
- SOPDocument: Zielgruppe nach Funktion (Standard leer = ohne Einschränkung).
- WorkerJobState: letzter Lauf der Erinnerungen im notify-worker.
- Daten: Funktionen am Dienstkonto „Wachenterminal“ werden entfernt; das Konto
  darf keine Funktion haben (AGENTS.md § 4). Eine Zeile je Wache, deshalb ein
  einzelnes UPDATE.

Rückweg: Die Schemaänderungen werden entfernt (die neuen Spalten und die
Tabelle WorkerJobState gehen dabei verloren; sie enthalten nur Einstellungen
und Zeitstempel). Entfernte Funktionen am Terminal-Konto kommen nicht zurück;
sie waren nie zulässig.
"""

from django.db import migrations, models


FUNCTION_FIELDS = ("is_mpg_lead", "is_hygiene_lead", "is_material_lead", "is_fleet_lead", "is_safety_lead")


def clear_terminal_functions(apps, schema_editor):
    Membership = apps.get_model("core", "Membership")
    StationTerminalCode = apps.get_model("core", "StationTerminalCode")
    service_ids = list(StationTerminalCode.objects.values_list("service_user_id", flat=True))
    if not service_ids:
        return
    flagged = models.Q()
    for field in FUNCTION_FIELDS:
        flagged |= models.Q(**{field: True})
    Membership.objects.filter(user_id__in=service_ids).filter(flagged).update(
        **{field: False for field in FUNCTION_FIELDS}
    )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0076_sop_deadlines_and_reminders'),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkerJobState',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=40, unique=True)),
                ('last_started_at', models.DateTimeField(blank=True, null=True)),
                ('last_finished_at', models.DateTimeField(blank=True, null=True)),
                ('last_failed_at', models.DateTimeField(blank=True, null=True)),
                ('last_period', models.CharField(blank=True, default='', max_length=10)),
                ('last_count', models.PositiveIntegerField(default=0)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.AddField(
            model_name='membership',
            name='remind_fleet',
            field=models.BooleanField(blank=True, default=None, null=True, verbose_name='Erinnerungen: Fahrzeuge'),
        ),
        migrations.AddField(
            model_name='membership',
            name='remind_material',
            field=models.BooleanField(blank=True, default=None, null=True, verbose_name='Erinnerungen: Material'),
        ),
        migrations.AddField(
            model_name='membership',
            name='remind_mpg',
            field=models.BooleanField(blank=True, default=None, null=True, verbose_name='Erinnerungen: Medizinprodukte'),
        ),
        migrations.AddField(
            model_name='membership',
            name='remind_sop',
            field=models.BooleanField(blank=True, default=None, null=True, verbose_name='Erinnerungen: Dienstanweisungen'),
        ),
        migrations.AddField(
            model_name='membership',
            name='remind_tasks',
            field=models.BooleanField(blank=True, default=None, null=True, verbose_name='Erinnerungen: Aufgaben und Prüfungen'),
        ),
        migrations.AddField(
            model_name='membership',
            name='reminder_email',
            field=models.BooleanField(default=False, help_text='Fristen-Erinnerungen und Wochenübersicht auch an die E-Mail-Adresse des Kontos.', verbose_name='Erinnerungen zusätzlich per E-Mail'),
        ),
        migrations.AddField(
            model_name='sopdocument',
            name='target_function',
            field=models.CharField(blank=True, default='', help_text='Leer = ohne Einschränkung nach Funktion', max_length=20, verbose_name='Zielgruppe (Funktion)'),
        ),
        migrations.AddField(
            model_name='station',
            name='sop_receipt_names_agreed',
            field=models.BooleanField(default=False, help_text='Nur einschalten, wenn eine Vereinbarung mit der Beschäftigtenvertretung (Betriebsrat, Personalrat oder MAV) das erlaubt. Aus: Schichtleitung und Master-Admin sehen nur Anzahl und Quote, keine Namen und keinen Export mit Namen.', verbose_name='Namen bei Lesebestätigungen von Dienstanweisungen anzeigen'),
        ),
        migrations.RunPython(clear_terminal_functions, migrations.RunPython.noop),
    ]
