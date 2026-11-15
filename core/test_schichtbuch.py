"""Schichtbuch (0.29): Schichtband, Bereitschaftszeilen, offene Quittierungen,
Verbindungsbanner und Vorsortierung unter „Mehr“."""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.fleet_models import Vehicle
from core.models import CalendarEvent, HandoverEntry, Membership, Station
from core.navigation import function_areas, more_config
from core.services import acknowledge_handover
from core.shift_band import DAY_MINUTES, dashboard_band, unacknowledged_handovers, vehicle_readiness

PASSWORD = "x-test-pass-123"


class SchichtbuchBase(TestCase):
    def setUp(self):
        self.station = Station.objects.create(
            name="RW Band", slug="rw-band", fleet_enabled=True, mpg_enabled=True, warehouse_enabled=True,
            orga_enabled=False, calendar_enabled=True,
        )
        self.user = User.objects.create_user(username="band-lead", password=PASSWORD)
        self.membership = Membership.objects.create(
            user=self.user, station=self.station, role=Membership.Role.SHIFT_LEAD,
        )
        self.other = User.objects.create_user(username="band-member", password=PASSWORD)
        Membership.objects.create(user=self.other, station=self.station, role=Membership.Role.MEMBER)
        self.client.force_login(self.user)

    def handover(self, author, **kwargs):
        values = {"title": "Sauerstoff", "details": "x", "category": "material", "author": author}
        values.update(kwargs)
        return HandoverEntry.objects.create(station=self.station, **values)

    def vehicle(self, slug="rtw-1", **kwargs):
        values = {"call_sign": slug.upper(), "license_plate": f"MU-{slug}"}
        values.update(kwargs)
        return Vehicle.objects.create(station=self.station, slug=slug, **values)

    def dashboard(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        return response


class UnacknowledgedHandoverTests(SchichtbuchBase):
    def test_foreign_handover_needs_attention_until_acknowledged(self):
        handover = self.handover(self.other)
        response = self.dashboard()
        item = next(i for i in response.context["attention_items"] if i["key"] == "handover_acks")
        self.assertEqual((item["value"], item["title"], item["tone"]), (1, "Übergabe", "warning"))
        self.assertContains(response, "von dir noch nicht quittiert")
        acknowledge_handover(handover, self.user)
        keys = [i["key"] for i in self.dashboard().context["attention_items"]]
        self.assertNotIn("handover_acks", keys)

    def test_own_and_finished_handovers_do_not_count(self):
        self.handover(self.user)
        self.handover(self.other, status=HandoverEntry.Status.DONE)
        self.assertEqual(unacknowledged_handovers(self.station, self.user), 0)
        self.assertContains(self.dashboard(), "Nichts Dringendes offen")

    def test_other_station_is_not_counted(self):
        foreign = Station.objects.create(name="Fremd", slug="fremd")
        HandoverEntry.objects.create(station=foreign, title="Fremd", details="x", category="material",
                                     author=self.other)
        self.assertEqual(unacknowledged_handovers(self.station, self.user), 0)

    def test_attention_rows_name_their_tone_as_text(self):
        self.handover(self.other, priority=HandoverEntry.Priority.URGENT)
        response = self.dashboard()
        self.assertContains(response, '<span class="status-label priority-urgent">Dringend</span>')
        self.assertContains(response, '<span class="status-label priority-important">Wichtig</span>')


class VehicleReadinessTests(SchichtbuchBase):
    def test_rows_show_state_and_lock_time_without_disinfection_details(self):
        now = timezone.now()
        self.vehicle("rtw-1")
        self.vehicle("rtw-2", tactical_status=Vehicle.TacticalStatus.DISINFECTION, last_disinfection=now,
                     disinfection_locked_until=now + timedelta(minutes=30), status_note="Geheime Notiz")
        self.vehicle("ktw-1", tactical_status=Vehicle.TacticalStatus.LIMITED)
        rows = vehicle_readiness(list(Vehicle.objects.filter(station=self.station)))
        self.assertEqual([row["name"] for row in rows], ["RTW-2", "KTW-1", "RTW-1"])
        self.assertEqual([row["tone"] for row in rows], ["locked", "warning", "success"])
        self.assertIn("Einwirkzeit läuft bis", rows[0]["note"])
        response = self.dashboard()
        self.assertContains(response, '<span class="status-label locked">Desinfektion</span>')
        self.assertContains(response, '<span class="status-label success">Einsatzbereit</span>')
        self.assertContains(response, reverse("fleet_vehicle_detail", args=["rtw-2"]))
        self.assertNotContains(response, "Geheime Notiz")

    def test_no_section_without_fleet_module(self):
        self.station.fleet_enabled = False
        self.station.save(update_fields=["fleet_enabled"])
        self.assertNotContains(self.dashboard(), 'id="vehicle-readiness"')


class ShiftBandTests(SchichtbuchBase):
    def test_band_marks_entries_events_and_locks_of_the_day(self):
        now = timezone.now()
        self.handover(self.user, priority=HandoverEntry.Priority.URGENT)
        self.handover(self.user, is_paper_backfill=True, occurred_at=now - timedelta(hours=1))
        CalendarEvent.objects.create(station=self.station, title="Fortbildung", starts_at=now,
                                     ends_at=now + timedelta(minutes=45), created_by=self.user)
        self.vehicle("rtw-2", tactical_status=Vehicle.TacticalStatus.DISINFECTION, last_disinfection=now,
                     disinfection_locked_until=now + timedelta(minutes=30))
        band = dashboard_band(self.station, now=now)
        self.assertEqual([mark["urgent"] for mark in band["entries"]], [True])
        self.assertEqual(len(band["events"]), 1)
        self.assertEqual(len(band["locks"]), 1)
        for mark in band["events"] + band["locks"]:
            self.assertGreaterEqual(mark["x"], 0)
            self.assertLessEqual(mark["x"] + mark["w"], DAY_MINUTES)
        self.assertTrue(0 <= band["now_x"] <= DAY_MINUTES)
        labels = {item["label"] for item in band["legend"]}
        self.assertEqual(labels, {"Termin", "Desinfektion"})

    def test_band_renders_without_inline_styles_and_with_text_alternative(self):
        now = timezone.now()
        self.vehicle("rtw-2", tactical_status=Vehicle.TacticalStatus.DISINFECTION, last_disinfection=now,
                     disinfection_locked_until=now + timedelta(minutes=30))
        html = self.dashboard().content.decode()
        self.assertIn("data-shift-band", html)
        self.assertIn('class="sb-lock"', html)
        self.assertIn('class="shift-band-legend"', html)
        self.assertNotIn(" style=", html)
        self.assertEqual(html.count("<h1"), 1)

    def test_other_station_does_not_leak_into_the_band(self):
        foreign = Station.objects.create(name="Fremd", slug="fremd", calendar_enabled=True)
        now = timezone.now()
        CalendarEvent.objects.create(station=foreign, title="Fremder Termin", starts_at=now,
                                     ends_at=now + timedelta(minutes=45), created_by=self.other)
        HandoverEntry.objects.create(station=foreign, title="Fremd", details="x", category="material",
                                     author=self.other)
        band = dashboard_band(self.station, now=now)
        self.assertEqual((band["entries"], band["events"], band["legend"]), ([], [], []))


class ConnectionBannerTests(SchichtbuchBase):
    def test_banner_names_the_paper_fallback(self):
        html = self.dashboard().content.decode()
        self.assertIn("data-connection-chip", html)
        self.assertIn("data-connection-text", html)
        self.assertIn(f'<a href="{reverse("paper_hub")}">Papier-Rückfall</a>', html)

    def test_public_pages_have_no_paper_link_in_the_banner(self):
        self.client.logout()
        html = self.client.get(reverse("landing")).content.decode()
        self.assertIn("data-connection-chip", html)
        self.assertNotIn(reverse("paper_hub"), html)


class MoreOrderByFunctionTests(SchichtbuchBase):
    def test_function_areas_come_first_in_their_chapter(self):
        self.assertEqual(function_areas(self.membership), [])
        self.assertEqual(more_config(self.station, self.membership), more_config(self.station))
        self.membership.is_mpg_lead = True
        self.membership.is_hygiene_lead = True
        self.membership.save(update_fields=["is_mpg_lead", "is_hygiene_lead"])
        self.assertEqual(function_areas(self.membership), ["mpg", "fleet"])
        order = more_config(self.station, self.membership)
        self.assertLess(order["mpg"], order["fleet"])
        self.assertLess(order["fleet"], order["warehouse"])
        response = self.client.get(reverse("more"))
        self.assertContains(response, 'data-more="mpg" data-order="-2"')
        self.assertContains(response, 'data-more="fleet" data-order="-1"')
