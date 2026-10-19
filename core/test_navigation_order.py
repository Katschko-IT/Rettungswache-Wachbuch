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
        keys = [entry["key"] for entry in config["entries"]]
        self.assertEqual(keys[0], "overview")
        self.assertIn("handovers", keys)

    def test_custom_order_changes_positions(self):
        self.station.nav_order = "help,overview,calendar"
        self.station.save(update_fields=["nav_order"])
        config = nav_config(self.station)
        entries = {entry["key"]: entry for entry in config["entries"]}
        self.assertEqual(entries["help"]["order"], 1)
        self.assertEqual(entries["overview"]["order"], 2)
        # Übergaben sind fest verankert und bleiben in der Leiste.
        self.assertIn("handovers", entries)

    def test_settings_page_saves_both_orders(self):
        self.client.force_login(self.admin)
        response = self.client.post("/einstellungen/darstellung/", {
            "order": "overview,handovers,news,wiki,more,help",
            "inbar_overview": "on",
            "inbar_news": "on",
            "inbar_more": "on",
            "inbar_help": "on",
            "more_order": "wiki,news,settings",
        })
        self.assertEqual(response.status_code, 302)
        self.station.refresh_from_db()
        self.assertEqual(self.station.nav_order, "overview,handovers,news,more,help")
        # Nicht angehakte Bereiche landen in Listenreihenfolge unter „Mehr“.
        self.assertEqual(self.station.more_order, "wiki")
        order = more_config(self.station)
        self.assertLess(order["wiki"], order["settings"])

    def test_presentation_page_renders_one_sortable_list(self):
        self.client.force_login(self.admin)
        response = self.client.get("/einstellungen/darstellung/")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('data-input="order"', body)
        self.assertIn("data-sortable", body)
        self.assertIn('name="inbar_news"', body)

    def test_more_page_reflects_order(self):
        self.station.more_order = "wiki,news"
        self.station.save(update_fields=["more_order"])
        self.client.force_login(self.admin)
        response = self.client.get("/mehr/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-more="wiki"')
