"""Schichtband und Bereitschaftszeilen für die Übersicht.

Das Schichtband zeigt den laufenden Tag der Wache als 24-Stunden-Leiste
(docs/DESIGN-SYSTEM.md, „Schichtband“). Es nutzt nur vorhandene Zeitdaten –
Übergaben des Tages, Termine, fällige Checklisten und die Einwirkzeit nach
einer Desinfektion – und legt nichts an.

Schichtgrenzen zeigt es nicht: Die Wache speichert keine Schichtzeiten.

Alle Positionen sind Minuten seit Mitternacht in der Zeitzone der Anwendung
(0 bis 1440); das Template setzt sie als SVG-Attribute.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta

from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

DAY_MINUTES = 24 * 60
# Mindestbreite einer Spanne, damit auch ein kurzer Termin sichtbar bleibt.
MIN_SPAN = 12
MAX_ENTRIES = 200
MAX_LEGEND = 8
MAX_READINESS = 8


def _day_bounds(now):
    local = timezone.localtime(now)
    start = timezone.make_aware(datetime.combine(local.date(), time.min), local.tzinfo)
    return local, start, start + timedelta(days=1)


def _minute(value, start) -> int:
    """Minuten seit Tagesbeginn, auf den Tag begrenzt."""
    minutes = int((value - start).total_seconds() // 60)
    return max(0, min(DAY_MINUTES, minutes))


def _clock(value) -> str:
    return timezone.localtime(value).strftime("%H:%M")


def _span(begin, end, start):
    x = _minute(begin, start)
    width = max(MIN_SPAN, _minute(end, start) - x)
    return {"x": x, "w": min(width, DAY_MINUTES - x)}


def unacknowledged_handovers(station, user) -> int:
    """Aktive Übergaben anderer, die diese Person noch nicht quittiert hat.

    Gleiche Regel wie die Schaltfläche „Gelesen – quittieren“: nie die eigene
    Übergabe und nie am Wachenterminal (Dienstkonto).
    """
    from .models import HandoverEntry
    from .terminal import is_service_user

    if is_service_user(user):
        return 0
    return (
        HandoverEntry.objects.filter(station=station)
        .exclude(status=HandoverEntry.Status.DONE)
        .exclude(author=user)
        .exclude(acknowledgements__user=user)
        .count()
    )


def vehicle_readiness(vehicles) -> list[dict]:
    """Eine Zeile je Fahrzeug: Zustand als Stempel, Sperrzeit als Hinweis.

    Nennt nie Art oder Stufe einer Desinfektion, nur den neutralen Zustand
    und die Uhrzeit (Glossar: „Desinfektion“).
    """
    from .fleet_models import Vehicle

    rows = []
    for vehicle in vehicles:
        note = ""
        if vehicle.is_disinfection_locked:
            rank, tone = 0, "locked"
            label = Vehicle.TacticalStatus.DISINFECTION.label
            note = _("Einwirkzeit läuft bis %(time)s Uhr") % {"time": _clock(vehicle.disinfection_locked_until)}
        elif vehicle.awaiting_crew_release:
            rank, tone = 0, "locked"
            label = Vehicle.TacticalStatus.DISINFECTION.label
            note = _("Einwirkzeit abgelaufen – Freigabe durch die Besatzung")
        elif vehicle.tactical_status == Vehicle.TacticalStatus.READY:
            rank, tone, label = 2, "success", vehicle.get_tactical_status_display()
        elif vehicle.tactical_status == Vehicle.TacticalStatus.LIMITED:
            rank, tone, label = 1, "warning", vehicle.get_tactical_status_display()
        else:
            rank, tone, label = 0, "locked", vehicle.get_tactical_status_display()
        rows.append({
            "rank": rank,
            "name": vehicle.call_sign,
            "href": reverse("fleet_vehicle_detail", args=[vehicle.slug]),
            "tone": tone,
            "label": label,
            "note": note,
        })
    rows.sort(key=lambda row: (row["rank"], row["name"]))
    return rows[:MAX_READINESS]


def dashboard_band(station, now=None, vehicles=None) -> dict:
    """Marken und Legende des Schichtbands für den laufenden Tag."""
    from .models import CalendarEvent, HandoverEntry

    now = now or timezone.now()
    local, start, end = _day_bounds(now)
    band = {
        "now_x": _minute(now, start),
        "now_label": local.strftime("%H:%M"),
        "now_iso": local.isoformat(timespec="minutes"),
        "entries": [],
        "events": [],
        "due": [],
        "locks": [],
    }
    legend = []

    # Geschriebene Einträge: Übergaben des Tages. Nachträge vom Papierbogen
    # zählen nicht – sie wurden nicht heute geschrieben.
    entries = HandoverEntry.objects.filter(
        station=station, created_at__gte=start, created_at__lt=end, is_paper_backfill=False,
    ).order_by("created_at").values_list("created_at", "priority")[:MAX_ENTRIES]
    for created_at, priority in entries:
        band["entries"].append({
            "x": _minute(created_at, start),
            "urgent": priority == HandoverEntry.Priority.URGENT,
        })

    if station.calendar_enabled:
        events = CalendarEvent.objects.filter(
            station=station, starts_at__lt=end, ends_at__gte=start,
        ).order_by("starts_at")[:12]
        for event in events:
            # Ganztägige Termine haben keine Stelle auf der Leiste.
            if event.starts_at <= start and event.ends_at >= end - timedelta(minutes=1):
                continue
            band["events"].append(_span(max(event.starts_at, start), min(event.ends_at, end), start))
            if event.starts_at >= start:
                legend.append({
                    "minute": _minute(event.starts_at, start),
                    "time": _clock(event.starts_at),
                    "iso": timezone.localtime(event.starts_at).isoformat(timespec="minutes"),
                    "tone": "neutral",
                    "label": _("Termin"),
                    "text": event.title,
                    "note": "",
                    "href": reverse("calendar"),
                })

    if station.checklists_enabled:
        from .wachalltag_models import ChecklistSchedule

        schedules = ChecklistSchedule.objects.filter(
            station=station, checklist__is_active=True, due_next__gte=start, due_next__lt=end,
        ).select_related("checklist").order_by("due_next")[:12]
        for schedule in schedules:
            minute = _minute(schedule.due_next, start)
            band["due"].append({"x": minute})
            legend.append({
                "minute": minute,
                "time": _clock(schedule.due_next),
                "iso": timezone.localtime(schedule.due_next).isoformat(timespec="minutes"),
                "tone": "warning",
                "label": _("Checkliste"),
                "text": schedule.checklist.title,
                "note": _("überfällig") if schedule.due_next < now else "",
                "href": reverse("checklists"),
            })

    if station.fleet_enabled:
        from .fleet_models import Vehicle

        if vehicles is None:
            vehicles = list(Vehicle.objects.filter(station=station, is_active=True))
        for vehicle in vehicles:
            until = vehicle.disinfection_locked_until
            if not until or until <= start:
                continue
            begin = vehicle.last_disinfection or now
            if begin >= end:
                continue
            band["locks"].append(_span(max(begin, start), min(until, end), start))
            if until > now:
                legend.append({
                    "minute": _minute(min(until, end), start),
                    "time": _clock(until),
                    "iso": timezone.localtime(until).isoformat(timespec="minutes"),
                    "tone": "locked",
                    "label": Vehicle.TacticalStatus.DISINFECTION.label,
                    "text": vehicle.call_sign,
                    "note": _("Einwirkzeit läuft bis %(time)s Uhr") % {"time": _clock(until)},
                    "href": reverse("fleet_vehicle_detail", args=[vehicle.slug]),
                })

    legend.sort(key=lambda item: item["minute"])
    # Was noch kommt, zuerst; Vergangenes fällt bei Platzmangel weg.
    upcoming = [item for item in legend if item["minute"] >= band["now_x"]]
    past = [item for item in legend if item["minute"] < band["now_x"]]
    band["legend"] = (upcoming + past[::-1])[:MAX_LEGEND]
    band["legend"].sort(key=lambda item: item["minute"])
    return band
