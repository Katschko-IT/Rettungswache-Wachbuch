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
        sop = SOPDocument.objects.create(
            station=self.station,
            slug="sop-test-01",
            doc_number="SOP-MED-01",
            title="Test-Dienstanweisung",
            status=SOPDocument.Status.ACTIVE,
            requires_acknowledgment=True,
            created_by=self.user,
        )
        SOPRevision.objects.create(
            sop=sop,
            version_label="1.0",
            content_markdown="# Testinhalt",
            change_summary="Erstfassung",
            approved_by=self.user,
        )

    def test_dashboard_never_invents_sops_or_emergency_numbers(self):
        # Versionen schützen ihre Dienstanweisung (PROTECT); QuerySet.delete
        # umgeht den Zeilenschutz der Versionen, wie es nur Tests dürfen.
        SOPRevision.objects.all().delete()
        SOPDocument.objects.all().delete()
        resp = self.client.get(reverse("orga_dashboard"))
        self.assertEqual(resp.status_code, 200)
        # Kein Auto-Seeding: keine erfundenen medizinischen Anweisungen oder
        # regional falschen Notrufnummern in einer echten Wache.
        self.assertFalse(SOPDocument.objects.filter(station=self.station).exists())
        self.assertFalse(StationContact.objects.filter(station=self.station).exists())

    def test_unread_sop_is_not_shown_as_acknowledged(self):
        resp = self.client.get(reverse("orga_dashboard"))
        self.assertContains(resp, "Quittierung nötig")
        self.assertNotContains(resp, 'status-done">Quittiert<')
        sop = SOPDocument.objects.get(slug="sop-test-01")
        self.client.post(reverse("sop_acknowledge", args=[sop.slug]))
        resp = self.client.get(reverse("orga_dashboard"))
        self.assertContains(resp, 'status-done">Quittiert<')

    def test_dashboard_lists_station_sops(self):
        resp = self.client.get(reverse("orga_dashboard"))
        self.assertContains(resp, "SOP-MED-01")

    def test_archived_sop_is_not_pending_acknowledgment(self):
        SOPDocument.objects.update(status=SOPDocument.Status.ARCHIVED)
        resp = self.client.get(reverse("orga_dashboard") + "?filter=pending")
        self.assertNotContains(resp, "SOP-MED-01")

    def test_sop_detail_and_acknowledgment(self):
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
        # Acknowledge v1.0
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


class SopOutOfForceTests(TestCase):
    """„Außer Kraft“ statt Löschen: Nachweise bleiben, neue Quittierungen gibt es nicht."""

    def setUp(self):
        self.station = Station.objects.create(name="RW Außer Kraft", slug="rw-ausser-kraft", orga_enabled=True)
        self.lead = User.objects.create_user(username="ak-lead", password="testpassword123")
        Membership.objects.create(user=self.lead, station=self.station, role=Membership.Role.SHIFT_LEAD)
        self.member = User.objects.create_user(username="ak-member", password="testpassword123")
        Membership.objects.create(user=self.member, station=self.station, role=Membership.Role.MEMBER)
        self.sop = SOPDocument.objects.create(
            station=self.station, slug="da-hyg-01", doc_number="DA-HYG-01", title="Händedesinfektion",
            status=SOPDocument.Status.ACTIVE, requires_acknowledgment=True, created_by=self.lead,
        )
        SOPRevision.objects.create(sop=self.sop, version_label="1.0", content_markdown="Text", approved_by=self.lead)

    def _edit(self, status):
        return self.client.post(reverse("sop_edit", args=[self.sop.slug]), {
            "doc_number": self.sop.doc_number, "title": self.sop.title, "category": self.sop.category,
            "status": status, "valid_from": self.sop.valid_from.isoformat(),
            "requires_acknowledgment": "on",
        })

    def test_archived_sop_cannot_be_acknowledged(self):
        """NEGATIV: Eine außer Kraft gesetzte Dienstanweisung nimmt keine Quittierung an."""
        SOPDocument.objects.filter(pk=self.sop.pk).update(status=SOPDocument.Status.ARCHIVED)
        self.client.force_login(self.member)
        detail = self.client.get(reverse("sop_detail", args=[self.sop.slug]))
        self.assertContains(detail, "Diese Dienstanweisung ist außer Kraft.")
        self.assertNotContains(detail, reverse("sop_acknowledge", args=[self.sop.slug]))
        response = self.client.post(reverse("sop_acknowledge", args=[self.sop.slug]), follow=True)
        self.assertContains(response, "kann nicht mehr quittiert werden")
        self.assertFalse(SOPReceipt.objects.filter(sop=self.sop).exists())

    def test_status_change_is_audited_and_evidence_stays(self):
        from core.models import AuditEvent

        self.client.force_login(self.member)
        self.client.post(reverse("sop_acknowledge", args=[self.sop.slug]))
        self.client.force_login(self.lead)
        form = self.client.get(reverse("sop_edit", args=[self.sop.slug]))
        self.assertContains(form, "Dienstanweisungen werden nicht gelöscht.")
        response = self._edit(SOPDocument.Status.ARCHIVED)
        self.assertEqual(response.status_code, 302)
        event = AuditEvent.objects.get(action="orga.sop_status_changed")
        self.assertEqual(event.metadata, {"fields": ["status"], "from": "active", "to": "archived"})
        self.assertEqual(event.object_type, "SOPDocument")
        self.assertEqual(SOPReceipt.objects.filter(sop=self.sop).count(), 1)
        self.assertEqual(SOPRevision.objects.filter(sop=self.sop).count(), 1)
        # Speichern ohne Statuswechsel schreibt keinen weiteren Eintrag.
        self._edit(SOPDocument.Status.ARCHIVED)
        self.assertEqual(AuditEvent.objects.filter(action="orga.sop_status_changed").count(), 1)

    def test_member_cannot_change_status(self):
        """NEGATIV: Mitglieder setzen keine Dienstanweisung außer Kraft."""
        from core.models import AuditEvent

        self.client.force_login(self.member)
        self._edit(SOPDocument.Status.ARCHIVED)
        self.sop.refresh_from_db()
        self.assertEqual(self.sop.status, SOPDocument.Status.ACTIVE)
        self.assertFalse(AuditEvent.objects.filter(action="orga.sop_status_changed").exists())

    def test_sop_with_versions_cannot_be_deleted(self):
        """NEGATIV: Versionen und Quittierungen schützen die Dienstanweisung."""
        from django.db.models.deletion import ProtectedError

        with self.assertRaises(ProtectedError):
            self.sop.delete()
        self.assertTrue(SOPDocument.objects.filter(pk=self.sop.pk).exists())
