"""Datenaufbereitung für den Wachen-Display-Modus.

Grundregel: Auf einem Wandmonitor im Flur darf nur stehen, was auch ein
Besucher sehen dürfte. Deshalb enthält dieser Baustein ausschließlich
aggregierte Angaben und keine Freitexte aus Übergaben, keine Namen von
Mitarbeitenden außer einem ausdrücklich freigegebenen Geburtstagsvornamen und
keine Beträge oder Kontaktdaten.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from django.utils import timezone

from .models import BirthdayPreference, CalendarEvent, HandoverEntry, WasteCollection
from .task_board import day_board


def _local_today(station):
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(station.timezone_name or "Europe/Berlin")
    except Exception:  # noqa: BLE001 - ungültige Zeitzone darf das Display nicht stoppen
        tz = timezone.get_current_timezone()
    return timezone.localtime(timezone.now(), tz).date(), tz


def _day_bounds(day, tz):
    start = datetime.combine(day, datetime.min.time(), tzinfo=tz)
    return start, start + timedelta(days=1)


def display_payload(station) -> dict:
    """Aggregierte Anzeige-Daten für genau eine Wache."""
    day, tz = _local_today(station)
    start, end = _day_bounds(day, tz)

    events = []
    if station.calendar_enabled:
        for event in CalendarEvent.objects.filter(
            station=station, starts_at__gte=start, starts_at__lt=end
        ).order_by("starts_at")[:6]:
            events.append({
                "time": timezone.localtime(event.starts_at, tz).strftime("%H:%M"),
                "title": event.title[:80],
            })

    waste = []
    if station.waste_calendar_enabled:
        for item in WasteCollection.objects.filter(
            station=station, starts_at__gte=start, starts_at__lt=start + timedelta(days=3)
        ).order_by("starts_at")[:3]:
            waste.append({
                "day": timezone.localtime(item.starts_at, tz).strftime("%d.%m."),
                "title": item.title[:60],
            })

    tasks = {"total": 0, "done": 0, "open": 0}
    if station.tasks_enabled:
        board = day_board(station, day)
        tasks = {
            "total": board["total"],
            "done": board["done_count"],
            "open": board["open_count"],
        }

    urgent = (
        HandoverEntry.objects.filter(
            station=station, priority=HandoverEntry.Priority.URGENT
        )
        .exclude(status=HandoverEntry.Status.DONE)
        .count()
    )

    birthdays = []
    if station.birthdays_enabled:
        for preference in BirthdayPreference.objects.filter(
            station=station,
            is_visible=True,
            consented_at__isnull=False,
            withdrawn_at__isnull=True,
            day=day.day,
            month=day.month,
        ).select_related("user")[:5]:
            first = (preference.user.first_name or "").strip()
            last = (preference.user.last_name or "").strip()
            if not first:
                continue
            # Nur Vorname plus Anfangsbuchstabe, kein Geburtsjahr.
            birthdays.append({"name": f"{first} {last[:1]}." if last else first})

    weather = None
    if getattr(station, "weather_enabled", False):
        try:
            from .weather import forecast_for_station, weather_code_label

            forecast = forecast_for_station(station)
            today = forecast.days[0]
            weather = {
                "max": round(float(today["temperature_max"])),
                "min": round(float(today["temperature_min"])),
                "code": today.get("weather_code"),
                "label": weather_code_label(today.get("weather_code")),
                "precipitation": today.get("precipitation_mm"),
                "stale": bool(forecast.stale),
            }
        except Exception:  # noqa: BLE001 - Wetter ist optional
            weather = None

    # Verkehr ist optional und darf die Anzeige nie blockieren: Schlägt eine
    # Quelle fehl, bleibt die Liste leer statt die ganze Anzeige zu kippen.
    traffic = None
    if getattr(station, "traffic_enabled", False):
        try:
            from .traffic import traffic_payload

            traffic = traffic_payload(station)
        except Exception:  # noqa: BLE001 - Verkehr ist optional
            traffic = None

    alerts = None
    if getattr(station, "dwd_alerts_enabled", False):
        try:
            from .alerts import alerts_payload

            alerts = alerts_payload(station)
        except Exception:  # noqa: BLE001 - Warnungen sind optional
            alerts = None

    return {
        "station": station.name,
        "date": day.isoformat(),
        "events": events,
        "waste": waste,
        "tasks": tasks,
        "urgent_handovers": urgent,
        "birthdays": birthdays,
        "weather": weather,
        "traffic": traffic,
        "alerts": alerts,
    }
