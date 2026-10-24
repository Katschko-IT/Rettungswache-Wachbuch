"""Übersicht: zuerst, was Aufmerksamkeit braucht; Unauffälliges bleibt ruhig."""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import HandoverEntry, Membership, Station
from core.wachalltag_models import Defect

PASSWORD = "x-test-pass-123"


class DashboardAttentionTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(
            name="RW Test", slug="rw-test", fleet_enabled=False, mpg_enabled=False,
            warehouse_enabled=False, orga_enabled=False,
        )
        self.user = User.objects.create_user(username="lead", password=PASSWORD)
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.SHIFT_LEAD)
        self.client.force_login(self.user)

    def get(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        return response

    def test_calm_station_says_so_in_the_heading(self):
        response = self.get()
        self.assertEqual(response.context["attention_items"], [])
        self.assertContains(response, "Nichts Dringendes offen")

    def test_attention_items_lead_and_are_sorted_by_severity(self):
        HandoverEntry.objects.create(
            station=self.station, title="Sauerstoff", details="x", category="material",
            priority=HandoverEntry.Priority.URGENT, author=self.user,
        )
        Defect.objects.create(station=self.station, title="Tür", priority=Defect.Priority.NORMAL,
                              created_by=self.user)
        response = self.get()
        items = response.context["attention_items"]
        self.assertEqual([item["tone"] for item in items], ["danger", "warning"])
        self.assertEqual(items[0]["title"], "Dringende Übergabe")
        self.assertContains(response, "2 Punkte brauchen Aufmerksamkeit")

    def test_singular_and_plural_labels(self):
        Defect.objects.create(station=self.station, title="Tür", created_by=self.user)
        item = next(i for i in self.get().context["attention_items"] if i["key"] == "defects")
        self.assertEqual((item["value"], item["title"]), (1, "Mangel"))
        Defect.objects.create(station=self.station, title="Fenster", created_by=self.user)
        item = next(i for i in self.get().context["attention_items"] if i["key"] == "defects")
        self.assertEqual((item["value"], item["title"]), (2, "Mängel"))

    def test_urgent_defect_is_danger(self):
        Defect.objects.create(station=self.station, title="Tür", priority=Defect.Priority.URGENT,
                              created_by=self.user)
        item = next(i for i in self.get().context["attention_items"] if i["key"] == "defects")
        self.assertEqual(item["tone"], "danger")

    def test_unremarkable_areas_are_listed_quietly(self):
        response = self.get()
        calm = [item["title"] for item in response.context["calm_items"]]
        self.assertIn("Mängel", calm)
        self.assertContains(response, "Ohne Auffälligkeiten")

    def test_due_vehicle_deadlines_need_attention_even_when_ready(self):
        from core.fleet_models import Vehicle

        self.station.fleet_enabled = True
        self.station.save(update_fields=["fleet_enabled"])
        Vehicle.objects.create(
            station=self.station, slug="rtw-1", call_sign="RTW 1", license_plate="MU-RD 1",
            next_hu_date=timezone.localdate() + timedelta(days=3),
        )
        item = next(i for i in self.get().context["attention_items"] if i["key"] == "fleet")
        # Die Zahl nennt den Grund (eine fällige Frist), keine „0 Fahrzeuge“.
        self.assertEqual((item["value"], item["title"]), (1, "Fahrzeugfrist"))
        self.assertNotIn("0", item["subtitle"])
