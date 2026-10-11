"""Public holidays and merged calendar agenda helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.utils import timezone


@dataclass(frozen=True)
class Holiday:
    day: date
    title: str

    @property
    def starts_at(self):
        return timezone.make_aware(datetime.combine(self.day, time.min))

    @property
    def ends_at(self):
        next_day = self.day + timedelta(days=1)
        return timezone.make_aware(datetime.combine(next_day, time.min))


@dataclass(frozen=True)
class AgendaEntry:
    starts_at: datetime
    ends_at: datetime
    title: str
    kind: str
    description: str = ""
    source_pk: int | None = None
    all_day: bool = False


def _easter_sunday(year):
    """Anonymous Gregorian algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    el = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * el) // 451
    month = (h + el - 7 * m + 114) // 31
    day = ((h + el - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def nrw_holidays_for_year(year):
    """Gesetzliche Feiertage in Nordrhein-Westfalen."""
    easter = _easter_sunday(year)
    return [
        Holiday(date(year, 1, 1), "Neujahr"),
        Holiday(easter - timedelta(days=2), "Karfreitag"),
        Holiday(easter + timedelta(days=1), "Ostermontag"),
        Holiday(date(year, 5, 1), "Tag der Arbeit"),
        Holiday(easter + timedelta(days=39), "Christi Himmelfahrt"),
        Holiday(easter + timedelta(days=50), "Pfingstmontag"),
        Holiday(easter + timedelta(days=60), "Fronleichnam"),
        Holiday(date(year, 10, 3), "Tag der Deutschen Einheit"),
        Holiday(date(year, 11, 1), "Allerheiligen"),
        Holiday(date(year, 12, 25), "1. Weihnachtstag"),
        Holiday(date(year, 12, 26), "2. Weihnachtstag"),
    ]


def _as_date(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if timezone.is_aware(value):
        return timezone.localtime(value).date()
    return value.date()


def holidays_between(start, end, region="nrw"):
    start = _as_date(start)
    end = _as_date(end)
    if start > end:
        return []
    items = []
    for year in range(start.year, end.year + 1):
        for holiday in nrw_holidays_for_year(year):
            if start <= holiday.day <= end:
                items.append(holiday)
    return items


def upcoming_holidays(days_ahead=366, region="nrw"):
    today = timezone.localdate()
    return holidays_between(today, today + timedelta(days=days_ahead), region=region)


def is_upcoming_agenda_item(item, *, now=None, today=None):
    """True if an agenda item should still appear as upcoming (all-day by date)."""
    now = now or timezone.now()
    today = today or timezone.localdate()
    if item.all_day:
        return timezone.localtime(item.starts_at).date() >= today
    return item.starts_at >= now


def station_agenda(station, events, *, past_days=1, future_days=400):
    """Merge station events, NRW holidays and waste collections into one agenda."""
    now = timezone.now()
    window_start = now - timedelta(days=past_days)
    window_end = now + timedelta(days=future_days)
    items = []
    for event in events:
        if event.ends_at < window_start:
            continue
        items.append(AgendaEntry(
            starts_at=event.starts_at,
            ends_at=event.ends_at,
            title=event.title,
            kind="event",
            description=event.description or "",
            source_pk=event.pk,
            all_day=False,
        ))
    if getattr(station, "holidays_enabled", True):
        for holiday in holidays_between(window_start, window_end):
            items.append(AgendaEntry(
                starts_at=holiday.starts_at,
                ends_at=holiday.ends_at,
                title=holiday.title,
                kind="holiday",
                description="Gesetzlicher Feiertag in Nordrhein-Westfalen",
                all_day=True,
            ))
    if getattr(station, "waste_calendar_enabled", False) and station.waste_collections.exists():
        for waste in station.waste_collections.all():
            ends_at = waste.ends_at or (waste.starts_at + timedelta(hours=1))
            if ends_at < window_start:
                continue
            items.append(AgendaEntry(
                starts_at=waste.starts_at,
                ends_at=ends_at,
                title=waste.title,
                kind="waste",
                description="Müllabfuhr (externe ICS-Quelle)",
                source_pk=waste.pk,
                all_day=False,
            ))
    items.sort(key=lambda item: (item.starts_at, item.title))
    return items
