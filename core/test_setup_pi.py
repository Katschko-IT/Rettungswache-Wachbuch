"""Ersteinrichtung auf dem Raspberry Pi: Einrichtungscode, Terminal-Schritt, Abschlussseite."""
from __future__ import annotations

import io

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import InstallationSetup, Membership, Station
from core.setup_wizard import bootstrap_fingerprint, normalize_bootstrap_token, verify_bootstrap_token
from core.terminal import COOKIE_NAME, hash_secret, set_station_code
from core.terminal_models import StationTerminal, StationTerminalCode
from core.test_argon_remediation import setup_payload

GROUPED = "K7QM-4XWP-HN2R-T9VB-ZC6D-8JFS"


class SetupCodeNormalizationTests(TestCase):
    def test_spaces_hyphens_and_case_do_not_matter(self):
        self.assertEqual(normalize_bootstrap_token(" k7qm 4xwp-hn2r\tT9VB "), "k7qm4xwphn2rt9vb")
        with self.settings(SETUP_BOOTSTRAP_TOKEN=GROUPED):
            self.assertTrue(verify_bootstrap_token("k7qm4xwphn2rt9vbzc6d8jfs"))
            self.assertTrue(verify_bootstrap_token("K7QM 4XWP HN2R T9VB ZC6D 8JFS"))
            self.assertFalse(verify_bootstrap_token("K7QM-4XWP-HN2R-T9VB-ZC6D-8JFX"))
            self.assertFalse(verify_bootstrap_token(" - "))

    @override_settings(SETUP_BOOTSTRAP_TOKEN=GROUPED)
    def test_wizard_accepts_lowercase_entry(self):
        cache.clear()
        response = self.client.post(reverse("setup_wizard"), {"bootstrap_token": "k7qm4xwp hn2r t9vb zc6d 8jfs"})
        self.assertRedirects(response, reverse("setup_wizard"), fetch_redirect_response=False)
        self.assertEqual(self.client.session["setup_bootstrap_hash"], bootstrap_fingerprint(GROUPED))
        self.assertContains(self.client.get(reverse("setup_wizard")), "Admin-Konto")


@override_settings(SETUP_BOOTSTRAP_TOKEN=GROUPED, ALLOWED_HOSTS=["localhost", "10.42.0.1", "testserver"])
class SetupWizardFinishTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.post(reverse("setup_wizard"), {"bootstrap_token": GROUPED})

    def test_finish_shows_next_steps_once(self):
        response = self.client.post(reverse("setup_wizard"), setup_payload())
        self.assertRedirects(response, reverse("setup_done"), fetch_redirect_response=False)
        page = self.client.get(reverse("setup_done"))
        self.assertContains(page, "Rettungswache Teststadt")
        self.assertContains(page, "Besatzung einladen")
        self.assertIn("no-store", page["Cache-Control"])
        self.assertTrue(InstallationSetup.objects.get(pk=1).completed_at)
        self.assertEqual(self.client.get(reverse("setup_wizard")).status_code, 404)

    def test_done_page_needs_fresh_setup(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("setup_done")).status_code, 404)

    def test_reserved_service_username_is_rejected(self):
        response = self.client.post(reverse("setup_wizard"), setup_payload(admin_username="Wachenterminal-1"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "reserviert")
        self.assertFalse(Station.objects.exists())

    def test_without_terminal_feature_no_terminal_fields(self):
        with self.settings(TERMINAL_ENABLED=False):
            response = self.client.get(reverse("setup_wizard"))
        self.assertNotContains(response, 'name="terminal_code"')

    @override_settings(TERMINAL_ENABLED=True)
    def test_terminal_step_sets_code_and_registers_this_device(self):
        response = self.client.post(
            reverse("setup_wizard"),
            setup_payload(terminal_code="2580", register_terminal="on"),
            HTTP_HOST="localhost",
        )
        self.assertRedirects(response, reverse("setup_done"), fetch_redirect_response=False)
        station = Station.objects.get()
        record = StationTerminalCode.objects.get(station=station)
        self.assertTrue(record.service_user.username.startswith("wachenterminal-"))
        raw = response.cookies[COOKIE_NAME].value
        terminal = StationTerminal.objects.get(station=station)
        self.assertEqual(terminal.token_hash, hash_secret(raw))
        self.assertTrue(response.cookies[COOKIE_NAME]["httponly"])
        self.assertEqual(self.client.get(reverse("terminal_home"), HTTP_HOST="localhost").status_code, 200)
        unlock = self.client.post(reverse("terminal_home"), {"code": "2580"}, HTTP_HOST="localhost")
        self.assertRedirects(unlock, reverse("terminal_menu"), fetch_redirect_response=False)

    @override_settings(TERMINAL_ENABLED=True)
    def test_weak_terminal_code_blocks_finish(self):
        response = self.client.post(reverse("setup_wizard"), setup_payload(terminal_code="1234"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Zahlenfolge")
        self.assertFalse(Station.objects.exists())

    @override_settings(TERMINAL_ENABLED=True)
    def test_terminal_checkbox_defaults_to_kiosk_only(self):
        local = self.client.get(reverse("setup_wizard"), HTTP_HOST="localhost")
        self.assertContains(local, 'id="id_register_terminal" checked')
        remote = self.client.get(reverse("setup_wizard"), HTTP_HOST="10.42.0.1")
        self.assertNotContains(remote, 'id="id_register_terminal" checked')
        self.assertContains(remote, 'name="register_terminal"')


@override_settings(TERMINAL_ENABLED=True)
class KioskFirstBootTests(TestCase):
    def test_kiosk_before_setup_opens_wizard(self):
        with self.settings(SETUP_BOOTSTRAP_TOKEN=GROUPED):
            response = self.client.get(reverse("terminal_home"))
            self.assertRedirects(response, reverse("setup_wizard"), fetch_redirect_response=False)
            self.assertContains(self.client.get(reverse("landing")), reverse("setup_wizard"))
            self.assertContains(self.client.get(reverse("login")), "noch nicht eingerichtet")

    def test_unregistered_device_gets_instructions(self):
        response = self.client.get(reverse("terminal_home"))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "register-terminal.sh", status_code=403)
        self.assertNotContains(self.client.get(reverse("landing")), reverse("setup_wizard"))

    def test_admin_registers_this_device(self):
        station = Station.objects.create(name="Wache Pi", slug="wache-pi")
        admin = User.objects.create_user("chef", password="pw-Sicher-2026!")
        Membership.objects.create(user=admin, station=station, role=Membership.Role.ADMIN)
        set_station_code(station, "2580", set_by=admin)
        self.client.force_login(admin)
        response = self.client.post(reverse("terminal_admin"), {"action": "create-here", "label": "Halle"})
        self.assertRedirects(response, reverse("terminal_home"), fetch_redirect_response=False)
        terminal = StationTerminal.objects.get(station=station)
        self.assertEqual(terminal.label, "Halle")
        self.assertEqual(terminal.token_hash, hash_secret(response.cookies[COOKIE_NAME].value))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.get(reverse("terminal_home")).status_code, 200)


@override_settings(ALLOWED_HOSTS=["localhost", "10.42.0.1", "testserver"])
class OnScreenKeyboardTests(TestCase):
    """Bildschirmtastatur nur am Kiosk (localhost) und auf registrierten Terminals."""

    @override_settings(TERMINAL_ENABLED=True)
    def test_kiosk_gets_keyboard(self):
        response = self.client.get(reverse("login"), HTTP_HOST="localhost")
        self.assertContains(response, 'id="osk-root"')
        self.assertContains(response, "core/osk.js")
        self.assertContains(response, "core/osk.css")

    @override_settings(TERMINAL_ENABLED=True)
    def test_phones_and_laptops_keep_their_own_keyboard(self):
        response = self.client.get(reverse("login"), HTTP_HOST="10.42.0.1")
        self.assertNotContains(response, "osk-root")

    @override_settings(TERMINAL_ENABLED=True)
    def test_registered_terminal_gets_keyboard_on_any_address(self):
        station = Station.objects.create(name="Wache OSK", slug="wache-osk")
        admin = User.objects.create_user("osk-chef", password="pw-Sicher-2026!")
        Membership.objects.create(user=admin, station=station, role=Membership.Role.ADMIN)
        raw = "osk-terminal-secret"
        StationTerminal.objects.create(station=station, label="Halle", token_hash=hash_secret(raw), created_by=admin)
        self.client.cookies[COOKIE_NAME] = raw
        self.assertContains(self.client.get(reverse("login"), HTTP_HOST="10.42.0.1"), 'id="osk-root"')

    def test_feature_off_means_no_keyboard(self):
        with self.settings(TERMINAL_ENABLED=False):
            self.assertNotContains(self.client.get(reverse("login"), HTTP_HOST="localhost"), "osk-root")


@override_settings(SETUP_BOOTSTRAP_TOKEN=GROUPED)
class DefaultStationAdoptionTests(TestCase):
    """Docker: migrate legt eine leere Standardwache an; die Einrichtung übernimmt sie."""

    def setUp(self):
        cache.clear()
        self.client.post(reverse("setup_wizard"), {"bootstrap_token": GROUPED})

    def test_wizard_adopts_empty_default_station(self):
        from django.core.management import call_command

        call_command("bootstrap_project", stdout=io.StringIO())
        default = Station.objects.get()
        tasks = default.station_tasks.count()
        self.assertGreater(tasks, 0)
        self.client.post(reverse("setup_wizard"), setup_payload())
        station = Station.objects.get()
        self.assertEqual(station.pk, default.pk)
        self.assertEqual(station.name, "Rettungswache Teststadt")
        self.assertEqual(station.city, "Osnabrück")
        self.assertTrue(Membership.objects.filter(station=station, role=Membership.Role.ADMIN).exists())
        self.assertEqual(station.station_tasks.count(), tasks)

    def test_used_station_is_never_taken_over(self):
        other = Station.objects.create(name="Andere Wache", slug="rettungswache")
        owner = User.objects.create_user("fremd", password="pw-Sicher-2026!")
        Membership.objects.create(user=owner, station=other, role=Membership.Role.ADMIN)
        self.client.post(reverse("setup_wizard"), setup_payload())
        self.assertEqual(Station.objects.count(), 2)
        other.refresh_from_db()
        self.assertEqual(other.name, "Andere Wache")
