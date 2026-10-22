"""Tests for navbar monitor button removal, multi-state holidays, and weather module in settings."""

from datetime import date
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from core.forms import StationSettingsForm
from core.holidays import (
    GERMAN_STATES,
    Holiday,
    holidays_between,
    holidays_for_year,
    normalize_state,
    nrw_holidays_for_year,
    station_agenda,
)
from core.models import AuditEvent, Membership, Station, User
from core.weather import WeatherUnavailable


class NavMonitorButtonRemovalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password123")
        self.station = Station.objects.create(name="Wache 1", slug="wache-1")
        self.membership = Membership.objects.create(
            user=self.user,
            station=self.station,
            role=Membership.Role.ADMIN,
            is_active=True,
        )
        self.client.force_login(self.user)

    def test_navbar_does_not_contain_monitor_display_button(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'class="nav-display-toggle"')
        self.assertNotContains(response, "data-display-open")


class GermanStateHolidaysTests(TestCase):
    def test_all_16_states_covered(self):
        self.assertEqual(len(GERMAN_STATES), 16)
        for code in GERMAN_STATES:
            holidays = holidays_for_year(2026, state=code)
            self.assertGreaterEqual(len(holidays), 9)
            titles = {h.title for h in holidays}
            # Common nationwide holidays
            self.assertIn("Neujahr", titles)
            self.assertIn("Karfreitag", titles)
            self.assertIn("Ostermontag", titles)
            self.assertIn("Tag der Arbeit", titles)
            self.assertIn("Christi Himmelfahrt", titles)
            self.assertIn("Pfingstmontag", titles)
            self.assertIn("Tag der Deutschen Einheit", titles)
            self.assertIn("1. Weihnachtstag", titles)
            self.assertIn("2. Weihnachtstag", titles)

    def test_nrw_backwards_compatibility(self):
        nrw_direct = nrw_holidays_for_year(2026)
        nrw_via_all = holidays_for_year(2026, state="NW")
        nrw_via_alias = holidays_for_year(2026, state="NRW")
        self.assertEqual(nrw_direct, nrw_via_all)
        self.assertEqual(nrw_direct, nrw_via_alias)
        titles = {h.title: h.day for h in nrw_direct}
        self.assertIn("Fronleichnam", titles)
        self.assertIn("Allerheiligen", titles)
        self.assertNotIn("Buß- und Bettag", titles)
        self.assertNotIn("Heilige Drei Könige", titles)

    def test_state_specific_holidays(self):
        # Sachsen has Buß- und Bettag
        sn_titles = {h.title: h.day for h in holidays_for_year(2026, state="SN")}
        self.assertIn("Buß- und Bettag", sn_titles)
        self.assertEqual(sn_titles["Buß- und Bettag"], date(2026, 11, 18))
        self.assertIn("Reformationstag", sn_titles)

        # Bayern has Heilige Drei Könige, Mariä Himmelfahrt, Fronleichnam, Allerheiligen
        by_titles = {h.title for h in holidays_for_year(2026, state="BY")}
        self.assertIn("Heilige Drei Könige", by_titles)
        self.assertIn("Mariä Himmelfahrt", by_titles)
        self.assertIn("Fronleichnam", by_titles)
        self.assertIn("Allerheiligen", by_titles)

        # Berlin has Internationaler Frauentag
        be_titles = {h.title for h in holidays_for_year(2026, state="BE")}
        self.assertIn("Internationaler Frauentag", be_titles)
        self.assertNotIn("Fronleichnam", be_titles)

        # Thüringen has Weltkindertag
        th_titles = {h.title for h in holidays_for_year(2026, state="TH")}
        self.assertIn("Weltkindertag", th_titles)
        self.assertIn("Reformationstag", th_titles)

        # Brandenburg has Ostersonntag and Pfingstsonntag
        bb_titles = {h.title for h in holidays_for_year(2026, state="BB")}
        self.assertIn("Ostersonntag", bb_titles)
        self.assertIn("Pfingstsonntag", bb_titles)

    def test_station_agenda_uses_station_holiday_state(self):
        station_by = Station.objects.create(name="Wache Bayern", slug="wache-by", holiday_state="BY")
        agenda_by = station_agenda(station_by, [], past_days=1, future_days=366)
        holiday_entries = [e for e in agenda_by if e.kind == "holiday"]
        titles_by = {e.title for e in holiday_entries}
        self.assertIn("Heilige Drei Könige", titles_by)
        self.assertTrue(all("Bayern" in e.description for e in holiday_entries))

        station_sn = Station.objects.create(name="Wache Sachsen", slug="wache-sn", holiday_state="SN")
        agenda_sn = station_agenda(station_sn, [], past_days=1, future_days=366)
        holiday_entries_sn = [e for e in agenda_sn if e.kind == "holiday"]
        titles_sn = {e.title for e in holiday_entries_sn}
        self.assertIn("Buß- und Bettag", titles_sn)
        self.assertTrue(all("Sachsen" in e.description for e in holiday_entries_sn))


class StationSettingsHolidaysAndWeatherTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="adminuser", password="password123")
        self.station = Station.objects.create(
            name="Wache Alpha",
            slug="wache-alpha",
            holiday_state="NW",
            weather_enabled=False,
        )
        self.membership = Membership.objects.create(
            user=self.user,
            station=self.station,
            role=Membership.Role.ADMIN,
            is_active=True,
        )
        self.client.force_login(self.user)

    def test_settings_can_change_holiday_state(self):
        response = self.client.post(reverse("station_settings"), {
            "name": "Wache Alpha",
            "organization_profile": "rescue",
            "holidays_enabled": "on",
            "holiday_state": "BY",
        })
        self.assertRedirects(response, reverse("station_settings"))
        self.station.refresh_from_db()
        self.assertEqual(self.station.holiday_state, "BY")
        self.assertTrue(self.station.holidays_enabled)

    def test_weather_enabled_requires_address(self):
        response = self.client.post(reverse("station_settings"), {
            "name": "Wache Alpha",
            "organization_profile": "rescue",
            "weather_enabled": "on",
            "street": "",
            "postal_code": "",
            "city": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "city", "Für die Wettervorhersage wird mindestens ein Ort oder eine Anschrift benötigt.")

    @mock.patch("core.weather.geocode")
    def test_weather_enabled_geocodes_address_and_saves_coordinates(self, mock_geocode):
        mock_geocode.return_value = {
            "latitude": 52.0432,
            "longitude": 8.4167,
            "label": "Steinhagen, Nordrhein-Westfalen, Deutschland",
        }
        response = self.client.post(reverse("station_settings"), {
            "name": "Wache Alpha",
            "organization_profile": "rescue",
            "weather_enabled": "on",
            "street": "Am Sportzentrum 1",
            "postal_code": "33803",
            "city": "Steinhagen",
        })
        self.assertRedirects(response, reverse("station_settings"))
        self.station.refresh_from_db()
        self.assertTrue(self.station.weather_enabled)
        self.assertEqual(self.station.street, "Am Sportzentrum 1")
        self.assertEqual(self.station.postal_code, "33803")
        self.assertEqual(self.station.city, "Steinhagen")
        self.assertAlmostEqual(self.station.latitude, 52.0432)
        self.assertAlmostEqual(self.station.longitude, 8.4167)
        mock_geocode.assert_called_once_with("Am Sportzentrum 1, 33803 Steinhagen")

    @mock.patch("core.weather.geocode")
    def test_weather_geocode_failure_shows_error(self, mock_geocode):
        mock_geocode.side_effect = WeatherUnavailable("Adresse konnte nicht gefunden werden.")
        response = self.client.post(reverse("station_settings"), {
            "name": "Wache Alpha",
            "organization_profile": "rescue",
            "weather_enabled": "on",
            "street": "Fantasieweg 999",
            "postal_code": "99999",
            "city": "Nirgendwo",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("weather_enabled", response.context["form"].errors)
        self.station.refresh_from_db()
        self.assertFalse(self.station.weather_enabled)

    @mock.patch("core.weather.geocode")
    def test_weather_unchanged_address_does_not_regeocode(self, mock_geocode):
        self.station.street = "Musterstr. 5"
        self.station.postal_code = "12345"
        self.station.city = "Musterstadt"
        self.station.latitude = 50.1234
        self.station.longitude = 8.5678
        self.station.weather_enabled = True
        self.station.save()

        response = self.client.post(reverse("station_settings"), {
            "name": "Wache Alpha",
            "organization_profile": "rescue",
            "weather_enabled": "on",
            "street": "Musterstr. 5",
            "postal_code": "12345",
            "city": "Musterstadt",
        })
        self.assertRedirects(response, reverse("station_settings"))
        mock_geocode.assert_not_called()
        self.station.refresh_from_db()
        self.assertEqual(self.station.latitude, 50.1234)

    def test_weather_disabled_saves_without_geocoding(self):
        response = self.client.post(reverse("station_settings"), {
            "name": "Wache Alpha",
            "organization_profile": "rescue",
            "street": "Hauptstr. 10",
            "city": "Berlin",
            # weather_enabled is omitted (off)
        })
        self.assertRedirects(response, reverse("station_settings"))
        self.station.refresh_from_db()
        self.assertFalse(self.station.weather_enabled)
        self.assertEqual(self.station.street, "Hauptstr. 10")
        self.assertEqual(self.station.city, "Berlin")

    def test_station_settings_saves_cleanly_with_fictional_test_address(self):
        response = self.client.post(reverse("station_settings"), {
            "name": "Wache Alpha",
            "organization_profile": "rescue",
            "weather_enabled": "on",
            "street": "Musterstraße 12",
            "postal_code": "12345",
            "city": "Musterstadt",
        })
        self.assertRedirects(response, reverse("station_settings"))
        self.station.refresh_from_db()
        self.assertTrue(self.station.weather_enabled)
        self.assertIsNotNone(self.station.latitude)
        self.assertIsNotNone(self.station.longitude)


class CombinedGeocodingTests(TestCase):
    def test_candidate_extraction_hierarchical(self):
        from core.weather import _extract_candidates

        candidates = _extract_candidates("Florianstraße 12, 49074 Osnabrück")
        self.assertIn("Florianstraße 12, 49074 Osnabrück", candidates)
        self.assertIn("49074 Osnabrück", candidates)
        self.assertIn("Osnabrück", candidates)

        candidates_comma = _extract_candidates("Hauptstraße 1, Hamburg")
        self.assertIn("Hauptstraße 1, Hamburg", candidates_comma)
        self.assertIn("Hamburg", candidates_comma)

    @mock.patch("core.weather._fetch_json")
    def test_osm_geocoding_resolves_street_address(self, mock_fetch):
        mock_fetch.return_value = [
            {
                "lat": "52.5215",
                "lon": "13.4124",
                "display_name": "Alexanderplatz 1, Berlin",
            }
        ]
        from core.weather import geocode

        result = geocode("Alexanderplatz 1, 10178 Berlin")
        self.assertEqual(result["latitude"], 52.5215)
        self.assertEqual(result["longitude"], 13.4124)
        self.assertIn("Alexanderplatz", result["label"])

    @mock.patch("core.weather._fetch_json")
    def test_osm_failure_cascades_to_open_meteo(self, mock_fetch):
        # First call (OSM) returns empty list, second call (Open-Meteo) returns results dict
        def side_effect(url, params):
            if "nominatim" in url:
                return []
            if "open-meteo" in url:
                return {
                    "results": [
                        {
                            "latitude": 52.2726,
                            "longitude": 8.0498,
                            "name": "Osnabrück",
                            "admin1": "Niedersachsen",
                            "country": "Deutschland",
                        }
                    ]
                }
            raise WeatherUnavailable("Unexpected URL")

        mock_fetch.side_effect = side_effect
        from core.weather import geocode

        result = geocode("Fantasieweg 999, 49074 Osnabrück")
        self.assertEqual(result["latitude"], 52.2726)
        self.assertEqual(result["longitude"], 8.0498)
        self.assertIn("Osnabrück", result["label"])

    def test_short_city_name_is_not_rejected(self):
        from core.weather import geocode

        result = geocode("Köln")
        self.assertAlmostEqual(result["latitude"], 50.9384, places=1)
        self.assertAlmostEqual(result["longitude"], 6.96, places=1)

    def test_fictional_address_uses_fallback_coordinates(self):
        from core.weather import geocode

        # 12345 matches Berlin PLZ prefix -> falls back to Berlin coordinates
        result = geocode("Musterstraße 12, 12345 Musterstadt")
        self.assertEqual(result["latitude"], 52.52)
        self.assertEqual(result["longitude"], 13.405)
        self.assertIn("Standardkoordinaten", result["label"])

