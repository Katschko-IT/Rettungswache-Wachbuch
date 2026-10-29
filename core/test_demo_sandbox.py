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
        self.assertContains(other, "Rundgang 1/6")
        # Das Banner führt direkt zum nächsten Schritt, vorausgefüllt.
        self.assertContains(other, f'{reverse("handover_create")}?vorlage=sauerstoff')

    def test_seeded_sample_data_does_not_count(self):
        # Musterdaten enthalten Übergaben und Einzahlungen – trotzdem nur 1 von 6.
        self.assertTrue(HandoverEntry.objects.filter(station=self.station).exists())
        self.assertContains(self.client.get(reverse("dashboard")), "1 von 6 erledigt")

    def test_all_steps_can_be_done_in_the_browser(self):
        """Jeder Schritt hat einen Knopf in der Weboberfläche – auch das Quittieren."""
        form = self.client.get(f'{reverse("handover_create")}?vorlage=sauerstoff')
        self.assertContains(form, "Sauerstoff RTW 83-2 fast leer")
        response = self.client.post(reverse("handover_create"), {
            "category": "material", "priority": "urgent", "title": "Sauerstoff RTW 83-2 fast leer",
            "details": "Flasche 2",
        })
        handover = HandoverEntry.objects.get(station=self.station, title="Sauerstoff RTW 83-2 fast leer")
        detail_url = reverse("handover_detail", args=[handover.pk])
        self.assertRedirects(response, detail_url, fetch_redirect_response=False)
        page = self.client.get(detail_url)
        self.assertContains(page, "Schritt 2 von 6 geschafft")
        # Schritt 3 wechselt die Rolle selbst und landet bei der neuen Übergabe.
        self.assertContains(page, f'<input type="hidden" name="next" value="{detail_url}">')
        switched = self.client.post(reverse("demo_switch_role"), {"role": "mitglied", "next": detail_url})
        self.assertRedirects(switched, detail_url, fetch_redirect_response=False)
        self.assertContains(self.client.get(detail_url), "Gelesen – quittieren")
        self.client.post(detail_url, {"action": "acknowledge"})
        self.client.post(reverse("mpg_routine_check", args=["demo-defi-rtw1"]), {"quick_pass": "1"})
        self.client.post(reverse("defect_create_web"), {
            "title": "Trage quietscht", "priority": "normal", "category": "vehicle",
        })
        self.client.post(reverse("coffee_pay"), {"amount_eur": "5.00", "method": "cash"})
        page = self.client.get(reverse("dashboard"))
        self.assertContains(page, "6 von 6 erledigt")
        self.assertContains(page, "Geschafft!")
        self.assertContains(page, reverse("install_guide"))
        self.assertContains(page, '<input type="hidden" name="role" value="audit">')

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


    def test_per_ip_default_fits_a_group_behind_one_router(self):
        self.assertEqual(self._setting("DEMO_SANDBOX_PER_IP_HOUR", DEMO_SANDBOX_PER_IP_HOUR=""), "30")


@override_settings(**SANDBOX_ON)
class DemoRoleAndTourTests(TestCase):
    """Rollenwechsel, Rundgang und Banner führen ohne Sackgasse durch die Demo."""

    def setUp(self):
        cache.clear()
        self.client.post(reverse("login"), DEMO)
        self.station = Membership.objects.get(user_id=self.client.session["_auth_user_id"]).station

    def test_auditor_lands_on_the_audit_log(self):
        response = self.client.post(reverse("demo_switch_role"), {"role": "audit"})
        self.assertRedirects(response, reverse("audit_log"))
        page = self.client.get(reverse("audit_log"))
        self.assertNotContains(page, "demo-bar-progress")
        self.assertContains(page, "Zurück zum Rundgang")
        # Gesperrte Bereiche führen den Auditor nicht auf die Übersicht (403).
        blocked = self.client.get(reverse("legal_settings"))
        self.assertRedirects(blocked, reverse("audit_log"), fetch_redirect_response=False)
        back = self.client.post(reverse("demo_switch_role"), {"role": "admin", "next": "/uebersicht/#demo-tour"})
        self.assertEqual(back["Location"], "/uebersicht/#demo-tour")

    def test_role_switch_ignores_foreign_next_targets(self):
        response = self.client.post(reverse("demo_switch_role"), {"role": "mitglied", "next": "https://example.org/"})
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        response = self.client.post(reverse("demo_switch_role"), {"role": "admin", "next": reverse("legal_settings")})
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)

    def test_role_switch_keeps_forms_in_other_tabs_valid(self):
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        token = str(client.get(reverse("login")).context["csrf_token"])
        client.post(reverse("login"), {**DEMO, "csrfmiddlewaretoken": token})
        old_tab = str(client.get(reverse("dashboard")).context["csrf_token"])
        other_tab = str(client.get(reverse("handover_list")).context["csrf_token"])
        switched = client.post(reverse("demo_switch_role"), {"role": "mitglied", "csrfmiddlewaretoken": other_tab})
        self.assertEqual(switched.status_code, 302)
        # Abmelden aus dem älteren Tab funktioniert weiter.
        response = client.post(reverse("logout"), {"csrfmiddlewaretoken": old_tab})
        self.assertRedirects(response, reverse("landing") + "?demo=ende", fetch_redirect_response=False)

    def test_stale_form_gets_a_page_with_a_way_back(self):
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        response = client.post(reverse("logout"), {"csrfmiddlewaretoken": "x" * 64},
                               HTTP_REFERER="http://testserver/uebergaben/")
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Diese Seite war veraltet", status_code=403)
        self.assertContains(response, 'href="http://testserver/uebergaben/"', status_code=403)
        self.assertNotContains(response, "CSRF", status_code=403)

    def test_progress_is_cached_and_refreshed_after_a_change(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self.client.get(reverse("more"))
        with CaptureQueriesContext(connection) as ctx:
            page = self.client.get(reverse("more"))
        tour_tables = ("core_handoverack", "core_deviceroutinecheck", "core_defect\"")
        self.assertFalse([q for q in ctx.captured_queries if any(t in q["sql"] for t in tour_tables)])
        self.assertContains(page, "Rundgang 1/6")
        self.client.post(reverse("handover_create"), {
            "category": "station", "priority": "normal", "title": "Neu", "details": "x",
        })
        self.assertContains(self.client.get(reverse("more")), "Rundgang 2/6")

    def test_banner_is_compact_on_phones_and_points_into_the_tour(self):
        page = self.client.get(reverse("dashboard"))
        self.assertContains(page, 'class="demo-bar-short"')
        self.assertContains(page, 'id="demo-tour"')
        self.assertContains(page, 'href="#demo-tour"')
        self.assertContains(page, "Mitglied (Mara)")

    def test_role_labels_are_translatable(self):
        from django.utils.functional import Promise

        self.assertIsInstance(Membership.Role.MEMBER.label, Promise)

    def test_restarting_inside_a_running_demo_reuses_it(self):
        response = self.client.post(reverse("demo_login"))
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        self.assertEqual(DemoSandbox.objects.count(), 1)

    def test_slide_deck_does_not_hide_the_demo_banner(self):
        from pathlib import Path

        page = self.client.get(reverse("vorfuehrung"))
        self.assertContains(page, '<aside class="demo-bar"')
        self.assertContains(page, 'class="demo-deck-bar"')
        css = (Path(__file__).resolve().parent / "static" / "core" / "demo.css").read_text()
        self.assertNotRegex(css, r"\.demo-bar\b")


@override_settings(**SANDBOX_ON)
class DemoBlockedActionsTests(TestCase):
    """In der Demo gesperrte Aktionen erscheinen gar nicht erst als Knopf."""

    def setUp(self):
        cache.clear()
        self.client.post(reverse("login"), DEMO)

    def test_blocked_controls_are_hidden(self):
        for name, blocked in (
            ("display_tokens", "display_token_create"),
            ("station_settings", "legal_settings"),
            ("team_invites", "team_invite_create"),
            ("team", "team_create"),
            ("account_home", "api_tokens_manage"),
            ("more", "api_tokens_manage"),
        ):
            page = self.client.get(reverse(name))
            self.assertEqual(page.status_code, 200, name)
            self.assertNotContains(page, f'"{reverse(blocked)}"', msg_prefix=name)
        self.assertContains(self.client.get(reverse("display_tokens")), reverse("display_home"))

    def test_blocked_area_returns_to_the_previous_page(self):
        response = self.client.get(reverse("display_token_create"), HTTP_REFERER="http://testserver/einstellungen/display/")
        self.assertRedirects(response, reverse("display_tokens"), fetch_redirect_response=False)


@override_settings(**SANDBOX_ON)
class DemoSampleDataTests(TestCase):
    """Musterdaten wie auf einer echten Rettungswache – ohne Testmarker."""

    def setUp(self):
        cache.clear()
        from core.demo_sandbox import create_sandbox

        self.sandbox, self.users = create_sandbox()
        self.station = self.sandbox.station

    def test_no_test_markers_in_a_sandbox(self):
        from django.apps import apps

        for model in apps.get_app_config("core").get_models():
            fields = {field.name for field in model._meta.concrete_fields}
            if "station" not in fields:
                continue
            for name in ("title", "name", "reason", "label", "batch_number", "serial_number", "model_type"):
                if name in fields:
                    values = model.objects.filter(station=self.station).values_list(name, flat=True)
                    for value in values:
                        self.assertNotIn("[Demo]", value, f"{model.__name__}.{name}")
                        self.assertNotIn("DEMO", value, f"{model.__name__}.{name}")
                        self.assertNotIn("(Demo)", value, f"{model.__name__}.{name}")

    def test_times_are_spread_and_appointments_are_in_the_daytime(self):
        from core.models import CalendarEvent

        created = set(HandoverEntry.objects.filter(station=self.station).values_list("created_at", flat=True))
        self.assertGreaterEqual(len(created), 6)
        self.assertTrue(all(value <= timezone.now() for value in created))
        for event in CalendarEvent.objects.filter(station=self.station):
            start = timezone.localtime(event.starts_at)
            self.assertTrue(6 <= start.hour <= 20, f"{event.title} {start}")
            self.assertLess(start.weekday() if "Briefing" not in event.title else 0, 5, event.title)

    def test_device_records_match_their_deadlines(self):
        from core.demo_modules import _months_before
        from core.mpg_models import MaintenanceLog, MedicalDevice

        for device in MedicalDevice.objects.filter(station=self.station, is_anlage_1=True):
            stk = MaintenanceLog.objects.get(device=device, kind=MaintenanceLog.Kind.STK)
            self.assertEqual(stk.performed_at, _months_before(device.next_stk_date, device.stk_interval_months))
            self.assertIsNotNone(device.last_routine_check)

    def test_member_has_the_current_month_open_for_the_tour(self):
        from core import coffee

        member = self.users["demo-mitglied"]
        status = coffee.member_status(self.station, member)
        self.assertEqual(status.open_cents, 500)
        self.assertEqual(coffee.member_status(self.station, self.users["demo-kasse"]).open_cents, 0)

    def test_modules_are_filled_and_chat_stays_empty(self):
        from core.models import ChatMessage, NewsPost, PinboardNote, WikiArticle
        from core.fleet_models import Vehicle
        from core.wachalltag_models import Defect, InventoryItem, StationAsset
        from core.warehouse_models import StockMovement

        for model, minimum in ((NewsPost, 2), (PinboardNote, 2), (WikiArticle, 1), (StationAsset, 5),
                               (InventoryItem, 2), (StockMovement, 5), (Defect, 2), (Vehicle, 5)):
            self.assertGreaterEqual(model.objects.filter(station=self.station).count(), minimum, model.__name__)
        types = set(Vehicle.objects.filter(station=self.station).values_list("vehicle_type", flat=True))
        self.assertEqual(types, {"rtw", "nef", "ktw"})
        self.assertFalse(ChatMessage.objects.filter(station=self.station).exists())

    def test_creation_stays_cheap(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from core.demo_sandbox import create_sandbox

        with CaptureQueriesContext(connection) as ctx:
            create_sandbox()
        self.assertLess(len(ctx.captured_queries), 300)

    def test_defect_history_is_readable(self):
        from core.wachalltag_models import Defect

        client = self.client
        client.force_login(self.users["demo-admin"])
        defect = Defect.objects.filter(station=self.station, status="in_progress").first()
        page = client.get(reverse("defect_detail_web", args=[defect.pk]))
        self.assertContains(page, "Offen → In Bearbeitung")
        self.assertNotContains(page, "in_progress ·")
        self.assertNotContains(page, f"demo-{self.sandbox.token}-")


@override_settings(**SANDBOX_ON)
class DemoPurgeBatchTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_expired_demos_are_purged_together_and_one_failure_does_not_block_the_rest(self):
        from unittest import mock

        from django.db import DatabaseError

        from core import demo_sandbox

        stations = [demo_sandbox.create_sandbox()[0].station_id for _ in range(3)]
        DemoSandbox.objects.update(ended_at=timezone.now())
        real = demo_sandbox.purge_stations
        calls = []

        def flaky(ids):
            calls.append(list(ids))
            if stations[1] in ids:
                raise DatabaseError("simuliert")
            return real(ids)

        with mock.patch.object(demo_sandbox, "purge_stations", side_effect=flaky):
            purged = demo_sandbox.purge_expired()
        self.assertEqual(purged, 2)
        self.assertEqual(calls[0], stations)  # erst alle in einem Durchlauf
        self.assertEqual(list(Station.objects.filter(pk__in=stations).values_list("pk", flat=True)), [stations[1]])
        connection.check_constraints()


class HandoverAcknowledgementTests(TestCase):
    """Übergaben lassen sich im Browser quittieren – nicht vom Wachenterminal."""

    def setUp(self):
        self.station = Station.objects.create(name="Wache Ack", slug="wache-ack")
        self.author = User.objects.create_user("autorin", password="x" * 16, first_name="Ada")
        self.reader = User.objects.create_user("leser", password="x" * 16, first_name="Lea")
        Membership.objects.create(user=self.author, station=self.station, role=Membership.Role.SHIFT_LEAD)
        Membership.objects.create(user=self.reader, station=self.station, role=Membership.Role.MEMBER)
        self.handover = HandoverEntry.objects.create(
            station=self.station, category="material", title="Sauerstoff", details="x", author=self.author,
        )
        self.url = reverse("handover_detail", args=[self.handover.pk])

    def test_acknowledging_twice_keeps_one_receipt_and_one_audit_entry(self):
        from core.wachalltag_models import HandoverAck

        self.client.force_login(self.reader)
        self.assertContains(self.client.get(self.url), "Gelesen – quittieren")
        self.client.post(self.url, {"action": "acknowledge"})
        self.client.post(self.url, {"action": "acknowledge"})
        self.assertEqual(HandoverAck.objects.filter(handover=self.handover, user=self.reader).count(), 1)
        self.assertEqual(AuditEvent.objects.filter(action="handover.acknowledged").count(), 1)
        page = self.client.get(self.url)
        self.assertContains(page, "Lea")
        self.assertContains(page, "bereits quittiert")
        self.assertNotContains(page, "Gelesen – quittieren")

    def test_terminal_service_account_cannot_acknowledge(self):
        from django.core.exceptions import PermissionDenied
        from django.test import RequestFactory

        from core.terminal import set_station_code
        from core.views import handover_detail
        from core.wachalltag_models import HandoverAck

        service = set_station_code(self.station, "4827", set_by=self.author).service_user
        request = RequestFactory().post(self.url, {"action": "acknowledge"})
        request.user = service
        with self.assertRaises(PermissionDenied):
            handover_detail(request, pk=self.handover.pk)
        self.assertFalse(HandoverAck.objects.filter(user=service).exists())
