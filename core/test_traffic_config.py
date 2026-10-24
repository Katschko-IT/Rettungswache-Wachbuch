"""Verkehrslage je Wache: Konfiguration, Cache, Filter, Formulare, Wizard, Migration.

Bis 0.24.0 war die Verkehrslage fest auf Gütersloh/Steinhagen verdrahtet
(A2/A33, feste NINA-Gebiete, Standort-Fallback, kommunale Quellen für alle).
Diese Tests sichern ab, dass keine dieser festen Werte mehr greift und dass
bestehende Wachen per Datenmigration ihr bisheriges Verhalten behalten.
Alle externen Abrufe sind ersetzt; kein Test spricht das Netz an.
"""

from __future__ import annotations

from unittest import mock

from django.core.cache import cache
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from core import traffic
from core.forms import SetupWizardForm, StationSettingsForm
from core.models import Membership, Station, User
from core.test_setup_wizard import BOOTSTRAP, setup_payload


def _no_sources():
    """Patches für alle Quellen; die Mocks werden zurückgegeben."""
    return (
        mock.patch("core.traffic.fetch_autobahn", return_value=[]),
        mock.patch("core.traffic.fetch_steinhagen", return_value=[]),
        mock.patch("core.traffic.fetch_kreis_guetersloh", return_value=[]),
        mock.patch("core.traffic._guarded_request_nina", return_value=[]),
    )


class RoadAndAreaParsingTests(TestCase):
    def test_roads_are_normalised_and_deduplicated(self):
        self.assertEqual(traffic.parse_roads(" a2, A33;b61  A2 "), ("A2", "A33", "B61"))
        self.assertEqual(traffic.parse_roads(""), ())
        self.assertEqual(traffic.parse_roads(None), ())

    def test_roads_reject_anything_that_could_alter_the_url(self):
        for bad in ("A2/../x", "C5", "A1234", "A", "A2?x=1", "L 782", "https://evil"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                traffic.parse_roads(bad)

    def test_at_most_six_roads(self):
        self.assertEqual(len(traffic.parse_roads("A1,A2,A3,A4,A5,A6")), 6)
        with self.assertRaises(ValueError):
            traffic.parse_roads("A1,A2,A3,A4,A5,A6,A7")

    def test_areas_are_trimmed_deduplicated_and_capped(self):
        self.assertEqual(
            traffic.parse_areas(" Gütersloh ,gütersloh,  Kreis   Gütersloh,,"),
            ("Gütersloh", "Kreis Gütersloh"),
        )
        many = ",".join(f"Ort{i}" for i in range(12))
        self.assertEqual(len(traffic.parse_areas(many)), traffic.MAX_WARNING_AREAS)

    def test_warning_areas_fall_back_to_station_city_only(self):
        self.assertEqual(
            traffic.warning_areas_for(Station(traffic_warning_areas="Bielefeld", city="Steinhagen")),
            ("Bielefeld",),
        )
        self.assertEqual(traffic.warning_areas_for(Station(city="Osnabrück")), ("Osnabrück",))
        self.assertEqual(traffic.warning_areas_for(Station()), ())

    def test_no_hardwired_region_left(self):
        self.assertFalse(hasattr(traffic, "DEFAULT_ROADS"))
        self.assertFalse(hasattr(traffic, "NINA_AREAS"))
        self.assertIsNone(traffic._origin(Station()))


class TrafficConfigurationTests(TestCase):
    def setUp(self):
        cache.clear()

    def _station(self, **kwargs):
        data = {"name": "Wache", "slug": f"wache-{Station.objects.count()}", "traffic_enabled": True}
        data.update(kwargs)
        return Station.objects.create(**data)

    def test_new_station_starts_empty_and_contacts_no_source(self):
        station = self._station()
        self.assertEqual(station.traffic_roads, "")
        self.assertEqual(station.traffic_warning_areas, "")
        self.assertFalse(station.traffic_local_sources)
        autobahn, steinhagen, kreis, nina = _no_sources()
        with autobahn as a, steinhagen as s, kreis as k, nina as n:
            payload = traffic.traffic_payload(station)
        a.assert_not_called()
        s.assert_not_called()
        k.assert_not_called()
        n.assert_not_called()
        self.assertEqual(payload["items"], [])
        self.assertEqual(payload["warnings"], [])
        self.assertEqual(payload["failed_sources"], [])

    def test_roads_without_coordinates_skip_autobahn(self):
        station = self._station(traffic_roads="A2")
        autobahn, steinhagen, kreis, nina = _no_sources()
        with autobahn as a, steinhagen, kreis, nina:
            traffic.traffic_payload(station)
        a.assert_not_called()

    def test_configured_roads_radius_and_origin_are_used(self):
        station = self._station(
            traffic_roads="A1, A30", traffic_radius_km=40, latitude=52.27, longitude=8.05
        )
        autobahn, steinhagen, kreis, nina = _no_sources()
        with autobahn as a, steinhagen as s, kreis as k, nina:
            payload = traffic.traffic_payload(station)
        a.assert_called_once_with((52.27, 8.05), roads=("A1", "A30"), radius_km=40.0)
        s.assert_not_called()
        k.assert_not_called()
        self.assertEqual(payload["sources"], [])

    def test_local_sources_only_when_enabled_per_station(self):
        station = self._station(traffic_local_sources=True)
        autobahn, steinhagen, kreis, nina = _no_sources()
        with autobahn as a, steinhagen as s, kreis as k, nina:
            traffic.traffic_payload(station)
        a.assert_not_called()
        s.assert_called_once()
        k.assert_called_once()

    def test_invalid_stored_roads_are_ignored(self):
        station = self._station(latitude=52.0, longitude=8.0)
        Station.objects.filter(pk=station.pk).update(traffic_roads="A2/../evil")
        station.refresh_from_db()
        autobahn, steinhagen, kreis, nina = _no_sources()
        with autobahn as a, steinhagen, kreis, nina:
            traffic.traffic_payload(station)
        a.assert_not_called()

    def test_fetch_autobahn_skips_roads_outside_the_pattern(self):
        with mock.patch("core.traffic._fetch_json", return_value={}) as fetch:
            traffic.fetch_autobahn((52.0, 8.0), roads=("A2", "../x"))
        urls = [call.args[0] for call in fetch.call_args_list]
        self.assertTrue(urls)
        self.assertTrue(all("/A2/" in url for url in urls))

    def test_failed_sources_are_reported(self):
        station = self._station(traffic_local_sources=True)
        with mock.patch("core.traffic.fetch_steinhagen", side_effect=traffic.TrafficUnavailable("x")), \
             mock.patch("core.traffic.fetch_kreis_guetersloh", return_value=[]), \
             mock.patch("core.traffic._guarded_request_nina", return_value=[]):
            payload = traffic.traffic_payload(station)
        self.assertEqual(payload["failed_sources"], ["Gemeinde Steinhagen"])

    def test_updated_at_is_timezone_aware(self):
        payload = traffic.traffic_payload(self._station())
        self.assertRegex(payload["updated_at"], r"[+-]\d{2}:\d{2}$")


class TrafficCacheTests(TestCase):
    def setUp(self):
        cache.clear()
        self.station = Station.objects.create(
            name="Cache", slug="cache-traffic", traffic_enabled=True,
            traffic_roads="A2", latitude=52.0, longitude=8.4,
        )

    def test_same_configuration_is_cached(self):
        autobahn, steinhagen, kreis, nina = _no_sources()
        with autobahn as a, steinhagen, kreis, nina:
            traffic.traffic_payload(self.station)
            traffic.traffic_payload(self.station)
        self.assertEqual(a.call_count, 1)

    def test_configuration_change_takes_effect_immediately(self):
        autobahn, steinhagen, kreis, nina = _no_sources()
        with autobahn as a, steinhagen as s, kreis, nina:
            traffic.traffic_payload(self.station)
            for field, value in (
                ("traffic_roads", "A2, A33"),
                ("traffic_radius_km", 50),
                ("latitude", 52.1),
                ("traffic_local_sources", True),
            ):
                setattr(self.station, field, value)
                traffic.traffic_payload(self.station)
        self.assertEqual(a.call_count, 5)
        s.assert_called_once()

    def test_warning_areas_are_part_of_the_cache_key(self):
        autobahn, steinhagen, kreis, nina = _no_sources()
        with autobahn, steinhagen, kreis, nina as n:
            self.station.traffic_warning_areas = "Bielefeld"
            traffic.traffic_payload(self.station)
            self.station.traffic_warning_areas = "Herford"
            traffic.traffic_payload(self.station)
        self.assertEqual(n.call_count, 2)


NINA_SAMPLE = [
    {"title": "Hochwasser Bielefeld", "regionName": "Stadt Bielefeld", "severity": "Severe"},
    {"title": "Ohne Gebiet", "severity": "Minor"},
    {"title": "Unwetter Kreis Gütersloh", "areaName": "KREIS GÜTERSLOH"},
    {"title": "Fern", "regionName": "München"},
    "kaputt",
]


class NinaFilterTests(TestCase):
    def test_without_areas_nothing_is_requested(self):
        with mock.patch("core.traffic._guarded_request_nina") as request:
            self.assertEqual(traffic.fetch_nina_warnings(()), [])
        request.assert_not_called()

    def test_filters_case_insensitive_and_drops_entries_without_area(self):
        with mock.patch("core.traffic._guarded_request_nina", return_value=NINA_SAMPLE):
            warnings = traffic.fetch_nina_warnings(("Bielefeld", "kreis gütersloh"))
        self.assertEqual(
            [w["title"] for w in warnings], ["Hochwasser Bielefeld", "Unwetter Kreis Gütersloh"]
        )

    def test_source_failure_yields_no_warnings(self):
        with mock.patch(
            "core.traffic._guarded_request_nina", side_effect=traffic.TrafficUnavailable("x")
        ):
            self.assertEqual(traffic.fetch_nina_warnings(("Bielefeld",)), [])

    def test_nina_host_is_on_the_allowlist(self):
        self.assertIn("warnung.bund.de", traffic.ALLOWED_HOSTS)
        self.assertTrue(traffic.NINA_URL.startswith("https://warnung.bund.de/"))


class StationSettingsTrafficFormTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Form", slug="form-traffic")

    def _form(self, **data):
        base = {"name": "Form", "organization_profile": self.station.organization_profile}
        base.update(data)
        return StationSettingsForm(base, instance=self.station)

    def test_valid_configuration_is_normalised(self):
        form = self._form(
            traffic_enabled="on", traffic_roads="a2 ; a33", traffic_radius_km="30",
            traffic_warning_areas=" Bielefeld , bielefeld, Herford ",
            latitude="52.02", longitude="8.42",
        )
        self.assertTrue(form.is_valid(), form.errors)
        station = form.save()
        self.assertEqual(station.traffic_roads, "A2, A33")
        self.assertEqual(station.traffic_radius_km, 30)
        self.assertEqual(station.traffic_warning_areas, "Bielefeld, Herford")
        self.assertFalse(station.traffic_local_sources)

    def test_invalid_road_is_rejected(self):
        form = self._form(traffic_roads="A2/../x", latitude="52", longitude="8")
        self.assertFalse(form.is_valid())
        self.assertIn("traffic_roads", form.errors)

    def test_too_many_roads_and_areas_are_rejected(self):
        form = self._form(
            traffic_roads="A1,A2,A3,A4,A5,A6,A7",
            traffic_warning_areas=",".join(f"Ort{i}" for i in range(9)),
            latitude="52", longitude="8",
        )
        self.assertFalse(form.is_valid())
        self.assertIn("traffic_roads", form.errors)
        self.assertIn("traffic_warning_areas", form.errors)

    def test_roads_need_coordinates(self):
        form = self._form(traffic_enabled="on", traffic_roads="A2")
        self.assertFalse(form.is_valid())
        self.assertIn("latitude", form.errors)

    def test_roads_without_traffic_module_do_not_need_coordinates(self):
        form = self._form(traffic_roads="A2")
        self.assertTrue(form.is_valid(), form.errors)

    def test_coordinates_only_together_and_in_range(self):
        form = self._form(latitude="52")
        self.assertFalse(form.is_valid())
        self.assertIn("longitude", form.errors)
        form = self._form(latitude="91", longitude="8")
        self.assertFalse(form.is_valid())
        self.assertIn("latitude", form.errors)
        form = self._form(latitude="52", longitude="181")
        self.assertFalse(form.is_valid())
        self.assertIn("longitude", form.errors)

    def test_radius_range_and_default(self):
        form = self._form(traffic_radius_km="0")
        self.assertFalse(form.is_valid())
        self.assertIn("traffic_radius_km", form.errors)
        form = self._form(traffic_radius_km="201")
        self.assertFalse(form.is_valid())
        form = self._form(traffic_radius_km="")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["traffic_radius_km"], 25)

    @mock.patch("core.weather.geocode")
    def test_entered_coordinates_win_over_geocoding(self, geocode):
        form = self._form(
            weather_enabled="on", city="Steinhagen", latitude="52.1", longitude="8.5",
        )
        self.assertTrue(form.is_valid(), form.errors)
        geocode.assert_not_called()
        station = form.save()
        self.assertEqual((station.latitude, station.longitude), (52.1, 8.5))

    @mock.patch("core.weather.geocode")
    def test_geocoded_coordinates_satisfy_roads(self, geocode):
        geocode.return_value = {"latitude": 52.04, "longitude": 8.41, "label": "Steinhagen"}
        form = self._form(
            weather_enabled="on", city="Steinhagen", traffic_enabled="on", traffic_roads="A2",
        )
        self.assertTrue(form.is_valid(), form.errors)
        station = form.save()
        self.assertEqual((station.latitude, station.longitude), (52.04, 8.41))


class StationSettingsTrafficViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="traffic-admin", password="pw-123456789")
        self.station = Station.objects.create(
            name="Wache Verkehr", slug="wache-verkehr", latitude=52.02, longitude=8.42
        )
        Membership.objects.create(
            user=self.user, station=self.station, role=Membership.Role.ADMIN, is_active=True
        )
        self.client.force_login(self.user)

    def test_settings_page_shows_traffic_fields(self):
        response = self.client.get(reverse("station_settings"))
        for name in ("traffic_roads", "traffic_radius_km", "traffic_warning_areas",
                     "traffic_local_sources", "latitude", "longitude"):
            self.assertContains(response, f'name="{name}"')

    def test_post_saves_configuration_and_keeps_coordinates_when_fields_absent(self):
        response = self.client.post(reverse("station_settings"), {
            "name": "Wache Verkehr",
            "organization_profile": "rescue",
            "traffic_enabled": "on",
            "traffic_roads": "A1",
            "traffic_radius_km": "15",
            "traffic_warning_areas": "Osnabrück",
        })
        self.assertRedirects(response, reverse("station_settings"))
        self.station.refresh_from_db()
        self.assertEqual(self.station.traffic_roads, "A1")
        self.assertEqual(self.station.traffic_radius_km, 15)
        self.assertEqual(self.station.traffic_warning_areas, "Osnabrück")
        self.assertEqual((self.station.latitude, self.station.longitude), (52.02, 8.42))

    def test_empty_coordinate_fields_clear_coordinates(self):
        response = self.client.post(reverse("station_settings"), {
            "name": "Wache Verkehr",
            "organization_profile": "rescue",
            "latitude": "",
            "longitude": "",
        })
        self.assertRedirects(response, reverse("station_settings"))
        self.station.refresh_from_db()
        self.assertIsNone(self.station.latitude)


class SetupWizardTrafficTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_wizard_form_validates_roads(self):
        form = SetupWizardForm(setup_payload(traffic_roads="Z9"))
        self.assertFalse(form.is_valid())
        self.assertIn("traffic_roads", form.errors)

    def test_wizard_has_no_local_sources_field(self):
        self.assertNotIn("traffic_local_sources", SetupWizardForm().fields)

    @override_settings(SETUP_BOOTSTRAP_TOKEN=BOOTSTRAP)
    def test_wizard_stores_traffic_configuration(self):
        self.client.post(reverse("setup_wizard"), {"bootstrap_token": BOOTSTRAP})
        response = self.client.post(reverse("setup_wizard"), setup_payload(
            traffic_enabled="on",
            traffic_roads="a30, A1",
            traffic_radius_km="35",
            traffic_warning_areas="Osnabrück, Landkreis Osnabrück",
        ))
        self.assertEqual(response.status_code, 302)
        station = Station.objects.get()
        self.assertTrue(station.traffic_enabled)
        self.assertEqual(station.traffic_roads, "A30, A1")
        self.assertEqual(station.traffic_radius_km, 35)
        self.assertEqual(station.traffic_warning_areas, "Osnabrück, Landkreis Osnabrück")
        self.assertFalse(station.traffic_local_sources)

    @override_settings(SETUP_BOOTSTRAP_TOKEN=BOOTSTRAP)
    def test_wizard_without_traffic_starts_empty(self):
        self.client.post(reverse("setup_wizard"), {"bootstrap_token": BOOTSTRAP})
        self.client.post(reverse("setup_wizard"), setup_payload())
        station = Station.objects.get()
        self.assertFalse(station.traffic_enabled)
        self.assertEqual(station.traffic_roads, "")
        self.assertEqual(station.traffic_radius_km, 25)
        self.assertEqual(station.traffic_warning_areas, "")

    @override_settings(SETUP_BOOTSTRAP_TOKEN=BOOTSTRAP)
    def test_wizard_page_renders_traffic_section(self):
        self.client.post(reverse("setup_wizard"), {"bootstrap_token": BOOTSTRAP})
        response = self.client.get(reverse("setup_wizard"))
        self.assertContains(response, 'name="traffic_roads"')
        self.assertContains(response, 'name="traffic_warning_areas"')


class TrafficDataMigrationTests(TransactionTestCase):
    """0056 übernimmt für aktive Wachen die bisherigen festen Werte."""

    before = [("core", "0055_station_traffic_per_station")]
    after = [("core", "0056_station_traffic_keep_existing")]

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_existing_traffic_stations_keep_previous_behaviour(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.before)
        old_apps = executor.loader.project_state(self.before).apps
        OldStation = old_apps.get_model("core", "Station")
        active = OldStation.objects.create(name="Aktiv", slug="mig-aktiv", traffic_enabled=True)
        inactive = OldStation.objects.create(name="Inaktiv", slug="mig-inaktiv", traffic_enabled=False)

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.after)
        new_apps = executor.loader.project_state(self.after).apps
        NewStation = new_apps.get_model("core", "Station")

        active = NewStation.objects.get(pk=active.pk)
        self.assertEqual(active.traffic_roads, "A2, A33")
        self.assertEqual(active.traffic_radius_km, 25)
        self.assertEqual(
            active.traffic_warning_areas, "Gütersloh, Bielefeld, Steinhagen, Kreis Gütersloh"
        )
        self.assertTrue(active.traffic_local_sources)
        # Die übernommenen Werte bestehen die heutige Prüfung.
        self.assertEqual(traffic.parse_roads(active.traffic_roads), ("A2", "A33"))

        inactive = NewStation.objects.get(pk=inactive.pk)
        self.assertEqual(inactive.traffic_roads, "")
        self.assertEqual(inactive.traffic_warning_areas, "")
        self.assertFalse(inactive.traffic_local_sources)
