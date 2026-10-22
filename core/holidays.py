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


GERMAN_STATES = {
    "BW": "Baden-Württemberg",
    "BY": "Bayern",
    "BE": "Berlin",
    "BB": "Brandenburg",
    "HB": "Bremen",
    "HH": "Hamburg",
    "HE": "Hessen",
    "MV": "Mecklenburg-Vorpommern",
    "NI": "Niedersachsen",
    "NW": "Nordrhein-Westfalen",
    "RP": "Rheinland-Pfalz",
    "SL": "Saarland",
    "SN": "Sachsen",
    "ST": "Sachsen-Anhalt",
    "SH": "Schleswig-Holstein",
    "TH": "Thüringen",
}

STATE_ALIASES = {
    "NRW": "NW",
    "DE-BW": "BW",
    "DE-BY": "BY",
    "DE-BE": "BE",
    "DE-BB": "BB",
    "DE-HB": "HB",
    "DE-HH": "HH",
    "DE-HE": "HE",
    "DE-MV": "MV",
    "DE-NI": "NI",
    "DE-NW": "NW",
    "DE-RP": "RP",
    "DE-SL": "SL",
    "DE-SN": "SN",
    "DE-ST": "ST",
    "DE-SH": "SH",
    "DE-TH": "TH",
}


def normalize_state(code: str | None) -> str:
    """Normalize a state code into a 2-letter uppercase key from GERMAN_STATES."""
    if not code:
        return "NW"
    code = str(code).strip().upper()
    if code in GERMAN_STATES:
        return code
    if code in STATE_ALIASES:
        return STATE_ALIASES[code]
    return "NW"


def _buss_und_bettag(year: int) -> date:
    """Mittwoch vor dem 23. November (zwischen 16. und 22. November)."""
    d = date(year, 11, 22)
    while d.weekday() != 2:
        d -= timedelta(days=1)
    return d


def holidays_for_year(year: int, state: str = "NW") -> list[Holiday]:
    """Gesetzliche Feiertage für ein deutsches Bundesland in einem Kalenderjahr."""
    norm_state = normalize_state(state)
    easter = _easter_sunday(year)

    # Bundesweite gesetzliche Feiertage (in allen 16 Ländern)
    holidays = [
        Holiday(date(year, 1, 1), "Neujahr"),
        Holiday(easter - timedelta(days=2), "Karfreitag"),
        Holiday(easter + timedelta(days=1), "Ostermontag"),
        Holiday(date(year, 5, 1), "Tag der Arbeit"),
        Holiday(easter + timedelta(days=39), "Christi Himmelfahrt"),
        Holiday(easter + timedelta(days=50), "Pfingstmontag"),
        Holiday(date(year, 10, 3), "Tag der Deutschen Einheit"),
        Holiday(date(year, 12, 25), "1. Weihnachtstag"),
        Holiday(date(year, 12, 26), "2. Weihnachtstag"),
    ]

    # Länderspezifische gesetzliche Feiertage
    if norm_state in {"BW", "BY", "ST"}:
        holidays.append(Holiday(date(year, 1, 6), "Heilige Drei Könige"))

    if norm_state in {"BE", "MV"}:
        holidays.append(Holiday(date(year, 3, 8), "Internationaler Frauentag"))

    if norm_state == "BB":
        holidays.append(Holiday(easter, "Ostersonntag"))
        holidays.append(Holiday(easter + timedelta(days=49), "Pfingstsonntag"))

    if norm_state in {"BW", "BY", "HE", "NW", "RP", "SL"}:
        holidays.append(Holiday(easter + timedelta(days=60), "Fronleichnam"))

    if norm_state in {"BY", "SL"}:
        holidays.append(Holiday(date(year, 8, 15), "Mariä Himmelfahrt"))

    if norm_state == "TH":
        holidays.append(Holiday(date(year, 9, 20), "Weltkindertag"))

    if norm_state in {"BB", "HB", "HH", "MV", "NI", "SN", "ST", "SH", "TH"}:
        holidays.append(Holiday(date(year, 10, 31), "Reformationstag"))

    if norm_state in {"BW", "BY", "NW", "RP", "SL"}:
        holidays.append(Holiday(date(year, 11, 1), "Allerheiligen"))

    if norm_state == "SN":
        holidays.append(Holiday(_buss_und_bettag(year), "Buß- und Bettag"))

    holidays.sort(key=lambda h: h.day)
    return holidays


def nrw_holidays_for_year(year):
    """Gesetzliche Feiertage in Nordrhein-Westfalen (Abwärtskompatibilität)."""
    return holidays_for_year(year, state="NW")


def _as_date(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if timezone.is_aware(value):
        return timezone.localtime(value).date()
    return value.date()


def holidays_between(start, end, region="NW"):
    start = _as_date(start)
    end = _as_date(end)
    if start > end:
        return []
    items = []
    norm_state = normalize_state(region)
    for year in range(start.year, end.year + 1):
        for holiday in holidays_for_year(year, state=norm_state):
            if start <= holiday.day <= end:
                items.append(holiday)
    return items


def upcoming_holidays(days_ahead=366, region="NW"):
    today = timezone.localdate()
    return holidays_between(today, today + timedelta(days=days_ahead), region=region)


def is_upcoming_agenda_item(item, *, now=None, today=None):
    """True if an agenda item should still appear as upcoming (all-day by date)."""
    now = now or timezone.now()
    today = today or timezone.localdate()
    if item.all_day:
        return timezone.localtime(item.starts_at).date() >= today
    return item.starts_at >= now


def _birthday_entries(station, window_start, window_end):
    """Freiwillig sichtbare Geburtstage als jaehrliche Kalendereintraege."""
    from .models import BirthdayPreference

    entries = []
    if not getattr(station, "birthdays_enabled", True):
        return entries
    first_day = timezone.localtime(window_start).date()
    last_day = timezone.localtime(window_end).date()
    preferences = (
        BirthdayPreference.objects.filter(
            station=station,
            is_visible=True,
            day__isnull=False,
            month__isnull=False,
        )
        .select_related("user")
        .order_by("month", "day")
    )
    for preference in preferences:
        for year in range(first_day.year, last_day.year + 1):
            try:
                day = date(year, preference.month, preference.day)
            except ValueError:
                # 29. Februar in einem Nicht-Schaltjahr.
                day = date(year, 2, 28)
            if not (first_day <= day <= last_day):
                continue
            name = preference.user.first_name or preference.user.username
            starts_at = timezone.make_aware(datetime.combine(day, time.min))
            entries.append(AgendaEntry(
                starts_at=starts_at,
                ends_at=starts_at + timedelta(days=1),
                title=f"Geburtstag: {name}",
                kind="birthday",
                description="",
                all_day=True,
            ))
    return entries


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
        state_code = getattr(station, "holiday_state", "NW") or "NW"
        state_key = normalize_state(state_code)
        state_name = GERMAN_STATES.get(state_key, "Nordrhein-Westfalen")
        for holiday in holidays_between(window_start, window_end, region=state_key):
            items.append(AgendaEntry(
                starts_at=holiday.starts_at,
                ends_at=holiday.ends_at,
                title=holiday.title,
                kind="holiday",
                description=f"Gesetzlicher Feiertag in {state_name}",
                all_day=True,
            ))
    birthday_items = _birthday_entries(station, window_start, window_end)
    items.extend(birthday_items)
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
                description="Muellabfuhr (externe ICS-Quelle)",
                source_pk=waste.pk,
                all_day=False,
            ))
    items.sort(key=lambda item: (item.starts_at, item.title))
    return items
