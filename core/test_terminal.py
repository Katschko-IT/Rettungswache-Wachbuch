"""Wachenterminal: Gerätebindung, PIN-Anmeldung, Sitzungsgrenzen und Handy-Kopplung."""
from __future__ import annotations

import json
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import ApiToken, AuditEvent, Membership, Station
from core.terminal import (
    COOKIE_NAME,
    MAX_PIN_FAILURES,
    SESSION_LAST_SEEN,
    hash_secret,
    pin_problem,
    set_pin,
)
from core.terminal_models import StationTerminal, TerminalPairing, TerminalPin

FINGERPRINT = "ab" * 32


@override_settings(TERMINAL_ENABLED=True, TERMINAL_IDLE_SECONDS=120)
class TerminalTestCase(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="RW Terminal", slug="rw-terminal")
        self.admin = User.objects.create_user(username="chefin", password="x-test-pass-123", first_name="Chefin")
        self.admin_membership = Membership.objects.create(
            user=self.admin, station=self.station, role=Membership.Role.ADMIN
        )
        self.user = User.objects.create_user(username="nfs", password="x-test-pass-123", first_name="Nina")
        self.membership = Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.MEMBER)
        self.raw = "terminal-secret-token-value"
        self.terminal = StationTerminal.objects.create(
            station=self.station, label="Fahrzeughalle", token_hash=hash_secret(self.raw), created_by=self.admin
        )
        set_pin(self.membership, "482915", set_by=self.admin, must_change=False)

    def use_terminal(self):
        self.client.cookies[COOKIE_NAME] = self.raw

    def pin_login(self, pin="482915", membership=None):
        membership = membership or self.membership
        return self.client.post(reverse("terminal_pin_login", args=[membership.pk]), data={"pin": pin})


class TerminalDeviceTests(TerminalTestCase):
    @override_settings(TERMINAL_ENABLED=False)
    def test_disabled_feature_is_not_reachable(self):
        self.use_terminal()
        self.assertEqual(self.client.get(reverse("terminal_home")).status_code, 404)

    def test_start_link_sets_cookie_and_unknown_link_is_rejected(self):
        response = self.client.get(reverse("terminal_start", args=[self.raw]))
        self.assertRedirects(response, reverse("terminal_home"), fetch_redirect_response=False)
        cookie = response.cookies[COOKIE_NAME]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Strict")
        self.assertEqual(self.client.get(reverse("terminal_start", args=["falsch"])).status_code, 403)

    def test_pages_need_a_registered_terminal(self):
        self.assertEqual(self.client.get(reverse("terminal_home")).status_code, 403)
        self.assertEqual(self.client.get(reverse("terminal_people")).status_code, 403)
        self.use_terminal()
        self.assertEqual(self.client.get(reverse("terminal_home")).status_code, 200)
        self.assertContains(self.client.get(reverse("terminal_people")), "Nina")

    def test_terminal_data_returns_display_payload(self):
        self.use_terminal()
        response = self.client.get(reverse("terminal_data"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("layout_config", response.json())

    def test_service_worker_is_blocked_on_terminals(self):
        self.use_terminal()
        self.assertEqual(self.client.get("/service-worker.js").status_code, 404)


class TerminalPinLoginTests(TerminalTestCase):
    def test_correct_pin_logs_in_and_opens_menu(self):
        self.use_terminal()
        response = self.pin_login()
        self.assertRedirects(response, reverse("terminal_menu"), fetch_redirect_response=False)
        menu = self.client.get(reverse("terminal_menu"))
        self.assertContains(menu, "Hallo Nina")
        self.assertContains(menu, "data-idle-logout")
        self.assertTrue(AuditEvent.objects.filter(action="terminal.login", actor=self.user).exists())

    def test_pin_without_terminal_is_useless(self):
        response = self.pin_login()
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_issued_start_pin_must_be_changed_first(self):
        set_pin(self.membership, "907153", set_by=self.admin, must_change=True)
        self.use_terminal()
        response = self.pin_login("907153")
        self.assertRedirects(response, reverse("terminal_pin_change"), fetch_redirect_response=False)
        response = self.client.post(
            reverse("terminal_pin_change"), data={"new_pin": "123456", "new_pin_repeat": "123456"}
        )
        self.assertEqual(response.status_code, 400)
        response = self.client.post(
            reverse("terminal_pin_change"), data={"new_pin": "730518", "new_pin_repeat": "730518"}
        )
        self.assertRedirects(response, reverse("terminal_menu"), fetch_redirect_response=False)
        record = TerminalPin.objects.get(membership=self.membership)
        self.assertFalse(record.must_change)

    def test_repeated_failures_lock_the_pin(self):
        self.use_terminal()
        for _ in range(MAX_PIN_FAILURES):
            self.assertEqual(self.pin_login("000001").status_code, 400)
        record = TerminalPin.objects.get(membership=self.membership)
        self.assertIsNotNone(record.locked_until)
        response = self.pin_login()
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_people_list_only_shows_members_with_pin(self):
        other = User.objects.create_user(username="ohnepin", first_name="Otto")
        Membership.objects.create(user=other, station=self.station)
        self.use_terminal()
        response = self.client.get(reverse("terminal_people"))
        self.assertContains(response, "Nina")
        self.assertNotContains(response, "Otto")

    def test_inactive_user_cannot_log_in(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.use_terminal()
        self.assertEqual(self.pin_login().status_code, 404)


class TerminalSessionLimitTests(TerminalTestCase):
    def setUp(self):
        super().setUp()
        self.use_terminal()
        self.pin_login()

    def test_account_and_team_pages_are_blocked(self):
        for path in ("/konto/", "/team/", "/einstellungen/", "/chat/", "/konto/api/", "/kalender/abo/", "/benachrichtigungen/"):
            response = self.client.get(path)
            self.assertRedirects(response, reverse("terminal_menu"), fetch_redirect_response=False, msg_prefix=path)

    def test_everyday_pages_are_allowed(self):
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("handover_list")).status_code, 200)

    def test_idle_session_is_ended(self):
        session = self.client.session
        session[SESSION_LAST_SEEN] = (timezone.now() - timedelta(seconds=121)).timestamp()
        session.save()
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, reverse("terminal_home"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_session_ends_when_terminal_cookie_is_missing(self):
        del self.client.cookies[COOKIE_NAME]
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_session_ends_when_terminal_is_revoked(self):
        StationTerminal.objects.filter(pk=self.terminal.pk).update(revoked_at=timezone.now())
        self.client.get(reverse("dashboard"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_clears_site_data_but_keeps_terminal(self):
        response = self.client.post(reverse("terminal_logout"))
        self.assertRedirects(response, reverse("terminal_home"), fetch_redirect_response=False)
        self.assertEqual(response["Clear-Site-Data"], '"cache", "storage"')
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.get(reverse("terminal_home")).status_code, 200)

    def test_responses_on_terminal_are_not_cached(self):
        self.assertEqual(self.client.get(reverse("dashboard"))["Cache-Control"], "no-store")


class TerminalPinRulesTests(TestCase):
    def test_pin_rules(self):
        self.assertEqual(pin_problem("730518"), "")
        for weak in ("12345", "1234567", "abcdef", "111111", "123456", "987654"):
            self.assertNotEqual(pin_problem(weak), "", weak)


class TerminalAdminTests(TerminalTestCase):
    def test_admin_registers_terminal_and_issues_pin(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("terminal_admin"), data={"action": "create", "label": "Halle 2"})
        self.assertRedirects(response, reverse("terminal_admin"), fetch_redirect_response=False)
        page = self.client.get(reverse("terminal_admin"))
        self.assertContains(page, "/terminal/start/")
        self.client.post(reverse("terminal_pin_issue", args=[self.membership.pk]))
        page = self.client.get(reverse("terminal_admin"))
        pin = page.context["new_pin"]["pin"]
        self.assertEqual(pin_problem(pin), "")
        self.assertTrue(TerminalPin.objects.get(membership=self.membership).must_change)

    def test_shift_lead_cannot_set_admin_pin(self):
        lead = User.objects.create_user(username="lead")
        Membership.objects.create(user=lead, station=self.station, role=Membership.Role.SHIFT_LEAD)
        self.client.force_login(lead)
        self.client.post(reverse("terminal_pin_issue", args=[self.admin_membership.pk]))
        self.assertFalse(TerminalPin.objects.filter(membership=self.admin_membership).exists())

    def test_member_cannot_open_admin_page(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("terminal_admin")).status_code, 403)

    @override_settings(LOCAL_TLS_CERT_SHA256=FINGERPRINT, SITE_URL="https://10.42.0.1")
    def test_connect_qr_link_carries_certificate_fingerprint(self):
        from django.test import RequestFactory

        from core.terminal_views import connect_link

        link = connect_link(RequestFactory().get("/"))
        self.assertTrue(link.startswith("wachbuch://connect?"))
        self.assertIn("url=https%3A%2F%2F10.42.0.1", link)
        self.assertIn(f"pin=sha256%2F{FINGERPRINT}", link)


class TerminalPairingTests(TerminalTestCase):
    def _pair_code(self):
        self.use_terminal()
        self.pin_login()
        with mock.patch("core.terminal.secrets.token_urlsafe", return_value="kopplungscode-123"):
            self.client.post(reverse("terminal_pair"))
        qr = self.client.get(reverse("terminal_pair_qr"))
        self.assertEqual(qr.status_code, 200)
        self.assertEqual(qr["Content-Type"], "image/png")
        return "kopplungscode-123"

    def _exchange(self, code):
        # Das Handy ist ein eigenes Gerät ohne Terminal-Cookie.
        phone = self.client_class()
        return phone.post(
            reverse("api_v1_token_pairing"), data=json.dumps({"code": code}), content_type="application/json"
        )

    def test_pairing_code_yields_token_once(self):
        code = self._pair_code()
        response = self._exchange(code)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["token"])
        self.assertTrue(ApiToken.objects.filter(user=self.user).exists())
        self.assertEqual(self._exchange(code).status_code, 401)

    def test_expired_pairing_code_is_rejected(self):
        code = self._pair_code()
        TerminalPairing.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self._exchange(code).status_code, 401)

    def test_qr_is_shown_only_once(self):
        self._pair_code()
        self.assertEqual(self.client.get(reverse("terminal_pair_qr")).status_code, 404)
