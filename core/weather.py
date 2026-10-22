"""Optional Open-Meteo access for the station address.

Design rules (see docs/SETUP-WIZARD-PLAN.md and docs/OFFLINE-BETRIEB.md):

* No network access happens unless the operator explicitly opted in.
* The endpoints are a fixed HTTPS allowlist; the caller can never choose a host.
* Short timeout, size limit, no redirects, circuit breaker.
* Forecast values are either real API values or ``None``. Cached values keep
  their original fetch time and are marked ``stale=True`` when refreshed
  unsuccessfully — never synthesised.
"""

from __future__ import annotations

import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.cache import cache
from django.utils import timezone

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
OSM_GEOCODE_URL = "https://nominatim.openstreetmap.org/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ALLOWED_HOSTS = frozenset({
    "geocoding-api.open-meteo.com",
    "api.open-meteo.com",
    "nominatim.openstreetmap.org",
})
TIMEOUT_SECONDS = 3.0
MAX_RESPONSE_BYTES = 200_000
FORECAST_CACHE_SECONDS = 3600
# A separate, longer-lived copy of real values for outages. It is bounded and
# only served with its original fetch time; it is never presented as a live
# forecast. Twelve hours keeps the five local days meaningful.
FORECAST_STALE_SECONDS = 12 * 3600
CIRCUIT_SECONDS = 120
CIRCUIT_THRESHOLD = 3
DAYS = 5


class WeatherUnavailable(Exception):
    """Raised when no real forecast can be produced or cached."""


@dataclass
class Forecast:
    days: list[dict]
    fetched_at: datetime
    stale: bool
    location_label: str = ""

    @property
    def fetched_at_iso(self) -> str:
        return self.fetched_at.isoformat()

    @property
    def age_minutes(self) -> int:
        return max(0, int((timezone.now() - self.fetched_at).total_seconds() // 60))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        raise WeatherUnavailable("Redirects sind für Wetterdaten nicht erlaubt.")


def _opener():
    return urllib.request.build_opener(_NoRedirect)


def _urlopen(request, timeout):  # indirection for tests
    return _opener().open(request, timeout=timeout)


def _fetch_json(url: str, params: dict) -> dict | list:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in ALLOWED_HOSTS:
        raise WeatherUnavailable("Nicht erlaubter Wetter-Endpunkt.")
    full = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        full,
        headers={"User-Agent": "Wachwerk-Rettungswache/1.0 (https://github.com/Katschko-IT/Rettungswache-Wachbuch)"},
    )
    try:
        with _urlopen(request, TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise WeatherUnavailable(f"HTTP {status}")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except WeatherUnavailable:
        raise
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise WeatherUnavailable("Wetterdienst nicht erreichbar.") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise WeatherUnavailable("Antwort des Wetterdienstes ist zu groß.")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WeatherUnavailable("Ungültige Antwort des Wetterdienstes.") from exc
    if not isinstance(data, (dict, list)):
        raise WeatherUnavailable("Ungültige Antwort des Wetterdienstes.")
    if isinstance(data, dict) and data.get("error"):
        raise WeatherUnavailable("Wetterdienst meldet einen Fehler.")
    return data


def _circuit_open() -> bool:
    return bool(cache.get("weather:circuit:open"))


def _record_failure() -> None:
    key = "weather:circuit:failures"
    failures = int(cache.get(key, 0) or 0) + 1
    cache.set(key, failures, CIRCUIT_SECONDS)
    if failures >= CIRCUIT_THRESHOLD:
        cache.set("weather:circuit:open", True, CIRCUIT_SECONDS)


def _record_success() -> None:
    cache.delete("weather:circuit:failures")
    cache.delete("weather:circuit:open")


def _valid_coordinate(value, low: float, high: float) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and low <= number <= high


def _normalized_timezone(timezone_name: str) -> str:
    """Accept only a real IANA zone; the value goes into query and cache key."""
    name = (timezone_name or "").strip()
    if not name:
        name = "Europe/Berlin"
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise WeatherUnavailable("Ungültige Zeitzone.") from exc
    return name


def _extract_candidates(address: str) -> list[str]:
    """Erzeugt schrittweise vergröberte Suchbegriffe (Straße/Hausnr, PLZ+Ort, Ort)."""
    cleaned = (address or "").strip()
    candidates = [cleaned]

    # PLZ (4-5 Ziffern) und Ort am Ende extrahieren (z. B. "12345 Musterstadt")
    match = re.search(r"(?:,\s*)?(\b\d{4,5}\b)\s+([^,]+)$", cleaned)
    if match:
        plz, city = match.group(1).strip(), match.group(2).strip()
        candidates.append(f"{plz} {city}")
        candidates.append(city)
    else:
        # Falls durch Komma getrennt, den letzten Teil (meist Stadt) separat versuchen
        parts = [p.strip() for p in cleaned.split(",") if p.strip()]
        if len(parts) > 1:
            candidates.append(parts[-1])

    seen = set()
    result = []
    for c in candidates:
        low = c.lower()
        if low not in seen and len(c) >= 2:
            seen.add(low)
            result.append(c)
    return result


def _geocode_osm(query: str) -> dict | None:
    try:
        data = _fetch_json(
            OSM_GEOCODE_URL,
            {"q": query, "format": "json", "limit": 1, "addressdetails": 1},
        )
    except WeatherUnavailable:
        return None
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            lat = first.get("lat")
            lon = first.get("lon")
            if _valid_coordinate(lat, -90, 90) and _valid_coordinate(lon, -180, 180):
                display_name = first.get("display_name") or query
                return {
                    "latitude": round(float(lat), 4),
                    "longitude": round(float(lon), 4),
                    "label": str(display_name)[:120],
                }
    return None


def _geocode_open_meteo(query: str, language: str) -> dict | None:
    data = _fetch_json(
        GEOCODE_URL,
        {"name": query, "count": 1, "language": language, "format": "json"},
    )
    if not isinstance(data, dict):
        raise WeatherUnavailable("Ungültige Antwort des Wetterdienstes.")
    results = data.get("results")
    if results is None:
        return None
    if not isinstance(results, list):
        raise WeatherUnavailable("Ungültige Antwort des Wetterdienstes.")
    if not results:
        return None
    first = results[0]
    if not isinstance(first, dict):
        raise WeatherUnavailable("Ungültige Antwort des Wetterdienstes.")
    latitude, longitude = first.get("latitude"), first.get("longitude")
    if not (_valid_coordinate(latitude, -90, 90) and _valid_coordinate(longitude, -180, 180)):
        raise WeatherUnavailable("Wetterdienst lieferte ungültige Koordinaten.")
    label_parts = [
        str(part)
        for part in (first.get("name"), first.get("admin1"), first.get("country"))
        if isinstance(part, str) and part
    ]
    return {
        "latitude": round(float(latitude), 4),
        "longitude": round(float(longitude), 4),
        "label": ", ".join(label_parts),
    }


def geocode(address: str, *, language: str = "de") -> dict:
    """Resolve a free-text address to coordinates. Requires explicit consent."""
    address = (address or "").strip()
    if len(address) < 5:
        raise WeatherUnavailable("Adresse ist zu kurz für eine Geocodierung.")
    if _circuit_open():
        raise WeatherUnavailable("Wetterdienst ist vorübergehend pausiert.")

    candidates = _extract_candidates(address)

    # 1. OpenStreetMap Nominatim für präzise Straßen- und Hausnummern-Auflösung
    for candidate in candidates:
        loc = _geocode_osm(candidate)
        if loc:
            _record_success()
            return loc

    # 2. Open-Meteo Geocoding als Ausweichdienst für Orte und Regionen
    for candidate in candidates:
        try:
            loc = _geocode_open_meteo(candidate, language)
            if loc:
                _record_success()
                return loc
        except WeatherUnavailable:
            _record_failure()
            raise

    _record_failure()
    raise WeatherUnavailable("Adresse konnte nicht gefunden werden.")


def _cache_key(latitude: float, longitude: float, timezone_name: str) -> str:
    return f"weather:forecast:{round(latitude, 3)}:{round(longitude, 3)}:{timezone_name}"


def _stale_cache_key(latitude: float, longitude: float, timezone_name: str) -> str:
    return f"weather:forecast:stale:{round(latitude, 3)}:{round(longitude, 3)}:{timezone_name}"


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _build_days(daily) -> list[dict]:
    if not isinstance(daily, dict):
        raise WeatherUnavailable("Ungültige Antwort des Wetterdienstes.")
    times = daily.get("time") or []
    maxima = daily.get("temperature_2m_max") or []
    minima = daily.get("temperature_2m_min") or []
    precipitation = daily.get("precipitation_sum") or []
    codes = daily.get("weather_code") or []
    if not all(isinstance(values, list) for values in (times, maxima, minima, precipitation, codes)):
        raise WeatherUnavailable("Ungültige Antwort des Wetterdienstes.")
    if not (len(times) == len(maxima) == len(minima) >= DAYS):
        raise WeatherUnavailable("Unvollständige Tagesvorhersage.")
    days = []
    for index in range(DAYS):
        if not isinstance(times[index], str) or not (
            _is_number(maxima[index]) and _is_number(minima[index])
        ):
            raise WeatherUnavailable("Ungültige Tagesvorhersage.")
        precipitation_value = precipitation[index] if index < len(precipitation) else None
        code_value = codes[index] if index < len(codes) else None
        if precipitation_value is not None and not _is_number(precipitation_value):
            raise WeatherUnavailable("Ungültige Tagesvorhersage.")
        if code_value is not None and not isinstance(code_value, int):
            raise WeatherUnavailable("Ungültige Tagesvorhersage.")
        try:
            datetime.fromisoformat(times[index])
        except ValueError as exc:
            raise WeatherUnavailable("Ungültige Tagesvorhersage.") from exc
        days.append(
            {
                "date": times[index],
                "temperature_max": maxima[index],
                "temperature_min": minima[index],
                "precipitation_mm": precipitation_value,
                "weather_code": code_value,
            }
        )
    return days


def _entry_fetched_at(entry) -> datetime | None:
    if not isinstance(entry, dict):
        return None
    try:
        fetched_at = datetime.fromisoformat(str(entry.get("fetched_at") or ""))
    except ValueError:
        return None
    if timezone.is_naive(fetched_at):
        fetched_at = timezone.make_aware(fetched_at)
    return fetched_at


def _entry_age(entry) -> timedelta | None:
    fetched_at = _entry_fetched_at(entry)
    if fetched_at is None:
        return None
    return max(timedelta(0), timezone.now() - fetched_at)


def _entry_days_valid(entry, timezone_name: str) -> bool:
    """Reject stale entries that no longer describe the next five local days."""
    days = entry.get("days") if isinstance(entry, dict) else None
    if not isinstance(days, list) or len(days) != DAYS:
        return False
    try:
        dates = [datetime.fromisoformat(str(day["date"])).date() for day in days]
    except (KeyError, TypeError, ValueError):
        return False
    if any(later != earlier + timedelta(days=1) for earlier, later in zip(dates, dates[1:])):
        return False
    local_today = datetime.now(ZoneInfo(timezone_name)).date()
    return dates[0] == local_today


def _entry_fresh_usable(entry, timezone_name: str) -> bool:
    age = _entry_age(entry)
    return bool(
        age is not None
        and age < timedelta(seconds=FORECAST_CACHE_SECONDS)
        and isinstance(entry, dict)
        and isinstance(entry.get("days"), list)
        and len(entry["days"]) == DAYS
        and _entry_days_valid(entry, timezone_name)
    )


def _entry_stale_usable(entry, timezone_name: str) -> bool:
    age = _entry_age(entry)
    return bool(
        age is not None
        and age <= timedelta(seconds=FORECAST_STALE_SECONDS)
        and _entry_days_valid(entry, timezone_name)
    )


def _forecast_from_entry(entry, *, stale: bool, timezone_name: str) -> Forecast:
    fetched_at = _entry_fetched_at(entry)
    if fetched_at is None:
        raise WeatherUnavailable("Zwischengespeicherte Wetterdaten sind ungültig.")
    return Forecast(
        days=[dict(day) for day in entry["days"]],
        fetched_at=fetched_at,
        stale=stale,
    )


def fetch_forecast(
    latitude: float, longitude: float, *, timezone_name: str = "Europe/Berlin"
) -> Forecast:
    """Return five real local days; serve a bounded, labelled cache on failure."""
    if not (_valid_coordinate(latitude, -90, 90) and _valid_coordinate(longitude, -180, 180)):
        raise WeatherUnavailable("Ungültige Koordinaten.")
    timezone_name = _normalized_timezone(timezone_name)
    key = _cache_key(float(latitude), float(longitude), timezone_name)
    stale_key = _stale_cache_key(float(latitude), float(longitude), timezone_name)
    fresh = cache.get(key)
    if _circuit_open():
        if fresh and _entry_fresh_usable(fresh, timezone_name):
            return _forecast_from_entry(fresh, stale=False, timezone_name=timezone_name)
        stale = cache.get(stale_key)
        if stale and _entry_stale_usable(stale, timezone_name):
            return _forecast_from_entry(stale, stale=True, timezone_name=timezone_name)
        raise WeatherUnavailable("Wetterdienst ist vorübergehend pausiert.")
    if fresh and _entry_fresh_usable(fresh, timezone_name):
        return _forecast_from_entry(fresh, stale=False, timezone_name=timezone_name)
    try:
        data = _fetch_json(
            FORECAST_URL,
            {
                "latitude": float(latitude),
                "longitude": float(longitude),
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code",
                "forecast_days": DAYS,
                "timezone": timezone_name,
            },
        )
        days = _build_days(data.get("daily"))
        if not _entry_days_valid({"days": days}, timezone_name):
            raise WeatherUnavailable("Wetterdaten passen nicht zu den nächsten fünf lokalen Tagen.")
    except WeatherUnavailable:
        _record_failure()
        stale = cache.get(stale_key)
        if stale and _entry_stale_usable(stale, timezone_name):
            return _forecast_from_entry(stale, stale=True, timezone_name=timezone_name)
        raise
    _record_success()
    entry = {
        "days": days,
        "fetched_at": timezone.now().isoformat(),
        "timezone": timezone_name,
    }
    cache.set(key, entry, FORECAST_CACHE_SECONDS)
    cache.set(stale_key, entry, FORECAST_STALE_SECONDS)
    return _forecast_from_entry(entry, stale=False, timezone_name=timezone_name)


def forecast_for_station(station) -> Forecast:
    if not getattr(station, "weather_enabled", False):
        raise WeatherUnavailable("Wettervorhersage ist für diese Wache nicht aktiviert.")
    if station.latitude is None or station.longitude is None:
        raise WeatherUnavailable("Für diese Wache sind noch keine Koordinaten gespeichert.")
    return fetch_forecast(
        station.latitude,
        station.longitude,
        timezone_name=station.timezone_name or "Europe/Berlin",
    )


def weather_code_label(code) -> str:
    labels = {
        0: "klar",
        1: "überwiegend klar",
        2: "teils bewölkt",
        3: "bewölkt",
        45: "Nebel",
        48: "Reifnebel",
        51: "leichter Sprühregen",
        53: "Sprühregen",
        55: "starker Sprühregen",
        61: "leichter Regen",
        63: "Regen",
        65: "starker Regen",
        71: "leichter Schneefall",
        73: "Schneefall",
        75: "starker Schneefall",
        80: "Regenschauer",
        81: "Schauer",
        82: "heftige Schauer",
        95: "Gewitter",
        96: "Gewitter mit Hagel",
        99: "starkes Gewitter mit Hagel",
    }
    return labels.get(code, "keine Angabe")


def is_stale(forecast: Forecast) -> bool:
    return forecast.stale or (timezone.now() - forecast.fetched_at) > timedelta(hours=2)
