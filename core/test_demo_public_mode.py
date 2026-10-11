"""Härtung der öffentlichen Wachbuch-Demo (``DEMO_PUBLIC_MODE``).

Prüft, dass die namensbasierte Server-Guard-Middleware Produktiv-/Verwaltungs-
Operationen für Besucher sperrt, während die operativen Kernabläufe interaktiv
bleiben und der Normalbetrieb unverändert ist. Zusätzlich wird der dokumentierte
Zugang der öffentlichen Demo (Login-Formular, ``Demo``/``Demo``) gegen den
passwortlosen Ein-Klick-Einstieg abgesichert.
"""

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from .demo import (
    DEMO_MARKER,
    DEMO_PUBLIC_PASSWORD,
    DEMO_PUBLIC_USERNAME,
    demo_protected_usernames,
    load_demo_data,
)
from .models import (
    CalendarEvent,
    ChatMessage,
    Checklist,
    CoffeeEntry,
    HandoverEntry,
    Membership,
    StationTask,
    StationTaskCompletion,
)
from .wachalltag_models import (
    AssetEvent,
    ChecklistSchedule,
    Defect,
    DefectEvent,
    InventoryEvent,
    InventoryItem,
    StationAsset,
)

PASSWORD = "Demo-Passwort-12345"

PUBLIC_DEMO = override_settings(DEMO_PUBLIC_MODE=True)
NORMAL_DEMO = override_settings(DEMO_PUBLIC_MODE=False, DEMO_MODE=True)


class PublicDemoModeHardeningTests(TestCase):
    def setUp(self):
        load_demo_data(force=True)
        self.station = Membership.objects.get(
            user__username="demo-admin", is_active=True
        ).station
        self.membership = Membership.objects.get(
            user__username="demo-admin", is_active=True
        )

    def _login_demo_admin(self):
        """One-click demo entry: still available outside ``DEMO_PUBLIC_MODE``."""
        return self.client.post(reverse("demo_login"))

    def _login_public(self):
        """Public demo: seed the Demo account under the active override, then
        authenticate through the normal login form with the documented
        credentials (``Demo``/``Demo``)."""
        load_demo_data(force=True)
        return self.client.post(
            reverse("login"),
            {"username": DEMO_PUBLIC_USERNAME, "password": DEMO_PUBLIC_PASSWORD},
        )

    # -- Sichtbarkeit der Demo ------------------------------------------------

    @PUBLIC_DEMO
    def test_public_demo_banner_is_visible_on_landing(self):
        response = self.client.get(reverse("landing"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Öffentliche Demo")
        self.assertContains(response, "fiktive Musterdaten")

    # -- Zugang der öffentlichen Demo (Login-Formular, Demo/Demo) -------------

    @PUBLIC_DEMO
    def test_public_demo_login_form_accepts_demo_credentials(self):
        load_demo_data(force=True)
        response = self.client.post(
            reverse("login"),
            {"username": DEMO_PUBLIC_USERNAME, "password": DEMO_PUBLIC_PASSWORD},
        )
        # Successful form login redirects to the configured LOGIN_REDIRECT_URL
        # (the landing page, which then forwards members to the dashboard).
        self.assertRedirects(
            response, reverse("landing"), fetch_redirect_response=False
        )
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        self.assertEqual(response.wsgi_request.user.username, DEMO_PUBLIC_USERNAME)

    @PUBLIC_DEMO
    def test_public_demo_login_rejects_wrong_password(self):
        load_demo_data(force=True)
        response = self.client.post(
            reverse("login"),
            {"username": DEMO_PUBLIC_USERNAME, "password": "falsch-falsch"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    @PUBLIC_DEMO
    def test_public_demo_login_is_case_sensitive(self):
        load_demo_data(force=True)
        # Falsche Schreibweise des Benutzernamens darf nicht anmelden.
        response = self.client.post(
            reverse("login"),
            {"username": "demo", "password": DEMO_PUBLIC_PASSWORD},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    @PUBLIC_DEMO
    def test_public_demo_has_no_passwordless_entry(self):
        load_demo_data(force=True)
        response = self.client.post(reverse("demo_login"))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    @PUBLIC_DEMO
    def test_public_demo_account_seeded_with_documented_credentials(self):
        load_demo_data(force=True)
        user = User.objects.get(username=DEMO_PUBLIC_USERNAME)
        self.assertTrue(user.check_password(DEMO_PUBLIC_PASSWORD))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(
            Membership.objects.filter(
                user=user, is_active=True, role=Membership.Role.ADMIN
            ).exists()
        )

    @NORMAL_DEMO
    def test_demo_account_absent_outside_public_mode(self):
        self.assertFalse(
            User.objects.filter(username=DEMO_PUBLIC_USERNAME).exists()
        )

    @PUBLIC_DEMO
    def test_login_and_landing_show_public_demo_hint(self):
        login_page = self.client.get(reverse("login"))
        self.assertEqual(login_page.status_code, 200)
        self.assertContains(login_page, "Öffentliche Demo")
        self.assertContains(login_page, DEMO_PUBLIC_USERNAME)
        landing = self.client.get(reverse("landing"))
        self.assertContains(landing, DEMO_PUBLIC_USERNAME)
        self.assertContains(landing, "Anmeldeformular")
        # Kein passwortloser Ein-Klick-Einstieg auf der öffentlichen Startseite.
        self.assertNotContains(landing, reverse("demo_login"))

    # -- Sperrliste (bestehende URLs) -----------------------------------------

    @PUBLIC_DEMO
    def test_forbidden_operations_return_404_for_visitor(self):
        self._login_public()
        targets = {
            "register": reverse("register"),
            "team_user_create": reverse("team_user_create"),
            "team_create": reverse("team_create"),
            "membership_update": reverse("membership_update", args=[self.membership.pk]),
            "registration_reject": reverse("registration_reject", args=[self.membership.pk]),
            "station_settings": reverse("station_settings"),
            "mfa_setup": reverse("mfa_setup"),
            "mfa_disable": reverse("mfa_disable"),
            "passkey_register_options": reverse("passkey_register_options"),
            "passkey_register_verify": reverse("passkey_register_verify"),
            "passkey_delete": reverse("passkey_delete", args=[1]),
            "api_tokens_manage": reverse("api_tokens_manage"),
            "push_settings": reverse("push_settings"),
            "calendar_feed_manage": reverse("calendar_feed_manage"),
            "api_v1_token": reverse("api_v1_token"),
            "api_v1_anmeldung": reverse("api_v1_anmeldung"),
            "demo_login": reverse("demo_login"),
            "django_admin": reverse("admin:index"),
        }
        for name, url in targets.items():
            with self.subTest(target=name):
                self.assertEqual(self.client.get(url).status_code, 404)

    @PUBLIC_DEMO
    def test_api_token_creation_is_blocked(self):
        self._login_public()
        response = self.client.post(
            reverse("api_v1_token"),
            data={"username": "demo-admin", "password": PASSWORD},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    @PUBLIC_DEMO
    def test_demo_account_cannot_be_deactivated_or_re_roled(self):
        self._login_public()
        before = Membership.objects.get(user__username="demo-schicht", is_active=True)
        response = self.client.post(
            reverse("membership_update", args=[before.pk]),
            data={"role": Membership.Role.MEMBER, "is_active": ""},
        )
        self.assertEqual(response.status_code, 404)
        before.refresh_from_db()
        self.assertTrue(before.is_active)
        self.assertEqual(before.role, Membership.Role.SHIFT_LEAD)
        self.assertTrue(User.objects.get(username="demo-schicht").is_active)

    @PUBLIC_DEMO
    def test_demo_account_cannot_change_its_password(self):
        self._login_public()
        before = User.objects.get(username="demo-admin").password
        response = self.client.post(
            reverse("account_home"),
            data={
                "action": "password",
                "password-old_password": PASSWORD,
                "password-new_password1": "Brand-New-Pass-98765",
                "password-new_password2": "Brand-New-Pass-98765",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(User.objects.get(username="demo-admin").password, before)

    # -- Kernabläufe bleiben interaktiv ---------------------------------------

    @PUBLIC_DEMO
    def test_core_operational_flows_stay_reachable(self):
        self._login_public()
        allowed = [
            "dashboard",
            "handover_list",
            "handover_create",
            "calendar",
            "calendar_create",
            "tasks_today",
            "task_create",
            "defects_web",
            "defect_create_web",
            "assets_inventory_web",
            "checklists",
            "checklist_schedules_web",
            "coffee",
            "coffee_create",
            "account_home",
        ]
        for name in allowed:
            with self.subTest(route=name):
                status = self.client.get(reverse(name)).status_code
                self.assertLess(status, 400)

    # -- Normalbetrieb nicht geschwächt ---------------------------------------

    @NORMAL_DEMO
    def test_normal_mode_endpoints_are_not_blocked(self):
        self._login_demo_admin()
        for name in [
            "station_settings",
            "api_tokens_manage",
            "calendar_feed_manage",
        ]:
            with self.subTest(route=name):
                self.assertNotEqual(self.client.get(reverse(name)).status_code, 404)
        self.assertNotEqual(
            self.client.get(
                reverse("membership_update", args=[self.membership.pk])
            ).status_code,
            404,
        )

    @NORMAL_DEMO
    def test_password_change_allowed_outside_public_demo(self):
        self._login_demo_admin()
        response = self.client.post(
            reverse("account_home"),
            data={
                "action": "password",
                "password-old_password": PASSWORD,
                "password-new_password1": "Brand-New-Pass-98765",
                "password-new_password2": "Brand-New-Pass-98765",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            User.objects.get(username="demo-admin").check_password("Brand-New-Pass-98765")
        )

    # -- Fiktive operative Demo-Daten -----------------------------------------

    def test_core_modules_are_seeded_with_fictional_data(self):
        self.assertTrue(
            HandoverEntry.objects.filter(
                station=self.station, title__startswith=DEMO_MARKER
            ).exists()
        )
        self.assertTrue(
            CalendarEvent.objects.filter(
                station=self.station, title__startswith=DEMO_MARKER
            ).exists()
        )
        self.assertTrue(
            Checklist.objects.filter(
                station=self.station, title__startswith=DEMO_MARKER
            ).exists()
        )
        self.assertTrue(
            CoffeeEntry.objects.filter(
                station=self.station, reason__startswith=DEMO_MARKER
            ).exists()
        )
        self.assertTrue(
            ChatMessage.objects.filter(
                station=self.station, body__startswith=DEMO_MARKER
            ).exists()
        )
        # Tagesaufgaben: Standardboard aktiv, ein Demo-Abschluss markiert.
        self.assertTrue(
            StationTask.objects.filter(station=self.station, is_active=True).exists()
        )
        self.assertTrue(
            StationTaskCompletion.objects.filter(
                station=self.station, note=DEMO_MARKER
            ).exists()
        )

    def test_operational_modules_are_seeded_with_fictional_data(self):
        self.assertTrue(
            Defect.objects.filter(station=self.station, title__startswith=DEMO_MARKER).exists()
        )
        self.assertTrue(
            StationAsset.objects.filter(
                station=self.station, label__startswith=DEMO_MARKER
            ).exists()
        )
        self.assertTrue(
            InventoryItem.objects.filter(
                station=self.station, label__startswith=DEMO_MARKER
            ).exists()
        )
        self.assertTrue(
            ChecklistSchedule.objects.filter(
                station=self.station, checklist__title__startswith=DEMO_MARKER
            ).exists()
        )
        # Append-only Ereignisse wurden wie im Betrieb erzeugt.
        self.assertTrue(
            DefectEvent.objects.filter(station=self.station).exists()
        )
        self.assertTrue(AssetEvent.objects.filter(station=self.station).exists())
        self.assertTrue(InventoryEvent.objects.filter(station=self.station).exists())

    def test_reset_rebuilds_operational_demo_data(self):
        def counts():
            return {
                "defects": Defect.objects.filter(
                    station=self.station, title__startswith=DEMO_MARKER
                ).count(),
                "assets": StationAsset.objects.filter(
                    station=self.station, label__startswith=DEMO_MARKER
                ).count(),
                "inventory": InventoryItem.objects.filter(
                    station=self.station, label__startswith=DEMO_MARKER
                ).count(),
                "schedules": ChecklistSchedule.objects.filter(
                    station=self.station, checklist__title__startswith=DEMO_MARKER
                ).count(),
            }

        before = counts()
        for key, value in before.items():
            self.assertGreater(value, 0, key)
        # Reset räumt auch die append-only Ereignisse per Roh-SQL ab.
        load_demo_data(reset=True)
        self.assertEqual(counts(), before)

    def test_demo_protected_usernames_match_seeded_accounts(self):
        self.assertEqual(
            demo_protected_usernames(),
            {"demo-admin", "demo-schicht", "demo-kasse", "demo-mitglied", "demo-audit"},
        )
        self.assertEqual(
            User.objects.filter(
                username__in=demo_protected_usernames(), is_active=True
            ).count(),
            5,
        )
