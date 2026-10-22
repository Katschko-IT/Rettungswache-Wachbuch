"""Fiktive Demo-Daten für die Fachmodule (MPG, Fuhrpark, Lager, Organisation).

Alle Objekte tragen den Slug-Präfix ``demo-`` und lassen sich dadurch beim
Zurücksetzen gezielt entfernen. Es werden ausschließlich erfundene Geräte,
Fahrzeuge, Artikel und Kontakte angelegt – keine Patienten- oder
Einsatzdaten.
"""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from .fleet_models import DisinfectantMaster, Vehicle, VehicleHandover
from .mpg_models import DeviceRoutineCheck, DeviceTrainingRecord, MaintenanceLog, MedicalDevice
from .orga_models import SOPDocument, SOPReceipt, SOPRevision, StationContact
from .warehouse_models import ItemBatch, MedicalItem, StockItem, StockMovement, StorageLocation

PREFIX = "demo-"
CONTACT_MARKER = "[Demo]"


def reset_module_demo(station) -> None:
    """Entfernt Demo-Objekte der Fachmodule in FK-sicherer Reihenfolge."""
    StockMovement.objects.filter(station=station, item__slug__startswith=PREFIX).delete()
    StockItem.objects.filter(station=station, item__slug__startswith=PREFIX).delete()
    ItemBatch.objects.filter(station=station, item__slug__startswith=PREFIX).delete()
    MedicalItem.objects.filter(station=station, slug__startswith=PREFIX).delete()
    StorageLocation.objects.filter(station=station, slug__startswith=PREFIX).delete()

    vehicles = Vehicle.objects.filter(station=station, slug__startswith=PREFIX)
    for vehicle in vehicles:
        vehicle.disinfections.all().delete()
        vehicle.handovers.all().delete()
    vehicles.delete()
    DisinfectantMaster.objects.filter(station=station, name__startswith=CONTACT_MARKER).delete()

    devices = MedicalDevice.objects.filter(station=station, slug__startswith=PREFIX)
    for device in devices:
        device.routine_checks.all().delete()
        device.trainings.all().delete()
        device.maintenance_logs.all().delete()
    devices.delete()

    sops = SOPDocument.objects.filter(station=station, slug__startswith=PREFIX)
    SOPReceipt.objects.filter(sop__in=sops).delete()
    SOPRevision.objects.filter(sop__in=sops).delete()
    sops.delete()
    StationContact.objects.filter(station=station, name__startswith=CONTACT_MARKER).delete()


def seed_module_demo(station, users: dict) -> None:
    admin = users["demo-admin"]
    lead = users.get("demo-schicht", admin)
    member = users.get("demo-mitglied", admin)
    today = timezone.localdate()

    station.mpg_enabled = True
    station.warehouse_enabled = True
    station.fleet_enabled = True
    station.orga_enabled = True
    station.display_enabled = True
    station.save(update_fields=[
        "mpg_enabled", "warehouse_enabled", "fleet_enabled", "orga_enabled", "display_enabled",
    ])

    # --- MPG -------------------------------------------------------------
    devices = [
        dict(slug="demo-defi-rtw1", name="Defibrillator/Monitor RTW 1",
             category=MedicalDevice.Category.DEFIBRILLATOR, manufacturer="Musterhersteller",
             model_type="Demo-Monitor 3", serial_number="DEMO-0001", inventory_number="INV-1001",
             location="RTW 1", next_stk_date=today + timedelta(days=200),
             next_dguv_date=today + timedelta(days=120)),
        dict(slug="demo-beatmung-rtw1", name="Beatmungsgerät RTW 1",
             category=MedicalDevice.Category.VENTILATOR, manufacturer="Musterhersteller",
             model_type="Demo-Vent 5", serial_number="DEMO-0002", inventory_number="INV-1002",
             location="RTW 1", next_stk_date=today + timedelta(days=12),
             next_dguv_date=today + timedelta(days=60)),
        dict(slug="demo-absaugung-lager", name="Absaugpumpe (Reserve)",
             category=MedicalDevice.Category.SUCTION, manufacturer="Musterhersteller",
             model_type="Demo-Suction", serial_number="DEMO-0003", inventory_number="INV-1003",
             location="Gerätelager", next_stk_date=today - timedelta(days=3),
             current_status=MedicalDevice.Status.MAINTENANCE,
             status_note="STK überfällig – Termin mit Servicepartner vereinbart"),
    ]
    for spec in devices:
        slug = spec.pop("slug")
        device, _ = MedicalDevice.objects.update_or_create(station=station, slug=slug, defaults=spec)
        if not device.maintenance_logs.exists():
            MaintenanceLog.objects.create(
                device=device, station=station, kind=MaintenanceLog.Kind.choices[0][0],
                performed_at=today - timedelta(days=180), performed_by="Demo-Servicepartner",
                passed=True, created_by=admin,
            )
        if not device.routine_checks.exists():
            DeviceRoutineCheck.objects.create(station=station, device=device, performed_by=member)
        if not device.trainings.exists():
            DeviceTrainingRecord.objects.create(
                station=station, device=device, trainee=member, instructor="Demo-Gerätebeauftragte",
            )

    # --- Fuhrpark ----------------------------------------------------------
    DisinfectantMaster.objects.get_or_create(
        station=station, name=f"{CONTACT_MARKER} Flächendesinfektion",
        defaults={"manufacturer": "Musterhersteller", "default_exposure_minutes": 15},
    )
    vehicles = [
        dict(slug="demo-rtw-1", call_sign="RTW 1", license_plate="MU-RD 101",
             vehicle_type=Vehicle.VehicleType.RTW, current_mileage=84200, fuel_level_percent=78,
             adblue_level_percent=64, next_hu_date=today + timedelta(days=140),
             next_uvv_date=today + timedelta(days=25)),
        dict(slug="demo-rtw-2", call_sign="RTW 2", license_plate="MU-RD 102",
             vehicle_type=Vehicle.VehicleType.RTW, current_mileage=132900, fuel_level_percent=35,
             adblue_level_percent=20, next_hu_date=today + timedelta(days=9)),
    ]
    for spec in vehicles:
        slug = spec.pop("slug")
        vehicle, _ = Vehicle.objects.update_or_create(station=station, slug=slug, defaults=spec)
        if not vehicle.handovers.exists():
            VehicleHandover.objects.create(
                station=station, vehicle=vehicle, crew_member=lead,
                mileage=vehicle.current_mileage, fuel_percent=vehicle.fuel_level_percent,
                adblue_percent=vehicle.adblue_level_percent, notes="Demo-Übernahme ohne Befund",
            )

    # --- Lager -------------------------------------------------------------
    central, _ = StorageLocation.objects.get_or_create(
        station=station, slug="demo-zentrallager", defaults={"name": "Zentrallager (Demo)"},
    )
    fridge, _ = StorageLocation.objects.get_or_create(
        station=station, slug="demo-kuehlschrank",
        defaults={"name": "Medikamentenkühlschrank (Demo)", "is_cold_storage": True},
    )
    items = [
        ("demo-nacl-500", "Infusionslösung 500 ml (Demo)", central, 30, 7, 40, 120),
        ("demo-handschuhe-m", "Untersuchungshandschuhe M (Demo)", central, 4, 10, 30, 400),
        ("demo-kuehlartikel", "Kühlpflichtiger Artikel (Demo)", fridge, 6, 2, 6, 45),
    ]
    for slug, name, location, qty, min_stock, target, days in items:
        item, _ = MedicalItem.objects.update_or_create(
            station=station, slug=slug,
            defaults={"name": name, "min_stock": min_stock, "target_stock": target,
                      "requires_cooling": location.is_cold_storage},
        )
        batch = item.batches.first() or ItemBatch.objects.create(
            item=item, station=station, batch_number=f"DEMO-{slug[-4:].upper()}",
            manufacturer_exp_date=today + timedelta(days=days),
        )
        StockItem.objects.update_or_create(
            station=station, item=item, batch=batch, location=location, defaults={"quantity": qty},
        )

    # --- Organisation ------------------------------------------------------
    sop, created = SOPDocument.objects.get_or_create(
        station=station, slug="demo-sop-fahrzeugdesinfektion",
        defaults={"title": "Fahrzeugdesinfektion nach Transport (Demo)", "doc_number": "DEMO-SOP-01", "created_by": admin,
                  "review_due_date": today + timedelta(days=300)},
    )
    if created or not sop.revisions.exists():
        SOPRevision.objects.create(
            sop=sop, version_label=sop.current_version,
            content_markdown=(
                "Fiktive Musteranweisung für die Demo.\n\n"
                "1. Schutzausrüstung anlegen.\n"
                "2. Kontaktflächen mit freigegebenem Mittel wischen.\n"
                "3. Einwirkzeit abwarten, dann Fahrzeug freigeben."
            ),
            change_summary="Erstfassung (Demo)", approved_by=admin,
        )
    contacts = [
        ("Werkstatt", "+49 000 0000001", True),
        ("Medizintechnik-Service", "+49 000 0000002", True),
        ("Hygienebeauftragte", "+49 000 0000003", False),
    ]
    for rank, (name, phone, speed) in enumerate(contacts, start=1):
        StationContact.objects.get_or_create(
            station=station, name=f"{CONTACT_MARKER} {name}",
            defaults={"phone_primary": phone, "is_speed_dial": speed, "order_rank": rank},
        )
