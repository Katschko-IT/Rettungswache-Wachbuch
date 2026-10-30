"""Demo mode helpers and sample data for local testing / presentations.

Creates fictional station operations data only — no patient, alarm or duty-plan data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.db import connection, models, transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import (
    BirthdayPreference,
    CalendarEvent,
    Checklist,
    ChecklistCompletion,
    ChecklistItem,
    CoffeeEntry,
    HandoverAttachment,
    HandoverEntry,
    HandoverRevision,
    Membership,
    NewsAcknowledgement,
    NewsAttachment,
    NewsPost,
    PinboardAttachment,
    PinboardNote,
    Station,
    StationTask,
    StationTaskCompletion,
)
from . import coffee
from .coffee_models import CoffeeCashMovement, CoffeeFund, CoffeeParticipant
from .demo_modules import reset_module_demo, seed_module_demo
from .holidays import holidays_between
from .services import audit, handover_snapshot
from .task_board import ensure_default_station_tasks
from .wachalltag_models import Defect, DefectAttachment, DefectEvent, HandoverAck
from .wiki_services import create_article
from .wiki_models import WikiArticle, WikiRevision

DEMO_MARKER = "[Demo]"
DEMO_PASSWORD_DEFAULT = "Demo-Passwort-12345"

DEMO_ACCOUNTS = (
    {
        "username": "demo-admin",
        "first_name": "Alex",
        "last_name": "Admin",
        "role": Membership.Role.ADMIN,
    },
    {
        "username": "demo-schicht",
        "first_name": "Samira",
        "last_name": "Schicht",
        "role": Membership.Role.SHIFT_LEAD,
    },
    {
        "username": "demo-kasse",
        "first_name": "Kai",
        "last_name": "Kasse",
        "role": Membership.Role.CASHIER,
    },
    {
        "username": "demo-mitglied",
        "first_name": "Mara",
        "last_name": "Mitglied",
        "role": Membership.Role.MEMBER,
    },
    {
        "username": "demo-audit",
        "first_name": "Andi",
        "last_name": "Audit",
        "role": Membership.Role.AUDITOR,
    },
)

# Weitere Kolleginnen und Kollegen der Demo-Wache je Besuch (Rolle Mitglied,
# ohne Zugang). Sie machen Team, Lesebestätigungen und Kaffeekasse glaubhaft.
DEMO_COLLEAGUES = (
    {"key": "jonas", "first_name": "Jonas", "last_name": "Becker"},
    {"key": "lea", "first_name": "Lea", "last_name": "Hoffmann"},
    {"key": "tim", "first_name": "Tim", "last_name": "Schulze"},
    {"key": "nora", "first_name": "Nora", "last_name": "Yilmaz"},
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
            "label": Membership.Role(account["role"]).label,
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
            f"DELETE FROM core_coffeecashmovement WHERE station_id = %s AND (created_by_id IN ({placeholders}) OR witness_id IN ({placeholders}))",
            [station.id, *user_ids, *user_ids],
        )
        CoffeeParticipant.objects.filter(station=station, user_id__in=user_ids).delete()
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
        demo_handovers = HandoverEntry.objects.filter(station=station).filter(
            models.Q(title__startswith=DEMO_MARKER) | models.Q(author_id__in=user_ids)
        )
        HandoverAck.objects.filter(station=station).filter(
            models.Q(handover__in=demo_handovers) | models.Q(user_id__in=user_ids)
        ).delete()
        demo_defects = Defect.objects.filter(station=station, created_by_id__in=user_ids)
        DefectEvent.objects.filter(defect__in=demo_defects).delete()
        DefectAttachment.objects.filter(defect__in=demo_defects).delete()
        demo_defects.delete()
        # Anhänge schützen ihre Einträge (PROTECT): zuerst die Anhänge löschen.
        demo_posts = NewsPost.objects.filter(station=station, created_by_id__in=user_ids)
        NewsAttachment.objects.filter(post__in=demo_posts).delete()
        demo_posts.delete()
        demo_notes = PinboardNote.objects.filter(station=station, author_id__in=user_ids)
        PinboardAttachment.objects.filter(note__in=demo_notes).delete()
        demo_notes.delete()
        HandoverAttachment.objects.filter(handover__in=demo_handovers).delete()
        articles = WikiArticle.objects.filter(station=station, created_by_id__in=user_ids)
        WikiRevision.objects.filter(article__in=articles).delete()
        articles.delete()
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


def insert_at(obj, when):
    """Musterzeile mit Zeitpunkt in der Vergangenheit anlegen.

    ``auto_now``/``auto_now_add`` würden den Zeitpunkt überschreiben, und
    append-only Tabellen dürfen nachträglich nicht geändert werden. Wie beim
    Laden von Fixtures schreibt ``save_base(raw=True)`` die Zeile einmal mit
    den gesetzten Werten. Nur für erfundene Musterdaten: Prüfungen aus
    ``save()`` entfallen dabei, die Werte müssen also schon stimmen.
    """
    for field in obj._meta.concrete_fields:
        if getattr(field, "auto_now", False) or getattr(field, "auto_now_add", False):
            setattr(obj, field.attname, when)
    obj.save_base(raw=True)
    return obj


def local_time(day, hour: int, minute: int = 0):
    """Ortszeit an einem Tag (Sommer-/Winterzeit wie im Kalender)."""
    return timezone.make_aware(datetime.combine(day, time(hour, minute)))


def next_workdays(station, start, count: int) -> list:
    """Die nächsten Werktage ab ``start`` (ohne Wochenende und Feiertage)."""
    region = getattr(station, "holiday_state", "") or "NW"
    off = {item.day for item in holidays_between(start, start + timedelta(days=count * 3 + 14), region=region)}
    days, day = [], start
    while len(days) < count:
        if day.weekday() < 5 and day not in off:
            days.append(day)
        day += timedelta(days=1)
    return days


def _seed_content(station: Station, users: dict[str, User], *, marker: str = DEMO_MARKER, fresh: bool = False) -> int:
    """Musterdaten einer Wache: Übergaben, Termine, Kaffeekasse, Neuigkeiten …

    Alle Zeitpunkte hängen am Besuchszeitpunkt: Übergaben stammen aus den
    letzten Schichten, Termine liegen tagsüber an Werktagen. In der geteilten
    Demo (``load_demo_data``) trägt jeder Titel ``marker``, damit
    ``reset_demo_data`` die Zeilen findet; eine Demo-Wache je Besuch
    (``fresh``) wird als Ganzes gelöscht und braucht keinen Marker.
    """
    admin = users["demo-admin"]
    lead = users["demo-schicht"]
    cashier = users["demo-kasse"]
    member = users["demo-mitglied"]
    crew = [users[f"demo-{colleague['key']}"] for colleague in DEMO_COLLEAGUES if f"demo-{colleague['key']}" in users]
    # Ohne zusätzliche Kolleginnen (geteilte Demo) übernehmen die Rollenkonten.
    jonas, lea, tim, nora = (crew + [lead, member, cashier, admin])[:4]
    now = timezone.now()
    today = timezone.localdate()

    def label(text: str) -> str:
        return f"{marker} {text}" if marker else text

    def ago(hours: float = 0, days: int = 0):
        return now - timedelta(days=days, hours=hours)

    if not fresh and HandoverEntry.objects.filter(station=station, title__startswith=DEMO_MARKER).exists():
        return 0

    # --- Übergaben aus den letzten Schichten -------------------------------
    handovers_spec = [
        (lead, 0.7, "material", "urgent", "open", "Kinder-Notfallset RTW 83-1 unvollständig",
         "Larynxmasken Größe 2 fehlen. Nachschub ist im Zentrallager bestellt; bis dahin das Set aus dem "
         "Reserverucksack nehmen.", [jonas]),
        (jonas, 3, "vehicle", "urgent", "in_progress", "RTW 83-3: Blaulicht hinten links ohne Funktion",
         "Fahrzeug ist außer Dienst. Werkstatttermin ist im Kalender eingetragen, Ersatz ist RTW 83-2.",
         [lead, tim]),
        (member, 5, "vehicle", "important", "open", "RTW 83-1 – Tankstand unter einem Viertel",
         "Nach der letzten Fahrt nicht mehr getankt. Tankkarte liegt im Fahrzeug.", [lea]),
        (lea, 9, "station", "important", "open", "Rolltor Fahrzeughalle 2 schließt nur mit Nachdruck",
         "Haustechnik ist informiert, der Mangel ist angelegt. Bitte das Tor beim Ausfahren im Blick behalten.", []),
        (admin, 14, "station", "normal", "open", "Spülmaschine entkalken",
         "Entkalker steht im Hauswirtschaftsschrank. Die Anleitung liegt im Wiki.", []),
        (tim, 20, "task", "normal", "open", "Wäschesäcke zur Abholung bereitstellen",
         "Die Wäscherei holt werktags zwischen 7 und 9 Uhr ab. Säcke bitte zuknoten und beschriften.", []),
        (lead, 26, "safety", "important", "done", "Beleuchtung Hofeinfahrt repariert",
         "Leuchtmittel getauscht, Bewegungsmelder neu eingestellt.", [jonas, lea]),
        (nora, 31, "material", "normal", "done", "Temperaturprotokoll Medikamentenkühlschrank abgeschlossen",
         "Alle Werte lagen zwischen 2 und 8 °C. Das Protokoll liegt im Ordner Hygiene.", []),
    ]
    created = 0
    for author, hours, category, priority, status, title, details, readers in handovers_spec:
        written = ago(hours)
        handover = insert_at(HandoverEntry(
            station=station, category=category, priority=priority, status=status, title=label(title),
            details=details, author=author,
            completed_at=written + timedelta(hours=3) if status == HandoverEntry.Status.DONE else None,
        ), written)
        if status == HandoverEntry.Status.DONE:
            HandoverEntry.objects.filter(pk=handover.pk).update(updated_at=handover.completed_at)
        insert_at(HandoverRevision(
            handover=handover, version=handover.version, snapshot=handover_snapshot(handover), changed_by=author,
        ), written)
        for index, reader in enumerate(dict.fromkeys(readers)):
            if reader.pk != author.pk:
                insert_at(HandoverAck(station=station, handover=handover, user=reader),
                          min(now, written + timedelta(minutes=25 + 40 * index)))
        created += 1

    # --- Termine: tagsüber an Werktagen ----------------------------------
    briefing = local_time(today, 7) if timezone.localtime(now).hour < 7 else local_time(today, 19)
    earlier = []
    if briefing <= now:
        # Abends bleibt das Briefing von 19 Uhr unter „Heute“ stehen
        # (Sperrbildschirm, Wand-Display); das nächste folgt morgen früh.
        earlier = [(lead, briefing, 15, "Schichtwechsel-Briefing",
                    "Kurz im Aufenthaltsraum: offene Übergaben, Fahrzeugstatus, Besonderheiten.")]
        briefing = local_time(today + timedelta(days=1), 7)
    workdays = next_workdays(station, today + timedelta(days=1), 8)
    events = earlier + [
        (lead, briefing, 15, "Schichtwechsel-Briefing",
         "Kurz im Aufenthaltsraum: offene Übergaben, Fahrzeugstatus, Besonderheiten."),
        (lead, local_time(workdays[0], 8), 60, "RTW 83-3 in die Werkstatt (Blaulicht)",
         "Fahrzeug um 8 Uhr zur Kfz-Werkstatt Rettungsdienst bringen, Ersatzschlüssel liegt in der Schlüsselbox."),
        (admin, local_time(workdays[1], 13, 30), 60, "Dienstbesprechung",
         "Im Schulungsraum. Themen: Dienstplan, Hygieneplan, Fortbildungen."),
        (nora, local_time(workdays[3], 10), 90, "Geräteeinweisung Beatmungsgerät",
         "Einweisung nach MPBetreibV für alle, die noch nicht eingewiesen sind."),
        (admin, local_time(workdays[7], 8), 8 * 60, "Pflichtfortbildung Reanimation",
         "Teil der jährlichen Fortbildung. Anmeldung bei der Wachleitung."),
    ]
    CalendarEvent.objects.bulk_create([
        CalendarEvent(station=station, title=label(title), description=description, starts_at=starts,
                      ends_at=starts + timedelta(minutes=minutes), created_by=author)
        for author, starts, minutes, title, description in events
    ])
    soon = today + timedelta(days=2)
    BirthdayPreference.objects.filter(station=station, user__in=[member, lead]).delete()
    BirthdayPreference.objects.bulk_create([
        BirthdayPreference(user=member, station=station, day=14, month=3, is_visible=True, consented_at=now),
        # Ein Geburtstag kurz nach dem Besuch, damit die Funktion sichtbar ist.
        BirthdayPreference(user=lead, station=station, day=soon.day, month=soon.month, is_visible=True,
                           consented_at=now),
    ])

    # --- Kaffeekasse: Beitrag 5 € im Monat, Verlauf seit drei Monaten -------
    fee = 500
    CoffeeFund.objects.update_or_create(station=station, defaults={"monthly_fee_cents": fee, "reminder_day": 10})
    current = coffee.month_start(coffee.station_today(station))
    first = coffee.add_months(current, -3)
    payers = [admin, lead, cashier, member, *crew]
    CoffeeParticipant.objects.bulk_create([
        CoffeeParticipant(station=station, user=person, since=first, created_by=cashier) for person in payers
    ], ignore_conflicts=True)
    months = [coffee.add_months(first, offset) for offset in range(4)]
    for person in payers:
        for month in months:
            insert_at(CoffeeEntry(
                station=station, member=person, amount_cents=-fee, kind=CoffeeEntry.Kind.FEE, period=month,
                reason=_("Monatsbeitrag %(month)s") % {"month": coffee.month_label(month)},
            ), min(local_time(month, 0, 5), now))
    # (Person, Monat ab Beginn, Tag, Betrag, Weg). Mara hat den laufenden Monat
    # noch offen – Schritt 6 des Rundgangs hakt ihn ab.
    payments = [
        (member, 0, 3, fee, "cash"), (member, 1, 4, fee, "cash"), (member, 2, 2, fee, "cash"),
        (lead, 0, 2, 3 * fee, "transfer"), (lead, 3, 1, fee, "transfer"),
        (cashier, 0, 1, 4 * fee, "cash"),
        (admin, 0, 5, fee, "transfer"), (admin, 1, 6, fee, "transfer"),
    ]
    if crew:
        payments += [
            (jonas, 0, 7, 2 * fee, "transfer"), (jonas, 2, 3, 2 * fee, "transfer"),
            (lea, 0, 4, fee, "cash"), (lea, 1, 3, fee, "cash"), (lea, 2, 5, fee, "cash"), (lea, 3, 1, fee, "cash"),
            (tim, 0, 9, fee, "cash"),
            (nora, 0, 2, 4 * fee, "transfer"),
        ]
    reasons = {"cash": label("Bar in die Kasse"), "transfer": label("Überweisung")}
    cash_paid = []
    for person, offset, day, cents, method in payments:
        when = local_time(months[offset], 9 + day % 8, 10 * day % 60) + timedelta(days=day - 1)
        if when >= now:
            continue
        insert_at(CoffeeEntry(
            station=station, member=person, amount_cents=cents, kind=CoffeeEntry.Kind.PAYMENT, method=method,
            reason=reasons[method], created_by=cashier if method == "cash" and person != member else person,
        ), when)
        if method == "cash":
            cash_paid.append((when, cents))
    purchases = [
        (0, 6, -1890, "Kaffeebohnen 2 kg"),
        (1, 12, -749, "Milch, Zucker, Filtertüten"),
        (2, 15, -2350, "Kaffeebohnen 2 kg und Entkalker"),
    ]
    cash_out = []
    for offset, day, cents, reason in purchases:
        when = local_time(months[offset], 16) + timedelta(days=day - 1)
        if when < now:
            insert_at(CoffeeCashMovement(
                station=station, pot=CoffeeCashMovement.Pot.CASH, kind=CoffeeCashMovement.Kind.PURCHASE,
                amount_cents=cents, reason=label(reason), created_by=cashier,
            ), when)
            cash_out.append((when, cents))
    # Kassensturz zu zweit am Monatsende: gezählt = erwartet.
    count_at = local_time(coffee.add_months(months[1], 1), 18) - timedelta(days=1)
    if count_at < now:
        expected = sum(cents for when, cents in cash_paid + cash_out if when < count_at)
        insert_at(CoffeeCashMovement(
            station=station, pot=CoffeeCashMovement.Pot.CASH, kind=CoffeeCashMovement.Kind.COUNT,
            amount_cents=0, counted_cents=expected, expected_cents=expected, witness=lead,
            reason=label("Kassensturz zum Monatsende"), created_by=cashier,
        ), count_at)
    coffee.ensure_fees(station)

    # --- Checklisten ----------------------------------------------------
    checklists = Checklist.objects.bulk_create([
        Checklist(station=station, title=label("Fahrzeugcheck RTW zu Schichtbeginn"),
                  description="Sichtprüfung vor der ersten Fahrt der Schicht.", is_active=True),
        Checklist(station=station, title=label("Wachenrundgang am Abend"),
                  description="Sicherheitsrundgang vor der Nacht.", is_active=True),
    ])
    if any(item.pk is None for item in checklists):
        checklists = list(Checklist.objects.filter(station=station, title__in=[c.title for c in checklists])
                          .order_by("pk"))
    vehicle_check, round_check = checklists
    ChecklistItem.objects.bulk_create([
        ChecklistItem(checklist=checklist, text=text, position=index)
        for checklist, texts in (
            (vehicle_check, ("Reifen, Beleuchtung und Sondersignal", "Medizingeräte: Selbsttest durchgeführt",
                             "Sauerstoff: Haupt- und Reserveflasche über 150 bar",
                             "Tankkarte und Fahrtenbuch an Bord")),
            (round_check, ("Fenster und Türen geschlossen", "Herd und Kaffeemaschine aus", "Hoftor verriegelt")),
        )
        for index, text in enumerate(texts, start=1)
    ])
    shift_start = local_time(today, 7, 15) if local_time(today, 7, 15) < now else local_time(today, 7, 15) - timedelta(days=1)
    for checklist, person, when, note in (
        (vehicle_check, member, shift_start, "RTW 83-1 ohne Befund"),
        (vehicle_check, jonas, shift_start - timedelta(hours=12), "RTW 83-2 ohne Befund"),
        (round_check, tim, shift_start - timedelta(hours=10, minutes=30), ""),
    ):
        insert_at(ChecklistCompletion(station=station, checklist=checklist, completed_by=person,
                                      note=label(note) if note else ""), when)

    # --- Tagesaufgaben: heute schon erledigt ------------------------------
    daily = list(StationTask.objects.filter(station=station, band=StationTask.Band.DAILY, is_active=True)
                 .order_by("sort_order", "pk")[:3])
    for task, person, (hour, minute) in zip(daily, (member, jonas, lea), ((7, 30), (8, 15), (10, 5))):
        when = local_time(today, hour, minute)
        if when < now and not StationTaskCompletion.objects.filter(task=task, work_date=today).exists():
            insert_at(StationTaskCompletion(task=task, station=station, work_date=today, completed_by=person,
                                            note=marker), when)

    # --- Neuigkeiten mit Lesebestätigung, Pinnwand, Wiki ------------------
    readers = list(dict.fromkeys(person for person in (lead, cashier, jonas, nora) if person != admin))
    news = [
        (admin, 2, "Neuer Hygieneplan gilt ab sofort",
         "Der überarbeitete Hygieneplan hängt im Aufenthaltsraum und steht im Wiki. Wichtigste Änderung: "
         "Flächendesinfektion im Patientenraum mit dem neuen Mittel, Einwirkzeit 5 Minuten. Bitte lesen und "
         "quittieren.", readers, False),
        (lead, 6, "Fortbildungsplan für das nächste Halbjahr",
         "Die Termine stehen im Kalender. Bitte bis Monatsende bei der Wachleitung anmelden.", payers, True),
    ]
    for author, days, title, body, acknowledged_by, archived in news:
        posted = ago(days=days, hours=3)
        post = insert_at(NewsPost(station=station, title=label(title), body=body, created_by=author,
                                  archived_at=posted + timedelta(days=2) if archived else None), posted)
        for index, person in enumerate(dict.fromkeys(acknowledged_by)):
            insert_at(NewsAcknowledgement(post=post, user=person), posted + timedelta(hours=1 + 2 * index))
    for author, days, category, pinned, title, body in (
        (admin, 3, PinboardNote.Category.IMPORTANT, True, "Neue Durchwahl Haustechnik",
         "Ab sofort 030 23125-450. Die Nummer steht auch unter Kontakte."),
        (lea, 1, PinboardNote.Category.EVENT, False, "Grillabend der Wache",
         "Samstag ab 18 Uhr im Hof. Die Liste für Salate hängt in der Küche."),
        (admin, 8, PinboardNote.Category.INFO, False, "Spinde: Schlüssel bei der Wachleitung",
         "Neue Kolleginnen und Kollegen holen ihren Spindschlüssel bei der Wachleitung ab."),
    ):
        insert_at(PinboardNote(station=station, author=author, title=label(title), body=body, category=category,
                               is_pinned=pinned), ago(days=days, hours=2))
    create_article(station=station, user=admin, title=label("Spülmaschine entkalken"), body=(
        "1. Maschine ausschalten und das Sieb reinigen.\n"
        "2. Entkalker aus dem Hauswirtschaftsschrank nach Packungsangabe einfüllen.\n"
        "3. Programm „Intensiv 65 °C“ ohne Geschirr starten.\n"
        "4. Danach einmal leer nachspülen und in der Übergabe abhaken."
    ))
    create_article(station=station, user=lead, title=label("Fahrzeugwäsche"), body=(
        "Die Waschhalle ist werktags von 7 bis 20 Uhr frei. Waschkarte liegt in der Schlüsselbox.\n\n"
        "- Patientenraum nie mit dem Hochdruckreiniger.\n"
        "- Nach der Wäsche Status und Tankstand im Fuhrpark eintragen."
    ))

    # --- Mängel mit Frist und Verlauf -------------------------------------
    # Bezug wie im Fuhrpark „Rufname (Kennzeichen)“: So erscheint der Mangel
    # auch beim Fahrzeug.
    for author, hours, owner, category, priority, status, due_days, title, asset_ref, description in (
        (jonas, 20, lead, "vehicle", "urgent", "open", 1, "Trage RTW 83-2: Verriegelung hakt",
         "RTW 1/83-2 (MU-RD 832)",
         "Fahrgestell rastet erst beim zweiten Versuch ein. Bis zur Reparatur vor jeder Fahrt prüfen."),
        # Grund für „Eingeschränkt“ beim KTW 85-1 (Fuhrpark).
        (lea, 30, lead, "vehicle", "important", "open", 7, "KTW 85-1: Gurt am Tragestuhl ausgefranst",
         "KTW 1/85-1 (MU-RD 851)",
         "Tragestuhl ist nutzbar. Ersatzgurt ist bestellt; bis dahin den Gurt vor jeder Fahrt prüfen."),
        (lea, 9, admin, "facility", "important", "in_progress", 6, "Rolltor Fahrzeughalle 2 schließt schwer",
         "Fahrzeughalle 2", "Haustechnik kommt in dieser Woche. Bis dahin Tor von Hand nachführen."),
        (tim, 96, admin, "facility", "normal", "done", None, "Seifenspender Umkleide defekt",
         "Umkleide", "Spender ist getauscht."),
    ):
        reported = ago(hours)
        defect = insert_at(Defect(
            station=station, title=label(title), description=description, asset_ref=asset_ref,
            priority=priority, status=status,
            category=category, owner=owner, created_by=author,
            due_at=local_time(today + timedelta(days=due_days), 12) if due_days else None,
            closed_at=reported + timedelta(days=2) if status == Defect.Status.DONE else None,
        ), reported)
        insert_at(DefectEvent(defect=defect, station=station, kind=DefectEvent.Kind.CREATED, to_status="open",
                              actor=author), reported)
        if status != "open":
            changed = defect.closed_at or min(now, reported + timedelta(hours=2))
            insert_at(DefectEvent(defect=defect, station=station, kind=DefectEvent.Kind.STATUS, from_status="open",
                                  to_status=status, actor=owner), changed)
            Defect.objects.filter(pk=defect.pk).update(updated_at=changed)

    seed_module_demo(station, users, marker=marker, fresh=fresh)

    audit(admin, station, "demo.seeded", station, {
        "fields": ["handovers", "calendar", "coffee", "checklists", "news", "pinboard", "wiki", "defects", "modules"],
        "marker": marker,
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
