"""Tests für die Verkehrs- und Baustellenlage.

Die Parser-Tests laufen ohne Netz. Die Quellen-Tests ersetzen die HTTP-Aufrufe
durch feste Antworten, damit weder Autobahn GmbH noch Kommunen im Test
angesprochen werden.
"""

from __future__ import annotations

from datetime import date
from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from core import traffic
from core.models import Station


class AutobahnPeriodTests(TestCase):
    def test_reads_phase_with_explicit_start_and_end(self):
        description = [
            "Zeitraum dieser Bauphase: Beginn: 19.10.26 um 20:00 Uhr",
            "Ende: 30.10.26 um 19:00 Uhr (Ende der Gesamtmaßnahme: 30.10.26)",
        ]
        start, end = traffic.parse_autobahn_period(description)
        self.assertEqual(start, date(2026, 10, 19))
        self.assertEqual(end, date(2026, 10, 30))

    def test_reads_single_day_with_time_window(self):
        start, end = traffic.parse_autobahn_period(
            ["Die Baustelle ist zu folgenden Zeiträumen gültig:", "20.10.26 von 10:00 bis 13:00 Uhr"]
        )
        self.assertEqual(start, date(2026, 10, 20))
        self.assertEqual(end, date(2026, 10, 20))

    def test_reads_window_across_midnight(self):
        start, end = traffic.parse_autobahn_period(
            ["20.10.26 19:00 bis 05:00 Uhr."]
        )
        self.assertEqual(start, date(2026, 10, 20))
        self.assertEqual(end, date(2026, 10, 21))

    def test_reads_range_with_explicit_end_date(self):
        start, end = traffic.parse_autobahn_period(
            ["20.10.26 19:00 bis zum 21.10.26 05:00 Uhr."]
        )
        self.assertEqual(start, date(2026, 10, 20))
        self.assertEqual(end, date(2026, 10, 21))

    def test_returns_none_without_dates(self):
        self.assertEqual(traffic.parse_autobahn_period(["Keine Angabe"]), (None, None))
        self.assertEqual(traffic.parse_autobahn_period(None), (None, None))


class GermanPeriodTests(TestCase):
    def test_reads_range_without_start_year(self):
        start, end = traffic.parse_german_period(
            "Aufgrund von Straßenbauarbeiten vom 21.10. bis zum 03.11.2026 zu Einschränkungen."
        )
        self.assertEqual(start, date(2026, 10, 21))
        self.assertEqual(end, date(2026, 11, 3))

    def test_handles_turn_of_the_year(self):
        start, end = traffic.parse_german_period("vom 28.12. bis zum 05.01.2026")
        self.assertEqual(end, date(2026, 1, 5))
        self.assertEqual(start, date(2025, 12, 28))

    def test_reads_weekday_formulation(self):
        start, end = traffic.parse_german_period(
            "vom 27.10. bis einschließlich Freitag dem 30.10.2026 nicht anfahrbar"
        )
        self.assertEqual(start, date(2026, 10, 27))
        self.assertEqual(end, date(2026, 10, 30))

    def test_returns_none_without_range(self):
        self.assertEqual(traffic.parse_german_period("Kein Datum vorhanden"), (None, None))


class ClosureDetectionTests(TestCase):
    def test_detects_closed_wording(self):
        self.assertTrue(traffic.looks_closed("Die Straße wird voll gesperrt."))
        self.assertTrue(traffic.looks_closed("Grundstücke sind nicht anfahrbar."))
        self.assertTrue(traffic.looks_closed("Vollsperrung beider Richtungen"))

    def test_does_not_invent_closures(self):
        self.assertFalse(traffic.looks_closed("Es kommt zu Einschränkungen."))
        self.assertFalse(traffic.looks_closed("Asphaltierungsarbeiten laufen."))


class DistanceTests(TestCase):
    def test_distance_between_steinhagen_and_bielefeld(self):
        # Steinhagen (52.02, 8.42) nach Bielefeld-Mitte (52.03, 8.53) sind
        # rund sieben Kilometer Luftlinie.
        distance = traffic.distance_km(52.02, 8.42, 52.03, 8.53)
        self.assertGreater(distance, 6.0)
        self.assertLess(distance, 9.0)

    def test_same_point_is_zero(self):
        self.assertAlmostEqual(traffic.distance_km(52.02, 8.42, 52.02, 8.42), 0.0)


AUTOBAHN_ANSWER = {
    "roadworks": [
        {
            "title": "A2 | Bielefeld - Bielefeld-Ost",
            "point": "52.04,8.55",
            "isBlocked": "false",
            "impact": {
                "lower": "Bielefeld",
                "upper": "Bielefeld-Ost",
                "symbols": ["CLOSED", "ARROW_UP"],
            },
            "description": [
                "Zeitraum dieser Bauphase: Beginn: 19.10.26 um 20:00 Uhr",
                "Ende: 30.10.26 um 19:00 Uhr",
            ],
        },
        {
            "title": "A2 | Weiter weg",
            "point": "51.10,6.80",
            "isBlocked": "false",
            "impact": {"lower": "X", "upper": "Y", "symbols": []},
            "description": ["20.10.26 von 10:00 bis 13:00 Uhr"],
        },
    ]
}


class AutobahnSourceTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_filters_by_radius_and_maps_fields(self):
        with mock.patch("core.traffic._fetch_json", return_value=AUTOBAHN_ANSWER):
            items = traffic.fetch_autobahn((52.02, 8.42), roads=("A2",), radius_km=25)
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.title, "A2 | Bielefeld - Bielefeld-Ost")
        self.assertEqual(item.section, "Bielefeld – Bielefeld-Ost")
        self.assertTrue(item.restricted)
        self.assertFalse(item.closed)
        self.assertEqual(item.starts_at, date(2026, 10, 19))
        self.assertLess(item.distance_km, 25)

    def test_full_closure_only_from_isblocked(self):
        answer = {
            "closure": [
                {
                    "title": "A2 | Vollsperrung",
                    "point": "52.04,8.55",
                    "isBlocked": "true",
                    "impact": {"lower": "A", "upper": "B", "symbols": ["CLOSED"]},
                    "description": ["20.10.26 19:00 bis zum 21.10.26 05:00 Uhr."],
                }
            ]
        }
        with mock.patch("core.traffic._fetch_json", return_value=answer):
            items = traffic.fetch_autobahn((52.02, 8.42), roads=("A2",))
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0].closed)

    def test_source_failure_yields_empty_list(self):
        with mock.patch(
            "core.traffic._fetch_json",
            side_effect=traffic.TrafficUnavailable("offline"),
        ):
            self.assertEqual(traffic.fetch_autobahn((52.02, 8.42)), [])


STEINHAGEN_HTML = """
<html><body>
<div class="id-content-first-column id-content">
  <h3 class="paragraph h2">Straßenbauarbeiten Kuhweg</h3>
  <p class="paragraph">Aufgrund von Straßenbauarbeiten wird es im Kuhweg vom
  21.10. bis zum 03.11.2026 zu Einschränkungen kommen. Die Grundstücke sind
  in dieser Zeit nicht anfahrbar.</p>
  <h3 class="paragraph h2">Hilfe zur Barrierefreiheit</h3>
  <p class="paragraph">Allgemein sind wir bemüht.</p>
</div>
<div class="footer">Soziale</div>
</body></html>
"""


class SteinhagenSourceTests(TestCase):
    def test_parses_period_and_closure_wording(self):
        with mock.patch("core.traffic._fetch_html", return_value=STEINHAGEN_HTML):
            items = traffic.fetch_steinhagen()
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.source, "Gemeinde Steinhagen")
        self.assertEqual(item.starts_at, date(2026, 10, 21))
        self.assertEqual(item.ends_at, date(2026, 11, 3))
        self.assertTrue(item.closed)
        self.assertNotIn("Barrierefreiheit", item.title)

    def test_drops_items_without_period_or_closure(self):
        html = """
        <div class="id-content-first-column id-content">
          <h3>Nur ein Hinweis</h3>
          <p>Ohne Datum und ohne Sperre.</p>
        </div>
        """
        with mock.patch("core.traffic._fetch_html", return_value=html):
            self.assertEqual(traffic.fetch_steinhagen(), [])


KREIS_HTML = """
<html><body>
<h2 class="image-with-text__headline">Ausbau der K 1 Hauptstraße, in Rheda-Wiedenbrück</h2>
<p>Die Arbeiten laufen seit April.</p>
<h2 class="image-with-text__headline">Öffnungszeiten</h2>
<p>Montag bis Freitag.</p>
</body></html>
"""


class KreisSourceTests(TestCase):
    def test_keeps_only_building_sections(self):
        with mock.patch("core.traffic._fetch_html", return_value=KREIS_HTML):
            items = traffic.fetch_kreis_guetersloh()
        self.assertEqual(len(items), 1)
        self.assertIn("K 1", items[0].title)
        self.assertEqual(items[0].source, "Kreis Gütersloh")


class TrafficPayloadTests(TestCase):
    def setUp(self):
        cache.clear()
        self.station = Station.objects.create(
            name="Steinhagen Rettungsdienst",
            slug="steinhagen-traffic",
            latitude=52.02,
            longitude=8.42,
        )

    def test_merges_sources_and_marks_closed_first(self):
        closed = traffic.TrafficItem(
            source="Gemeinde Steinhagen",
            title="Vollsperrung Kuhweg",
            closed=True,
            distance_km=3.0,
        )
        open_item = traffic.TrafficItem(
            source="Autobahn A2",
            title="Baustelle A2",
            distance_km=1.0,
        )
        with mock.patch("core.traffic.fetch_autobahn", return_value=[open_item]), \
             mock.patch("core.traffic.fetch_steinhagen", return_value=[closed]), \
             mock.patch("core.traffic.fetch_kreis_guetersloh", return_value=[]), \
             mock.patch("core.traffic.fetch_nina_warnings", return_value=[]):
            payload = traffic.traffic_payload(self.station)
        self.assertEqual([item["title"] for item in payload["items"]],
                         ["Vollsperrung Kuhweg", "Baustelle A2"])
        self.assertEqual(payload["total"], 2)

    def test_failing_source_does_not_break_payload(self):
        with mock.patch(
            "core.traffic.fetch_autobahn",
            side_effect=traffic.TrafficUnavailable("offline"),
        ), mock.patch("core.traffic.fetch_steinhagen", return_value=[]), \
           mock.patch("core.traffic.fetch_kreis_guetersloh", return_value=[]), \
           mock.patch("core.traffic.fetch_nina_warnings", return_value=[]):
            payload = traffic.traffic_payload(self.station)
        self.assertEqual(payload["items"], [])
        self.assertEqual(payload["sources"], [])

    def test_payload_is_cached(self):
        with mock.patch("core.traffic.fetch_autobahn", return_value=[]) as autobahn, \
             mock.patch("core.traffic.fetch_steinhagen", return_value=[]), \
             mock.patch("core.traffic.fetch_kreis_guetersloh", return_value=[]), \
             mock.patch("core.traffic.fetch_nina_warnings", return_value=[]):
            traffic.traffic_payload(self.station)
            traffic.traffic_payload(self.station)
        self.assertEqual(autobahn.call_count, 1)
