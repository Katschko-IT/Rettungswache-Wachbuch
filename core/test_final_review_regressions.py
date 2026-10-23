"""Final review regressions: synthetic tokens and weather only."""

import io
import logging
from contextlib import ExitStack
from datetime import timedelta
from unittest.mock import patch
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from core import weather
from core.models import InstallationSetup
from core.setup_wizard import bootstrap_fingerprint, complete_setup
from core.test_argon_remediation import forecast_payload, setup_payload, BOOTSTRAP


class LiveForecastCalendarTests(TestCase):
    def setUp(self):
        cache.clear()

    def assert_bad_dates(self, offsets):
        payload = forecast_payload()
        today = timezone.localdate()
        payload["daily"]["time"] = [
            (today + timedelta(days=d)).isoformat() for d in offsets
        ]
        key = weather._stale_cache_key(52.0, 8.0, "Europe/Berlin")
        with patch("core.weather._fetch_json", return_value=payload):
            with self.assertRaises(weather.WeatherUnavailable):
                weather.fetch_forecast(52.0, 8.0)
        self.assertIsNone(cache.get(key))

    def test_past_live_dates_rejected(self):
        self.assert_bad_dates([-1, 0, 1, 2, 3])

    def test_gapped_live_dates_rejected(self):
        self.assert_bad_dates([0, 2, 3, 4, 5])

    def test_future_shifted_live_dates_rejected(self):
        self.assert_bad_dates([1, 2, 3, 4, 5])

    def test_invalid_live_response_preserves_good_stale_entry(self):
        payload = forecast_payload()
        with patch("core.weather._fetch_json", return_value=payload):
            original = weather.fetch_forecast(52.0, 8.0)
        cache.delete(weather._cache_key(52.0, 8.0, "Europe/Berlin"))
        payload["daily"]["time"][1] = (
            timezone.localdate() + timedelta(days=9)
        ).isoformat()
        with patch("core.weather._fetch_json", return_value=payload):
            fallback = weather.fetch_forecast(52.0, 8.0)
        self.assertTrue(fallback.stale)
        self.assertEqual(fallback.days, original.days)
        self.assertEqual(fallback.fetched_at, original.fetched_at)


class FrameworkTokenLogTests(TestCase):
    def test_django_410_console_does_not_leak_activation_token(self):
        token = "SYNTHETIC-final-review-token-not-a-credential"
        stream = io.StringIO()
        logger = logging.getLogger("django.request")
        handlers = list(logger.handlers)
        self.assertTrue(handlers)
        with ExitStack() as stack:
            for handler in handlers:
                stack.enter_context(patch.object(handler, "stream", stream))
            response = self.client.get("/aktivieren/" + token + "/")
        self.assertEqual(response.status_code, 410)
        output = stream.getvalue()
        self.assertIn("[redacted]", output)
        self.assertNotIn(token, output)

    def test_configured_console_redacts_formatted_and_mapping_messages(self):
        token = "SYNTHETIC-final-review-token-not-a-credential"
        logger = logging.getLogger("django.request")
        stream = io.StringIO()
        with ExitStack() as stack:
            for handler in logger.handlers:
                stack.enter_context(patch.object(handler, "stream", stream))
            logger.warning("Not Found: %s", "/aktivieren/" + token)
            logger.warning("Path: %(path)s", {"path": "/aktivieren/" + token + "/"})
        self.assertNotIn(token, stream.getvalue())
        self.assertIn("[redacted]", stream.getvalue())


class DirectBootstrapNormalizationTests(TestCase):
    @override_settings(SETUP_BOOTSTRAP_TOKEN=BOOTSTRAP)
    def test_direct_setup_normalizes_before_hashing(self):
        complete_setup(
            data={**setup_payload(), "slug": "final-review-station"},
            raw_token=" " + BOOTSTRAP + " ",
        )
        self.assertEqual(
            InstallationSetup.objects.get(pk=1).bootstrap_fingerprint,
            bootstrap_fingerprint(BOOTSTRAP),
        )
