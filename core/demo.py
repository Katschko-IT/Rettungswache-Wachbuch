"""Demo mode helpers and sample data for local testing / presentations.

Creates fictional station operations data only — no patient, alarm or duty-plan data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.db import connection, transaction
from django.utils import timezone

from .models import (
    BirthdayPreference,
    CalendarEvent,
    ChatMessage,
    Checklist,
    ChecklistCompletion,
    ChecklistItem,
    CoffeeEntry,
    HandoverEntry,
    HandoverRevision,
    Membership,
    Station,
    StationTask,
    StationTaskCompletion,
)
from .demo_modules import reset_module_demo, seed_module_demo
from .services import audit, handover_snapshot
from .task_board import ensure_default_station_tasks

DEMO_MARKER = "[Demo]"
DEMO_PASSWORD_DEFAULT = "Demo-Passwort-12345"

DEMO_ACCOUNTS = (
    {
        "username": "demo-admin",
        "first_name": "Alex",
        "last_name": "Admin",
        "role": Membership.Role.ADMIN,
        "label": "Master-Admin",
    },
    {
        "username": "demo-schicht",
        "first_name": "Samira",
        "last_name": "Schicht",
        "role": Membership.Role.SHIFT_LEAD,
        "label": "Schichtleitung",
    },
    {
        "username": "demo-kasse",
        "first_name": "Kai",
        "last_name": "Kasse",
        "role": Membership.Role.CASHIER,
        "label": "Kassenwart",
    },
    {
        "username": "demo-mitglied",
        "first_name": "Mara",
        "last_name": "Mitglied",
        "role": Membership.Role.MEMBER,
        "label": "Mitglied",
    },
    {
        "username": "demo-audit",
        "first_name": "Andi",
        "last_name": "Audit",
        "role": Membership.Role.AUDITOR,
        "label": "Auditor",
    },
)


@dataclass
class DemoLoadResult:
    station: Station
    created_users: int = 0
    created_handovers: int = 0
    skipped: bool = False
    reset: bool = False


def demo_mode_enabled() -> bool:
    return bool(getattr(settings, "DEMO_MODE", False))


def demo_password() -> str:
    value = (getattr(settings, "DEMO_PASSWORD", None) or DEMO_PASSWORD_DEFAULT).strip()
    return value or DEMO_PASSWORD_DEFAULT


def demo_accounts_for_display():
    password = demo_password()
    return [
        {
            "username": account["username"],
            "label": account["label"],
            "password": password,
        }
        for account in DEMO_ACCOUNTS
    ]


def _ensure_station() -> Station:
    station = Station.get_default()
    station.name = getattr(settings, "DEFAULT_STATION_NAME", None) or station.name
    if "Demo" not in station.name and "Muster" not in station.name:
        station.name = "Demo-Wache Musterstadt"
    station.calendar_enabled = True
    station.birthdays_enabled = True
    station.coffee_enabled = True
    station.tasks_enabled = True
    station.chat_enabled = True
    station.holidays_enabled = True
    station.checklists_enabled = True
    # Feeds stay opt-in / off unless explicitly configured.
    station.is_active = True
    station.save()
    ensure_default_station_tasks(station)
    return station


def _demo_usernames():
    return [account["username"] for account in DEMO_ACCOUNTS]


def _raw_delete(sql: str, params: list):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)


def reset_demo_data(station: Station):
    """Remove previously seeded demo rows (including append-only demo markers)."""
    usernames = _demo_usernames()
    user_ids = list(User.objects.filter(username__in=usernames).values_list("id", flat=True))
    if user_ids:
        placeholders = ",".join(["%s"] * len(user_ids))
        _raw_delete(
            f"DELETE FROM core_stationtaskcompletion WHERE station_id = %s AND completed_by_id IN ({placeholders})",
            [station.id, *user_ids],
        )
        _raw_delete(
            f"DELETE FROM core_checklistcompletion WHERE station_id = %s AND completed_by_id IN ({placeholders})",
            [station.id, *user_ids],
        )
        _raw_delete(
            f"DELETE FROM core_coffeeentry WHERE station_id = %s AND (created_by_id IN ({placeholders}) OR member_id IN ({placeholders}))",
            [station.id, *user_ids, *user_ids],
        )
        _raw_delete(
            f"DELETE FROM core_chatmessage WHERE station_id = %s AND author_id IN ({placeholders})",
            [station.id, *user_ids],
        )
        _raw_delete(
            f"DELETE FROM core_calendarevent WHERE station_id = %s AND created_by_id IN ({placeholders})",
            [station.id, *user_ids],
        )
        _raw_delete(
            f"DELETE FROM core_birthdaypreference WHERE station_id = %s AND user_id IN ({placeholders})",
            [station.id, *user_ids],
        )
        _raw_delete(
            f"""
            DELETE FROM core_handoverrevision
            WHERE handover_id IN (
              SELECT id FROM core_handoverentry
              WHERE station_id = %s AND (title LIKE %s OR author_id IN ({placeholders}))
            )
            """,
            [station.id, f"{DEMO_MARKER}%", *user_ids],
        )
        _raw_delete(
            f"DELETE FROM core_handoverentry WHERE station_id = %s AND (title LIKE %s OR author_id IN ({placeholders}))",
            [station.id, f"{DEMO_MARKER}%", *user_ids],
        )
        _raw_delete(
            f"DELETE FROM core_auditevent WHERE station_id = %s AND (actor_id IN ({placeholders}) OR action LIKE %s)",
            [station.id, *user_ids, "demo.%"],
        )
    ChecklistItem.objects.filter(checklist__station=station, checklist__title__startswith=DEMO_MARKER).delete()
    Checklist.objects.filter(station=station, title__startswith=DEMO_MARKER).delete()
    reset_module_demo(station)


def _ensure_users(station: Station, password: str) -> tuple[dict[str, User], int]:
    users = {}
    created = 0
    for account in DEMO_ACCOUNTS:
        user, was_created = User.objects.get_or_create(
            username=account["username"],
            defaults={
                "first_name": account["first_name"],
                "last_name": account["last_name"],
                "is_active": True,
            },
        )
        if was_created:
            created += 1
        user.first_name = account["first_name"]
        user.last_name = account["last_name"]
        user.is_active = True
        user.set_password(password)
        user.save()
        Membership.objects.update_or_create(
            user=user,
            station=station,
            defaults={"role": account["role"], "is_active": True},
        )
        users[account["username"]] = user
    return users, created


def _seed_content(station: Station, users: dict[str, User]) -> int:
    admin = users["demo-admin"]
    lead = users["demo-schicht"]
    cashier = users["demo-kasse"]
    member = users["demo-mitglied"]
    now = timezone.now()

    if HandoverEntry.objects.filter(station=station, title__startswith=DEMO_MARKER).exists():
        return 0

    handovers_spec = [
        {
            "author": lead,
            "category": HandoverEntry.Category.MATERIAL,
            "priority": HandoverEntry.Priority.URGENT,
            "status": HandoverEntry.Status.OPEN,
            "title": f"{DEMO_MARKER} Sauerstoffflasche tauschen",
            "details": "Reserve im Gerätewagen prüfen. Keine Patientendaten.",
        },
        {
            "author": member,
            "category": HandoverEntry.Category.VEHICLE,
            "priority": HandoverEntry.Priority.IMPORTANT,
            "status": HandoverEntry.Status.IN_PROGRESS,
            "title": f"{DEMO_MARKER} RTW 1 – Tankstand niedrig",
            "details": "Nächste Gelegenheit tanken. Kilometerstand laut Bordbuch.",
        },
        {
            "author": admin,
            "category": HandoverEntry.Category.STATION,
            "priority": HandoverEntry.Priority.NORMAL,
            "status": HandoverEntry.Status.OPEN,
            "title": f"{DEMO_MARKER} Spülmaschine entkalken",
            "details": "Mittel liegt im Hauswirtschaftsschrank.",
        },
        {
            "author": lead,
            "category": HandoverEntry.Category.SAFETY,
            "priority": HandoverEntry.Priority.IMPORTANT,
            "status": HandoverEntry.Status.DONE,
            "title": f"{DEMO_MARKER} Beleuchtung Hof repariert",
            "details": "Lampe getauscht, wieder hell.",
        },
    ]
    created = 0
    for spec in handovers_spec:
        handover = HandoverEntry.objects.create(
            station=station,
            category=spec["category"],
            priority=spec["priority"],
            status=spec["status"],
            title=spec["title"],
            details=spec["details"],
            author=spec["author"],
            completed_at=now if spec["status"] == HandoverEntry.Status.DONE else None,
        )
        HandoverRevision.objects.create(
            handover=handover,
            version=handover.version,
            snapshot=handover_snapshot(handover),
            changed_by=spec["author"],
        )
        created += 1

    CalendarEvent.objects.create(
        station=station,
        title=f"{DEMO_MARKER} Dienstbesprechung",
        description="Kurzes Team-Update im Schulungsraum.",
        starts_at=now + timedelta(days=1, hours=2),
        ends_at=now + timedelta(days=1, hours=3),
        created_by=lead,
    )
    CalendarEvent.objects.create(
        station=station,
        title=f"{DEMO_MARKER} Geräteunterweisung",
        description="Auffrischung für neue Kolleginnen und Kollegen.",
        starts_at=now + timedelta(days=3, hours=10),
        ends_at=now + timedelta(days=3, hours=12),
        created_by=admin,
    )

    CoffeeEntry.objects.create(
        station=station,
        member=member,
        amount_cents=1000,
        reason=f"{DEMO_MARKER} Einzahlung Mara",
        created_by=cashier,
    )
    CoffeeEntry.objects.create(
        station=station,
        member=lead,
        amount_cents=-250,
        reason=f"{DEMO_MARKER} Verbrauch Samira",
        created_by=cashier,
    )

    checklist = Checklist.objects.create(
        station=station,
        title=f"{DEMO_MARKER} Fahrzeugcheck RTW",
        description="Wiederkehrende Sichtprüfung vor Schichtbeginn.",
        is_active=True,
    )
    for index, text in enumerate(
        ("Reifen und Beleuchtung", "Medizinprodukteliste vollständig", "Tankkarte vorhanden"),
        start=1,
    ):
        ChecklistItem.objects.create(checklist=checklist, text=text, position=index)
    ChecklistCompletion.objects.create(
        station=station,
        checklist=checklist,
        completed_by=member,
        note=f"{DEMO_MARKER} Vormittag erledigt",
    )

    Checklist.objects.create(
        station=station,
        title=f"{DEMO_MARKER} Wachenrundgang",
        description="Abendlicher Sicherheitsrundgang.",
        is_active=True,
    )

    BirthdayPreference.objects.update_or_create(
        user=member,
        station=station,
        defaults={
            "day": 14,
            "month": 3,
            "is_visible": True,
            "consented_at": now,
            "withdrawn_at": None,
        },
    )
    BirthdayPreference.objects.update_or_create(
        user=lead,
        station=station,
        defaults={
            "day": 2,
            "month": 11,
            "is_visible": True,
            "consented_at": now,
            "withdrawn_at": None,
        },
    )

    ChatMessage.objects.create(
        station=station,
        author=lead,
        body=f"{DEMO_MARKER} Wer übernimmt heute den Fahrzeugcheck?",
        is_encrypted=False,
    )
    ChatMessage.objects.create(
        station=station,
        author=member,
        body=f"{DEMO_MARKER} Ich mache den Check nach dem Mittag.",
        is_encrypted=False,
    )

    daily = StationTask.objects.filter(station=station, band=StationTask.Band.DAILY, is_active=True).first()
    if daily:
        StationTaskCompletion.objects.get_or_create(
            task=daily,
            work_date=timezone.localdate(),
            defaults={"station": station, "completed_by": member, "note": DEMO_MARKER},
        )

    seed_module_demo(station, users)

    audit(admin, station, "demo.seeded", station, {
        "fields": ["handovers", "calendar", "coffee", "checklists", "chat", "modules"],
        "marker": DEMO_MARKER,
    })
    return created


@transaction.atomic
def load_demo_data(*, reset: bool = False, force: bool = False) -> DemoLoadResult:
    """Load fictional sample data. Idempotent unless reset/force."""
    station = _ensure_station()
    password = demo_password()

    already = User.objects.filter(username="demo-admin").exists() and HandoverEntry.objects.filter(
        station=station, title__startswith=DEMO_MARKER
    ).exists()
    if already and not reset and not force:
        users, created_users = _ensure_users(station, password)
        return DemoLoadResult(station=station, created_users=created_users, skipped=True)

    if reset:
        reset_demo_data(station)

    users, created_users = _ensure_users(station, password)
    created_handovers = _seed_content(station, users)
    return DemoLoadResult(
        station=station,
        created_users=created_users,
        created_handovers=created_handovers,
        skipped=False,
        reset=reset,
    )
