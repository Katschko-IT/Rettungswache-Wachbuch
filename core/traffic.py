"""Verkehrs- und Baustellenlage rund um die Wache.

Drei Quellen, jede für sich optional:

* **Autobahn GmbH** (``verkehr.autobahn.de``) liefert Baustellen und Sperrungen
  der Bundesautobahnen als JSON – ohne Schlüssel und ohne Registrierung.
* **Gemeinde Steinhagen** veröffentlicht Straßenbauarbeiten im Ortsgebiet als
  HTML-Seite; Zeitraum und Sperrart stehen im Fließtext.
* **Kreis Gütersloh** listet die laufenden Bauabschnitte an Kreisstraßen.

Fällt eine Quelle aus, liefert sie eine leere Liste – die Anzeige bleibt
bestehen und zeigt die übrigen Quellen. Es gibt keine erfundenen Ersatzdaten.
"""

from __future__ import annotations

import html
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from html.parser import HTMLParser

from django.core.cache import cache

TIMEOUT_SECONDS = 12
MAX_RESPONSE_BYTES = 3 * 1024 * 1024
CACHE_SECONDS = 600

AUTOBAHN_BASE = "https://verkehr.autobahn.de/o/autobahn"
STEINHAGEN_URL = "https://www.steinhagen.de/wirtschaft-wohnen/baustellen/"
KREIS_URL = (
    "https://www.kreis-guetersloh.de/themen/auto-verkehr-mobilitaet/"
    "kreisstrassen-und-deren-radwege/aktuelle-bauabschnitte/"
)

ALLOWED_HOSTS = {
    "verkehr.autobahn.de",
    "www.steinhagen.de",
    "steinhagen.de",
    "www.kreis-guetersloh.de",
    "kreis-guetersloh.de",
}

# Autobahnen im Einzugsbereich der Wache (A2 Bielefeld/Gütersloh, A33 Bielefeld).
DEFAULT_ROADS = ("A2", "A33")
DEFAULT_RADIUS_KM = 25.0

USER_AGENT = "Wachbuch/1.0 (interner Wachenbetrieb)"

_MONTHS = {
    "januar": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4, "mai": 5,
    "juni": 6, "juli": 7, "august": 8, "september": 9, "oktober": 10,
    "november": 11, "dezember": 12,
}

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


class TrafficUnavailable(Exception):
    """Eine Verkehrsquelle ist nicht erreichbar oder liefert Unerwartetes."""


@dataclass(frozen=True)
class TrafficItem:
    """Ein einzelner Baustellen- oder Sperrhinweis."""

    source: str
    title: str
    section: str = ""
    starts_at: date | None = None
    ends_at: date | None = None
    closed: bool = False
    restricted: bool = False
    distance_km: float | None = None
    url: str = ""
    detail: str = ""

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "title": self.title,
            "section": self.section,
            "starts_at": self.starts_at.isoformat() if self.starts_at else None,
            "ends_at": self.ends_at.isoformat() if self.ends_at else None,
            "closed": self.closed,
            "restricted": self.restricted,
            "distance_km": round(self.distance_km, 1) if self.distance_km is not None else None,
            "url": self.url,
            "detail": self.detail,
        }

    def sort_key(self) -> tuple:
        """Gesperrtes zuerst, danach nach Entfernung, dann nach Namen."""
        return (not self.closed, self.distance_km if self.distance_km is not None else 9e9, self.title)


# --------------------------------------------------------------------------- #
# Netzwerk
# --------------------------------------------------------------------------- #


def _guarded_request(url: str, *, accept: str) -> bytes:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in ALLOWED_HOSTS:
        raise TrafficUnavailable("Nicht erlaubte Verkehrsquelle.")
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": accept}
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise TrafficUnavailable(f"HTTP {status}")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except TrafficUnavailable:
        raise
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise TrafficUnavailable("Verkehrsquelle nicht erreichbar.") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise TrafficUnavailable("Antwort der Verkehrsquelle ist zu groß.")
    return raw


def _fetch_json(url: str) -> dict:
    raw = _guarded_request(url, accept="application/json")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrafficUnavailable("Ungültige Antwort der Verkehrsquelle.") from exc
    if not isinstance(data, dict):
        raise TrafficUnavailable("Unerwartetes Format der Verkehrsquelle.")
    return data


def _fetch_html(url: str) -> str:
    raw = _guarded_request(url, accept="text/html")
    for encoding in ("utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise TrafficUnavailable("Antwort der Verkehrsquelle ist nicht lesbar.")


# --------------------------------------------------------------------------- #
# Datums- und Textauswertung
# --------------------------------------------------------------------------- #


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _two_digit_year(year: int) -> int:
    return 2000 + year if year < 100 else year


_AUTOBAHN_RANGE = re.compile(
    r"(?P<d1>\d{1,2})\.(?P<m1>\d{1,2})\.(?P<y1>\d{2,4})"
    r"(?:\s*(?:von\s*)?(?P<t1>\d{1,2}:\d{2}))?"
    r"\s*bis\s*(?:zum\s+)?"
    r"(?:(?P<d2>\d{1,2})\.(?P<m2>\d{1,2})\.(?P<y2>\d{2,4}))?"
    r"(?:\s*(?P<t2>\d{1,2}:\d{2}))?",
    re.IGNORECASE,
)


_AUTOBAHN_PHASE = re.compile(
    r"Beginn:\s*(?P<d1>\d{1,2})\.(?P<m1>\d{1,2})\.(?P<y1>\d{2,4})"
    r"(?:\s*um\s*(?P<t1>\d{1,2}:\d{2}))?"
    r".{0,40}?Ende:\s*(?P<d2>\d{1,2})\.(?P<m2>\d{1,2})\.(?P<y2>\d{2,4})"
    r"(?:\s*um\s*(?P<t2>\d{1,2}:\d{2}))?",
    re.IGNORECASE | re.DOTALL,
)


def parse_autobahn_period(description: list[str] | str | None) -> tuple[date | None, date | None]:
    """Liest den Gültigkeitszeitraum aus dem Beschreibungstext der Autobahn-API.

    Die API liefert keine strukturierten Zeitstempel; der Zeitraum steht als
    Fließtext in ``description``, etwa
    ``"20.10.26 19:00 bis zum 21.10.26 05:00 Uhr."``.
    """
    if isinstance(description, list):
        text = " ".join(str(part) for part in description)
    else:
        text = str(description or "")
    if not text.strip():
        return None, None

    # Format der längeren Bauphasen: "Beginn: 19.10.26 um 20:00 Uhr
    # Ende: 30.10.26 um 19:00 Uhr".
    phase = _AUTOBAHN_PHASE.search(text)
    if phase:
        start = _safe_date(
            _two_digit_year(int(phase.group("y1"))),
            int(phase.group("m1")),
            int(phase.group("d1")),
        )
        end = _safe_date(
            _two_digit_year(int(phase.group("y2"))),
            int(phase.group("m2")),
            int(phase.group("d2")),
        )
        if start or end:
            return start, end

    match = _AUTOBAHN_RANGE.search(text)
    if not match:
        return None, None
    start_year = _two_digit_year(int(match.group("y1")))
    start = _safe_date(start_year, int(match.group("m1")), int(match.group("d1")))
    if match.group("d2"):
        end_year = _two_digit_year(int(match.group("y2")))
        end = _safe_date(end_year, int(match.group("m2")), int(match.group("d2")))
    elif start:
        # Ohne Enddatum gilt derselbe Tag; läuft die Uhrzeit über Mitternacht
        # ("19:00 bis 05:00"), endet der Zeitraum am Folgetag.
        end = start
        first, last = match.group("t1"), match.group("t2")
        if first and last and last < first:
            end = start + timedelta(days=1)
    else:
        end = None
    return start, end


_STEINHAGEN_RANGE = re.compile(
    r"vom\s+(?P<d1>\d{1,2})\.\s*(?P<m1>\d{1,2})\."
    r"(?:\s*(?P<y1>\d{4}))?"
    r"\s+bis\s+(?:einschließlich\s+\w+\s+)?(?:zum\s+|dem\s+)?"
    r"(?P<d2>\d{1,2})\.\s*(?P<m2>\d{1,2})\.\s*(?P<y2>\d{4})",
    re.IGNORECASE,
)


def parse_german_period(text: str) -> tuple[date | None, date | None]:
    """Liest Zeiträume wie ``"vom 21.10. bis zum 03.11.2026"``.

    Fehlt das Jahr am Startdatum, gilt das Jahr des Enddatums; liegt der Start
    damit in der Zukunft, gehört er ins Vorjahr (Jahreswechsel).
    """
    if not text:
        return None, None
    match = _STEINHAGEN_RANGE.search(text)
    if not match:
        return None, None
    end_year = int(match.group("y2"))
    start_year = int(match.group("y1")) if match.group("y1") else end_year
    start = _safe_date(start_year, int(match.group("m1")), int(match.group("d1")))
    end = _safe_date(end_year, int(match.group("m2")), int(match.group("d2")))
    if start and end and not match.group("y1") and start > end:
        start = _safe_date(start_year - 1, start.month, start.day)
    return start, end


_CLOSURE_WORDS = (
    "vollsperrung",
    "gesperrt",
    "sperrung",
    "nicht anfahrbar",
    "nicht befahrbar",
    "keine durchfahrt",
    "unpassierbar",
)


def looks_closed(text: str) -> bool:
    """Erkennt eine Sperraussage im Fließtext – ohne sie zu erfinden."""
    lowered = (text or "").lower().translate(_UMLAUTS)
    return any(word.translate(_UMLAUTS) in lowered for word in _CLOSURE_WORDS)


def _short(text: str, limit: int = 220) -> str:
    collapsed = re.sub(r"\s+", " ", text or "").strip()
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1].rstrip() + "…"


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Luftlinie in Kilometern (Haversine)."""
    radius = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(a))


# --------------------------------------------------------------------------- #
# Quelle 1: Autobahn GmbH
# --------------------------------------------------------------------------- #


def _autobahn_items(
    road: str, service: str, origin: tuple[float, float]
) -> list[TrafficItem]:
    data = _fetch_json(f"{AUTOBAHN_BASE}/{road}/services/{service}")
    entries = data.get(service) or []
    if not isinstance(entries, list):
        return []
    items: list[TrafficItem] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        point = entry.get("point")
        distance: float | None = None
        if isinstance(point, str) and "," in point:
            try:
                lat, lon = (float(part) for part in point.split(",")[:2])
            except ValueError:
                distance = None
            else:
                distance = distance_km(origin[0], origin[1], lat, lon)
        impact = entry.get("impact") if isinstance(entry.get("impact"), dict) else {}
        symbols = impact.get("symbols") if isinstance(impact.get("symbols"), list) else []
        # ``isBlocked`` ist die Vollsperrung. Das Symbol ``CLOSED`` allein
        # bedeutet in der Autobahn-API nur, dass mindestens eine Spur zu ist.
        closed = str(entry.get("isBlocked", "")).lower() == "true"
        restricted = (not closed) and "CLOSED" in symbols
        lower, upper = impact.get("lower") or "", impact.get("upper") or ""
        section = f"{lower} – {upper}" if lower and upper else (lower or upper)
        starts, ends = parse_autobahn_period(entry.get("description"))
        title = entry.get("title") or f"{road} Baustelle"
        items.append(
            TrafficItem(
                source=f"Autobahn {road}",
                title=title,
                section=section,
                starts_at=starts,
                ends_at=ends,
                closed=closed,
                restricted=restricted,
                distance_km=distance,
                url=f"{AUTOBAHN_BASE}/{road}",
                detail=_short(" ".join(entry.get("description") or []) if isinstance(entry.get("description"), list) else str(entry.get("description") or "")),
            )
        )
    return items


def fetch_autobahn(
    origin: tuple[float, float],
    *,
    roads: tuple[str, ...] = DEFAULT_ROADS,
    radius_km: float = DEFAULT_RADIUS_KM,
) -> list[TrafficItem]:
    """Baustellen und Sperrungen der angegebenen Autobahnen im Umkreis."""
    items: list[TrafficItem] = []
    for road in roads:
        for service in ("closure", "roadworks"):
            try:
                items.extend(_autobahn_items(road, service, origin))
            except TrafficUnavailable:
                continue
    unique: dict[tuple, TrafficItem] = {}
    for item in items:
        if item.distance_km is not None and item.distance_km > radius_km:
            continue
        key = (item.title, item.section, item.starts_at, item.ends_at)
        unique.setdefault(key, item)
    return sorted(unique.values(), key=TrafficItem.sort_key)


# --------------------------------------------------------------------------- #
# Quelle 2 und 3: kommunale Seiten (HTML)
# --------------------------------------------------------------------------- #


class _BlockParser(HTMLParser):
    """Sammelt Überschriften und Absätze aus einem HTML-Ausschnitt.

    Bewusst tolerant: Die kommunalen Seiten ändern ihr Layout gelegentlich;
    gesucht wird nach ``h2``/``h3``-Überschriften mit folgendem Fließtext.
    """

    BLOCK_TAGS = {"h2", "h3", "h4", "p", "li"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str, str]] = []
        self._tag: str | None = None
        self._buffer: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "nav", "footer"}:
            self._skip += 1
            return
        if tag in self.BLOCK_TAGS:
            self._flush()
            self._tag = tag
            self._buffer = []

    def handle_endtag(self, tag):
        if tag in {"script", "style", "nav", "footer"} and self._skip:
            self._skip -= 1
            return
        if tag in self.BLOCK_TAGS:
            self._flush()

    def handle_data(self, data):
        if self._skip:
            return
        if self._tag is not None:
            self._buffer.append(data)

    def _flush(self):
        if self._tag is not None:
            text = re.sub(r"\s+", " ", "".join(self._buffer)).strip()
            if text:
                self.blocks.append((self._tag, text))
        self._tag = None
        self._buffer = []

    def close(self):
        self._flush()
        super().close()


def _section_between(html_text: str, start_marker: str, end_marker: str | None) -> str:
    lowered = html_text.lower()
    start = lowered.find(start_marker.lower())
    if start < 0:
        return html_text
    if end_marker:
        end = lowered.find(end_marker.lower(), start + len(start_marker))
        if end > start:
            return html_text[start:end]
    return html_text[start:]


def fetch_steinhagen() -> list[TrafficItem]:
    """Baustellen der Gemeinde Steinhagen mit Zeitraum und Sperrart."""
    html_text = _fetch_html(STEINHAGEN_URL)
    content = _section_between(html_text, "id-content-first-column", "Soziale")
    parser = _BlockParser()
    parser.feed(content)
    parser.close()

    items: list[TrafficItem] = []
    current_title = ""
    collected: list[str] = []

    def flush() -> None:
        nonlocal current_title, collected
        if not current_title:
            collected = []
            return
        body = " ".join(collected)
        starts, ends = parse_german_period(body)
        if starts or ends or body:
            items.append(
                TrafficItem(
                    source="Gemeinde Steinhagen",
                    title=current_title,
                    section="",
                    starts_at=starts,
                    ends_at=ends,
                    closed=looks_closed(body),
                    url=STEINHAGEN_URL,
                    detail=_short(body),
                )
            )
        current_title, collected = "", []

    for tag, text in parser.blocks:
        if tag in {"h2", "h3", "h4"}:
            flush()
            current_title = text
        elif current_title:
            collected.append(text)
    flush()

    # Seitenmenü, Barrierefreiheitshinweise und leere Überschriften aussortieren.
    ignored = (
        "baustellen", "übersicht", "kontakt", "service", "öffnungszeiten",
        "hilfe zur barrierefreiheit", "barrierefreiheit", "leichte sprache",
    )
    usable = []
    for item in items:
        if item.title.lower().strip() in ignored:
            continue
        # Nur echte Bauhinweise: mit Zeitraum oder mit erkennbarer Sperraussage.
        if item.starts_at is None and not item.closed:
            continue
        usable.append(item)
    return usable


def fetch_kreis_guetersloh() -> list[TrafficItem]:
    """Laufende Bauabschnitte an Kreisstraßen im Kreis Gütersloh."""
    html_text = _fetch_html(KREIS_URL)
    parser = _BlockParser()
    parser.feed(html_text)
    parser.close()

    items: list[TrafficItem] = []
    current_title = ""
    collected: list[str] = []

    def flush() -> None:
        nonlocal current_title, collected
        if not current_title:
            collected = []
            return
        body = " ".join(collected)
        starts, ends = parse_german_period(current_title) or parse_german_period(body)
        items.append(
            TrafficItem(
                source="Kreis Gütersloh",
                title=current_title,
                starts_at=starts,
                ends_at=ends,
                closed=looks_closed(body) or looks_closed(current_title),
                url=KREIS_URL,
                detail=_short(body),
            )
        )
        current_title, collected = "", []

    for tag, text in parser.blocks:
        if tag in {"h2", "h3"}:
            flush()
            current_title = text if re.match(
                r"^(ausbau|erneuerung|anlage|sanierung|neubau|brücke|bau)", text, re.I
            ) else ""
        elif current_title:
            collected.append(text)
    flush()
    return items


# --------------------------------------------------------------------------- #
# NINA-Warnungen (BBK)
# --------------------------------------------------------------------------- #

NINA_AREAS = ("Gütersloh", "Bielefeld", "Steinhagen", "Kreis Gütersloh")


def fetch_nina_warnings(limit: int = 5) -> list[dict]:
    """Bevölkerungswarnungen des BBK, gefiltert auf den Wachenbereich."""
    try:
        raw = _guarded_request_nina()
    except TrafficUnavailable:
        return []
    warnings: list[dict] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        title = (entry.get("i18nTitle") or {}).get("de") or entry.get("title") or ""
        area_text = " ".join(
            str(part)
            for part in (
                entry.get("regionName"),
                entry.get("areaName"),
                (entry.get("transKeys") or {}).get("area"),
            )
            if part
        )
        if NINA_AREAS and area_text and not any(area in area_text for area in NINA_AREAS):
            continue
        if not title:
            continue
        warnings.append(
            {
                "title": _short(title, 160),
                "severity": entry.get("severity") or "",
                "started_at": entry.get("startDate") or "",
                "url": "https://warnung.bund.de/meldungen",
            }
        )
        if len(warnings) >= limit:
            break
    return warnings


def _guarded_request_nina():
    url = "https://warnung.bund.de/api31/mowas/mapData.json"
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() != "warnung.bund.de":
        raise TrafficUnavailable("Nicht erlaubte Warnquelle.")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            if getattr(response, "status", 200) != 200:
                raise TrafficUnavailable("Warnquelle antwortet nicht.")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except TrafficUnavailable:
        raise
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise TrafficUnavailable("Warnquelle nicht erreichbar.") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise TrafficUnavailable("Antwort der Warnquelle ist zu groß.")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrafficUnavailable("Ungültige Antwort der Warnquelle.") from exc
    if not isinstance(data, list):
        raise TrafficUnavailable("Unerwartetes Format der Warnquelle.")
    return data


# --------------------------------------------------------------------------- #
# Zusammenführung
# --------------------------------------------------------------------------- #


def _origin(station) -> tuple[float, float]:
    latitude = getattr(station, "latitude", None)
    longitude = getattr(station, "longitude", None)
    if latitude is None or longitude is None:
        # Fallback nur für die Anzeige, keine gespeicherten Nutzerdaten.
        return (52.0200, 8.4200)
    return (float(latitude), float(longitude))


def traffic_payload(station, *, limit: int = 6) -> dict:
    """Aggregierte Verkehrslage für Anzeige und Display.

    Das Ergebnis enthält niemals Personendaten. Jede Quelle wird einzeln
    abgesichert; ein Ausfall verkleinert die Liste, statt die Anzeige zu kippen.
    """
    if station is None:
        return {"items": [], "warnings": [], "sources": [], "updated_at": None}

    cache_key = f"traffic:{getattr(station, 'pk', 0)}:{limit}"
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        return cached

    origin = _origin(station)
    collected: list[TrafficItem] = []
    active_sources: list[str] = []

    for label, loader in (
        ("Autobahn A2/A33", lambda: fetch_autobahn(origin)),
        ("Gemeinde Steinhagen", fetch_steinhagen),
        ("Kreis Gütersloh", fetch_kreis_guetersloh),
    ):
        try:
            found = loader()
        except TrafficUnavailable:
            continue
        if found:
            active_sources.append(label)
            collected.extend(found)

    collected.sort(key=TrafficItem.sort_key)
    payload = {
        "items": [item.as_dict() for item in collected[:limit]],
        "total": len(collected),
        "warnings": fetch_nina_warnings(),
        "sources": active_sources,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    cache.set(cache_key, payload, CACHE_SECONDS)
    return payload
