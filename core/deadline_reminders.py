"""Fristen-Erinnerungen bei 30, 7 und 0 Tagen und Wochenübersicht (Roadmap 0.28).

Quellen (eine Stelle für Erinnerungen und Wochenübersicht, ``_sources``):

- Medizinprodukte (``MedicalDevice`` ohne ausgemusterte Geräte): STK zum
  Monatsende, MTK zum Jahresende, DGUV V3; offene Mängel an Medizingeräten.
- Fahrzeuge (``Vehicle``, nicht ausgemustert): HU (§ 29 StVZO), SP,
  UVV-Prüfung (DGUV Vorschrift 70), Wartung Tragentisch; offene Mängel an
  Fahrzeugen.
- Material (``ItemBatch`` mit Bestand, nicht zurückgerufen): Verfall;
  offene Material-Mängel.
- Dienstanweisungen (nur „In Kraft“): Lesefrist (persönlich an die offenen
  Personen der Zielgruppe, die Quote an die Leitung) und QM-Überprüfung.
- Aufgaben und Prüfungen: aktive Wachaufgaben mit Fälligkeitsdatum,
  Prüfintervalle von Checklisten (``ChecklistSchedule.due_next``, nur
  wöchentlich und monatlich; tägliche Checklisten stehen auf der Übersicht)
  und alle übrigen offenen Mängel.
- Hygiene: Es gibt noch keine Fristquelle; der Bereich ist deshalb (noch)
  nicht abonnierbar.

Schwellen (Fensterlogik): Je Eintrag und Fälligkeit geht nur die kleinste
überschrittene Schwelle T (verbleibende Tage <= T) hinaus, die noch nicht
versendet wurde. Wer einen Termin 5 Tage vorher einträgt, bekommt einmal die
7-Tage-Erinnerung, nicht 30 und 7. Eine verpasste 0-Tage-Erinnerung (Server
aus) wird nachgeholt, höchstens ``OVERDUE_CATCH_UP_DAYS`` Tage nach der
Fälligkeit; ältere überfällige Einträge stehen in der Wochenübersicht. Es gibt
keine tägliche Wiederholung: Der Schlüssel jeder Nachricht enthält Quelle,
Eintrag, Schwelle und Fälligkeit (bei Dienstanweisungen auch die Version).

Empfänger je Bereich: Schichtleitung und Master-Admin sowie die Personen mit
der passenden Funktion (``CATEGORIES``), jeweils nur, wenn die Person den
Bereich abonniert hat (``Membership.remind_*``; Standard: an für die Bereiche
der eigenen Funktionen, für die Leitung alle). Würde niemand der Wache eine
Erinnerung erhalten, bekommt die Leitung sie trotzdem. Nie: Auditoren, das
Dienstkonto „Wachenterminal“, deaktivierte Konten oder Mitgliedschaften.

Zustellung: Posteingang (``UserNotification``), Web-Push, App-Relay und Signal
wie bisher, dazu E-Mail für Personen, die das selbst eingeschaltet haben, wenn
E-Mail eingerichtet ist (``EMAIL_HOST``) und keine öffentliche Demo läuft.

Zeitplan: Der notify-worker ruft ``run_scheduled_reminders`` auf; Erinnerungen
höchstens einmal je Stunde, die Wochenübersicht einmal je ISO-Kalenderwoche ab
Montag 06:00 Ortszeit (verpasst: beim nächsten Lauf derselben Woche).
"""
from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Iterable

from django.conf import settings
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _, gettext_lazy, ngettext

from .crew_notifications import _enqueue_channels
from .models import Membership, Station, StationTask
from .notification_models import UserNotification, WorkerJobState

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLDS = (30, 7, 0)
# Eine verpasste Fälligkeitserinnerung wird höchstens so lange nachgeholt.
OVERDUE_CATCH_UP_DAYS = 30
DIGEST_DAYS = 7
DIGEST_MAX_LINES = 8
DIGEST_MAX_SUBJECT = 48
BODY_LIMIT = 300
TITLE_LIMIT = 120

LEAD_ROLES = (Membership.Role.ADMIN, Membership.Role.SHIFT_LEAD)

# Zeitplan im notify-worker (ohne Cron auf dem Host).
JOB_REMINDERS = "deadline_reminders"
JOB_DIGEST = "weekly_digest"
REMINDER_INTERVAL = timedelta(hours=1)
RETRY_AFTER = timedelta(minutes=10)
DIGEST_WEEKDAY = 0  # Montag
DIGEST_HOUR = 6

# Bereiche: Kurzname, Bezeichnung, Feld des Abos, Funktionen, Inhalt.
FLEET, MPG, MATERIAL, SOP, TASKS = "fleet", "mpg", "material", "sop", "tasks"


@dataclass(frozen=True)
class Category:
    code: str
    label: Any
    field: str
    functions: tuple[str, ...]
    help_text: Any


CATEGORIES = (
    Category(FLEET, gettext_lazy("Fahrzeuge"), "remind_fleet", ("is_fleet_lead", "is_safety_lead"),
             gettext_lazy("HU, SP, UVV-Prüfung, Wartung Tragentisch und Mängel an Fahrzeugen. "
                          "Sicherheit / Arbeitsschutz erhält hier nur die UVV-Prüfung.")),
    Category(MPG, gettext_lazy("Medizinprodukte"), "remind_mpg", ("is_mpg_lead",),
             gettext_lazy("STK, MTK, DGUV V3 und Mängel an Medizingeräten.")),
    Category(MATERIAL, gettext_lazy("Material"), "remind_material", ("is_material_lead",),
             gettext_lazy("Verfall von Chargen mit Bestand und Material-Mängel.")),
    Category(SOP, gettext_lazy("Dienstanweisungen"), "remind_sop", (),
             gettext_lazy("Lesefristen (Quote) und QM-Überprüfung. Nur Schichtleitung und Master-Admin.")),
    Category(TASKS, gettext_lazy("Aufgaben und Prüfungen"), "remind_tasks", ("is_safety_lead",),
             gettext_lazy("Wachaufgaben mit Fälligkeitsdatum, Prüfintervalle von Checklisten und übrige Mängel.")),
)
CATEGORY_BY_CODE = {category.code: category for category in CATEGORIES}


# ---- Fälligkeiten -------------------------------------------------------------


def get_stk_due_date(device: Any) -> date | None:
    """Berechnet die STK-Fälligkeit nach der Monatsende-Regel (MPBetreibV)."""
    raw_date = getattr(device, "next_stk_date", None)
    if not raw_date:
        return None
    # Falls Gerät nicht Anlage 1 ist, entfällt STK-Pflicht
    if hasattr(device, "is_anlage_1") and not device.is_anlage_1:
        return None
    last_day = calendar.monthrange(raw_date.year, raw_date.month)[1]
    return date(raw_date.year, raw_date.month, last_day)


def get_mtk_due_date(device: Any) -> date | None:
    """Berechnet die MTK-Fälligkeit nach der Jahresende-Regel (MPBetreibV / Eichrecht)."""
    raw_date = getattr(device, "next_mtk_date", None)
    if not raw_date:
        return None
    # Falls Gerät nicht Anlage 2 ist, entfällt MTK-Pflicht
    if hasattr(device, "is_anlage_2") and not device.is_anlage_2:
        return None
    return date(raw_date.year, 12, 31)


def pick_threshold(days: int, thresholds: Iterable[int]) -> int | None:
    """Kleinste überschrittene Schwelle (Fensterlogik), sonst ``None``."""
    if days < -OVERDUE_CATCH_UP_DAYS:
        return None
    crossed = [threshold for threshold in thresholds if days <= threshold]
    return min(crossed) if crossed else None


def _date(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def _when(days: int) -> str:
    if days > 0:
        return ngettext("fällig in %(days)d Tag", "fällig in %(days)d Tagen", days) % {"days": days}
    if days == 0:
        return _("heute fällig")
    return ngettext("seit %(days)d Tag überfällig", "seit %(days)d Tagen überfällig", -days) % {"days": -days}


def _title(what: str, name: str, days: int) -> str:
    # Teile sind übersetzt; die Reihenfolge ist im Deutschen und Englischen gleich.
    return f"{what} {_when(days)}: {name}"[:TITLE_LIMIT]


# ---- Empfänger ----------------------------------------------------------------


def _service_user_ids() -> set[int]:
    from .terminal_models import StationTerminalCode

    return set(StationTerminalCode.objects.values_list("service_user_id", flat=True))


def reminder_memberships(station: Station) -> list[Membership]:
    """Mögliche Empfänger: aktive Inhaltsrollen mit aktivem Konto, ohne Terminal-Konto."""
    from .access import CONTENT_ROLES

    return list(
        Membership.objects.filter(
            station=station, is_active=True, user__is_active=True, role__in=CONTENT_ROLES,
        )
        .exclude(user_id__in=_service_user_ids())
        .select_related("user")
        .order_by("user_id")
    )


def is_lead(membership: Membership) -> bool:
    return membership.role in LEAD_ROLES


def eligible_categories(membership: Membership) -> list[Category]:
    """Bereiche, die eine Person abonnieren kann: Leitung alle, sonst nach Funktion."""
    if is_lead(membership):
        return list(CATEGORIES)
    return [
        category for category in CATEGORIES
        if any(getattr(membership, flag, False) for flag in category.functions)
    ]


def is_subscribed(membership: Membership, category: Category) -> bool:
    """Abo der Person; ohne eigene Wahl gilt: an, wenn der Bereich zu Rolle oder Funktion passt."""
    if category not in eligible_categories(membership):
        return False
    choice = getattr(membership, category.field, None)
    return True if choice is None else bool(choice)


class StationRecipients:
    """Empfänger einer Wache für einen Lauf (eine Abfrage)."""

    def __init__(self, station: Station):
        self.memberships = reminder_memberships(station)
        self.by_user = {membership.user_id: membership for membership in self.memberships}
        self.leads = [membership for membership in self.memberships if is_lead(membership)]

    def eligible(self, functions: Iterable[str]) -> list[Membership]:
        functions = tuple(functions)
        return [
            membership for membership in self.memberships
            if is_lead(membership) or any(getattr(membership, flag, False) for flag in functions)
        ]

    def for_item(self, category: Category, functions: Iterable[str]) -> list[User]:
        chosen = [membership for membership in self.eligible(functions) if is_subscribed(membership, category)]
        if not chosen:
            # Niemand hat den Bereich abonniert: Die Leitung bekommt ihn trotzdem.
            chosen = self.leads
        return [membership.user for membership in chosen]


def get_station_leads(station: Station) -> list[User]:
    """Schichtleitung und Master-Admins der Wache (ohne Auditor und Terminal-Konto)."""
    return [membership.user for membership in StationRecipients(station).leads]


def get_mpg_leads(station: Station) -> list[User]:
    """MPG-Beauftragte sowie Schichtleitung und Master-Admins.

    Rolle und Funktion gelten für dieselbe Mitgliedschaft an genau dieser Wache.
    """
    return [membership.user for membership in StationRecipients(station).eligible(("is_mpg_lead",))]


# ---- Quellen ------------------------------------------------------------------


@dataclass
class Source:
    """Eine Frist, unabhängig von Schwellen und Empfängern."""

    station: Station
    code: str
    pk: int
    category: str
    functions: tuple[str, ...]
    what: str
    name: str
    due: date
    url: str
    body: str
    key_extra: str = ""
    owner_id: int | None = None
    thresholds: tuple[int, ...] | None = None
    # Dienstanweisung: offene Personen der Zielgruppe und Quote
    sop: Any = None


def _sop_open(sop, cache: dict) -> tuple[list[User], dict]:
    if sop.pk not in cache:
        cache[sop.pk] = (list(sop.unacknowledged_users()), sop.ack_progress())
    return cache[sop.pk]


def _sources(station: Station, until: date, sop_cache: dict | None = None) -> list[Source]:
    """Alle Fristen der Wache bis einschließlich ``until`` (auch überfällige)."""
    from .paper import active_devices, active_vehicles

    sop_cache = {} if sop_cache is None else sop_cache
    rows: list[Source] = []

    if station.mpg_enabled:
        # Rohdatum <= until ist eine Obermenge (Monats- bzw. Jahresende liegt später).
        devices = active_devices(station).filter(
            Q(is_anlage_1=True, next_stk_date__lte=until)
            | Q(is_anlage_2=True, next_mtk_date__lte=until)
            | Q(next_dguv_date__lte=until)
        )
        for device in devices:
            url = reverse("mpg_device_detail", args=[device.slug])
            stk = get_stk_due_date(device)
            if stk and stk <= until:
                rows.append(Source(
                    station, "stk", device.pk, MPG, ("is_mpg_lead",), _("STK"), device.name, stk, url,
                    _("Sicherheitstechnische Kontrolle (Monatsende: %(date)s) für „%(name)s“.")
                    % {"date": _date(stk), "name": device.name},
                ))
            mtk = get_mtk_due_date(device)
            if mtk and mtk <= until:
                rows.append(Source(
                    station, "mtk", device.pk, MPG, ("is_mpg_lead",), _("MTK"), device.name, mtk, url,
                    _("Messtechnische Kontrolle (Jahresende: %(date)s) für „%(name)s“.")
                    % {"date": _date(mtk), "name": device.name},
                ))
            if device.next_dguv_date and device.next_dguv_date <= until:
                rows.append(Source(
                    station, "dguv", device.pk, MPG, ("is_mpg_lead",), _("DGUV-V3-Prüfung"), device.name,
                    device.next_dguv_date, url,
                    _("Elektrische Prüfung DGUV Vorschrift 3 für „%(name)s“ fällig am %(date)s.")
                    % {"name": device.name, "date": _date(device.next_dguv_date)},
                ))

    if station.fleet_enabled:
        vehicle_checks = (
            ("hu", "next_hu_date", _("HU"), ("is_fleet_lead",),
             _("Hauptuntersuchung (§ 29 StVZO) für %(call_sign)s (%(plate)s) fällig am %(date)s.")),
            ("sp", "next_sp_date", _("SP"), ("is_fleet_lead",),
             _("Sicherheitsprüfung (SP) für %(call_sign)s (%(plate)s) fällig am %(date)s.")),
            ("uvv", "next_uvv_date", _("UVV-Prüfung"), ("is_fleet_lead", "is_safety_lead"),
             _("UVV-Prüfung (DGUV Vorschrift 70) für %(call_sign)s (%(plate)s) fällig am %(date)s.")),
            ("stretcher", "next_stretcher_service_date", _("Wartung Tragentisch"), ("is_fleet_lead",),
             _("Wartung des Tragentischs für %(call_sign)s (%(plate)s) fällig am %(date)s.")),
        )
        query = Q()
        for _code, field_name, _what, _functions, _body in vehicle_checks:
            query |= Q(**{f"{field_name}__lte": until})
        for vehicle in active_vehicles(station).filter(query):
            url = reverse("fleet_vehicle_detail", args=[vehicle.slug])
            for code, field_name, what, functions, body in vehicle_checks:
                due = getattr(vehicle, field_name)
                if due and due <= until:
                    rows.append(Source(
                        station, code, vehicle.pk, FLEET, functions, what, vehicle.call_sign, due, url,
                        body % {"call_sign": vehicle.call_sign, "plate": vehicle.license_plate, "date": _date(due)},
                    ))

    if station.warehouse_enabled:
        from .warehouse_models import ItemBatch

        batches = (
            ItemBatch.objects.filter(station=station, is_recalled=False, stock_items__quantity__gt=0)
            .filter(
                Q(calculated_exp_date__lte=until)
                | Q(calculated_exp_date__isnull=True, manufacturer_exp_date__lte=until)
            )
            .select_related("item")
            .distinct()
        )
        for batch in batches:
            due = batch.effective_date
            rows.append(Source(
                station, "batch", batch.pk, MATERIAL, ("is_material_lead",), _("Verfall"),
                f"{batch.item.name} ({batch.batch_number})", due,
                reverse("warehouse_item_detail", args=[batch.item.slug]),
                _("Charge %(lot)s von „%(item)s“ verfällt am %(date)s.")
                % {"lot": batch.batch_number, "item": batch.item.name, "date": _date(due)},
            ))

    from .wachalltag_models import Defect

    until_end = timezone.make_aware(datetime.combine(until + timedelta(days=1), time.min))
    defects = (
        Defect.objects.filter(station=station, due_at__isnull=False, due_at__lt=until_end)
        .exclude(status=Defect.Status.DONE)
    )
    for defect in defects:
        due = defect.due_date
        if not due or due > until:
            continue
        if defect.medical_device_id or defect.category == Defect.Category.DEVICE:
            category, functions = MPG, ("is_mpg_lead",)
        elif defect.category == Defect.Category.VEHICLE:
            category, functions = FLEET, ("is_fleet_lead",)
        elif defect.category == Defect.Category.MATERIAL:
            category, functions = MATERIAL, ("is_material_lead",)
        else:
            category, functions = TASKS, ("is_safety_lead",)
        rows.append(Source(
            station, "defect", defect.pk, category, functions, _("Mangel-Frist"), defect.title, due,
            reverse("defect_detail_web", args=[defect.pk]),
            _("Mangel „%(title)s“ hat Fälligkeit am %(date)s.") % {"title": defect.title, "date": _date(due)},
            owner_id=defect.owner_id,
        ))

    if station.orga_enabled:
        from .orga_models import SOPDocument

        sops = SOPDocument.objects.filter(station=station, status=SOPDocument.Status.ACTIVE).filter(
            Q(requires_acknowledgment=True, ack_due_date__lte=until) | Q(review_due_date__lte=until)
        )
        for sop in sops:
            url = reverse("sop_detail", args=[sop.slug])
            latest = sop.latest_revision
            if sop.requires_acknowledgment and sop.ack_due_date and sop.ack_due_date <= until and latest:
                unacked, progress = _sop_open(sop, sop_cache)
                if unacked:
                    rows.append(Source(
                        station, "sop_lead", sop.pk, SOP, (), _("Lesefrist Dienstanweisung"), sop.doc_number,
                        sop.ack_due_date, url,
                        _("Dienstanweisung „%(title)s“ (Frist: %(date)s). Aktuelle Lesequote: "
                          "%(ack)d / %(total)d (%(pct)d %%).") % {
                            "title": sop.title, "date": _date(sop.ack_due_date),
                            "ack": progress["acknowledged_count"], "total": progress["target_count"],
                            "pct": progress["percent"],
                        },
                        key_extra=f"r{latest.pk}", sop=sop,
                    ))
            if sop.review_due_date and sop.review_due_date <= until:
                rows.append(Source(
                    station, "sop_review", sop.pk, SOP, (), _("QM-Überprüfung"), sop.doc_number,
                    sop.review_due_date, url,
                    _("Regelmäßige Überprüfung für Dienstanweisung „%(title)s“ fällig am %(date)s.")
                    % {"title": sop.title, "date": _date(sop.review_due_date)},
                ))

    if station.tasks_enabled:
        url = reverse("tasks_today")
        for task in StationTask.objects.filter(station=station, is_active=True, due_date__lte=until):
            rows.append(Source(
                station, "task", task.pk, TASKS, ("is_safety_lead",), _("Aufgabe"), task.title, task.due_date, url,
                _("Aufgabe / Prüfung „%(title)s“ ist am %(date)s fällig.")
                % {"title": task.title, "date": _date(task.due_date)},
            ))

    if station.checklists_enabled:
        rows.extend(_checklist_sources(station, until))

    return rows


# Abstand der Prüfintervalle in Tagen. Schwellen ab dieser Länge entfallen:
# Eine wöchentliche Checkliste erinnert nur am Fälligkeitstag, eine monatliche
# 7 Tage vorher und am Fälligkeitstag. Tägliche Checklisten stehen auf der
# Übersicht und erzeugen keine Erinnerung.
CHECKLIST_INTERVAL_DAYS = {"weekly": 7, "monthly": 28}


def _checklist_sources(station: Station, until: date) -> list[Source]:
    """Prüfintervalle der Checklisten (nur lesend; das Modell gehört zu den Checklisten)."""
    from .wachalltag_models import ChecklistSchedule

    rows = []
    url = reverse("checklists")
    schedules = (
        ChecklistSchedule.objects.filter(
            station=station,
            checklist__is_active=True,
            due_next__isnull=False,
            interval__in=tuple(CHECKLIST_INTERVAL_DAYS),
        )
        .select_related("checklist")
    )
    for schedule in schedules:
        due = timezone.localtime(schedule.due_next).date()
        if due > until:
            continue
        span = CHECKLIST_INTERVAL_DAYS[schedule.interval]
        rows.append(Source(
            station, "checklist", schedule.pk, TASKS, ("is_safety_lead",), _("Checkliste"),
            schedule.checklist.title, due, url,
            _("Prüfintervall der Checkliste „%(title)s“: fällig am %(date)s.")
            % {"title": schedule.checklist.title, "date": _date(due)},
            thresholds=tuple(threshold for threshold in DEFAULT_THRESHOLDS if threshold < span),
        ))
    return rows


# ---- Erinnerungen ---------------------------------------------------------------


@dataclass
class DeadlineItem:
    station: Station
    category: str  # Quelle, z. B. „stk“ oder „hu“ (Teil des Schlüssels)
    item_pk: int
    item_name: str
    due_date: date
    days_remaining: int
    threshold: int
    title: str
    body: str
    url: str
    recipients: list[User]
    kind: str = UserNotification.Kind.DEADLINE_DUE
    is_user_specific: bool = False
    area: str = ""  # Bereich des Abos (CATEGORIES)
    key_extra: str = ""

    def dedupe_key(self, user: User) -> str:
        parts = ["deadline", self.category, str(self.item_pk)]
        if self.key_extra:
            parts.append(self.key_extra)
        if self.is_user_specific:
            parts.append(str(user.pk))
        parts += [str(self.threshold), self.due_date.isoformat()]
        return ":".join(parts)[:120]


def _active_stations(station: Station | None) -> list[Station]:
    return [station] if station is not None else list(Station.objects.filter(is_active=True))


def collect_deadline_items(
    station: Station | None = None,
    today: date | None = None,
    thresholds: Iterable[int] = DEFAULT_THRESHOLDS,
) -> list[DeadlineItem]:
    """Fristen, für die jetzt eine Schwelle überschritten ist (Fensterlogik)."""
    today = today or timezone.localdate()
    thresholds = tuple(sorted({int(value) for value in thresholds}, reverse=True))
    if not thresholds:
        return []
    until = today + timedelta(days=max(thresholds))
    items: list[DeadlineItem] = []

    for st in _active_stations(station):
        recipients = StationRecipients(st)
        sop_cache: dict = {}
        for source in _sources(st, until, sop_cache):
            days = (source.due - today).days
            allowed = thresholds if source.thresholds is None else tuple(
                value for value in thresholds if value in source.thresholds
            )
            threshold = pick_threshold(days, allowed)
            if threshold is None:
                continue
            category = CATEGORY_BY_CODE[source.category]
            users = recipients.for_item(category, source.functions)
            if source.owner_id and source.owner_id in recipients.by_user:
                # Wer einen Mangel bearbeitet, erfährt von seiner Frist immer.
                owner = recipients.by_user[source.owner_id].user
                users = list(dict.fromkeys(users + [owner]))
            items.append(DeadlineItem(
                station=st, category=source.code, item_pk=source.pk, item_name=source.name,
                due_date=source.due, days_remaining=days, threshold=threshold,
                title=_title(source.what, source.name, days), body=source.body[:BODY_LIMIT], url=source.url,
                recipients=users, area=source.category, key_extra=source.key_extra,
            ))
            if source.code == "sop_lead":
                # Persönliche Erinnerung an die offenen Personen der Zielgruppe
                # (kein Abo: Die Lesepflicht gilt für die Person selbst).
                unacked, _progress = _sop_open(source.sop, sop_cache)
                sop = source.sop
                items.append(DeadlineItem(
                    station=st, category="sop", item_pk=sop.pk, item_name=sop.doc_number,
                    due_date=source.due, days_remaining=days, threshold=threshold,
                    title=_title(_("Lesefrist Dienstanweisung"), sop.doc_number, days),
                    body=(_("Bitte nimm die Dienstanweisung „%(title)s“ (Frist: %(date)s) zur Kenntnis und "
                            "bestätige sie.") % {"title": sop.title, "date": _date(source.due)})[:BODY_LIMIT],
                    url=source.url, recipients=unacked, kind=UserNotification.Kind.SOP_DUE,
                    is_user_specific=True, area=SOP, key_extra=source.key_extra,
                ))
    return items


def create_notification(user: User, station: Station, dedupe_key: str, kind: str, title: str, body: str,
                        url: str) -> UserNotification | None:
    """Eine Nachricht je Person und Schlüssel; neue gehen in Push und Signal."""
    try:
        with transaction.atomic():
            note, created = UserNotification.objects.get_or_create(
                user=user,
                dedupe_key=dedupe_key[:120],
                defaults={
                    "station": station,
                    "kind": kind,
                    "title": title[:TITLE_LIMIT],
                    "body": body[:BODY_LIMIT],
                    "url": url,
                },
            )
            if created:
                _enqueue_channels(note, {
                    "title": note.title,
                    "body": note.body,
                    "url": note.url,
                    "notification_id": note.pk,
                })
    except IntegrityError:
        # Ein paralleler Lauf war schneller; die Nachricht existiert schon.
        return None
    return note if created else None


def send_deadline_reminders(
    station: Station | None = None,
    today: date | None = None,
    thresholds: Iterable[int] = DEFAULT_THRESHOLDS,
) -> int:
    """Versendet deduplizierte Erinnerungen. Idempotent; gibt die Zahl neuer Nachrichten zurück."""
    with translation.override(settings.LANGUAGE_CODE):
        items = collect_deadline_items(station=station, today=today, thresholds=thresholds)
        created: dict[int, list[UserNotification]] = {}
        for item in items:
            keys = {user.pk: item.dedupe_key(user) for user in item.recipients}
            if not keys:
                continue
            existing = set(
                UserNotification.objects.filter(user_id__in=keys, dedupe_key__in=set(keys.values()))
                .values_list("user_id", "dedupe_key")
            )
            for user in item.recipients:
                if (user.pk, keys[user.pk]) in existing:
                    continue
                note = create_notification(user, item.station, keys[user.pk], item.kind, item.title, item.body,
                                           item.url)
                if note is not None:
                    created.setdefault(user.pk, []).append(note)
        send_reminder_emails(created)
    return sum(len(notes) for notes in created.values())


# ---- Wochenübersicht --------------------------------------------------------------


def iso_week_key(day: date) -> str:
    year, week, _weekday = day.isocalendar()
    return f"{year}-W{week:02d}"


@dataclass
class DigestRow:
    due: date
    category: str
    functions: tuple[str, ...]
    what: str
    subject: str

    def line(self, today: date) -> str:
        subject = self.subject if len(self.subject) <= DIGEST_MAX_SUBJECT else self.subject[: DIGEST_MAX_SUBJECT - 1] + "…"
        values = {"date": self.due.strftime("%d.%m."), "what": self.what, "subject": subject}
        if self.due < today:
            return _("• %(date)s überfällig – %(what)s: %(subject)s") % values
        return "• {date} {what}: {subject}".format(**values)


def _more_line(count: int) -> str:
    return ngettext("… und %(count)d weitere Frist", "… und %(count)d weitere Fristen", count) % {"count": count}


def fit_digest_lines(lines: list[str], limit: int = BODY_LIMIT, max_lines: int = DIGEST_MAX_LINES) -> str:
    """Ganze Zeilen bis zur Länge des Posteingangs; der Rest als „… und N weitere“."""
    kept: list[str] = []
    for index, line in enumerate(lines[:max_lines]):
        remaining = len(lines) - index - 1
        candidate = kept + [line] + ([_more_line(remaining)] if remaining else [])
        if len("\n".join(candidate)) > limit:
            break
        kept.append(line)
    rest = len(lines) - len(kept)
    if rest:
        kept.append(_more_line(rest))
    return "\n".join(kept)


@dataclass
class _DigestRecipient:
    membership: Membership
    categories: set[str] = field(default_factory=set)


def _digest_rows(station: Station, today: date) -> list[DigestRow]:
    until = today + timedelta(days=DIGEST_DAYS)
    rows = [
        DigestRow(source.due, source.category, source.functions, source.what, source.name)
        for source in _sources(station, until)
    ]
    rows.sort(key=lambda row: (row.due, row.what, row.subject.casefold()))
    return rows


def send_weekly_digest(station: Station | None = None, today: date | None = None) -> int:
    """Wochenübersicht je Person mit den abonnierten Bereichen (auch Überfälliges)."""
    today = today or timezone.localdate()
    week = iso_week_key(today)
    week_number = today.isocalendar()[1]
    created: dict[int, list[UserNotification]] = {}
    with translation.override(settings.LANGUAGE_CODE):
        for st in _active_stations(station):
            rows = _digest_rows(st, today)
            if not rows:
                continue
            recipients = StationRecipients(st)
            people = []
            for membership in recipients.memberships:
                subscribed = {category.code for category in CATEGORIES if is_subscribed(membership, category)}
                if subscribed:
                    people.append(_DigestRecipient(membership, subscribed))
            # Bereiche mit Fristen, die niemand abonniert hat, gehen an die Leitung.
            covered = set().union(*(person.categories for person in people)) if people else set()
            orphaned = {row.category for row in rows} - covered
            if orphaned:
                lead_ids = {membership.user_id for membership in recipients.leads}
                known = {person.membership.user_id for person in people}
                for person in people:
                    if person.membership.user_id in lead_ids:
                        person.categories |= orphaned
                people += [_DigestRecipient(m, set(orphaned)) for m in recipients.leads if m.user_id not in known]
            url = reverse("paper_deadlines")
            key = f"deadline_weekly_digest:{st.pk}:{week}"
            for person in people:
                membership = person.membership
                mine = [
                    row for row in rows
                    if row.category in person.categories
                    and (is_lead(membership) or any(getattr(membership, flag, False) for flag in row.functions))
                ]
                if not mine:
                    continue
                lines = [row.line(today) for row in mine]
                title = ngettext(
                    "Wochenübersicht KW %(week)d: %(count)d Frist",
                    "Wochenübersicht KW %(week)d: %(count)d Fristen",
                    len(mine),
                ) % {"week": week_number, "count": len(mine)}
                note = create_notification(
                    membership.user, st, key, UserNotification.Kind.DEADLINE_DUE, title,
                    fit_digest_lines(lines), url,
                )
                if note is not None:
                    # Die E-Mail bekommt die vollständige Liste.
                    note.full_text = "\n".join(lines)
                    created.setdefault(membership.user_id, []).append(note)
        send_reminder_emails(created)
    return sum(len(notes) for notes in created.values())


# ---- E-Mail ---------------------------------------------------------------------


def reminder_email_enabled() -> bool:
    """E-Mail nur mit eingerichtetem SMTP-Server und nie in der öffentlichen Demo."""
    from .coffee import email_enabled

    return email_enabled() and not getattr(settings, "DEMO_MODE", False)


def send_reminder_emails(created: dict[int, list[UserNotification]]) -> int:
    """Neue Erinnerungen als eine E-Mail je Person, nur wer das selbst eingeschaltet hat.

    SMTP-Fehler werden protokolliert und halten nichts auf; die Nachricht im
    Posteingang bleibt in jedem Fall bestehen.
    """
    if not created or not reminder_email_enabled():
        return 0
    from django.core.mail import EmailMessage, get_connection

    opted_in = {
        membership.user_id: membership
        for membership in Membership.objects.filter(
            user_id__in=list(created), is_active=True, reminder_email=True,
        ).select_related("user", "station")
    }
    outbox = []
    site = getattr(settings, "SITE_URL", "")
    for user_id, notes in created.items():
        membership = opted_in.get(user_id)
        if membership is None or not membership.user.email:
            continue
        notes = [note for note in notes if note.station_id == membership.station_id]
        if not notes:
            continue
        if len(notes) == 1:
            subject = notes[0].title
        else:
            subject = ngettext(
                "%(app)s: %(count)d Fristen-Erinnerung", "%(app)s: %(count)d Fristen-Erinnerungen", len(notes),
            ) % {"app": settings.APP_NAME, "count": len(notes)}
        parts = []
        for note in notes:
            text = getattr(note, "full_text", "") or note.body
            link = f"{site}{note.url}" if site and note.url else ""
            parts.append("\n".join(part for part in (note.title, text, link) if part))
        footer = _(
            "Du bekommst diese E-Mail, weil du Erinnerungen per E-Mail eingeschaltet hast. "
            "Abschalten unter Mein Konto → Erinnerungen."
        )
        if site:
            footer += f"\n{site}{reverse('reminder_settings')}"
        outbox.append(EmailMessage(subject[:150], "\n\n".join(parts + [footer]), to=[membership.user.email]))
    if not outbox:
        return 0
    sent = 0
    try:
        connection = get_connection()
        connection.open()
    except Exception:
        logger.exception("Fristen-Erinnerungen: E-Mail-Server nicht erreichbar")
        return 0
    try:
        for message in outbox:
            try:
                connection.send_messages([message])
                sent += 1
            except Exception:
                logger.exception("Fristen-Erinnerungen: E-Mail an eine Person fehlgeschlagen")
    finally:
        try:
            connection.close()
        except Exception:  # pragma: no cover
            logger.exception("Fristen-Erinnerungen: E-Mail-Verbindung nicht sauber geschlossen")
    return sent


# ---- Zeitplan im notify-worker ---------------------------------------------------


def _state(name: str) -> WorkerJobState:
    try:
        state, _created = WorkerJobState.objects.get_or_create(name=name)
    except IntegrityError:
        state = WorkerJobState.objects.get(name=name)
    return state


def _claim_interval(name: str, now: datetime, gap: timedelta) -> bool:
    """Atomarer Anspruch auf den nächsten Lauf: höchstens einer je Abstand, auch bei mehreren Prozessen."""
    _state(name)
    return WorkerJobState.objects.filter(name=name).filter(
        Q(last_started_at__isnull=True) | Q(last_started_at__lte=now - gap)
    ).update(last_started_at=now) == 1


def _claim_period(name: str, period: str, now: datetime) -> bool:
    _state(name)
    return WorkerJobState.objects.filter(name=name).exclude(last_period=period).filter(
        Q(last_failed_at__isnull=True) | Q(last_failed_at__lte=now - RETRY_AFTER)
    ).update(last_period=period, last_started_at=now) == 1


def digest_week_due(now: datetime) -> str | None:
    """ISO-Woche, deren Übersicht ab Montag 06:00 Ortszeit fällig ist, sonst ``None``."""
    local = timezone.localtime(now)
    monday = local.date() - timedelta(days=local.weekday() - DIGEST_WEEKDAY)
    start = timezone.make_aware(datetime.combine(monday, time(DIGEST_HOUR)), timezone.get_current_timezone())
    if local < start:
        return None
    return iso_week_key(monday)


def run_scheduled_reminders(now: datetime | None = None) -> int:
    """Schritt des notify-workers: Erinnerungen stündlich, Wochenübersicht einmal je Woche.

    Fehler werden protokolliert und erst nach ``RETRY_AFTER`` erneut versucht;
    sie zählen nicht als Fehlversuch des Dienstes.
    """
    now = now or timezone.now()
    total = 0
    if _claim_interval(JOB_REMINDERS, now, REMINDER_INTERVAL):
        try:
            count = send_deadline_reminders(today=timezone.localtime(now).date())
        except Exception:
            logger.exception("Fristen-Erinnerungen fehlgeschlagen")
            WorkerJobState.objects.filter(name=JOB_REMINDERS).update(
                last_failed_at=now, last_started_at=now - REMINDER_INTERVAL + RETRY_AFTER,
            )
        else:
            WorkerJobState.objects.filter(name=JOB_REMINDERS).update(last_finished_at=timezone.now(), last_count=count)
            total += count
    week = digest_week_due(now)
    if week and _claim_period(JOB_DIGEST, week, now):
        try:
            count = send_weekly_digest(today=timezone.localtime(now).date())
        except Exception:
            logger.exception("Wochenübersicht fehlgeschlagen")
            WorkerJobState.objects.filter(name=JOB_DIGEST).update(last_period="", last_failed_at=now)
        else:
            WorkerJobState.objects.filter(name=JOB_DIGEST).update(last_finished_at=timezone.now(), last_count=count)
            total += count
    return total


def schedule_status() -> dict[str, WorkerJobState | None]:
    """Letzte Läufe für Systemstatus und Heartbeat (eine Abfrage)."""
    states = {state.name: state for state in WorkerJobState.objects.filter(name__in=(JOB_REMINDERS, JOB_DIGEST))}
    return {"reminders": states.get(JOB_REMINDERS), "digest": states.get(JOB_DIGEST)}
