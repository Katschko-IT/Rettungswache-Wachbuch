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
from .services import audit, handover_snapshot
from .task_board import ensure_default_station_tasks
from .wachalltag_models import (
    AssetEvent,
    ChecklistSchedule,
    Defect,
    DefectEvent,
    InventoryEvent,
    InventoryItem,
    StationAsset,
)

DEMO_MARKER = "[Demo]"
DEMO_PASSWORD_DEFAULT = "Demo-Passwort-12345"

# Fixed, documented login of the shared public-demo visitor account. Only used
# while ``DEMO_PUBLIC_MODE`` is on. The normal login form is the sole way in;
# the passwordless one-click ``demo_login`` route is disabled in that mode.
# Case-sensitive: username ``Demo``, password ``Demo``.
DEMO_PUBLIC_USERNAME = "Demo"
DEMO_PUBLIC_PASSWORD = "Demo"

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
    # DEMO_PUBLIC_MODE is a strict superset: enabling it turns a normal demo on.
    return bool(
        getattr(settings, "DEMO_MODE", False)
        or getattr(settings, "DEMO_PUBLIC_MODE", False)
    )


def demo_public_mode_enabled() -> bool:
    """True on the public, internet-facing demo instance."""
    return bool(getattr(settings, "DEMO_PUBLIC_MODE", False))


def demo_public_username() -> str:
    """Documented username of the shared public-demo account (empty if off)."""
    return DEMO_PUBLIC_USERNAME if demo_public_mode_enabled() else ""


def demo_public_password() -> str:
    """Documented password of the shared public-demo account (empty if off)."""
    return DEMO_PUBLIC_PASSWORD if demo_public_mode_enabled() else ""


def demo_protected_usernames() -> frozenset[str]:
    """Demo accounts that visitors must not be able to disable or re-role."""
    return frozenset(account["username"] for account in DEMO_ACCOUNTS)


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
    """Demo login names whose seeded rows ``reset_demo_data`` should remove.

    On the public demo the shared visitor account (``Demo``) is included so a
    reset also clears any content a visitor produced while logged in.
    """
    usernames = [account["username"] for account in DEMO_ACCOUNTS]
    if demo_public_mode_enabled() and DEMO_PUBLIC_USERNAME not in usernames:
        usernames.append(DEMO_PUBLIC_USERNAME)
    return usernames


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
    # Operative Demo-Module (Mängel, Fuhrpark/Geräte, Inventar, Prüfintervalle).
    # Append-only Ereignistabellen lassen sich nur per Roh-SQL entfernen; die
    # Marker-Auswahl stellt sicher, dass nur Demodaten betroffen sind.
    marker_like = f"{DEMO_MARKER}%"
    _raw_delete(
        "DELETE FROM core_defectattachment WHERE station_id = %s AND defect_id IN "
        "(SELECT id FROM core_defect WHERE station_id = %s AND title LIKE %s)",
        [station.id, station.id, marker_like],
    )
    _raw_delete(
        "DELETE FROM core_defectevent WHERE station_id = %s AND defect_id IN "
        "(SELECT id FROM core_defect WHERE station_id = %s AND title LIKE %s)",
        [station.id, station.id, marker_like],
    )
    _raw_delete(
        "DELETE FROM core_defect WHERE station_id = %s AND title LIKE %s",
        [station.id, marker_like],
    )
    _raw_delete(
        "DELETE FROM core_assetevent WHERE station_id = %s AND asset_id IN "
        "(SELECT id FROM core_stationasset WHERE station_id = %s AND label LIKE %s)",
        [station.id, station.id, marker_like],
    )
    _raw_delete(
        "DELETE FROM core_stationasset WHERE station_id = %s AND label LIKE %s",
        [station.id, marker_like],
    )
    _raw_delete(
        "DELETE FROM core_inventoryevent WHERE station_id = %s AND item_id IN "
        "(SELECT id FROM core_inventoryitem WHERE station_id = %s AND label LIKE %s)",
        [station.id, station.id, marker_like],
    )
    _raw_delete(
        "DELETE FROM core_inventoryitem WHERE station_id = %s AND label LIKE %s",
        [station.id, marker_like],
    )
    _raw_delete(
        "DELETE FROM core_checklistschedule WHERE station_id = %s AND checklist_id IN "
        "(SELECT id FROM core_checklist WHERE station_id = %s AND title LIKE %s)",
        [station.id, station.id, marker_like],
    )
    ChecklistItem.objects.filter(checklist__station=station, checklist__title__startswith=DEMO_MARKER).delete()
    Checklist.objects.filter(station=station, title__startswith=DEMO_MARKER).delete()


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


def _ensure_public_demo_user(station: Station) -> User:
    """Create/refresh the shared public-demo login (username/password ``Demo``).

    Only ever called while ``DEMO_PUBLIC_MODE`` is on. The account holds an
    active admin membership so visitors can exercise the operational modules;
    ``PublicDemoGuardMiddleware`` still keeps every management route out of
    reach. It is never a Django staff/superuser account.
    """
    user, _ = User.objects.get_or_create(
        username=DEMO_PUBLIC_USERNAME,
        defaults={"first_name": "Demo", "last_name": "Zugang", "is_active": True},
    )
    user.first_name = "Demo"
    user.last_name = "Zugang"
    user.is_active = True
    user.is_staff = False
    user.is_superuser = False
    user.set_password(DEMO_PUBLIC_PASSWORD)
    user.save()
    Membership.objects.update_or_create(
        user=user,
        station=station,
        defaults={"role": Membership.Role.ADMIN, "is_active": True},
    )
    return user


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

    round_checklist = Checklist.objects.create(
        station=station,
        title=f"{DEMO_MARKER} Wachenrundgang",
        description="Abendlicher Sicherheitsrundgang.",
        is_active=True,
    )
    for index, text in enumerate(
        ("Türen und Fenster geschlossen", "Beleuchtung ausgeschaltet", "Müll entsorgt"),
        start=1,
    ):
        ChecklistItem.objects.create(checklist=round_checklist, text=text, position=index)

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

    _seed_operational_demo_data(
        station,
        admin=admin,
        lead=lead,
        member=member,
        checklist=checklist,
        round_checklist=round_checklist,
        now=now,
    )

    audit(admin, station, "demo.seeded", station, {
        "fields": [
            "handovers",
            "calendar",
            "coffee",
            "checklists",
            "chat",
            "defects",
            "assets",
            "inventory",
            "checklist_schedules",
        ],
        "marker": DEMO_MARKER,
    })
    return created


def _seed_operational_demo_data(
    station, *, admin, lead, member, checklist, round_checklist, now
) -> None:
    """Fictional rows for the operative modules (defects, assets, inventory).

    All titles/ids/labels carry ``DEMO_MARKER`` so ``reset_demo_data`` can find
    and remove exactly this data. Append-only event rows are written the same
    way the application creates them.
    """
    # Fuhrpark und Geräte (Fahrzeug-/Gerätestatus).
    assets_spec = [
        ("demo-rtw-1", StationAsset.Kind.VEHICLE, StationAsset.Status.LIMITED,
         "Blaulicht hinten links ohne Funktion, Werkstattauftrag offen."),
        ("demo-rtw-2", StationAsset.Kind.VEHICLE, StationAsset.Status.READY, ""),
        ("demo-absaugpumpe", StationAsset.Kind.DEVICE, StationAsset.Status.WORKSHOP,
         "Wartung in der Werkstatt."),
        ("demo-schluessel-hauswirtschaft", StationAsset.Kind.KEY, StationAsset.Status.READY, ""),
    ]
    for asset_id, kind, status, note in assets_spec:
        asset = StationAsset.objects.create(
            station=station,
            asset_id=asset_id,
            label=f"{DEMO_MARKER} {asset_id.removeprefix('demo-').replace('-', ' ').title()}",
            kind=kind,
            status=status,
            note=note,
            updated_by=lead,
        )
        AssetEvent.objects.create(
            asset=asset,
            station=station,
            from_status="",
            to_status=status,
            note=note,
            actor=lead,
        )

    # Inventar / Ausgabe (wer hat was).
    inventory_spec = [
        ("demo-funkgeraet-1", InventoryItem.Kind.DEVICE, member),
        ("demo-schluessel-hof", InventoryItem.Kind.KEY, lead),
        ("demo-funkgeraet-2", InventoryItem.Kind.DEVICE, None),
    ]
    for item_id, kind, holder in inventory_spec:
        item = InventoryItem.objects.create(
            station=station,
            item_id=item_id,
            label=f"{DEMO_MARKER} {item_id.removeprefix('demo-').replace('-', ' ').title()}",
            kind=kind,
            holder=holder,
            checked_out_at=now if holder else None,
            updated_by=lead,
        )
        if holder is not None:
            InventoryEvent.objects.create(
                item=item,
                station=station,
                action=InventoryEvent.Action.CHECKOUT,
                actor=lead,
                holder=holder,
            )

    # Mängel in allen Statusstufen.
    defects_spec = [
        {
            "title": f"{DEMO_MARKER} RTW 1 – Blaulicht hinten links defekt",
            "description": "Sichtprüfung vor Schichtbeginn. Werkstatttermin angefragt.",
            "asset_ref": "demo-rtw-1",
            "category": Defect.Category.VEHICLE,
            "priority": Defect.Priority.URGENT,
            "status": Defect.Status.IN_PROGRESS,
            "owner": lead,
            "due_at": now + timedelta(days=1),
        },
        {
            "title": f"{DEMO_MARKER} Absaugpumpe dicht prüfen",
            "description": "Dichtung wirkt porös, Funktion eingeschränkt.",
            "asset_ref": "demo-absaugpumpe",
            "category": Defect.Category.DEVICE,
            "priority": Defect.Priority.IMPORTANT,
            "status": Defect.Status.OPEN,
            "owner": member,
            "due_at": now + timedelta(days=3),
        },
        {
            "title": f"{DEMO_MARKER} Flurbeleuchtung Aufenthaltsraum flackert",
            "description": "Leuchtmittel vermutlich am Lebensende.",
            "asset_ref": "",
            "category": Defect.Category.FACILITY,
            "priority": Defect.Priority.NORMAL,
            "status": Defect.Status.WAITING,
            "owner": admin,
            "due_at": now + timedelta(days=7),
        },
        {
            "title": f"{DEMO_MARKER} Schlüsselbund Hauswirtschaft vollzählig",
            "description": "Vollzähligkeit bestätigt, keine Maßnahme nötig.",
            "asset_ref": "demo-schluessel-hauswirtschaft",
            "category": Defect.Category.KEY,
            "priority": Defect.Priority.NORMAL,
            "status": Defect.Status.DONE,
            "owner": member,
            "due_at": None,
        },
    ]
    for spec in defects_spec:
        defect = Defect.objects.create(
            station=station,
            title=spec["title"],
            description=spec["description"],
            asset_ref=spec["asset_ref"],
            category=spec["category"],
            priority=spec["priority"],
            status=spec["status"],
            owner=spec["owner"],
            due_at=spec["due_at"],
            created_by=admin,
            closed_at=now if spec["status"] == Defect.Status.DONE else None,
        )
        DefectEvent.objects.create(
            defect=defect,
            station=station,
            kind=DefectEvent.Kind.CREATED,
            from_status="",
            to_status=defect.status,
            actor=admin,
        )

    # Wiederkehrende Prüfungen: ein überfälliger und ein anstehender Lauf.
    ChecklistSchedule.objects.create(
        station=station,
        checklist=checklist,
        interval=ChecklistSchedule.Interval.DAILY,
        due_next=now - timedelta(hours=2),
    )
    ChecklistSchedule.objects.create(
        station=station,
        checklist=round_checklist,
        interval=ChecklistSchedule.Interval.WEEKLY,
        due_next=now + timedelta(days=3),
    )


@transaction.atomic
def load_demo_data(*, reset: bool = False, force: bool = False) -> DemoLoadResult:
    """Load fictional sample data. Idempotent unless reset/force."""
    station = _ensure_station()
    password = demo_password()
    public = demo_public_mode_enabled()

    already = User.objects.filter(username="demo-admin").exists() and HandoverEntry.objects.filter(
        station=station, title__startswith=DEMO_MARKER
    ).exists()
    if already and not reset and not force:
        users, created_users = _ensure_users(station, password)
        if public:
            _ensure_public_demo_user(station)
        return DemoLoadResult(station=station, created_users=created_users, skipped=True)

    if reset:
        reset_demo_data(station)

    users, created_users = _ensure_users(station, password)
    if public:
        _ensure_public_demo_user(station)
    created_handovers = _seed_content(station, users)
    return DemoLoadResult(
        station=station,
        created_users=created_users,
        created_handovers=created_handovers,
        skipped=False,
        reset=reset,
    )
