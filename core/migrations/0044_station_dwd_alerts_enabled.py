from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0043_station_traffic_customization"),
    ]

    operations = [
        migrations.AddField(
            model_name="station",
            name="dwd_alerts_enabled",
            field=models.BooleanField(default=False, help_text="Ruft Warnungen über Bright Sky ab. Dabei wird die auf zwei Nachkommastellen gerundete Koordinate der Wache übermittelt. Benötigt Koordinaten der Wache.", verbose_name="Amtliche DWD-Wetterwarnungen"),
        ),
    ]
