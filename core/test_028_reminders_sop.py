"""Tests für Roadmap 0.28 Paket 3:
- Fristen-Erinnerungen bei 30, 7 und 0 Tagen (STK zum Monatsende, MTK zum Jahresende,
  DGUV V3, HU, UVV, Chargenverfall, Mangel, Dienstanweisung, Prüfung/Aufgabe) + Wochenübersicht
- Dienstanweisungen-Lesepflicht mit Frist (ack_due_date), Zielgruppe (target_role),
  aggregierter Lesequote (ack_progress) und gezielter Erinnerung nur an Offene (sop_remind).
"""
from __future__ import annotations

import io
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
from core.warehouse_models import ItemBatch, MedicalItem


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

        # 7 Tage vor dem 31.12.2026 (MTK Jahresende) ist der 24.12.2026
        count_mtk_7 = send_deadline_reminders(station=self.station, today=date(2026, 12, 24))
        self.assertEqual(count_mtk_7, 2)
        self.assertTrue(
            UserNotification.objects.filter(
                user=self.mpg_lead,
                kind=UserNotification.Kind.DEADLINE_DUE,
                title__icontains="MTK fällig in 7 Tagen",
            ).exists()
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
        # 2. Chargenverfall
        item = MedicalItem.objects.create(station=self.station, slug="adrenalin", name="Adrenalin 1 mg")
        ItemBatch.objects.create(
            station=self.station,
            item=item,
            batch_number="LOT-7D",
            manufacturer_exp_date=due,
        )
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
        self.assertTrue(any("Verfall in 7 Tagen" in t for t in titles))
        self.assertTrue(any("Mangel-Frist in 30 Tagen" in t for t in titles))
        self.assertTrue(any("Aufgabe heute fällig" in t for t in titles))

        # Defect-Owner (member) hat die Mangel-Frist ebenfalls erhalten
        self.assertTrue(
            UserNotification.objects.filter(
                user=self.member,
                title__icontains="Mangel-Frist in 30 Tagen",
            ).exists()
        )

        # Zweiter Lauf am selben Tag: 0 neue Benachrichtigungen (Deduplizierung via dedupe_key)
        total_before = UserNotification.objects.count()
        created_second = send_deadline_reminders(station=self.station, today=self.today)
        self.assertEqual(created_second, 0)
        self.assertEqual(UserNotification.objects.count(), total_before)

        # Nicht-Schwellenwert-Tag (z. B. 15 Tage vorher) erzeugt nichts
        created_off_day = send_deadline_reminders(
            station=self.station,
            today=self.today - timedelta(days=8),
        )
        self.assertEqual(created_off_day, 0)

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
        call_command(
            "send_deadline_reminders",
            station=self.station.slug,
            thresholds="3",
            dry_run=True,
            stdout=out,
        )
        self.assertIn("Dry-Run:", out.getvalue())

        out_live = io.StringIO()
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
        self.assertIn("Lesefrist in 7 Tagen", user_note.title)
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
