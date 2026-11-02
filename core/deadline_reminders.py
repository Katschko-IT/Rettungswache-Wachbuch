"""Fristen-Erinnerungen bei 30, 7 und 0 Tagen und Wochenübersicht (Roadmap 0.28).

Prüft Fristen aus:
- Medizinprodukte (core.mpg_models.MedicalDevice): STK (zum Monatsende), MTK (zum Jahresende), DGUV V3
- Fuhrpark (core.fleet_models.Vehicle): HU (§ 29 StVZO), UVV (DGUV V70), SP, Tragentisch
- Lager / Chargen (core.warehouse_models.ItemBatch / StockBatch): Verfall (MHD / out-of-fridge)
- Mängel (core.wachalltag_models.Defect): Fälligkeit (due_at / due_date)
- Dienstanweisungen (core.orga_models.SOPDocument / StandardOperatingProcedure): Lesefrist (ack_due_date) & QM-Review
- Prüfungen / Aufgaben (core.models.StationTask): Fälligkeitsdatum (due_date)

Erzeugt deduplizierte persönliche Benachrichtigungen (UserNotification) für
Verantwortliche / Funktionsbeauftragte und unquittierte Beschäftigte.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from .crew_notifications import _enqueue_channels
from .models import Membership, Station, StationTask
from .notification_models import UserNotification
from .paper import collect_deadlines


DEFAULT_THRESHOLDS = (30, 7, 0)


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


@dataclass
class DeadlineItem:
    station: Station
    category: str
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


def get_station_leads(station: Station) -> list[User]:
    """Wachleitung und Master-Admins der Wache."""
    return list(
        User.objects.filter(
            station_memberships__station=station,
            station_memberships__is_active=True,
            station_memberships__role__in=[Membership.Role.ADMIN, Membership.Role.SHIFT_LEAD],
        ).distinct()
    )


def get_mpg_leads(station: Station) -> list[User]:
    """MPG-Beauftragte sowie Wachleitung und Master-Admins."""
    return list(
        User.objects.filter(
            station_memberships__station=station,
            station_memberships__is_active=True,
        )
        .filter(
            Q(station_memberships__is_mpg_lead=True)
            | Q(station_memberships__role__in=[Membership.Role.ADMIN, Membership.Role.SHIFT_LEAD])
        )
        .distinct()
    )


def collect_deadline_items(
    station: Station | None = None,
    today: date | None = None,
    thresholds: Iterable[int] = DEFAULT_THRESHOLDS,
) -> list[DeadlineItem]:
    """Sammelt alle fälligen Fristen an den Schwellenwerten (30, 7, 0 Tage)."""
    today = today or timezone.localdate()
    threshold_set = set(thresholds)
    stations = [station] if station is not None else list(Station.objects.filter(is_active=True))

    items: list[DeadlineItem] = []

    for st in stations:
        leads = get_station_leads(st)

        # 1. Medizingeräte (MPG)
        if st.mpg_enabled:
            from .mpg_models import MedicalDevice

            mpg_leads = get_mpg_leads(st)
            devices = MedicalDevice.objects.filter(station=st)
            for dev in devices:
                url = reverse("mpg_device_detail", args=[dev.slug])

                # STK zum Monatsende
                stk_due = get_stk_due_date(dev)
                if stk_due:
                    days = (stk_due - today).days
                    if days in threshold_set:
                        title = (
                            _("STK fällig in %(days)d Tagen: %(name)s") % {"days": days, "name": dev.name}
                            if days > 0
                            else _("STK heute fällig: %(name)s") % {"name": dev.name}
                        )
                        body = _("Sicherheitstechnische Kontrolle (Monatsende: %(date)s) für „%(name)s“.") % {
                            "date": stk_due.strftime("%d.%m.%Y"),
                            "name": dev.name,
                        }
                        items.append(
                            DeadlineItem(
                                station=st,
                                category="stk",
                                item_pk=dev.pk,
                                item_name=dev.name,
                                due_date=stk_due,
                                days_remaining=days,
                                threshold=days,
                                title=title[:120],
                                body=body[:300],
                                url=url,
                                recipients=mpg_leads,
                            )
                        )

                # MTK zum Jahresende
                mtk_due = get_mtk_due_date(dev)
                if mtk_due:
                    days = (mtk_due - today).days
                    if days in threshold_set:
                        title = (
                            _("MTK fällig in %(days)d Tagen: %(name)s") % {"days": days, "name": dev.name}
                            if days > 0
                            else _("MTK heute fällig: %(name)s") % {"name": dev.name}
                        )
                        body = _("Messtechnische Kontrolle (Jahresende: %(date)s) für „%(name)s“.") % {
                            "date": mtk_due.strftime("%d.%m.%Y"),
                            "name": dev.name,
                        }
                        items.append(
                            DeadlineItem(
                                station=st,
                                category="mtk",
                                item_pk=dev.pk,
                                item_name=dev.name,
                                due_date=mtk_due,
                                days_remaining=days,
                                threshold=days,
                                title=title[:120],
                                body=body[:300],
                                url=url,
                                recipients=mpg_leads,
                            )
                        )

                # DGUV V3 (Elektrische Prüfung)
                if dev.next_dguv_date:
                    days = (dev.next_dguv_date - today).days
                    if days in threshold_set:
                        title = (
                            _("DGUV V3 Prüfung in %(days)d Tagen: %(name)s") % {"days": days, "name": dev.name}
                            if days > 0
                            else _("DGUV V3 Prüfung heute fällig: %(name)s") % {"name": dev.name}
                        )
                        body = _("Elektrische Prüfung DGUV Vorschrift 3 für „%(name)s“ fällig am %(date)s.") % {
                            "name": dev.name,
                            "date": dev.next_dguv_date.strftime("%d.%m.%Y"),
                        }
                        items.append(
                            DeadlineItem(
                                station=st,
                                category="dguv",
                                item_pk=dev.pk,
                                item_name=dev.name,
                                due_date=dev.next_dguv_date,
                                days_remaining=days,
                                threshold=days,
                                title=title[:120],
                                body=body[:300],
                                url=url,
                                recipients=mpg_leads,
                            )
                        )

        # 2. Fuhrpark (HU, UVV, SP, Tragentisch)
        if st.fleet_enabled:
            from .fleet_models import Vehicle

            vehicles = Vehicle.objects.filter(station=st, is_active=True)
            for v in vehicles:
                url = reverse("fleet_vehicle_detail", args=[v.slug])

                # HU (§ 29 StVZO)
                if v.next_hu_date:
                    days = (v.next_hu_date - today).days
                    if days in threshold_set:
                        title = (
                            _("HU fällig in %(days)d Tagen: %(call_sign)s") % {"days": days, "call_sign": v.call_sign}
                            if days > 0
                            else _("HU heute fällig: %(call_sign)s") % {"call_sign": v.call_sign}
                        )
                        body = _("Hauptuntersuchung (§ 29 StVZO) für %(call_sign)s (%(plate)s) fällig am %(date)s.") % {
                            "call_sign": v.call_sign,
                            "plate": v.license_plate,
                            "date": v.next_hu_date.strftime("%d.%m.%Y"),
                        }
                        items.append(
                            DeadlineItem(
                                station=st,
                                category="hu",
                                item_pk=v.pk,
                                item_name=v.call_sign,
                                due_date=v.next_hu_date,
                                days_remaining=days,
                                threshold=days,
                                title=title[:120],
                                body=body[:300],
                                url=url,
                                recipients=leads,
                            )
                        )

                # UVV (DGUV V70)
                if v.next_uvv_date:
                    days = (v.next_uvv_date - today).days
                    if days in threshold_set:
                        title = (
                            _("UVV-Prüfung in %(days)d Tagen: %(call_sign)s")
                            % {"days": days, "call_sign": v.call_sign}
                            if days > 0
                            else _("UVV-Prüfung heute fällig: %(call_sign)s") % {"call_sign": v.call_sign}
                        )
                        body = _("UVV-Prüfung (DGUV Vorschrift 70) für %(call_sign)s (%(plate)s) fällig am %(date)s.") % {
                            "call_sign": v.call_sign,
                            "plate": v.license_plate,
                            "date": v.next_uvv_date.strftime("%d.%m.%Y"),
                        }
                        items.append(
                            DeadlineItem(
                                station=st,
                                category="uvv",
                                item_pk=v.pk,
                                item_name=v.call_sign,
                                due_date=v.next_uvv_date,
                                days_remaining=days,
                                threshold=days,
                                title=title[:120],
                                body=body[:300],
                                url=url,
                                recipients=leads,
                            )
                        )

        # 3. Lager / Chargen (ItemBatch / StockBatch)
        if st.warehouse_enabled:
            from .warehouse_models import ItemBatch

            batches = ItemBatch.objects.filter(station=st, is_recalled=False).select_related("item")
            for batch in batches:
                exp = batch.expiry_date
                if exp:
                    days = (exp - today).days
                    if days in threshold_set:
                        url = reverse("warehouse_item_detail", args=[batch.item.slug])
                        title = (
                            _("Verfall in %(days)d Tagen: %(item)s") % {"days": days, "item": batch.item.name}
                            if days > 0
                            else _("Material verfällt heute: %(item)s") % {"item": batch.item.name}
                        )
                        body = _("Charge %(lot)s von „%(item)s“ verfällt am %(date)s.") % {
                            "lot": batch.batch_number,
                            "item": batch.item.name,
                            "date": exp.strftime("%d.%m.%Y"),
                        }
                        items.append(
                            DeadlineItem(
                                station=st,
                                category="batch",
                                item_pk=batch.pk,
                                item_name=f"{batch.item.name} ({batch.batch_number})",
                                due_date=exp,
                                days_remaining=days,
                                threshold=days,
                                title=title[:120],
                                body=body[:300],
                                url=url,
                                recipients=leads,
                            )
                        )

        # 4. Mängel (Defect)
        from .wachalltag_models import Defect

        defects = (
            Defect.objects.filter(station=st)
            .exclude(status=Defect.Status.DONE)
            .select_related("owner")
        )
        for defect in defects:
            due = defect.due_date
            if due:
                days = (due - today).days
                if days in threshold_set:
                    recipients = list(dict.fromkeys(leads + ([defect.owner] if defect.owner else [])))
                    url = reverse("defect_detail_web", args=[defect.pk])
                    title = (
                        _("Mangel-Frist in %(days)d Tagen: %(title)s") % {"days": days, "title": defect.title}
                        if days > 0
                        else _("Mangel-Frist heute fällig: %(title)s") % {"title": defect.title}
                    )
                    body = _("Mangel „%(title)s“ hat Fälligkeit am %(date)s.") % {
                        "title": defect.title,
                        "date": due.strftime("%d.%m.%Y"),
                    }
                    items.append(
                        DeadlineItem(
                            station=st,
                            category="defect",
                            item_pk=defect.pk,
                            item_name=defect.title,
                            due_date=due,
                            days_remaining=days,
                            threshold=days,
                            title=title[:120],
                            body=body[:300],
                            url=url,
                            recipients=recipients,
                        )
                    )

        # 5. Dienstanweisungen (SOPDocument / StandardOperatingProcedure)
        if st.orga_enabled:
            from .orga_models import SOPDocument

            sops = SOPDocument.objects.filter(station=st, status=SOPDocument.Status.ACTIVE)
            for sop in sops:
                url = reverse("sop_detail", args=[sop.slug])

                # Lesefrist (ack_due_date)
                if sop.requires_acknowledgment and sop.ack_due_date:
                    days = (sop.ack_due_date - today).days
                    if days in threshold_set:
                        # a) Erinnerung an unquittierte Beschäftigte
                        unacked = list(sop.unacknowledged_users())
                        if unacked:
                            user_title = (
                                _("Dienstanweisung: Lesefrist in %(days)d Tagen – %(doc)s")
                                % {"days": days, "doc": sop.doc_number}
                                if days > 0
                                else _("Dienstanweisung: Lesefrist heute – %(doc)s") % {"doc": sop.doc_number}
                            )
                            user_body = _(
                                "Bitte nimm die Dienstanweisung „%(title)s“ (Frist: %(date)s) zur Kenntnis und bestätige sie."
                            ) % {
                                "title": sop.title,
                                "date": sop.ack_due_date.strftime("%d.%m.%Y"),
                            }
                            items.append(
                                DeadlineItem(
                                    station=st,
                                    category="sop",
                                    item_pk=sop.pk,
                                    item_name=f"{sop.doc_number}: {sop.title}",
                                    due_date=sop.ack_due_date,
                                    days_remaining=days,
                                    threshold=days,
                                    title=user_title[:120],
                                    body=user_body[:300],
                                    url=url,
                                    recipients=unacked,
                                    kind=UserNotification.Kind.SOP_DUE,
                                    is_user_specific=True,
                                )
                            )

                        # b) Frist-Erinnerung für Wachleitung
                        prog = sop.ack_progress()
                        lead_title = (
                            _("Dienstanweisung Lesefrist in %(days)d Tagen: %(doc)s")
                            % {"days": days, "doc": sop.doc_number}
                            if days > 0
                            else _("Dienstanweisung Lesefrist heute: %(doc)s") % {"doc": sop.doc_number}
                        )
                        lead_body = _(
                            "Dienstanweisung „%(title)s“ (Frist: %(date)s). Aktuelle Lesequote: %(ack)d / %(total)d (%(pct)d %%)."
                        ) % {
                            "title": sop.title,
                            "date": sop.ack_due_date.strftime("%d.%m.%Y"),
                            "ack": prog["acknowledged_count"],
                            "total": prog["target_count"],
                            "pct": prog["percent"],
                        }
                        items.append(
                            DeadlineItem(
                                station=st,
                                category="sop_lead",
                                item_pk=sop.pk,
                                item_name=f"{sop.doc_number}: {sop.title}",
                                due_date=sop.ack_due_date,
                                days_remaining=days,
                                threshold=days,
                                title=lead_title[:120],
                                body=lead_body[:300],
                                url=url,
                                recipients=leads,
                                kind=UserNotification.Kind.DEADLINE_DUE,
                            )
                        )

                # QM-Review (review_due_date)
                if sop.review_due_date:
                    days = (sop.review_due_date - today).days
                    if days in threshold_set:
                        title = (
                            _("QM-Review fällig in %(days)d Tagen: %(doc)s") % {"days": days, "doc": sop.doc_number}
                            if days > 0
                            else _("QM-Review heute fällig: %(doc)s") % {"doc": sop.doc_number}
                        )
                        body = _("Regelmäßige Überprüfung für Dienstanweisung „%(title)s“ fällig am %(date)s.") % {
                            "title": sop.title,
                            "date": sop.review_due_date.strftime("%d.%m.%Y"),
                        }
                        items.append(
                            DeadlineItem(
                                station=st,
                                category="sop_review",
                                item_pk=sop.pk,
                                item_name=f"{sop.doc_number}: {sop.title}",
                                due_date=sop.review_due_date,
                                days_remaining=days,
                                threshold=days,
                                title=title[:120],
                                body=body[:300],
                                url=url,
                                recipients=leads,
                            )
                        )

        # 6. Prüfungen / Aufgaben (StationTask)
        tasks = StationTask.objects.filter(station=st, due_date__isnull=False)
        for task in tasks:
            days = (task.due_date - today).days
            if days in threshold_set:
                url = reverse("tasks_today")
                title = (
                    _("Aufgabe fällig in %(days)d Tagen: %(title)s") % {"days": days, "title": task.title}
                    if days > 0
                    else _("Aufgabe heute fällig: %(title)s") % {"title": task.title}
                )
                body = _("Aufgabe / Prüfung „%(title)s“ ist am %(date)s fällig.") % {
                    "title": task.title,
                    "date": task.due_date.strftime("%d.%m.%Y"),
                }
                items.append(
                    DeadlineItem(
                        station=st,
                        category="task",
                        item_pk=task.pk,
                        item_name=task.title,
                        due_date=task.due_date,
                        days_remaining=days,
                        threshold=days,
                        title=title[:120],
                        body=body[:300],
                        url=url,
                        recipients=leads,
                    )
                )

    return items


def send_deadline_reminders(
    station: Station | None = None,
    today: date | None = None,
    thresholds: Iterable[int] = DEFAULT_THRESHOLDS,
) -> int:
    """Versendet deduplizierte Benachrichtigungen für Fristen an den Schwellenwerten."""
    items = collect_deadline_items(station=station, today=today, thresholds=thresholds)
    created_count = 0

    for item in items:
        for user in item.recipients:
            if item.is_user_specific:
                dedupe_key = f"deadline:{item.category}:{item.item_pk}:{user.pk}:{item.threshold}:{item.due_date.isoformat()}"
            else:
                dedupe_key = f"deadline:{item.category}:{item.item_pk}:{item.threshold}:{item.due_date.isoformat()}"

            try:
                with transaction.atomic():
                    note, was_created = UserNotification.objects.get_or_create(
                        user=user,
                        dedupe_key=dedupe_key,
                        defaults={
                            "station": item.station,
                            "kind": item.kind,
                            "title": item.title[:120],
                            "body": item.body[:300],
                            "url": item.url,
                        },
                    )
                    if was_created:
                        _enqueue_channels(
                            note,
                            {
                                "title": note.title,
                                "body": note.body,
                                "url": note.url,
                                "notification_id": note.pk,
                            },
                        )
                        created_count += 1
            except IntegrityError:
                continue

    return created_count


def send_weekly_digest(station: Station | None = None, today: date | None = None) -> int:
    """Montags-Wochenübersicht über alle in den nächsten 7 Tagen anstehenden Fristen."""
    today = today or timezone.localdate()
    monday = today - timedelta(days=today.weekday())
    until = today + timedelta(days=7)
    stations = [station] if station is not None else list(Station.objects.filter(is_active=True))

    created_count = 0

    for st in stations:
        leads = get_station_leads(st)
        if not leads:
            continue

        all_deadlines = collect_deadlines(st, until=until)
        # Nur zukünftige oder heute fällige Fristen in der Wochenübersicht
        upcoming = [d for d in all_deadlines if d.due >= today]

        if st.orga_enabled:
            from .orga_models import SOPDocument
            from .paper import Deadline

            for sop in SOPDocument.objects.filter(
                station=st,
                status=SOPDocument.Status.ACTIVE,
                requires_acknowledgment=True,
                ack_due_date__gte=today,
                ack_due_date__lte=until,
            ):
                upcoming.append(
                    Deadline(sop.ack_due_date, _("Dienstanweisung"), _("Lesefrist"), sop.title, sop.doc_number)
                )

        from .paper import Deadline
        from .wachalltag_models import Defect

        for defect in Defect.objects.filter(station=st).exclude(status=Defect.Status.DONE):
            if defect.due_date and today <= defect.due_date <= until:
                upcoming.append(Deadline(defect.due_date, _("Mangel"), _("Frist"), defect.title, ""))

        for task in StationTask.objects.filter(station=st, due_date__gte=today, due_date__lte=until):
            upcoming.append(Deadline(task.due_date, _("Aufgabe"), _("Prüfung"), task.title, ""))

        upcoming.sort(key=lambda d: (d.due, str(d.area), d.subject.casefold()))
        if not upcoming:
            continue

        preview_lines = [f"• {d.area}: {d.subject} ({d.due.strftime('%d.%m.')})" for d in upcoming[:6]]
        if len(upcoming) > 6:
            preview_lines.append(_("… und %(count)d weitere Fristen") % {"count": len(upcoming) - 6})

        body = "\n".join(preview_lines)
        title = _("Wochenübersicht: %(count)d Fristen anstehend") % {"count": len(upcoming)}
        url = reverse("paper_deadlines")
        dedupe_key = f"deadline_weekly_digest:{st.pk}:{monday.isoformat()}"

        for user in leads:
            try:
                with transaction.atomic():
                    note, was_created = UserNotification.objects.get_or_create(
                        user=user,
                        dedupe_key=dedupe_key,
                        defaults={
                            "station": st,
                            "kind": UserNotification.Kind.DEADLINE_DUE,
                            "title": title[:120],
                            "body": body[:300],
                            "url": url,
                        },
                    )
                    if was_created:
                        _enqueue_channels(
                            note,
                            {
                                "title": note.title,
                                "body": note.body,
                                "url": note.url,
                                "notification_id": note.pk,
                            },
                        )
                        created_count += 1
            except IntegrityError:
                continue

    return created_count
