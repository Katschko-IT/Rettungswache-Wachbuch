"""0.26.1 „Schaden begrenzen“ – Fuhrpark ohne Einsatz- und Erregerangaben.

Regressionstests für:

1. Desinfektion: Die Art (z. B. MRSA) steht nur im Protokoll, nie im
   Fahrzeugstatus, auf Display, Sperrbildschirm, Übersicht, CSV oder in der App.
2. Bemerkungsfeld „Bemerkung (keine Patienten- oder Einsatzangaben)“.
3. Fahrzeugstatus nur als Verfügbarkeit; Einsatzphasen 2/3/4 sind nicht wählbar.
4. Fahrzeugübernahme ohne Vorauswahl (Ja/Nein, km-Stand leer, Füllstände wählen).
"""
from __future__ import annotations

import importlib
import json
import re
from datetime import timedelta

from django.apps import apps
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.api.views import hash_api_token
from core.display import display_payload
from core.fleet_forms import DisinfectionProtocolForm, VehicleForm, VehicleHandoverForm
from core.fleet_models import (
    DisinfectantMaster,
    DisinfectionProtocol,
    Vehicle,
    VehicleHandover,
)
from core.models import ApiToken, AuditEvent, Membership, Station
from core.terminal_views import _lock_screen_data

PATHOGENS = ("MRSA", "VRE", "MRGN", "Noro", "Rotavirus", "difficile", "Schlussdesinfektion")
CHECKS_YES = {"btm_seal_intact": "yes", "medical_devices_checked": "yes", "vehicle_clean": "yes"}


class FleetFixture(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache 0.26.1", slug="wache-0261", fleet_enabled=True)
        self.user = User.objects.create_user("crew-0261", first_name="Kim", password="pw-123456789")
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.SHIFT_LEAD)
        self.client.force_login(self.user)
        self.vehicle = Vehicle.objects.create(
            station=self.station, slug="rtw-0261", call_sign="RTW 0261", license_plate="RW-0261",
            current_mileage=45000, fuel_level_percent=90, adblue_level_percent=85, o2_pressure_bar=180,
        )
        self.disinfectant = DisinfectantMaster.objects.create(
            station=self.station, name="Wischdesinfektion", default_exposure_minutes=15,
        )

    def disinfect(self, kind=DisinfectionProtocol.Kind.FINAL_MRSA):
        return self.client.post(reverse("fleet_vehicle_disinfection_create", args=[self.vehicle.slug]), {
            "disinfectant": self.disinfectant.pk, "kind": kind, "exposure_minutes": 30,
            "lock_timer_applied": "on", "notes": "",
        })

    def assert_no_pathogen(self, text: str):
        for word in PATHOGENS:
            self.assertNotIn(word, text)


class DisinfectionStaysNeutralTests(FleetFixture):
    def test_status_note_is_neutral_for_every_kind(self):
        for kind in DisinfectionProtocol.Kind.values:
            with self.subTest(kind=kind):
                self.disinfect(kind)
                self.vehicle.refresh_from_db()
                until = timezone.localtime(self.vehicle.disinfection_locked_until).strftime("%H:%M")
                self.assertEqual(self.vehicle.status_note, f"Desinfektion bis {until} Uhr")
                self.assert_no_pathogen(self.vehicle.status_note)
                self.assertNotIn(DisinfectionProtocol(kind=kind).get_kind_display(), self.vehicle.status_note)

    def test_outputs_outside_the_protocol_show_only_neutral_state(self):
        self.disinfect()
        self.vehicle.refresh_from_db()
        # Wanddisplay und Sperrbildschirm/Terminal-Daten
        self.assert_no_pathogen(json.dumps(display_payload(self.station), ensure_ascii=False))
        lock = _lock_screen_data(self.station)
        self.assert_no_pathogen(json.dumps(lock, ensure_ascii=False))
        self.assertEqual(lock["fleet_vehicles"][0]["status_short"], "Desinfektion")
        # Übersicht und CSV-Export
        self.assert_no_pathogen(self.client.get(reverse("dashboard")).content.decode())
        self.assert_no_pathogen(self.client.get(reverse("fleet_export_csv")).content.decode("utf-8-sig"))
        # App-API: laufende Sperren der eigenen Fahrzeuge
        raw = "wb_test_0261_token_1234567890"
        ApiToken.objects.create(
            user=self.user, label="t", token_prefix=raw[:11], token_hash=hash_api_token(raw),
            scopes=["read:me"], expires_at=timezone.now() + timedelta(days=1),
        )
        api = self.client.get(reverse("api_v1_vehicle_locks"), HTTP_AUTHORIZATION=f"Token {raw}")
        self.assertEqual(len(api.json()["results"]), 1)
        self.assert_no_pathogen(api.content.decode())

    def test_fleet_dashboard_lists_protocols_without_kind(self):
        self.disinfect()
        html = self.client.get(reverse("fleet_dashboard")).content.decode()
        section = html.split("RKI-Desinfektionsbuch (Letzte Protokolle)", 1)[1].split("</table>", 1)[0]
        self.assertIn("RTW 0261", section)
        self.assertIn(reverse("fleet_vehicle_detail", args=[self.vehicle.slug]) + "#fleet-disinfection-history",
                      section)
        self.assertNotIn("Art der Desinfektion", section)
        self.assert_no_pathogen(html)

    def test_note_is_stored_in_station_language(self):
        from django.utils import translation

        with translation.override("en"):
            self.disinfect()
        self.vehicle.refresh_from_db()
        self.assertTrue(self.vehicle.status_note.startswith("Desinfektion bis "), self.vehicle.status_note)

    def test_vehicle_page_shows_kind_only_in_protocol_history(self):
        self.disinfect()
        page = self.client.get(reverse("fleet_vehicle_detail", args=[self.vehicle.slug])).content.decode()
        rest, history = page.split("Desinfektionsbuch-Historie", 1)
        # Protokollformular (Auswahl der Art) und Protokoll-Historie dürfen die Art nennen.
        before, protocol_form = rest.split('id="fleet-disinfection"', 1)
        after_form = protocol_form.split('id="fleet-defect"', 1)[1]
        self.assert_no_pathogen(before + after_form)
        self.assertIn("MRSA", history)  # Das Protokoll selbst bleibt vollständig.


class NeutralStatusMigrationTests(FleetFixture):
    migration = importlib.import_module("core.migrations.0067_fleet_neutral_status")

    def test_rewrites_old_notes_and_mission_statuses_but_not_audit(self):
        old = "Desinfektion läuft (Gezielte Schlussdesinfektion: MRSA / VRE / 3MRGN): Gesperrt bis 14:30 Uhr"
        Vehicle.objects.filter(pk=self.vehicle.pk).update(tactical_status="disinfection", status_note=old)
        # Abgelaufene Desinfektion: Die alte Bemerkung ist veraltet und wird geleert.
        stale = Vehicle.objects.create(
            station=self.station, slug="rtw-s", call_sign="RTW S", license_plate="RW-S",
            tactical_status="3", status_note="Desinfektion läuft (Noro): Gesperrt bis 09:15 Uhr",
        )
        broken = Vehicle.objects.create(
            station=self.station, slug="rtw-b", call_sign="RTW B", license_plate="RW-B",
            tactical_status="disinfection", status_note="Desinfektion läuft (Norovirus)",
        )
        others = [
            Vehicle.objects.create(station=self.station, slug=f"rtw-{value}", call_sign=f"RTW {value}",
                                   license_plate=f"RW-{value}", tactical_status=value, status_note="Reifen prüfen")
            for value in ("2", "4", "6", "workshop")
        ]
        event = AuditEvent.objects.create(
            actor=self.user, station=self.station, action="fleet.status_changed", object_type="Vehicle",
            object_id=str(self.vehicle.pk), metadata={"fields": ["tactical_status"], "from": "3", "to": "4"},
        )

        self.migration.neutralize_vehicles(apps, None)

        self.vehicle.refresh_from_db()
        broken.refresh_from_db()
        stale.refresh_from_db()
        self.assertEqual(self.vehicle.tactical_status, "disinfection")
        self.assertEqual(self.vehicle.status_note, "Desinfektion bis 14:30 Uhr")
        self.assertEqual((stale.tactical_status, stale.status_note), ("1", ""))
        self.assertEqual(broken.status_note, "Desinfektion läuft")
        self.assertEqual(broken.tactical_status, "disinfection")
        self.assertEqual([Vehicle.objects.get(pk=v.pk).tactical_status for v in others], ["1", "1", "6", "workshop"])
        self.assertTrue(all(Vehicle.objects.get(pk=v.pk).status_note == "Reifen prüfen" for v in others))
        event.refresh_from_db()
        self.assertEqual(event.metadata, {"fields": ["tactical_status"], "from": "3", "to": "4"})

    def test_reverse_is_noop(self):
        operation = self.migration.Migration.operations[-1]
        self.assertTrue(operation.reversible)


class DisinfectionNoteLabelTests(FleetFixture):
    def test_label_and_hint_warn_against_patient_and_mission_data(self):
        field = DisinfectionProtocol._meta.get_field("notes")
        self.assertEqual(str(field.verbose_name), "Bemerkung (keine Patienten- oder Einsatzangaben)")
        self.assertIn("Einsatzdaten", str(field.help_text))
        form = DisinfectionProtocolForm(station=self.station, auto_id="disinfection_%s")
        self.assertNotIn("Transport", str(form["notes"]))
        page = self.client.get(reverse("fleet_vehicle_detail", args=[self.vehicle.slug]))
        self.assertNotContains(page, "Transportgrund")
        self.assertContains(page, "Bemerkung (keine Patienten- oder Einsatzangaben)")
        self.assertContains(page, 'aria-describedby="disinfection_notes_helptext"')


class VehicleStatusWithoutMissionPhasesTests(FleetFixture):
    def test_forms_offer_only_neutral_states(self):
        form = VehicleForm(station=self.station)
        self.assertEqual([value for value, _ in form.fields["tactical_status"].choices], ["1", "6", "workshop"])
        for value, label in Vehicle.TacticalStatus.choices:
            self.assertIsNone(re.search(r"\d", str(label)), label)
            if value not in Vehicle.LEGACY_STATUSES:
                self.assertNotIn("Status", str(label))
        page = self.client.get(reverse("fleet_vehicle_detail", args=[self.vehicle.slug])).content.decode()
        values = set(re.findall(r'name="status" value="([^"]+)"', page))
        self.assertEqual(values, {"1", "6", "workshop"})
        for word in ("Anfahrt", "Einsatzort", "Funk", "BOS-Status", "Status 1"):
            self.assertNotIn(word, page)
        dashboard = self.client.get(reverse("fleet_dashboard")).content.decode()
        self.assertIsNone(re.search(r"Status [1-6]|1 &amp; 2|Status 1/2", dashboard))

    def test_vehicle_form_rejects_mission_phase(self):
        data = {"call_sign": "RTW 0262", "license_plate": "RW-0262", "vehicle_type": "rtw",
                "current_mileage": 45000, "fuel_level_percent": 90, "adblue_level_percent": 85,
                "o2_pressure_bar": 180}
        for value in ("2", "3", "4", "disinfection"):
            with self.subTest(value=value):
                form = VehicleForm({**data, "tactical_status": value}, station=self.station)
                self.assertFalse(form.is_valid())
                self.assertIn("tactical_status", form.errors)

    def test_edit_form_cannot_change_status_or_lift_disinfection_lock(self):
        self.disinfect()
        self.vehicle.refresh_from_db()
        self.assertTrue(self.vehicle.is_disinfection_locked)
        form = VehicleForm(instance=self.vehicle, station=self.station)
        self.assertNotIn("tactical_status", form.fields)
        page = self.client.get(reverse("fleet_vehicle_edit", args=[self.vehicle.slug]))
        self.assertNotContains(page, 'name="tactical_status"')
        self.assertContains(page, "Den Status ändert das Fahrzeug-Cockpit")
        data = {"call_sign": "RTW 0261", "license_plate": "RW-0261", "vehicle_type": "rtw",
                "current_mileage": 45000, "fuel_level_percent": 90, "adblue_level_percent": 85,
                "o2_pressure_bar": 180, "tactical_status": "1", "status_note": ""}
        resp = self.client.post(reverse("fleet_vehicle_edit", args=[self.vehicle.slug]), data)
        self.assertRedirects(resp, reverse("fleet_vehicle_detail", args=[self.vehicle.slug]))
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.tactical_status, Vehicle.TacticalStatus.DISINFECTION)
        self.assertTrue(self.vehicle.is_disinfection_locked)

    def test_status_change_during_lock_is_refused_with_translated_message(self):
        self.disinfect()
        resp = self.client.post(reverse("fleet_vehicle_status_change", args=[self.vehicle.slug]),
                                {"status": "1"}, follow=True)
        self.assertContains(resp, "noch in der Einwirkzeit")
        self.assertNotContains(resp, "SPERRPFLICHT")
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.tactical_status, Vehicle.TacticalStatus.DISINFECTION)

    def test_mission_phases_and_manual_disinfection_are_rejected(self):
        for value in ("2", "3", "4", "disinfection"):
            with self.subTest(value=value):
                resp = self.client.post(reverse("fleet_vehicle_status_change", args=[self.vehicle.slug]),
                                        {"status": value}, follow=True)
                self.assertEqual(resp.status_code, 200)
                self.vehicle.refresh_from_db()
                self.assertEqual(self.vehicle.tactical_status, "1")
        self.assertFalse(AuditEvent.objects.filter(action="fleet.status_changed").exists())

    def test_allowed_change_writes_no_mission_phase(self):
        Vehicle.objects.filter(pk=self.vehicle.pk).update(tactical_status="4")
        resp = self.client.post(reverse("fleet_vehicle_status_change", args=[self.vehicle.slug]),
                                {"status": "workshop"}, follow=True)
        self.assertContains(resp, "„Werkstatt“")
        event = AuditEvent.objects.get(action="fleet.status_changed")
        self.assertEqual((event.metadata["from"], event.metadata["to"]), ("1", "workshop"))

    def test_display_and_lock_screen_without_status_numbers(self):
        for value in ("1", "6", "workshop", "3"):
            Vehicle.objects.filter(pk=self.vehicle.pk).update(tactical_status=value)
            vehicle = display_payload(self.station)["fleet_vehicles"][0]
            short = _lock_screen_data(self.station)["fleet_vehicles"][0]["status_short"]
            with self.subTest(value=value):
                self.assertNotIn(vehicle["status"], Vehicle.LEGACY_STATUSES)
                self.assertNotIn("Status", vehicle["status_label"] + short)
                self.assertIsNone(re.search(r"\d", vehicle["status_label"] + short))


class DefectReportMessagesTests(FleetFixture):
    def test_urgent_defect_is_calm_and_translated(self):
        url = reverse("fleet_vehicle_defect_report", args=[self.vehicle.slug])
        resp = self.client.post(url, {"title": "Bremse quietscht", "priority": "urgent"}, follow=True)
        self.assertContains(resp, "steht jetzt auf „Werkstatt“.")
        self.assertNotContains(resp, "Dringender Mangel erfasst!")
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.tactical_status, Vehicle.TacticalStatus.WORKSHOP)
        self.assertTrue(self.vehicle.status_note.startswith("Dringender Mangel #"))
        page = self.client.get(reverse("fleet_vehicle_detail", args=[self.vehicle.slug]))
        self.assertContains(page, 'value="Mangel an RTW 0261"')

    def test_empty_title_falls_back_to_default(self):
        url = reverse("fleet_vehicle_defect_report", args=[self.vehicle.slug])
        self.client.post(url, {"title": "  ", "priority": "normal"})
        from core.wachalltag_models import Defect

        self.assertEqual(Defect.objects.get().title, "Mangel an RTW 0261")


class HandoverWithoutPreselectionTests(FleetFixture):
    def setUp(self):
        super().setUp()
        # Eine frühere Übernahme macht den km-Stand (45.000) verlässlich.
        VehicleHandover.objects.create(
            station=self.station, vehicle=self.vehicle, crew_member=self.user, mileage=45000,
            fuel_percent=90, adblue_percent=85, o2_pressure_bar=180,
        )

    def post(self, follow=False, **overrides):
        data = {"mileage": 45120, "fuel_percent": "75", "adblue_percent": "50", "o2_pressure_bar": 190,
                **CHECKS_YES, "notes": ""}
        data.update(overrides)
        return self.client.post(reverse("fleet_vehicle_handover_create", args=[self.vehicle.slug]),
                                {k: v for k, v in data.items() if v is not None}, follow=follow)

    def test_unbound_form_has_no_preselection(self):
        form = VehicleHandoverForm(auto_id="handover_%s", vehicle=self.vehicle)
        html = str(form["mileage"]) + "".join(str(field) for field in form.level_fields + form.checkpoint_fields)
        self.assertIsNone(re.search(r"\schecked[\s>=]", html))
        self.assertNotIn("value=", str(form["mileage"]))
        self.assertNotIn("value=", str(form["o2_pressure_bar"]))
        self.assertIn('inputmode="numeric"', str(form["mileage"]))
        self.assertEqual(str(form["mileage"].help_text), "zuletzt 45.000 km")
        page = self.client.get(reverse("fleet_vehicle_detail", args=[self.vehicle.slug])).content.decode()
        handover = page.split('id="fleet-handover"', 1)[1].split('id="fleet-disinfection"', 1)[0]
        self.assertIsNone(re.search(r"\schecked[\s>=]", handover))
        self.assertNotIn('name="mileage" value', handover)
        self.assertIn("zuletzt 45.000 km", handover)
        self.assertIn('aria-describedby="handover_mileage_helptext"', handover)
        self.assertEqual(handover.count('value="yes"'), 3)
        self.assertEqual(handover.count('value="no"'), 3)

    def test_unanswered_checkpoints_are_rejected_and_input_kept(self):
        resp = self.post(btm_seal_intact=None, vehicle_clean=None, fuel_percent=None, mileage=45120)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(VehicleHandover.objects.count(), 1)
        self.assertContains(resp, "Bitte Ja oder Nein wählen.", count=2)
        self.assertContains(resp, "Bitte den Füllstand wählen.")
        self.assertContains(resp, 'value="45120"')
        self.assertContains(resp, "Bitte Eingaben prüfen")
        self.assertContains(resp, "Schichtübernahme nicht gespeichert.")

    def test_mileage_must_not_be_below_last_value(self):
        resp = self.post(mileage=44999)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "nicht unter dem letzten Stand (45.000 km)")
        self.assertEqual(VehicleHandover.objects.count(), 1)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.current_mileage, 45000)

    def test_mileage_jump_over_limit_is_rejected(self):
        resp = self.post(mileage=450000)  # eine Ziffer zu viel
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Mehr als 2.000 km seit dem letzten Stand (45.000 km)")
        self.assertEqual(VehicleHandover.objects.count(), 1)
        self.assertRedirects(self.post(mileage=47000), reverse("fleet_vehicle_detail", args=[self.vehicle.slug]))

    def test_first_handover_has_no_bounds(self):
        # Fahrzeug aus dem Gerätemodul bzw. ohne km-Angabe: nur der Platzhalter 10.000 km.
        for slug, km in (("ktw-neu", 3500), ("rtw-alt", 158430)):
            with self.subTest(km=km):
                vehicle = Vehicle.objects.create(station=self.station, slug=slug, call_sign=slug.upper(),
                                                 license_plate=slug.upper())
                self.assertEqual(vehicle.current_mileage, 10000)
                form = VehicleHandoverForm(auto_id="handover_%s", vehicle=vehicle)
                self.assertIn('min="0"', str(form["mileage"]))
                self.assertIn("Erste Übernahme", str(form["mileage"].help_text))
                data = {"mileage": km, "fuel_percent": "75", "adblue_percent": "50", "o2_pressure_bar": 190,
                        **CHECKS_YES, "notes": ""}
                resp = self.client.post(reverse("fleet_vehicle_handover_create", args=[slug]), data)
                self.assertRedirects(resp, reverse("fleet_vehicle_detail", args=[slug]))
                vehicle.refresh_from_db()
                self.assertEqual(vehicle.current_mileage, km)

    def test_low_levels_warn_in_plain_language(self):
        resp = self.post(o2_pressure_bar=80, fuel_percent="25", follow=True)
        self.assertContains(resp, "Sauerstoffvorrat niedrig (80 bar).")
        self.assertContains(resp, "Kraftstoffstand niedrig (25 %).")

    def test_all_yes_saves_without_defect_hint(self):
        resp = self.post()
        self.assertRedirects(resp, reverse("fleet_vehicle_detail", args=[self.vehicle.slug]))
        handover = VehicleHandover.objects.latest("pk")
        self.assertEqual((handover.fuel_percent, handover.adblue_percent, handover.mileage), (75, 50, 45120))
        self.assertTrue(handover.btm_seal_intact and handover.medical_devices_checked and handover.vehicle_clean)

    def test_no_answer_is_saved_and_leads_to_prefilled_defect(self):
        resp = self.post(btm_seal_intact="no")
        handover = VehicleHandover.objects.latest("pk")
        self.assertFalse(handover.btm_seal_intact)
        self.assertTrue(handover.vehicle_clean)
        detail = reverse("fleet_vehicle_detail", args=[self.vehicle.slug])
        self.assertEqual(resp["Location"], f"{detail}?mangel=btm_seal_intact#fleet-defect")
        page = self.client.get(resp["Location"])
        self.assertContains(page, "Bitte jetzt den Mangel melden.")
        self.assertContains(page, 'value="RTW 0261: BTM-Plombe nicht unversehrt"')
        self.assertContains(page, 'id="fleet-defect"')
        self.assertContains(page, "Befund")
