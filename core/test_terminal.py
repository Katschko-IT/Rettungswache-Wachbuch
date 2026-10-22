"""Wachenterminal: Gerätebindung, gemeinsamer Wachen-Code, Alltagsmodus und Handy-Kopplung."""
from __future__ import annotations

import json
from datetime import date, timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import ApiToken, AuditEvent, HandoverEntry, Membership, Station, StationTask
from core.task_board import month_tasks
from core.terminal import COOKIE_NAME, SESSION_LAST_SEEN, code_problem, hash_secret, set_station_code
from core.terminal_models import StationTerminal, StationTerminalCode, TerminalPairing

FINGERPRINT = "ab" * 32
CODE = "4827"


@override_settings(TERMINAL_ENABLED=True, TERMINAL_IDLE_SECONDS=120)
class TerminalTestCase(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="RW Terminal", slug="rw-terminal", waste_calendar_enabled=True)
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
        set_station_code(self.station, CODE, set_by=self.admin)

    def use_terminal(self):
        self.client.cookies[COOKIE_NAME] = self.raw

    def unlock(self, code=CODE):
        return self.client.post(reverse("terminal_home"), data={"code": code})


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

    def test_lock_screen_needs_a_registered_terminal(self):
        self.assertEqual(self.client.get(reverse("terminal_home")).status_code, 403)
        self.use_terminal()
        page = self.client.get(reverse("terminal_home"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "data-lock-screen")
        self.assertContains(page, 'data-pin-pad="terminal-code"')

    def test_terminal_data_returns_lock_screen_payload(self):
        self.use_terminal()
        response = self.client.get(reverse("terminal_data"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("open_handovers", response.json())
        self.assertIn("tasks", response.json())

    def test_lock_screen_shows_photo_of_the_day_with_credit(self):
        self.use_terminal()
        page = self.client.get(reverse("terminal_home"))
        self.assertContains(page, "lock-bg lock-bg-")
        self.assertContains(page, "Wikimedia Commons")

    def test_service_worker_is_blocked_on_terminals(self):
        self.use_terminal()
        self.assertEqual(self.client.get("/service-worker.js").status_code, 404)


class TerminalCodeTests(TerminalTestCase):
    def test_correct_code_opens_everyday_mode(self):
        self.use_terminal()
        response = self.unlock()
        self.assertRedirects(response, reverse("terminal_menu"), fetch_redirect_response=False)
        page = self.client.get(reverse("terminal_menu"))
        self.assertContains(page, "Offene Übergaben")
        self.assertContains(page, "Monatsaufgaben")
        self.assertContains(page, "Müllabfuhr")
        self.assertContains(page, "data-idle-logout")
        self.assertTrue(AuditEvent.objects.filter(action="terminal.unlocked_by_code").exists())

    def test_code_without_terminal_is_useless(self):
        self.assertEqual(self.unlock().status_code, 403)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_wrong_code_and_stepwise_lock(self):
        self.use_terminal()
        for _ in range(5):
            self.assertEqual(self.unlock("9051").status_code, 400)
        self.terminal.refresh_from_db()
        self.assertIsNotNone(self.terminal.locked_until)
        response = self.unlock()
        self.assertContains(response, "Gesperrt bis", status_code=400)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(AuditEvent.objects.filter(action="terminal.code_failed").count(), 5)

    def test_admin_can_lift_the_lock(self):
        StationTerminal.objects.filter(pk=self.terminal.pk).update(
            failed_attempts=5, locked_until=timezone.now() + timedelta(minutes=1)
        )
        self.client.force_login(self.admin)
        self.client.post(reverse("terminal_admin"), data={"action": "unlock", "terminal_id": self.terminal.pk})
        self.terminal.refresh_from_db()
        self.assertIsNone(self.terminal.locked_until)
        self.assertEqual(self.terminal.failed_attempts, 0)

    def test_missing_station_code_is_explained(self):
        StationTerminalCode.objects.all().delete()
        self.use_terminal()
        self.assertContains(self.unlock(), "Noch kein Wachen-Code", status_code=400)

    def test_code_rules(self):
        self.assertEqual(code_problem("4827"), "")
        for weak in ("123", "12345", "abcd", "1111", "1234", "9876", "0123"):
            self.assertNotEqual(code_problem(weak), "", weak)


class TerminalOpenModeTests(TerminalTestCase):
    def setUp(self):
        super().setUp()
        self.use_terminal()
        self.unlock()

    def test_management_and_personal_areas_are_blocked(self):
        for path in (
            "/konto/", "/team/", "/einstellungen/", "/chat/", "/uebersicht/", "/fuhrpark/", "/mpg/",
            "/aufgaben/verwaltung/", "/kalender/abo/", "/terminal/handy/", "/konto/api/",
        ):
            response = self.client.get(path)
            self.assertRedirects(response, reverse("terminal_menu"), fetch_redirect_response=False, msg_prefix=path)

    def test_everyday_pages_are_allowed(self):
        for name in ("handover_list", "handover_create", "calendar", "tasks_today", "tasks_week"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_entries_are_recorded_under_the_terminal_account(self):
        service_user = StationTerminalCode.objects.get(station=self.station).service_user
        self.assertEqual(int(self.client.session["_auth_user_id"]), service_user.pk)
        self.assertEqual(service_user.first_name, "Wachenterminal")
        self.assertFalse(service_user.has_usable_password())

    def test_idle_session_is_locked_again(self):
        session = self.client.session
        session[SESSION_LAST_SEEN] = (timezone.now() - timedelta(seconds=121)).timestamp()
        session.save()
        response = self.client.get(reverse("terminal_menu"))
        self.assertRedirects(response, reverse("terminal_home"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_session_ends_when_terminal_cookie_is_missing(self):
        del self.client.cookies[COOKIE_NAME]
        response = self.client.get(reverse("handover_list"))
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_session_ends_when_terminal_is_revoked(self):
        StationTerminal.objects.filter(pk=self.terminal.pk).update(revoked_at=timezone.now())
        self.client.get(reverse("handover_list"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_lock_button_clears_site_data_but_keeps_terminal(self):
        response = self.client.post(reverse("terminal_logout"))
        self.assertRedirects(response, reverse("terminal_home"), fetch_redirect_response=False)
        self.assertEqual(response["Clear-Site-Data"], '"cache", "storage"')
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.get(reverse("terminal_home")).status_code, 200)

    def test_responses_on_terminal_are_not_cached(self):
        self.assertEqual(self.client.get(reverse("terminal_menu"))["Cache-Control"], "no-store")

    def test_terminal_shows_open_handovers(self):
        HandoverEntry.objects.create(
            station=self.station, category=HandoverEntry.Category.MATERIAL, title="Kühlschrank leer",
            details="bitte auffüllen", priority=HandoverEntry.Priority.URGENT, author=self.user,
        )
        self.assertContains(self.client.get(reverse("terminal_menu")), "Kühlschrank leer")


class TerminalAdminTests(TerminalTestCase):
    def test_admin_registers_terminal_and_sets_code(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("terminal_admin"), data={"action": "create", "label": "Halle 2"})
        self.assertContains(self.client.get(reverse("terminal_admin")), "/terminal/start/")

        response = self.client.post(
            reverse("terminal_admin"), data={"action": "set-code", "code": "1234", "code_repeat": "1234"}, follow=True
        )
        self.assertContains(response, "Zahlenfolge")
        self.client.post(reverse("terminal_admin"), data={"action": "set-code", "code": "7305", "code_repeat": "7305"})
        self.client.logout()
        self.use_terminal()
        self.assertEqual(self.unlock(CODE).status_code, 400)
        self.assertRedirects(self.unlock("7305"), reverse("terminal_menu"), fetch_redirect_response=False)

    def test_generated_code_is_shown_once(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("terminal_admin"), data={"action": "generate-code"})
        first = self.client.get(reverse("terminal_admin"))
        self.assertEqual(code_problem(first.context["new_code"]), "")
        self.assertEqual(self.client.get(reverse("terminal_admin")).context["new_code"], "")

    def test_only_admins_manage_terminals(self):
        lead = User.objects.create_user(username="lead")
        Membership.objects.create(user=lead, station=self.station, role=Membership.Role.SHIFT_LEAD)
        self.client.force_login(lead)
        self.assertEqual(self.client.get(reverse("terminal_admin")).status_code, 403)

    def test_service_account_cannot_be_promoted(self):
        service = StationTerminalCode.objects.get(station=self.station).service_user
        membership = Membership.objects.get(user=service)
        self.client.force_login(self.admin)
        self.client.post(
            reverse("membership_update", args=[membership.pk]), data={"role": "admin", "is_active": "on"}
        )
        membership.refresh_from_db()
        self.assertEqual(membership.role, Membership.Role.MEMBER)

    def test_service_account_is_not_offered_for_phone_pairing(self):
        self.client.force_login(self.admin)
        names = [m.user.first_name for m in self.client.get(reverse("terminal_admin")).context["members"]]
        self.assertIn("Nina", names)
        self.assertNotIn("Wachenterminal", names)

    @override_settings(LOCAL_TLS_CERT_SHA256=FINGERPRINT, SITE_URL="https://10.42.0.1")
    def test_connect_qr_link_carries_certificate_fingerprint(self):
        from core.terminal_views import connect_link

        link = connect_link(RequestFactory().get("/"))
        self.assertTrue(link.startswith("wachbuch://connect?"))
        self.assertIn("url=https%3A%2F%2F10.42.0.1", link)
        self.assertIn(f"pin=sha256%2F{FINGERPRINT}", link)


class TerminalPairingTests(TerminalTestCase):
    def _exchange(self, code):
        # Das Handy ist ein eigenes Gerät ohne Terminal-Cookie.
        phone = self.client_class()
        return phone.post(
            reverse("api_v1_token_pairing"), data=json.dumps({"code": code}), content_type="application/json"
        )

    def _admin_pairs_member(self):
        self.client.force_login(self.admin)
        with mock.patch("core.terminal.secrets.token_urlsafe", return_value="kopplungscode-123"):
            self.client.post(
                reverse("terminal_admin"), data={"action": "pair-member", "membership_id": self.membership.pk}
            )
        self.assertContains(self.client.get(reverse("terminal_admin")), "QR-Code für Nina")
        qr = self.client.get(reverse("terminal_pair_qr"))
        self.assertEqual(qr["Content-Type"], "image/png")
        return "kopplungscode-123"

    def test_admin_shown_qr_signs_the_member_in_once(self):
        code = self._admin_pairs_member()
        self.assertEqual(self._exchange(code).status_code, 200)
        self.assertTrue(ApiToken.objects.filter(user=self.user).exists())
        self.assertEqual(self._exchange(code).status_code, 401)

    def test_expired_pairing_code_is_rejected(self):
        code = self._admin_pairs_member()
        TerminalPairing.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self._exchange(code).status_code, 401)

    def test_own_pairing_from_personal_session(self):
        self.client.force_login(self.user)
        self.client.post(reverse("terminal_pair"))
        self.assertEqual(self.client.get(reverse("terminal_pair_qr")).status_code, 200)
        self.assertEqual(self.client.get(reverse("terminal_pair_qr")).status_code, 404)


class LockScreenBackgroundTests(TestCase):
    def test_at_least_thirty_licensed_backgrounds_exist(self):
        from pathlib import Path

        from django.conf import settings

        from core.lockscreen import backgrounds

        items = backgrounds()
        self.assertGreaterEqual(len(items), 30)
        allowed = ("CC0", "Public domain", "CC BY ", "CC BY-SA ")
        static = Path(settings.BASE_DIR) / "core" / "static" / "core" / "lockscreen"
        css = (static.parent / "lockscreen.css").read_text(encoding="utf-8")
        for number, item in enumerate(items, 1):
            self.assertTrue(item["license"].startswith(allowed), item)
            self.assertTrue(item["artist"] and item["source"].startswith("https://commons.wikimedia.org/"), item)
            self.assertTrue((static / item["file"]).is_file(), item["file"])
            self.assertIn(f".lock-bg-{number:02d} ", css)

    def test_background_changes_daily_and_carries_credit(self):
        from core.lockscreen import background_for

        today, tomorrow = date(2026, 10, 22), date(2026, 10, 23)
        self.assertNotEqual(background_for(today)["css_class"], background_for(tomorrow)["css_class"])
        self.assertEqual(background_for(today), background_for(today))
        self.assertIn("Wikimedia Commons", background_for(today)["credit"])


class MonthTasksTests(TestCase):
    def test_monthly_task_appears_on_its_day(self):
        station = Station.objects.create(name="RW Monat", slug="rw-monat")
        StationTask.objects.create(
            station=station, title="Sauerstoff bestellen", band=StationTask.Band.EXTRA,
            repeat=StationTask.Repeat.MONTHLY, month_day=31,
        )
        items = month_tasks(station, date(2026, 2, 10))
        self.assertEqual(
            [(item["task"].title, item["date"]) for item in items],
            [("Sauerstoff bestellen", date(2026, 2, 28))],
        )
