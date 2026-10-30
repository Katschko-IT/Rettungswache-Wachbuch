"""Entfernt die alten Lager-Spiegelungen von Schlüsseln, Funkgeräten und Pool-Geräten.

Bis 0.26.0 legte die Lagerübersicht für jedes Inventarstück („Geräte &
Fahrzeuge“, InventoryItem) einen Lagerartikel an – bis 0.25.0 mit dem
Mindestbestand 5. Diese Zeilen erschienen als „Kein Bestand“ im Lager und als
„Unter Mindestbestand (0 von 5)“ auf dem Wachen-Display und in der
Nachbestellung. Gelöscht wird nur, was die Spiegelung unverändert angelegt hat:
gleicher Schlüssel in derselben Wache, Standardwerte, keine Chargen, kein
Bestand, keine Lagerbewegung. Von Hand gepflegte Artikel bleiben stehen.
"""

from django.db import migrations
from django.db.models import Exists, OuterRef, Q

# (Mindestbestand, Sollbestand) der Spiegelung: Modell-Standard bis 0.25.0, 0/0 ab 0.26.0.
MIRROR_STOCK_LEVELS = Q(min_stock=5, target_stock=10) | Q(min_stock=0, target_stock=0)


def untouched_inventory_mirrors(apps):
    MedicalItem = apps.get_model("core", "MedicalItem")
    InventoryItem = apps.get_model("core", "InventoryItem")
    ItemBatch = apps.get_model("core", "ItemBatch")
    StockItem = apps.get_model("core", "StockItem")
    StockMovement = apps.get_model("core", "StockMovement")
    return (
        MedicalItem.objects.filter(
            Exists(InventoryItem.objects.filter(station_id=OuterRef("station_id"), item_id=OuterRef("slug")))
        )
        .filter(
            MIRROR_STOCK_LEVELS,
            category__in=("other", "airway"),
            unit="pcs",
            pzn="",
            gtin="",
            notes="",
            requires_cooling=False,
            room_temp_max_days__isnull=True,
        )
        .exclude(Exists(ItemBatch.objects.filter(item_id=OuterRef("pk"))))
        .exclude(Exists(StockItem.objects.filter(item_id=OuterRef("pk"))))
        .exclude(Exists(StockMovement.objects.filter(item_id=OuterRef("pk"))))
    )


def remove_inventory_mirrors(apps, schema_editor):
    untouched_inventory_mirrors(apps).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0065_demo_daily_stat"),
    ]

    operations = [
        migrations.RunPython(remove_inventory_mirrors, migrations.RunPython.noop),
    ]
