from datetime import timedelta
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Membership, Station
from core.orga_models import SOPDocument, SOPReceipt, SOPRevision, StationContact


class OrgaModuleTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(
            name="Rettungswache Test Orga",
            slug="rw-test-orga",
            orga_enabled=True,
        )
        self.user = User.objects.create_user(
            username="notfallsani_orga",
            first_name="Maximilian",
            last_name="Retter",
            password="testpassword123",
        )
        self.membership = Membership.objects.create(
            user=self.user,
            station=self.station,
            role=Membership.Role.SHIFT_LEAD,
            is_active=True,
        )
        self.client.force_login(self.user)

    def test_dashboard_renders_and_seeds_defaults(self):
        resp = self.client.get(reverse("orga_dashboard"))
        self.assertEqual(resp.status_code, 200)

        # Verified auto-seeding of emergency contacts and standard SOP
        self.assertTrue(StationContact.objects.filter(station=self.station, is_speed_dial=True).exists())
        self.assertTrue(SOPDocument.objects.filter(station=self.station, doc_number="SOP-MED-01").exists())
        self.assertContains(resp, "SOP-MED-01")
        self.assertContains(resp, "Integrierte Leitstelle")

    def test_sop_detail_and_acknowledgment(self):
        # Trigger seeding first
        self.client.get(reverse("orga_dashboard"))
        sop = SOPDocument.objects.get(station=self.station, doc_number="SOP-MED-01")

        self.assertFalse(sop.user_has_acknowledged(self.user))

        detail_resp = self.client.get(reverse("sop_detail", args=[sop.slug]))
        self.assertEqual(detail_resp.status_code, 200)
        self.assertContains(detail_resp, "Pflichtquittierung ausstehend")

        # Quittieren
        ack_resp = self.client.post(reverse("sop_acknowledge", args=[sop.slug]), follow=True)
        self.assertEqual(ack_resp.status_code, 200)
        self.assertContains(ack_resp, "Kenntnisnahme quittiert")

        # Verification
        self.assertTrue(sop.user_has_acknowledged(self.user))
        self.assertTrue(SOPReceipt.objects.filter(sop=sop, user=self.user).exists())

        # Second acknowledgment should not duplicate
        self.client.post(reverse("sop_acknowledge", args=[sop.slug]))
        self.assertEqual(SOPReceipt.objects.filter(sop=sop, user=self.user).count(), 1)

    def test_sop_create_with_sha256_hash(self):
        resp = self.client.post(
            reverse("sop_create"),
            {
                "doc_number": "SOP-MED-02",
                "title": "Akutes Koronarsyndrom & ACS-Algorithmus",
                "category": SOPDocument.Category.MED_HEILKUNDE,
                "status": SOPDocument.Status.ACTIVE,
                "valid_from": timezone.localdate().isoformat(),
                "requires_acknowledgment": True,
                "initial_version": "1.0",
                "initial_content": "# ACS Leitfaden\n\n12-Kanal-EKG innerhalb von 10 Minuten schreiben.",
            },
        )
        self.assertEqual(resp.status_code, 302)
        sop = SOPDocument.objects.get(doc_number="SOP-MED-02")
        self.assertIsNotNone(sop.latest_revision)
        self.assertEqual(sop.current_version, "1.0")
        self.assertTrue(len(sop.latest_revision.content_hash) == 64)  # SHA-256 length

    def test_new_revision_requires_re_acknowledgment(self):
        # Seed and acknowledge v1.0
        self.client.get(reverse("orga_dashboard"))
        sop = SOPDocument.objects.get(station=self.station, doc_number="SOP-MED-01")
        self.client.post(reverse("sop_acknowledge", args=[sop.slug]))
        self.assertTrue(sop.user_has_acknowledged(self.user))

        # Publish v1.1
        rev_resp = self.client.post(
            reverse("sop_revision_create", args=[sop.slug]),
            {
                "version_label": "1.1",
                "effective_date": timezone.localdate().isoformat(),
                "change_summary": "Aktualisierung der Schockraumkriterien",
                "content_markdown": "# SOP-MED-01 v1.1\n\nNeue Kriterien gem. Traumaregister.",
            },
        )
        self.assertEqual(rev_resp.status_code, 302)
        sop.refresh_from_db()
        self.assertEqual(sop.current_version, "1.1")

        # Must require new acknowledgment for v1.1!
        self.assertFalse(sop.user_has_acknowledged(self.user))

    def test_contact_management(self):
        # Create contact
        resp = self.client.post(
            reverse("contact_create"),
            {
                "category": StationContact.Category.HOSPITAL,
                "name": "Klinikum Großhadern Notaufnahme",
                "contact_person": "Triage / Schockraum",
                "phone_primary": "089 4400 0",
                "phone_secondary": "089 4400 75111",
                "notes": "Überregionaler Maximalversorger",
                "is_speed_dial": True,
                "order_rank": 5,
            },
        )
        self.assertEqual(resp.status_code, 302)
        contact = StationContact.objects.get(name="Klinikum Großhadern Notaufnahme")
        self.assertTrue(contact.is_speed_dial)

        # Delete contact
        del_resp = self.client.post(reverse("contact_delete", args=[contact.pk]))
        self.assertEqual(del_resp.status_code, 302)
        self.assertFalse(StationContact.objects.filter(pk=contact.pk).exists())

    def test_export_audit_csv(self):
        self.client.get(reverse("orga_dashboard"))
        sop = SOPDocument.objects.get(station=self.station, doc_number="SOP-MED-01")
        self.client.post(reverse("sop_acknowledge", args=[sop.slug]))

        csv_resp = self.client.get(reverse("sop_export_audit", args=[sop.slug]))
        self.assertEqual(csv_resp.status_code, 200)
        self.assertEqual(csv_resp["Content-Type"], "text/csv; charset=utf-8-sig")
        self.assertIn("SHA-256", csv_resp.content.decode("utf-8-sig"))
        self.assertIn(self.user.username, csv_resp.content.decode("utf-8-sig"))

    def test_station_orga_disabled_denied(self):
        self.station.orga_enabled = False
        self.station.save()

        resp = self.client.get(reverse("orga_dashboard"))
        self.assertEqual(resp.status_code, 404)
