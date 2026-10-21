"""DWD-Warnungen (Bright Sky): Parser, Konfiguration und Sicherheitsgrenzen."""

from __future__ import annotations

from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from core import alerts, traffic
from core.forms import StationSettingsForm
from core.models import Station

SAMPLE = {
    "alerts": [
        {
            "headline_de": "Amtliche WARNUNG vor FROST",
            "severity": "Minor",
            "onset": "2026-10-22T04:00:00+02:00",
            "expires": "2026-10-22T09:00:00+02:00",
        },
        {
            "headline_de": "Amtliche UNWETTERWARNUNG vor STURMBÖEN",
            "severity": "Severe",
            "onset": "2026-10-21T18:00:00+02:00",
            "expires": "2026-10-22T02:00:00+02:00",
        },
        {"severity": "Minor"},
        "kaputt",
    ],
    "location": {"lat": 52.02},
}


class ParserTests(TestCase):
    def test_sorted_by_severity_and_dates_trimmed(self):
        with mock.patch("core.alerts._fetch_json", return_value=SAMPLE) as fetch:
            result = alerts.fetch_dwd_alerts(52.0234, 8.4251)
        self.assertIn("lat=52.02&lon=8.43", fetch.call_args[0][0])
        self.assertEqual([a["severity"] for a in result], ["severe", "minor"])
        self.assertEqual(result[0]["starts_at"], "2026-10-21")
        self.assertEqual(result[0]["ends_at"], "2026-10-22")

    def test_unexpected_format_raises(self):
        with mock.patch("core.alerts._fetch_json", return_value={"alerts": "x"}):
            with self.assertRaises(traffic.TrafficUnavailable):
                alerts.fetch_dwd_alerts(52.0, 8.0)

    def test_host_is_allowlisted_https_only(self):
        self.assertIn("api.brightsky.dev", traffic.ALLOWED_HOSTS)
        with self.assertRaises(traffic.TrafficUnavailable):
            traffic._guarded_request("http://api.brightsky.dev/alerts", accept="application/json")
        with self.assertRaises(traffic.TrafficUnavailable):
            traffic._guarded_request("https://evil.example/alerts", accept="application/json")


class PayloadTests(TestCase):
    def setUp(self):
        cache.clear()

    def _station(self, **kw):
        d = dict(name="W", slug="w-alerts", latitude=52.02, longitude=8.42, dwd_alerts_enabled=True)
        d.update(kw)
        return Station.objects.create(**d)

    def test_disabled_makes_no_request(self):
        with mock.patch("core.alerts._fetch_json") as fetch:
            self.assertEqual(alerts.alerts_payload(self._station(dwd_alerts_enabled=False))["items"], [])
            self.assertEqual(alerts.alerts_payload(self._station(slug="w2", latitude=None, longitude=None))["items"], [])
        fetch.assert_not_called()

    def test_failure_is_flagged_not_raised(self):
        with mock.patch("core.alerts._fetch_json", side_effect=traffic.TrafficUnavailable("x")):
            payload = alerts.alerts_payload(self._station())
        self.assertTrue(payload["failed"])
        self.assertEqual(payload["items"], [])

    def test_payload_is_cached(self):
        station = self._station()
        with mock.patch("core.alerts._fetch_json", return_value=SAMPLE) as fetch:
            alerts.alerts_payload(station)
            alerts.alerts_payload(station)
        self.assertEqual(fetch.call_count, 1)


class FormTests(TestCase):
    def _form(self, **data):
        station = Station.objects.create(name="F", slug="f-alerts")
        base = {"name": "F", "organization_profile": station.organization_profile}
        base.update(data)
        return StationSettingsForm(base, instance=station)

    def test_requires_coordinates(self):
        form = self._form(dwd_alerts_enabled="on")
        self.assertFalse(form.is_valid())
        self.assertIn("dwd_alerts_enabled", form.errors)

    def test_valid_with_coordinates(self):
        form = self._form(dwd_alerts_enabled="on", latitude="52.0", longitude="8.4")
        self.assertTrue(form.is_valid(), form.errors)
