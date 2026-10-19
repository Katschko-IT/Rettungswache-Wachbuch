"""Soll-Regressionstests für die Argon-Setup-/Einladungsbefunde S1-S7.

Diese Tests beschreiben das sichere Zielverhalten und sind bewusst vor der
Korrektur rot. Die historischen Reproduktionen in
``cache/scratch/test_argon_repro.py`` behaupten dagegen den Fehler und bleiben
unverändert.
"""

from __future__ import annotations

import time
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import IntegrityError, connection
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.forms import EmployeeInviteForm
from core.models import EmployeeActivation, Membership, Station
from core.setup_wizard import (
    SetupConflict,
    active_activations,
    create_activation,
    create_employee_invite,
    revoke_activation,
)
from core.setup_views import (
    DRAFT_SESSION_KEY,
    SETUP_SESSION_AT,
    SETUP_SESSION_KEY,
    WEATHER_SESSION_KEY,
)

BOOTSTRAP = "argon-remediation-bootstrap-token"
PASSWORD = "Sicher-Passwort-2026!"


def setup_payload(**overrides):
    data = {
        "station_name": "Rettungswache Teststadt",
        "organization_profile": "rescue",
        "employee_count": "24",
        "street": "Musterstraße 12",
        "postal_code": "49074",
        "city": "Osnabrück",
        "timezone_name": "Europe/Berlin",
        "admin_username": "admin-chef",
        "admin_first_name": "Alex",
        "admin_last_name": "Admin",
        "admin_email": "admin@example.invalid",
        "password1": PASSWORD,
        "password2": PASSWORD,
    }
    data.update(overrides)
    return data


def mkstation(slug="wache-soll"):
    return Station.objects.create(name="Wache Soll", slug=slug)


def mkadmin(station):
    admin = User.objects.create_user("admin-soll", password=PASSWORD)
    Membership.objects.create(user=admin, station=station, role=Membership.Role.ADMIN)
    return admin


def mkpending(username="pending-soll"):
    user = User.objects.create_user(username=username, password=None)
    user.set_unusable_password()
    user.is_active = False
    user.save(update_fields=["password", "is_active"])
    return user


class ExpiredActivationReissueTests(TestCase):
    """S1: abgelaufene offene Aktivierung wird atomar widerrufen."""

    def setUp(self):
        cache.clear()
        self.station = mkstation()
        self.user = User.objects.create_user("s1-user", password=PASSWORD)

    def test_expired_activation_is_revoked_before_reissue(self):
        old, _ = create_activation(user=self.user, station=self.station, created_by=None)
        EmployeeActivation.objects.filter(pk=old.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        new, raw = create_activation(user=self.user, station=self.station, created_by=None)

        old.refresh_from_db()
        self.assertIsNotNone(old.revoked_at)
        self.assertIsNone(new.revoked_at)
        self.assertTrue(raw)
        self.assertNotEqual(old.pk, new.pk)
        self.assertEqual(
            list(active_activations(self.station).values_list("pk", flat=True)),
            [new.pk],
        )

    def test_open_activation_unique_constraint_exists(self):
        # S1 relies on the database enforcing at most one open activation per
        # account even if two reissues race.
        constraint = next(
            item for item in EmployeeActivation._meta.constraints
            if item.name == "unique_open_activation_per_user"
        )
        self.assertEqual(set(constraint.fields), {"user"})
        self.assertEqual(
            set(constraint.condition.children),
            {("used_at__isnull", True), ("revoked_at__isnull", True)},
        )
        if connection.vendor == "sqlite":
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT sql FROM sqlite_master WHERE type='index' AND name=%s",
                    ["unique_open_activation_per_user"],
                )
                ddl = (cursor.fetchone() or [""])[0] or ""
            self.assertIn("WHERE", ddl.upper())
            self.assertRegex(ddl, r'"?used_at"?\s+IS\s+NULL')
            self.assertRegex(ddl, r'"?revoked_at"?\s+IS\s+NULL')
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(
                cursor, EmployeeActivation._meta.db_table
            )
        self.assertTrue(
            any(
                info.get("unique")
                and info.get("columns") == ["user_id"]
                and name == "unique_open_activation_per_user"
                for name, info in constraints.items()
            ),
            "partieller Unique-Index auf EmployeeActivation.user fehlt",
        )

    def test_reissue_rolls_back_when_creation_fails(self):
        old, _ = create_activation(user=self.user, station=self.station, created_by=None)
        EmployeeActivation.objects.filter(pk=old.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        with mock.patch(
            "core.setup_wizard.EmployeeActivation.objects.create",
            side_effect=IntegrityError,
        ):
            with self.assertRaises(SetupConflict):
                create_activation(user=self.user, station=self.station, created_by=None)
        old.refresh_from_db()
        self.assertIsNone(old.revoked_at, "Widerruf muss mit der fehlgeschlagenen Ausstellung zurückrollen")


class ReinstatePendingInviteTests(TestCase):
    """S2: eigenes unaktiviertes Einladungskonto wiederverwenden, nie übernehmen."""

    def setUp(self):
        cache.clear()
        self.station = mkstation()
        self.admin = mkadmin(self.station)

    def _invite(self, username="reinvite"):
        return create_employee_invite(
            station=self.station,
            created_by=self.admin,
            data={"username": username, "first_name": "", "last_name": "", "role": "member"},
        )

    def test_revoked_invite_can_be_reissued_for_same_pending_user(self):
        user, activation, _ = self._invite()
        revoke_activation(activation, actor=self.admin)

        again, new_activation, new_raw = self._invite()

        self.assertEqual(user.pk, again.pk)
        self.assertEqual(User.objects.filter(username="reinvite").count(), 1)
        self.assertFalse(again.is_active)
        self.assertFalse(again.has_usable_password())
        self.assertEqual(Membership.objects.filter(user=again).count(), 0)
        activation.refresh_from_db()
        self.assertIsNotNone(activation.revoked_at)
        self.assertIsNone(new_activation.revoked_at)
        self.assertGreater(len(new_raw), 20)

    def test_expired_invite_can_be_reissued_for_same_pending_user(self):
        user, activation, _ = self._invite()
        EmployeeActivation.objects.filter(pk=activation.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        again, new_activation, _ = self._invite()

        self.assertEqual(user.pk, again.pk)
        activation.refresh_from_db()
        self.assertIsNotNone(activation.revoked_at)
        self.assertIsNone(new_activation.revoked_at)

    def test_open_invitation_blocks_silent_replacement(self):
        user, activation, _ = self._invite("open-pending")

        with self.assertRaises(SetupConflict) as caught:
            self._invite("open-pending")

        self.assertIn("offener Aktivierungslink", str(caught.exception))
        self.assertEqual(EmployeeActivation.objects.filter(user=user).count(), 1)
        activation.refresh_from_db()
        self.assertIsNone(activation.revoked_at)

    def test_reissue_through_view_succeeds(self):
        client = Client()
        client.force_login(self.admin)
        first = client.post(reverse("team_invite_create"), {"username": "view-reinvite", "role": "member"})
        self.assertEqual(first.status_code, 200)
        activation = EmployeeActivation.objects.get(user__username="view-reinvite")
        client.post(reverse("team_invite_revoke", kwargs={"pk": activation.pk}))

        second = client.post(
            reverse("team_invite_create"), {"username": "view-reinvite", "role": "member"}
        )

        self.assertEqual(second.status_code, 200)
        if "form" in second.context:
            self.assertNotIn("username", second.context["form"].errors)
        self.assertEqual(User.objects.filter(username="view-reinvite").count(), 1)
        self.assertEqual(
            EmployeeActivation.objects.filter(
                user__username="view-reinvite",
                used_at__isnull=True,
                revoked_at__isnull=True,
            ).count(),
            1,
        )

    def test_active_account_is_never_taken_over(self):
        existing = User.objects.create_user("active-user", password=PASSWORD)
        Membership.objects.create(user=existing, station=self.station, role=Membership.Role.MEMBER)
        original_hash = existing.password

        form = EmployeeInviteForm(data={"username": "active-user", "role": "member"})
        self.assertFalse(form.is_valid())
        self.assertIn("username", form.errors)

        with self.assertRaises(SetupConflict):
            create_employee_invite(
                station=self.station,
                created_by=self.admin,
                data={"username": "active-user", "role": "member"},
            )

        existing.refresh_from_db()
        self.assertTrue(existing.is_active)
        self.assertEqual(existing.password, original_hash)
        self.assertEqual(Membership.objects.filter(user=existing).count(), 1)
        self.assertFalse(
            EmployeeActivation.objects.filter(user=existing).exists(),
            "Für ein aktives Konto darf keine Einladung entstehen",
        )

    def test_ever_activated_account_is_not_reused(self):
        user = mkpending("was-active")
        activation, _ = create_activation(user=user, station=self.station, created_by=None)
        EmployeeActivation.objects.filter(pk=activation.pk).update(
            used_at=timezone.now()
        )

        form = EmployeeInviteForm(data={"username": "was-active", "role": "member"})
        self.assertFalse(form.is_valid())
        with self.assertRaises(SetupConflict):
            self._invite("was-active")

    def test_pending_user_of_foreign_station_is_not_reused(self):
        other = Station.objects.create(name="Wache Fremd", slug="wache-fremd")
        foreign = mkpending("foreign-pending")
        Membership.objects.create(
            user=foreign, station=other, role=Membership.Role.MEMBER, is_active=False
        )

        form = EmployeeInviteForm(data={"username": "foreign-pending", "role": "member"})
        self.assertFalse(form.is_valid())
        with self.assertRaises(SetupConflict):
            create_employee_invite(
                station=self.station,
                created_by=self.admin,
                data={"username": "foreign-pending", "role": "member"},
            )
        self.assertEqual(Membership.objects.filter(user=foreign).count(), 1)


@override_settings(SETUP_BOOTSTRAP_TOKEN=BOOTSTRAP)
class BootstrapSessionProofTests(TestCase):
    """S3: Sessionnachweis gilt nur für das aktuell konfigurierte Token."""

    def setUp(self):
        cache.clear()
        self.client.post(reverse("setup_wizard"), {"bootstrap_token": BOOTSTRAP})

    def test_rotated_token_invalidates_session_and_blocks_weather_call(self):
        location = {"latitude": 52.2787, "longitude": 8.0479, "label": "Osnabrück"}
        forecast = SimpleNamespace(
            days=[{"date": "2026-10-19"}], fetched_at_iso="x", stale=False, age_minutes=0
        )
        with override_settings(SETUP_BOOTSTRAP_TOKEN="rotated-secret"), \
             mock.patch("core.weather.geocode", return_value=location) as geocode, \
             mock.patch("core.weather.fetch_forecast", return_value=forecast):
            response = self.client.post(
                reverse("setup_weather_preview"),
                setup_payload(weather_enabled="on", geo_consent="1"),
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("setup_wizard"))
        geocode.assert_not_called()
        self.assertNotIn(SETUP_SESSION_KEY, self.client.session)

    def test_rotated_token_hides_wizard_form(self):
        with override_settings(SETUP_BOOTSTRAP_TOKEN="rotated-secret"):
            response = self.client.get(reverse("setup_wizard"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Master-Admin-Konto")
        self.assertContains(response, "Bootstrap-Token")

    def test_tampered_proof_with_fresh_ttl_is_rejected(self):
        # A valid TTL alone must not authenticate: the stored proof has to be
        # the hash of the token that is configured right now.
        from core.setup_views import _session_proof_valid

        session = {
            SETUP_SESSION_KEY: "0" * 64,
            SETUP_SESSION_AT: time.time(),
        }
        request = SimpleNamespace(session=session)

        self.assertFalse(_session_proof_valid(request))
        self.assertNotIn(SETUP_SESSION_KEY, session)


@override_settings(SETUP_BOOTSTRAP_TOKEN=BOOTSTRAP)
class WeatherAddressBindingTests(TestCase):
    """S4: Koordinaten gehören ausschließlich zur geprüften Anschrift."""

    def setUp(self):
        cache.clear()
        self.client.post(reverse("setup_wizard"), {"bootstrap_token": BOOTSTRAP})
        self.osnabrueck = {"latitude": 52.2787, "longitude": 8.0479, "label": "Osnabrück"}
        self.berlin = {"latitude": 52.5200, "longitude": 13.4050, "label": "Berlin"}
        self.forecast = SimpleNamespace(
            days=[{"date": "2026-10-19"}], fetched_at_iso="x", stale=False, age_minutes=0
        )

    def _preview(self, location, **overrides):
        with mock.patch("core.weather.geocode", return_value=location), \
             mock.patch("core.weather.fetch_forecast", return_value=self.forecast):
            return self.client.post(
                reverse("setup_weather_preview"),
                setup_payload(weather_enabled="on", geo_consent="1", **overrides),
            )

    def test_changed_address_requires_a_new_preview(self):
        self.assertEqual(self._preview(self.osnabrueck).status_code, 302)

        response = self.client.post(
            reverse("setup_wizard"),
            setup_payload(
                street="Hauptstr. 1",
                postal_code="10115",
                city="Berlin",
                weather_enabled="on",
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("weather_enabled", response.context["form"].errors)
        self.assertEqual(Station.objects.count(), 0)
        self.assertNotIn(WEATHER_SESSION_KEY, self.client.session)

    def test_matching_address_stores_its_own_coordinates(self):
        self.assertEqual(
            self._preview(
                self.berlin, street="Hauptstr. 1", postal_code="10115", city="Berlin"
            ).status_code,
            302,
        )
        response = self.client.post(
            reverse("setup_wizard"),
            setup_payload(
                street="Hauptstr. 1",
                postal_code="10115",
                city="Berlin",
                weather_enabled="on",
            ),
        )
        self.assertEqual(response.status_code, 302)
        station = Station.objects.get()
        self.assertEqual(station.city, "Berlin")
        self.assertEqual(station.latitude, self.berlin["latitude"])
        self.assertEqual(station.longitude, self.berlin["longitude"])


@override_settings(SETUP_BOOTSTRAP_TOKEN=BOOTSTRAP)
class PartialWeatherPreviewTests(TestCase):
    """S5: Teil-POST zeigt keine sachfremden Admin-/Passwortfehler."""

    def setUp(self):
        cache.clear()
        self.client.post(reverse("setup_wizard"), {"bootstrap_token": BOOTSTRAP})
        self.station_payload = {
            "station_name": "Wache 1",
            "organization_profile": "rescue",
            "timezone_name": "Europe/Berlin",
            "weather_enabled": "on",
        }

    def test_missing_consent_does_not_mark_admin_fields(self):
        response = self.client.post(reverse("setup_weather_preview"), self.station_payload)
        self.assertEqual(response.status_code, 200)
        errors = response.context["form"].errors
        for field in ("admin_username", "password1", "password2"):
            self.assertNotIn(field, errors)
        self.assertTrue(response.context["weather_error"])

    def test_successful_preview_keeps_admin_values_for_next_step(self):
        location = {"latitude": 52.2787, "longitude": 8.0479, "label": "Osnabrück"}
        forecast = SimpleNamespace(
            days=[{"date": "2026-10-19"}], fetched_at_iso="x", stale=False, age_minutes=0
        )
        with mock.patch("core.weather.geocode", return_value=location), \
             mock.patch("core.weather.fetch_forecast", return_value=forecast):
            response = self.client.post(
                reverse("setup_weather_preview"),
                setup_payload(weather_enabled="on", geo_consent="1"),
            )
        self.assertEqual(response.status_code, 302)
        draft = self.client.session[DRAFT_SESSION_KEY]
        self.assertEqual(draft["admin_username"], "admin-chef")
        self.assertEqual(draft["admin_email"], "admin@example.invalid")
        for key in draft:
            self.assertNotIn("password", key)

        page = self.client.get(reverse("setup_wizard"))
        self.assertEqual(page.context["form"].initial["admin_username"], "admin-chef")


class ActivationGetEligibilityTests(TestCase):
    """S6: GET zeigt keinen Aktivierungsdialog für nicht einlösbare Links."""

    def setUp(self):
        cache.clear()
        self.station = mkstation()
        self.user = User.objects.create_user("s6-user", password=PASSWORD)

    def test_inactive_station_returns_410_without_names(self):
        _, raw = create_activation(user=self.user, station=self.station, created_by=None)
        Station.objects.filter(pk=self.station.pk).update(is_active=False)

        response = self.client.get(reverse("activate_account", kwargs={"token": raw}))

        self.assertEqual(response.status_code, 410)
        body = response.content.decode("utf-8")
        self.assertNotIn(self.user.username, body)
        self.assertNotIn(self.station.name, body)

    def test_foreign_active_membership_returns_410_and_closes_link(self):
        other = Station.objects.create(name="Wache Andere", slug="wache-andere")
        Membership.objects.create(user=self.user, station=other, role=Membership.Role.MEMBER)
        activation, raw = create_activation(
            user=self.user, station=self.station, created_by=None
        )

        response = self.client.get(reverse("activate_account", kwargs={"token": raw}))

        self.assertEqual(response.status_code, 410)
        activation.refresh_from_db()
        self.assertIsNotNone(activation.revoked_at)
        self.assertTrue(
            Membership.objects.get(user=self.user, station=other).is_active,
            "Fremde Wache darf nicht verändert werden",
        )


class InviteUsernameRaceTests(TestCase):
    """S7: Username-Rennen wird kontrolliert und vollständig zurückgerollt."""

    def setUp(self):
        cache.clear()
        self.station = mkstation()
        self.admin = mkadmin(self.station)

    def test_race_is_translated_to_conflict_without_leftovers(self):
        form = EmployeeInviteForm(data={"username": "raceuser", "role": "member"})
        self.assertTrue(form.is_valid())
        User.objects.create_user("raceuser", password=PASSWORD)

        with self.assertRaises(SetupConflict):
            create_employee_invite(
                station=self.station, created_by=self.admin, data=form.cleaned_data
            )

        self.assertEqual(User.objects.filter(username="raceuser").count(), 1)
        self.assertFalse(EmployeeActivation.objects.filter(user__username="raceuser").exists())
        self.assertFalse(Membership.objects.filter(user__username="raceuser").exists())

    def test_view_reports_conflict_as_form_error(self):
        client = Client()
        client.force_login(self.admin)
        with mock.patch(
            "core.setup_views.create_employee_invite",
            side_effect=SetupConflict("Dieser Benutzername wurde gerade vergeben."),
        ):
            response = client.post(
                reverse("team_invite_create"),
                {"username": "race-view", "role": "member"},
            )
        self.assertIn(response.status_code, (200, 409))
        self.assertIn("username", response.context["form"].errors)
        self.assertFalse(User.objects.filter(username="race-view").exists())
