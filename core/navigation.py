"""Konfigurierbare Hauptnavigation einer Wache."""
from __future__ import annotations

# Schlüssel, die in der oberen Leiste stehen dürfen, mit Reihenfolge-Label.
NAV_ITEMS = (
    ("overview", "Übersicht"),
    ("handovers", "Übergaben"),
    ("calendar", "Kalender"),
    ("tasks", "Tagesaufgaben"),
    ("news", "Neuigkeiten"),
    ("wiki", "Wachen-Wiki"),
    ("more", "Mehr"),
    ("help", "Hilfe"),
)

DEFAULT_ORDER = ("overview", "handovers", "calendar", "more", "help")

# Diese Bereiche dürfen zusätzlich in die Leiste, wenn die Wache sie hat.
OPTIONAL_ITEMS = {"tasks", "news", "wiki"}


def parse_order(raw: str) -> list[str]:
    keys = [part.strip() for part in (raw or "").split(",") if part.strip()]
    valid = {key for key, _label in NAV_ITEMS}
    result = [key for key in keys if key in valid]
    # Doppelte entfernen, Reihenfolge der ersten Nennung behalten.
    seen = set()
    ordered = []
    for key in result:
        if key not in seen:
            seen.add(key)
            ordered.append(key)
    return ordered


def nav_config(station) -> dict:
    """Liefert CSS-Reihenfolge und Sichtbarkeit je Navigationspunkt."""
    if station is None:
        order = list(DEFAULT_ORDER)
    else:
        order = parse_order(getattr(station, "nav_order", ""))
        if not order:
            order = list(DEFAULT_ORDER)

    flags = {}
    for index, key in enumerate(order):
        flags[key] = index + 1

    enabled = {
        "tasks": bool(getattr(station, "tasks_enabled", False)),
        "news": True,
        "wiki": True,
        "calendar": bool(getattr(station, "calendar_enabled", False)),
    }

    visible = {}
    for key, _label in NAV_ITEMS:
        required = enabled.get(key, True)
        visible[key] = key in flags and required

    return {"order": flags, "visible": visible, "sequence": order}


MORE_ITEMS = (
    ("defects", "Mängel"),
    ("assets", "Geräte & Status"),
    ("reports", "Auswertung"),
    ("tasks", "Tagesaufgaben"),
    ("birthdays", "Geburtstage"),
    ("coffee", "Kaffeekasse"),
    ("feeds", "Meldungen & Verkehr"),
    ("checklists", "Checklisten"),
    ("schedules", "Prüfintervalle"),
    ("pinboard", "Pinnwand"),
    ("news", "Neuigkeiten"),
    ("wiki", "Wachen-Wiki"),
    ("chat", "Wachenchat"),
    ("account", "Mein Konto"),
    ("tokens", "App-Tokens"),
    ("team", "Team & Rollen"),
    ("invites", "Mitarbeiter-Aktivierungen"),
    ("appearance", "Darstellung"),
    ("settings", "Einstellungen"),
    ("audit", "Audit"),
    ("mfa", "Zwei-Faktor"),
    ("push", "Push-Benachrichtigungen"),
    ("admin", "Technische Verwaltung"),
)


def more_config(station) -> dict:
    """CSS-Reihenfolge der Bausteine unter 'Mehr'."""
    default = {key: index for index, (key, _label) in enumerate(MORE_ITEMS)}
    if station is None:
        return default
    order = parse_order_more(getattr(station, "more_order", ""))
    if not order:
        return default
    result = dict(default)
    for index, key in enumerate(order):
        result[key] = index
    return result


def parse_order_more(raw: str) -> list[str]:
    valid = {key for key, _label in MORE_ITEMS}
    seen = set()
    ordered = []
    for part in (raw or "").split(","):
        key = part.strip()
        if key in valid and key not in seen:
            seen.add(key)
            ordered.append(key)
    return ordered


def save_order(station, order: list[str]) -> None:
    valid = [key for key in parse_order(",".join(order))]
    station.nav_order = ",".join(valid)
