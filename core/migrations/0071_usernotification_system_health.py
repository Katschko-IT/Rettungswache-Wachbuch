"""0.27: Benachrichtigungsart „Technischer Hinweis zum Server“.

Meldungen der Host-Überwachung (core/host_health.py) an die Master-Admins.
Nur die Auswahlliste ändert sich; PostgreSQL bekommt keine DDL (sqlmigrate
ist leer). Rückweg ohne Datenänderung.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0070_masterdata_import_altbestand"),
    ]

    operations = [
        migrations.AlterField(
            model_name="usernotification",
            name="kind",
            field=models.CharField(
                choices=[
                    ("vehicle_ready", "Fahrzeug kann freigegeben werden"),
                    ("coffee_due", "Kaffeekasse: Beitrag offen"),
                    ("system_health", "Technischer Hinweis zum Server"),
                ],
                max_length=32,
            ),
        ),
    ]
