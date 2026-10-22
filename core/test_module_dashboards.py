"""Tests for new module dashboards (MPG, Warehouse, Fleet, Orga)."""
from django.contrib.auth.models import User
from django.test import TestCase

from core.models import Membership, Station
from core.wachalltag_models import Defect, InventoryItem, StationAsset
from core.wiki_models import WikiArticle


class ModuleDashboardTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(
            name="Rettungswache Mitte",
            slug="rw-mitte",
            mpg_enabled=True,
            warehouse_enabled=True,
            fleet_enabled=True,
            orga_enabled=True,
        )
        self.member = User.objects.create_user("member-1", password="Test-Password-12345")
        Membership.objects.create(
            user=self.member,
            station=self.station,
            role=Membership.Role.MEMBER,
        )

        # Seed sample data
        StationAsset.objects.create(
            station=self.station,
            asset_id="defi-1",
            label="Corpuls C3",
            kind=StationAsset.Kind.DEVICE,
            status=StationAsset.Status.READY,
        )
        StationAsset.objects.create(
            station=self.station,
            asset_id="rtw-1",
            label="Rotkreuz 01/83-01 (RTW)",
            kind=StationAsset.Kind.VEHICLE,
            status=StationAsset.Status.READY,
        )
        InventoryItem.objects.create(
            station=self.station,
            item_id="koffer-atmung",
            label="Notfallkoffer Atmung",
            kind=InventoryItem.Kind.DEVICE,
        )
        WikiArticle.objects.create(
            station=self.station,
            title="Dienstanweisung Reanimation",
            slug="da-reanimation",
            body="Leitlinie zur Reanimation 2026...",
        )

    def test_mpg_dashboard_renders_for_member(self):
        self.client.force_login(self.member)
        response = self.client.get("/mpg/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "MPG & Medizingeräte")
        self.assertContains(response, "Corpuls C3")
        self.assertEqual(response.context["kpis"]["ready"], 1)

    def test_mpg_dashboard_blocked_when_disabled(self):
        self.station.mpg_enabled = False
        self.station.save(update_fields=["mpg_enabled"])
        self.client.force_login(self.member)
        response = self.client.get("/mpg/")
        self.assertEqual(response.status_code, 404)

    def test_warehouse_dashboard_renders(self):
        self.client.force_login(self.member)
        response = self.client.get("/lager/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lager & Material")
        self.assertContains(response, "Notfallkoffer Atmung")

    def test_fleet_dashboard_renders(self):
        self.client.force_login(self.member)
        response = self.client.get("/fuhrpark/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fuhrpark & Fahrzeuge")
        self.assertContains(response, "Rotkreuz 01/83-01 (RTW)")

    def test_orga_dashboard_renders(self):
        self.client.force_login(self.member)
        response = self.client.get("/orga/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Organisation & Desk")
        self.assertContains(response, "Dienstanweisung Reanimation")

    def test_navigation_config_includes_modules(self):
        from core.navigation import nav_config
        config = nav_config(self.station)
        option_keys = {opt["key"] for opt in config["options"]}
        self.assertIn("mpg", option_keys)
        self.assertIn("warehouse", option_keys)
        self.assertIn("fleet", option_keys)
        self.assertIn("display", option_keys)
        self.assertIn("orga", option_keys)
