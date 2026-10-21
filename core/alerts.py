"""Amtliche DWD-Wetterwarnungen über Bright Sky (öffentlich, ohne Schlüssel).

Es wird nur die auf zwei Nachkommastellen gerundete Wachenkoordinate an den
Dienst gesendet. Der Abruf ist je Wache abschaltbar (Standard: aus), nutzt die
HTTPS-Allowlist aus ``core.traffic`` und folgt keinen Weiterleitungen.
Ein Ausfall liefert eine leere Liste mit Ausfallkennzeichen statt eines Fehlers.
"""

from __future__ import annotations

from django.core.cache import cache
from django.utils import timezone

from .traffic import TrafficUnavailable, _fetch_json, _short

ALERTS_URL = "https://api.brightsky.dev/alerts"
CACHE_SECONDS = 600
MAX_ALERTS = 5
SEVERITY_RANK = {"extreme": 0, "severe": 1, "moderate": 2, "minor": 3}


def fetch_dwd_alerts(latitude: float, longitude: float) -> list[dict]:
    url = f"{ALERTS_URL}?lat={round(float(latitude), 2):.2f}&lon={round(float(longitude), 2):.2f}"
    data = _fetch_json(url)
    entries = data.get("alerts")
    if not isinstance(entries, list):
        raise TrafficUnavailable("Unerwartetes Format der DWD-Warnungen.")
    alerts: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        title = entry.get("headline_de") or entry.get("event_de") or entry.get("event_en") or ""
        if not title:
            continue
        severity = str(entry.get("severity") or "").lower()
        alerts.append(
            {
                "title": _short(str(title), 160),
                "severity": severity,
                "starts_at": str(entry.get("onset") or entry.get("effective") or "")[:10],
                "ends_at": str(entry.get("expires") or "")[:10],
            }
        )
    alerts.sort(key=lambda a: (SEVERITY_RANK.get(a["severity"], 9), a["starts_at"]))
    return alerts[:MAX_ALERTS]


def alerts_payload(station) -> dict:
    """Warnungen für Anzeige/Display; immer ein Dict, nie eine Ausnahme."""
    empty = {"items": [], "failed": False, "updated_at": None}
    latitude = getattr(station, "latitude", None)
    longitude = getattr(station, "longitude", None)
    if station is None or not getattr(station, "dwd_alerts_enabled", False):
        return empty
    if latitude is None or longitude is None:
        return empty
    key = f"dwd-alerts:{round(float(latitude), 2)}:{round(float(longitude), 2)}"
    cached = cache.get(key)
    if isinstance(cached, dict):
        return cached
    try:
        payload = {"items": fetch_dwd_alerts(latitude, longitude), "failed": False}
    except TrafficUnavailable:
        payload = {"items": [], "failed": True}
    payload["updated_at"] = timezone.now().isoformat(timespec="seconds")
    cache.set(key, payload, CACHE_SECONDS if not payload["failed"] else 60)
    return payload
