"""Tests für den Wachen-Display-Modus."""
from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    BirthdayPreference,
    CalendarEvent,
    HandoverEntry,
    Membership,
    Station,
    StationTask,
)
from .display_models import DisplayToken


class DisplayAccessTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache Nord", slug="wache-nord")
        self.user = User.objects.create_user("admin@example.org", password="test-password-12345")
        Membership.objects.create(
            user=self.user, station=self.station, role=Membership.Role.ADMIN
        )
        self.raw = secrets.token_urlsafe(32)
        self.token = DisplayToken.objects.create(
            station=self.station,
            label="Flur",
            token_hash=hashlib.sha256(self.raw.encode()).hexdigest(),
            created_by=self.user,
        )

    def test_start_sets_cookie_and_redirects(self):
        response = self.client.get(reverse("display_start", args=[self.raw]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("display_home"))
        self.assertIn("rwsth_display", response.cookies)
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow, noarchive")
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
        self.assertIn("no-store", response["Cache-Control"])

    def test_display_page_requires_token(self):
        response = self.client.get(reverse("display_home"))
        self.assertEqual(response.status_code, 403)

    def test_display_page_opens_with_cookie(self):
        self.client.cookies["rwsth_display"] = self.raw
        response = self.client.get(reverse("display_home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Wache Nord")

    def test_unknown_token_is_rejected(self):
        response = self.client.get(reverse("display_start", args=["falsch"]))
        self.assertEqual(response.status_code, 403)

    def test_revoked_token_is_rejected(self):
        self.token.revoked_at = timezone.now()
        self.token.save(update_fields=["revoked_at"])
        response = self.client.get(reverse("display_start", args=[self.raw]))
        self.assertEqual(response.status_code, 403)

    def test_expired_token_is_rejected(self):
        self.token.expires_at = timezone.now() - timedelta(minutes=1)
        self.token.save(update_fields=["expires_at"])
        response = self.client.get(reverse("display_start", args=[self.raw]))
        self.assertEqual(response.status_code, 403)

    def test_last_used_is_recorded(self):
        self.client.get(reverse("display_start", args=[self.raw]))
        self.token.refresh_from_db()
        self.assertIsNotNone(self.token.last_used_at)


class DisplayDataTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache Süd", slug="wache-sued")
        self.user = User.objects.create_user("person@example.org", password="test-password-12345")
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.ADMIN)
        self.raw = secrets.token_urlsafe(32)
        DisplayToken.objects.create(
            station=self.station,
            label="TV",
            token_hash=hashlib.sha256(self.raw.encode()).hexdigest(),
            created_by=self.user,
        )
        self.client.cookies["rwsth_display"] = self.raw

    def payload(self):
        response = self.client.get(reverse("display_data"))
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_payload_has_expected_fields(self):
        data = self.payload()
        for key in ("station", "date", "events", "waste", "tasks", "urgent_handovers", "birthdays"):
            self.assertIn(key, data)
        self.assertEqual(data["station"], "Wache Süd")

    def test_handover_titles_never_appear(self):
        HandoverEntry.objects.create(
            station=self.station,
            category=HandoverEntry.Category.TASK,
            priority=HandoverEntry.Priority.URGENT,
            title="Geheimer Patientenhinweis",
            details="Interne Details",
            author=self.user,
        )
        data = self.payload()
        self.assertEqual(data["urgent_handovers"], 1)
        body = str(data)
        self.assertNotIn("Geheimer Patientenhinweis", body)
        self.assertNotIn("Interne Details", body)

    def test_task_counts_are_aggregated(self):
        StationTask.objects.create(
            station=self.station, title="Fahrzeug prüfen", band=StationTask.Band.DAILY
        )
        data = self.payload()
        self.assertGreaterEqual(data["tasks"]["total"], 1)
        self.assertEqual(
            data["tasks"]["total"], data["tasks"]["done"] + data["tasks"]["open"]
        )

    def test_birthday_requires_consent(self):
        other = User.objects.create_user(
            "geheim@example.org", password="test-password-12345", first_name="Anna", last_name="Beispiel"
        )
        today = timezone.localdate()
        BirthdayPreference.objects.create(
            user=other,
            station=self.station,
            day=today.day,
            month=today.month,
            is_visible=False,
        )
        self.assertEqual(self.payload()["birthdays"], [])

        BirthdayPreference.objects.filter(user=other).update(
            is_visible=True, consented_at=timezone.now()
        )
        birthdays = self.payload()["birthdays"]
        self.assertEqual(len(birthdays), 1)
        self.assertEqual(birthdays[0]["name"], "Anna B.")

    def test_todays_events_are_listed(self):
        # Bewusst lokale Zeit: das Display rechnet in der Zeitzone der Wache.
        start = timezone.localtime().replace(hour=9, minute=30, second=0, microsecond=0)
        CalendarEvent.objects.create(
            station=self.station,
            title="Fahrzeugübergabe",
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            created_by=self.user,
        )
        titles = [entry["title"] for entry in self.payload()["events"]]
        self.assertIn("Fahrzeugübergabe", titles)


class DisplayManagementTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache Ost", slug="wache-ost")
        self.admin = User.objects.create_user("chef@example.org", password="test-password-12345")
        Membership.objects.create(
            user=self.admin, station=self.station, role=Membership.Role.ADMIN
        )

    def test_create_token_shows_link_once(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("display_token_create"), {"label": "Flur"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(DisplayToken.objects.count(), 1)
        body = response.content.decode()
        self.assertIn("/display/start/", body)

    def test_revoke_marks_token(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("display_token_create"), {"label": "Flur"})
        token = DisplayToken.objects.first()
        self.client.post(reverse("display_token_revoke", args=[token.pk]))
        token.refresh_from_db()
        self.assertIsNotNone(token.revoked_at)

    def test_tokens_are_bound_to_station(self):
        other_station = Station.objects.create(name="Fremd", slug="fremd")
        foreign = DisplayToken.objects.create(
            station=other_station,
            label="fremd",
            token_hash=hashlib.sha256(b"x").hexdigest(),
            created_by=self.admin,
        )
        self.client.force_login(self.admin)
        response = self.client.post(reverse("display_token_revoke", args=[foreign.pk]))
        self.assertEqual(response.status_code, 302)
        foreign.refresh_from_db()
        self.assertIsNone(foreign.revoked_at)
