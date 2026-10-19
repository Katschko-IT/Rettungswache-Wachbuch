"""Navigations-Reihenfolge je Wache."""
from django.contrib.auth.models import User
from django.test import TestCase

from core.models import Membership, Station
from core.navigation import more_config, nav_config, parse_order, parse_order_more


class NavigationOrderTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Nav", slug="nav", calendar_enabled=True)
        self.admin = User.objects.create_user("nav-admin", password="Nav-Test-12345")
        Membership.objects.create(user=self.admin, station=self.station, role=Membership.Role.ADMIN)

    def test_parse_order_filters_unknown_and_duplicates(self):
        self.assertEqual(
            parse_order("overview,calendar,foo,calendar,help"),
            ["overview", "calendar", "help"],
        )

    def test_default_order_without_configuration(self):
        config = nav_config(self.station)
        self.assertEqual(
            config["sequence"], ["overview", "handovers", "calendar", "more", "help"]
        )
        self.assertTrue(config["visible"]["overview"])

    def test_custom_order_changes_positions(self):
        self.station.nav_order = "help,overview,calendar"
        self.station.save(update_fields=["nav_order"])
        config = nav_config(self.station)
        self.assertEqual(config["order"]["help"], 1)
        self.assertEqual(config["order"]["overview"], 2)
        self.assertFalse(config["visible"]["handovers"])

    def test_settings_page_saves_both_orders(self):
        self.client.force_login(self.admin)
        response = self.client.post("/einstellungen/darstellung/", {
            "nav_order": "overview,more,help",
            "more_order": "wiki,news,settings",
        })
        self.assertEqual(response.status_code, 302)
        self.station.refresh_from_db()
        self.assertEqual(self.station.nav_order, "overview,more,help")
        self.assertEqual(self.station.more_order, "wiki,news,settings")
        order = more_config(self.station)
        self.assertLess(order["wiki"], order["settings"])

    def test_presentation_page_renders_both_sortable_lists(self):
        self.client.force_login(self.admin)
        response = self.client.get("/einstellungen/darstellung/")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('data-input="nav_order"', body)
        self.assertIn('data-input="more_order"', body)
        self.assertIn("data-sortable", body)

    def test_more_page_reflects_order(self):
        self.station.more_order = "wiki,news"
        self.station.save(update_fields=["more_order"])
        self.client.force_login(self.admin)
        response = self.client.get("/mehr/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-more="wiki"')
