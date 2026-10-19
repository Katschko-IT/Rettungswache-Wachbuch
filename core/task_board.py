"""Hilfen fuer Tagesaufgaben analog zur Wandtafel."""

from __future__ import annotations

from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from .models import Station, StationTask, StationTaskCompletion
from .services import audit


DEFAULT_TASKS = (
    # Gruene Zone: taegliche Routine
    ("Fahrzeugcheck", StationTask.Band.DAILY, None, "", 10),
    ("Geraetekontrolle", StationTask.Band.DAILY, None, "", 20),
    ("Hygiene / Desinfektion", StationTask.Band.DAILY, None, "", 30),
    ("Kueche / Aufenthaltsraum", StationTask.Band.DAILY, None, "", 40),
    ("Waesche / Muell", StationTask.Band.DAILY, None, "", 50),
    # Gelbe Zone: Wochentagsrotation
    ("Sauger und Tuecher waschen", StationTask.Band.WEEKDAY, 0, "", 10),
    ("Materialbestellung", StationTask.Band.WEEKDAY, 1, "", 10),
    ("Kueche und Kuehlschrank", StationTask.Band.WEEKDAY, 2, "", 10),
    ("Technischer Fahrzeugcheck", StationTask.Band.WEEKDAY, 3, "", 10),
    ("Desinfektionsmittel auffuellen", StationTask.Band.WEEKDAY, 4, "", 10),
    ("Tiefenreinigung / Wochenabschluss", StationTask.Band.WEEKDAY, 5, "", 10),
    ("Wochenbericht und Lagerblick", StationTask.Band.WEEKDAY, 6, "", 10),
    # Blaue Zone: zusaetzliche / individuelle Punkte
    (
        "Monatliche Fahrzeugdurchsicht",
        StationTask.Band.EXTRA,
        None,
        "Typisch am 1. Freitag im Monat – analog zum Wandbogen.",
        10,
    ),
    (
        "Individuelle Aufgabe",
        StationTask.Band.EXTRA,
        None,
        "Frei nutzbar für einmalige Wachenaufgaben ohne Patientendaten.",
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
            StationTask.objects.create(
                station=station,
                title=title,
                band=band,
                weekday=weekday,
                notes=notes,
                sort_order=sort_order,
            )
            created += 1
        return created


def week_monday(value: date) -> date:
    return value - timedelta(days=value.weekday())


def iso_week_label(value: date) -> str:
    return f"KW {value.isocalendar().week}"


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
        if completion:
            done_count += 1
        groups[task.band].append({"task": task, "completion": completion})
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
        for task in daily + [t for t in weekday_rows if t.weekday == day.weekday()] + extras:
            if not task.applies_to_date(day):
                continue
            completion = done_map.get((task.pk, day))
            day_tasks.append({"task": task, "completion": completion})
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
