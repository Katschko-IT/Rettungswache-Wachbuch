"""Muellkalender-ICS-Fallback je Station.

Die offizielle AbfallNavi/RegioIT-Quelle fuer den Kreis Guetersloh ist noch
nicht freigegeben. Bis dahin kann jede Wache eine eigene ICS-URL hinterlegen.
Der Abruf nutzt dasselbe Haertungsprofil wie die Feed-Sync
(``core/feed_sync.py``): HTTPS-only, Port 443, Host in
``FEED_ALLOWED_HOSTS``, keine Weiterleitungen, DNS wird
aufgeloest und es darf nur globale Adressen erreicht werden, der Request geht
direkt an die aufgeloeste IP (DNS-Pinning mit SNI/Host-Header).
"""

from __future__ import annotations

import ipaddress
import re
import socket
from datetime import datetime, timezone as datetime_timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import certifi
import urllib3
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import WasteCollection


_WASTE_MAX_BYTES = getattr(settings, "WASTE_CALENDAR_MAX_BYTES", 1_048_576)


def fetch_waste_calendar(url):
    """HTTPS-only Abruf einer ICS-URL mit DNS-Pinning und Groessenlimit.

    Liefert die rohen Bytes zurueck oder wirft ``ValueError`` bei jeder
    Abweichung vom Haertungsprofil (HTTP, nicht-globaler IP, Redirect,
    zu gross).
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Müllkalender-URL muss HTTPS verwenden.")
    if not parsed.hostname:
        raise ValueError("Müllkalender-URL hat keinen Hostnamen.")
    if parsed.username or parsed.password:
        raise ValueError("Müllkalender-URL darf keine Zugangsdaten enthalten.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Die Portangabe der Müllkalender-URL ist ungültig.") from exc
    if port not in {None, 443}:
        raise ValueError("Müllkalender-URL darf nur HTTPS-Port 443 verwenden.")
    host = parsed.hostname.lower()
    if host not in settings.FEED_ALLOWED_HOSTS:
        raise ValueError("Müllkalender-Host ist nicht in FEED_ALLOWED_HOSTS freigegeben.")

    resolved = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    addresses = list(dict.fromkeys(item[4][0] for item in resolved))
    if not addresses:
        raise ValueError("Müllkalender-Host konnte nicht aufgelöst werden.")
    if any(not ipaddress.ip_address(value).is_global for value in addresses):
        raise ValueError("Müllkalender-URL zeigt auf private oder nicht globale Adressen.")

    target = parsed.path or "/"
    if parsed.query:
        target = f"{target}?{parsed.query}"
    timeout = urllib3.Timeout(connect=5, read=20)
    connection_error = None
    for address in addresses:
        pool = urllib3.HTTPSConnectionPool(
            address,
            port=443,
            assert_hostname=parsed.hostname,
            server_hostname=parsed.hostname,
            cert_reqs="CERT_REQUIRED",
            ca_certs=certifi.where(),
            timeout=timeout,
            maxsize=1,
        )
        try:
            response = pool.request(
                "GET",
                target,
                headers={
                    "Host": parsed.hostname,
                    "User-Agent": "Wachbuch/1.0",
                },
                preload_content=False,
                redirect=False,
                retries=False,
            )
        except urllib3.exceptions.HTTPError as exc:
            connection_error = exc
            pool.close()
            continue
        try:
            if 300 <= response.status < 400:
                raise ValueError("Weiterleitungen sind für Müllkalender deaktiviert.")
            if response.status >= 400:
                raise ValueError(f"Müllkalender-Quelle antwortet mit HTTP {response.status}.")
            content = bytearray()
            for chunk in response.stream(64 * 1024):
                content.extend(chunk)
                if len(content) > _WASTE_MAX_BYTES:
                    raise ValueError("Müllkalender-Quelle überschreitet das Größenlimit (1 MB).")
            return bytes(content)
        finally:
            response.release_conn()
            pool.close()
    raise ValueError(f"Müllkalender-Quelle ist nicht erreichbar: {connection_error}")


_VEVENT_RE = re.compile(r"BEGIN:VEVENT(?P<body>.*?)\r?\nEND:VEVENT", re.IGNORECASE | re.DOTALL)
_LINE_RE = re.compile(r"(?P<name>[A-Z0-9-]+)(?P<params>;[^:\r\n]*)?:(?P<value>.*)")


def _unfold(text):
    """RFC 5545 Zeilenfaltung aufheben (Fortsetzungszeilen beginnen mit Leerzeichen/Tab)."""
    lines = text.splitlines()
    out = []
    for line in lines:
        if line and line[0] in (" ", "\t"):
            if out:
                out[-1] += line[1:]
            continue
        out.append(line)
    return out


def _parse_ics_date(value, tzid=None, tzid_present=False):
    """Parse DTSTART/DTEND Werte. Liefert einen bewussten datetime oder ``None``.

    ``tzid_present`` gibt an, ob der Parameter TZID im ICS-Eintrag explizit
    vorhanden war. Ist er vorhanden, aber leer oder unbekannt, wird ein
    ``ValueError`` ausgeloest, damit keine stillschweigende lokale Zeit
    verwendet wird.
    """
    value = (value or "").strip()
    if not value:
        return None
    if "T" in value:
        core = value.split("T", 1)[1]
        if core.endswith("Z"):
            dt = datetime.strptime(value, "%Y%m%dT%H%M%SZ")
            return dt.replace(tzinfo=datetime_timezone.utc)
        try:
            dt = datetime.strptime(value, "%Y%m%dT%H%M%S")
        except ValueError:
            return None
        if tzid_present:
            if not tzid:
                raise ValueError("Leere Zeitzone im TZID-Parameter.")
            try:
                zone = ZoneInfo(tzid)
            except ZoneInfoNotFoundError:
                raise ValueError(f"Unbekannte Zeitzone: {tzid}")
            return dt.replace(tzinfo=zone)
        return timezone.make_aware(dt)
    if len(value) == 8:
        try:
            dt = datetime.strptime(value, "%Y%m%d")
        except ValueError:
            return None
        return timezone.make_aware(dt)
    return None


def parse_ics(payload):
    """Einfacher ICS-Parser: liefert eine Liste von (title, starts_at, ends_at)."""
    if isinstance(payload, bytes):
        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = payload.decode("latin-1", errors="replace")
    else:
        text = payload
    unfolded = "\n".join(_unfold(text))
    results = []
    for match in _VEVENT_RE.finditer(unfolded):
        body = match.group("body")
        title = None
        starts_at = None
        ends_at = None
        for raw_line in body.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            line_match = _LINE_RE.match(line)
            if not line_match:
                continue
            name = line_match.group("name").upper()
            value = line_match.group("value")
            if name == "SUMMARY":
                title = value
            elif name == "DTSTART":
                tzid = None
                tzid_present = False
                params = line_match.groupdict().get("params")
                if params:
                    for param in params.split(";"):
                        if param.upper().startswith("TZID="):
                            tzid_present = True
                            tzid = param[5:].strip('"')
                            break
                starts_at = _parse_ics_date(value, tzid, tzid_present)
            elif name == "DTEND":
                tzid = None
                tzid_present = False
                params = line_match.groupdict().get("params")
                if params:
                    for param in params.split(";"):
                        if param.upper().startswith("TZID="):
                            tzid_present = True
                            tzid = param[5:].strip('"')
                            break
                ends_at = _parse_ics_date(value, tzid, tzid_present)
        if title and starts_at:
            results.append((title[:200], starts_at, ends_at))
    return results


@transaction.atomic
def store_station_waste(station, payload):
    """Ersetzt die Abfuhrtermine der Wache durch einen geparsten ICS-Inhalt."""
    events = parse_ics(payload)
    WasteCollection.objects.filter(station=station).delete()
    for title, starts_at, ends_at in events:
        WasteCollection.objects.create(
            station=station,
            title=title,
            starts_at=starts_at,
            ends_at=ends_at,
        )
    return len(events)


@transaction.atomic
def sync_station_waste(station):
    """Loescht alte Abfuhrtermine der Wache und ersetzt sie durch den ICS-Import."""
    payload = fetch_waste_calendar(station.waste_calendar_url)
    return store_station_waste(station, payload)
