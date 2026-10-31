"""Datenkatalog: welche Daten Wachwerk speichert, wer sie sieht und wie lange.

Grundlage für Datenschutz (VVT, DSFA, Art.-13-Information) und Mitbestimmung
(Anlage 1 einer Betriebs- oder Dienstvereinbarung). Aufbau:

- Von Hand gepflegt wird nur die Ebene der Modelle: Modul, Schalter, Zweck,
  Lese- und Schreibrollen, Zugriffswege, Nachweischarakter und Frist.
- Die Felder kommen aus den Django-Metadaten (``_meta``). Eine Heuristik
  ordnet jedes Feld einer Art zu (Person, Name/Kontakt, Freitext …);
  ``FIELD_OVERRIDES`` korrigiert sie, wo sie irrt.
- Abgeleitet statt behauptet: Django-Admin-Zugriff (``admin.site``) und
  Löschschutz (``on_delete``) kommen aus dem Code. Display-Modelle,
  Terminal-Zugang, Schreibrollen (Rollenprüfung in der Ansicht, nicht nur der
  Decorator), Nachweise (Nachweisverzeichnis aus Paket B1), append-only
  (Zeilenschutz und Datenbankrechte) und Namen in App-Schnittstellen prüfen
  die Tests gegen den Code (``core/test_data_catalog.py``).

Die Texte hier sind Betreiber-Dokumentation (``docs/DATENKATALOG.md`` und
Ausgabe von ``manage.py data_catalog``) und deshalb nicht übersetzt – wie
andere Ausgaben von Verwaltungsbefehlen. Choice-Labels werden nie ausgegeben.

Neue Modelle oder Felder: hier eintragen, dann
``python manage.py data_catalog --write`` und den Unterschied in
``docs/DATENKATALOG.md`` mit committen.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from django.conf import settings

REFERENCE_PATH = Path(settings.BASE_DIR) / "docs" / "DATENKATALOG.md"

# ---- Rollen und Zugriffswege ----------------------------------------------

CONTENT = ("member", "shift_lead", "cashier", "admin")

ROLE_LABELS = {
    "member": "Mitglied",
    "shift_lead": "Schichtleitung",
    "cashier": "Kassenwart",
    "admin": "Master-Admin",
    "auditor": "Auditor",
    "self": "die Person selbst",
    "terminal": "Wachenterminal (Dienstkonto)",
    "display": "Wachen-Display",
    "public": "öffentlich",
    "superuser": "Superuser (Django-Admin)",
    "system": "System",
}

ROLE_LEGEND = (
    ("Inhaltsrollen", "Mitglied, Schichtleitung, Kassenwart und Master-Admin einer Wache"),
    ("Mitglied", "Rolle `member`"),
    ("Schichtleitung", "Rolle `shift_lead`"),
    ("Kassenwart", "Rolle `cashier`, nur für die Kaffeekasse"),
    ("Master-Admin", "Rolle `admin`, Verwaltung der Wache"),
    ("Auditor", "Rolle `auditor`, liest nur das Audit-Protokoll, keine fachlichen Freitexte"),
    ("die Person selbst", "nur die eigenen Einträge"),
    ("Wachenterminal (Dienstkonto)", "gemeinsames Gerät an der Wache, Rolle Mitglied, nur Alltagsbereiche (docs/PI-WACHENTERMINAL.md)"),
    ("Wachen-Display", "Bildschirm mit Display-Link, ohne Anmeldung"),
    ("öffentlich", "ohne Anmeldung erreichbar"),
    ("Superuser (Django-Admin)", "technischer Betrieb unter `/django-admin/`, ohne Bindung an eine Wache"),
    ("System", "Hintergrunddienste (housekeeping, worker, Abgleich), keine Person"),
)

CHANNEL_LABELS = {
    "web": "Web",
    "app": "App (API)",
    "terminal": "Wachenterminal",
    "display": "Display",
    "public": "öffentliche Seite",
    "export": "Export/Datei",
    "email": "E-Mail",
    "signal": "Signal",
    "push": "Push",
}

CHANNEL_LEGEND = (
    ("Web", "Weboberfläche nach Anmeldung, immer an die eigene Wache gebunden"),
    ("App (API)", "App-Zugang über `/api/v1/` mit persönlichem App-Token"),
    ("Wachenterminal", "Alltagsmodus am registrierten Terminal unter dem Dienstkonto; geprüft gegen `core/terminal.py` (OPEN_MODE_PATHS)"),
    ("Display", "Wachen-Display sowie Sperrbildschirm und Startseite des Wachenterminals: nur Titel, Zählwerte und Ampeln, ohne Anmeldung sichtbar; geprüft gegen die Abfragen von `core/display.py`"),
    ("öffentliche Seite", "Impressum, Datenschutz und Anmeldung ohne Konto"),
    ("Export/Datei", "CSV-, ICS- oder Druckausgabe"),
    ("E-Mail", "Versand über den eingetragenen SMTP-Server (nur wenn eingerichtet)"),
    ("Signal", "Versand über Signal (nur wenn eingerichtet)"),
    ("Push", "Benachrichtigung an Browser oder App (nur wenn eingerichtet)"),
    ("Django-Admin", "aus `admin.site` abgeleitet: Superuser lesen oder ändern ohne Bindung an eine Wache"),
)


# ---- Fristen ---------------------------------------------------------------


def _days(value) -> str:
    value = int(value or 0)
    if value <= 0:
        return "unbegrenzt (0)"
    return "1 Tag" if value == 1 else f"{value} Tage"


def _login_log_days() -> int:
    from core.management.commands.housekeeping import _env_int

    return _env_int("LOGIN_LOG_RETENTION_DAYS", 30)


def _session_hours() -> int:
    return int(getattr(settings, "SESSION_COOKIE_AGE", 43200)) // 3600


def _push_days() -> int:
    from core.models import PushOutbox

    return PushOutbox.RETENTION_DAYS


def _signal_days() -> int:
    from core.signal_messenger import OUTBOX_RETENTION_DAYS

    return OUTBOX_RETENTION_DAYS


def _error_days() -> int:
    return max(int(getattr(settings, "ERROR_EVENT_RETENTION_DAYS", 30) or 30), 1)


@dataclass(frozen=True)
class RetentionRule:
    key: str
    title: str
    default_text: str
    live_text: Callable[[], str] | None = None
    automatic: bool = False
    gap: bool = False

    def text(self, live: bool = False) -> str:
        if live and self.live_text is not None:
            return self.live_text()
        return self.default_text


RETENTION_RULES = {
    rule.key: rule
    for rule in (
        RetentionRule(
            "sessions", "Sitzung",
            "läuft nach 12 Stunden ab; abgelaufene Sitzungen löscht `housekeeping` stündlich",
            lambda: f"läuft nach {_session_hours()} Stunden ab (SESSION_COOKIE_AGE); abgelaufene Sitzungen löscht `housekeeping` stündlich",
            automatic=True,
        ),
        RetentionRule(
            "login_log", "Anmeldeprotokoll",
            "30 Tage (LOGIN_LOG_RETENTION_DAYS, `housekeeping`)",
            lambda: f"{_days(_login_log_days())} (LOGIN_LOG_RETENTION_DAYS, `housekeeping`)",
            automatic=True,
        ),
        RetentionRule(
            "login_attempts", "Sperrzähler",
            "django-axes entfernt den Zähler nach erfolgreicher Anmeldung und nach Ablauf der Sperrzeit (1 Stunde) beim nächsten Anmeldeversuch",
            automatic=True,
        ),
        RetentionRule(
            "error_events", "Fehlerereignis",
            "30 Tage (ERROR_EVENT_RETENTION_DAYS, `housekeeping`)",
            lambda: f"{_days(_error_days())} (ERROR_EVENT_RETENTION_DAYS, `housekeeping`)",
            automatic=True,
        ),
        RetentionRule(
            "qr_login_24h", "QR-Anmeldung",
            "abgeschlossene oder abgelaufene Vorgänge nach 24 Stunden (`housekeeping`)",
            automatic=True,
        ),
        RetentionRule(
            "terminal_pairing", "Kopplungscode",
            "gilt 120 Sekunden; abgelaufene Codes löscht die nächste Kopplung nach einem Tag",
            automatic=True,
        ),
        RetentionRule(
            "push_outbox", "Push-Warteschlange",
            "versendete oder verworfene Nachrichten nach 30 Tagen (`housekeeping`)",
            lambda: f"versendete oder verworfene Nachrichten nach {_days(_push_days())} (`housekeeping`)",
            automatic=True,
        ),
        RetentionRule(
            "signal_outbox", "Signal-Warteschlange",
            "gesendete Nachrichten nach 30 Tagen (Signal-Worker)",
            lambda: f"gesendete Nachrichten nach {_days(_signal_days())} (Signal-Worker)",
            automatic=True,
        ),
        RetentionRule(
            "feed", "Meldungen",
            "90 Tage nach dem letzten Abruf (RETENTION_FEED_DAYS, `housekeeping`)",
            lambda: f"{_days(getattr(settings, 'RETENTION_FEED_DAYS', 0))} nach dem letzten Abruf (RETENTION_FEED_DAYS, `housekeeping`)",
            automatic=True,
        ),
        RetentionRule(
            "feedback", "Rückmeldung",
            "365 Tage (FEEDBACK_RETENTION_DAYS, `housekeeping`); vorher von Hand löschbar",
            lambda: f"{_days(getattr(settings, 'FEEDBACK_RETENTION_DAYS', 0))} (FEEDBACK_RETENTION_DAYS, `housekeeping`); vorher von Hand löschbar",
            automatic=True,
        ),
        RetentionRule(
            "audit", "Audit",
            "unbegrenzt, solange RETENTION_AUDIT_DAYS = 0 (Standard); sonst löscht `apply_retention` mit den Rechten des Datenbank-Eigentümers",
            lambda: f"{_days(getattr(settings, 'RETENTION_AUDIT_DAYS', 0))} (RETENTION_AUDIT_DAYS, `apply_retention` mit den Rechten des Datenbank-Eigentümers)",
            automatic=True,
        ),
        RetentionRule(
            "rate_limit", "Rate-Limit-Zähler",
            "abgelaufene Zähler stündlich (`housekeeping`); gespeichert ist nur ein Hash",
            automatic=True,
        ),
        RetentionRule(
            "demo", "Demo-Besuch",
            "beim Abmelden, nach 30 Minuten ohne Aktivität oder spätestens nach 120 Minuten (DEMO_SANDBOX_IDLE_MINUTES, DEMO_SANDBOX_MAX_MINUTES)",
            lambda: (
                f"beim Abmelden, nach {getattr(settings, 'DEMO_SANDBOX_IDLE_MINUTES', 30)} Minuten ohne Aktivität "
                f"oder spätestens nach {getattr(settings, 'DEMO_SANDBOX_MAX_MINUTES', 120)} Minuten"
            ),
            automatic=True,
        ),
        RetentionRule(
            "waste_replace", "Abholtermine",
            "werden bei jedem Abgleich des Müllkalenders ersetzt",
            automatic=True,
        ),
        RetentionRule(
            "withdrawal", "Freiwillige Angabe",
            "beim Widerruf sofort entfernt (Geburtstag: Tag und Monat geleert; Signal: Nummer gelöscht)",
            automatic=True,
        ),
        RetentionRule(
            "device_unregister", "Gerätebindung",
            "beim Abmelden des Geräts oder wenn der Push-Dienst die Adresse als ungültig meldet",
            automatic=True,
        ),
        RetentionRule(
            "token", "Zugangsschlüssel",
            "gilt bis Ablauf oder Widerruf; widerrufene und abgelaufene Einträge bleiben ohne technische Löschung",
            gap=True,
        ),
        RetentionRule(
            "account", "Konto",
            "solange das Konto besteht; Deaktivieren oder Löschen durch Master-Admin bzw. Superuser",
        ),
        RetentionRule(
            "evidence", "Nachweis",
            "keine automatische Löschung; Web und App bieten kein Löschen an; Aufbewahrung laut Löschkonzept",
        ),
        RetentionRule(
            "training_replace", "Einweisung",
            "keine automatische Löschung; eine neue Einweisung derselben Person am selben Gerät ersetzt die vorige "
            "(Einzeleinweisung löscht sie, Gruppenschulung überschreibt sie); Aufbewahrung laut Löschkonzept",
        ),
        RetentionRule(
            "task_reopen", "Erledigt-Vermerk",
            "keine automatische Löschung; „Wieder öffnen“ löscht den Vermerk (Audit station_task.reopened)",
        ),
        RetentionRule(
            "organisational", "Organisationsdaten",
            "keine automatische Löschung; bleibt, bis die Wache den Eintrag nicht mehr braucht",
        ),
        RetentionRule(
            "attachment", "Anhang",
            "keine automatische Löschung; Löschung zusammen mit dem Vorgang laut Löschkonzept",
            gap=True,
        ),
        RetentionRule(
            "config", "Einstellung",
            "solange die Installation besteht; Änderung durch Master-Admin",
        ),
        RetentionRule(
            "technical", "Technische Tabelle",
            "ohne Personenbezug; bleibt, solange die Installation besteht",
        ),
        RetentionRule(
            "gap", "Lücke",
            "keine technische Löschung (siehe docs/LOESCHKONZEPT.md, Lücken)",
            gap=True,
        ),
    )
}

PERIOD_DECISION_TEXT = "laut freigegebenem Löschkonzept: [festlegen]"


# ---- Registry ---------------------------------------------------------------


@dataclass(frozen=True)
class ModelSpec:
    label: str
    purpose: str
    read: tuple
    write: tuple
    channels: tuple = ("web",)
    retention: str = "organisational"
    evidence: bool = False
    note: str = ""


@dataclass(frozen=True)
class EvaluationSpec:
    url_name: str
    title: str
    roles: tuple
    person_related: bool
    note: str = ""


@dataclass(frozen=True)
class ModuleSpec:
    key: str
    title: str
    purpose: str
    models: tuple
    flag: str | None = None
    gate: str | None = None
    web_prefixes: tuple = ()
    entry_url: str | None = None
    evaluations: tuple = field(default_factory=tuple)
    note: str = ""


def _gate_terminal() -> bool:
    return bool(getattr(settings, "TERMINAL_ENABLED", False))


def _gate_signal() -> bool:
    from core.signal_messenger import signal_enabled

    return signal_enabled()


def _gate_demo() -> bool:
    from core.demo_sandbox import sandbox_enabled

    return sandbox_enabled()


def _gate_feedback() -> bool:
    from core.feedback import feedback_enabled

    return feedback_enabled()


GATES = {
    "terminal": ("TERMINAL_ENABLED", _gate_terminal),
    "signal": ("SIGNAL_API_URL und SIGNAL_NUMBER", _gate_signal),
    "demo_sandbox": ("DEMO_SANDBOX", _gate_demo),
    "feedback": ("FEEDBACK_ENABLED", _gate_feedback),
}

C = CONTENT
CS = ("shift_lead", "admin")

MODULES = (
    ModuleSpec(
        "konto", "Konten, Anmeldung und Rollen",
        "Anmeldung, Zwei-Faktor-Schutz, Rollen je Wache und App-Zugänge.",
        flag=None, web_prefixes=("/konto/", "/team/", "/anmelden/", "/registrieren/", "/aktivieren/", "/abmelden/", "/sprache/"),
        entry_url="account_home",
        evaluations=(
            EvaluationSpec("team", "Teamliste mit Namen, Rollen und Zwei-Faktor-Stand", ("admin",), True),
            EvaluationSpec("team_invites", "Offene Einladungen mit Namen", ("admin",), True),
        ),
        models=(
            ModelSpec("auth.User", "Benutzerkonto: Anmeldename, Name, E-Mail, Passwort-Hash", ("self", "admin", "auditor", "display", "superuser"), ("self", "admin", "superuser"), ("web", "app", "display"), "account",
                      note="Andere Inhaltsrollen sehen Vor- und Nachnamen dort, wo Einträge einer Person zugeordnet sind; der Auditor sieht Namen im Audit-Protokoll; "
                           "Display und Sperrbildschirm zeigen am Geburtstag Vorname und Anfangsbuchstaben (nur mit Einwilligung)."),
            ModelSpec("auth.Group", "Django-Gruppen (in Wachwerk ungenutzt)", ("superuser",), ("superuser",), (), "technical"),
            ModelSpec("auth.Permission", "Django-Rechte für den Django-Admin", ("superuser",), ("system",), (), "technical"),
            ModelSpec("core.UserProfile", "Sprache und Profilbild", ("self", "member", "shift_lead", "cashier", "admin", "terminal"), ("self",), ("web", "app", "terminal"), "account",
                      note="Profilbilder sehen Inhaltsrollen derselben Wache und das Wachenterminal (nur Anzeige)."),
            ModelSpec("core.Membership", "Rolle einer Person in einer Wache", ("self", "admin"), ("admin",), ("web", "app"), "account",
                      note="Die eigene Rolle sieht jede Person; die Teamliste nur der Master-Admin."),
            ModelSpec("core.TotpDevice", "Zwei-Faktor-Schlüssel (TOTP), verschlüsselt gespeichert", ("self",), ("self", "admin"), ("web",), "account",
                      note="Der Master-Admin kann den zweiten Faktor zurücksetzen, aber nicht lesen."),
            ModelSpec("core.WebAuthnCredential", "Passkeys (öffentlicher Schlüssel, Gerätename)", ("self",), ("self",), ("web",), "account"),
            ModelSpec("core.QrLoginRequest", "Anmeldung per QR-Code (Hashes, Status, Herkunft)", ("system",), ("self", "system"), ("web",), "qr_login_24h"),
            ModelSpec("core.QrTotpUse", "Schutz gegen doppelt benutzte TOTP-Codes", ("system",), ("system",), (), "qr_login_24h"),
            ModelSpec("core.ApiToken", "App-Zugänge (nur Hash und Präfix gespeichert)", ("self",), ("self",), ("web", "app"), "token"),
            ModelSpec("core.RegistrationRequest", "Selbstregistrierung mit Wunschwache und Notiz", ("admin",), ("public", "admin"), ("web", "public"), "gap"),
            ModelSpec("core.EmployeeActivation", "Einladungen zur Kontoaktivierung (nur Hash)", ("admin",), ("admin",), ("web",), "gap"),
        ),
    ),
    ModuleSpec(
        "anmeldeschutz", "Sitzungen und Anmeldeschutz",
        "Sitzungen, Sperre nach Fehlversuchen und Begrenzung der Anfragen.",
        models=(
            ModelSpec("sessions.Session", "Angemeldete Sitzungen (Inhalt verschlüsselt signiert)", ("system",), ("system",), (), "sessions"),
            ModelSpec("axes.AccessAttempt", "Fehlgeschlagene Anmeldungen je Benutzername und IP-Adresse (Sperrzähler)", ("superuser",), ("system",), (), "login_attempts"),
            ModelSpec("axes.AccessAttemptExpiration", "Ablaufzeit der Sperre", ("system",), ("system",), (), "login_attempts"),
            ModelSpec("axes.AccessLog", "Anmeldeprotokoll: Benutzername, IP-Adresse, Browser, Zeit", ("superuser",), ("system",), (), "login_log"),
            ModelSpec("axes.AccessFailureLog", "Protokoll fehlgeschlagener Anmeldungen", ("superuser",), ("system",), (), "login_log"),
            ModelSpec("core.RateLimit", "Zähler gegen zu viele Anfragen (nur Hash des Schlüssels)", ("system",), ("system",), (), "rate_limit"),
        ),
    ),
    ModuleSpec(
        "wache", "Wache, Betreiber und Datenschutzkontakt",
        "Stammdaten der Wache, Impressum und Datenschutzinformation, Modulschalter.",
        web_prefixes=("/einstellungen/", "/datenschutz/", "/impressum/", "/setup/"),
        entry_url="station_settings",
        models=(
            ModelSpec("core.Station", "Wache: Name, Adresse, Modulschalter, Zahlungsangaben der Kaffeekasse", C + ("superuser",), ("admin", "superuser"), ("web", "app", "display"), "config",
                      note="Der Auditor sieht nur den Namen der Wache. Zahlungsangaben (IBAN, BIC, Verwendungszweck) sehen Inhaltsrollen auf der Seite Kaffeekasse."),
            ModelSpec("core.SiteProfile", "Betreiberangaben für Impressum und Datenschutzinformation", ("public",), ("admin",), ("public", "terminal"), "config"),
            ModelSpec("core.DataProtectionOfficer", "Kontakt der Datenschutzbeauftragten", ("public", "admin", "superuser"), ("admin", "superuser"), ("public", "terminal"), "config",
                      note="Öffentlich nur, wenn „in der Datenschutzinformation veröffentlichen“ gesetzt ist; interne Notizen nie."),
            ModelSpec("core.InstallationSetup", "Abschluss der Ersteinrichtung", ("system",), ("system",), (), "config"),
            ModelSpec("core.AppVersion", "Aktuelle App-Versionen für die Update-Prüfung", ("public",), ("superuser",), ("app",), "technical"),
        ),
    ),
    ModuleSpec(
        "audit", "Audit, Fehler und Verwaltungsprotokoll",
        "Nachvollziehbarkeit von Änderungen und Betrieb ohne fachliche Freitexte.",
        web_prefixes=("/audit/", "/system/", "/django-admin/"),
        entry_url="audit_log",
        evaluations=(
            EvaluationSpec("audit_log", "Audit-Protokoll mit Person, Zeit, Aktion und geänderten Feldern", ("auditor", "admin"), True),
            EvaluationSpec("error_events", "Fehlerereignisse ohne Personenbezug", ("admin",), False),
            EvaluationSpec("support_export", "Supportbericht (Fehlercodes, Version, ohne Personen)", ("admin",), False,
                           "Felder siehe SUPPORT_EXPORT_FIELDS in core/diagnostics_export.py"),
        ),
        models=(
            ModelSpec("core.AuditEvent", "Audit: wer hat wann was an welchem Objekt geändert", ("auditor", "admin", "superuser"), ("system",), ("web",), "audit", evidence=True,
                      note="Append-only. Enthält Feldnamen und Statuswerte, keine fachlichen Freitexte."),
            ModelSpec("core.ErrorEvent", "Fehlerereignisse (Route, Kategorie, Status, Version)", ("admin",), ("system",), ("web", "export"), "error_events"),
            ModelSpec("admin.LogEntry", "Änderungsprotokoll des Django-Admin", ("superuser",), ("superuser",), (), "gap"),
            ModelSpec("contenttypes.ContentType", "Technische Liste der Datentypen", ("system",), ("system",), (), "technical"),
        ),
    ),
    ModuleSpec(
        "uebergaben", "Übergaben",
        "Informationen von Schicht zu Schicht mit Quittierung.",
        web_prefixes=("/uebergaben/",), entry_url="handover_list",
        evaluations=(
            EvaluationSpec("handover_detail", "Lesebestätigungen und Änderungsverlauf einer Übergabe mit Namen und Zeit", C + ("terminal",), True,
                           "für alle Inhaltsrollen und am Wachenterminal sichtbar"),
            EvaluationSpec("api_v1_handover_acks", "Lesebestätigungen mit Namen und Zeit (App)", C, True),
        ),
        models=(
            ModelSpec("core.HandoverEntry", "Übergabe: Titel, Text, Kategorie, Priorität, Status, Autor", C + ("terminal", "display"), C + ("terminal",), ("web", "app", "terminal", "display"),
                      "evidence", evidence=True,
                      note="Display: nur die Zahl dringender offener Übergaben. Status und Bearbeitung: Schichtleitung und Master-Admin; "
                           "jede Änderung bleibt als Version in core.HandoverRevision erhalten."),
            ModelSpec("core.HandoverRevision", "Versionen einer Übergabe (Schnappschuss, Person)", C, ("system",), ("web",), "evidence", evidence=True),
            ModelSpec("core.HandoverAttachment", "Anhänge (Bild oder PDF)", C + ("terminal",), C + ("terminal",), ("web", "app", "terminal"), "attachment", evidence=True),
            ModelSpec("core.HandoverAck", "Lesebestätigung: Person und Zeit", C + ("terminal",), C, ("web", "app", "terminal"), "evidence", evidence=True),
        ),
    ),
    ModuleSpec(
        "neuigkeiten", "Neuigkeiten mit Lesebestätigung",
        "Mitteilungen der Wachleitung, die alle quittieren.",
        web_prefixes=("/neuigkeiten/",), entry_url="news_index",
        evaluations=(
            EvaluationSpec("news_detail", "Lesestand einer Neuigkeit als Anzahl („3 von 8 haben gelesen“)", C + ("terminal",), False,
                           "keine Namen; bei sehr kleinen Wachen lässt die Zahl Rückschlüsse zu"),
        ),
        models=(
            ModelSpec("core.NewsPost", "Neuigkeit: Titel, Text, Autor", C + ("terminal", "display"), CS, ("web", "terminal", "display")),
            ModelSpec("core.NewsAcknowledgement", "Quittierung: Person und Zeit", ("self",), ("self",), ("web",),
                      note="Lesestatus, kein Nachweis. Andere sehen nur die Anzahl. Das Wachenterminal kann nicht quittieren."),
            ModelSpec("core.NewsAttachment", "Anhänge (Bild oder PDF)", C + ("terminal",), CS, ("web", "terminal"), "attachment", evidence=True),
        ),
    ),
    ModuleSpec(
        "wiki", "Wachen-Wiki",
        "Wissen der Wache mit Versionsverlauf.",
        web_prefixes=("/wiki/",), entry_url="wiki_index",
        evaluations=(
            EvaluationSpec("wiki_detail", "Versionsverlauf eines Artikels mit Vorname der bearbeitenden Person", C, True),
        ),
        models=(
            ModelSpec("core.WikiArticle", "Artikel: Titel, Text, Autor", C, ("admin",), ("web",)),
            ModelSpec("core.WikiRevision", "Versionen mit bearbeitender Person", C, ("system",), ("web",), "evidence", evidence=True),
        ),
    ),
    ModuleSpec(
        "maengel", "Mängel",
        "Mängel an Fahrzeugen, Geräten und Gebäude mit Frist und Verlauf.",
        web_prefixes=("/maengel/",), entry_url="defects_web",
        evaluations=(
            EvaluationSpec("defects_web", "Mängelliste mit Vorname der zuständigen Person", C + ("terminal",), True),
            EvaluationSpec("defect_detail_web", "Verlauf und Anhänge eines Mangels mit Vorname der handelnden Person", C + ("terminal",), True),
            EvaluationSpec("api_v1_defects", "Mängelliste mit Benutzername der zuständigen Person (App)", C, True),
            EvaluationSpec("api_v1_defect_detail", "Mangel mit Verlauf und Anhängen, jeweils mit Benutzername (App)", C, True),
            EvaluationSpec("api_v1_defect_attachments", "Anhänge eines Mangels mit Benutzername der hochladenden Person (App)", C, True),
        ),
        models=(
            ModelSpec("core.Defect", "Mangel: Titel, Beschreibung, Priorität, Status, zuständige Person", C + ("terminal",), C + ("terminal",), ("web", "app", "terminal"),
                      "evidence", evidence=True, note="Bearbeitung möglich; Statuswechsel stehen im Verlauf core.DefectEvent."),
            ModelSpec("core.DefectEvent", "Verlauf: Statuswechsel mit Person", C + ("terminal",), ("system",), ("web", "app", "terminal"), "evidence", evidence=True),
            ModelSpec("core.DefectAttachment", "Fotos zum Mangel (Metadaten entfernt)", C + ("terminal",), C + ("terminal",), ("web", "app", "terminal"), "attachment", evidence=True),
        ),
    ),
    ModuleSpec(
        "geraete", "Geräte, Status und Ausgabe",
        "Einsatzbereitschaft von Geräten und Ausgabe von Gegenständen (Funk, Schlüssel).",
        web_prefixes=("/geraete/", "/auswertung/"), entry_url="assets_inventory_web",
        evaluations=(
            EvaluationSpec("assets_inventory_web", "Ausgabeliste: wer hat welchen Gegenstand", C, True),
            EvaluationSpec("api_v1_inventory", "Ausgabeliste mit Namen (App)", C, True),
            EvaluationSpec("wachalltag_reports_web", "Kennzahlen der Wache; je Person nur die eigenen Quittierungen", C, False),
            EvaluationSpec("api_v1_reports", "Kennzahlen der Wache (App)", C, False),
        ),
        models=(
            ModelSpec("core.StationAsset", "Gerät mit Status und Notiz", C, CS + ("system",), ("web", "app"),
                      note="Anlegen und Statuswechsel: Schichtleitung und Master-Admin. Bei Medizingeräten übernimmt Wachwerk den Status aus dem Modul Medizinprodukte."),
            ModelSpec("core.AssetEvent", "Statusverlauf mit Person", C, ("system",), ("web",), "evidence", evidence=True),
            ModelSpec("core.InventoryItem", "Ausgabegegenstand mit aktueller Inhaberin oder aktuellem Inhaber", C, CS, ("web", "app"),
                      note="Anlegen: Schichtleitung und Master-Admin. Ausgabe und Rückgabe (Inhaberin oder Inhaber) tragen alle Inhaltsrollen ein."),
            ModelSpec("core.InventoryEvent", "Ausgabe und Rückgabe mit Person", C, ("system",), ("web",), "evidence", evidence=True),
        ),
    ),
    ModuleSpec(
        "kalender", "Kalender",
        "Termine der Wache, auch als Kalender-Abo.",
        flag="calendar_enabled", web_prefixes=("/kalender/",), entry_url="calendar",
        evaluations=(
            EvaluationSpec("calendar_feed_ics", "Kalender als ICS-Datei", C, False),
            EvaluationSpec("calendar_feed_token_ics", "Kalender-Abo über geheimen Link (ohne Anmeldung)", ("public",), False,
                           "Termine der Wache ohne Personen; der Link wirkt wie ein Passwort"),
            EvaluationSpec("calendar_event_ics", "Einzeltermin als ICS-Datei", C, False),
        ),
        models=(
            ModelSpec("core.CalendarEvent", "Termin: Titel, Beschreibung, Zeit, Autor", C + ("terminal", "display"), CS, ("web", "app", "terminal", "display", "export"), "gap"),
            ModelSpec("core.CalendarFeedToken", "Geheime Links für Kalender-Abos", CS, CS, ("web",), "token"),
        ),
    ),
    ModuleSpec(
        "muellkalender", "Müllkalender",
        "Abholtermine aus einer ICS-Adresse der Gemeinde.",
        flag="waste_calendar_enabled",
        models=(
            ModelSpec("core.WasteCollection", "Abholtermin: Titel und Zeit", C + ("display",), ("system",), ("web", "display"), "waste_replace"),
        ),
    ),
    ModuleSpec(
        "geburtstage", "Geburtstage (freiwillig)",
        "Freiwillige Anzeige von Tag und Monat, nie das Geburtsjahr.",
        flag="birthdays_enabled", web_prefixes=("/geburtstage/",), entry_url="birthdays",
        evaluations=(
            EvaluationSpec("birthdays", "Liste der freigegebenen Geburtstage mit Namen", C, True),
        ),
        models=(
            ModelSpec("core.BirthdayPreference", "Tag und Monat mit Einwilligung und Widerruf", C + ("display",), ("self",), ("web", "display"), "withdrawal",
                      note="Display und Sperrbildschirm des Terminals: Vorname und Anfangsbuchstabe am Tag selbst."),
        ),
    ),
    ModuleSpec(
        "kaffeekasse", "Kaffeekasse (freiwillig)",
        "Gemeinschaftskasse mit Monatsbeiträgen und Kassenbuch (docs/KAFFEEKASSE.md).",
        flag="coffee_enabled", web_prefixes=("/kaffeekasse/",), entry_url="coffee",
        evaluations=(
            EvaluationSpec("coffee_book", "Mappe: Stand aller Teilnehmenden", ("cashier",), True),
            EvaluationSpec("coffee_ledger", "Buchungen aller Teilnehmenden", ("cashier",), True),
            EvaluationSpec("coffee_participants", "Teilnehmendenliste", ("cashier", "admin"), True),
            EvaluationSpec("coffee_export", "Export aller Buchungen als CSV", ("cashier",), True),
            EvaluationSpec("api_v1_kaffeekasse", "Buchungen aller Teilnehmenden mit vollem Namen (App)", ("cashier",), True,
                           "andere Inhaltsrollen erhalten nur ihre eigenen Buchungen"),
        ),
        models=(
            ModelSpec("core.CoffeeEntry", "Buchung: Person, Betrag, Art, Monat, erfasst von", ("self", "cashier"), ("cashier", "self"), ("web", "app", "export"), "evidence", evidence=True,
                      note="Append-only. Jede Person sieht ihre eigenen Buchungen, der Kassenwart alle."),
            ModelSpec("core.CoffeeFund", "Einstellungen der Kasse (Beitrag, Kontoinhaber, Erinnerungen)", C, ("cashier", "admin"), ("web", "app")),
            ModelSpec("core.CoffeeParticipant", "Teilnahme mit Zeitraum und E-Mail-Wunsch", ("self", "cashier", "admin"), ("cashier", "admin", "self"), ("web", "email")),
            ModelSpec("core.CoffeeCashMovement", "Kassenbewegung und Kassensturz mit Person", C, ("cashier",) + C, ("web", "export"), "evidence", evidence=True,
                      note="Append-only. Einkäufe können alle Inhaltsrollen erfassen."),
        ),
    ),
    ModuleSpec(
        "aufgaben", "Tagesaufgaben",
        "Wiederkehrende Aufgaben der Wache mit Erledigt-Vermerk.",
        flag="tasks_enabled", web_prefixes=("/aufgaben/",), entry_url="tasks_today",
        evaluations=(
            EvaluationSpec("tasks_today", "Tagesansicht mit Vorname der erledigenden Person und Uhrzeit", C + ("terminal",), True),
            EvaluationSpec("tasks_week", "Wochenansicht mit erledigender Person", C + ("terminal",), True),
        ),
        models=(
            ModelSpec("core.StationTask", "Aufgabe mit Wiederholung", C + ("terminal", "display"), CS, ("web", "terminal", "display")),
            ModelSpec("core.StationTaskCompletion", "Erledigt-Vermerk: Person, Tag, Uhrzeit, Notiz", C + ("terminal", "display"), C + ("terminal",), ("web", "terminal", "display"), "task_reopen",
                      note="Kein Nachweis. Display: nur Zählwerte. Am Wachenterminal erledigte Aufgaben tragen das Dienstkonto, keine Person."),
        ),
    ),
    ModuleSpec(
        "checklisten", "Checklisten und Prüfintervalle",
        "Checklisten mit Abschluss und Fälligkeit.",
        flag="checklists_enabled", web_prefixes=("/checklisten/",), entry_url="checklists",
        evaluations=(
            EvaluationSpec("checklists", "Letzter Abschluss je Checkliste mit Vorname und Zeit", C + ("terminal",), True),
            EvaluationSpec("api_v1_checklisten", "Letzter Abschluss je Checkliste mit vollem Namen und Zeit (App)", C, True),
        ),
        models=(
            ModelSpec("core.Checklist", "Checkliste mit Beschreibung", C + ("terminal",), ("superuser",), ("web", "app", "terminal"),
                      note="Anlegen und Bearbeiten nur im Django-Admin; Web und App zeigen Checklisten nur an."),
            ModelSpec("core.ChecklistItem", "Punkte einer Checkliste", C + ("terminal",), ("superuser",), ("web", "app", "terminal"),
                      note="Anlegen und Bearbeiten nur im Django-Admin."),
            ModelSpec("core.ChecklistCompletion", "Abschluss: Person, Zeit, Notiz", C + ("terminal",), C + ("terminal",), ("web", "app", "terminal"), "evidence", evidence=True,
                      note="Append-only."),
            ModelSpec("core.ChecklistSchedule", "Prüfintervall und nächste Fälligkeit", C + ("terminal",), CS, ("web", "app", "terminal"),
                      note="Die Seite /checklisten/intervalle/ hängt nicht am Modulschalter."),
        ),
    ),
    ModuleSpec(
        "lage", "Meldungen, Verkehr und Wetter",
        "Öffentliche Meldungen aus eingetragenen Quellen.",
        flag="feeds_enabled", web_prefixes=("/lage/",), entry_url="feeds",
        models=(
            ModelSpec("core.FeedSource", "Quelle: Name, Adresse, Abrufstatus", C, ("superuser",), ("web",), "config"),
            ModelSpec("core.FeedItem", "Meldung aus einer Quelle", C, ("system",), ("web",), "feed"),
        ),
    ),
    ModuleSpec(
        "pinnwand", "Pinnwand",
        "Aushänge der Wache.",
        flag="pinboard_enabled", web_prefixes=("/pinnwand/",), entry_url="pinboard",
        models=(
            ModelSpec("core.PinboardNote", "Aushang: Titel, Text, Kategorie, Autor", C + ("terminal", "display"), C + ("terminal",), ("web", "app", "terminal", "display"), "gap",
                      note="Anpinnen: Schichtleitung und Master-Admin. Archivierte Aushänge bleiben gespeichert. Display: nur Titel angepinnter Aushänge."),
            ModelSpec("core.PinboardAttachment", "Anhänge (Bild oder PDF)", C + ("terminal",), C + ("terminal",), ("web", "terminal"), "attachment", evidence=True),
        ),
    ),
    ModuleSpec(
        "chat", "Wachenchat, Privatnachrichten und Post (E2EE)",
        "Nachrichten unter Kolleginnen und Kollegen, Ende-zu-Ende-verschlüsselt (docs/SECURITY-PRIVACY.md).",
        flag="chat_enabled", web_prefixes=("/chat/", "/post/", "/konto/crypto/"), entry_url="chat",
        note="Der Server speichert verschlüsselte Inhalte; der ausgelieferte Webclient und der Server bleiben Teil des Vertrauensmodells. "
             "Für die Empfängerauswahl sehen alle Inhaltsrollen die Mitglieder der Wache mit Namen.",
        models=(
            ModelSpec("core.UserCryptoIdentity", "Schlüsselpaar (privater Schlüssel nur verschlüsselt)", ("self",) + C, ("self",), ("web", "app"), "account",
                      note="Den öffentlichen Schlüssel sehen Inhaltsrollen derselben Wache."),
            ModelSpec("core.ChatMessage", "Wachenchat-Nachricht (verschlüsselt, Autor, Zeit)", C, C, ("web", "app"), "gap",
                      note="Ausblenden: Schichtleitung und Master-Admin."),
            ModelSpec("core.PrivateConversation", "Privater Verlauf zwischen zwei Personen", ("self",), ("self",), ("web", "app"), "gap"),
            ModelSpec("core.PrivateMessage", "Privatnachricht (verschlüsselt)", ("self",), ("self",), ("web", "app"), "gap"),
            ModelSpec("core.SecureMail", "Post (verschlüsselt) mit Absender", ("self",), C, ("web", "app"), "gap"),
            ModelSpec("core.SecureMailRecipient", "Empfänger und Lesezeit", ("self",), ("system",), ("web", "app"), "gap"),
            ModelSpec("core.ChatGroup", "Gruppe: Name und anlegende Person", ("self",), C, ("web", "app"), "gap"),
            ModelSpec("core.ChatGroupMember", "Gruppenmitglieder", ("self",), C, ("web", "app"), "gap"),
            ModelSpec("core.GroupMessage", "Gruppennachricht (verschlüsselt)", ("self",), ("self",), ("web", "app"), "gap"),
        ),
    ),
    ModuleSpec(
        "benachrichtigungen", "Benachrichtigungen und Push",
        "Hinweise im Posteingang, Push an Browser und App.",
        web_prefixes=("/benachrichtigungen/", "/hinweise/"), entry_url="push_settings",
        models=(
            ModelSpec("core.UserNotification", "Persönlicher Hinweis: Titel, Text, Link, gelesen", ("self",), ("system",), ("web", "app", "push"), "gap"),
            ModelSpec("core.MobilePushDevice", "App-Gerät für Push (Plattform, Geräte-Token, App-Version)", ("self",), ("self",), ("app",), "device_unregister"),
            ModelSpec("core.PushSubscription", "Browser-Push-Abo (Adresse beim Browserhersteller, Schlüssel, Browser)", ("self",), ("self",), ("web",), "device_unregister"),
            ModelSpec("core.PushOutbox", "Warteschlange für Push-Nachrichten", ("system",), ("system",), ("push",), "push_outbox"),
        ),
    ),
    ModuleSpec(
        "signal", "Signal-Benachrichtigungen",
        "Erinnerungen über Signal an Personen, die ihre Nummer selbst bestätigt haben (docs/SIGNAL.md).",
        gate="signal", web_prefixes=("/konto/signal/", "/einstellungen/signal/"), entry_url="signal_account",
        models=(
            ModelSpec("core.SignalContact", "Signal-Nummer mit Bestätigung", ("self",), ("self",), ("web",), "withdrawal"),
            ModelSpec("core.SignalOutbox", "Warteschlange: Empfänger und Nachrichtentext", ("superuser",), ("system",), ("signal",), "signal_outbox"),
        ),
    ),
    ModuleSpec(
        "mpg", "Medizinprodukte (MPBetreibV)",
        "Bestandsverzeichnis, Prüffristen, Funktionskontrollen und Einweisungen.",
        flag="mpg_enabled", web_prefixes=("/mpg/",), entry_url="mpg_dashboard",
        evaluations=(
            EvaluationSpec("mpg_dashboard", "Letzte Prüfungen und Funktionskontrollen mit Namen", C, True),
            EvaluationSpec("mpg_device_detail", "Einweisungen und Kontrollen eines Geräts mit Namen", C, True),
            EvaluationSpec("mpg_geraetepass", "Einweisungsmatrix aller Mitglieder mit Quote je Person", C, True,
                           "für alle Inhaltsrollen sichtbar"),
            EvaluationSpec("mpg_export_bestandsverzeichnis", "Bestandsverzeichnis als CSV (ohne Personen)", C, False),
        ),
        models=(
            ModelSpec("core.MedicalDevice", "Medizingerät mit Fristen und Status", C + ("display",), CS + ("system",), ("web", "display", "export"),
                      note="Stammdaten, Bearbeitung möglich. Anlegen, Bearbeiten und Freigabe: Schichtleitung und Master-Admin. "
                           "Den Status ändern alle Inhaltsrollen über Funktionskontrollen und Mängelmeldungen; Prüfungen setzen die Fristen neu."),
            ModelSpec("core.MaintenanceLog", "STK/MTK/DGUV-Prüfung mit prüfender Stelle", C, CS, ("web",), "evidence", evidence=True),
            ModelSpec("core.DeviceTrainingRecord", "Einweisung: Person, einweisende Person, Datum", C, CS, ("web",), "training_replace", evidence=True),
            ModelSpec("core.DeviceRoutineCheck", "Funktionskontrolle mit Person und Ergebnis", C, C, ("web",), "evidence", evidence=True),
        ),
    ),
    ModuleSpec(
        "lager", "Lager und Material",
        "Artikel, Chargen, Bestände und Bewegungen (FEFO, Kühlware, Rückruf).",
        flag="warehouse_enabled", web_prefixes=("/lager/",), entry_url="warehouse_dashboard",
        evaluations=(
            EvaluationSpec("warehouse_dashboard", "Letzte Bewegungen mit Namen", C, True),
            EvaluationSpec("warehouse_item_detail", "Bewegungen eines Artikels mit Namen", C, True),
            EvaluationSpec("warehouse_export_fefo", "Verfallsliste als CSV (ohne Personen)", C, False),
            EvaluationSpec("warehouse_reorder_proposal", "Nachbestellvorschlag (ohne Personen)", C, False),
        ),
        models=(
            ModelSpec("core.StorageLocation", "Lagerort", C, ("system",), ("web",),
                      note="Die Standardlagerorte legt Wachwerk beim ersten Aufruf des Lagers an; eine Oberfläche für weitere Lagerorte gibt es nicht."),
            ModelSpec("core.MedicalItem", "Artikel mit Mindestbestand", C + ("display",), CS, ("web", "display")),
            ModelSpec("core.ItemBatch", "Charge mit Verfall und Rückruf", C + ("display",), C, ("web", "display", "export"),
                      note="Stammdaten der Charge; Rückruf und Entnahme aus der Kühlung ändern sie. Die Bewegungen stehen in core.StockMovement."),
            ModelSpec("core.StockItem", "Bestand je Lagerort", C + ("display",), C, ("web", "display"),
                      note="Display: nur Summe für den Mindestbestand."),
            ModelSpec("core.StockMovement", "Bewegung: Menge, Art, Person", C, C, ("web",), "evidence", evidence=True,
                      note="Append-only. Nur Bestand, kein Verbrauch je Einsatz."),
        ),
    ),
    ModuleSpec(
        "fuhrpark", "Fuhrpark",
        "Fahrzeuge, Fristen, Übernahme und Desinfektion.",
        flag="fleet_enabled", web_prefixes=("/fuhrpark/",), entry_url="fleet_dashboard",
        evaluations=(
            EvaluationSpec("fleet_dashboard", "Letzte Desinfektionen mit Namen", C, True),
            EvaluationSpec("fleet_vehicle_detail", "Übernahmen und Desinfektionen eines Fahrzeugs mit Namen", C, True),
            EvaluationSpec("fleet_export_csv", "Fahrzeugliste als CSV (ohne Personen)", C, False),
        ),
        models=(
            ModelSpec("core.Vehicle", "Fahrzeug mit Zustand, Füllständen und Fristen", C + ("display",), CS, ("web", "app", "display", "export"),
                      note="Stammdaten, Bearbeitung möglich. Anlegen und Bearbeiten: Schichtleitung und Master-Admin. "
                           "Status, Kilometerstand und Füllstände ändern alle Inhaltsrollen über Statuswechsel, Übernahme, Desinfektion und Mängelmeldung."),
            ModelSpec("core.DisinfectantMaster", "Desinfektionsmittel", C, ("system", "superuser"), ("web",), "config",
                      note="Das Standardmittel legt Wachwerk beim ersten Aufruf des Fuhrparks an; weitere Mittel nur im Django-Admin."),
            ModelSpec("core.DisinfectionProtocol", "Desinfektion: Fahrzeug, Mittel, Person, Beginn, Einwirkzeit", C, C, ("web",), "evidence", evidence=True),
            ModelSpec("core.VehicleHandover", "Fahrzeugübernahme: Person, Kilometerstand, Füllstände, Prüfpunkte", C, C, ("web",), "evidence", evidence=True),
        ),
    ),
    ModuleSpec(
        "orga", "Dienstanweisungen und Telefonbuch",
        "Dienstanweisungen mit Version und Lesequittung, Telefonbuch der Wache.",
        flag="orga_enabled", web_prefixes=("/orga/",), entry_url="orga_dashboard",
        evaluations=(
            EvaluationSpec("sop_detail", "Quittierungsliste einer Dienstanweisung mit Namen", CS, True),
            EvaluationSpec("sop_export_audit", "Quittierungsnachweis als CSV mit Namen", CS, True),
        ),
        models=(
            ModelSpec("core.SOPDocument", "Dienstanweisung: Nummer, Titel, Status, Fristen", C, CS, ("web",),
                      note="Stammdaten, Bearbeitung möglich; die Texte stehen versioniert in core.SOPRevision."),
            ModelSpec("core.SOPRevision", "Version mit Text, Prüfsumme und Freigabe", C, CS, ("web",), "evidence", evidence=True),
            ModelSpec("core.SOPReceipt", "Lesequittung: Person, Version, Zeit", ("self",) + CS, ("self",), ("web", "export"), "evidence", evidence=True,
                      note="Mitglieder sehen nur ihren eigenen Stand."),
            ModelSpec("core.StationContact", "Telefonbuch: Einrichtung, Ansprechperson, Nummern", C, CS, ("web",)),
        ),
    ),
    ModuleSpec(
        "display", "Wachen-Display",
        "Anzeige für einen Monitor in der Wache über einen Display-Link.",
        flag="display_enabled", web_prefixes=("/display/", "/einstellungen/display/"), entry_url="display_tokens",
        models=(
            ModelSpec("core.DisplayToken", "Display-Link (nur Hash) mit Anzeigeauswahl", ("admin",), ("admin",), ("web",), "token"),
        ),
    ),
    ModuleSpec(
        "terminal", "Wachenterminal",
        "Gemeinsames Touch-Gerät an der Wache mit Wachen-Code (docs/PI-WACHENTERMINAL.md).",
        gate="terminal", web_prefixes=("/terminal/", "/team/terminal/"), entry_url="terminal_admin",
        models=(
            ModelSpec("core.StationTerminal", "Registriertes Terminal (nur Hash), Fehlversuche, letzte Nutzung", ("admin",), ("admin", "system"), ("web", "terminal"), "token"),
            ModelSpec("core.StationTerminalCode", "Wachen-Code (nur Hash) und Dienstkonto", ("admin",), ("admin",), ("web",), "config"),
            ModelSpec("core.TerminalPairing", "Einmaliger Code zum Koppeln eines Handys", ("system",), ("self", "system"), ("web", "app"), "terminal_pairing"),
        ),
    ),
    ModuleSpec(
        "demo", "Öffentliche Demo",
        "Zeitlich begrenzte Demo-Wache je Besuch.",
        gate="demo_sandbox", web_prefixes=("/demo/", "/demo-einstieg/"),
        models=(
            ModelSpec("core.DemoSandbox", "Demo-Besuch mit eigener Demo-Wache", ("system",), ("system",), (), "demo"),
            ModelSpec("core.DemoDailyStat", "Tageszähler der Demo ohne Personenbezug", ("superuser",), ("system",), (), "technical"),
        ),
    ),
    ModuleSpec(
        "feedback", "Rückmeldungen",
        "Rückmeldungen über ein öffentliches Formular, Name und E-Mail freiwillig.",
        gate="feedback", web_prefixes=("/feedback/", "/einstellungen/feedback/"), entry_url="feedback_inbox",
        models=(
            ModelSpec("core.Feedback", "Rückmeldung mit Text, Bewertung, freiwillig Name und E-Mail", ("admin",), ("public", "admin"), ("public", "web"), "feedback",
                      note="Lesen nur der Master-Admin der Betreiber-Wache."),
        ),
    ),
)

# ---- Feldebene --------------------------------------------------------------

FIELD_OVERRIDES = {
    "core.MaintenanceLog.performed_by": ("Kontakt/Name", "Name der prüfenden Person oder Firma als Text"),
    "core.DeviceTrainingRecord.instructor": ("Kontakt/Name", "Name der einweisenden Person als Text"),
    "core.StationContact.name": ("Kontakt/Name", "Einrichtung oder Person"),
    "core.StationContact.contact_person": ("Kontakt/Name", ""),
    "core.CoffeeFund.account_holder": ("Kontakt/Name", ""),
    "core.Feedback.name": ("Kontakt/Name", "freiwillig"),
    "core.SiteProfile.represented_by": ("Kontakt/Name", "öffentlich im Impressum"),
    "core.SiteProfile.content_responsible": ("Kontakt/Name", "öffentlich im Impressum"),
    "core.SignalContact.number": ("Kontakt/Name", "Telefonnummer, erst nach Bestätigung genutzt"),
    "core.SignalOutbox.recipient": ("Kontakt/Name", "Telefonnummer oder Gruppen-ID"),
    "core.SOPReceipt.ip_address": (None, "seit 0.26.1 nicht mehr befüllt; Altwerte entfernt der einmalige Bereinigungsbefehl (Paket C, D1); Sicherungen behalten sie bis zum Ablauf"),
    "core.SOPReceipt.user_agent": (None, "seit 0.26.1 nicht mehr befüllt; Altwerte entfernt der einmalige Bereinigungsbefehl (Paket C, D1); Sicherungen behalten sie bis zum Ablauf"),
    "core.AuditEvent.metadata": ("strukturierte Angaben", "Feldnamen, Statuswerte, vereinzelt Benutzernamen; keine fachlichen Freitexte"),
    "core.SOPRevision.content_hash": ("Wert", "SHA-256 des Dokumenttexts, kein Geheimnis"),
    "core.WebAuthnCredential.credential_id": ("Kennung", "Kennung des Passkeys, kein Geheimnis"),
    "core.ApiToken.token_prefix": ("Kennung", "erste Zeichen zur Wiedererkennung, kein Geheimnis"),
    "core.DataProtectionOfficer.postal_address": ("Kontakt/Name", ""),
    "core.SiteProfile.operator_name": ("Kontakt/Name", "öffentlich im Impressum; bei Einzelpersonen ein Name"),
    "core.BirthdayPreference.day": ("persönliche Angabe", "freiwillig, nur mit Einwilligung"),
    "core.BirthdayPreference.month": ("persönliche Angabe", "freiwillig, nur mit Einwilligung"),
    "core.PushSubscription.endpoint": ("Netzwerk/Gerät", "Push-Adresse beim Browserhersteller"),
    "core.PushSubscription.p256dh": ("Geheimnis/Prüfwert", "Schlüssel des Push-Abos"),
    "core.PushSubscription.auth": ("Geheimnis/Prüfwert", "Schlüssel des Push-Abos"),
    "core.QrLoginRequest.origin": ("Netzwerk/Gerät", "Adresse des anfragenden Browsers"),
    "core.MobilePushDevice.token": ("Geheimnis/Prüfwert", "Geräte-Token für Apple oder Google"),
    "core.UserProfile.avatar": (None, "für Inhaltsrollen und am Wachenterminal sichtbar"),
    "core.ChatMessage.body": ("Freitext", "nur bei unverschlüsselten Altnachrichten; neue Nachrichten stehen verschlüsselt in ciphertext"),
    "core.Station.iban": ("Kontakt/Name", "Zahlungsangabe der Kaffeekasse"),
    "core.Station.bic": ("Wert", "Zahlungsangabe der Kaffeekasse"),
    "core.Station.latitude": ("Wert", "auf 4 Nachkommastellen gerundet, Standort der Wache"),
    "core.Station.longitude": ("Wert", "auf 4 Nachkommastellen gerundet, Standort der Wache"),
    "axes.AccessAttempt.http_accept": ("Netzwerk/Gerät", ""),
    "axes.AccessAttempt.path_info": ("Wert", "aufgerufene Anmeldeadresse"),
    "axes.AccessAttempt.get_data": ("Freitext", "Abfrageparameter des Anmeldeversuchs"),
    "axes.AccessAttempt.post_data": ("Freitext", "Formulardaten des Anmeldeversuchs ohne Passwort"),
    "axes.AccessLog.http_accept": ("Netzwerk/Gerät", ""),
    "axes.AccessLog.path_info": ("Wert", "aufgerufene Anmeldeadresse"),
    "axes.AccessFailureLog.http_accept": ("Netzwerk/Gerät", ""),
    "axes.AccessFailureLog.path_info": ("Wert", "aufgerufene Anmeldeadresse"),
    "admin.LogEntry.object_repr": ("Freitext", "Bezeichnung des geänderten Objekts"),
    "admin.LogEntry.change_message": ("Freitext", "Beschreibung der Änderung im Django-Admin"),
}

# Diese Felder dürfen nie als „Wert“ oder „Freitext“ erscheinen.
NAME_FIELDS = (
    "core.MaintenanceLog.performed_by",
    "core.DeviceTrainingRecord.instructor",
    "core.StationContact.contact_person",
    "core.CoffeeFund.account_holder",
    "core.Feedback.name",
    "core.SiteProfile.represented_by",
    "core.SiteProfile.content_responsible",
    "core.SignalContact.number",
    "core.SignalOutbox.recipient",
)

PERSON_KINDS = ("Person (Konto)", "Kontakt/Name", "Netzwerk/Gerät", "persönliche Angabe")

_ENCRYPTED_RE = re.compile(r"cipher|nonce|encrypt|wrap")
_SECRET_RE = re.compile(r"password|secret|token|_hash$|^session_key$|^session_data$|fingerprint|salt")
_NAME_RE = re.compile(r"^(first_name|last_name|username|display_name)$|^phone|_phone$")


def field_label(model, f) -> str:
    return f"{model._meta.label}.{f.name}"


def classify_field(f) -> str:
    from django.contrib.auth import get_user_model
    from django.db import models

    name = f.name
    if isinstance(f, models.BooleanField):
        return "Wert"
    if isinstance(f, models.GenericIPAddressField) or name == "user_agent":
        return "Netzwerk/Gerät"
    if name in ("public_key", "public_jwk"):
        return "Schlüssel (öffentlich)"
    if _SECRET_RE.search(name):
        return "Geheimnis/Prüfwert"
    if _ENCRYPTED_RE.search(name):
        return "verschlüsselt"
    if f.is_relation and f.related_model is get_user_model():
        return "Person (Konto)"
    if isinstance(f, models.BinaryField):
        return "Datei/Bild"
    if isinstance(f, models.JSONField):
        return "strukturierte Angaben"
    if isinstance(f, models.EmailField) or _NAME_RE.search(name):
        return "Kontakt/Name"
    if isinstance(f, models.URLField):
        return "Link"
    if isinstance(f, models.TextField) or (
        isinstance(f, models.CharField) and not f.choices and (f.max_length or 0) >= 120
    ):
        return "Freitext"
    if isinstance(f, (models.DateField, models.DateTimeField)):
        return "Zeitpunkt"
    if f.choices:
        return "Auswahl"
    if f.is_relation:
        return "Verweis"
    return "Wert"


def model_fields(model):
    return list(model._meta.concrete_fields) + list(model._meta.many_to_many)


def field_kind(model, f) -> tuple[str, str]:
    kind, note = FIELD_OVERRIDES.get(field_label(model, f), (None, ""))
    return kind or classify_field(f), note


def _verbose(model, f) -> str:
    """Nur ausdrücklich gesetzte Bezeichnungen eigener Modelle (Snapshot bleibt bei Django-Updates stabil)."""
    if model._meta.app_label != "core":
        return ""
    text = str(f.verbose_name)
    return "" if text == f.name.replace("_", " ") or text == "ID" else text


# ---- Prüfbare Konstanten ----------------------------------------------------

STATION_FLAGS_WITHOUT_OWN_DATA = ("holidays_enabled", "weather_enabled", "traffic_enabled", "traffic_local_sources")

# Daten, die die Display-Ansicht selbst liest (Name der Wache in der Kopfzeile).
DISPLAY_VIEW_MODELS = ("core.Station",)

# Tabellen mit Zeilenschutz: save() verweigert Änderungen, delete() das Löschen
# („dürfen nicht verändert/gelöscht werden“). Korrektur nur als neuer Eintrag.
# Prüft core/test_data_catalog.py gegen die Modelle.
ROW_APPEND_ONLY = (
    "core.AssetEvent",
    "core.AuditEvent",
    "core.ChecklistCompletion",
    "core.CoffeeCashMovement",
    "core.CoffeeEntry",
    "core.DefectAttachment",
    "core.DefectEvent",
    "core.HandoverAck",
    "core.HandoverAttachment",
    "core.HandoverRevision",
    "core.InventoryEvent",
    "core.NewsAttachment",
    "core.PinboardAttachment",
    "core.StockMovement",
    "core.WikiRevision",
)

# Tabellen, die die Datenbankrolle der App nicht ändern oder löschen darf
# (REVOKE UPDATE, DELETE in core/management/commands/grant_database_access.py).
DB_APPEND_ONLY = (
    "core.AuditEvent",
    "core.ChecklistCompletion",
    "core.CoffeeCashMovement",
    "core.CoffeeEntry",
    "core.HandoverRevision",
    "core.StockMovement",
)

_FORBIDDEN_TOKENS = (
    "patient", "patienten", "diagnose", "diagnosis", "mission", "einsatz", "alarmierung", "dispatch",
    "disposition", "pathogen", "erreger", "infection", "infektion", "disease", "krankheit", "symptom",
    "triage", "vital", "vitals",
)
FORBIDDEN_FIELD_NAME_RE = re.compile(r"(?:^|_)(?:" + "|".join(_FORBIDDEN_TOKENS) + r")(?:_|$)")

EVALUATION_URL_RE = re.compile(r"export|csv|report|auswertung|geraetepass|audit_log|_ics$|druck|print")

# Treffer von EVALUATION_URL_RE, die keine Auswertung sind.
NOT_EVALUATIONS = {
    "fleet_vehicle_defect_report": "Formular zum Melden eines Mangels am Fahrzeug, keine Auswertung",
}

# Seiten, die andere Personen namentlich auflisten. Jede muss im Katalog als
# Auswertung mit Personenbezug stehen.
PERSON_LIST_VIEWS = (
    "handover_detail", "api_v1_handover_acks", "sop_detail", "sop_export_audit",
    "coffee_book", "coffee_ledger", "coffee_participants", "coffee_export", "api_v1_kaffeekasse",
    "tasks_today", "tasks_week", "checklists", "api_v1_checklisten", "birthdays", "team", "team_invites", "audit_log",
    "assets_inventory_web", "api_v1_inventory", "wiki_detail",
    "defects_web", "defect_detail_web", "api_v1_defects", "api_v1_defect_detail", "api_v1_defect_attachments",
    "mpg_dashboard", "mpg_device_detail", "mpg_geraetepass",
    "warehouse_dashboard", "warehouse_item_detail", "fleet_dashboard", "fleet_vehicle_detail",
)

# App-Schnittstellen, die andere Personen nennen, ohne Auswertung zu sein:
# Autorin oder Autor eines Eintrags wie in den Weblisten (siehe auth.User) und
# die Empfängerauswahl im Chat (Modulhinweis). Jede andere App-Schnittstelle
# mit Namen anderer Personen gehört in PERSON_LIST_VIEWS;
# core/test_data_catalog.py ruft dafür alle lesenden Schnittstellen auf.
API_NAMES_WITHOUT_EVALUATION = {
    "api_v1_handover_detail": "Autorin oder Autor der Übergabe, wie die Übergabe im Web",
    "api_v1_uebergabe_detail": "Autorin oder Autor der Übergabe, wie die Übergabe im Web",
    "api_v1_pinnwand": "Autorin oder Autor je Aushang, wie die Pinnwand im Web",
    "api_v1_chat_keys": "Empfängerauswahl im Chat: Mitglieder der Wache mit Namen und öffentlichem Schlüssel",
    "api_v1_chat_private": "Empfängerauswahl für Privatnachrichten: Mitglieder der Wache mit Namen",
    "api_v1_post": "Empfängerauswahl und Absender der eigenen Post",
}


# ---- Abfragen ---------------------------------------------------------------


def catalog_models():
    from django.apps import apps

    return list(apps.get_models())


def iter_model_specs():
    for module in MODULES:
        for spec in module.models:
            yield module, spec


def spec_for_label(label: str):
    for module, spec in iter_model_specs():
        if spec.label == label:
            return module, spec
    return None, None


def module_read_roles(module) -> set:
    roles = set()
    for spec in module.models:
        roles.update(spec.read)
    return roles


def module_channels(module) -> set:
    channels = set()
    for spec in module.models:
        channels.update(spec.channels)
    return channels


def module_active(module, station) -> bool:
    if module.flag and not getattr(station, module.flag, False):
        return False
    if module.gate and not GATES[module.gate][1]():
        return False
    return True


def all_evaluations():
    for module in MODULES:
        for evaluation in module.evaluations:
            yield module, evaluation


def admin_model_admin(model):
    """ModelAdmin oder Inline, über das ``model`` im Django-Admin erreichbar ist (sonst None)."""
    from django.contrib import admin

    model_admin = admin.site._registry.get(model)
    if model_admin is not None:
        return model_admin
    for parent_admin in admin.site._registry.values():
        for inline_class in parent_admin.inlines:
            if inline_class.model is model:
                return inline_class(parent_admin.model, admin.site)
    return None


def admin_access(model) -> str:
    """Rechte eines Superusers im Django-Admin, abgeleitet aus ``admin.site`` (auch Inlines)."""
    from django.contrib.auth import get_user_model
    from django.http import HttpRequest

    model_admin = admin_model_admin(model)
    if model_admin is None:
        return ""
    request = HttpRequest()
    request.user = get_user_model()(is_active=True, is_staff=True, is_superuser=True)

    def allowed(method) -> bool:
        try:
            return bool(method(request))
        except TypeError:  # Inlines verlangen ein Objekt
            return bool(method(request, None))

    rights = ["lesen"]
    if allowed(model_admin.has_add_permission):
        rights.append("anlegen")
    if allowed(model_admin.has_change_permission):
        rights.append("ändern")
    if allowed(model_admin.has_delete_permission):
        rights.append("löschen")
    return ", ".join(rights)


# ---- Markdown ---------------------------------------------------------------


def _cell(text) -> str:
    return str(text or "").replace("|", "\\|").replace("\n", " ").strip()


def _roles(roles) -> str:
    roles = list(roles)
    parts = []
    if all(role in roles for role in CONTENT):
        parts.append("Inhaltsrollen")
        roles = [role for role in roles if role not in CONTENT]
    parts.extend(ROLE_LABELS[role] for role in roles)
    return ", ".join(parts) or "–"


def _channels(model, spec) -> str:
    parts = [CHANNEL_LABELS[channel] for channel in spec.channels]
    access = admin_access(model)
    if access:
        parts.append(f"Django-Admin ({access})")
    return ", ".join(parts) or "nur intern"


def _person_marker(module) -> str:
    from django.apps import apps

    kinds = set()
    for spec in module.models:
        model = apps.get_model(spec.label)
        for f in model_fields(model):
            kinds.add(field_kind(model, f)[0])
        if spec.label == "auth.User":
            kinds.add("Person (Konto)")
    if kinds & set(PERSON_KINDS):
        return "ja"
    if "Freitext" in kinds:
        return "Freitext möglich"
    return "nein"


def _switch(module) -> str:
    if module.flag:
        return f"`Station.{module.flag}`"
    if module.gate:
        return f"Einstellung {GATES[module.gate][0]}"
    return "immer aktiv"


def _switch_state(module, station) -> str:
    state = "an" if module_active(module, station) else "aus"
    return f"{_switch(module)}: {state}" if (module.flag or module.gate) else "immer aktiv"


def evidence_text(spec) -> str:
    if not spec.evidence:
        return "nein"
    if spec.label in DB_APPEND_ONLY:
        return "ja, append-only (Anwendung und Datenbankrechte)"
    if spec.label in ROW_APPEND_ONLY:
        return "ja, append-only (Anwendung)"
    return "ja"


def deletion_guard_text(model) -> str:
    """Was mit dem Nachweis geschieht, wenn ein verknüpfter Eintrag gelöscht wird (aus ``on_delete``)."""
    from django.db import models

    relations = [f for f in model._meta.concrete_fields if f.is_relation]
    if not relations:
        return "keine Verknüpfungen"
    cascade, released = [], []
    for f in relations:
        on_delete = f.remote_field.on_delete
        if on_delete in (models.PROTECT, models.RESTRICT):
            continue
        (cascade if on_delete is models.CASCADE else released).append(f"`{f.name}`")
    if not cascade and not released:
        return "verknüpfte Einträge lassen sich nicht löschen, solange dieser Nachweis besteht (PROTECT)"
    parts = []
    if cascade:
        parts.append(f"wird mitgelöscht, wenn der verknüpfte Eintrag in {' oder '.join(cascade)} gelöscht wird (CASCADE)")
    if released:
        parts.append(f"die Verknüpfung {' und '.join(released)} wird gelöst, wenn der verknüpfte Eintrag gelöscht wird")
    return "; ".join(parts)


def _retention_text(spec, live: bool) -> str:
    rule = RETENTION_RULES[spec.retention]
    return rule.text(live=live)


def _module_retentions(module) -> str:
    seen = []
    for spec in module.models:
        title = RETENTION_RULES[spec.retention].title
        if title not in seen:
            seen.append(title)
    return ", ".join(seen)


def _anchor(module) -> str:
    return f'<a id="modul-{module.key}"></a>'


def _module_section(module, *, live: bool) -> list[str]:
    from django.apps import apps

    lines = [_anchor(module), "", f"## {module.title}", "", module.purpose, ""]
    lines.append(f"- Schalter: {_switch(module)}")
    if module.web_prefixes:
        lines.append("- Bereiche: " + ", ".join(f"`{prefix}`" for prefix in module.web_prefixes))
    if module.note:
        lines.append(f"- Hinweis: {module.note}")
    lines.append("")
    if module.evaluations:
        lines += [
            "**Auswertungen und Personenlisten**",
            "",
            "| Ausgabe | URL-Name | Rollen | Personenbezug | Hinweis |",
            "| --- | --- | --- | --- | --- |",
        ]
        for evaluation in module.evaluations:
            lines.append(
                f"| {_cell(evaluation.title)} | `{evaluation.url_name}` | {_cell(_roles(evaluation.roles))} | "
                f"{'**ja**' if evaluation.person_related else 'nein'} | {_cell(evaluation.note)} |"
            )
        lines.append("")
    for spec in sorted(module.models, key=lambda item: item.label):
        model = apps.get_model(spec.label)
        lines += [f"### {spec.label}", "", spec.purpose, ""]
        lines.append(f"- Lesen: {_roles(spec.read)}")
        lines.append(f"- Schreiben: {_roles(spec.write)}")
        lines.append(f"- Zugriffswege: {_channels(model, spec)}")
        lines.append(f"- Nachweis: {evidence_text(spec)}")
        if spec.evidence:
            lines.append(f"- Löschschutz: {deletion_guard_text(model)}")
        lines.append(f"- Frist technisch: {_retention_text(spec, live)}")
        if spec.retention != "technical":
            lines.append(f"- Frist festgelegt: {PERIOD_DECISION_TEXT}")
        if spec.note:
            lines.append(f"- Hinweis: {spec.note}")
        lines += ["", "| Feld | Bezeichnung | Art | Hinweis |", "| --- | --- | --- | --- |"]
        for f in model_fields(model):
            kind, note = field_kind(model, f)
            lines.append(f"| `{f.name}` | {_cell(_verbose(model, f))} | {kind} | {_cell(note)} |")
        lines.append("")
    return lines


def _device_section() -> list[str]:
    from core.display_views import COOKIE_NAME as DISPLAY_COOKIE
    from core.terminal import COOKIE_NAME as TERMINAL_COOKIE

    language_days = int(getattr(settings, "LANGUAGE_COOKIE_AGE", 0) or 0) // 86400
    csrf_days = int(getattr(settings, "CSRF_COOKIE_AGE", 0) or 0) // 86400
    session_hours = _session_hours()
    rows = (
        (f"`{settings.SESSION_COOKIE_NAME}`", "Cookie, HttpOnly", f"Anmeldung; {session_hours} Stunden"),
        (f"`{settings.CSRF_COOKIE_NAME}`", "Cookie, HttpOnly", f"Schutz vor gefälschten Formularen; {csrf_days} Tage"),
        (f"`{settings.LANGUAGE_COOKIE_NAME}`", "Cookie, HttpOnly",
         f"gewählte Sprache; {language_days} Tage; gesetzt beim Sprachwechsel und bei der Anmeldung, wenn im Profil eine Sprache hinterlegt ist"),
        ("`wb_theme`", "Cookie, per JavaScript lesbar", "helle oder dunkle Darstellung; 365 Tage"),
        (f"`{TERMINAL_COOKIE}`", "Cookie, HttpOnly", "Gerätegeheimnis eines registrierten Wachenterminals; 5 Jahre; nur auf Terminals"),
        (f"`{DISPLAY_COOKIE}`", "Cookie, HttpOnly", "Display-Link; 365 Tage; nur auf Display-Geräten"),
        ("`rwsth-installed`, `rwsth-install-dismissed`", "localStorage", "Hinweis zur Installation als App ausgeblendet"),
        ("privater Chat-Schlüssel", "sessionStorage", "nur während der Sitzung im Browser, nur bei eingeschaltetem Chat"),
        ("Service Worker", "Browser-Cache",
         "Programmdateien, Offline-Seite und zuletzt aufgerufene Seiten für die Anzeige ohne Netz; Abmelden leert den Cache; auf Wachenterminals gesperrt"),
        ("App", "Gerät", "App-Token im sicheren Speicher; Lesecache ab App 1.1 laut docs/CLIENT-OFFLINE-CONTRACT.md"),
    )
    lines = [
        "## Daten auf Endgeräten",
        "",
        "| Name | Art | Zweck und Dauer |",
        "| --- | --- | --- |",
    ]
    lines += [f"| {name} | {kind} | {_cell(purpose)} |" for name, kind, purpose in rows]
    lines.append("")
    return lines


def _outside_section() -> list[str]:
    return [
        "## Außerhalb der Datenbank",
        "",
        "| Ort | Inhalt | Frist |",
        "| --- | --- | --- |",
        "| Sicherungen (Backup-Volume, `./backups`) | vollständige Datenbank | 7 Tage (BACKUP_RETENTION_DAYS in scripts/backup-loop.sh) |",
        "| Docker-Protokolle | Ausgaben der Dienste, darunter das Zugriffsprotokoll von Gunicorn mit Absenderadresse, Pfad und Browserkennung; Aktivierungslinks geschwärzt (core/gunicorn_logging.py) | nur Größe: 3 × 10 MB je Dienst (docker-compose.yml), keine Zeitgrenze |",
        "| Proxy-Protokolle (Caddy oder eigener Proxy) | Zugriffe mit IP-Adresse | laut Betreiber |",
        "| Offsite-Kopie | verschlüsselte Sicherung | laut Betreiber (docs/OPERATIONS.md) |",
        "",
        "Externe Dienste und Datenflüsse an Dritte: docs/DATENFLUESSE.md.",
        "",
    ]


def _legend() -> list[str]:
    lines = ["## Rollen", "", "| Rolle | Bedeutung |", "| --- | --- |"]
    lines += [f"| {name} | {_cell(text)} |" for name, text in ROLE_LEGEND]
    lines += ["", "## Zugriffswege", "", "| Weg | Bedeutung |", "| --- | --- |"]
    lines += [f"| {name} | {_cell(text)} |" for name, text in CHANNEL_LEGEND]
    lines += [
        "",
        "## Arten von Feldern",
        "",
        "Die Art leitet sich aus dem Datenmodell ab. „Person (Konto)“ ist ein Verweis auf ein Benutzerkonto; "
        "„Kontakt/Name“ sind Namen, Telefonnummern, Bankverbindungen oder E-Mail-Adressen als Text; "
        "„persönliche Angabe“ sind weitere freiwillige Angaben zu einer Person; „Freitext“ kann alles enthalten, "
        "was Menschen eintippen; „Netzwerk/Gerät“ sind IP-Adressen, Browserkennungen oder Geräteadressen; "
        "„Geheimnis/Prüfwert“ sind Hashes und Schlüssel, die niemand im Klartext liest. "
        "Auswahlfelder werden ohne ihre Werte aufgeführt. Die Spalte Bezeichnung zeigt nur ausdrücklich gesetzte "
        "Bezeichnungen.",
        "",
        "## Nachweis und Löschschutz",
        "",
        "„Nachweis: ja“ heißt: Die Tabelle belegt, wer wann was getan, geprüft oder quittiert hat. Wie lange sie bleibt "
        "und ob Wachwerk selbst etwas löscht, steht in „Frist technisch“. „append-only (Anwendung)“: Wachwerk verweigert "
        "jede Änderung und jedes Löschen einer Zeile, Korrekturen sind neue Einträge. „und Datenbankrechte“: zusätzlich "
        "darf die Datenbankrolle der App die Tabelle weder ändern noch löschen (PostgreSQL nach `grant_database_access`). "
        "„Löschschutz“ sagt, was mit dem Nachweis geschieht, wenn ein verknüpfter Eintrag gelöscht wird, etwa ein Gerät "
        "im Django-Admin.",
        "",
    ]
    return lines


def _overview(modules, station=None) -> list[str]:
    lines = [
        "## Übersicht",
        "",
        "| Modul | Schalter | Personenbezug | Auswertungen mit Personenbezug | Fristen |",
        "| --- | --- | --- | --- | --- |",
    ]
    for module in modules:
        person_evals = sum(1 for evaluation in module.evaluations if evaluation.person_related)
        switch = _switch_state(module, station) if station is not None else _switch(module)
        lines.append(
            f"| [{module.title}](#modul-{module.key}) | {_cell(switch)} | {_person_marker(module)} | "
            f"{person_evals} | {_cell(_module_retentions(module))} |"
        )
    lines.append("")
    return lines


def reference_markdown() -> str:
    """Referenzkatalog aller Module mit Standardfristen (deterministisch, ohne Datum)."""
    from django.utils import translation

    with translation.override("de"):
        lines = [
            "# Datenkatalog",
            "",
            "Erzeugt – nicht von Hand ändern. Quelle: `core/data_catalog.py`; neu erzeugen mit "
            "`python manage.py data_catalog --write`.",
            "",
            "Dieser Referenzkatalog nennt alle Module mit den Standardfristen. Für eine Wache "
            "(Anlage 1 der Vereinbarung) erzeugt der Betreiber die Fassung mit den dort aktiven Modulen "
            "und den eingestellten Fristen:",
            "",
            "```bash",
            "docker compose exec -T web python manage.py data_catalog --station auto > datenkatalog.md",
            "```",
            "",
            "Die Fristen in diesem Katalog sind die technisch umgesetzten. Verbindliche Fristen legt das "
            "Löschkonzept fest (docs/LOESCHKONZEPT.md); dort steht auch der Vorschlag für den Pilot.",
            "",
        ]
        lines += _overview(MODULES)
        lines += _legend()
        for module in MODULES:
            lines += _module_section(module, live=False)
        lines += _device_section()
        lines += _outside_section()
    return "\n".join(lines).rstrip() + "\n"


def station_markdown(station) -> str:
    """Katalog einer Wache: nur aktive Module, eingestellte Fristen, keine Inhalte."""
    from django.utils import timezone, translation

    with translation.override("de"):
        modules = [module for module in MODULES if module_active(module, station)]
        others = [flag for flag in STATION_FLAGS_WITHOUT_OWN_DATA if getattr(station, flag, False)]
        lines = [
            f"# Datenkatalog – {station.name}",
            "",
            f"Stand: {timezone.localdate().strftime('%d.%m.%Y')} · Wachwerk {getattr(settings, 'APP_VERSION', '')}",
            "",
            "Erzeugt mit `python manage.py data_catalog --station`. Der Katalog enthält nur Metadaten und "
            "Einstellungen, keine Inhalte. Aufgeführt sind die Module, die in dieser Wache eingeschaltet sind, "
            "mit den eingestellten technischen Fristen. Verbindliche Fristen legt das freigegebene "
            "Löschkonzept fest (Anlage 3 der Vereinbarung).",
            "",
        ]
        if others:
            lines += [
                "Weitere eingeschaltete Funktionen ohne eigene Tabellen: "
                + ", ".join(f"`{flag}`" for flag in others)
                + " (Datenflüsse siehe docs/DATENFLUESSE.md).",
                "",
            ]
        lines += _overview(modules, station)
        lines += _legend()
        for module in modules:
            lines += _module_section(module, live=True)
        lines += _device_section()
        lines += _outside_section()
    return "\n".join(lines).rstrip() + "\n"
