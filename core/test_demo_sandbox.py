"""Öffentliche Demo: eigene Demo-Wache je Besuch, Löschung beim Abmelden."""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.demo_models import DemoSandbox
from core.models import AuditEvent, CoffeeEntry, HandoverEntry, HandoverRevision, Membership, Station

DEMO = {"username": "Demo", "password": "Demo"}
SANDBOX_ON = dict(DEMO_MODE=True, DEMO_SANDBOX=True, MFA_REQUIRED=False)


@override_settings(**SANDBOX_ON)
class DemoSandboxTests(TestCase):
    def setUp(self):
        cache.clear()

    def _start(self, client=None):
        client = client or self.client
        response = client.post(reverse("login"), DEMO)
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        user = User.objects.get(pk=client.session["_auth_user_id"])
        return user, Membership.objects.get(user=user).station

    def test_login_form_is_prefilled_with_demo(self):
        response = self.client.get(reverse("login"))
        self.assertContains(response, 'value="Demo"', count=2)
        self.assertContains(response, "eigene Demo-Wache")

    def test_demo_credentials_create_own_station_with_sample_data(self):
        user, station = self._start()
        self.assertTrue(user.username.startswith("demo-"))
        self.assertEqual(Membership.objects.get(user=user).role, Membership.Role.ADMIN)
        self.assertTrue(DemoSandbox.objects.filter(station=station).exists())
        self.assertGreaterEqual(HandoverEntry.objects.filter(station=station).count(), 3)
        self.assertTrue(CoffeeEntry.objects.filter(station=station).exists())
        self.assertFalse(user.has_usable_password(), "Demo-Konten sind nur über den Demo-Einstieg erreichbar")
        page = self.client.get(reverse("dashboard"))
        self.assertContains(page, "Deine eigene Demo-Wache")

    def test_each_visit_gets_an_isolated_station(self):
        _, station_a = self._start()
        other = self.client_class()
        user_b, station_b = self._start(other)
        self.assertNotEqual(station_a.pk, station_b.pk)
        HandoverEntry.objects.create(
            station=station_b, category="station", title="Nur in Demo B", details="x", author=user_b,
        )
        self.assertNotContains(self.client.get(reverse("handover_list")), "Nur in Demo B")
        self.assertContains(other.get(reverse("handover_list")), "Nur in Demo B")

    def test_logout_deletes_station_accounts_and_append_only_rows(self):
        real_station = Station.objects.create(name="Echte Wache", slug="echt")
        real_user = User.objects.create_user("echt", password="x" * 16)
        Membership.objects.create(user=real_user, station=real_station, role=Membership.Role.ADMIN)
        real_handover = HandoverEntry.objects.create(
            station=real_station, category="station", title="Echt", details="x", author=real_user,
        )
        user, station = self._start()
        self.assertTrue(AuditEvent.objects.filter(station=station).exists())

        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, reverse("landing") + "?demo=ende", fetch_redirect_response=False)
        self.assertFalse(Station.objects.filter(pk=station.pk).exists())
        self.assertFalse(DemoSandbox.objects.exists())
        self.assertFalse(User.objects.filter(username__startswith="demo-").exists())
        self.assertFalse(HandoverEntry.objects.filter(station_id=station.pk).exists())
        self.assertFalse(HandoverRevision.objects.filter(handover__station_id=station.pk).exists())
        self.assertFalse(CoffeeEntry.objects.filter(station_id=station.pk).exists())
        self.assertFalse(AuditEvent.objects.filter(station_id=station.pk).exists())
        connection.check_constraints()
        # Andere Wachen bleiben unberührt.
        self.assertTrue(HandoverEntry.objects.filter(pk=real_handover.pk).exists())
        self.assertTrue(User.objects.filter(pk=real_user.pk).exists())
        landing = self.client.get(response["Location"])
        self.assertContains(landing, "Deine Demo ist beendet")

    def test_idle_demo_ends_and_is_deleted(self):
        _, station = self._start()
        DemoSandbox.objects.update(last_seen_at=timezone.now() - timedelta(hours=1))
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, reverse("landing") + "?demo=abgelaufen", fetch_redirect_response=False)
        self.assertFalse(Station.objects.filter(pk=station.pk).exists())

    def test_role_switch_stays_in_the_same_demo(self):
        user, station = self._start()
        response = self.client.post(reverse("demo_switch_role"), {"role": "mitglied"})
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        member = User.objects.get(pk=self.client.session["_auth_user_id"])
        self.assertNotEqual(member.pk, user.pk)
        self.assertEqual(Membership.objects.get(user=member).station, station)
        self.assertEqual(Membership.objects.get(user=member).role, Membership.Role.MEMBER)
        self.client.post(reverse("demo_switch_role"), {"role": "unbekannt"})
        self.assertEqual(int(self.client.session["_auth_user_id"]), member.pk)

    def test_installation_wide_settings_are_blocked(self):
        self._start()
        for name in ("legal_settings", "display_token_create", "team_invite_create", "terminal_admin"):
            response = self.client.get(reverse(name))
            self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False, msg_prefix=name)

    @override_settings(DEMO_SANDBOX_PER_IP_HOUR=2)
    def test_starts_per_client_are_limited(self):
        self._start(self.client_class())
        self._start(self.client_class())
        response = self.client_class().post(reverse("login"), DEMO)
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertEqual(DemoSandbox.objects.count(), 2)

    @override_settings(DEMO_SANDBOX_MAX_ACTIVE=1)
    def test_active_demos_are_capped(self):
        self._start(self.client_class())
        self.client_class().post(reverse("login"), DEMO)
        self.assertEqual(DemoSandbox.objects.count(), 1)

    def test_purge_command_keeps_running_demos(self):
        _, running = self._start(self.client_class())
        _, stale = self._start(self.client_class())
        DemoSandbox.objects.filter(station=stale).update(created_at=timezone.now() - timedelta(hours=5))
        call_command("purge_demo_sandboxes", verbosity=0)
        self.assertTrue(Station.objects.filter(pk=running.pk).exists())
        self.assertFalse(Station.objects.filter(pk=stale.pk).exists())
        call_command("purge_demo_sandboxes", "--all", verbosity=0)
        self.assertFalse(DemoSandbox.objects.exists())
        connection.check_constraints()

    def test_default_station_never_is_a_demo(self):
        self._start()
        self.assertFalse(DemoSandbox.objects.filter(station=Station.get_default()).exists())

    def test_demo_start_button_on_landing(self):
        landing = self.client.get(reverse("landing"))
        self.assertContains(landing, "Benutzername Demo und Passwort Demo")
        response = self.client.post(reverse("demo_login"))
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        self.assertEqual(DemoSandbox.objects.count(), 1)


class DemoSandboxOffTests(TestCase):
    def test_demo_credentials_are_a_normal_failed_login_without_sandbox(self):
        response = self.client.post(reverse("login"), DEMO)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(DemoSandbox.objects.exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(DEMO_MODE=True, DEMO_SANDBOX=False)
    def test_shared_demo_mode_is_unchanged(self):
        response = self.client.get(reverse("login"))
        self.assertNotContains(response, 'value="Demo"')
