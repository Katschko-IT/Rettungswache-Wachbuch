"""Tests für Roadmap 0.28 Paket 3:
- Fristen-Erinnerungen bei 30, 7 und 0 Tagen (STK zum Monatsende, MTK zum Jahresende,
  DGUV V3, HU, UVV, Chargenverfall, Mangel, Dienstanweisung, Prüfung/Aufgabe) + Wochenübersicht
- Dienstanweisungen-Lesepflicht mit Frist (ack_due_date), Zielgruppe (target_role),
  aggregierter Lesequote (ack_progress) und gezielter Erinnerung nur an Offene (sop_remind).
"""
from __future__ import annotations

import io
from unittest import mock
from datetime import date, datetime, time, timedelta

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.deadline_reminders import (
    get_mtk_due_date,
    get_stk_due_date,
    send_deadline_reminders,
    send_weekly_digest,
)
from core.fleet_models import Vehicle
from core.models import Membership, Station, StationTask
from core.mpg_models import MedicalDevice
from core.notification_models import UserNotification
from core.orga_models import SOPDocument, SOPReceipt, SOPRevision
from core.wachalltag_models import Defect
from core.warehouse_models import ItemBatch, MedicalItem, StockItem, StorageLocation


class DeadlineRemindersTests(TestCase):
    def setUp(self):
        self.today = date(2026, 11, 2)
        self.station = Station.objects.create(
            name="RW Fristen Test",
            slug="rw-fristen-test",
            mpg_enabled=True,
            fleet_enabled=True,
            warehouse_enabled=True,
            orga_enabled=True,
            tasks_enabled=True,
        )
        self.lead = User.objects.create_user(username="wachleiter", password="testpassword123")
        Membership.objects.create(
            user=self.lead,
            station=self.station,
            role=Membership.Role.SHIFT_LEAD,
            is_active=True,
        )
        self.mpg_lead = User.objects.create_user(username="mpg_beauftragter", password="testpassword123")
        Membership.objects.create(
            user=self.mpg_lead,
            station=self.station,
            role=Membership.Role.MEMBER,
            is_mpg_lead=True,
            is_active=True,
        )
        self.member = User.objects.create_user(username="rettungssani", password="testpassword123")
        Membership.objects.create(
            user=self.member,
            station=self.station,
            role=Membership.Role.MEMBER,
            is_active=True,
        )

    def test_stk_month_end_and_mtk_year_end_calculation(self):
        """STK gilt bis zum Monatsende, MTK bis zum Jahresende (MPBetreibV)."""
        dev = MedicalDevice.objects.create(
            station=self.station,
            slug="corpuls-c3",
            name="Corpuls3",
            is_anlage_1=True,
            is_anlage_2=True,
            next_stk_date=date(2026, 11, 10),
            next_mtk_date=date(2026, 5, 14),
        )
        self.assertEqual(get_stk_due_date(dev), date(2026, 11, 30))
        self.assertEqual(get_mtk_due_date(dev), date(2026, 12, 31))

        # 30 Tage vor dem 30.11.2026 ist der 31.10.2026
        count_30 = send_deadline_reminders(station=self.station, today=date(2026, 10, 31))
        self.assertEqual(count_30, 2)  # lead + mpg_lead
        self.assertTrue(
            UserNotification.objects.filter(
                user=self.mpg_lead,
                kind=UserNotification.Kind.DEADLINE_DUE,
                title__icontains="STK fällig in 30 Tagen",
            ).exists()
        )
        self.assertFalse(UserNotification.objects.filter(user=self.member).exists())

        # 7 Tage vor dem 31.12.2026 (MTK Jahresende) ist der 24.12.2026. Die
        # STK (30.11.) ist inzwischen überfällig: Ihre verpasste 0-Tage-Erinnerung
        # wird einmal nachgeholt (Fensterlogik, Entscheidung 2), daher 2 + 2.
        count_mtk_7 = send_deadline_reminders(station=self.station, today=date(2026, 12, 24))
        self.assertEqual(count_mtk_7, 4)
        self.assertTrue(
            UserNotification.objects.filter(
                user=self.mpg_lead,
                kind=UserNotification.Kind.DEADLINE_DUE,
                title__icontains="MTK fällig in 7 Tagen",
            ).exists()
        )
        self.assertTrue(
            UserNotification.objects.filter(user=self.mpg_lead, title__icontains="STK seit 24 Tagen überfällig").exists()
        )

    def test_thresholds_30_7_0_and_deduplication_across_all_sources(self):
        """Prüft Erinnerungen bei 30, 7 und 0 Tagen sowie Deduplizierung über alle Quellen."""
        due = self.today + timedelta(days=7)

        # 1. Fahrzeug HU & UVV
        Vehicle.objects.create(
            station=self.station,
            slug="rtw-1",
            call_sign="RK-RTW-1",
            license_plate="M-RK 112",
            next_hu_date=due,
            next_uvv_date=self.today,
        )
        # 2. Chargenverfall (nur Chargen mit Bestand)
        item = MedicalItem.objects.create(station=self.station, slug="adrenalin", name="Adrenalin 1 mg")
        batch = ItemBatch.objects.create(
            station=self.station,
            item=item,
            batch_number="LOT-7D",
            manufacturer_exp_date=due,
        )
        location = StorageLocation.objects.create(station=self.station, slug="lager", name="Lager")
        StockItem.objects.create(station=self.station, item=item, batch=batch, location=location, quantity=2)
        # 3. Mangel mit Frist (Owner = self.member)
        due_dt = timezone.make_aware(datetime.combine(self.today + timedelta(days=30), time(12, 0)))
        Defect.objects.create(
            station=self.station,
            title="Blaulicht vorne links Wackelkontakt",
            created_by=self.lead,
            owner=self.member,
            due_at=due_dt,
        )
        # 4. Aufgabe / Prüfung (StationTask)
        StationTask.objects.create(
            station=self.station,
            title="Desinfektionsplan Monatsprüfung",
            due_date=self.today,
        )

        # Erster Lauf: erstellt Benachrichtigungen für alle passenden Schwellenwerte (30, 7, 0)
        created_first = send_deadline_reminders(station=self.station, today=self.today)
        self.assertGreaterEqual(created_first, 5)

        # Prüfe einzelne Kategorien
        lead_notes = UserNotification.objects.filter(user=self.lead, kind=UserNotification.Kind.DEADLINE_DUE)
        titles = list(lead_notes.values_list("title", flat=True))
        self.assertTrue(any("HU fällig in 7 Tagen" in t for t in titles))
        self.assertTrue(any("UVV-Prüfung heute fällig" in t for t in titles))
        self.assertTrue(any("Verfall fällig in 7 Tagen" in t for t in titles))
        self.assertTrue(any("Mangel-Frist fällig in 30 Tagen" in t for t in titles))
        self.assertTrue(any("Aufgabe heute fällig" in t for t in titles))

        # Defect-Owner (member) hat die Mangel-Frist ebenfalls erhalten
        self.assertTrue(
            UserNotification.objects.filter(
                user=self.member,
                title__icontains="Mangel-Frist fällig in 30 Tagen",
            ).exists()
        )

        # Zweiter Lauf am selben Tag: 0 neue Benachrichtigungen (Deduplizierung via dedupe_key)
        total_before = UserNotification.objects.count()
        created_second = send_deadline_reminders(station=self.station, today=self.today)
        self.assertEqual(created_second, 0)
        self.assertEqual(UserNotification.objects.count(), total_before)

        # Keine tägliche Wiederholung: Am Folgetag ist für jeden Eintrag die
        # kleinste überschrittene Schwelle schon versendet. (Früher prüfte dieser
        # Test, dass ein Tag ohne exakte Schwelle nichts sendet; mit der
        # Fensterlogik holt ein solcher Tag eine verpasste Schwelle nach.)
        created_next_day = send_deadline_reminders(
            station=self.station,
            today=self.today + timedelta(days=1),
        )
        self.assertEqual(created_next_day, 0)

    def test_weekly_digest_and_management_command(self):
        """Montags-Wochenübersicht und Management-Command send_deadline_reminders."""
        Vehicle.objects.create(
            station=self.station,
            slug="nef-1",
            call_sign="RK-NEF-1",
            license_plate="M-RK 110",
            next_hu_date=self.today + timedelta(days=3),
        )
        count = send_weekly_digest(station=self.station, today=self.today)
        self.assertEqual(count, 1)
        note = UserNotification.objects.get(
            user=self.lead,
            dedupe_key__startswith="deadline_weekly_digest:",
        )
        self.assertIn("Wochenübersicht", note.title)
        self.assertIn("RK-NEF-1", note.body)

        # Deduplizierung in derselben Kalenderwoche
        self.assertEqual(send_weekly_digest(station=self.station, today=self.today + timedelta(days=1)), 0)

        # Management Command dry-run & regulärer Aufruf
        out = io.StringIO()
        with mock.patch("django.utils.timezone.localdate", return_value=self.today):
            call_command(
                "send_deadline_reminders",
                station=self.station.slug,
                thresholds="3",
                dry_run=True,
                stdout=out,
            )
        self.assertIn("Dry-Run:", out.getvalue())

        out_live = io.StringIO()
        # Der Befehl rechnet mit dem heutigen Datum; der Test legt es fest,
        # sonst hängt das Ergebnis vom Tag des Testlaufs ab.
        with mock.patch("django.utils.timezone.localdate", return_value=self.today):
            call_command(
                "send_deadline_reminders",
                station=self.station.slug,
                thresholds="3",
                weekly_digest=True,
                stdout=out_live,
            )
        self.assertIn("Fristen-Erinnerungen: 1 Benachrichtigung(en) erstellt.", out_live.getvalue())


class SopReadingObligationAndQuoteTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(
            name="RW SOP Quote",
            slug="rw-sop-quote",
            orga_enabled=True,
        )
        self.lead = User.objects.create_user(username="sop_lead", password="testpassword123")
        Membership.objects.create(
            user=self.lead,
            station=self.station,
            role=Membership.Role.SHIFT_LEAD,
            is_active=True,
        )
        self.member1 = User.objects.create_user(username="sani_eins", password="testpassword123")
        Membership.objects.create(
            user=self.member1,
            station=self.station,
            role=Membership.Role.MEMBER,
            is_active=True,
        )
        self.member2 = User.objects.create_user(username="sani_zwei", password="testpassword123")
        Membership.objects.create(
            user=self.member2,
            station=self.station,
            role=Membership.Role.MEMBER,
            is_active=True,
        )
        self.due_date = timezone.localdate() + timedelta(days=7)
        self.sop = SOPDocument.objects.create(
            station=self.station,
            slug="sop-med-rsi",
            doc_number="SOP-MED-05",
            title="Notfallnarkose & Airway-Management",
            status=SOPDocument.Status.ACTIVE,
            requires_acknowledgment=True,
            ack_due_date=self.due_date,
            target_role=Membership.Role.MEMBER,
            created_by=self.lead,
        )
        self.rev = SOPRevision.objects.create(
            sop=self.sop,
            version_label="1.0",
            content_markdown="# Airway-Algorithmus",
            change_summary="Erstfassung",
            approved_by=self.lead,
        )

    def test_ack_progress_with_target_role_and_all_members(self):
        """Aggregierte Lesequote berücksichtigt Zielgruppe (target_role) und Quittierungen."""
        # Zielgruppe = MEMBER (member1 + member2 = 2 Personen, lead zählt nicht dazu)
        prog0 = self.sop.ack_progress()
        self.assertEqual(prog0, {"acknowledged_count": 0, "target_count": 2, "percent": 0})
        self.assertCountEqual(list(self.sop.unacknowledged_users()), [self.member1, self.member2])

        # member1 quittiert -> 1 / 2 = 50 %
        SOPReceipt.objects.create(
            station=self.station,
            sop=self.sop,
            revision=self.rev,
            user=self.member1,
        )
        prog1 = self.sop.ack_progress()
        self.assertEqual(prog1, {"acknowledged_count": 1, "target_count": 2, "percent": 50})
        self.assertEqual(list(self.sop.unacknowledged_users()), [self.member2])

        # Ohne target_role (alle aktiven Mitglieder = 3 Personen: lead, member1, member2)
        self.sop.target_role = ""
        self.sop.save(update_fields=["target_role"])
        prog_all = self.sop.ack_progress()
        self.assertEqual(prog_all, {"acknowledged_count": 1, "target_count": 3, "percent": 33})

    def test_sop_detail_displays_aggregate_quote_and_remind_button_for_lead_only(self):
        """Wachleitung sieht aggregierte Lesequote und Erinnern-Knopf; Mitglieder nicht."""
        SOPReceipt.objects.create(
            station=self.station,
            sop=self.sop,
            revision=self.rev,
            user=self.member1,
        )
        # Als Wachleitung
        self.client.force_login(self.lead)
        resp_lead = self.client.get(reverse("sop_detail", args=[self.sop.slug]))
        self.assertEqual(resp_lead.status_code, 200)
        self.assertContains(resp_lead, "1 / 2 (50")
        self.assertContains(resp_lead, reverse("sop_remind", args=[self.sop.slug]))

        # Als reguläres Mitglied
        self.client.force_login(self.member1)
        resp_member = self.client.get(reverse("sop_detail", args=[self.sop.slug]))
        self.assertEqual(resp_member.status_code, 200)
        self.assertNotContains(resp_member, reverse("sop_remind", args=[self.sop.slug]))

    def test_sop_remind_dispatches_only_to_unacknowledged_target_members(self):
        """sop_remind sendet UserNotification(SOP_DUE) nur an offene Personen der Zielgruppe."""
        SOPReceipt.objects.create(
            station=self.station,
            sop=self.sop,
            revision=self.rev,
            user=self.member1,
        )

        # Mitglied darf keine Erinnerung auslösen (403)
        self.client.force_login(self.member1)
        forbidden = self.client.post(reverse("sop_remind", args=[self.sop.slug]))
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(UserNotification.objects.count(), 0)

        # Wachleitung löst Erinnerung aus -> geht NUR an member2 (offen & in target_role=MEMBER)
        self.client.force_login(self.lead)
        resp = self.client.post(reverse("sop_remind", args=[self.sop.slug]), follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Erinnerung an 1 offene Person(en) versendet.")

        self.assertEqual(UserNotification.objects.filter(kind=UserNotification.Kind.SOP_DUE).count(), 1)
        note = UserNotification.objects.get(kind=UserNotification.Kind.SOP_DUE)
        self.assertEqual(note.user, self.member2)
        self.assertIn("SOP-MED-05", note.title)
        self.assertFalse(UserNotification.objects.filter(user=self.member1).exists())
        self.assertFalse(UserNotification.objects.filter(user=self.lead).exists())

        # Erneutes Klicken am selben Tag erzeugt kein Duplikat
        resp_dup = self.client.post(reverse("sop_remind", args=[self.sop.slug]), follow=True)
        self.assertContains(resp_dup, "bereits an diese Version erinnert")
        self.assertEqual(UserNotification.objects.filter(kind=UserNotification.Kind.SOP_DUE).count(), 1)

    def test_automated_deadline_reminder_for_sop_ack_due_date(self):
        """Automatische 7-Tage-Frist-Erinnerung erinnert offene Zielpersonen und informiert Leitung."""
        SOPReceipt.objects.create(
            station=self.station,
            sop=self.sop,
            revision=self.rev,
            user=self.member1,
        )
        today = self.due_date - timedelta(days=7)
        created = send_deadline_reminders(station=self.station, today=today)
        # 1x SOP_DUE an member2 + 1x DEADLINE_DUE mit Quote an lead
        self.assertEqual(created, 2)

        user_note = UserNotification.objects.get(user=self.member2, kind=UserNotification.Kind.SOP_DUE)
        self.assertIn("Lesefrist Dienstanweisung fällig in 7 Tagen", user_note.title)
        self.assertFalse(UserNotification.objects.filter(user=self.member1).exists())

        lead_note = UserNotification.objects.get(user=self.lead, kind=UserNotification.Kind.DEADLINE_DUE)
        self.assertIn("1 / 2 (50 %)", lead_note.body)

    def test_sop_create_with_ack_due_date_and_target_role(self):
        """SOP-Formular speichert ack_due_date und target_role."""
        self.client.force_login(self.lead)
        due_str = (timezone.localdate() + timedelta(days=14)).isoformat()
        resp = self.client.post(
            reverse("sop_create"),
            {
                "doc_number": "SOP-HYG-09",
                "title": "Infektionstransport & Schutzkleidung",
                "category": SOPDocument.Category.HYGIENE,
                "status": SOPDocument.Status.ACTIVE,
                "valid_from": timezone.localdate().isoformat(),
                "ack_due_date": due_str,
                "target_role": Membership.Role.MEMBER,
                "requires_acknowledgment": "on",
                "initial_version": "1.0",
                "initial_content": "# Schutzstufe\n\nFFP2 und Schutzkittel anlegen.",
            },
        )
        self.assertEqual(resp.status_code, 302)
        created_sop = SOPDocument.objects.get(doc_number="SOP-HYG-09")
        self.assertEqual(created_sop.ack_due_date.isoformat(), due_str)
        self.assertEqual(created_sop.target_role, Membership.Role.MEMBER)


# ---------------------------------------------------------------------------
# Paket P2 (Audit 0.28): Zeitplan, Fensterlogik, Funktionen und Abo, Quellen,
# Wochenübersicht, E-Mail, Leserschaft, „Namen nur nach Vereinbarung“, App.
# ---------------------------------------------------------------------------

import importlib  # noqa: E402
import json  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

from django.apps import apps as django_apps  # noqa: E402
from django.core import mail  # noqa: E402
from django.core.exceptions import ValidationError  # noqa: E402
from django.test import override_settings  # noqa: E402

from core import deadline_reminders as dr  # noqa: E402
from core.api.views import DEFAULT_MOBILE_SCOPES, hash_api_token  # noqa: E402
from core.models import ApiToken, AuditEvent, Checklist  # noqa: E402
from core.notification_models import WorkerJobState  # noqa: E402
from core.terminal import set_station_code  # noqa: E402
from core.wachalltag_models import ChecklistSchedule  # noqa: E402

TZ = timezone.get_default_timezone()


def _at(day: date, hour: int = 12, minute: int = 0):
    return timezone.make_aware(datetime.combine(day, time(hour, minute)), TZ)


class _StationMixin:
    """Wache mit Leitung, Funktionsträgern, Auditor und Wachenterminal."""

    def make_station(self, slug="rw-p2", **flags):
        defaults = dict(mpg_enabled=True, fleet_enabled=True, warehouse_enabled=True, orga_enabled=True,
                        tasks_enabled=True, checklists_enabled=True)
        defaults.update(flags)
        return Station.objects.create(name=f"Wache {slug}", slug=slug, **defaults)

    def person(self, station, username, role=Membership.Role.MEMBER, **flags):
        user = User.objects.create_user(username=username, password="pw-123456789", email=f"{username}@example.org")
        Membership.objects.create(user=user, station=station, role=role, **flags)
        return user

    def notes_for(self, user, **filters):
        return UserNotification.objects.filter(user=user, **filters)


class WindowSemanticsTests(_StationMixin, TestCase):
    """Entscheidung 2: kleinste überschrittene Schwelle, Nachholen, keine Wiederholung."""

    def setUp(self):
        self.station = self.make_station()
        self.lead = self.person(self.station, "p2-lead", Membership.Role.SHIFT_LEAD)
        self.today = date(2026, 11, 2)

    def vehicle(self, **dates):
        return Vehicle.objects.create(station=self.station, slug=f"v-{Vehicle.objects.count()}", call_sign="RTW 1",
                                      license_plate="RW-1", **dates)

    def titles(self):
        return list(self.notes_for(self.lead).values_list("title", flat=True))

    def test_pick_threshold(self):
        self.assertEqual(dr.pick_threshold(45, (30, 7, 0)), None)
        self.assertEqual(dr.pick_threshold(30, (30, 7, 0)), 30)
        self.assertEqual(dr.pick_threshold(29, (30, 7, 0)), 30)
        self.assertEqual(dr.pick_threshold(5, (30, 7, 0)), 7)
        self.assertEqual(dr.pick_threshold(0, (30, 7, 0)), 0)
        self.assertEqual(dr.pick_threshold(-3, (30, 7, 0)), 0)
        self.assertEqual(dr.pick_threshold(-(dr.OVERDUE_CATCH_UP_DAYS + 1), (30, 7, 0)), None)

    def test_deadline_entered_five_days_ahead_gets_only_the_7_day_reminder_once(self):
        self.vehicle(next_hu_date=self.today + timedelta(days=5))
        self.assertEqual(send_deadline_reminders(station=self.station, today=self.today), 1)
        self.assertEqual(self.titles(), ["HU fällig in 5 Tagen: RTW 1"])
        for offset in (1, 2, 3, 4):
            self.assertEqual(send_deadline_reminders(station=self.station, today=self.today + timedelta(days=offset)), 0)
        self.assertEqual(send_deadline_reminders(station=self.station, today=self.today + timedelta(days=5)), 1)
        self.assertEqual(len(self.titles()), 2)
        self.assertIn("HU heute fällig: RTW 1", self.titles())

    def test_missed_run_day_still_sends_the_30_day_reminder(self):
        self.vehicle(next_hu_date=self.today + timedelta(days=29))
        self.assertEqual(send_deadline_reminders(station=self.station, today=self.today), 1)
        note = self.notes_for(self.lead).get()
        self.assertTrue(note.dedupe_key.endswith(f":30:{(self.today + timedelta(days=29)).isoformat()}"))

    def test_missed_zero_day_reminder_is_caught_up_once(self):
        self.vehicle(next_uvv_date=self.today - timedelta(days=3))
        self.assertEqual(send_deadline_reminders(station=self.station, today=self.today), 1)
        self.assertEqual(self.titles(), ["UVV-Prüfung seit 3 Tagen überfällig: RTW 1"])
        self.assertEqual(send_deadline_reminders(station=self.station, today=self.today + timedelta(days=1)), 0)

    def test_long_overdue_items_are_not_reminded_again(self):
        self.vehicle(next_uvv_date=self.today - timedelta(days=dr.OVERDUE_CATCH_UP_DAYS + 5))
        self.assertEqual(send_deadline_reminders(station=self.station, today=self.today), 0)

    def test_new_due_date_starts_a_new_series(self):
        vehicle = self.vehicle(next_hu_date=self.today + timedelta(days=7))
        self.assertEqual(send_deadline_reminders(station=self.station, today=self.today), 1)
        Vehicle.objects.filter(pk=vehicle.pk).update(next_hu_date=self.today + timedelta(days=6))
        self.assertEqual(send_deadline_reminders(station=self.station, today=self.today), 1)

    def test_singular_day_is_grammatical(self):
        self.vehicle(next_hu_date=self.today + timedelta(days=1))
        send_deadline_reminders(station=self.station, today=self.today)
        self.assertEqual(self.titles(), ["HU fällig in 1 Tag: RTW 1"])


class FunctionRoutingAndSubscriptionTests(_StationMixin, TestCase):
    """Entscheidung 3 und 7: Empfänger nach Funktion und eigenem Abo."""

    def setUp(self):
        self.station = self.make_station()
        self.today = date(2026, 11, 2)
        self.admin = self.person(self.station, "r-admin", Membership.Role.ADMIN)
        self.fleet = self.person(self.station, "r-fleet", is_fleet_lead=True)
        self.safety = self.person(self.station, "r-safety", is_safety_lead=True)
        self.mpg = self.person(self.station, "r-mpg", Membership.Role.CASHIER, is_mpg_lead=True)
        self.material = self.person(self.station, "r-material", is_material_lead=True)
        self.plain = self.person(self.station, "r-plain")
        self.auditor = self.person(self.station, "r-auditor", Membership.Role.AUDITOR, is_fleet_lead=True)
        self.inactive_user = self.person(self.station, "r-gone", Membership.Role.SHIFT_LEAD)
        User.objects.filter(pk=self.inactive_user.pk).update(is_active=False)
        self.inactive_membership = self.person(self.station, "r-left", is_fleet_lead=True)
        Membership.objects.filter(user=self.inactive_membership).update(is_active=False)
        terminal = set_station_code(self.station, "4711", set_by=self.admin)
        self.terminal_user = terminal.service_user
        # Altbestand vor 0.28: Funktion am Terminal-Konto (die Migration entfernt sie).
        Membership.objects.filter(user=self.terminal_user).update(is_fleet_lead=True, is_mpg_lead=True)
        self.soon = self.today + timedelta(days=7)

    def recipients(self, title_part):
        return set(
            UserNotification.objects.filter(title__contains=title_part).values_list("user__username", flat=True)
        )

    def test_fleet_items_go_to_leads_fleet_and_safety_only_for_uvv(self):
        Vehicle.objects.create(station=self.station, slug="rtw", call_sign="RTW 7", license_plate="RW-7",
                               next_hu_date=self.soon, next_uvv_date=self.soon)
        send_deadline_reminders(station=self.station, today=self.today)
        self.assertEqual(self.recipients("HU fällig"), {"r-admin", "r-fleet"})
        self.assertEqual(self.recipients("UVV-Prüfung fällig"), {"r-admin", "r-fleet", "r-safety"})

    def test_mpg_material_and_task_routing(self):
        MedicalDevice.objects.create(station=self.station, slug="defi", name="Defi", is_anlage_1=True,
                                     next_stk_date=date(2026, 11, 5))
        item = MedicalItem.objects.create(station=self.station, slug="nacl", name="NaCl")
        batch = ItemBatch.objects.create(station=self.station, item=item, batch_number="L1",
                                         manufacturer_exp_date=self.soon)
        location = StorageLocation.objects.create(station=self.station, slug="l", name="Lager")
        StockItem.objects.create(station=self.station, item=item, batch=batch, location=location, quantity=1)
        StationTask.objects.create(station=self.station, title="Rauchmelder prüfen", due_date=self.soon)
        send_deadline_reminders(station=self.station, today=self.today)
        self.assertEqual(self.recipients("STK"), {"r-admin", "r-mpg"})
        self.assertEqual(self.recipients("Verfall"), {"r-admin", "r-material"})
        self.assertEqual(self.recipients("Rauchmelder"), {"r-admin", "r-safety"})

    def test_defects_follow_the_area_of_the_defect(self):
        device = MedicalDevice.objects.create(station=self.station, slug="pumpe", name="Pumpe")
        due = timezone.make_aware(datetime.combine(self.soon, time(12)))
        Defect.objects.create(station=self.station, title="Display defekt", created_by=self.admin,
                              medical_device=device, due_at=due)
        Defect.objects.create(station=self.station, title="Spiegel lose", created_by=self.admin,
                              category=Defect.Category.VEHICLE, due_at=due, owner=self.plain)
        Defect.objects.create(station=self.station, title="Tür klemmt", created_by=self.admin,
                              category=Defect.Category.FACILITY, due_at=due, owner=self.auditor)
        send_deadline_reminders(station=self.station, today=self.today)
        self.assertEqual(self.recipients("Display defekt"), {"r-admin", "r-mpg"})
        # Wer den Mangel bearbeitet, erfährt die Frist immer.
        self.assertEqual(self.recipients("Spiegel lose"), {"r-admin", "r-fleet", "r-plain"})
        # Auditoren nie, auch nicht als eingetragene Bearbeitung.
        self.assertEqual(self.recipients("Tür klemmt"), {"r-admin", "r-safety"})

    def test_never_auditor_terminal_inactive_user_or_membership(self):
        Vehicle.objects.create(station=self.station, slug="rtw", call_sign="RTW 7", license_plate="RW-7",
                               next_hu_date=self.soon)
        MedicalDevice.objects.create(station=self.station, slug="defi", name="Defi", next_dguv_date=self.soon)
        send_deadline_reminders(station=self.station, today=self.today)
        for user in (self.auditor, self.terminal_user, self.inactive_user, self.inactive_membership, self.plain):
            self.assertFalse(self.notes_for(user).exists(), user.username)

    def test_unsubscribed_function_holder_gets_nothing(self):
        Membership.objects.filter(user=self.fleet).update(remind_fleet=False)
        Vehicle.objects.create(station=self.station, slug="rtw", call_sign="RTW 7", license_plate="RW-7",
                               next_hu_date=self.soon)
        send_deadline_reminders(station=self.station, today=self.today)
        self.assertEqual(self.recipients("HU fällig"), {"r-admin"})

    def test_leads_get_items_nobody_subscribed(self):
        Membership.objects.filter(user__in=[self.fleet, self.admin]).update(remind_fleet=False)
        Vehicle.objects.create(station=self.station, slug="rtw", call_sign="RTW 7", license_plate="RW-7",
                               next_hu_date=self.soon)
        send_deadline_reminders(station=self.station, today=self.today)
        self.assertEqual(self.recipients("HU fällig"), {"r-admin"})

    def test_lead_can_unsubscribe_when_a_function_holder_covers_the_area(self):
        Membership.objects.filter(user=self.admin).update(remind_fleet=False)
        Vehicle.objects.create(station=self.station, slug="rtw", call_sign="RTW 7", license_plate="RW-7",
                               next_hu_date=self.soon)
        send_deadline_reminders(station=self.station, today=self.today)
        self.assertEqual(self.recipients("HU fällig"), {"r-fleet"})

    def test_subscription_defaults(self):
        member = Membership.objects.get(user=self.safety)
        codes = {category.code for category in dr.eligible_categories(member)}
        self.assertEqual(codes, {dr.FLEET, dr.TASKS})
        self.assertTrue(all(dr.is_subscribed(member, c) for c in dr.eligible_categories(member)))
        admin = Membership.objects.get(user=self.admin)
        self.assertEqual(len(dr.eligible_categories(admin)), len(dr.CATEGORIES))
        self.assertEqual(dr.eligible_categories(Membership.objects.get(user=self.plain)), [])

    def test_get_mpg_leads_checks_role_and_function_on_the_same_membership(self):
        other = self.make_station(slug="rw-other")
        wanderer = User.objects.create_user("wanderer", password="pw-123456789")
        Membership.objects.create(user=wanderer, station=self.station, role=Membership.Role.MEMBER)
        Membership.objects.create(user=wanderer, station=other, role=Membership.Role.ADMIN, is_mpg_lead=True,
                                  is_active=False)
        names = {user.username for user in dr.get_mpg_leads(self.station)}
        self.assertNotIn("wanderer", names)
        self.assertEqual(names, {"r-admin", "r-mpg"})


class SourceExclusionTests(_StationMixin, TestCase):
    """Entscheidung 7: ausgemusterte Geräte und Fahrzeuge, leere Chargen, inaktive Aufgaben."""

    def setUp(self):
        self.station = self.make_station()
        self.lead = self.person(self.station, "x-lead", Membership.Role.SHIFT_LEAD)
        self.today = date(2026, 11, 2)
        self.soon = self.today + timedelta(days=7)

    def test_retired_and_empty_sources_send_nothing(self):
        MedicalDevice.objects.create(station=self.station, slug="alt", name="Alt", next_dguv_date=self.soon,
                                     current_status=MedicalDevice.Status.DECOMMISSIONED)
        Vehicle.objects.create(station=self.station, slug="alt", call_sign="Alt", license_plate="A-1",
                               next_hu_date=self.soon, is_active=False)
        item = MedicalItem.objects.create(station=self.station, slug="leer", name="Leer")
        ItemBatch.objects.create(station=self.station, item=item, batch_number="L0", manufacturer_exp_date=self.soon)
        StationTask.objects.create(station=self.station, title="Abgeschaltet", due_date=self.soon, is_active=False)
        self.assertEqual(send_deadline_reminders(station=self.station, today=self.today), 0)
        self.assertEqual(send_weekly_digest(station=self.station, today=self.today), 0)

    def test_sp_and_stretcher_service_are_reminded_for_the_fleet(self):
        Vehicle.objects.create(station=self.station, slug="rtw", call_sign="RTW 2", license_plate="RW-2",
                               next_sp_date=self.soon, next_stretcher_service_date=self.soon)
        self.assertEqual(send_deadline_reminders(station=self.station, today=self.today), 2)
        titles = set(self.notes_for(self.lead).values_list("title", flat=True))
        self.assertEqual(titles, {"SP fällig in 7 Tagen: RTW 2", "Wartung Tragentisch fällig in 7 Tagen: RTW 2"})

    def test_checklist_schedules_are_a_source_of_checks(self):
        monthly = Checklist.objects.create(station=self.station, title="Monatscheck")
        weekly = Checklist.objects.create(station=self.station, title="Wochencheck")
        daily = Checklist.objects.create(station=self.station, title="Tagescheck")
        off = Checklist.objects.create(station=self.station, title="Abgeschaltet", is_active=False)
        ChecklistSchedule.objects.create(checklist=monthly, station=self.station, interval="monthly",
                                         due_next=_at(self.today + timedelta(days=5)))
        ChecklistSchedule.objects.create(checklist=weekly, station=self.station, interval="weekly",
                                         due_next=_at(self.today + timedelta(days=3)))
        ChecklistSchedule.objects.create(checklist=daily, station=self.station, interval="daily",
                                         due_next=_at(self.today))
        ChecklistSchedule.objects.create(checklist=off, station=self.station, interval="monthly",
                                         due_next=_at(self.today))
        self.assertEqual(send_deadline_reminders(station=self.station, today=self.today), 1)
        self.assertEqual(list(self.notes_for(self.lead).values_list("title", flat=True)),
                         ["Checkliste fällig in 5 Tagen: Monatscheck"])
        # Die wöchentliche Checkliste erinnert erst am Fälligkeitstag.
        self.assertEqual(send_deadline_reminders(station=self.station, today=self.today + timedelta(days=3)), 1)
        self.assertTrue(self.notes_for(self.lead, title="Checkliste heute fällig: Wochencheck").exists())

    def test_checklists_module_off_means_no_checklist_reminders(self):
        Station.objects.filter(pk=self.station.pk).update(checklists_enabled=False)
        self.station.refresh_from_db()
        checklist = Checklist.objects.create(station=self.station, title="Monatscheck")
        ChecklistSchedule.objects.create(checklist=checklist, station=self.station, interval="monthly",
                                         due_next=_at(self.today))
        self.assertEqual(send_deadline_reminders(station=self.station, today=self.today), 0)


class WeeklyDigestTests(_StationMixin, TestCase):
    """Entscheidung 3 und 7: Wochenübersicht je Person, überfällig, gleiche Fälligkeit, ganze Zeilen."""

    def setUp(self):
        self.station = self.make_station()
        self.today = date(2026, 11, 2)  # Montag, KW 45
        self.lead = self.person(self.station, "d-lead", Membership.Role.SHIFT_LEAD)
        self.fleet = self.person(self.station, "d-fleet", is_fleet_lead=True)
        self.mpg = self.person(self.station, "d-mpg", is_mpg_lead=True)

    def digest(self, user):
        return self.notes_for(user, dedupe_key__startswith="deadline_weekly_digest:").first()

    def test_digest_is_per_person_and_lists_overdue_items_with_month_end_stk(self):
        Vehicle.objects.create(station=self.station, slug="rtw", call_sign="RTW 9", license_plate="RW-9",
                               next_hu_date=self.today - timedelta(days=2))
        # STK roh am 01.11., fällig zum Monatsende 30.11.: nicht in dieser Woche.
        MedicalDevice.objects.create(station=self.station, slug="defi", name="Defi", is_anlage_1=True,
                                     next_stk_date=date(2026, 11, 1))
        MedicalDevice.objects.create(station=self.station, slug="beatmung", name="Beatmung",
                                     next_dguv_date=self.today + timedelta(days=4))
        self.assertEqual(send_weekly_digest(station=self.station, today=self.today), 3)
        lead_note = self.digest(self.lead)
        self.assertEqual(lead_note.title, "Wochenübersicht KW 45: 2 Fristen")
        self.assertIn("überfällig – HU: RTW 9", lead_note.body)
        self.assertNotIn("Defi", lead_note.body)
        self.assertEqual(self.digest(self.fleet).title, "Wochenübersicht KW 45: 1 Frist")
        self.assertNotIn("Beatmung", self.digest(self.fleet).body)
        self.assertIn("DGUV-V3-Prüfung: Beatmung", self.digest(self.mpg).body)
        self.assertTrue(lead_note.dedupe_key.endswith(":2026-W45"))
        # Gleiche Woche, anderer Tag: keine zweite Übersicht.
        self.assertEqual(send_weekly_digest(station=self.station, today=self.today + timedelta(days=2)), 0)

    def test_digest_never_cuts_a_line(self):
        for n in range(15):
            StationTask.objects.create(station=self.station, title=f"Prüfung mit langem Namen Nummer {n:02d}",
                                       due_date=self.today + timedelta(days=n % 7))
        send_weekly_digest(station=self.station, today=self.today)
        body = self.digest(self.lead).body
        self.assertLessEqual(len(body), 300)
        lines = body.split("\n")
        self.assertRegex(lines[-1], r"^… und \d+ weitere Fristen$")
        shown = len(lines) - 1
        self.assertEqual(int(lines[-1].split()[2]), 15 - shown)
        for line in lines[:-1]:
            self.assertRegex(line, r"^• \d\d\.\d\d\. Aufgabe: Prüfung mit langem Namen Nummer \d\d$")

    def test_fit_digest_lines_limits_by_count_then_length(self):
        lines = [f"• Zeile {n}" for n in range(12)]
        text = dr.fit_digest_lines(lines)
        self.assertEqual(text.split("\n")[-1], "… und 4 weitere Fristen")
        self.assertEqual(dr.fit_digest_lines(lines[:2]), "• Zeile 0\n• Zeile 1")
        long = ["• " + "x" * 120 for _ in range(4)]
        fitted = dr.fit_digest_lines(long)
        self.assertLessEqual(len(fitted), 300)
        self.assertTrue(fitted.endswith("… und 2 weitere Fristen"))

    def test_unsubscribed_area_goes_to_leads_anyway(self):
        Membership.objects.filter(user__in=[self.lead, self.fleet]).update(remind_fleet=False)
        Vehicle.objects.create(station=self.station, slug="rtw", call_sign="RTW 9", license_plate="RW-9",
                               next_hu_date=self.today + timedelta(days=1))
        send_weekly_digest(station=self.station, today=self.today)
        self.assertIn("RTW 9", self.digest(self.lead).body)
        self.assertIsNone(self.digest(self.fleet))


class ScheduledWorkerStepTests(_StationMixin, TestCase):
    """Entscheidung 1: stündlich, Wochenübersicht ab Montag 06:00, Nachholen, Neustart."""

    def setUp(self):
        self.station = self.make_station()
        self.lead = self.person(self.station, "w-lead", Membership.Role.SHIFT_LEAD)
        self.monday = date(2026, 11, 9)  # Montag, KW 46
        Vehicle.objects.create(station=self.station, slug="rtw", call_sign="RTW 5", license_plate="RW-5",
                               next_hu_date=self.monday + timedelta(days=3))

    def digests(self):
        return self.notes_for(self.lead, dedupe_key__startswith="deadline_weekly_digest:")

    def test_reminders_run_at_most_once_per_hour(self):
        with mock.patch.object(dr, "send_deadline_reminders", return_value=0) as send:
            dr.run_scheduled_reminders(now=_at(self.monday - timedelta(days=1), 10))
            dr.run_scheduled_reminders(now=_at(self.monday - timedelta(days=1), 10, 59))
            self.assertEqual(send.call_count, 1)
            dr.run_scheduled_reminders(now=_at(self.monday - timedelta(days=1), 11, 0))
            self.assertEqual(send.call_count, 2)
        state = WorkerJobState.objects.get(name=dr.JOB_REMINDERS)
        self.assertIsNotNone(state.last_finished_at)

    def test_state_survives_a_restart(self):
        dr.run_scheduled_reminders(now=_at(self.monday, 7))
        # Der Zeitplan hält keinen Zustand im Prozess, nur in der Datenbank: Ein
        # neu gestarteter Dienst sieht denselben Stand und läuft nicht sofort.
        self.assertEqual(WorkerJobState.objects.filter(last_started_at__isnull=False).count(), 2)
        with mock.patch.object(dr, "send_deadline_reminders", return_value=0) as send, \
                mock.patch.object(dr, "send_weekly_digest", return_value=0) as digest:
            dr.run_scheduled_reminders(now=_at(self.monday, 7, 20))
        send.assert_not_called()
        digest.assert_not_called()

    def test_weekly_digest_from_monday_six_oclock(self):
        dr.run_scheduled_reminders(now=_at(self.monday, 5, 59))
        self.assertFalse(self.digests().exists())
        dr.run_scheduled_reminders(now=_at(self.monday, 6, 0))
        self.assertEqual(self.digests().count(), 1)
        self.assertEqual(WorkerJobState.objects.get(name=dr.JOB_DIGEST).last_period, "2026-W46")
        with mock.patch.object(dr, "send_weekly_digest", return_value=0) as digest:
            dr.run_scheduled_reminders(now=_at(self.monday + timedelta(days=2), 9))
        digest.assert_not_called()

    def test_missed_monday_is_caught_up_in_the_same_week(self):
        wednesday = self.monday + timedelta(days=2)
        dr.run_scheduled_reminders(now=_at(wednesday, 14))
        note = self.digests().get()
        self.assertTrue(note.title.startswith("Wochenübersicht KW 46"))
        # Sonntag vor 06:00 des nächsten Montags: noch dieselbe Woche, kein zweiter Versand.
        dr.run_scheduled_reminders(now=_at(self.monday + timedelta(days=6), 23))
        self.assertEqual(self.digests().count(), 1)
        dr.run_scheduled_reminders(now=_at(self.monday + timedelta(days=7), 6, 30))
        self.assertEqual(self.digests().count(), 2)

    def test_failure_is_logged_and_retried_after_ten_minutes(self):
        now = _at(self.monday, 8)
        with mock.patch.object(dr, "send_deadline_reminders", side_effect=RuntimeError("kaputt")) as send, \
                self.assertLogs("core.deadline_reminders", level="ERROR"):
            dr.run_scheduled_reminders(now=now)
            dr.run_scheduled_reminders(now=now + timedelta(minutes=5))
            self.assertEqual(send.call_count, 1)
            dr.run_scheduled_reminders(now=now + timedelta(minutes=10))
            self.assertEqual(send.call_count, 2)
        self.assertIsNotNone(WorkerJobState.objects.get(name=dr.JOB_REMINDERS).last_failed_at)

    def test_notify_crew_pass_runs_the_step_and_writes_the_last_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            heartbeat = Path(tmp) / "alive"
            with mock.patch("core.management.commands.notify_crew.close_old_connections"), \
                    mock.patch("core.management.commands.notify_crew.run_scheduled_reminders",
                               wraps=dr.run_scheduled_reminders) as step:
                call_command("notify_crew", heartbeat_file=str(heartbeat), stdout=io.StringIO())
            step.assert_called_once()
            lines = heartbeat.read_text().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertRegex(lines[1], r"^deadline_reminders=\d{4}-\d\d-\d\dT\S+ weekly_digest=(\d{4}-W\d\d|-)$")
        self.assertTrue(self.notes_for(self.lead).exists())

    def test_reminder_failure_does_not_stop_notify_crew(self):
        with mock.patch("core.management.commands.notify_crew.close_old_connections"), \
                mock.patch("core.management.commands.notify_crew.run_scheduled_reminders",
                           side_effect=RuntimeError("x")), \
                self.assertLogs("core.management.commands.notify_crew", level="ERROR"):
            call_command("notify_crew", stdout=io.StringIO())

    def test_system_status_shows_the_last_run(self):
        admin = self.person(self.station, "w-admin", Membership.Role.ADMIN)
        dr.run_scheduled_reminders(now=_at(self.monday, 7))
        self.client.force_login(admin)
        page = self.client.get(reverse("system_status"))
        self.assertContains(page, "Fristen-Erinnerungen")
        self.assertContains(page, "2026-W46")


@override_settings(EMAIL_HOST="smtp.example.org", EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
                   SITE_URL="https://wache.example")
class ReminderEmailTests(_StationMixin, TestCase):
    """Entscheidung 6: E-Mail nur eingerichtet und nur nach eigener Wahl."""

    def setUp(self):
        self.station = self.make_station()
        self.lead = self.person(self.station, "m-lead", Membership.Role.SHIFT_LEAD)
        self.other = self.person(self.station, "m-other", Membership.Role.ADMIN)
        self.today = date(2026, 11, 2)
        Vehicle.objects.create(station=self.station, slug="rtw", call_sign="RTW 3", license_plate="RW-3",
                               next_hu_date=self.today + timedelta(days=7), next_uvv_date=self.today)

    def test_opted_in_person_gets_one_mail_with_all_new_reminders(self):
        Membership.objects.filter(user=self.lead).update(reminder_email=True)
        self.assertEqual(send_deadline_reminders(station=self.station, today=self.today), 4)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["m-lead@example.org"])
        self.assertIn("2 Fristen-Erinnerungen", message.subject)
        self.assertIn("HU fällig in 7 Tagen: RTW 3", message.body)
        self.assertIn("https://wache.example/konto/erinnerungen/", message.body)

    def test_no_mail_without_opt_in(self):
        send_deadline_reminders(station=self.station, today=self.today)
        self.assertEqual(mail.outbox, [])

    @override_settings(EMAIL_HOST="")
    def test_no_mail_when_email_is_not_configured(self):
        Membership.objects.filter(user=self.lead).update(reminder_email=True)
        send_deadline_reminders(station=self.station, today=self.today)
        self.assertEqual(mail.outbox, [])

    @override_settings(DEMO_MODE=True)
    def test_no_mail_in_the_public_demo(self):
        Membership.objects.filter(user=self.lead).update(reminder_email=True)
        send_deadline_reminders(station=self.station, today=self.today)
        self.assertEqual(mail.outbox, [])

    def test_digest_mail_contains_the_full_list(self):
        Membership.objects.filter(user=self.lead).update(reminder_email=True)
        for n in range(12):
            StationTask.objects.create(station=self.station, title=f"Aufgabe {n:02d}",
                                       due_date=self.today + timedelta(days=2))
        send_weekly_digest(station=self.station, today=self.today)
        self.assertEqual(len(mail.outbox), 1)
        for n in range(12):
            self.assertIn(f"Aufgabe {n:02d}", mail.outbox[0].body)

    def test_smtp_failure_keeps_the_inbox_entry(self):
        Membership.objects.filter(user=self.lead).update(reminder_email=True)
        with mock.patch("django.core.mail.backends.locmem.EmailBackend.send_messages", side_effect=OSError("smtp")), \
                self.assertLogs("core.deadline_reminders", level="ERROR"):
            self.assertEqual(send_deadline_reminders(station=self.station, today=self.today), 4)
        self.assertEqual(self.notes_for(self.lead).count(), 2)


class SopAudienceTests(_StationMixin, TestCase):
    """Entscheidung 4: Zielgruppe ohne Terminal, Auditor und Inaktive; Funktion; nur „In Kraft“."""

    def setUp(self):
        self.station = self.make_station(slug="rw-sop-p2")
        self.lead = self.person(self.station, "s-lead", Membership.Role.SHIFT_LEAD)
        self.member = self.person(self.station, "s-member")
        self.hygiene = self.person(self.station, "s-hygiene", is_hygiene_lead=True)
        self.auditor = self.person(self.station, "s-auditor", Membership.Role.AUDITOR)
        self.gone = self.person(self.station, "s-gone")
        User.objects.filter(pk=self.gone.pk).update(is_active=False)
        self.left = self.person(self.station, "s-left")
        Membership.objects.filter(user=self.left).update(is_active=False)
        self.terminal_user = set_station_code(self.station, "1234", set_by=self.lead).service_user
        self.due = timezone.localdate() + timedelta(days=7)
        self.sop = SOPDocument.objects.create(
            station=self.station, slug="da-1", doc_number="DA-1", title="Händedesinfektion",
            requires_acknowledgment=True, ack_due_date=self.due, created_by=self.lead,
        )
        self.rev = SOPRevision.objects.create(sop=self.sop, version_label="1.0", content_markdown="Text",
                                              approved_by=self.lead)

    def test_quota_and_open_people_exclude_terminal_auditor_and_inactive(self):
        self.assertEqual(self.sop.ack_progress()["target_count"], 3)
        self.assertCountEqual(list(self.sop.unacknowledged_users()), [self.lead, self.member, self.hygiene])
        for user in (self.lead, self.member, self.hygiene):
            SOPReceipt.objects.create(station=self.station, sop=self.sop, revision=self.rev, user=user)
        self.assertEqual(self.sop.ack_progress()["percent"], 100)
        self.client.force_login(self.lead)
        page = self.client.get(reverse("sop_detail", args=[self.sop.slug]))
        self.assertNotContains(page, reverse("sop_remind", args=[self.sop.slug]))

    def test_reminders_never_reach_terminal_or_auditor(self):
        send_deadline_reminders(station=self.station, today=timezone.localdate())
        self.client.force_login(self.lead)
        self.client.post(reverse("sop_remind", args=[self.sop.slug]))
        for user in (self.auditor, self.terminal_user, self.gone, self.left):
            self.assertFalse(self.notes_for(user).exists(), user.username)
        self.assertTrue(self.notes_for(self.member, kind=UserNotification.Kind.SOP_DUE).exists())

    def test_target_function(self):
        self.sop.target_function = "hygiene"
        self.sop.save(update_fields=["target_function"])
        self.assertEqual(self.sop.target_user_ids(), {self.hygiene.pk})
        self.assertEqual(self.sop.target_group_label, "Funktion Hygiene / Desinfektor:in")
        self.sop.target_role = Membership.Role.SHIFT_LEAD
        self.sop.save(update_fields=["target_role"])
        self.assertEqual(self.sop.target_user_ids(), set())
        self.assertEqual(self.sop.target_group_label, "Schichtleitung mit Funktion Hygiene / Desinfektor:in")

    def test_outside_target_group_is_not_asked_but_may_acknowledge_voluntarily(self):
        self.sop.target_function = "hygiene"
        self.sop.save(update_fields=["target_function"])
        self.client.force_login(self.member)
        page = self.client.get(reverse("sop_detail", args=[self.sop.slug]))
        self.assertNotContains(page, "Pflichtquittierung ausstehend")
        self.assertContains(page, "Nicht für deine Zielgruppe")
        self.client.post(reverse("sop_acknowledge", args=[self.sop.slug]))
        self.assertTrue(SOPReceipt.objects.filter(sop=self.sop, user=self.member).exists())
        self.assertEqual(self.sop.ack_progress(), {"acknowledged_count": 0, "target_count": 1, "percent": 0})
        self.client.force_login(self.hygiene)
        self.assertContains(self.client.get(reverse("sop_detail", args=[self.sop.slug])), "Pflichtquittierung ausstehend")

    def test_for_you_card_and_list_apply_the_target_group(self):
        from core.module_overview import module_attention_cards

        self.sop.target_role = Membership.Role.SHIFT_LEAD
        self.sop.save(update_fields=["target_role"])
        member_cards = {card["key"]: card for card in module_attention_cards(self.station, self.member)}
        self.assertNotIn("orga", member_cards)
        lead_cards = {card["key"]: card for card in module_attention_cards(self.station, self.lead)}
        self.assertEqual(lead_cards["orga"]["value"], 1)
        auditor_cards = {card["key"] for card in module_attention_cards(self.station, self.auditor)}
        self.assertNotIn("orga", auditor_cards)

    def test_orga_list_labels_follow_the_target_group(self):
        self.sop.target_role = Membership.Role.SHIFT_LEAD
        self.sop.save(update_fields=["target_role"])
        self.client.force_login(self.member)
        page = self.client.get(reverse("orga_dashboard"))
        self.assertNotContains(page, "Quittierung nötig")
        self.assertNotContains(page, ">Quittiert<")
        self.client.force_login(self.lead)
        self.assertContains(self.client.get(reverse("orga_dashboard")), "Quittierung nötig")

    def test_reminders_only_for_sops_in_force(self):
        SOPDocument.objects.filter(pk=self.sop.pk).update(status=SOPDocument.Status.DRAFT)
        self.assertEqual(send_deadline_reminders(station=self.station, today=timezone.localdate()), 0)
        self.client.force_login(self.lead)
        response = self.client.post(reverse("sop_remind", args=[self.sop.slug]), follow=True)
        self.assertContains(response, "Erinnerungen gibt es nur für Dienstanweisungen in Kraft.")
        self.assertFalse(UserNotification.objects.exists())

    def test_draft_cannot_be_acknowledged(self):
        SOPDocument.objects.filter(pk=self.sop.pk).update(status=SOPDocument.Status.DRAFT)
        self.client.force_login(self.member)
        response = self.client.post(reverse("sop_acknowledge", args=[self.sop.slug]), follow=True)
        self.assertContains(response, "noch ein Entwurf")
        self.assertFalse(SOPReceipt.objects.exists())

    def test_terminal_service_account_cannot_acknowledge(self):
        from core.orga_models import acknowledgement_refusal

        # Außerhalb eines registrierten Terminals hält schon die Middleware das
        # Dienstkonto auf; die Regel selbst verweigert unabhängig davon.
        self.client.force_login(self.terminal_user)
        response = self.client.post(reverse("sop_acknowledge", args=[self.sop.slug]))
        self.assertNotEqual(response.status_code, 200)
        self.assertFalse(SOPReceipt.objects.exists())
        refusal = acknowledgement_refusal(self.sop, Membership.objects.get(user=self.terminal_user))
        self.assertEqual(refusal[0], "forbidden")
        self.assertIsNone(acknowledgement_refusal(self.sop, Membership.objects.get(user=self.member)))

    def test_new_revision_reminds_again_at_the_same_threshold(self):
        today = self.due - timedelta(days=7)
        send_deadline_reminders(station=self.station, today=today)
        self.assertEqual(self.notes_for(self.member, kind=UserNotification.Kind.SOP_DUE).count(), 1)
        SOPRevision.objects.create(sop=self.sop, version_label="1.1", content_markdown="Neu", approved_by=self.lead)
        send_deadline_reminders(station=self.station, today=today)
        self.assertEqual(self.notes_for(self.member, kind=UserNotification.Kind.SOP_DUE).count(), 2)

    def test_form_offers_no_auditor_and_offers_functions(self):
        from core.orga_forms import SOPDocumentForm

        form = SOPDocumentForm(station=self.station)
        roles = [value for value, _label in form.fields["target_role"].choices]
        self.assertNotIn(Membership.Role.AUDITOR, roles)
        functions = [value for value, _label in form.fields["target_function"].choices]
        self.assertEqual(functions, ["", "mpg", "hygiene", "material", "fleet", "safety"])


class SopNamesAgreementTests(_StationMixin, TestCase):
    """Entscheidung 5: Namen nur nach Vereinbarung."""

    def setUp(self):
        self.station = self.make_station(slug="rw-names")
        self.admin = self.person(self.station, "n-admin", Membership.Role.ADMIN)
        self.lead = self.person(self.station, "n-lead", Membership.Role.SHIFT_LEAD)
        self.member = User.objects.create_user("n-member", password="pw-123456789", first_name="Mara",
                                               last_name="Muster")
        Membership.objects.create(user=self.member, station=self.station, role=Membership.Role.MEMBER)
        self.open_member = self.person(self.station, "n-open")
        self.sop = SOPDocument.objects.create(station=self.station, slug="da-2", doc_number="DA-2", title="Funk",
                                              created_by=self.lead)
        self.rev = SOPRevision.objects.create(sop=self.sop, version_label="1.0", content_markdown="Text",
                                              approved_by=self.lead)
        SOPReceipt.objects.create(station=self.station, sop=self.sop, revision=self.rev, user=self.member)
        self.client.force_login(self.lead)

    def test_without_agreement_only_counts_and_quota(self):
        page = self.client.get(reverse("sop_detail", args=[self.sop.slug]))
        self.assertContains(page, "1 / 4 (25")
        self.assertNotContains(page, "Mara")
        self.assertNotContains(page, "Mitarbeiter-Quittierungsbuch")
        self.assertContains(page, "Namen sind ausgeblendet")
        csv_text = self.client.get(reverse("sop_export_audit", args=[self.sop.slug])).content.decode("utf-8-sig")
        self.assertNotIn("n-member", csv_text)
        self.assertNotIn("Mara", csv_text)
        header, row = csv_text.strip().split("\r\n")[:2]
        self.assertIn("Lesebestätigungen", header)
        self.assertTrue(row.endswith(";1;1;4"), row)

    def test_manual_reminder_works_without_names(self):
        response = self.client.post(reverse("sop_remind", args=[self.sop.slug]), follow=True)
        self.assertContains(response, "Erinnerung an 3 offene Person(en) versendet.")
        self.assertNotContains(response, "n-open")
        self.assertTrue(self.notes_for(self.open_member, kind=UserNotification.Kind.SOP_DUE).exists())

    def test_with_agreement_names_are_shown(self):
        Station.objects.filter(pk=self.station.pk).update(sop_receipt_names_agreed=True)
        page = self.client.get(reverse("sop_detail", args=[self.sop.slug]))
        self.assertContains(page, "Mara")
        csv_text = self.client.get(reverse("sop_export_audit", args=[self.sop.slug])).content.decode("utf-8-sig")
        self.assertIn("n-member", csv_text)

    def test_only_the_admin_switches_and_the_change_is_audited(self):
        self.assertEqual(self.client.get(reverse("station_settings")).status_code, 403)
        self.client.force_login(self.admin)
        page = self.client.get(reverse("station_settings"))
        self.assertContains(page, "Beschäftigtenvertretung")
        data = {
            "name": self.station.name, "organization_profile": self.station.organization_profile,
            "holiday_state": self.station.holiday_state, "orga_enabled": "on", "sop_receipt_names_agreed": "on",
            "traffic_radius_km": 25,
        }
        response = self.client.post(reverse("station_settings"), data)
        self.assertEqual(response.status_code, 302, getattr(response, "context", None) and response.context["form"].errors)
        self.station.refresh_from_db()
        self.assertTrue(self.station.sop_receipt_names_agreed)
        event = AuditEvent.objects.filter(action="station.settings_updated").latest("pk")
        self.assertIn("sop_receipt_names_agreed", event.metadata["fields"])


class TerminalFunctionGuardTests(_StationMixin, TestCase):
    """Entscheidung 8: Das Wachenterminal-Konto bekommt keine Funktion."""

    def setUp(self):
        self.station = self.make_station(slug="rw-terminal")
        self.admin = self.person(self.station, "t-admin", Membership.Role.ADMIN)
        self.terminal_user = set_station_code(self.station, "2468", set_by=self.admin).service_user
        self.membership = Membership.objects.get(user=self.terminal_user)

    def test_membership_update_rejects_functions(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("membership_update", args=[self.membership.pk]), {
            "role": Membership.Role.MEMBER, "is_active": "on", "is_hygiene_lead": "on", "is_mpg_lead": "on",
        })
        self.assertIn(response.status_code, (200, 302))
        self.membership.refresh_from_db()
        self.assertFalse(self.membership.is_hygiene_lead)
        self.assertFalse(self.membership.is_mpg_lead)
        page = self.client.get(reverse("membership_update", args=[self.membership.pk]))
        self.assertContains(page, "Das Wachenterminal-Konto kann keine Funktion übernehmen.")

    def test_model_clean_rejects_functions(self):
        self.membership.is_fleet_lead = True
        with self.assertRaises(ValidationError):
            self.membership.full_clean()
        other = Membership.objects.get(user=self.admin)
        other.is_fleet_lead = True
        other.full_clean()

    def test_migration_clears_existing_functions(self):
        Membership.objects.filter(pk=self.membership.pk).update(is_hygiene_lead=True, is_safety_lead=True)
        Membership.objects.filter(user=self.admin).update(is_hygiene_lead=True)
        migration = importlib.import_module("core.migrations.0078_reminder_subscriptions_sop_audience")
        migration.clear_terminal_functions(django_apps, None)
        self.membership.refresh_from_db()
        self.assertFalse(self.membership.is_hygiene_lead or self.membership.is_safety_lead)
        self.assertTrue(Membership.objects.get(user=self.admin).is_hygiene_lead)


class ReminderSettingsPageTests(_StationMixin, TestCase):
    """Entscheidung 3 und 6: Abo und E-Mail stellt jede Person selbst ein."""

    def setUp(self):
        self.station = self.make_station(slug="rw-settings")
        self.fleet = self.person(self.station, "e-fleet", is_fleet_lead=True)
        self.plain = self.person(self.station, "e-plain")
        self.url = reverse("reminder_settings")

    def test_function_holder_sees_only_own_areas_and_can_switch_off(self):
        self.client.force_login(self.fleet)
        page = self.client.get(self.url)
        self.assertContains(page, "Fahrzeuge")
        self.assertNotContains(page, "Medizinprodukte")
        self.assertContains(page, "E-Mail ist auf diesem Server nicht eingerichtet")
        self.client.post(self.url, {})
        membership = Membership.objects.get(user=self.fleet)
        self.assertIs(membership.remind_fleet, False)
        self.assertIs(membership.remind_mpg, None)
        self.assertTrue(AuditEvent.objects.filter(action="membership.reminders_updated").exists())
        self.client.post(self.url, {"remind_fleet": "on"})
        self.assertIsNone(Membership.objects.get(user=self.fleet).remind_fleet)

    @override_settings(EMAIL_HOST="smtp.example.org")
    def test_email_opt_in_only_when_configured(self):
        self.client.force_login(self.plain)
        page = self.client.get(self.url)
        self.assertContains(page, "Bereiche abonnieren können")
        self.client.post(self.url, {"reminder_email": "on"})
        self.assertTrue(Membership.objects.get(user=self.plain).reminder_email)

    def test_terminal_account_has_no_settings(self):
        admin = self.person(self.station, "e-admin", Membership.Role.ADMIN)
        terminal_user = set_station_code(self.station, "1357", set_by=admin).service_user
        self.client.force_login(terminal_user)
        self.assertNotEqual(self.client.get(self.url).status_code, 200)
        # Auch ohne die Terminal-Middleware: die Ansicht selbst lehnt ab.
        from django.http import Http404
        from django.test import RequestFactory

        from core.reminder_views import reminder_settings

        request = RequestFactory().get(self.url)
        request.user = terminal_user
        with self.assertRaises(Http404):
            reminder_settings(request)

    def test_account_page_links_the_settings(self):
        self.client.force_login(self.plain)
        self.assertContains(self.client.get(reverse("account_home")), self.url)


class SopAppApiTests(_StationMixin, TestCase):
    """Entscheidung 10: Lesepflicht und Benachrichtigungen in der App."""

    def setUp(self):
        self.station = self.make_station(slug="rw-api-sop")
        self.lead = self.person(self.station, "a-lead", Membership.Role.SHIFT_LEAD)
        self.member = self.person(self.station, "a-member")
        self.auth = self.token(self.member)
        self.due = timezone.localdate() + timedelta(days=3)
        self.sop = SOPDocument.objects.create(station=self.station, slug="da-3", doc_number="DA-3", title="Funk",
                                              ack_due_date=self.due, created_by=self.lead)
        self.rev = SOPRevision.objects.create(sop=self.sop, version_label="1.0", content_markdown="Text")
        self.lead_only = SOPDocument.objects.create(station=self.station, slug="da-4", doc_number="DA-4",
                                                    title="Leitung", target_role=Membership.Role.SHIFT_LEAD,
                                                    created_by=self.lead)
        SOPRevision.objects.create(sop=self.lead_only, version_label="1.0", content_markdown="Text")
        draft = SOPDocument.objects.create(station=self.station, slug="da-5", doc_number="DA-5", title="Entwurf",
                                           status=SOPDocument.Status.DRAFT, created_by=self.lead)
        SOPRevision.objects.create(sop=draft, version_label="1.0", content_markdown="Text")
        self.draft = draft

    def token(self, user, scopes=None):
        raw = f"wb_test_p2_{user.username}_token_1234567890"
        ApiToken.objects.create(user=user, label="t", token_prefix=raw[:11], token_hash=hash_api_token(raw),
                                scopes=list(scopes or DEFAULT_MOBILE_SCOPES),
                                expires_at=timezone.now() + timedelta(days=1))
        return {"HTTP_AUTHORIZATION": f"Token {raw}"}

    def test_list_shows_only_own_obligations_without_names(self):
        data = self.client.get("/api/v1/dienstanweisungen/", **self.auth).json()
        self.assertEqual([item["doc_number"] for item in data["results"]], ["DA-3"])
        item = data["results"][0]
        self.assertEqual(item["revision"], {"id": self.rev.pk, "version": "1.0"})
        self.assertEqual(item["ack_due_date"], self.due.isoformat())
        self.assertFalse(item["acknowledged"])
        self.assertIsNone(item["acknowledged_at"])
        self.assertEqual(item["url"], reverse("sop_detail", args=[self.sop.slug]))
        self.assertNotIn("a-lead", json.dumps(data))

    def test_acknowledge_like_the_web(self):
        response = self.client.post(f"/api/v1/dienstanweisungen/{self.sop.pk}/quittieren/",
                                    data=json.dumps({"revision": self.rev.pk}), content_type="application/json",
                                    REMOTE_ADDR="203.0.113.5", HTTP_USER_AGENT="App/1.0", **self.auth)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["acknowledged"])
        receipt = SOPReceipt.objects.get(sop=self.sop, user=self.member)
        self.assertIsNone(receipt.ip_address)
        self.assertEqual(receipt.user_agent, "")
        again = self.client.post(f"/api/v1/dienstanweisungen/{self.sop.pk}/quittieren/", **self.auth)
        self.assertEqual(again.status_code, 200)
        self.assertFalse(again.json()["created"])
        listing = self.client.get("/api/v1/dienstanweisungen/?offen=1", **self.auth).json()
        self.assertEqual(listing["results"], [])
        full = self.client.get("/api/v1/dienstanweisungen/", **self.auth).json()
        self.assertTrue(full["results"][0]["acknowledged"])
        self.assertIsNotNone(full["results"][0]["acknowledged_at"])

    def test_outdated_revision_draft_and_foreign_station_are_refused(self):
        stale = self.client.post(f"/api/v1/dienstanweisungen/{self.sop.pk}/quittieren/",
                                 data=json.dumps({"revision": self.rev.pk + 999}), content_type="application/json",
                                 **self.auth)
        self.assertEqual(stale.status_code, 409)
        draft = self.client.post(f"/api/v1/dienstanweisungen/{self.draft.pk}/quittieren/", **self.auth)
        self.assertEqual(draft.status_code, 409)
        other = self.make_station(slug="rw-api-other")
        foreign = SOPDocument.objects.create(station=other, slug="x", doc_number="X", title="X", created_by=self.lead)
        SOPRevision.objects.create(sop=foreign, version_label="1.0", content_markdown="Text")
        self.assertEqual(self.client.post(f"/api/v1/dienstanweisungen/{foreign.pk}/quittieren/",
                                          **self.auth).status_code, 404)
        self.assertFalse(SOPReceipt.objects.exists())

    def test_auditor_is_refused(self):
        auditor = self.person(self.station, "a-auditor", Membership.Role.AUDITOR)
        auth = self.token(auditor)
        with self.assertLogs("django.request", "WARNING"):
            self.assertEqual(self.client.get("/api/v1/dienstanweisungen/", **auth).status_code, 403)
            self.assertEqual(self.client.post(f"/api/v1/dienstanweisungen/{self.sop.pk}/quittieren/",
                                              **auth).status_code, 403)

    def test_scope_read_me_is_required(self):
        auth = self.token(self.lead, scopes=["read:handovers"])
        with self.assertLogs("django.request", "WARNING"):
            self.assertEqual(self.client.get("/api/v1/dienstanweisungen/", **auth).status_code, 403)

    def test_notifications_kinds_filter_and_mark_read(self):
        for kind, key in (("vehicle_ready", "a"), ("deadline_due", "b"), ("sop_due", "c")):
            UserNotification.objects.create(station=self.station, user=self.member, kind=kind, title=kind,
                                            dedupe_key=key)
        data = self.client.get("/api/v1/benachrichtigungen/?kinds=vehicle_ready,unbekannt", **self.auth).json()
        self.assertEqual([item["kind"] for item in data["results"]], ["vehicle_ready"])
        self.assertEqual(data["unread_count"], 1)
        marked = self.client.post("/api/v1/benachrichtigungen/gelesen/",
                                  data=json.dumps({"kinds": ["deadline_due", "sop_due"]}),
                                  content_type="application/json", **self.auth)
        self.assertEqual(marked.json()["marked"], 2)
        self.assertEqual(self.client.get("/api/v1/benachrichtigungen/", **self.auth).json()["unread_count"], 1)
        with self.assertLogs("django.request", "WARNING"):
            refused = self.client.post("/api/v1/benachrichtigungen/gelesen/", **self.auth)
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(UserNotification.objects.filter(read_at__isnull=True).count(), 1)


class FunctionLabelTests(_StationMixin, TestCase):
    """Entscheidung 9: Funktionsbezeichnungen über gettext."""

    def test_labels_come_from_the_translated_function_list(self):
        station = self.make_station(slug="rw-labels")
        user = self.person(station, "l-user", is_mpg_lead=True, is_safety_lead=True)
        membership = Membership.objects.get(user=user)
        with mock.patch("core.models.Membership.FUNCTIONS", (
            ("mpg", "is_mpg_lead", "MPG officer"),
            ("safety", "is_safety_lead", "Safety"),
        )):
            self.assertEqual(list(membership.function_labels), ["MPG officer", "Safety"])
        self.assertEqual(list(membership.function_labels), ["MPG-Beauftragte/r", "Sicherheit / Arbeitsschutz"])
