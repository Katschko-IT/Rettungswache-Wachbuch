"""Zustand der Host-Überwachung (``wachwerk-health``) in Wachwerk.

Vertrauensgrenze: Der Host (root) schreibt ``status.json`` (Schema 1) in einen
Ordner, den Compose nur lesend in ``web`` und ``notify-worker`` einbindet
(``/run/wachwerk-health``, siehe ``WACHWERK_HEALTH_DIR``). Die Datei enthält
nur Codes, Zeiten und Zahlen – keine Texte, Hostnamen, Pfade oder Geheimnisse.
Wachwerk liest sie streng: keine Symlinks, höchstens 64 KiB, jedes Feld wird
einzeln geprüft und bei Fehlern verworfen. Die Codes übersetzt Wachwerk selbst
(``PROBLEM_TEXTS``); unbekannte Codes erscheinen nur als allgemeiner Text, nie
im Wortlaut. Die Datei dient nur der Anzeige und den Meldungen, nie als
Auslöser für Aktionen. Der Host bekommt keine Datenbankrechte.

Sichtbar ist der Zustand nur für Master-Admins echter Wachen: nicht in der
öffentlichen Demo (gemeinsame Demo-Konten oder Demo-Wachen), nicht am
Wachenterminal und nicht auf dem Wachen-Display.

Meldungen (``notify_host_health`` im notify-worker): je Master-Admin und
Störung eine ``UserNotification`` (Art ``system_health``) im Posteingang, dazu
Web-Push, App-Relay und Signal über die vorhandenen Kanäle und eine E-Mail,
wenn SMTP eingerichtet ist (zusätzlich an ``HEALTH_ALERT_EMAIL``). Nach dem
Beheben folgt „Störung behoben“ an dieselben Personen; schweigt die
Überwachung länger als ``STALE_AFTER``, „Überwachung meldet sich nicht“.
"""
from __future__ import annotations

import json
import logging
import os
import re
import stat
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.formats import date_format
from django.utils.translation import gettext as _, gettext_lazy

logger = logging.getLogger(__name__)

DEFAULT_STATUS_FILE = "/run/wachwerk-health/status.json"
MAX_STATUS_BYTES = 64 * 1024
# Der Timer läuft alle 5 Minuten; nach 20 Minuten ohne neuen Stand schweigt
# die Überwachung (Timer aus, Host hängt, Platte voll).
STALE_AFTER = timedelta(minutes=20)
MAX_PROBLEMS = 20
MAX_MEDIA = 5
MAX_NUMBER = 10_000_000
# Ohne Änderung am Zustand fragt der notify-worker die Datenbank höchstens so
# oft (z. B. für inzwischen ernannte Master-Admins); sonst alle 30 Sekunden.
REPROCESS_AFTER_SECONDS = 15 * 60

ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
ALERT_RE = re.compile(r"\d{8}T\d{6}Z")
CODE_RE = re.compile(r"[a-z_]{1,20}")
PARAM_RE = re.compile(r"[a-z0-9-]{0,40}")
MEDIUM_RE = re.compile(r"[A-Za-z0-9 ._-]{1,30}")
SHA_RE = re.compile(r"[0-9a-f]{64}")

GENERIC_TEXT = gettext_lazy("Weitere Meldung der Überwachung.")

# (Bereich, Art) → Text; %(param)s ist der Wert aus dem Code (Zahl oder Name
# eines Dienstes). Vertrag mit deploy/hetzner/wachwerk-health.sh: jeder Code,
# den das Skript schreibt, steht hier (core/test_host_health.py prüft das).
PROBLEM_TEXTS = {
    ("update", "lock_stale"): gettext_lazy("Das automatische Update hängt oder wurde unterbrochen."),
    ("update", "never"): gettext_lazy("Das automatische Update lief noch nie."),
    ("update", "failed"): gettext_lazy("Das letzte automatische Update ist fehlgeschlagen."),
    ("update", "stale"): gettext_lazy("Das automatische Update lief zuletzt vor %(param)s Stunden."),
    ("web", "unreachable"): gettext_lazy("Wachwerk ist über die Adresse der Wache nicht erreichbar."),
    ("config", "hostname"): gettext_lazy("Der Überwachung fehlt die Adresse, die sie prüfen soll."),
    ("config", "services"): gettext_lazy(
        "Die Liste der zu prüfenden Dienste ist ungültig; geprüft wird die Grundliste."
    ),
    ("certificate", "unreadable"): gettext_lazy("Das TLS-Zertifikat ist nicht lesbar."),
    ("certificate", "expiring"): gettext_lazy("Das TLS-Zertifikat läuft in %(param)s Tagen ab."),
    ("service", "unhealthy"): gettext_lazy("Dienst „%(param)s“ reagiert nicht richtig."),
    ("service", "restart_limit"): gettext_lazy(
        "Dienst „%(param)s“ reagiert auch nach drei Neustarts in einer Stunde nicht richtig."
    ),
    ("service", "restarted"): gettext_lazy("Dienst „%(param)s“ reagierte nicht und wurde neu gestartet."),
    ("service", "restart_failed"): gettext_lazy(
        "Dienst „%(param)s“ reagiert nicht richtig; der Neustart ist fehlgeschlagen."
    ),
    ("service", "missing"): gettext_lazy("Dienst „%(param)s“ fehlt."),
    ("service", "stopped"): gettext_lazy("Dienst „%(param)s“ läuft nicht."),
    ("service", "restarting"): gettext_lazy("Dienst „%(param)s“ startet ständig neu."),
    ("containers", "missing"): gettext_lazy("Es laufen keine Dienste von Wachwerk."),
    ("containers", "unreadable"): gettext_lazy("Der Zustand der Dienste ist nicht lesbar."),
    ("errors", "server"): gettext_lazy("%(param)s Serverfehler in den letzten 15 Minuten."),
    ("backup", "volume_missing"): gettext_lazy("Der Speicherort der Backups fehlt."),
    ("backup", "missing"): gettext_lazy("Es gibt noch kein Backup."),
    ("backup", "stale"): gettext_lazy("Das neueste Backup ist %(param)s Stunden alt."),
    ("offsite", "never"): gettext_lazy("Die Kopie außer Haus ist noch nie gelungen."),
    ("offsite", "sync_stale"): gettext_lazy("Die letzte Kopie außer Haus liegt %(param)s Stunden zurück."),
    ("offsite", "copy_missing"): gettext_lazy("Es gibt keine verschlüsselte Kopie für außer Haus."),
    ("offsite", "copy_stale"): gettext_lazy("Die neueste verschlüsselte Kopie ist %(param)s Stunden alt."),
    # USB-Wechsel (Kopie außer Haus mit Sticks); das Skript schreibt diese
    # Codes erst mit der USB-Rotation.
    ("offsite", "no_medium"): gettext_lazy("Seit %(param)s Stunden wurde kein Backup-Stick beschrieben."),
    ("offsite", "rotation"): gettext_lazy(
        "Der Backup-Stick außer Haus ist %(param)s Tage alt. Bitte Stick tauschen."
    ),
    ("restore", "stale"): gettext_lazy("Die letzte Wiederherstellungsprobe liegt %(param)s Tage zurück."),
    ("restore", "failed"): gettext_lazy("Die letzte Wiederherstellungsprobe ist fehlgeschlagen."),
    ("disk", "full"): gettext_lazy("Die Systemplatte ist zu %(param)s Prozent belegt."),
    ("docker", "missing"): gettext_lazy("Docker fehlt auf dem Server."),
    ("test", "alert"): gettext_lazy("Testmeldung der Überwachung."),
}

OFFSITE_KIND_LABELS = {
    "usb": gettext_lazy("USB-Sticks im Wechsel"),
    "path": gettext_lazy("Netzlaufwerk (NAS)"),
    "ssh": gettext_lazy("Server per SSH"),
    "storagebox": gettext_lazy("Hetzner Storage Box"),
}


@dataclass(frozen=True)
class Problem:
    area: str
    issue: str
    param: str = ""

    @property
    def text(self) -> str:
        template = PROBLEM_TEXTS.get((self.area, self.issue))
        if template is None:
            return str(GENERIC_TEXT)
        template = str(template)
        if "%(param)s" not in template:
            return template
        if not self.param:
            return str(GENERIC_TEXT)
        return template % {"param": self.param}


@dataclass(frozen=True)
class Medium:
    name: str
    last_write: datetime | None = None


@dataclass(frozen=True)
class RestoreResult:
    at: datetime
    ok: bool | None = None
    dump_at: datetime | None = None
    tables: int | None = None
    migrations: int | None = None
    stations: int | None = None
    users: int | None = None
    audit: int | None = None
    sha256: str = ""


@dataclass(frozen=True)
class HostHealth:
    available: bool = False
    checked_at: datetime | None = None
    state: str = ""
    failing_since: datetime | None = None
    alert: str = ""
    last_alert: str = ""
    problems: tuple[Problem, ...] = ()
    notes: tuple[Problem, ...] = ()
    backup_newest_at: datetime | None = None
    backup_age_hours: int | None = None
    offsite_kind: str = ""
    offsite_newest_at: datetime | None = None
    offsite_age_hours: int | None = None
    offsite_sync_age_hours: int | None = None
    offsite_away_age_days: int | None = None
    media: tuple[Medium, ...] = ()
    restore_test: RestoreResult | None = None
    restore_probe: RestoreResult | None = None

    def is_stale(self, now: datetime | None = None) -> bool:
        if not self.available or self.checked_at is None:
            return False
        return (now or timezone.now()) - self.checked_at > STALE_AFTER

    @property
    def alerting(self) -> bool:
        """Eine Störung ist gemeldet (Schwelle FAILS_BEFORE_ALERT erreicht)."""
        return self.available and bool(self.alert) and self.state == "problem"

    @property
    def recovered(self) -> bool:
        """Die zuletzt gemeldete Störung ist behoben, alles wieder in Ordnung."""
        return self.available and not self.alert and bool(self.last_alert) and self.state == "ok"

    def needs_banner(self, now: datetime | None = None) -> bool:
        return self.alerting or self.is_stale(now)

    @property
    def offsite_kind_label(self) -> str:
        label = OFFSITE_KIND_LABELS.get(self.offsite_kind)
        return str(label) if label else ""


UNAVAILABLE = HostHealth()


# --- Lesen und Prüfen ---------------------------------------------------------

def _iso(value) -> datetime | None:
    if not isinstance(value, str) or not ISO_RE.fullmatch(value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt_timezone.utc)
    except ValueError:
        return None


def _number(value) -> int | None:
    # bool ist in Python ein int; true/false sind keine Zahlen.
    if type(value) is not int or not 0 <= value <= MAX_NUMBER:
        return None
    return value


def _flag(value) -> bool | None:
    return value if type(value) is bool else None


def _code(value) -> str:
    return value if isinstance(value, str) and CODE_RE.fullmatch(value) else ""


def _problems(value) -> tuple[Problem, ...]:
    if not isinstance(value, list):
        return ()
    result = []
    for item in value:
        if len(result) >= MAX_PROBLEMS:
            break
        if not isinstance(item, dict):
            continue
        area, issue = _code(item.get("area")), _code(item.get("issue"))
        if not area or not issue:
            continue
        param = item.get("param")
        if not isinstance(param, str) or not PARAM_RE.fullmatch(param):
            param = ""
        result.append(Problem(area, issue, param))
    return tuple(result)


def _media(value) -> tuple[Medium, ...]:
    if not isinstance(value, list):
        return ()
    result = []
    for item in value:
        if len(result) >= MAX_MEDIA:
            break
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not MEDIUM_RE.fullmatch(name):
            continue
        result.append(Medium(name=name, last_write=_iso(item.get("last_write"))))
    return tuple(result)


def _restore(value, *, with_digest: bool = False) -> RestoreResult | None:
    if not isinstance(value, dict):
        return None
    at = _iso(value.get("at"))
    if at is None:
        return None
    digest = value.get("sha256") if with_digest else None
    return RestoreResult(
        at=at,
        ok=_flag(value.get("ok")),
        dump_at=_iso(value.get("dump_at")),
        tables=_number(value.get("tables")),
        migrations=_number(value.get("migrations")),
        stations=_number(value.get("stations")),
        users=_number(value.get("users")),
        audit=_number(value.get("audit")),
        sha256=digest if isinstance(digest, str) and SHA_RE.fullmatch(digest) else "",
    )


def parse_status(data) -> HostHealth:
    """Prüft den Inhalt von status.json (Schema 1) Feld für Feld.

    Ohne gültiges ``schema`` und ``checked_at`` gilt der Zustand als nicht
    vorhanden; jedes andere ungültige Feld fällt einzeln weg.
    """
    if not isinstance(data, dict):
        return UNAVAILABLE
    schema = data.get("schema")
    if type(schema) is not int or schema != 1:
        return UNAVAILABLE
    checked_at = _iso(data.get("checked_at"))
    if checked_at is None:
        return UNAVAILABLE
    problems = _problems(data.get("problems"))
    state = data.get("state")
    if state not in ("ok", "problem"):
        state = "problem" if problems else "ok"
    alert = data.get("alert")
    last_alert = data.get("last_alert")
    backup = data.get("backup") if isinstance(data.get("backup"), dict) else {}
    offsite = data.get("offsite") if isinstance(data.get("offsite"), dict) else {}
    offsite_kind = offsite.get("kind") if offsite.get("kind") in OFFSITE_KIND_LABELS else ""
    if not offsite_kind:
        offsite = {}
    return HostHealth(
        available=True,
        checked_at=checked_at,
        state=state,
        failing_since=_iso(data.get("failing_since")),
        alert=alert if isinstance(alert, str) and ALERT_RE.fullmatch(alert) else "",
        last_alert=last_alert if isinstance(last_alert, str) and ALERT_RE.fullmatch(last_alert) else "",
        problems=problems,
        notes=_problems(data.get("notes")),
        backup_newest_at=_iso(backup.get("newest_at")),
        backup_age_hours=_number(backup.get("age_hours")),
        offsite_kind=offsite_kind,
        offsite_newest_at=_iso(offsite.get("newest_at")),
        offsite_age_hours=_number(offsite.get("age_hours")),
        offsite_sync_age_hours=_number(offsite.get("sync_age_hours")),
        offsite_away_age_days=_number(offsite.get("away_age_days")),
        media=_media(offsite.get("media")),
        restore_test=_restore(data.get("restore_test")),
        restore_probe=_restore(data.get("restore_probe"), with_digest=True),
    )


def status_path() -> str:
    return getattr(settings, "HOST_HEALTH_FILE", "") or DEFAULT_STATUS_FILE


# Pfad → (Schlüssel aus stat, Ergebnis). Der Host ersetzt die Datei per mv;
# eine neue Fassung hat damit eine neue Inode und wird neu gelesen.
_cache: dict[str, tuple[tuple, HostHealth]] = {}


def _stat_key(path: str, info: os.stat_result) -> tuple:
    return (path, info.st_dev, info.st_ino, info.st_mtime_ns, info.st_size)


def _load(path: str) -> tuple[tuple | None, HostHealth]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        return None, UNAVAILABLE
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_STATUS_BYTES:
            return None, UNAVAILABLE
        chunks, total = [], 0
        while total <= MAX_STATUS_BYTES:
            chunk = os.read(fd, MAX_STATUS_BYTES + 1 - total)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
    except OSError:
        return None, UNAVAILABLE
    finally:
        os.close(fd)
    if total > MAX_STATUS_BYTES:
        return None, UNAVAILABLE
    try:
        data = json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return _stat_key(path, info), UNAVAILABLE
    return _stat_key(path, info), parse_status(data)


def read_host_health(path: str | None = None) -> HostHealth:
    """Liest den Zustand; wirft nie. Fehlt die Datei oder ist sie ungültig: nicht vorhanden."""
    path = path or status_path()
    try:
        try:
            info = os.stat(path, follow_symlinks=False)
        except OSError:
            return UNAVAILABLE
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_STATUS_BYTES:
            return UNAVAILABLE
        cached = _cache.get(path)
        if cached and cached[0] == _stat_key(path, info):
            return cached[1]
        key, value = _load(path)
        if key is not None:
            if len(_cache) > 8:
                _cache.clear()
            _cache[path] = (key, value)
        return value
    except Exception:  # pragma: no cover - Anzeige darf nie an der Datei scheitern
        logger.exception("Zustand der Host-Überwachung nicht lesbar")
        return UNAVAILABLE


# --- Sichtbarkeit und Banner ----------------------------------------------------

def _shared_demo() -> bool:
    """Gemeinsame Vorführ-Demo mit öffentlichem Passwort (DEMO_MODE ohne Sandbox)."""
    return bool(getattr(settings, "DEMO_MODE", False)) and not bool(getattr(settings, "DEMO_SANDBOX", False))


def _is_demo_station(station) -> bool:
    from django.core.exceptions import ObjectDoesNotExist

    try:
        return station.demo_sandbox is not None
    except ObjectDoesNotExist:
        return False


def host_health_visible(membership) -> bool:
    """Nur echte Wachen; nie in der gemeinsamen Demo, nie in einer Demo-Wache.

    Ohne öffentliche Demo (``DEMO_SANDBOX`` aus) entsteht dabei keine Abfrage.
    """
    if membership is None or _shared_demo():
        return False
    if getattr(settings, "DEMO_SANDBOX", False) and _is_demo_station(membership.station):
        return False
    return True


def banner_for(membership, now: datetime | None = None) -> dict | None:
    """Angaben für das Banner (nur Master-Admins), sonst None."""
    from .models import Membership

    if membership is None or membership.role != Membership.Role.ADMIN:
        return None
    if not host_health_visible(membership):
        return None
    health = read_host_health()
    now = now or timezone.now()
    if not health.needs_banner(now):
        return None
    if health.is_stale(now):
        return {"stale": True, "checked_at": health.checked_at, "first_problem": "", "more": 0}
    first = health.problems[0].text if health.problems else str(GENERIC_TEXT)
    return {
        "stale": False,
        "checked_at": health.checked_at,
        "first_problem": first,
        "more": max(len(health.problems) - 1, 0),
    }


# --- Meldungen (notify-worker) ----------------------------------------------------

def admin_recipients() -> list:
    """Aktive Master-Admins aktiver, echter Wachen; je Person eine Mitgliedschaft.

    Gespeichert wird die Nachricht bei der Wache dieser Mitgliedschaft (die
    niedrigste Wachen-ID, falls es je mehrere gäbe); dort sehen Posteingang,
    App und Push sie.
    """
    from .models import Membership

    if _shared_demo():
        return []
    memberships = (
        Membership.objects.filter(
            role=Membership.Role.ADMIN,
            is_active=True,
            station__is_active=True,
            station__demo_sandbox__isnull=True,
            user__is_active=True,
        )
        .select_related("user", "station")
        .order_by("station_id", "user_id")
    )
    seen: set[int] = set()
    result = []
    for membership in memberships:
        if membership.user_id in seen:
            continue
        seen.add(membership.user_id)
        result.append(membership)
    return result


def _clock(moment: datetime, now: datetime) -> str:
    local = timezone.localtime(moment)
    if local.date() == timezone.localtime(now).date():
        return date_format(local, "H:i")
    return date_format(local, "d.m. H:i")


def _compact(moment: datetime) -> str:
    return moment.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _alert_body(health: HostHealth, now: datetime) -> str:
    since = health.failing_since or health.checked_at
    texts = [problem.text for problem in health.problems[:3]] or [str(GENERIC_TEXT)]
    body = _("Seit %(time)s Uhr: %(problems)s") % {"time": _clock(since, now), "problems": " ".join(texts)}
    rest = len(health.problems) - 3
    if rest > 0:
        body += " " + _("(+%(count)s weitere)") % {"count": rest}
    suffix = " " + _("Details unter System.")
    return body[: 300 - len(suffix)] + suffix


def _deliver(memberships, key: str, title: str, body: str, outbox: list) -> int:
    """Eine Nachricht je Person und Schlüssel; neue Nachrichten gehen in die Kanäle."""
    from .crew_notifications import _enqueue_channels
    from .notification_models import UserNotification

    url = reverse("system_status")
    created_count = 0
    for membership in memberships:
        try:
            with transaction.atomic():
                note, created = UserNotification.objects.get_or_create(
                    user=membership.user,
                    dedupe_key=key,
                    defaults={
                        "station": membership.station,
                        "kind": UserNotification.Kind.SYSTEM_HEALTH,
                        "title": title[:120],
                        "body": body[:300],
                        "url": url,
                    },
                )
                if created:
                    _enqueue_channels(note, {"title": note.title, "body": note.body, "url": url,
                                             "notification_id": note.pk})
        except IntegrityError:
            # Ein paralleler Lauf war schneller; die Nachricht existiert schon.
            continue
        if created:
            created_count += 1
            if membership.user.email:
                outbox.append((title, body, [membership.user.email]))
    extra = list(getattr(settings, "HEALTH_ALERT_EMAIL", []) or [])
    if created_count and extra:
        outbox.append((title, body, extra))
    return created_count


def _send_emails(outbox: list) -> None:
    """E-Mails über eine Verbindung; Fehler werden protokolliert, nie weitergereicht."""
    from django.core.mail import EmailMessage, get_connection

    from .coffee import email_enabled

    if not outbox or not email_enabled():
        return
    site = getattr(settings, "SITE_URL", "")
    link = f"{site}{reverse('system_status')}" if site else ""
    footer = _(
        "Diese Nachricht geht an die Master-Admins dieser Wachwerk-Installation. "
        "Sie enthält keine Inhalte aus Wachwerk, nur den technischen Zustand des Servers."
    )
    try:
        connection = get_connection()
        connection.open()
    except Exception:
        logger.exception("Host-Überwachung: E-Mail-Server nicht erreichbar")
        return
    try:
        for subject, body, recipients in outbox:
            text = "\n\n".join(part for part in (body, link, footer) if part)
            try:
                connection.send_messages([EmailMessage(subject, text, to=recipients)])
            except Exception:
                logger.exception("Host-Überwachung: E-Mail an %s Empfänger fehlgeschlagen", len(recipients))
    finally:
        try:
            connection.close()
        except Exception:  # pragma: no cover
            logger.exception("Host-Überwachung: E-Mail-Verbindung nicht sauber geschlossen")


def _notify(health: HostHealth, now: datetime, stale: bool, allow_stale_alert: bool) -> int:
    from .notification_models import UserNotification

    kind = UserNotification.Kind.SYSTEM_HEALTH
    recipients = admin_recipients()
    outbox: list = []
    created = 0
    if health.alerting:
        created += _deliver(recipients, f"host_health:{health.alert}", _("Wachwerk: technische Störung"),
                            _alert_body(health, now), outbox)
    if health.recovered:
        alert_key = f"host_health:{health.last_alert}"
        alerted = set(
            UserNotification.objects.filter(kind=kind, dedupe_key=alert_key).values_list("user_id", flat=True)
        )
        if alerted:
            body = _("Die Überwachung meldet seit %(time)s Uhr wieder alles in Ordnung.") % {
                "time": _clock(health.checked_at, now)}
            created += _deliver([m for m in recipients if m.user_id in alerted], f"{alert_key}:ok",
                                _("Wachwerk: Störung behoben"), body, outbox)
            UserNotification.objects.filter(kind=kind, dedupe_key=alert_key, read_at__isnull=True).update(
                read_at=now)
    if stale and allow_stale_alert:
        body = _("Letzte Prüfung um %(time)s Uhr. Bitte den Server prüfen (sudo wachwerk-health --verbose).") % {
            "time": _clock(health.checked_at, now)}
        created += _deliver(recipients, f"host_health_stale:{_compact(health.checked_at)}",
                            _("Wachwerk: Überwachung meldet sich nicht"), body, outbox)
    elif not stale:
        # Die Überwachung meldet sich wieder: offene Hinweise darauf sind erledigt.
        UserNotification.objects.filter(
            kind=kind, dedupe_key__startswith="host_health_stale:", read_at__isnull=True,
        ).update(read_at=now)
    _send_emails(outbox)
    return created


# Pfad → (bereits verarbeiteter Zustand, Zeitpunkt). Ein Prozess je Worker.
_processed: dict[str, tuple[tuple, float]] = {}


def reset_state() -> None:
    """Zwischenspeicher leeren (Tests)."""
    _cache.clear()
    _processed.clear()


def notify_host_health(now: datetime | None = None, *, allow_stale_alert: bool = True,
                       path: str | None = None) -> int:
    """Meldet Störungen, Behebung und Schweigen der Überwachung. Idempotent.

    Ohne Statusdatei oder bei ungültigem Inhalt geschieht nichts, auch keine
    Datenbankabfrage. ``allow_stale_alert=False`` (Worker gerade gestartet)
    verhindert eine Meldung „Überwachung meldet sich nicht“ nach einem
    Neustart, bevor der Timer wieder lief.
    """
    path = path or status_path()
    health = read_host_health(path)
    if not health.available or _shared_demo():
        return 0
    now = now or timezone.now()
    stale = health.is_stale(now)
    signature = (
        health.alert if health.alerting else "",
        health.last_alert if health.recovered else "",
        _compact(health.checked_at) if stale and allow_stale_alert else "",
        stale,
    )
    previous = _processed.get(path)
    if previous and previous[0] == signature and time.monotonic() - previous[1] < REPROCESS_AFTER_SECONDS:
        return 0
    with translation.override(settings.LANGUAGE_CODE):
        created = _notify(health, now, stale, allow_stale_alert)
    _processed[path] = (signature, time.monotonic())
    return created
