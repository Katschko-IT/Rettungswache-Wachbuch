# Mangel in drei Tipps (0.28): Fahrzeug als Bezug eines Mangels.
#
# Nur ein neues, leeres Feld (NULL für alle vorhandenen Mängel): keine
# Datenänderung, deterministisch, ohne Verlust. Vorhandene Mängel behalten
# ihren Bezug als Text in asset_ref und werden weiterhin über den exakten Text
# zugeordnet (core/defect_refs.py).
#
# Rückweg: ``python manage.py migrate core 0076`` (bzw. die Vorgängermigration
# nach dem Umhängen durch die Integration) entfernt die Spalte wieder. Dabei
# geht nur die Verknüpfung verloren; der Bezug als Text bleibt erhalten.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0076_sop_deadlines_and_reminders"),
    ]

    operations = [
        migrations.AddField(
            model_name="defect",
            name="vehicle",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="defects",
                to="core.vehicle",
            ),
        ),
    ]
