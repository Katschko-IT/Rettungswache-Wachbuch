"""Hilfetext der Kaffeekasse nennt den Produktnamen Staffeta (reine Textänderung).

Vorwärts und rückwärts: Nur ``help_text`` an ``CoffeeFund.reminder_day`` ändert sich.
Es gibt keine Schemaänderung und keine Datenänderung; PostgreSQL schreibt keine Zeile um.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0080_paper_backfill_all_records"),
    ]

    operations = [
        migrations.AlterField(
            model_name="coffeefund",
            name="reminder_day",
            field=models.PositiveSmallIntegerField(
                default=10,
                help_text="Ab diesem Tag des Monats erinnert Staffeta an einen offenen Beitrag. 0 = keine Erinnerung.",
                verbose_name="Erinnerung ab Tag",
            ),
        ),
    ]
