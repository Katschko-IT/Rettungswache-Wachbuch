"""Fiktive Demo-Daten für die Fachmodule (MPG, Fuhrpark, Lager, Organisation).

Alle Objekte tragen den Slug-Präfix ``demo-`` und lassen sich dadurch beim
Zurücksetzen gezielt entfernen. Es werden ausschließlich erfundene Geräte,
Fahrzeuge, Artikel und Kontakte angelegt – keine Patienten- oder
Einsatzdaten. Hersteller, Seriennummern, Chargen und Rufnummern sind
erfunden; die Rufnummern stammen aus dem für Film und Fernsehen
freigehaltenen Berliner Block 030 23125.
"""
from __future__ import annotations

from datetime import date, timedelta

from django.utils import timezone

from .device_status import DEVICE_TO_ASSET
from .fleet_models import DisinfectantMaster, DisinfectionProtocol, Vehicle, VehicleHandover
from .mpg_models import DeviceRoutineCheck, DeviceTrainingRecord, MaintenanceLog, MedicalDevice
from .orga_models import SOPDocument, SOPReceipt, SOPRevision, StationContact
from .wachalltag_models import AssetEvent, InventoryEvent, InventoryItem, StationAsset
from .warehouse_models import ItemBatch, MedicalItem, StockItem, StockMovement, StorageLocation

PREFIX = "demo-"
CONTACT_MARKER = "[Demo]"

# Fahrzeugstatus → Status in „Geräte & Fahrzeuge“.
VEHICLE_TO_ASSET = {
    Vehicle.TacticalStatus.STATUS_1: StationAsset.Status.READY,
    Vehicle.TacticalStatus.STATUS_2: StationAsset.Status.READY,
    Vehicle.TacticalStatus.DISINFECTION: StationAsset.Status.LIMITED,
    Vehicle.TacticalStatus.WORKSHOP: StationAsset.Status.WORKSHOP,
    Vehicle.TacticalStatus.STATUS_6: StationAsset.Status.OOB,
}


def reset_module_demo(station) -> None:
    """Entfernt Demo-Objekte der Fachmodule in FK-sicherer Reihenfolge."""
    # Lagerbewegungen sind append-only: Der App-Rolle fehlt DELETE darauf, und
    # PostgreSQL prüft das Recht auch, wenn keine Zeile passt. Beim ersten
    # Laden (``load_demo_data`` als App-Rolle) gibt es nichts zu löschen.
    movements = StockMovement.objects.filter(station=station, item__slug__startswith=PREFIX)
    if movements.exists():
        movements.delete()
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

    AssetEvent.objects.filter(station=station, asset__asset_id__startswith=PREFIX).delete()
    StationAsset.objects.filter(station=station, asset_id__startswith=PREFIX).delete()
    InventoryEvent.objects.filter(station=station, item__item_id__startswith=PREFIX).delete()
    InventoryItem.objects.filter(station=station, item_id__startswith=PREFIX).delete()

    sops = SOPDocument.objects.filter(station=station, slug__startswith=PREFIX)
    SOPReceipt.objects.filter(sop__in=sops).delete()
    SOPRevision.objects.filter(sop__in=sops).delete()
    sops.delete()
    StationContact.objects.filter(station=station, name__startswith=CONTACT_MARKER).delete()


def _months_before(day: date, months: int) -> date:
    """Gleicher Tag ``months`` Monate früher (am Monatsende gekürzt)."""
    index = day.year * 12 + day.month - 1 - months
    year, month = divmod(index, 12)
    month += 1
    for candidate in (day.day, 30, 29, 28):
        try:
            return date(year, month, min(day.day, candidate))
        except ValueError:
            continue
    raise ValueError(day)


def seed_module_demo(station, users: dict, *, marker: str = CONTACT_MARKER, fresh: bool = False) -> None:
    from .demo import insert_at, local_time

    admin = users["demo-admin"]
    lead = users.get("demo-schicht", admin)
    member = users.get("demo-mitglied", admin)
    jonas = users.get("demo-jonas", lead)
    lea = users.get("demo-lea", member)
    nora = users.get("demo-nora", admin)
    now = timezone.now()
    today = timezone.localdate()
    shift_start = local_time(today, 7) if local_time(today, 7) < now else local_time(today, 7) - timedelta(hours=12)

    def label(text: str) -> str:
        return f"{marker} {text}" if marker else text

    # Neu anlegen statt nachschlagen: Eine Demo-Wache ist frisch, die geteilte
    # Demo räumt vorher ihre eigenen Objekte weg.
    if not fresh:
        reset_module_demo(station)

    station.mpg_enabled = True
    station.warehouse_enabled = True
    station.fleet_enabled = True
    station.orga_enabled = True
    station.display_enabled = True
    station.pinboard_enabled = True
    station.save(update_fields=[
        "mpg_enabled", "warehouse_enabled", "fleet_enabled", "orga_enabled", "display_enabled", "pinboard_enabled",
    ])

    # --- Medizinprodukte: Fristen passen zu den Prüfnachweisen ---------------
    service = "Medizintechnik-Service Musterstadt"
    devices_spec = [
        # slug, Name, Kategorie, Hersteller, Typ, Serie, Ort, STK in Tagen (None = keine Pflicht),
        # STK-Intervall, MTK (Blutdruck), DGUV in Tagen, Status, letzter Check vor Stunden, eingewiesen
        ("demo-defi-rtw1", "Defibrillator/Monitor RTW 83-1", MedicalDevice.Category.DEFIBRILLATOR,
         "Medica Systems", "Monitor/Defibrillator M3", "M3-2219-0412", "RTW 1/83-1", 200, 24, True, 140,
         MedicalDevice.Status.READY, 26, (member, lead, jonas, lea)),
        ("demo-defi-rtw2", "Defibrillator/Monitor RTW 83-2", MedicalDevice.Category.DEFIBRILLATOR,
         "Medica Systems", "Monitor/Defibrillator M3", "M3-2219-0587", "RTW 1/83-2", 40, 24, True, 75,
         MedicalDevice.Status.READY, 3, (member, lead, jonas, lea, nora)),
        ("demo-defi-nef", "Defibrillator/Monitor NEF 82-1", MedicalDevice.Category.DEFIBRILLATOR,
         "Medica Systems", "Monitor/Defibrillator M3 compact", "M3C-2301-0033", "NEF 1/82-1", 300, 24, True, 210,
         MedicalDevice.Status.READY, 5, (lead, jonas, nora)),
        ("demo-beatmung-rtw1", "Beatmungsgerät RTW 83-1", MedicalDevice.Category.VENTILATOR,
         "Respira Medical", "Notfallbeatmung V5", "V5-21-11873", "RTW 1/83-1", 12, 12, False, 160,
         MedicalDevice.Status.READY, 26, (lead, jonas)),
        ("demo-spritzenpumpe-rtw1", "Spritzenpumpe RTW 83-1", MedicalDevice.Category.PERFUSOR,
         "Infusa", "Spritzenpumpe SP 50", "SP50-1940-221", "RTW 1/83-1", 150, 24, False, 150,
         MedicalDevice.Status.READY, 26, (member, lead, jonas, lea)),
        ("demo-thoraxkompression-rtw2", "Thoraxkompressionsgerät RTW 83-2", MedicalDevice.Category.CPR,
         "Vitalis Medizintechnik", "Kompressionshilfe K2", "K2-2207-0091", "RTW 1/83-2", 90, 12, False, 90,
         MedicalDevice.Status.READY, 3, (lead, jonas, nora)),
        ("demo-pulsoxy-nef", "Pulsoximeter NEF 82-1", MedicalDevice.Category.DIAGNOSTIC,
         "Vitalis Medizintechnik", "Pulsoximeter PX 2", "PX2-0815-773", "NEF 1/82-1", None, 24, False, 230,
         MedicalDevice.Status.READY, 5, (lead, nora)),
        ("demo-absaugung-lager", "Absaugpumpe (Reserve)", MedicalDevice.Category.SUCTION,
         "Aspira", "Akku-Absaugpumpe A 40", "A40-1822-010", "Gerätelager", -3, 24, False, 45,
         MedicalDevice.Status.MAINTENANCE, 200, (member, lead, jonas)),
    ]
    devices = []
    for (slug, name, category, maker, model_type, serial, location, stk_days, stk_months, mtk, dguv_days,
         status, checked_hours, trained) in devices_spec:
        next_stk = today + timedelta(days=stk_days) if stk_days is not None else None
        devices.append(MedicalDevice(
            station=station, slug=slug, name=name, category=category, manufacturer=maker, model_type=model_type,
            serial_number=serial, inventory_number=f"MPG-{len(devices) + 101:04d}", location=location,
            is_anlage_1=stk_days is not None, is_anlage_2=mtk, stk_interval_months=stk_months,
            mtk_interval_months=24 if mtk else None, next_stk_date=next_stk,
            next_mtk_date=next_stk if mtk else None, next_dguv_date=today + timedelta(days=dguv_days),
            current_status=status, last_routine_check=now - timedelta(hours=checked_hours),
            status_note="STK überfällig – Termin mit dem Medizintechnik-Service ist vereinbart"
            if status == MedicalDevice.Status.MAINTENANCE else "",
        ))
    MedicalDevice.objects.bulk_create(devices)
    if any(device.pk is None for device in devices):
        devices = list(MedicalDevice.objects.filter(station=station, slug__startswith=PREFIX).order_by("pk"))
    logs, trainings = [], []
    for device, spec in zip(devices, devices_spec):
        trained, checked_hours = spec[-1], spec[-2]
        if device.next_stk_date:
            logs.append(MaintenanceLog(
                device=device, station=station, kind=MaintenanceLog.Kind.STK, passed=True, created_by=admin,
                performed_at=_months_before(device.next_stk_date, device.stk_interval_months),
                performed_by=service, next_due_date=device.next_stk_date,
            ))
        if device.next_mtk_date:
            logs.append(MaintenanceLog(
                device=device, station=station, kind=MaintenanceLog.Kind.MTK, passed=True, created_by=admin,
                performed_at=_months_before(device.next_mtk_date, 24), performed_by=service,
                next_due_date=device.next_mtk_date,
            ))
        logs.append(MaintenanceLog(
            device=device, station=station, kind=MaintenanceLog.Kind.DGUV, passed=True, created_by=admin,
            performed_at=_months_before(device.next_dguv_date, 12), performed_by="Elektrofachkraft Haustechnik",
            next_due_date=device.next_dguv_date,
        ))
        for index, person in enumerate(dict.fromkeys(trained)):
            trainings.append(DeviceTrainingRecord(
                station=station, device=device, trainee=person, instructor="Nora Yilmaz (Gerätebeauftragte)",
                trained_at=today - timedelta(days=60 + 45 * index),
            ))
        insert_at(DeviceRoutineCheck(station=station, device=device, performed_by=jonas if checked_hours > 12 else lea,
                                     notes="Selbsttest ohne Befund"), device.last_routine_check)
    MaintenanceLog.objects.bulk_create(logs)
    DeviceTrainingRecord.objects.bulk_create(trainings)

    # --- Fuhrpark ----------------------------------------------------------
    disinfectant = DisinfectantMaster.objects.create(
        station=station, name=label("Flächendesinfektion Wischtücher"), default_exposure_minutes=15,
    )
    vehicles_spec = [
        ("demo-rtw-831", "RTW 1/83-1", "MU-RD 831", Vehicle.VehicleType.RTW, Vehicle.TacticalStatus.STATUS_2, "",
         84213, 22, 64, 190, 140, 25, 2021),
        ("demo-rtw-832", "RTW 1/83-2", "MU-RD 832", Vehicle.VehicleType.RTW, Vehicle.TacticalStatus.STATUS_1, "",
         132904, 81, 70, 200, 260, 120, 2019),
        ("demo-rtw-833", "RTW 1/83-3", "MU-RD 833", Vehicle.VehicleType.RTW, Vehicle.TacticalStatus.STATUS_6,
         "Blaulicht hinten links ohne Funktion – Werkstatttermin steht im Kalender", 201480, 64, 55, 180, 75, 60, 2016),
        ("demo-nef-821", "NEF 1/82-1", "MU-RD 821", Vehicle.VehicleType.NEF, Vehicle.TacticalStatus.STATUS_2, "",
         61022, 70, 80, 200, 9, 150, 2022),
        ("demo-ktw-851", "KTW 1/85-1", "MU-RD 851", Vehicle.VehicleType.KTW, Vehicle.TacticalStatus.STATUS_1, "",
         158430, 55, 48, 200, 190, 45, 2018),
    ]
    vehicles = [
        Vehicle(
            station=station, slug=slug, call_sign=call_sign, license_plate=plate, vehicle_type=kind,
            tactical_status=status, status_note=note, current_mileage=km, fuel_level_percent=fuel,
            adblue_level_percent=adblue, o2_pressure_bar=o2, next_hu_date=today + timedelta(days=hu),
            next_uvv_date=today + timedelta(days=uvv), year_of_manufacture=year,
            chassis_manufacturer="Mercedes-Benz Sprinter" if kind != Vehicle.VehicleType.NEF else "VW Tiguan",
            body_manufacturer="Fahrtec Systeme" if kind != Vehicle.VehicleType.NEF else "Ausbau Rettungstechnik",
        )
        for slug, call_sign, plate, kind, status, note, km, fuel, adblue, o2, hu, uvv, year in vehicles_spec
    ]
    Vehicle.objects.bulk_create(vehicles)
    if any(vehicle.pk is None for vehicle in vehicles):
        vehicles = list(Vehicle.objects.filter(station=station, slug__startswith=PREFIX).order_by("pk"))
    crews = (member, jonas, lea, lead, nora)
    for vehicle, crew_member in zip(vehicles, crews):
        insert_at(VehicleHandover(
            station=station, vehicle=vehicle, crew_member=crew_member, mileage=vehicle.current_mileage,
            fuel_percent=vehicle.fuel_level_percent, adblue_percent=vehicle.adblue_level_percent,
            o2_pressure_bar=vehicle.o2_pressure_bar, notes="Übernahme ohne Befund",
        ), shift_start + timedelta(minutes=10))
    # RTW 83-2 kommt gerade aus der Wischdesinfektion: Die Einwirkzeit läuft noch.
    DisinfectionProtocol.objects.create(
        station=station, vehicle=vehicles[1], performed_by=jonas, disinfectant=disinfectant,
        started_at=now - timedelta(minutes=3), exposure_minutes=15, notes="Routinedesinfektion Patientenraum",
    )
    vehicles[1].tactical_status = Vehicle.TacticalStatus.DISINFECTION

    # --- Geräte & Fahrzeuge, Schlüssel und Poolgeräte ------------------------
    assets = [
        StationAsset(station=station, asset_id=device.slug, label=device.name, kind=StationAsset.Kind.DEVICE,
                     status=DEVICE_TO_ASSET[device.current_status], note=device.status_note[:300], updated_by=admin)
        for device in devices
    ] + [
        StationAsset(station=station, asset_id=vehicle.slug, label=f"{vehicle.call_sign} ({vehicle.license_plate})",
                     kind=StationAsset.Kind.VEHICLE, status=VEHICLE_TO_ASSET.get(
                         vehicle.tactical_status, StationAsset.Status.READY),
                     note=vehicle.status_note[:300], updated_by=lead)
        for vehicle in vehicles
    ]
    StationAsset.objects.bulk_create(assets)
    radio_out = now - timedelta(hours=5)
    InventoryItem.objects.bulk_create([
        InventoryItem(station=station, item_id="demo-schluessel-rtw-831", label="Ersatzschlüssel RTW 83-1",
                      kind=InventoryItem.Kind.KEY, updated_by=admin),
        InventoryItem(station=station, item_id="demo-schluessel-medikamentenraum", label="Schlüssel Medikamentenraum",
                      kind=InventoryItem.Kind.KEY, updated_by=admin),
        InventoryItem(station=station, item_id="demo-hrt-1", label="Handfunkgerät HRT 1",
                      kind=InventoryItem.Kind.DEVICE, holder=lead, checked_out_at=radio_out, updated_by=lead),
        InventoryItem(station=station, item_id="demo-hrt-2", label="Handfunkgerät HRT 2",
                      kind=InventoryItem.Kind.DEVICE, updated_by=admin),
    ])
    radio = InventoryItem.objects.get(station=station, item_id="demo-hrt-1")
    insert_at(InventoryEvent(item=radio, station=station, action=InventoryEvent.Action.CHECKOUT, actor=lead,
                             holder=lead), radio_out)

    # --- Lager: Bestand, Chargen mit Haltbarkeit, Buchungsjournal ------------
    locations = StorageLocation.objects.bulk_create([
        StorageLocation(station=station, slug="demo-zentrallager", name="Zentrallager",
                        kind=StorageLocation.Kind.CENTRAL),
        StorageLocation(station=station, slug="demo-kuehlschrank", name="Medikamentenkühlschrank",
                        kind=StorageLocation.Kind.FRIDGE, is_cold_storage=True),
    ])
    if any(location.pk is None for location in locations):
        locations = list(StorageLocation.objects.filter(station=station, slug__startswith=PREFIX).order_by("pk"))
    central, fridge = locations
    C, U = MedicalItem.Category, MedicalItem.Unit
    # slug, Name, Kategorie, Einheit, Lagerort, Mindest-/Sollbestand, [(Charge, Menge, haltbar Tage, Rückruf)]
    items_spec = [
        ("demo-vollelektrolyt-500", "Vollelektrolytlösung 500 ml", C.INFUSION, U.BOTTLE, central, 12, 40,
         [("L24B117", 30, 420, "")]),
        ("demo-nacl-100", "Natriumchlorid 0,9 % 100 ml", C.INFUSION, U.BOTTLE, central, 10, 30,
         [("N5C221", 18, 260, "")]),
        ("demo-glukose-40", "Glukose 40 % 10 ml", C.MEDICATION, U.AMPOULE, central, 10, 20,
         [("G40-2311", 12, 380, ""), ("G40-2307", 5, 200, "Rückruf des Herstellers – Charge gesperrt")]),
        ("demo-larynxmaske-2", "Larynxmaske Größe 2", C.AIRWAY, U.PIECE, central, 2, 4,
         [("LM2-2311", 1, 540, "")]),
        ("demo-hme-filter", "Beatmungsfilter (HME)", C.AIRWAY, U.PIECE, central, 10, 40,
         [("F2406-77", 25, 900, "")]),
        ("demo-handschuhe-m", "Untersuchungshandschuhe Nitril M", C.HYGIENE, U.PACK, central, 10, 30,
         [("HN-2408-M", 4, 700, "")]),
        ("demo-wundauflage-10", "Wundauflage steril 10 × 10 cm", C.BANDAGE, U.PACK, central, 10, 30,
         [("W10-2405", 22, 40, "")]),
        ("demo-rettungsdecke", "Rettungsdecke gold/silber", C.IMMOBILIZATION, U.PIECE, central, 10, 30,
         [("RD-2201", 30, 1500, "")]),
        ("demo-suxamethonium", "Suxamethonium 100 mg", C.MEDICATION, U.AMPOULE, fridge, 4, 6,
         [("SX-24-118", 6, 120, "")]),
    ]
    items = MedicalItem.objects.bulk_create([
        MedicalItem(station=station, slug=slug, name=name, category=category, unit=unit, min_stock=minimum,
                    target_stock=target, requires_cooling=location.is_cold_storage)
        for slug, name, category, unit, location, minimum, target, _batches in items_spec
    ])
    if any(item.pk is None for item in items):
        items = list(MedicalItem.objects.filter(station=station, slug__startswith=PREFIX).order_by("pk"))
    batches, stock = [], []
    for item, (*_spec, location, _min, _target, batch_specs) in zip(items, items_spec):
        for number, quantity, days, recall in batch_specs:
            expires = today + timedelta(days=days)
            batch = ItemBatch(item=item, station=station, batch_number=number, manufacturer_exp_date=expires,
                              calculated_exp_date=expires, is_recalled=bool(recall), recall_reason=recall)
            batches.append(batch)
            stock.append((item, batch, location, quantity))
    ItemBatch.objects.bulk_create(batches)
    if any(batch.pk is None for batch in batches):
        by_number = {(b.item_id, b.batch_number): b for b in ItemBatch.objects.filter(station=station)}
        stock = [(item, by_number[(item.pk, batch.batch_number)], location, quantity)
                 for item, batch, location, quantity in stock]
    StockItem.objects.bulk_create([
        StockItem(station=station, item=item, batch=batch, location=location, quantity=quantity)
        for item, batch, location, quantity in stock
    ])
    for index, (item, batch, location, quantity) in enumerate(stock):
        received = now - timedelta(days=4 + 3 * index, hours=index)
        insert_at(StockMovement(
            station=station, item=item, batch=batch, target_location=location, quantity=quantity,
            kind=StockMovement.Kind.INBOUND, actor=lead if index % 2 else nora, note=label("Wareneingang"),
        ), received)
        if batch.is_recalled:
            insert_at(StockMovement(
                station=station, item=item, batch=batch, source_location=location, quantity=quantity,
                kind=StockMovement.Kind.RECALL_QUARANTINE, actor=nora, note=batch.recall_reason,
            ), now - timedelta(days=1, hours=2))

    # --- Organisation ------------------------------------------------------
    sop = SOPDocument.objects.create(
        station=station, slug="demo-sop-fahrzeugdesinfektion", title=label("Fahrzeugdesinfektion nach Transport"),
        doc_number="DA-HYG-04", category=SOPDocument.Category.HYGIENE, created_by=admin,
        valid_from=today - timedelta(days=30), review_due_date=today + timedelta(days=300),
    )
    revision = SOPRevision.objects.create(
        sop=sop, version_label=sop.current_version, approved_by=admin, effective_date=today - timedelta(days=30),
        content_markdown=(
            "1. Schutzausrüstung anlegen (Handschuhe, bei Bedarf Schutzkittel).\n"
            "2. Kontaktflächen im Patientenraum mit freigegebenem Mittel wischen.\n"
            "3. Einwirkzeit im Fuhrpark starten – das Fahrzeug ist so lange gesperrt.\n"
            "4. Nach Ablauf prüft die Besatzung das Fahrzeug und meldet es einsatzbereit."
        ),
        change_summary="Erstfassung",
    )
    SOPReceipt.objects.bulk_create([
        SOPReceipt(station=station, sop=sop, revision=revision, user=person,
                   acknowledged_at=now - timedelta(days=20 - 3 * index))
        for index, person in enumerate(dict.fromkeys((lead, jonas, nora)))
    ])
    contacts = [
        ("Integrierte Leitstelle (Verwaltung)", StationContact.Category.DISPATCH, "030 23125-100", True),
        ("Kfz-Werkstatt Rettungsdienst", StationContact.Category.SUPPLIER, "030 23125-410", True),
        ("Medizintechnik-Service Musterstadt", StationContact.Category.SUPPLIER, "030 23125-420", True),
        ("Hygienebeauftragte", StationContact.Category.MANAGEMENT, "030 23125-430", False),
        ("Haustechnik", StationContact.Category.OTHER, "030 23125-450", False),
        ("Wachleitung", StationContact.Category.MANAGEMENT, "030 23125-401", False),
    ]
    StationContact.objects.bulk_create([
        StationContact(station=station, name=label(name), category=category, phone_primary=phone,
                       is_speed_dial=speed, order_rank=rank)
        for rank, (name, category, phone, speed) in enumerate(contacts, start=1)
    ])
