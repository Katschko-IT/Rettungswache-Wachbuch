"""0.27, Entscheidung D2: Wer sieht Stufe, Einwirkzeit und Bemerkung einer Desinfektion?

Bis zum Funktionsmodell (0.28): die durchführende Person, Schichtleitung und
Admin der Wache. Alle anderen sehen „Desinfektion“ mit Datum, Mittel und
Person. Display, Sperrbildschirm, Terminal, Übersicht, CSV und App-API nennen
nie eine Stufe.
"""
from __future__ import annotations

import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.api.views import hash_api_token
from core.disinfection_plan import ensure_default_levels
from core.display import display_payload
from core.fleet_models import DisinfectantMaster, DisinfectionLevel, DisinfectionProtocol, Vehicle
from core.models import ApiToken, AuditEvent, Membership, Station
from core.terminal_views import _lock_screen_data
from core.test_release_0261_fleet import PATHOGENS

LEVEL = "Schlussdesinfektion (viruzid)"
NOTE = "Trage zusätzlich gewischt"


class DisinfectionVisibilityTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache D2", slug="wache-d2", fleet_enabled=True)
        self.users = {}
        for key, role, first in (
            ("performer", Membership.Role.MEMBER, "Alex"),
            ("member", Membership.Role.MEMBER, "Bea"),
            ("cashier", Membership.Role.CASHIER, "Cem"),
            ("lead", Membership.Role.SHIFT_LEAD, "Lena"),
            ("admin", Membership.Role.ADMIN, "Mia"),
            ("auditor", Membership.Role.AUDITOR, "Uwe"),
        ):
            user = User.objects.create_user(f"d2-{key}", first_name=first, password="pw-123456789")
            Membership.objects.create(user=user, station=self.station, role=role)
            self.users[key] = user
        self.vehicle = Vehicle.objects.create(station=self.station, slug="rtw-d2", call_sign="RTW D2",
                                              license_plate="RW-D2")
        self.agent = DisinfectantMaster.objects.create(station=self.station, name="Flächenmittel D2",
                                                       default_exposure_minutes=30)
        ensure_default_levels(self.station)
        self.level = DisinfectionLevel.objects.get(station=self.station, name=LEVEL)
        self.client.force_login(self.users["performer"])
        response = self.client.post(reverse("fleet_vehicle_disinfection_create", args=[self.vehicle.slug]), {
            "level": self.level.pk, "disinfectant": self.agent.pk, "exposure_minutes": 30,
            "lock_timer_applied": "on", "notes": NOTE,
        })
        self.assertEqual(response.status_code, 302)
        self.protocol = DisinfectionProtocol.objects.get()

    def history(self, key):
        self.client.force_login(self.users[key])
        page = self.client.get(reverse("fleet_vehicle_detail", args=[self.vehicle.slug])).content.decode()
        return page.split('id="fleet-disinfection-history"', 1)[1]

    def assert_details(self, key):
        history = self.history(key)
        self.assertIn(LEVEL, history)
        self.assertIn("Einwirkzeit 30 Min.", history)
        self.assertIn(NOTE, history)
        self.assertIn("Desinfektionsmittel: Flächenmittel D2", history)

    def test_performer_sees_level_minutes_and_note(self):
        self.assert_details("performer")

    def test_shift_lead_and_admin_see_level(self):
        self.assert_details("lead")
        self.assert_details("admin")

    def test_other_member_and_cashier_see_only_desinfektion_date_agent_person(self):
        day = timezone.localtime(self.protocol.started_at).strftime("%d.%m.%Y")
        for key in ("member", "cashier"):
            with self.subTest(role=key):
                history = self.history(key)
                self.assertNotIn(LEVEL, history)
                self.assertNotIn("Min.", history)
                self.assertNotIn(NOTE, history)
                self.assertNotIn("viruzid", history)
                self.assertIn("Desinfektion", history)
                self.assertIn("Desinfektionsmittel: Flächenmittel D2", history)
                self.assertIn(day, history)
                self.assertIn("Alex", history)  # durchführende Person bleibt sichtbar (Betreiberentscheid)

    def test_details_require_the_same_station(self):
        other = Station.objects.create(name="Andere D2", slug="andere-d2", fleet_enabled=True)
        foreign_lead = User.objects.create_user("d2-foreign-lead", password="pw-123456789")
        foreign = Membership.objects.create(user=foreign_lead, station=other, role=Membership.Role.SHIFT_LEAD)
        self.assertFalse(self.protocol.details_visible_to(foreign))
        self.client.force_login(foreign_lead)
        self.assertEqual(self.client.get(reverse("fleet_vehicle_detail", args=[self.vehicle.slug])).status_code, 404)
        self.assertFalse(self.protocol.details_visible_to(None))
        own = Membership.objects.get(user=self.users["lead"], station=self.station)
        self.assertTrue(self.protocol.details_visible_to(own))
        # Gleiche Person, andere Wache: auch die durchführende Person sieht dort nichts.
        elsewhere = Membership(user=self.users["performer"], station=other, role=Membership.Role.MEMBER)
        self.assertFalse(self.protocol.details_visible_to(elsewhere))

    def test_auditor_gets_403_on_fleet_and_audit_has_no_level_name(self):
        self.client.force_login(self.users["auditor"])
        self.assertEqual(self.client.get(reverse("fleet_vehicle_detail", args=[self.vehicle.slug])).status_code, 403)
        self.assertEqual(self.client.get(reverse("fleet_dashboard")).status_code, 403)
        page = self.client.get(reverse("audit_log")).content.decode()
        self.assertNotIn(LEVEL, page)
        self.assertNotIn(NOTE, page)
        for event in AuditEvent.objects.all():
            self.assertNotIn("viruzid", json.dumps(event.metadata, ensure_ascii=False))

    def test_dashboard_table_has_no_level_or_minutes_for_all_roles(self):
        for key in ("performer", "member", "cashier", "lead", "admin"):
            with self.subTest(role=key):
                self.client.force_login(self.users[key])
                page = self.client.get(reverse("fleet_dashboard")).content.decode()
                table = page.split("RKI-Desinfektionsbuch (Letzte Protokolle)", 1)[1].split("</table>", 1)[0]
                self.assertIn("RTW D2", table)
                self.assertIn("Flächenmittel D2", table)
                self.assertNotIn("Min.", table)
                self.assertNotIn("Einwirkzeit", table)
                self.assertNotIn(NOTE, page)
                for word in PATHOGENS:
                    self.assertNotIn(word, page)

    def test_display_lockscreen_terminal_data_and_vehicle_locks_api_never_contain_level(self):
        texts = [
            json.dumps(display_payload(self.station), ensure_ascii=False),
            json.dumps(_lock_screen_data(self.station), ensure_ascii=False),
        ]
        for key in ("performer", "member"):
            raw = f"wb_test_d2_{key}_token_1234567890"
            ApiToken.objects.create(
                user=self.users[key], label="t", token_prefix=raw[:11], token_hash=hash_api_token(raw),
                scopes=["read:me"], expires_at=timezone.now() + timedelta(days=1),
            )
            response = self.client.get(reverse("api_v1_vehicle_locks"), HTTP_AUTHORIZATION=f"Token {raw}")
            self.assertEqual(response.status_code, 200)
            # Sperren erhält nur die Besatzung (hier die durchführende Person).
            self.assertEqual(len(response.json()["results"]), 1 if key == "performer" else 0)
            texts.append(response.content.decode())
            self.client.force_login(self.users[key])
            texts.append(self.client.get(reverse("dashboard")).content.decode())
            texts.append(self.client.get(reverse("fleet_export_csv")).content.decode("utf-8-sig"))
        for text in texts:
            self.assertNotIn(LEVEL, text)
            self.assertNotIn("viruzid", text)
            self.assertNotIn(NOTE, text)
            for word in PATHOGENS:
                self.assertNotIn(word, text)
