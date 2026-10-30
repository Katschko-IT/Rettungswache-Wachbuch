"""Anonyme Kennzahlen der öffentlichen Demo für den Betreiber.

Gezählt wird nur je Tag: gestartete Demos, abgeschlossene Rundgänge und
Rückmeldungen. Es gibt keine IP-Adresse, kein Konto, kein Token und keine
Verknüpfung zu einer Demo-Wache – die Zahlen sind keine personenbezogenen
Daten und überdauern die Löschung der Demo-Wachen. Sichtbar sind sie im
Feedback-Posteingang (Master-Admins echter Wachen) und über
``python manage.py demo_stats``.

Eine Zählung darf eine Demo nie aufhalten: Fehler werden nur protokolliert.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.core.cache import cache
from django.db import DatabaseError, transaction
from django.db.models import F, Sum
from django.utils import timezone

from .demo_models import DemoDailyStat

logger = logging.getLogger(__name__)

COUNTERS = ("started", "tour_completed", "feedback")
# Ab dieser Zahl laufender Demos zeigt die Startseite „Gerade aktiv“.
ACTIVE_MINIMUM = 3
ACTIVE_CACHE_KEY = "demo-stats:active"
ACTIVE_CACHE_SECONDS = 60


def _sandbox_enabled() -> bool:
    from .demo_sandbox import sandbox_enabled

    return sandbox_enabled()


def _bump(counter: str, day=None) -> None:
    if counter not in COUNTERS:
        raise ValueError(counter)
    day = day or timezone.localdate()
    try:
        # Eigener Savepoint: Ein Fehler hier bricht keine umgebende Transaktion ab.
        with transaction.atomic():
            DemoDailyStat.objects.get_or_create(day=day)
            DemoDailyStat.objects.filter(day=day).update(**{counter: F(counter) + 1})
    except DatabaseError:
        logger.warning("Demo-Kennzahl %s konnte nicht gezählt werden.", counter, exc_info=True)


def record_start() -> None:
    """Nach dem Anlegen einer Demo-Wache (``start_demo``)."""
    _bump("started")


def record_feedback() -> None:
    """Nach einer gespeicherten Rückmeldung, nur auf Instanzen mit Demo-Wachen."""
    if _sandbox_enabled():
        _bump("feedback")


def record_purge(sandbox) -> None:
    """Vor dem Löschen einer Demo-Wache: War der Rundgang vollständig?

    Gezählt wird für den Tag, an dem die Demo begann, damit „gestartet“ und
    „Rundgang abgeschlossen“ vergleichbar bleiben.
    """
    from .demo_sandbox import _tour_flags

    try:
        # Ohne Anfrage aus den Daten der Wache bestimmt; Schritt 1 (Übersicht)
        # ist immer erledigt. Eigener Savepoint: Ein Abfragefehler darf die
        # umgebende Lösch-Transaktion (PostgreSQL) nicht abbrechen.
        with transaction.atomic():
            complete = all(_tour_flags(sandbox).values())
    except Exception:  # noqa: BLE001 - eine Statistik darf das Löschen nie verhindern
        logger.warning("Rundgang der Demo %s nicht auswertbar.", sandbox.token, exc_info=True)
        return
    if complete:
        _bump("tour_completed", timezone.localdate(sandbox.created_at))


def totals(days: int, today=None) -> dict:
    """Summen der letzten ``days`` Tage (einschließlich heute)."""
    today = today or timezone.localdate()
    since = today - timedelta(days=days - 1)
    sums = DemoDailyStat.objects.filter(day__gte=since, day__lte=today).aggregate(
        **{name: Sum(name) for name in COUNTERS}
    )
    result = {name: sums[name] or 0 for name in COUNTERS}
    result["days"] = days
    result["tour_share"] = round(100 * result["tour_completed"] / result["started"]) if result["started"] else None
    return result


def recent_days(days: int = 14, today=None) -> list[dict]:
    """Ein Eintrag je Tag, auch für Tage ohne Demo (neuester zuerst)."""
    today = today or timezone.localdate()
    since = today - timedelta(days=days - 1)
    stored = {row.day: row for row in DemoDailyStat.objects.filter(day__gte=since, day__lte=today)}
    rows = []
    for offset in range(days):
        day = today - timedelta(days=offset)
        row = stored.get(day)
        rows.append({"day": day, **{name: getattr(row, name, 0) if row else 0 for name in COUNTERS}})
    return rows


def active_count() -> int:
    from .demo_sandbox import active_sandboxes

    return active_sandboxes().count()


def active_for_landing() -> int:
    """Laufende Demos für die Startseite: 60 s zwischengespeichert, unter drei 0."""
    if not _sandbox_enabled():
        return 0
    count = cache.get(ACTIVE_CACHE_KEY)
    if count is None:
        count = active_count()
        cache.set(ACTIVE_CACHE_KEY, count, ACTIVE_CACHE_SECONDS)
    return count if count >= ACTIVE_MINIMUM else 0


def operator_summary() -> dict | None:
    """Karte für den Feedback-Posteingang; ``None`` ohne Demo-Wachen."""
    if not _sandbox_enabled():
        return None
    from django.db.models import Avg, Count

    from .feedback_models import Feedback

    since = timezone.now() - timedelta(days=30)
    rating = Feedback.objects.filter(created_at__gte=since, rating__isnull=False).aggregate(
        average=Avg("rating"), count=Count("id"),
    )
    return {
        "active": active_count(),
        "week": totals(7),
        "month": totals(30),
        "days": recent_days(14),
        "rating": rating if rating["count"] else None,
    }
