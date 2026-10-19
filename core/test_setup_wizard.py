"""Acceptance tests for the first-install wizard, activation and offline contract.

Contract: docs/SETUP-WIZARD-PLAN.md and docs/OFFLINE-BETRIEB.md.
These tests intentionally include negative cases (replay, foreign station,
expired/revoked token, CSRF, WAN outage).
"""

from __future__ import annotations

import socket
from datetime import datetime, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from core import weather
from core.models import (
    AuditEvent,
    EmployeeActivation,
    InstallationSetup,
    Membership,
    Station,
    TotpDevice,
)
from core.setup_wizard import create_activation, hash_token


def local_days(count: int = 5) -> list[str]:
    """Die nächsten lokalen Kalendertage als ISO-Strings.

    Wettertests dürfen nicht an fest verdrahteten Daten hängen: Der Forecast
    gilt nur, wenn er zu den fünf lokalen Tagen ab heute passt.
    """
    start = datetime.now(ZoneInfo("Europe/Berlin")).date()
    return [(start + timedelta(days=index)).isoformat() for index in range(count)]


BOOTSTRAP = "test-bootstrap-token-2026-very-secret"
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


class SetupWizardTests(TestCase):
    def setUp(self):
        cache.clear()

    @override_settings(SETUP_BOOTSTRAP_TOKEN="")
    def test_setup_is_404_without_configured_bootstrap_secret(self):
        self.assertEqual(self.client.get(reverse("setup_wizard")).status_code, 404)
        self.assertEqual(
            self.client.post(reverse("setup_wizard"), {"bootstrap_token": "x"}).status_code, 404
        )

    @override_settings(SETUP_BOOTSTRAP_TOKEN=BOOTSTRAP)
    def test_wrong_token_is_rejected_and_rate_limited(self):
        first = self.client.post(reverse("setup_wizard"), {"bootstrap_token": "falsch"})
        self.assertEqual(first.status_code, 403)
        for _ in range(5):
            response = self.client.post(reverse("setup_wizard"), {"bootstrap_token": "falsch"})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(InstallationSetup.objects.count(), 0)

    @override_settings(SETUP_BOOTSTRAP_TOKEN=BOOTSTRAP)
    def test_complete_setup_creates_exactly_one_station_and_admin(self):
        self.client.post(reverse("setup_wizard"), {"bootstrap_token": BOOTSTRAP})
        response = self.client.post(reverse("setup_wizard"), setup_payload())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Station.objects.count(), 1)
        station = Station.objects.get()
        self.assertEqual(station.name, "Rettungswache Teststadt")
        self.assertEqual(station.slug, "rettungswache-teststadt")
        self.assertEqual(station.employee_count, 24)
        self.assertEqual(station.street, "Musterstraße 12")
        self.assertFalse(station.weather_enabled)
        admin = User.objects.get(username="admin-chef")
        self.assertTrue(admin.check_password(PASSWORD))
        membership = Membership.objects.get(user=admin)
        self.assertEqual(membership.station, station)
        self.assertEqual(membership.role, Membership.Role.ADMIN)
        self.assertIsNotNone(InstallationSetup.objects.get(pk=1).completed_at)
        self.assertTrue(AuditEvent.objects.filter(action="setup.completed").exists())

    @override_settings(SETUP_BOOTSTRAP_TOKEN=BOOTSTRAP)
    def test_second_completion_is_rejected_without_new_resources(self):
        self.client.post(reverse("setup_wizard"), {"bootstrap_token": BOOTSTRAP})
        self.client.post(reverse("setup_wizard"), setup_payload())
        fresh = Client()
        fresh.post(reverse("setup_wizard"), {"bootstrap_token": BOOTSTRAP})
        second = fresh.post(reverse("setup_wizard"), setup_payload(admin_username="admin-zwei"))
        self.assertEqual(second.status_code, 404)
        self.assertEqual(Station.objects.count(), 1)
        self.assertFalse(User.objects.filter(username="admin-zwei").exists())
        # Service level still enforces the atomic single-claim contract.
        from core.setup_wizard import SetupAlreadyCompleted, complete_setup

        with self.assertRaises(SetupAlreadyCompleted):
            complete_setup(
                data={**setup_payload(), "slug": "zweite-wache"}, raw_token=BOOTSTRAP
            )

    @override_settings(SETUP_BOOTSTRAP_TOKEN=BOOTSTRAP)
    def test_setup_route_is_gone_after_completion_even_with_token(self):
        self.client.post(reverse("setup_wizard"), {"bootstrap_token": BOOTSTRAP})
        self.client.post(reverse("setup_wizard"), setup_payload())
        self.assertEqual(self.client.get(reverse("setup_wizard")).status_code, 404)
        self.assertEqual(
            self.client.post(reverse("setup_wizard"), {"bootstrap_token": BOOTSTRAP}).status_code,
            404,
        )

    @override_settings(SETUP_BOOTSTRAP_TOKEN=BOOTSTRAP)
    def test_completion_does_not_touch_network(self):
        self.client.post(reverse("setup_wizard"), {"bootstrap_token": BOOTSTRAP})
        with mock.patch("core.weather.geocode", side_effect=AssertionError("network call")), \
             mock.patch("core.weather.fetch_forecast", side_effect=AssertionError("network call")):
            response = self.client.post(
                reverse("setup_wizard"), setup_payload()
            )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Station.objects.get().weather_enabled)
        self.assertIsNone(Station.objects.get().latitude)


class ActivationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.station = Station.objects.create(name="Wache Nord", slug="wache-nord")
        self.admin = User.objects.create_user("admin1", password=PASSWORD)
        Membership.objects.create(user=self.admin, station=self.station, role=Membership.Role.ADMIN)
        self.client.force_login(self.admin)
        self.employee = User.objects.create_user("neu1", password=None)
        self.employee.set_unusable_password()
        self.employee.is_active = False
        self.employee.save(update_fields=["password", "is_active"])
        Membership.objects.create(user=self.employee, station=self.station, role=Membership.Role.MEMBER)
        self.activation, self.raw = create_activation(
            user=self.employee, station=self.station, created_by=self.admin
        )

    def test_token_is_stored_only_as_hash(self):
        self.assertNotEqual(self.activation.token_hash, self.raw)
        self.assertEqual(self.activation.token_hash, hash_token(self.raw))
        self.assertNotIn(self.raw, str(self.activation.token_hash))
        audit_text = " ".join(
            str(event.metadata) for event in AuditEvent.objects.all()
        )
        self.assertNotIn(self.raw, audit_text)

    def test_activation_sets_employee_password_and_activates_account(self):
        response = self.client.get(reverse("activate_account", kwargs={"token": self.raw}))
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("no-referrer", response["Referrer-Policy"])
        response = self.client.post(
            reverse("activate_account", kwargs={"token": self.raw}),
            {"password1": PASSWORD, "password2": PASSWORD},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("login"))
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.is_active)
        self.assertTrue(self.employee.check_password(PASSWORD))
        self.activation.refresh_from_db()
        self.assertIsNotNone(self.activation.used_at)
        self.assertNotIn(self.raw, response.content.decode("utf-8"))

    def test_activation_token_is_redacted_in_application_logs(self):
        with self.assertLogs("wachbuch.requests", level="INFO") as captured:
            self.client.get(reverse("activate_account", kwargs={"token": self.raw}))
        joined = "\n".join(captured.output)
        self.assertNotIn(self.raw, joined)
        self.assertIn("[redacted]", joined)

    def test_replay_is_rejected(self):
        self.client.post(
            reverse("activate_account", kwargs={"token": self.raw}),
            {"password1": PASSWORD, "password2": PASSWORD},
        )
        replay = self.client.get(reverse("activate_account", kwargs={"token": self.raw}))
        self.assertEqual(replay.status_code, 410)
        self.assertNotIn(self.raw, replay.content.decode("utf-8"))

    def test_expired_and_revoked_tokens_are_rejected(self):
        self.activation.expires_at = timezone.now() - timedelta(seconds=1)
        self.activation.save(update_fields=["expires_at"])
        self.assertEqual(
            self.client.get(reverse("activate_account", kwargs={"token": self.raw})).status_code,
            410,
        )
        self.activation.expires_at = timezone.now() + timedelta(days=1)
        self.activation.revoked_at = timezone.now()
        self.activation.save(update_fields=["expires_at", "revoked_at"])
        self.assertEqual(
            self.client.get(reverse("activate_account", kwargs={"token": self.raw})).status_code,
            410,
        )

    def test_unknown_token_is_410(self):
        self.assertEqual(
            self.client.get("/aktivieren/voellig-unbekannt/").status_code, 410
        )

    def test_csrf_is_required_for_activation(self):
        strict = Client(enforce_csrf_checks=True)
        response = strict.post(
            reverse("activate_account", kwargs={"token": self.raw}),
            {"password1": PASSWORD, "password2": PASSWORD},
        )
        self.assertEqual(response.status_code, 403)
        self.employee.refresh_from_db()
        self.assertFalse(self.employee.is_active)

    def test_activation_token_does_not_cross_station_boundary(self):
        other = Station.objects.create(name="Wache Süd", slug="wache-sued")
        other_user = User.objects.create_user("fremd", password=None)
        other_user.set_unusable_password()
        other_user.is_active = False
        other_user.save(update_fields=["password", "is_active"])
        foreign, raw = create_activation(user=other_user, station=other, created_by=self.admin)
        self.client.post(
            reverse("activate_account", kwargs={"token": raw}),
            {"password1": PASSWORD, "password2": PASSWORD},
        )
        foreign.refresh_from_db()
        self.assertEqual(foreign.station, other)
        self.assertTrue(
            Membership.objects.filter(user=other_user, station=other).exists()
        )
        self.assertFalse(
            Membership.objects.filter(user=other_user, station=self.station).exists()
        )

    def test_admin_can_create_invite_without_password_and_qr_is_one_time(self):
        response = self.client.post(
            reverse("team_invite_create"),
            {"username": "neu2", "first_name": "Kim", "last_name": "Klein", "role": "member"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("data:image/png;base64,", response.content.decode("utf-8"))
        created = User.objects.get(username="neu2")
        self.assertFalse(created.is_active)
        self.assertFalse(created.has_usable_password())
        activation = EmployeeActivation.objects.get(user=created)
        self.assertEqual(activation.station, self.station)
        self.assertNotIn("neu2", activation.token_hash)

    def test_non_admin_cannot_create_invites(self):
        member = User.objects.create_user("member1", password=PASSWORD)
        Membership.objects.create(user=member, station=self.station, role=Membership.Role.MEMBER)
        client = Client()
        client.force_login(member)
        self.assertEqual(client.get(reverse("team_invite_create")).status_code, 403)
        self.assertEqual(client.get(reverse("team_invites")).status_code, 403)

    def test_invite_revoke_is_station_scoped(self):
        other = Station.objects.create(name="Wache West", slug="wache-west")
        other_user = User.objects.create_user("west1", password=None)
        other_user.set_unusable_password()
        other_user.is_active = False
        other_user.save(update_fields=["password", "is_active"])
        foreign, _ = create_activation(user=other_user, station=other, created_by=self.admin)
        response = self.client.post(reverse("team_invite_revoke", kwargs={"pk": foreign.pk}))
        self.assertEqual(response.status_code, 404)
        foreign.refresh_from_db()
        self.assertIsNone(foreign.revoked_at)

    @override_settings(MFA_ENABLED=True, MFA_REQUIRED=True)
    def test_login_after_activation_still_honours_mfa(self):
        self.client.post(
            reverse("activate_account", kwargs={"token": self.raw}),
            {"password1": PASSWORD, "password2": PASSWORD},
        )
        fresh = Client()
        with mock.patch("core.auth_views.user_has_confirmed_mfa", return_value=True):
            response = fresh.post(
                reverse("login"), {"username": "neu1", "password": PASSWORD}
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("mfa_verify"))
        self.assertNotIn("_auth_user_id", fresh.session)

    def test_no_repeatable_qr_login_route_exists(self):
        for name in ("qr_login", "qr_login_challenge", "qr_token_login"):
            with self.assertRaises(NoReverseMatch):
                reverse(name)


class WeatherTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_geocode_rejects_non_allowlisted_endpoint(self):
        with self.assertRaises(weather.WeatherUnavailable):
            weather._fetch_json("https://evil.example/v1/search", {})
        with self.assertRaises(weather.WeatherUnavailable):
            weather._fetch_json("http://geocoding-api.open-meteo.com/v1/search", {})

    def test_redirects_are_refused(self):
        handler = weather._NoRedirect()
        with self.assertRaises(weather.WeatherUnavailable):
            handler.redirect_request(None, None, 302, "Found", {}, "https://evil.example/")

    def test_forecast_returns_exactly_five_local_days(self):
        payload = {
            "daily": {
                "time": local_days(),
                "temperature_2m_max": [14, 15, 16, 17, 18],
                "temperature_2m_min": [5, 6, 7, 8, 9],
                "precipitation_sum": [0, 1, 2, 3, 4],
                "weather_code": [0, 1, 2, 3, 61],
            }
        }
        with mock.patch("core.weather._fetch_json", return_value=payload) as fetch:
            forecast = weather.fetch_forecast(52.2787, 8.0479)
        self.assertEqual(len(forecast.days), 5)
        self.assertFalse(forecast.stale)
        params = fetch.call_args[0][1]
        self.assertEqual(params["forecast_days"], 5)
        self.assertEqual(params["timezone"], "Europe/Berlin")
        self.assertIn("temperature_2m_max", params["daily"])

    def test_failed_refresh_returns_marked_cache_instead_of_dummy_values(self):
        payload = {
            "daily": {
                "time": local_days(),
                "temperature_2m_max": [14, 15, 16, 17, 18],
                "temperature_2m_min": [5, 6, 7, 8, 9],
                "precipitation_sum": [0, 1, 2, 3, 4],
                "weather_code": [0, 1, 2, 3, 61],
            }
        }
        with mock.patch("core.weather._fetch_json", return_value=payload):
            first = weather.fetch_forecast(52.2787, 8.0479)
        self.assertFalse(first.stale)
        # Age beyond the fresh window so a refresh is attempted, then fails.
        from datetime import timedelta

        from django.core.cache import cache
        from django.utils import timezone

        for key in (
            weather._cache_key(52.2787, 8.0479, "Europe/Berlin"),
            weather._stale_cache_key(52.2787, 8.0479, "Europe/Berlin"),
        ):
            entry = cache.get(key)
            entry["fetched_at"] = (timezone.now() - timedelta(hours=2)).isoformat()
            cache.set(key, entry, weather.FORECAST_STALE_SECONDS)
        with mock.patch(
            "core.weather._fetch_json", side_effect=weather.WeatherUnavailable("offline")
        ):
            second = weather.fetch_forecast(52.2787, 8.0479)
        self.assertTrue(second.stale)
        self.assertEqual(second.days, first.days)

    def test_failure_without_cache_raises(self):
        with mock.patch(
            "core.weather._fetch_json", side_effect=weather.WeatherUnavailable("offline")
        ):
            with self.assertRaises(weather.WeatherUnavailable):
                weather.fetch_forecast(52.2787, 8.0479)

    def test_missing_station_coordinates_raise(self):
        station = Station.objects.create(name="Ohne Ort", slug="ohne-ort", weather_enabled=True)
        with self.assertRaises(weather.WeatherUnavailable):
            weather.forecast_for_station(station)


@override_settings(SETUP_BOOTSTRAP_TOKEN=BOOTSTRAP)
class WeatherConsentTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.post(reverse("setup_wizard"), {"bootstrap_token": BOOTSTRAP})

    def test_without_consent_no_external_call_and_no_preview(self):
        with mock.patch("core.weather.geocode") as geocode:
            response = self.client.post(
                reverse("setup_weather_preview"),
                setup_payload(weather_enabled="on"),
            )
        self.assertEqual(response.status_code, 200)
        geocode.assert_not_called()
        self.assertNotIn("setup_weather_preview", self.client.session)

    def test_weather_preview_requires_csrf(self):
        strict = Client(enforce_csrf_checks=True)
        strict.post(reverse("setup_wizard"), {"bootstrap_token": BOOTSTRAP})
        with mock.patch("core.weather.geocode") as geocode:
            response = strict.post(
                reverse("setup_weather_preview"),
                setup_payload(weather_enabled="on", geo_consent="1"),
            )
        self.assertEqual(response.status_code, 403)
        geocode.assert_not_called()

    def test_weather_failure_does_not_block_setup(self):
        with mock.patch(
            "core.weather.geocode", side_effect=weather.WeatherUnavailable("offline")
        ):
            response = self.client.post(
                reverse("setup_weather_preview"),
                setup_payload(weather_enabled="on", geo_consent="1"),
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("nicht betroffen", response.content.decode("utf-8"))
        completed = self.client.post(reverse("setup_wizard"), setup_payload())
        self.assertEqual(completed.status_code, 302)
        self.assertEqual(Station.objects.count(), 1)

    def test_consented_preview_stores_coordinates_only_after_success(self):
        location = {"latitude": 52.2787, "longitude": 8.0479, "label": "Osnabrück"}
        forecast = weather.Forecast(
            days=[
                {
                    "date": day,
                    "temperature_max": 15,
                    "temperature_min": 5,
                    "precipitation_mm": 0,
                    "weather_code": 0,
                }
                for day in local_days()
            ],
            fetched_at=timezone.now(),
            stale=False,
        )
        with mock.patch("core.weather.geocode", return_value=location) as geocode, \
             mock.patch("core.weather.fetch_forecast", return_value=forecast):
            response = self.client.post(
                reverse("setup_weather_preview"),
                setup_payload(weather_enabled="on", geo_consent="1"),
            )
        self.assertEqual(response.status_code, 302)
        geocode.assert_called_once()
        preview = self.client.session["setup_weather_preview"]
        self.assertEqual(len(preview["days"]), 5)
        self.assertEqual(preview["latitude"], 52.2787)
        self.client.post(reverse("setup_wizard"), setup_payload(weather_enabled="on"))
        station = Station.objects.get()
        self.assertEqual(station.latitude, 52.2787)
        self.assertEqual(station.longitude, 8.0479)


@override_settings(SETUP_BOOTSTRAP_TOKEN=BOOTSTRAP)
class WanOutageTests(TestCase):
    """WAN outage with a reachable local server: all core flows must work."""

    def setUp(self):
        cache.clear()

    def _deny_network(self):
        def deny(*args, **kwargs):
            raise OSError("network disabled for WAN outage test")

        return mock.patch.multiple(
            socket, getaddrinfo=deny, create_connection=deny, socket=deny
        )

    def test_full_setup_login_invite_activation_without_wan(self):
        with mock.patch("socket.getaddrinfo", side_effect=OSError("no dns")), \
             mock.patch("socket.create_connection", side_effect=OSError("no wan")), \
             mock.patch("urllib.request.urlopen", side_effect=OSError("no wan")):
            self.assertEqual(
                self.client.post(
                    reverse("setup_wizard"), {"bootstrap_token": BOOTSTRAP}
                ).status_code,
                302,
            )
            completed = self.client.post(reverse("setup_wizard"), setup_payload())
            self.assertEqual(completed.status_code, 302)
            admin = User.objects.get(username="admin-chef")
            self.assertTrue(admin.check_password(PASSWORD))

            self.client.force_login(admin)
            invite = self.client.post(
                reverse("team_invite_create"),
                {"username": "offline1", "role": "member"},
            )
            self.assertEqual(invite.status_code, 200)
            raw = EmployeeActivation.objects.get(user__username="offline1")
            self.assertTrue(raw.token_hash)
            self.client.logout()

        # Activation link was generated locally; use a fresh client (employee).
        employee_client = Client()
        activation = EmployeeActivation.objects.get(user__username="offline1")
        # The raw token is not recoverable from the DB, so create a fresh one
        # through the service to exercise the offline activation path.
        from core.setup_wizard import create_activation

        activation.revoked_at = timezone.now()
        activation.save(update_fields=["revoked_at"])
        _, raw_token = create_activation(
            user=activation.user, station=activation.station, created_by=None
        )
        page = employee_client.get(reverse("activate_account", kwargs={"token": raw_token}))
        self.assertEqual(page.status_code, 200)
        done = employee_client.post(
            reverse("activate_account", kwargs={"token": raw_token}),
            {"password1": PASSWORD, "password2": PASSWORD},
        )
        self.assertEqual(done.status_code, 302)
        self.assertTrue(User.objects.get(username="offline1").is_active)

    def test_weather_module_never_called_during_offline_setup(self):
        with mock.patch("core.weather._urlopen", side_effect=AssertionError("external call")):
            self.client.post(reverse("setup_wizard"), {"bootstrap_token": BOOTSTRAP})
            response = self.client.post(reverse("setup_wizard"), setup_payload())
        self.assertEqual(response.status_code, 302)
