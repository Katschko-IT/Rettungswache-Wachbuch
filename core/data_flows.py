"""Übersicht der externen Datenflüsse an Dritte (Paket E2).

Dieses Modul ermittelt den aktuellen Betriebszustand aller in docs/DATENFLUESSE.md
dokumentierten Wege, auf denen Daten die Installation verlassen können.
Die Seite /datenschutz/ bindet diesen Stand ein, sodass Betreiber und
Nutzende transparent sehen, welche externen Dienste aktiv bzw. abgeschaltet sind.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

from django.conf import settings
from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class DataFlow:
    """Konkreter Zustand eines Datenflusses zur Laufzeit."""

    key: str
    title: str
    recipient: str
    personal_data: str
    is_active: bool
    switch: str
    pilot_recommendation: str
    description: str
    in_application: bool = True


@dataclass(frozen=True)
class DataFlowSpec:
    """Definition und Prüffunktion eines Datenflusses."""

    key: str
    title: str
    recipient: str
    personal_data: str
    switch: str
    pilot_recommendation: str
    description: str
    in_application: bool
    checker: Callable[[], bool]


# --- Prüffunktionen für die einzelnen Datenflüsse ---------------------------


def _check_weather() -> bool:
    try:
        from core.models import Station

        return Station.objects.filter(weather_enabled=True).exists()
    except Exception:
        return False


def _check_traffic() -> bool:
    try:
        from core.models import Station

        return Station.objects.filter(traffic_enabled=True).exists()
    except Exception:
        return False


def _check_traffic_local() -> bool:
    try:
        from core.models import Station

        return Station.objects.filter(traffic_local_sources=True).exists()
    except Exception:
        return False


def _check_feeds() -> bool:
    try:
        from core.models import Station

        return Station.objects.filter(feeds_enabled=True).exists()
    except Exception:
        return False


def _check_waste_calendar() -> bool:
    try:
        from core.models import Station

        return Station.objects.filter(waste_calendar_enabled=True).exists()
    except Exception:
        return False


def _check_web_push() -> bool:
    try:
        from core.push import web_push_enabled

        if web_push_enabled():
            return True
    except Exception:
        pass
    return bool(getattr(settings, "WEB_PUSH_ENABLED", False))


def _check_push_relay() -> bool:
    url = getattr(settings, "PUSH_RELAY_URL", "")
    if not url:
        url = os.getenv("PUSH_RELAY_URL", "")
    return bool(str(url).strip())


def _check_signal() -> bool:
    try:
        from core.signal_messenger import signal_enabled

        return bool(signal_enabled())
    except Exception:
        return bool(
            getattr(settings, "SIGNAL_API_URL", "")
            and getattr(settings, "SIGNAL_NUMBER", "")
        )


def _check_email() -> bool:
    if getattr(settings, "DEMO_SANDBOX", False):
        return False
    host = getattr(settings, "EMAIL_HOST", "")
    if not host:
        host = os.getenv("EMAIL_HOST", "")
    return bool(str(host).strip())


def _check_images() -> bool:
    val = getattr(settings, "AUTO_UPDATE", None)
    if val is not None:
        return bool(val)
    return os.getenv("AUTO_UPDATE", "").strip().lower() in ("true", "1", "yes")


def _check_health_ping() -> bool:
    ping = getattr(settings, "PING_URL", "") or os.getenv("PING_URL", "")
    if ping and str(ping).strip():
        return True
    for path in ("/etc/wachwerk/health.env", "/run/wachwerk-health/health.env"):
        try:
            if os.path.exists(path):
                with open(path, encoding="utf-8") as handle:
                    for line in handle:
                        if line.startswith("PING_URL="):
                            val = line.strip().split("=", 1)[1].strip("'\"")
                            if val:
                                return True
        except (OSError, PermissionError):
            pass
    return False


def _check_offsite() -> bool:
    target = getattr(settings, "BACKUP_OFF_TARGET", "") or os.getenv("BACKUP_OFF_TARGET", "")
    return bool(str(target).strip())


def _check_acme() -> bool:
    mode = getattr(settings, "WACHBUCH_MODE", "") or os.getenv("WACHBUCH_MODE", "")
    return str(mode).strip().lower() == "domain"


def _check_os() -> bool:
    # Betriebssystem-Dienste (NTP, Paketquellen, DNS) auf Host-Ebene
    return bool(getattr(settings, "HOST_OS_NETWORK_ACTIVE", True))


def _check_hosting() -> bool:
    try:
        from core.site_profile import SiteProfile

        profile = SiteProfile.current()
        if profile is None:
            return False
        if profile.hosting_provider.strip():
            return True
        return profile.server_location != SiteProfile.ServerLocation.STATION
    except Exception:
        return False


def _check_user_links() -> bool:
    # Werden nur bei manuellem Klick durch den Nutzer ausgelöst
    return False


def _check_app_stores() -> bool:
    # App-Store-Downloads erfolgen extern über die Stores der Anbieter
    return False


def _check_support_report() -> bool:
    # Nur manueller Export auf Wunsch des Master-Admins
    return False


# --- Registrierung aller Datenflüsse aus docs/DATENFLUESSE.md ---------------

FLOW_SPECS: tuple[DataFlowSpec, ...] = (
    DataFlowSpec(
        key="weather",
        title=str(_("Wetter")),
        recipient="Open-Meteo, bei der Ortssuche OpenStreetMap",
        personal_data="nein (Standort der Wache)",
        switch="Station.weather_enabled",
        pilot_recommendation="aus oder nach Entscheidung",
        description="Wettervorhersage für Display, Übersicht und Terminal.",
        in_application=True,
        checker=_check_weather,
    ),
    DataFlowSpec(
        key="traffic",
        title=str(_("Verkehr")),
        recipient="Autobahn GmbH des Bundes, BBK (NINA)",
        personal_data="nein",
        switch="Station.traffic_enabled",
        pilot_recommendation="aus oder nach Entscheidung",
        description="Verkehrs- und Gefahrenmeldungen für Display und Übersicht.",
        in_application=True,
        checker=_check_traffic,
    ),
    DataFlowSpec(
        key="traffic_local",
        title=str(_("Verkehr lokal")),
        recipient="Gemeinde Steinhagen, Kreis Gütersloh",
        personal_data="nein",
        switch="Station.traffic_local_sources",
        pilot_recommendation="aus",
        description="Lokale Baustellen- und Verkehrsmeldungen kommunaler Webseiten.",
        in_application=True,
        checker=_check_traffic_local,
    ),
    DataFlowSpec(
        key="feeds",
        title=str(_("Meldungen")),
        recipient="eingetragene Feed-Quellen",
        personal_data="nein",
        switch="Station.feeds_enabled",
        pilot_recommendation="aus oder nach Entscheidung",
        description="Regelmäßiger Abruf von RSS/Atom-Feeds durch den Hintergrunddienst.",
        in_application=True,
        checker=_check_feeds,
    ),
    DataFlowSpec(
        key="waste_calendar",
        title=str(_("Müllkalender")),
        recipient="Gemeinde bzw. Entsorger",
        personal_data="nein",
        switch="Station.waste_calendar_enabled",
        pilot_recommendation="nach Entscheidung",
        description="Abruf von Abfuhrterminen über eine externe ICS-Kalenderdatei.",
        in_application=True,
        checker=_check_waste_calendar,
    ),
    DataFlowSpec(
        key="web_push",
        title=str(_("Web-Push")),
        recipient="Push-Dienst des Browserherstellers (Google, Mozilla, Apple)",
        personal_data="ja",
        switch="WEB_PUSH_ENABLED",
        pilot_recommendation="aus",
        description="Browser-Benachrichtigungen für dringende Mitteilungen.",
        in_application=True,
        checker=_check_web_push,
    ),
    DataFlowSpec(
        key="push_relay",
        title=str(_("Push-Relay")),
        recipient="Betreiber des Relays, Apple (APNs), Google (FCM)",
        personal_data="ja",
        switch="PUSH_RELAY_URL",
        pilot_recommendation="aus",
        description="Weiterleitung von Benachrichtigungen an mobile Endgeräte (App).",
        in_application=True,
        checker=_check_push_relay,
    ),
    DataFlowSpec(
        key="signal",
        title=str(_("Signal")),
        recipient="Signal Messenger LLC (USA)",
        personal_data="ja",
        switch="SIGNAL_API_URL, SIGNAL_NUMBER",
        pilot_recommendation="aus",
        description="Benachrichtigungen und Kaffeekassen-Erinnerungen über Signal.",
        in_application=True,
        checker=_check_signal,
    ),
    DataFlowSpec(
        key="email",
        title=str(_("E-Mail")),
        recipient="SMTP-Anbieter des Betreibers",
        personal_data="ja",
        switch="EMAIL_HOST",
        pilot_recommendation="nach Entscheidung",
        description=(
            "E-Mail-Versand für Kaffeekasse, technische Servermeldungen und – nur für Personen, die das selbst "
            "eingeschaltet haben – Fristen-Erinnerungen und Wochenübersicht."
        ),
        in_application=True,
        checker=_check_email,
    ),
    DataFlowSpec(
        key="images",
        title=str(_("Images und Updates")),
        recipient="GitHub (ghcr.io, api.github.com)",
        personal_data="nein (IP des Servers)",
        switch="Update-Modus der Installation",
        pilot_recommendation="manuell, Wartungsfenster",
        description="Abruf neuer Container-Images und Release-Informationen.",
        in_application=False,
        checker=_check_images,
    ),
    DataFlowSpec(
        key="health_ping",
        title=str(_("Healthcheck-Ping")),
        recipient="Dienst hinter PING_URL (z. B. healthchecks.io)",
        personal_data="gering (Hostname, Fehlertexte)",
        switch="PING_URL",
        pilot_recommendation="aus",
        description="Regelmäßiger Heartbeat zur Überwachung des Serverzustands.",
        in_application=False,
        checker=_check_health_ping,
    ),
    DataFlowSpec(
        key="offsite",
        title=str(_("Offsite-Sicherung")),
        recipient="Speicherziel des Betreibers (Storage Box, NAS, USB)",
        personal_data="ja (verschlüsselt)",
        switch="BACKUP_OFF_TARGET",
        pilot_recommendation="USB-Rotation oder NAS",
        description="Verschlüsselte Kopie der Datensicherung an ein externes Ziel.",
        in_application=False,
        checker=_check_offsite,
    ),
    DataFlowSpec(
        key="acme",
        title=str(_("Zertifikate")),
        recipient="Let's Encrypt (ACME)",
        personal_data="nein (Domainname)",
        switch="Modus domain",
        pilot_recommendation="nicht nötig (Modus lan)",
        description="Automatische Ausstellung öffentlicher TLS-Zertifikate.",
        in_application=False,
        checker=_check_acme,
    ),
    DataFlowSpec(
        key="os",
        title=str(_("Betriebssystem")),
        recipient="Paketquellen, Zeitserver (NTP), DNS-Resolver",
        personal_data="nein (IP des Servers)",
        switch="Host",
        pilot_recommendation="nach Betreiber",
        description="Paketaktualisierungen, Zeitsynchronisation und Namensauflösung.",
        in_application=False,
        checker=_check_os,
    ),
    DataFlowSpec(
        key="hosting",
        title=str(_("Hosting")),
        recipient="Hoster (SiteProfile.hosting_provider)",
        personal_data="ja",
        switch="Betriebsweg",
        pilot_recommendation="Pi/LAN vor Ort",
        description="Betrieb des Servers bei einem externen Rechenzentrum.",
        in_application=False,
        checker=_check_hosting,
    ),
    DataFlowSpec(
        key="user_links",
        title=str(_("Links für Nutzende")),
        recipient="PayPal, Wero, Signal, Kalender-Apps",
        personal_data="nur durch die Person selbst",
        switch="einzelne Einstellungen",
        pilot_recommendation="nach Entscheidung",
        description="Freiwillige Links auf externe Zahlungs- oder Kalenderdienste.",
        in_application=False,
        checker=_check_user_links,
    ),
    DataFlowSpec(
        key="app_stores",
        title=str(_("App-Stores")),
        recipient="Apple, Google, F-Droid",
        personal_data="ja (Konto im Store)",
        switch="Verteilung der App",
        pilot_recommendation="nach Entscheidung",
        description="Verteilung der mobilen App über offizielle App-Stores.",
        in_application=False,
        checker=_check_app_stores,
    ),
    DataFlowSpec(
        key="support_report",
        title=str(_("Supportbericht")),
        recipient="Empfänger, dem der Admin ihn schickt",
        personal_data="nein",
        switch="manuell",
        pilot_recommendation="nur bei Bedarf",
        description="Manueller Export technischer Fehlerprotokolle durch den Admin.",
        in_application=False,
        checker=_check_support_report,
    ),
)

FLOW_MAP: dict[str, DataFlowSpec] = {spec.key: spec for spec in FLOW_SPECS}


def get_data_flow(key: str) -> DataFlow | None:
    """Einen einzelnen Datenfluss anhand seines Schlüssels prüfen."""
    spec = FLOW_MAP.get(key)
    if spec is None:
        return None
    return DataFlow(
        key=spec.key,
        title=spec.title,
        recipient=spec.recipient,
        personal_data=spec.personal_data,
        is_active=bool(spec.checker()),
        switch=spec.switch,
        pilot_recommendation=spec.pilot_recommendation,
        description=spec.description,
        in_application=spec.in_application,
    )


def get_data_flows(in_application_only: bool = False) -> list[DataFlow]:
    """Alle Datenflüsse mit aktuellem Aktivitätsstatus zurückgeben."""
    results: list[DataFlow] = []
    for spec in FLOW_SPECS:
        if in_application_only and not spec.in_application:
            continue
        results.append(
            DataFlow(
                key=spec.key,
                title=spec.title,
                recipient=spec.recipient,
                personal_data=spec.personal_data,
                is_active=bool(spec.checker()),
                switch=spec.switch,
                pilot_recommendation=spec.pilot_recommendation,
                description=spec.description,
                in_application=spec.in_application,
            )
        )
    return results


def inspect_data_flows(in_application_only: bool = False) -> list[DataFlow]:
    """Alias für get_data_flows."""
    return get_data_flows(in_application_only=in_application_only)


def get_active_data_flows(in_application_only: bool = False) -> list[DataFlow]:
    """Nur die aktuell aktiven Datenflüsse zurückgeben."""
    return [flow for flow in get_data_flows(in_application_only=in_application_only) if flow.is_active]


def get_disabled_data_flows(in_application_only: bool = False) -> list[DataFlow]:
    """Nur die aktuell abgeschalteten Datenflüsse zurückgeben."""
    return [flow for flow in get_data_flows(in_application_only=in_application_only) if not flow.is_active]


def has_active_flows(in_application_only: bool = False) -> bool:
    """True, wenn mindestens ein Datenfluss aktiv ist."""
    return any(flow.is_active for flow in get_data_flows(in_application_only=in_application_only))
