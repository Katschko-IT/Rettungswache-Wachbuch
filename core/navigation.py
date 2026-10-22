"""Konfigurierbare Hauptnavigation einer Wache.

Ein Katalog beschreibt alle Bereiche, die in der oberen Leiste stehen dürfen.
Welche davon oben erscheinen und in welcher Reihenfolge, legt die Wache in den
Einstellungen fest; die übrigen bleiben unter „Mehr“ erreichbar.
"""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _

# key: (Label, URL-Name, Modul-Flag oder None, Aktiv-Präfixe)
CATALOG = {
    "overview": (_("Übersicht"), "dashboard", None, ("dashboard",)),
    "handovers": (_("Übergaben"), "handover_list", None, ("handover",)),
    "calendar": (_("Kalender"), "calendar", "calendar_enabled", ("calendar",)),
    "tasks": (_("Aufgaben"), "tasks_today", "tasks_enabled", ("task",)),
    "news": (_("Neuigkeiten"), "news_index", None, ("news",)),
    "wiki": (_("Wiki"), "wiki_index", None, ("wiki",)),
    "pinboard": (_("Pinnwand"), "pinboard", "pinboard_enabled", ("pinboard",)),
    "defects": (_("Mängel"), "defects_web", None, ("defect",)),
    "assets": (_("Geräte"), "assets_inventory_web", None, ("asset",)),
    "mpg": (_("MPG & Geräte"), "mpg_dashboard", "mpg_enabled", ("mpg",)),
    "warehouse": (_("Lager & Material"), "warehouse_dashboard", "warehouse_enabled", ("warehouse", "lager")),
    "fleet": (_("Fuhrpark"), "fleet_dashboard", "fleet_enabled", ("fleet", "fuhrpark")),
    "display": (_("Wachen-Display"), "display_home", "display_enabled", ("display",)),
    "orga": (_("Organisation"), "orga_dashboard", "orga_enabled", ("orga",)),
    "reports": (_("Auswertung"), "wachalltag_reports_web", None, ("wachalltag_reports",)),
    "coffee": (_("Kaffeekasse"), "coffee", "coffee_enabled", ("coffee",)),
    "birthdays": (_("Geburtstage"), "birthdays", "birthdays_enabled", ("birthday",)),
    "feeds": (_("Meldungen"), "feeds", "feeds_enabled", ("feeds",)),
    "checklists": (_("Checklisten"), "checklists", "checklists_enabled", ("checklist",)),
    "chat": (_("Wachenchat"), "chat", "chat_enabled", ("chat",)),
    "account": (_("Mein Konto"), "account_home", None, ("account_home",)),
    "more": (_("Mehr"), "more", None, ("more",)),
    "help": (_("Hilfe"), "help_index", None, ("help", "system_status")),
}

# Bereiche, die immer in der Leiste bleiben.
PINNED = ("overview", "handovers", "more", "help")

DEFAULT_PRIMARY = ("overview", "handovers", "calendar", "more", "help")

# Bausteine der Seite „Mehr“ in ihrer Standardreihenfolge.
MORE_ITEMS = (
    ("mpg", _("MPG & Medizingeräte")),
    ("warehouse", _("Lager & Material")),
    ("fleet", _("Fuhrpark & Fahrzeuge")),
    ("display", _("Wachen-Display")),
    ("orga", _("Organisation & Desk")),
    ("defects", _("Mängel")),
    ("assets", _("Geräte & Status")),
    ("reports", _("Auswertung")),
    ("tasks", _("Tagesaufgaben")),
    ("birthdays", _("Geburtstage")),
    ("coffee", _("Kaffeekasse")),
    ("feeds", _("Meldungen & Verkehr")),
    ("checklists", _("Checklisten")),
    ("schedules", _("Prüfintervalle")),
    ("pinboard", _("Pinnwand")),
    ("news", _("Neuigkeiten")),
    ("wiki", _("Wachen-Wiki")),
    ("chat", _("Wachenchat")),
    ("account", _("Mein Konto")),
    ("tokens", _("App-Tokens")),
    ("team", _("Team & Rollen")),
    ("invites", _("Mitarbeiter-Aktivierungen")),
    ("appearance", _("Darstellung")),
    ("settings", _("Einstellungen")),
    ("audit", _("Audit")),
    ("mfa", _("Zwei-Faktor")),
    ("push", _("Push-Benachrichtigungen")),
    ("admin", _("Technische Verwaltung")),
)


def parse_order(raw: str) -> list[str]:
    seen = set()
    ordered = []
    for part in (raw or "").split(","):
        key = part.strip()
        if key in CATALOG and key not in seen:
            seen.add(key)
            ordered.append(key)
    return ordered


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


def _enabled(station, flag):
    if flag is None:
        return True
    return bool(getattr(station, flag, False))


def nav_config(station) -> dict:
    """Leisteneinträge in Reihenfolge plus alle wählbaren Bereiche."""
    primary = parse_order(getattr(station, "nav_order", "") if station else "")
    if not primary:
        primary = list(DEFAULT_PRIMARY)
    for key in PINNED:
        if key not in primary:
            primary.append(key)

    entries = []
    position = 0
    for key in primary:
        label, url_name, flag, active = CATALOG[key]
        if not _enabled(station, flag):
            continue
        position += 1
        entries.append({
            "key": key,
            "label": label,
            "url_name": url_name,
            "active": active,
            "order": position,
        })

    options = []
    for key, (label, _url, flag, _active) in CATALOG.items():
        options.append({
            "key": key,
            "label": label,
            "available": _enabled(station, flag),
            "pinned": key in PINNED,
            "selected": key in primary,
        })
    return {"entries": entries, "options": options, "sequence": primary}


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
