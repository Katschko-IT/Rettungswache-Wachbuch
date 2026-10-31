"""Papier-Rückfallebene: Daten für die Druckansichten (Roadmap 0.27, Baustein 8).

Alles hier liest nur. Jede Abfrage ist an genau eine Wache gebunden. Die leeren
Formulare enthalten nur Konfiguration (Fahrzeuge, Geräte, Mittel, Checklisten),
nie frühere Ergebnisse, Namen oder Freitexte aus Nachweisen. Die Fristenliste
nennt keine Personen. Das Telefonbuch zeigt die Kontakte so, wie sie in der App
stehen (auch Ansprechpersonen und Rufnummern).

Welche Objekte „aktiv“ sind, steht nur in den ``active_*``-Funktionen. Nicht
gedruckt werden Fahrzeuge und Medizingeräte, die außer Betrieb genommen sind
(``core/evidence.py``), Desinfektionsmittel, die nicht mehr in Gebrauch sind
(``core/disinfection_plan.py``), Dienstanweisungen, die außer Kraft gesetzt
sind, und inaktive Checklisten. Der Fahrzeugzustand (auch „Außer Dienst“ oder
„Werkstatt“) ändert daran nichts: Das Fahrzeug bleibt im Bestand und bekommt
seine Blätter. Stufen des Desinfektionsplans stehen auf keinem Blatt.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import groupby

from django.db.models import Prefetch, Q
from django.utils.translation import gettext as _

# Leere Zeilen je Formular: Je Blatt passt das auf eine A4-Seite (hochkant).
HANDOVER_ROWS = 12
DISINFECTION_ROWS = 14
PHONEBOOK_BLANK_ROWS = 4

_ISO_WEEK = re.compile(r"^(?P<year>\d{4})-W(?P<week>\d{2})$")


# ---- Woche -------------------------------------------------------------------


def week_start(day: date) -> date:
    """Montag der Kalenderwoche (ISO 8601) von ``day``."""
    return day - timedelta(days=day.weekday())


def parse_week(raw: str | None) -> date | None:
    """``2026-W46`` → Montag dieser Woche; alles andere → ``None``."""
    match = _ISO_WEEK.match((raw or "").strip())
    if not match:
        return None
    year, week = int(match["year"]), int(match["week"])
    if not 2000 <= year <= 2100:
        return None
    try:
        return date.fromisocalendar(year, week, 1)
    except ValueError:
        return None


def iso_week_param(monday: date) -> str:
    year, week, _weekday = monday.isocalendar()
    return f"{year}-W{week:02d}"


def selected_week(raw: str | None, today: date) -> date:
    """Montag der gewünschten Woche, frühestens die aktuelle Woche.

    Eine vergangene Woche lässt sich nicht rekonstruieren: Nach erledigten
    Prüfungen sind die nächsten Fristen schon weitergerückt. Ungültige oder
    vergangene Wochen ergeben daher die aktuelle Woche.
    """
    current = week_start(today)
    monday = parse_week(raw)
    if monday is None or monday < current:
        return current
    return monday


# ---- Aktive Objekte (eine Stelle für „außer Betrieb“) ------------------------


def active_vehicles(station):
    """Fahrzeuge, die nicht außer Betrieb genommen sind (``evidence.is_vehicle_retired``)."""
    from .fleet_models import Vehicle

    return Vehicle.objects.filter(station=station, is_active=True).order_by("call_sign")


def active_devices(station):
    """Medizingeräte, die nicht außer Betrieb genommen sind (``evidence.is_device_retired``)."""
    from .mpg_models import MedicalDevice

    return MedicalDevice.objects.filter(station=station).exclude(
        current_status=MedicalDevice.Status.DECOMMISSIONED,
    )


def active_disinfectants(station):
    """Mittel in Gebrauch, dieselbe Auswahl wie im Desinfektionsprotokoll."""
    from .disinfection_plan import active_disinfectants as in_use

    return in_use(station)


def active_checklists(station):
    from .models import Checklist

    return (
        Checklist.objects.filter(station=station, is_active=True)
        .select_related("schedule")
        .prefetch_related("items")
        .order_by("title")
    )


def active_sops(station):
    from .orga_models import SOPDocument

    return SOPDocument.objects.filter(station=station, status=SOPDocument.Status.ACTIVE)


# ---- Formulare ----------------------------------------------------------------


def device_groups(station) -> list[dict]:
    """Geräte je Standort (Freitext am Gerät), für die Funktionskontrolle."""
    devices = sorted(
        active_devices(station),
        key=lambda device: ((device.location or "").strip().casefold(), device.name.casefold()),
    )
    groups = []
    for _key, items in groupby(devices, key=lambda device: (device.location or "").strip().casefold()):
        items = list(items)
        groups.append({"location": (items[0].location or "").strip() or _("Ohne Standort"), "devices": items})
    return groups


def phonebook(station) -> dict:
    from .orga_models import StationContact

    contacts = list(StationContact.objects.filter(station=station).order_by("order_rank", "name"))
    speed = [contact for contact in contacts if contact.is_speed_dial]
    groups = []
    for value, label in StationContact.Category.choices:
        rows = [contact for contact in contacts if not contact.is_speed_dial and contact.category == value]
        if rows:
            groups.append({"label": label, "contacts": rows})
    return {"speed_dial": speed, "groups": groups, "count": len(contacts)}


# ---- Fristenliste ---------------------------------------------------------------


@dataclass(frozen=True)
class Deadline:
    due: date
    area: str
    what: str
    subject: str
    detail: str = ""


def collect_deadlines(station, until: date) -> list[Deadline]:
    """Alle offenen Fristen bis einschließlich ``until`` (auch überfällige).

    Eine Abfrage je Modul, unabhängig von der Zahl der Einträge. Keine Namen,
    keine Freitexte aus Nachweisen.
    """
    rows: list[Deadline] = []

    if station.fleet_enabled:
        vehicle_fields = (
            ("next_hu_date", _("HU (Hauptuntersuchung)")),
            ("next_sp_date", _("SP (Sicherheitsprüfung)")),
            ("next_uvv_date", _("UVV-Prüfung")),
            ("next_stretcher_service_date", _("Wartung Tragentisch")),
        )
        query = Q()
        for field, _label in vehicle_fields:
            query |= Q(**{f"{field}__lte": until})
        for vehicle in active_vehicles(station).filter(query):
            for field, label in vehicle_fields:
                due = getattr(vehicle, field)
                if due and due <= until:
                    rows.append(Deadline(due, _("Fahrzeug"), label, vehicle.call_sign, vehicle.license_plate))

    if station.mpg_enabled:
        devices = active_devices(station).filter(
            Q(is_anlage_1=True, next_stk_date__lte=until)
            | Q(is_anlage_2=True, next_mtk_date__lte=until)
            | Q(next_dguv_date__lte=until)
        )
        for device in devices:
            detail = " · ".join(part for part in (device.location, device.inventory_number) if part)
            checks = (
                (device.is_anlage_1, device.next_stk_date, _("STK (sicherheitstechnische Kontrolle)")),
                (device.is_anlage_2, device.next_mtk_date, _("MTK (messtechnische Kontrolle)")),
                (True, device.next_dguv_date, _("DGUV V3 (elektrische Prüfung)")),
            )
            for applies, due, label in checks:
                if applies and due and due <= until:
                    rows.append(Deadline(due, _("Medizingerät"), label, device.name, detail))

    if station.orga_enabled:
        for sop in active_sops(station).filter(review_due_date__lte=until):
            rows.append(Deadline(
                sop.review_due_date, _("Dienstanweisung"), _("Überprüfung"), sop.title, sop.doc_number,
            ))

    if station.warehouse_enabled:
        from .warehouse_models import ItemBatch, StockItem

        batches = (
            ItemBatch.objects.filter(station=station, is_recalled=False, stock_items__quantity__gt=0)
            .filter(
                Q(calculated_exp_date__lte=until)
                | Q(calculated_exp_date__isnull=True, manufacturer_exp_date__lte=until)
            )
            .select_related("item")
            .prefetch_related(Prefetch(
                "stock_items",
                queryset=(
                    StockItem.objects.filter(station=station, quantity__gt=0)
                    .select_related("location__parent")
                    .order_by("location__name")
                ),
                to_attr="in_stock",
            ))
            .distinct()
        )
        for batch in batches:
            # str(location) nennt auch den übergeordneten Lagerort („RTW 1 → Schrank 2“).
            places = ", ".join(dict.fromkeys(str(stock.location) for stock in batch.in_stock))
            detail = _("Charge %(lot)s · %(places)s") % {"lot": batch.batch_number, "places": places}
            rows.append(Deadline(batch.effective_date, _("Material"), _("Verfall"), batch.item.name, detail))

    rows.sort(key=lambda row: (row.due, str(row.area), row.subject.casefold()))
    return rows


def week_deadlines(station, monday: date) -> dict:
    sunday = monday + timedelta(days=6)
    rows = collect_deadlines(station, sunday)
    return {
        "week_start": monday,
        "week_end": sunday,
        "week_number": monday.isocalendar()[1],
        "earlier": [row for row in rows if row.due < monday],
        "this_week": [row for row in rows if row.due >= monday],
    }
