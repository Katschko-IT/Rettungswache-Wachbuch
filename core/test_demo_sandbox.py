"""Öffentliche Demo: eigene Demo-Wache je Besuch, Löschung beim Abmelden."""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import SimpleTestCase, TestCase, override_settings
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


@override_settings(**SANDBOX_ON)
class DemoTourTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.post(reverse("login"), DEMO)
        self.user = User.objects.get(pk=self.client.session["_auth_user_id"])
        self.station = Membership.objects.get(user=self.user).station

    def test_tour_starts_with_overview_done_and_points_to_next_step(self):
        page = self.client.get(reverse("dashboard"))
        self.assertContains(page, "Dein erster Schichtwechsel")
        self.assertContains(page, "1 von 6 erledigt")
        self.assertContains(page, reverse("handover_create"))
        self.assertNotContains(page, "Geschafft!")
        other = self.client.get(reverse("handover_list"))
        self.assertNotContains(other, "Dein erster Schichtwechsel")
        self.assertContains(other, "Rundgang: 1 von 6")

    def test_seeded_sample_data_does_not_count(self):
        # Musterdaten enthalten Übergaben und Einzahlungen – trotzdem nur 1 von 6.
        self.assertTrue(HandoverEntry.objects.filter(station=self.station).exists())
        self.assertContains(self.client.get(reverse("dashboard")), "1 von 6 erledigt")

    def test_all_steps_done_shows_installation_call_to_action(self):
        from core.mpg_models import DeviceRoutineCheck, MedicalDevice
        from core.wachalltag_models import Defect, HandoverAck

        handover = HandoverEntry.objects.create(
            station=self.station, category="material", priority="urgent",
            title="Sauerstoff RTW 2 fast leer", details="Flasche 2", author=self.user,
        )
        HandoverAck.objects.create(station=self.station, handover=handover, user=self.user)
        device = MedicalDevice.objects.filter(station=self.station).first()
        DeviceRoutineCheck.objects.create(station=self.station, device=device, performed_by=self.user)
        Defect.objects.create(station=self.station, title="Trage quietscht", created_by=self.user)
        CoffeeEntry.objects.create(
            station=self.station, member=self.user, amount_cents=500, reason="Oktober",
            kind=CoffeeEntry.Kind.PAYMENT, method="cash", created_by=self.user,
        )
        page = self.client.get(reverse("dashboard"))
        self.assertContains(page, "6 von 6 erledigt")
        self.assertContains(page, "Geschafft!")
        self.assertContains(page, reverse("install_guide"))

    def test_logout_notice_offers_installation_and_new_demo(self):
        response = self.client.post(reverse("logout"))
        landing = self.client.get(response["Location"])
        self.assertContains(landing, reverse("install_guide"))
        self.assertContains(landing, "Neue Demo starten")


class InstallGuideTests(TestCase):
    def test_public_install_guide(self):
        page = self.client.get(reverse("install_guide"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "install.sh")
        self.assertContains(page, "In der Wache (Insellösung)")
        self.assertContains(page, "wachbuch setup-code")
        landing = self.client.get(reverse("landing"))
        self.assertContains(landing, reverse("install_guide"))

    def test_no_tour_for_regular_users(self):
        station = Station.objects.create(name="Echte Wache", slug="echt")
        user = User.objects.create_user("echt", password="x" * 16)
        Membership.objects.create(user=user, station=station, role=Membership.Role.ADMIN)
        self.client.force_login(user)
        page = self.client.get(reverse("dashboard"))
        self.assertNotContains(page, "Dein erster Schichtwechsel")
        self.assertNotContains(page, "demo-bar")


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


@override_settings(DEMO_MODE=True, DEMO_SANDBOX=True, MFA_REQUIRED=True)
class DemoSandboxMfaTests(TestCase):
    """Öffentliche Instanz: 2FA-Pflicht für echte Konten, nicht für Demo-Besuche."""

    def setUp(self):
        cache.clear()

    def test_demo_visit_is_not_forced_into_mfa_setup(self):
        response = self.client.post(reverse("login"), DEMO)
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_real_account_without_second_factor_must_set_it_up(self):
        station = Station.get_default()
        user = User.objects.create_user("betreiber", password="ein-langes-Passwort-42")
        Membership.objects.create(user=user, station=station, role=Membership.Role.ADMIN)
        self.client.force_login(user)
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("mfa_setup"),
                             fetch_redirect_response=False)


@override_settings(**SANDBOX_ON)
class DemoSandboxBoundaryTests(TestCase):
    """Ein Demo-Besuch erreicht keine Konten der Installation und füllt die Datenbank nicht."""

    def setUp(self):
        cache.clear()

    def _start(self, client=None, **extra):
        client = client or self.client
        response = client.post(reverse("login"), DEMO, **extra)
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        user = User.objects.get(pk=client.session["_auth_user_id"])
        return user, Membership.objects.get(user=user).station

    def test_accounts_without_membership_stay_out_of_reach(self):
        from core.models import TotpDevice

        root = User.objects.create_superuser("root", "root@example.org", "ein-langes-Passwort-42")
        TotpDevice.objects.create(user=root, secret="JBSWY3DPEHPK3PXP", is_confirmed=True)
        former = User.objects.create_user("ehemalig", password="ein-langes-Passwort-42", first_name="Erika")
        _, station = self._start()

        self.assertRedirects(self.client.get(reverse("team_create")), reverse("dashboard"))
        self.client.post(reverse("team_create"), {"user": root.pk, "role": Membership.Role.ADMIN})
        self.assertFalse(Membership.objects.filter(user=root).exists())
        self.assertNotContains(self.client.get(reverse("team")), "Erika")

        # Selbst wenn ein altes Konto in die Demo-Wache geriete: Ende der Demo
        # sperrt oder löscht es nicht.
        Membership.objects.create(user=former, station=station, role=Membership.Role.MEMBER)
        self.client.post(reverse("logout"))
        self.assertFalse(Station.objects.filter(pk=station.pk).exists())
        former.refresh_from_db()
        self.assertTrue(former.is_active)
        self.assertTrue(User.objects.filter(pk=root.pk, is_active=True).exists())
        self.assertTrue(TotpDevice.objects.filter(user=root).exists())

    def test_member_created_in_the_demo_is_deleted_with_it(self):
        self._start()
        response = self.client.post(reverse("team_user_create"), {
            "username": "neu-im-team", "first_name": "Neu", "password1": "ein-langes-Passwort-42",
            "password2": "ein-langes-Passwort-42", "role": Membership.Role.MEMBER,
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="neu-im-team").exists())
        self.client.post(reverse("logout"))
        self.assertFalse(User.objects.filter(username="neu-im-team").exists())

    def test_login_records_with_ip_addresses_are_deleted(self):
        from axes.models import AccessLog

        user, _ = self._start()
        self.assertTrue(AccessLog.objects.filter(username=user.username).exists())
        self.client.post(reverse("logout"))
        self.assertFalse(AccessLog.objects.filter(username__startswith="demo-").exists())

    def test_app_access_cannot_be_created_in_the_demo(self):
        from core.models import ApiToken

        self._start()
        self.client.post(reverse("api_tokens_manage"), {"action": "create", "label": "x"})
        self.assertEqual(ApiToken.objects.count(), 0)
        self.assertRedirects(self.client.get(reverse("mobile_setup_qr")), reverse("dashboard"))

    @override_settings(DEMO_SANDBOX_MAX_WRITES=2)
    def test_write_budget_per_visit(self):
        _, station = self._start()
        for title in ("eins", "zwei", "drei"):
            self.client.post(reverse("handover_create"), {
                "category": "station", "title": title, "details": "x", "priority": "normal",
            }, HTTP_REFERER="http://testserver/uebergaben/")
        page = self.client.get(reverse("handover_list"))
        self.assertContains(page, "Limit an Änderungen")
        self.assertFalse(HandoverEntry.objects.filter(station=station, title="drei").exists())
        # Abmelden geht immer.
        self.client.post(reverse("logout"))
        self.assertFalse(Station.objects.filter(pk=station.pk).exists())

    def _png(self):
        import io

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (8, 8), "red").save(buffer, format="PNG")
        return SimpleUploadedFile("a.png", buffer.getvalue(), content_type="image/png")

    def _handover_with_file(self, title):
        return self.client.post(reverse("handover_create"), {
            "category": "station", "title": title, "details": "x", "priority": "normal",
            "attachments": self._png(),
        })

    def test_upload_within_quota_works(self):
        _, station = self._start()
        self._handover_with_file("Mit Datei")
        self.assertTrue(HandoverEntry.objects.filter(station=station, title="Mit Datei").exists())

    @override_settings(DEMO_SANDBOX_MAX_UPLOAD_MB=0)
    def test_upload_quota_per_visit(self):
        _, station = self._start()
        self._handover_with_file("Mit Datei")
        self.assertFalse(HandoverEntry.objects.filter(station=station, title="Mit Datei").exists())

    @override_settings(TRUSTED_PROXY=True, DEMO_SANDBOX_PER_IP_HOUR=2)
    def test_ipv6_starts_are_counted_per_64_network(self):
        for suffix in ("1", "2", "3"):
            self.client_class().post(reverse("login"), DEMO, HTTP_X_FORWARDED_FOR=f"2001:db8:1:2::{suffix}")
        self.assertEqual(DemoSandbox.objects.count(), 2)
        self.client_class().post(reverse("login"), DEMO, HTTP_X_FORWARDED_FOR="2001:db8:1:3::1")
        self.assertEqual(DemoSandbox.objects.count(), 3)


class AdminLoginTests(TestCase):
    """Der Django-Admin nutzt die normale Anmeldung mit zweitem Faktor."""

    def test_admin_login_page_redirects_to_app_login(self):
        response = self.client.get("/django-admin/login/")
        self.assertRedirects(response, f"{reverse('login')}?next=/django-admin/", fetch_redirect_response=False)

    def test_password_alone_does_not_open_the_admin(self):
        from core.models import TotpDevice

        root = User.objects.create_superuser("root", "root@example.org", "ein-langes-Passwort-42")
        TotpDevice.objects.create(user=root, secret="JBSWY3DPEHPK3PXP", is_confirmed=True)
        self.client.post("/django-admin/login/", {"username": "root", "password": "ein-langes-Passwort-42"})
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotEqual(self.client.get("/django-admin/auth/user/").status_code, 200)

    def test_logged_in_staff_reaches_the_admin(self):
        root = User.objects.create_superuser("root", "root@example.org", "ein-langes-Passwort-42")
        self.client.force_login(root)
        self.assertEqual(self.client.get("/django-admin/").status_code, 200)
        self.assertRedirects(self.client.get("/django-admin/login/"), "/django-admin/")

    def test_logged_in_non_staff_gets_forbidden_not_a_loop(self):
        user = User.objects.create_user("mitglied", password="ein-langes-Passwort-42")
        self.client.force_login(user)
        response = self.client.get("/django-admin/", follow=True)
        self.assertEqual(response.status_code, 403)


class DemoSettingsTests(SimpleTestCase):
    """MFA_REQUIRED bleibt in der öffentlichen Demo für echte Konten erhalten."""

    def _setting(self, name, **env):
        import os
        import subprocess
        import sys
        from pathlib import Path

        environment = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings", **env}
        result = subprocess.run(
            [sys.executable, "-c", f"from django.conf import settings; print(settings.{name})"],
            capture_output=True, text=True, env=environment, check=True,
            cwd=Path(__file__).resolve().parents[1],
        )
        return result.stdout.strip()

    def test_public_demo_keeps_mfa_required(self):
        self.assertEqual(self._setting("MFA_REQUIRED", DEMO_MODE="true", DEMO_SANDBOX="true", MFA_REQUIRED="true"), "True")

    def test_shared_demo_switches_mfa_off(self):
        self.assertEqual(self._setting("MFA_REQUIRED", DEMO_MODE="true", DEMO_SANDBOX="false", MFA_REQUIRED="true"), "False")
