"""Öffentliche Feedback-Seite und Posteingang für Master-Admins."""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.feedback import apply_feedback_retention
from core.feedback_models import Feedback
from core.models import AuditEvent, Membership, Station

VALID = {"kind": "wish", "message": "Bitte eine Ansicht für die Desinfektion am Monitor.", "consent": "on"}


@override_settings(FEEDBACK_ENABLED=True, FEEDBACK_PER_IP_HOUR=5)
class FeedbackPageTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_public_form_saves_without_ip_and_thanks(self):
        response = self.client.post(reverse("feedback"), {**VALID, "rating": "5", "role": "crew", "name": "Mara"})
        self.assertRedirects(response, reverse("feedback") + "?danke=1", fetch_redirect_response=False)
        entry = Feedback.objects.get()
        self.assertEqual((entry.kind, entry.rating, entry.role, entry.name), ("wish", 5, "crew", "Mara"))
        self.assertFalse(entry.from_demo)
        self.assertNotIn("127.0.0.1", str(Feedback.objects.values().get()))
        self.assertContains(self.client.get(response["Location"]), "Danke!")

    def test_consent_and_message_are_required(self):
        response = self.client.post(reverse("feedback"), {"kind": "idea", "message": ""})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Feedback.objects.exists())

    def test_honeypot_stores_nothing(self):
        response = self.client.post(reverse("feedback"), {**VALID, "website": "http://spam.example"})
        self.assertRedirects(response, reverse("feedback") + "?danke=1", fetch_redirect_response=False)
        self.assertFalse(Feedback.objects.exists())

    def test_rate_limit_per_client(self):
        for _ in range(5):
            self.client.post(reverse("feedback"), VALID)
        response = self.client.post(reverse("feedback"), VALID)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Feedback.objects.count(), 5)

    def test_rating_outside_scale_is_rejected(self):
        self.client.post(reverse("feedback"), {**VALID, "rating": "9"})
        self.assertFalse(Feedback.objects.exists())

    def test_footer_link_and_privacy_notice(self):
        self.assertContains(self.client.get(reverse("landing")), reverse("feedback"))
        self.assertContains(self.client.get(reverse("privacy")), 'id="feedback"')


class FeedbackDisabledTests(TestCase):
    @override_settings(FEEDBACK_ENABLED=False)
    def test_page_is_hidden_when_off(self):
        self.assertEqual(self.client.get(reverse("feedback")).status_code, 404)
        self.assertNotContains(self.client.get(reverse("landing")), reverse("feedback"))


@override_settings(FEEDBACK_ENABLED=True)
class FeedbackInboxTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Echte Wache", slug="echt")
        self.admin = User.objects.create_user("admin", password="x" * 16)
        Membership.objects.create(user=self.admin, station=self.station, role=Membership.Role.ADMIN)
        self.member = User.objects.create_user("mitglied", password="x" * 16)
        Membership.objects.create(user=self.member, station=self.station, role=Membership.Role.MEMBER)
        self.entry = Feedback.objects.create(kind="bug", message="Knopf reagiert nicht", email="m@example.org")

    def test_admin_reads_marks_and_deletes(self):
        self.client.force_login(self.admin)
        page = self.client.get(reverse("feedback_inbox"))
        self.assertContains(page, "Knopf reagiert nicht")
        self.assertContains(page, "mailto:m@example.org")
        self.client.post(reverse("feedback_status", args=[self.entry.pk]), {"status": "done"})
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, "done")
        self.assertNotContains(self.client.get(reverse("feedback_inbox")), "Knopf reagiert nicht")
        self.assertContains(self.client.get(reverse("feedback_inbox") + "?status=done"), "Knopf reagiert nicht")
        self.client.post(reverse("feedback_delete", args=[self.entry.pk]))
        self.assertFalse(Feedback.objects.exists())
        self.assertTrue(AuditEvent.objects.filter(action="feedback.deleted").exists())

    def test_members_have_no_access(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse("feedback_inbox")).status_code, 403)
        self.client.post(reverse("feedback_delete", args=[self.entry.pk]))
        self.assertTrue(Feedback.objects.exists())

    @override_settings(DEMO_MODE=True, DEMO_SANDBOX=True, MFA_REQUIRED=False)
    def test_demo_admins_cannot_read_feedback(self):
        cache.clear()
        self.client.post(reverse("login"), {"username": "Demo", "password": "Demo"})
        response = self.client.get(reverse("feedback_inbox"))
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        self.client.post(reverse("feedback_delete", args=[self.entry.pk]))
        self.assertTrue(Feedback.objects.exists())
        # Rückmeldungen aus der Demo werden markiert.
        self.client.post(reverse("feedback"), VALID)
        self.assertTrue(Feedback.objects.filter(from_demo=True).exists())

    def test_retention_deletes_old_entries(self):
        Feedback.objects.filter(pk=self.entry.pk).update(created_at=timezone.now() - timedelta(days=400))
        fresh = Feedback.objects.create(kind="praise", message="Super")
        self.assertEqual(apply_feedback_retention(days=365), 1)
        self.assertEqual(list(Feedback.objects.values_list("pk", flat=True)), [fresh.pk])
        self.assertEqual(apply_feedback_retention(days=0), 0)


class InstallGuideHardwareTests(TestCase):
    def test_hardware_section_lists_thin_clients(self):
        page = self.client.get(reverse("install_guide"))
        for text in ("Welcher Rechner?", "Mindestens", "Empfohlen", "Fujitsu Futro S740", "HP t630",
                     "Dell Wyse 5070", "ThinkCentre M720q", "Nicht empfohlen"):
            self.assertContains(page, text)
