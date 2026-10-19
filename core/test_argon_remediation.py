"""Regression tests for the confirmed Argon review findings (2026-10-19).

Each test class names the finding ID from ``docs/ARGON-FINAL-REVIEW.md``.
All weather cases use synthetic coordinates and mocked payloads; no real
address, no real Open-Meteo call.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core import weather
from core.errors import log_exception
from core.forms import ActivationPasswordForm, SetupWizardForm
from core.middleware import redact_request_path
from core.models import (
    EmployeeActivation,
    RateLimit,
    InstallationSetup,
    Membership,
    Station,
)
from core.setup_wizard import (
    ActivationInvalid,
    SetupConflict,
    active_activations,
    complete_setup,
    consume_activation,
    create_activation,
    create_employee_invite,
)

BOOTSTRAP = "argon-remediation-bootstrap-token"
PASSWORD = "Sicher-Passwort-2026!"
SYNTH_TOKEN = "SYNTHETIC-ONLY-token-abc123"


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


def forecast_payload():
    today = timezone.localdate()
    return {
        "daily": {
            "time": [(today + timedelta(days=offset)).isoformat() for offset in range(5)],
            "temperature_2m_max": [14, 15, 16, 17, 18],
            "temperature_2m_min": [5, 6, 7, 8, 9],
            "precipitation_sum": [0, 1, 2, 3, 4],
            "weather_code": [0, 1, 2, 3, 61],
        }
    }


class RoleActivationTests(TestCase):
    """P2-1: invited role is stored and applied without privilege escalation."""

    def setUp(self):
        cache.clear()
        self.station = Station.objects.create(name="Wache Nord", slug="wache-nord")
        self.admin = User.objects.create_user("admin1", password=PASSWORD)
        Membership.objects.create(
            user=self.admin, station=self.station, role=Membership.Role.ADMIN
        )

    def _invite(self, username, role):
        data = {"username": username, "first_name": "", "last_name": "", "role": role}
        return create_employee_invite(
            station=self.station, created_by=self.admin, data=data
        )

    def test_invited_role_is_persisted_and_applied(self):
        for role in (
            Membership.Role.MEMBER,
            Membership.Role.SHIFT_LEAD,
            Membership.Role.CASHIER,
        ):
            user, activation, raw = self._invite(f"neu-{role}", role)
            self.assertEqual(activation.role, role)
            consume_activation(raw, password=PASSWORD)
            membership = Membership.objects.get(user=user, station=self.station)
            self.assertEqual(membership.role, role)
            self.assertTrue(membership.is_active)
            self.assertTrue(User.objects.get(pk=user.pk).is_active)

    def test_tampered_admin_role_does_not_escalate(self):
        user, activation, raw = self._invite("neu-tamper", Membership.Role.MEMBER)
        EmployeeActivation.objects.filter(pk=activation.pk).update(role="admin")
        consume_activation(raw, password=PASSWORD)
        membership = Membership.objects.get(user=user, station=self.station)
        self.assertEqual(membership.role, Membership.Role.MEMBER)

    def test_existing_admin_membership_is_not_downgraded(self):
        activation, raw = create_activation(
            user=self.admin, station=self.station, created_by=self.admin,
            role=Membership.Role.MEMBER,
        )
        consume_activation(raw, password=PASSWORD)
        membership = Membership.objects.get(user=self.admin, station=self.station)
        self.assertEqual(membership.role, Membership.Role.ADMIN)
        self.assertTrue(membership.is_active)

    def test_user_of_foreign_station_is_not_moved_or_deactivated(self):
        other = Station.objects.create(name="Wache Süd", slug="wache-sued")
        foreign_user = User.objects.create_user("fremd1", password=PASSWORD)
        foreign_membership = Membership.objects.create(
            user=foreign_user, station=other, role=Membership.Role.SHIFT_LEAD
        )
        activation, raw = create_activation(
            user=foreign_user, station=self.station, created_by=self.admin,
            role=Membership.Role.MEMBER,
        )
        with self.assertRaises(ActivationInvalid):
            consume_activation(raw, password=PASSWORD)
        foreign_membership.refresh_from_db()
        self.assertTrue(foreign_membership.is_active)
        self.assertEqual(foreign_membership.role, Membership.Role.SHIFT_LEAD)
        activation.refresh_from_db()
        self.assertIsNone(activation.used_at)
        self.assertFalse(
            Membership.objects.filter(user=foreign_user, station=self.station).exists()
        )

    def test_failure_after_consumption_rolls_back_token_and_password(self):
        user, activation, raw = self._invite("neu-rollback", Membership.Role.MEMBER)
        original_hash = user.password
        with mock.patch(
            "core.setup_wizard.Membership.objects.create",
            side_effect=RuntimeError("synthetic failure"),
        ):
            with self.assertRaises(RuntimeError):
                consume_activation(raw, password=PASSWORD)
        activation.refresh_from_db()
        self.assertIsNone(activation.used_at)
        user.refresh_from_db()
        self.assertEqual(user.password, original_hash)
        self.assertFalse(user.is_active)

    def test_invite_view_stores_selected_role(self):
        client = Client()
        client.force_login(self.admin)
        response = client.post(
            reverse("team_invite_create"),
            {"username": "neu-view", "role": Membership.Role.CASHIER},
        )
        self.assertEqual(response.status_code, 200)
        activation = EmployeeActivation.objects.get(user__username="neu-view")
        self.assertEqual(activation.role, Membership.Role.CASHIER)


class RedactionTests(TestCase):
    """P2-2: activation tokens are redacted with and without trailing slash."""

    def test_redacts_without_trailing_slash(self):
        self.assertEqual(
            redact_request_path(f"/aktivieren/{SYNTH_TOKEN}"),
            "/aktivieren/[redacted]",
        )

    def test_redacts_with_trailing_slash(self):
        self.assertEqual(
            redact_request_path(f"/aktivieren/{SYNTH_TOKEN}/"),
            "/aktivieren/[redacted]/",
        )

    def test_unrelated_paths_are_untouched(self):
        self.assertEqual(redact_request_path("/uebersicht/"), "/uebersicht/")

    def test_exception_logger_redacts_token(self):
        request = mock.Mock()
        request.path = f"/aktivieren/{SYNTH_TOKEN}"
        request.method = "GET"
        request.META = {}
        with self.assertLogs("wachbuch.errors", level="ERROR") as captured:
            log_exception(request, message="synthetic")
        self.assertNotIn(SYNTH_TOKEN, "\n".join(captured.output))
        self.assertIn("[redacted]", "\n".join(captured.output))

    def test_request_logger_redacts_token_in_both_forms(self):
        station = Station.objects.create(name="Wache Log", slug="wache-log")
        user = User.objects.create_user("log1", password=PASSWORD)
        Membership.objects.create(user=user, station=station, role=Membership.Role.MEMBER)
        _, raw = create_activation(user=user, station=station, created_by=None)
        logger = logging.getLogger("wachbuch.requests")
        records: list[str] = []

        class Collect(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        handler = Collect()
        logger.addHandler(handler)
        try:
            client = Client()
            client.get(f"/aktivieren/{raw}")
            client.get(f"/aktivieren/{raw}/")
        finally:
            logger.removeHandler(handler)
        joined = "\n".join(records)
        self.assertNotIn(raw, joined)


class WeatherCacheTests(TestCase):
    """P2-3: fresh cache is read; separate bounded stale cache keeps fetch time."""

    def setUp(self):
        cache.clear()
        self.lat, self.lon = 52.2787, 8.0479
        self.tz = "Europe/Berlin"
        self.key = weather._cache_key(self.lat, self.lon, self.tz)
        self.stale_key = weather._stale_cache_key(self.lat, self.lon, self.tz)

    def _age_entry(self, hours: float, *, days=None):
        entry = dict(cache.get(self.key))
        entry["fetched_at"] = (timezone.now() - timedelta(hours=hours)).isoformat()
        if days is not None:
            entry["days"] = days
        cache.set(self.key, entry, weather.FORECAST_CACHE_SECONDS)
        cache.set(self.stale_key, entry, weather.FORECAST_STALE_SECONDS)
        return entry

    def test_second_call_within_one_hour_does_not_hit_network(self):
        payload = forecast_payload()
        with mock.patch("core.weather._fetch_json", return_value=payload) as fetch:
            first = weather.fetch_forecast(self.lat, self.lon)
            second = weather.fetch_forecast(self.lat, self.lon)
        self.assertEqual(fetch.call_count, 1)
        self.assertFalse(first.stale)
        self.assertFalse(second.stale)
        self.assertEqual(second.days, first.days)

    def test_failure_after_fresh_window_returns_stale_with_original_time(self):
        payload = forecast_payload()
        with mock.patch("core.weather._fetch_json", return_value=payload):
            first = weather.fetch_forecast(self.lat, self.lon)
        aged = self._age_entry(2)
        with mock.patch(
            "core.weather._fetch_json", side_effect=weather.WeatherUnavailable("offline")
        ):
            stale = weather.fetch_forecast(self.lat, self.lon)
        self.assertTrue(stale.stale)
        self.assertEqual(stale.fetched_at.isoformat(), aged["fetched_at"])
        self.assertEqual(stale.days, first.days)
        self.assertGreaterEqual(stale.age_minutes, 120)

    def test_expired_stale_entry_is_not_served(self):
        with mock.patch("core.weather._fetch_json", return_value=forecast_payload()):
            weather.fetch_forecast(self.lat, self.lon)
        self._age_entry(weather.FORECAST_STALE_SECONDS / 3600 + 1)
        with mock.patch(
            "core.weather._fetch_json", side_effect=weather.WeatherUnavailable("offline")
        ):
            with self.assertRaises(weather.WeatherUnavailable):
                weather.fetch_forecast(self.lat, self.lon)

    def test_circuit_open_serves_fresh_cache_without_network(self):
        with mock.patch("core.weather._fetch_json", return_value=forecast_payload()):
            weather.fetch_forecast(self.lat, self.lon)
        cache.set("weather:circuit:open", True, weather.CIRCUIT_SECONDS)
        with mock.patch("core.weather._fetch_json") as fetch:
            result = weather.fetch_forecast(self.lat, self.lon)
        fetch.assert_not_called()
        self.assertFalse(result.stale)

    def test_stale_days_in_the_past_are_not_presented_as_next_five_days(self):
        old_days = [
            {
                "date": (timezone.localdate() - timedelta(days=5 - offset)).isoformat(),
                "temperature_max": 10,
                "temperature_min": 1,
                "precipitation_mm": 0,
                "weather_code": 0,
            }
            for offset in range(5)
        ]
        with mock.patch("core.weather._fetch_json", return_value=forecast_payload()):
            weather.fetch_forecast(self.lat, self.lon)
        self._age_entry(0.5, days=old_days)
        with mock.patch(
            "core.weather._fetch_json", side_effect=weather.WeatherUnavailable("offline")
        ):
            with self.assertRaises(weather.WeatherUnavailable):
                weather.fetch_forecast(self.lat, self.lon)

    def test_non_consecutive_stale_days_are_rejected(self):
        today = timezone.localdate()
        gapped = [
            {
                "date": (today + timedelta(days=offset * 2)).isoformat(),
                "temperature_max": 10,
                "temperature_min": 1,
                "precipitation_mm": 0,
                "weather_code": 0,
            }
            for offset in range(5)
        ]
        with mock.patch("core.weather._fetch_json", return_value=forecast_payload()):
            weather.fetch_forecast(self.lat, self.lon)
        self._age_entry(0.5, days=gapped)
        with mock.patch(
            "core.weather._fetch_json", side_effect=weather.WeatherUnavailable("offline")
        ):
            with self.assertRaises(weather.WeatherUnavailable):
                weather.fetch_forecast(self.lat, self.lon)

    def test_invalid_timezone_is_rejected_and_never_used_in_cache_key(self):
        with mock.patch("core.weather._fetch_json") as fetch:
            with self.assertRaises(weather.WeatherUnavailable):
                weather.fetch_forecast(self.lat, self.lon, timezone_name="Nicht/Real")
        fetch.assert_not_called()


@override_settings(SETUP_BOOTSTRAP_TOKEN=BOOTSTRAP)
class WeatherPreviewConsentTests(TestCase):
    """P2-4: preview needs weather_enabled AND consent AND an allowed timezone."""

    def setUp(self):
        cache.clear()
        self.client.post(reverse("setup_wizard"), {"bootstrap_token": BOOTSTRAP})

    def test_preview_without_weather_enabled_sends_nothing(self):
        with mock.patch("core.weather.geocode") as geocode, mock.patch(
            "core.weather.fetch_forecast"
        ) as forecast:
            response = self.client.post(
                reverse("setup_weather_preview"),
                setup_payload(geo_consent="1"),
            )
        self.assertEqual(response.status_code, 200)
        geocode.assert_not_called()
        forecast.assert_not_called()
        self.assertNotIn("setup_weather_preview", self.client.session)

    def test_preview_rejects_invalid_timezone_before_geocoding(self):
        with mock.patch("core.weather.geocode") as geocode:
            response = self.client.post(
                reverse("setup_weather_preview"),
                setup_payload(
                    weather_enabled="on",
                    geo_consent="1",
                    timezone_name="Nicht/Real",
                ),
            )
        self.assertEqual(response.status_code, 200)
        geocode.assert_not_called()

    def test_preview_rejects_unlisted_valid_timezone(self):
        with mock.patch("core.weather.geocode") as geocode:
            response = self.client.post(
                reverse("setup_weather_preview"),
                setup_payload(
                    weather_enabled="on",
                    geo_consent="1",
                    timezone_name="America/New_York",
                ),
            )
        self.assertEqual(response.status_code, 200)
        geocode.assert_not_called()

    def test_preview_with_both_consents_calls_once(self):
        location = {"latitude": 52.2787, "longitude": 8.0479, "label": "Osnabrück"}
        days = [
            {
                "date": day,
                "temperature_max": 15,
                "temperature_min": 5,
                "precipitation_mm": 0,
                "weather_code": 0,
            }
            for day in forecast_payload()["daily"]["time"]
        ]
        forecast = weather.Forecast(
            days=days, fetched_at=timezone.now(), stale=False
        )
        with mock.patch("core.weather.geocode", return_value=location) as geocode, mock.patch(
            "core.weather.fetch_forecast", return_value=forecast
        ) as fetch:
            response = self.client.post(
                reverse("setup_weather_preview"),
                setup_payload(weather_enabled="on", geo_consent="1"),
            )
        self.assertEqual(response.status_code, 302)
        geocode.assert_called_once()
        fetch.assert_called_once()
        self.assertEqual(fetch.call_args.kwargs["timezone_name"], "Europe/Berlin")


class PasswordValidatorTests(TestCase):
    """P3-1: similarity validator receives the user context."""

    def test_setup_form_rejects_password_similar_to_username(self):
        form = SetupWizardForm(
            setup_payload(
                admin_username="MaxMustermann",
                password1="MaxMustermann1!",
                password2="MaxMustermann1!",
            )
        )
        self.assertFalse(form.is_valid())
        self.assertIn("password1", form.errors)

    def test_activation_form_rejects_password_similar_to_username(self):
        station = Station.objects.create(name="Wache Pw", slug="wache-pw")
        user = User.objects.create_user("MaxMustermann", password=None)
        user.set_unusable_password()
        user.save()
        form = ActivationPasswordForm(
            {"password1": "MaxMustermann1!", "password2": "MaxMustermann1!"}, user=user
        )
        self.assertFalse(form.is_valid())
        self.assertIn("password1", form.errors)
        self.assertIn("MaxMustermann", str(user.username))
        self.assertEqual(station.name, "Wache Pw")


class ActivationRateLimitTests(TestCase):
    """P3-2: activation lookups are rate limited; expired invites are not open."""

    def setUp(self):
        cache.clear()
        RateLimit.objects.all().delete()

    @mock.patch("core.rate_limit.timezone.now")
    def test_activation_endpoint_is_rate_limited(self, mock_now):
        mock_now.return_value = datetime(2026, 10, 19, 10, 0, 30, tzinfo=dt_timezone.utc)
        client = Client()
        statuses = [
            client.get(f"/aktivieren/unbekannt-{index}/").status_code
            for index in range(61)
        ]
        self.assertEqual(statuses[:60], [410] * 60)
        self.assertEqual(statuses[60], 429)

    @mock.patch("core.rate_limit.timezone.now")
    def test_new_window_resets_counter(self, mock_now):
        mock_now.return_value = datetime(2026, 10, 19, 10, 0, 59, tzinfo=dt_timezone.utc)
        client = Client()
        for index in range(60):
            self.assertEqual(client.get(f"/aktivieren/unbekannt-{index}/").status_code, 410)
        self.assertEqual(client.get("/aktivieren/last-in-window/").status_code, 429)

        mock_now.return_value = datetime(2026, 10, 19, 10, 1, 0, tzinfo=dt_timezone.utc)
        self.assertEqual(client.get("/aktivieren/first-in-new-window/").status_code, 410)

    @mock.patch("core.rate_limit.timezone.now")
    def test_different_key_not_blocked(self, mock_now):
        mock_now.return_value = datetime(2026, 10, 19, 10, 0, 30, tzinfo=dt_timezone.utc)
        client = Client()
        for index in range(60):
            response = client.get(
                f"/aktivieren/unbekannt-{index}/", REMOTE_ADDR="192.0.2.10"
            )
            self.assertEqual(response.status_code, 410)
        self.assertEqual(
            client.get("/aktivieren/last-for-client1/", REMOTE_ADDR="192.0.2.10").status_code,
            429,
        )
        self.assertEqual(
            client.get("/aktivieren/first-for-client2/", REMOTE_ADDR="192.0.2.11").status_code,
            410,
        )

    def test_expired_activation_is_not_listed_as_open(self):
        station = Station.objects.create(name="Wache Liste", slug="wache-liste")
        user = User.objects.create_user("liste1", password=None)
        user.set_unusable_password()
        user.save()
        activation, _ = create_activation(user=user, station=station, created_by=None)
        self.assertIn(activation, list(active_activations(station)))
        activation.expires_at = timezone.now() - timedelta(seconds=1)
        activation.save(update_fields=["expires_at"])
        self.assertNotIn(activation, list(active_activations(station)))


class CanonicalOriginTests(TestCase):
    """P3-3: configured origin is used for activation URLs/QR."""

    def _request(self):
        request = mock.Mock()
        request.build_absolute_uri.side_effect = lambda path: f"http://host.test{path}"
        request.is_secure.return_value = False
        return request

    @override_settings(SITE_URL="https://wache.example")
    def test_configured_site_url_wins(self):
        from core.setup_wizard import activation_url

        url = activation_url(self._request(), SYNTH_TOKEN)
        self.assertEqual(url, f"https://wache.example/aktivieren/{SYNTH_TOKEN}/")

    @override_settings(SITE_URL="https://wache.example/")
    def test_configured_site_url_trailing_slash_is_normalized(self):
        from core.setup_wizard import activation_url

        url = activation_url(self._request(), SYNTH_TOKEN)
        self.assertEqual(url, f"https://wache.example/aktivieren/{SYNTH_TOKEN}/")

    @override_settings(SITE_URL="")
    def test_without_site_url_request_origin_is_used(self):
        from core.setup_wizard import activation_url

        url = activation_url(self._request(), SYNTH_TOKEN)
        self.assertTrue(url.startswith("http://host.test/aktivieren/"))


@override_settings(SETUP_BOOTSTRAP_TOKEN=BOOTSTRAP)
class BootstrapWhitespaceTests(TestCase):
    """P3-4: bootstrap token with surrounding whitespace works in step 2."""

    def setUp(self):
        cache.clear()

    def test_token_with_whitespace_completes_both_steps(self):
        response = self.client.post(
            reverse("setup_wizard"), {"bootstrap_token": f"  {BOOTSTRAP}  "}
        )
        self.assertEqual(response.status_code, 302)
        completed = self.client.post(reverse("setup_wizard"), setup_payload())
        self.assertEqual(completed.status_code, 302)
        self.assertEqual(Station.objects.count(), 1)


@override_settings(SETUP_BOOTSTRAP_TOKEN=BOOTSTRAP)
class WeatherEnabledWithoutPreviewTests(TestCase):
    """P3-5: enabling weather without a preview is explicit, not silently broken."""

    def setUp(self):
        cache.clear()
        self.client.post(reverse("setup_wizard"), {"bootstrap_token": BOOTSTRAP})

    def test_enabled_without_preview_is_rejected_with_hint(self):
        response = self.client.post(
            reverse("setup_wizard"), setup_payload(weather_enabled="on")
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Station.objects.count(), 0)
        body = response.content.decode("utf-8")
        self.assertIn("Wettervorschau", body)

    def test_user_can_skip_weather_and_finish(self):
        response = self.client.post(reverse("setup_wizard"), setup_payload())
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Station.objects.get().weather_enabled)


class WeatherResponseValidationTests(TestCase):
    """P3-6: malformed API payloads become WeatherUnavailable, not 500."""

    def setUp(self):
        cache.clear()

    def test_geocode_non_dict_result_is_unavailable(self):
        with mock.patch("core.weather._fetch_json", return_value={"results": [1]}):
            with self.assertRaises(weather.WeatherUnavailable):
                weather.geocode("Musterstraße 12, 49074 Osnabrück")

    def test_geocode_non_list_results_is_unavailable(self):
        with mock.patch("core.weather._fetch_json", return_value={"results": "x"}):
            with self.assertRaises(weather.WeatherUnavailable):
                weather.geocode("Musterstraße 12, 49074 Osnabrück")

    def test_forecast_empty_daily_is_unavailable(self):
        with mock.patch("core.weather._fetch_json", return_value={"daily": []}):
            with self.assertRaises(weather.WeatherUnavailable):
                weather.fetch_forecast(52.2787, 8.0479)

    def test_forecast_non_numeric_temperatures_are_unavailable(self):
        payload = forecast_payload()
        payload["daily"]["temperature_2m_max"] = "warm"
        with mock.patch("core.weather._fetch_json", return_value=payload):
            with self.assertRaises(weather.WeatherUnavailable):
                weather.fetch_forecast(52.2787, 8.0479)


class DocumentationContractTests(TestCase):
    """P3-7: docs and template match the real timeout, SSRF scope and age display."""

    def test_setup_doc_states_real_timeout_and_ssrf_scope(self):
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        text = (root / "docs" / "SETUP-WIZARD-PLAN.md").read_text(encoding="utf-8")
        self.assertIn("Timeout 3 s", text)
        self.assertNotIn("Timeout 4 s", text)
        self.assertIn("DNS-Rebinding", text)
        self.assertIn("ausdrücklich **nicht** Teil der Zusage", text)

    def test_template_shows_age_of_stale_preview(self):
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        template = (root / "templates" / "core" / "setup_wizard.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("age_minutes", template)
        self.assertIn("Alter", template)


class SetupConflictTests(TestCase):
    """P3-8: a unique-username race yields a clean conflict without leftovers."""

    def setUp(self):
        cache.clear()
        User.objects.create_user("admin-chef", password=PASSWORD)

    @override_settings(SETUP_BOOTSTRAP_TOKEN=BOOTSTRAP)
    def test_view_reports_conflict_as_409(self):
        self.client.post(reverse("setup_wizard"), {"bootstrap_token": BOOTSTRAP})
        with mock.patch(
            "core.setup_views.complete_setup",
            side_effect=SetupConflict("Benutzername bereits vergeben."),
        ):
            response = self.client.post(
                reverse("setup_wizard"), setup_payload(admin_username="admin-view")
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Station.objects.count(), 0)

    @override_settings(SETUP_BOOTSTRAP_TOKEN=BOOTSTRAP)
    def test_integrity_error_becomes_conflict_and_rolls_back(self):
        with self.assertRaises(SetupConflict):
            complete_setup(
                data={**setup_payload(), "slug": "wache-race"}, raw_token=BOOTSTRAP
            )
        self.assertEqual(Station.objects.count(), 0)
        state = InstallationSetup.objects.filter(pk=1).first()
        self.assertTrue(state is None or state.completed_at is None)
        self.assertFalse(
            Membership.objects.filter(user__username="admin-chef").exists()
        )
