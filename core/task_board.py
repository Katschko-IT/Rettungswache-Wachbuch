"""Hilfen fuer Tagesaufgaben analog zur Wandtafel."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _lazy

from .models import Station, StationTask, StationTaskCompletion
from .services import audit


DEFAULT_TASKS = (
    # Gruene Zone: taegliche Routine
    (_lazy("Fahrzeugcheck"), StationTask.Band.DAILY, None, "", 10),
    (_lazy("Gerätekontrolle"), StationTask.Band.DAILY, None, "", 20),
    (_lazy("Hygiene / Desinfektion"), StationTask.Band.DAILY, None, "", 30),
    (_lazy("Küche / Aufenthaltsraum"), StationTask.Band.DAILY, None, "", 40),
    (_lazy("Wäsche / Müll"), StationTask.Band.DAILY, None, "", 50),
    # Gelbe Zone: Wochentagsrotation
    (_lazy("Sauger und Tücher waschen"), StationTask.Band.WEEKDAY, 0, "", 10),
    (_lazy("Materialbestellung"), StationTask.Band.WEEKDAY, 1, "", 10),
    (_lazy("Küche und Kühlschrank"), StationTask.Band.WEEKDAY, 2, "", 10),
    (_lazy("Technischer Fahrzeugcheck"), StationTask.Band.WEEKDAY, 3, "", 10),
    (_lazy("Desinfektionsmittel auffüllen"), StationTask.Band.WEEKDAY, 4, "", 10),
    (_lazy("Tiefenreinigung / Wochenabschluss"), StationTask.Band.WEEKDAY, 5, "", 10),
    (_lazy("Wochenbericht und Lagerblick"), StationTask.Band.WEEKDAY, 6, "", 10),
    # Blaue Zone: zusaetzliche / individuelle Punkte
    (
        _lazy("Monatliche Fahrzeugdurchsicht"),
        StationTask.Band.EXTRA,
        None,
        _lazy("Typisch am 1. Freitag im Monat – analog zum Wandbogen."),
        10,
    ),
    (
        _lazy("Individuelle Aufgabe"),
        StationTask.Band.EXTRA,
        None,
        _lazy("Frei nutzbar für einmalige Wachenaufgaben ohne Patientendaten."),
        20,
    ),
)


def ensure_default_station_tasks(station):
    """Legt die Standardvorlage einmalig und parallelitätssicher an."""
    with transaction.atomic():
        # Lock the stable station row before checking for tasks. A lock on a
        # non-existing StationTask row would not serialize two first requests.
        Station.objects.select_for_update().get(pk=station.pk)
        if StationTask.objects.filter(station=station).exists():
            return 0
        created = 0
        for title, band, weekday, notes, sort_order in DEFAULT_TASKS:
            task = StationTask(
                station=station,
                title=str(title),
                band=band,
                weekday=weekday,
                notes=str(notes),
                sort_order=sort_order,
            )
            # Wiederholung passend zum Band setzen, sonst gilt eine
            # Wochentagsvorlage jeden Tag.
            if band == StationTask.Band.WEEKDAY and weekday is not None:
                task.repeat = StationTask.Repeat.WEEKLY
                task.set_weekdays([weekday])
            else:
                task.repeat = StationTask.Repeat.DAILY
            task.save()
            created += 1
        return created


def week_monday(value: date) -> date:
    return value - timedelta(days=value.weekday())


def iso_week_label(value: date) -> str:
    return _("KW %(week)s") % {"week": value.isocalendar().week}


def tasks_for_date(station, work_date: date):
    tasks = list(
        StationTask.objects.filter(station=station, is_active=True).order_by(
            "band", "weekday", "sort_order", "title"
        )
    )
    return [task for task in tasks if task.applies_to_date(work_date)]


def completions_for_dates(station, dates):
    return {
        (item.task_id, item.work_date): item
        for item in StationTaskCompletion.objects.filter(
            station=station,
            work_date__in=dates,
        ).select_related("completed_by", "task")
    }


def day_board(station, work_date: date):
    tasks = tasks_for_date(station, work_date)
    done_map = completions_for_dates(station, [work_date])
    groups = {
        StationTask.Band.DAILY: [],
        StationTask.Band.WEEKDAY: [],
        StationTask.Band.EXTRA: [],
    }
    done_count = 0
    for task in tasks:
        completion = done_map.get((task.pk, work_date))
        if not completion and task.repeat == StationTask.Repeat.ONCE and task.due_date:
            completion = task.completions.first()
        if completion:
            done_count += 1
        groups[task.band].append({
            "task": task,
            "completion": completion,
            "urgency": task.get_urgency(work_date),
        })

    def _urgency_sort_key(item):
        is_done = 1 if item["completion"] else 0
        urg = item["urgency"]
        level_map = {
            "overdue": 0,
            "critical": 1,
            "warning": 2,
            "ok": 3,
            "none": 4,
        }
        level_order = level_map.get(urg.get("level"), 4)
        days = urg.get("days_left") if urg.get("days_left") is not None else 9999
        return (is_done, level_order, days, item["task"].sort_order, item["task"].title)

    for band in groups:
        groups[band].sort(key=_urgency_sort_key)

    total = len(tasks)
    return {
        "work_date": work_date,
        "week_label": iso_week_label(work_date),
        "groups": groups,
        "total": total,
        "done_count": done_count,
        "open_count": total - done_count,
    }


def week_board(station, any_day: date):
    monday = week_monday(any_day)
    days = [monday + timedelta(days=offset) for offset in range(7)]
    tasks = list(
        StationTask.objects.filter(station=station, is_active=True).order_by(
            "band", "weekday", "sort_order", "title"
        )
    )
    done_map = completions_for_dates(station, days)
    daily = [task for task in tasks if task.band == StationTask.Band.DAILY]
    weekday_rows = [task for task in tasks if task.band == StationTask.Band.WEEKDAY]
    extras = [task for task in tasks if task.band == StationTask.Band.EXTRA]
    columns = []
    for day in days:
        day_tasks = []
        for task in tasks:
            if not task.applies_to_date(day):
                continue
            completion = done_map.get((task.pk, day))
            if not completion and task.repeat == StationTask.Repeat.ONCE and task.due_date:
                completion = task.completions.first()
            day_tasks.append({
                "task": task,
                "completion": completion,
                "urgency": task.get_urgency(day),
            })
        columns.append({
            "date": day,
            "is_today": day == timezone.localdate(),
            "tasks": day_tasks,
            "done_count": sum(1 for item in day_tasks if item["completion"]),
            "total": len(day_tasks),
        })
    return {
        "monday": monday,
        "week_label": iso_week_label(monday),
        "columns": columns,
        "daily": daily,
        "weekday_rows": weekday_rows,
        "extras": extras,
    }


def month_tasks(station, any_day: date):
    """Monatliche Aufgaben im Monat von ``any_day`` mit Termin und Erledigt-Status."""
    first = any_day.replace(day=1)
    last_day = calendar.monthrange(first.year, first.month)[1]
    days = [first + timedelta(days=offset) for offset in range(last_day)]
    tasks = StationTask.objects.filter(
        station=station, is_active=True, repeat=StationTask.Repeat.MONTHLY
    ).order_by("month_day", "sort_order", "title")
    done_map = completions_for_dates(station, days)
    items = []
    for task in tasks:
        for day in days:
            if task.applies_to_date(day):
                items.append({
                    "task": task,
                    "date": day,
                    "completion": done_map.get((task.pk, day)),
                    "urgency": task.get_urgency(day),
                })
    return items


def toggle_task_completion(*, task, membership, work_date: date, mark_done: bool):
    station = membership.station
    with transaction.atomic():
        # Serialize all completion changes for the same task, including the
        # first completion where no row exists yet.
        locked_task = StationTask.objects.select_for_update().get(
            pk=task.pk,
            station=station,
            is_active=True,
        )
        existing = (
            StationTaskCompletion.objects.select_for_update()
            .filter(task=locked_task, work_date=work_date)
            .first()
        )
        if mark_done:
            if existing:
                return existing
            completion = StationTaskCompletion.objects.create(
                task=locked_task,
                station=station,
                work_date=work_date,
                completed_by=membership.user,
            )
            audit(membership.user, station, "station_task.completed", completion, {
                "fields": ["task", "work_date"],
            })
            return completion
        if existing:
            audit(membership.user, station, "station_task.reopened", existing, {
                "fields": ["task", "work_date"],
            })
            existing.delete()
    return None
