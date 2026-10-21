from django.db import migrations, models


def keep_existing_traffic_behaviour(apps, schema_editor):
    Station = apps.get_model("core", "Station")
    Station.objects.filter(traffic_enabled=True).update(
        traffic_roads="A2, A33",
        traffic_radius_km=25,
        traffic_warning_areas="Gütersloh, Bielefeld, Steinhagen, Kreis Gütersloh",
        traffic_local_sources=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0042_station_traffic_enabled"),
    ]

    operations = [
        migrations.AddField(
            model_name="station",
            name="traffic_roads",
            field=models.CharField(blank=True, default="", help_text="Kommagetrennt, z. B. A2, A33. Benötigt Koordinaten der Wache.", max_length=60, verbose_name="Autobahnen und Bundesstraßen"),
        ),
        migrations.AddField(
            model_name="station",
            name="traffic_radius_km",
            field=models.PositiveSmallIntegerField(default=25, verbose_name="Umkreis in km"),
        ),
        migrations.AddField(
            model_name="station",
            name="traffic_warning_areas",
            field=models.CharField(blank=True, default="", help_text="Kommagetrennte Orts- oder Kreisnamen. Leer: Ort der Wache.", max_length=200, verbose_name="Gebiete für Bevölkerungswarnungen"),
        ),
        migrations.AddField(
            model_name="station",
            name="traffic_local_sources",
            field=models.BooleanField(default=False, verbose_name="Kommunale Quellen Steinhagen und Kreis Gütersloh"),
        ),
        migrations.RunPython(keep_existing_traffic_behaviour, migrations.RunPython.noop),
    ]
