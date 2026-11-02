"""Tests für Paket C1-Rest (has_adblue) und Paket C2 (Desinfektion nach Plan Freigabe)."""
from __future__ import annotations

import re
from datetime import date
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.disinfection_plan import (
    active_disinfectants,
    active_levels,
    apply_level_defaults,
    can_confirm_disinfection,
    ensure_default_levels,
)
from core.fleet_forms import (
    DisinfectionLevelRuleForm,
    DisinfectionProtocolForm,
    VehicleForm,
    VehicleHandoverForm,
)
from core.fleet_models import (
    DisinfectantMaster,
    DisinfectionLevel,
    DisinfectionProtocol,
    Vehicle,
    VehicleHandover,
)
from core.models import AuditEvent, Membership, Station


CHECKS_YES = {
    "btm_seal_intact": "yes",
    "medical_devices_checked": "yes",
    "vehicle_clean": "yes",
}


class VehicleHasAdblueTests(TestCase):
    """Prüfungen für die Option 'AdBlue nicht vorhanden' (has_adblue auf Vehicle)."""

    def setUp(self):
        self.station = Station.objects.create(name="Hauptwache", slug="hauptwache", fleet_enabled=True)
        self.lead_user = User.objects.create_user("lead", password="password123")
        self.membership = Membership.objects.create(
            user=self.lead_user, station=self.station, role=Membership.Role.SHIFT_LEAD
        )
        self.client.force_login(self.lead_user)

        self.vehicle_with_adblue = Vehicle.objects.create(
            station=self.station,
            slug="rtw-1",
            call_sign="Rotkreuz 1/83-1",
            license_plate="M-RK 8301",
            has_adblue=True,
            current_mileage=10000,
            fuel_level_percent=100,
            adblue_level_percent=100,
            o2_pressure_bar=200,
        )
        self.vehicle_without_adblue = Vehicle.objects.create(
            station=self.station,
            slug="ktw-e",
            call_sign="Rotkreuz 1/85-1 (Elektro)",
            license_plate="M-RK 8501",
            has_adblue=False,
            current_mileage=5000,
            fuel_level_percent=100,
            adblue_level_percent=0,
            o2_pressure_bar=200,
        )

    def test_vehicle_model_default_has_adblue_is_true(self):
        v = Vehicle(station=self.station, slug="nef-1", call_sign="NEF 1", license_plate="M-RK 8201")
        self.assertTrue(v.has_adblue)

    def test_vehicle_form_contains_has_adblue(self):
        form = VehicleForm(station=self.station)
        self.assertIn("has_adblue", form.fields)

    def test_vehicle_form_with_adblue_requires_adblue_percent(self):
        data = {
            "call_sign": "RTW Neu",
            "license_plate": "M-RK 9999",
            "vehicle_type": Vehicle.VehicleType.RTW,
            "current_mileage": 1000,
            "fuel_level_percent": 80,
            "has_adblue": True,
            "o2_pressure_bar": 200,
        }
        form = VehicleForm(data=data, station=self.station)
        self.assertFalse(form.is_valid())
        self.assertIn("adblue_level_percent", form.errors)

    def test_vehicle_form_without_adblue_defaults_adblue_percent_to_zero(self):
        data = {
            "call_sign": "KTW Elektro",
            "license_plate": "M-RK 8888",
            "vehicle_type": Vehicle.VehicleType.KTW,
            "tactical_status": Vehicle.TacticalStatus.READY,
            "current_mileage": 1000,
            "fuel_level_percent": 90,
            "has_adblue": False,
            "o2_pressure_bar": 200,
        }
        form = VehicleForm(data=data, station=self.station)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["adblue_level_percent"], 0)

    def test_vehicle_handover_form_requires_adblue_when_has_adblue_true(self):
        form = VehicleHandoverForm(vehicle=self.vehicle_with_adblue)
        self.assertTrue(form.fields["adblue_percent"].required)
        self.assertEqual(len(form.level_fields), 2)

        post_data = {
            "mileage": 10100,
            "fuel_percent": 75,
            "o2_pressure_bar": 200,
            **CHECKS_YES,
            "notes": "",
        }
        # Ohne adblue_percent unvollständig
        bound_form = VehicleHandoverForm(data=post_data, vehicle=self.vehicle_with_adblue)
        self.assertFalse(bound_form.is_valid())
        self.assertIn("adblue_percent", bound_form.errors)

    def test_vehicle_handover_form_does_not_require_adblue_when_has_adblue_false(self):
        form = VehicleHandoverForm(vehicle=self.vehicle_without_adblue)
        self.assertFalse(form.fields["adblue_percent"].required)
        self.assertEqual(len(form.level_fields), 1)
        self.assertEqual(form.level_fields[0].name, "fuel_percent")

        post_data = {
            "mileage": 5100,
            "fuel_percent": 75,
            "o2_pressure_bar": 200,
            **CHECKS_YES,
            "notes": "",
        }
        bound_form = VehicleHandoverForm(data=post_data, vehicle=self.vehicle_without_adblue)
        self.assertTrue(bound_form.is_valid(), bound_form.errors)
        self.assertEqual(bound_form.cleaned_data["adblue_percent"], 0)

        # Speichern setzt adblue_percent am Protokoll und am Fahrzeug auf 0
        handover = bound_form.save(commit=False)
        handover.station = self.station
        handover.vehicle = self.vehicle_without_adblue
        handover.crew_member = self.lead_user
        handover.save()

        self.assertEqual(handover.adblue_percent, 0)
        self.vehicle_without_adblue.refresh_from_db()
        self.assertEqual(self.vehicle_without_adblue.adblue_level_percent, 0)
        self.assertEqual(self.vehicle_without_adblue.current_mileage, 5100)

    def test_vehicle_detail_and_dashboard_display_adblue_only_when_has_adblue(self):
        # Fahrzeug mit AdBlue zeigt AdBlue
        resp_with = self.client.get(reverse("fleet_vehicle_detail", args=[self.vehicle_with_adblue.slug]))
        self.assertEqual(resp_with.status_code, 200)
        content_with = resp_with.content.decode()
        self.assertIn("AdBlue", content_with)
        self.assertNotIn("AdBlue: Entfällt (kein AdBlue-Tank)", content_with)

        # Fahrzeug ohne AdBlue zeigt Hinweis „Entfällt“ im Formular
        resp_without = self.client.get(reverse("fleet_vehicle_detail", args=[self.vehicle_without_adblue.slug]))
        self.assertEqual(resp_without.status_code, 200)
        content_without = resp_without.content.decode()
        self.assertIn("AdBlue: Entfällt (kein AdBlue-Tank)", content_without)


class DisinfectionPlanConfirmationTests(TestCase):
    """Prüfungen für Paket C2: Bestätigung von Desinfektionsstufen und automatische Vorbelegung."""

    def setUp(self):
        self.station = Station.objects.create(name="Rettungswache Süd", slug="rw-sued", fleet_enabled=True)
        self.admin_user = User.objects.create_user("admin-user", password="password123")
        self.hygiene_lead = User.objects.create_user("hygiene-lead", password="password123")
        self.regular_member = User.objects.create_user("regular-member", password="password123")

        self.admin_mem = Membership.objects.create(
            user=self.admin_user, station=self.station, role=Membership.Role.ADMIN
        )
        self.lead_mem = Membership.objects.create(
            user=self.hygiene_lead, station=self.station, role=Membership.Role.SHIFT_LEAD
        )
        self.regular_mem = Membership.objects.create(
            user=self.regular_member, station=self.station, role=Membership.Role.MEMBER
        )

        self.agent = DisinfectantMaster.objects.create(
            station=self.station,
            name="Incidin Pro",
            manufacturer="Ecolab",
            default_exposure_minutes=15,
            is_active=True,
        )
        ensure_default_levels(self.station)
        self.level = DisinfectionLevel.objects.filter(station=self.station).first()

        self.vehicle = Vehicle.objects.create(
            station=self.station,
            slug="rtw-sued-1",
            call_sign="Rotkreuz 2/83-1",
            license_plate="M-RK 2831",
        )

    def test_can_confirm_disinfection_permissions(self):
        self.assertTrue(can_confirm_disinfection(self.lead_mem))
        self.assertTrue(can_confirm_disinfection(self.admin_mem))
        self.assertFalse(can_confirm_disinfection(self.regular_mem))
        self.assertFalse(can_confirm_disinfection(None))

    def test_apply_level_defaults_noop_when_unconfirmed_or_none(self):
        cleaned = {"disinfectant": None, "exposure_minutes": None}
        self.assertEqual(apply_level_defaults(cleaned.copy(), None), cleaned)

        # Unbestätigte Stufe verändert cleaned_data nicht
        self.assertFalse(self.level.is_rule_confirmed)
        res = apply_level_defaults(cleaned.copy(), self.level)
        self.assertEqual(res, cleaned)

    def test_apply_level_defaults_populates_when_confirmed(self):
        self.level.disinfectant = self.agent
        self.level.release_rule = DisinfectionLevel.ReleaseRule.AFTER_EXPOSURE
        self.level.exposure_minutes = 20
        self.level.rule_confirmed_at = timezone.now()
        self.level.rule_confirmed_by = self.hygiene_lead
        self.level.save()

        self.assertTrue(self.level.is_rule_confirmed)

        cleaned = {"disinfectant": None, "exposure_minutes": None}
        result = apply_level_defaults(cleaned, self.level)

        self.assertEqual(result["disinfectant"], self.agent)
        self.assertEqual(result["exposure_minutes"], 20)
        self.assertEqual(result["release_rule"], "exposure")
        self.assertTrue(result["lock_timer_applied"])

    def test_apply_level_defaults_respects_drying_rule(self):
        self.level.disinfectant = self.agent
        self.level.release_rule = DisinfectionLevel.ReleaseRule.AFTER_DRYING
        self.level.exposure_minutes = None
        self.level.rule_confirmed_at = timezone.now()
        self.level.rule_confirmed_by = self.admin_user
        self.level.save()

        cleaned = {"disinfectant": None}
        result = apply_level_defaults(cleaned, self.level)

        self.assertEqual(result["disinfectant"], self.agent)
        self.assertEqual(result["release_rule"], "dry")
        self.assertFalse(result["lock_timer_applied"])

    def test_apply_level_defaults_preserves_explicit_user_input(self):
        other_agent = DisinfectantMaster.objects.create(
            station=self.station, name="Terralin Protect", default_exposure_minutes=30
        )
        self.level.disinfectant = self.agent
        self.level.release_rule = DisinfectionLevel.ReleaseRule.AFTER_EXPOSURE
        self.level.exposure_minutes = 15
        self.level.rule_confirmed_at = timezone.now()
        self.level.save()

        cleaned = {"disinfectant": other_agent, "exposure_minutes": 45}
        result = apply_level_defaults(cleaned, self.level)

        self.assertEqual(result["disinfectant"], other_agent)
        self.assertEqual(result["exposure_minutes"], 45)

    def test_disinfection_protocol_form_widget_renders_data_attributes(self):
        self.level.disinfectant = self.agent
        self.level.release_rule = DisinfectionLevel.ReleaseRule.AFTER_EXPOSURE
        self.level.exposure_minutes = 15
        self.level.rule_confirmed_at = timezone.now()
        self.level.save()

        form = DisinfectionProtocolForm(station=self.station)
        html = str(form["level"])
        self.assertIn(f'data-disinfectant="{self.agent.pk}"', html)
        self.assertIn('data-release-rule="exposure"', html)
        self.assertIn('data-exposure-minutes="15"', html)
        self.assertIn('data-confirmed="1"', html)

    def test_disinfection_protocol_form_autofills_when_confirmed_level_selected(self):
        self.level.disinfectant = self.agent
        self.level.release_rule = DisinfectionLevel.ReleaseRule.AFTER_EXPOSURE
        self.level.exposure_minutes = 25
        self.level.rule_confirmed_at = timezone.now()
        self.level.rule_confirmed_by = self.admin_user
        self.level.save()

        # Benutzer gibt nur die Stufe an, Mittel und Einwirkzeit leer
        post_data = {
            "level": self.level.pk,
            "disinfectant": "",
            "exposure_minutes": "",
            "lock_timer_applied": "on",
            "notes": "Test nach Plan",
        }
        form = DisinfectionProtocolForm(data=post_data, station=self.station)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["disinfectant"], self.agent)
        self.assertEqual(form.cleaned_data["exposure_minutes"], 25)

        protocol = form.save(commit=False)
        protocol.station = self.station
        protocol.vehicle = self.vehicle
        protocol.performed_by = self.admin_user
        protocol.save()

        self.assertEqual(protocol.disinfectant, self.agent)
        self.assertEqual(protocol.exposure_minutes, 25)
        self.assertTrue(protocol.lock_timer_applied)

    def test_disinfection_protocol_form_rejects_missing_disinfectant_when_unconfirmed(self):
        self.assertIsNone(self.level.rule_confirmed_at)
        post_data = {
            "level": self.level.pk,
            "disinfectant": "",
            "exposure_minutes": "15",
            "notes": "",
        }
        form = DisinfectionProtocolForm(data=post_data, station=self.station)
        self.assertFalse(form.is_valid())
        self.assertIn("disinfectant", form.errors)

    def test_disinfection_levels_manage_view_access(self):
        url = reverse("fleet_disinfection_levels_manage")

        # Einfaches Mitglied: 403
        self.client.force_login(self.regular_member)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 403)

        # Schichtleiter / Hygienebeauftragter: 200
        self.client.force_login(self.hygiene_lead)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Desinfektionsplan der Wache")
        self.assertContains(resp, self.level.name)

        # Admin: 200
        self.client.force_login(self.admin_user)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_disinfection_level_confirm_view_updates_and_logs_audit(self):
        self.client.force_login(self.hygiene_lead)
        confirm_url = reverse("fleet_disinfection_level_confirm", args=[self.level.pk])

        # GET zeigt das Formular
        get_resp = self.client.get(confirm_url)
        self.assertEqual(get_resp.status_code, 200)
        self.assertContains(get_resp, self.level.name)

        # POST bestätigt die Stufe
        post_data = {
            "disinfectant": self.agent.pk,
            "release_rule": DisinfectionLevel.ReleaseRule.AFTER_EXPOSURE,
            "exposure_minutes": 30,
        }
        post_resp = self.client.post(confirm_url, post_data, follow=True)
        self.assertEqual(post_resp.status_code, 200)
        self.assertContains(post_resp, "wurde bestätigt")

        self.level.refresh_from_db()
        self.assertEqual(self.level.disinfectant, self.agent)
        self.assertEqual(self.level.release_rule, "exposure")
        self.assertEqual(self.level.exposure_minutes, 30)
        self.assertIsNotNone(self.level.rule_confirmed_at)
        self.assertEqual(self.level.rule_confirmed_by, self.hygiene_lead)
        self.assertTrue(self.level.is_rule_confirmed)

        # AuditEvent geprüft
        event = AuditEvent.objects.filter(
            station=self.station,
            action="fleet.disinfection_level_confirmed",
            object_id=str(self.level.pk),
        ).latest("created_at")
        self.assertEqual(event.actor, self.hygiene_lead)
        self.assertEqual(event.metadata["level"], self.level.name)
        self.assertEqual(event.metadata["disinfectant"], self.agent.name)
        self.assertEqual(event.metadata["exposure_minutes"], 30)
        self.assertEqual(event.metadata["release_rule"], "exposure")

    def test_disinfection_level_confirm_requires_exposure_minutes_for_exposure_rule(self):
        self.client.force_login(self.admin_user)
        confirm_url = reverse("fleet_disinfection_level_confirm", args=[self.level.pk])

        post_data = {
            "disinfectant": self.agent.pk,
            "release_rule": DisinfectionLevel.ReleaseRule.AFTER_EXPOSURE,
            "exposure_minutes": "",
        }
        post_resp = self.client.post(confirm_url, post_data)
        self.assertEqual(post_resp.status_code, 200)
        self.assertFormError(post_resp.context["form"], "exposure_minutes", "Bei Freigabe nach Einwirkzeit ist die Dauer in Minuten erforderlich.")

    def test_disinfection_level_cross_station_isolation(self):
        other_station = Station.objects.create(name="Andere Wache", slug="andere", fleet_enabled=True)
        ensure_default_levels(other_station)
        foreign_level = DisinfectionLevel.objects.filter(station=other_station).first()

        self.client.force_login(self.admin_user)
        # Versuch, eine fremde Desinfektionsstufe aufzurufen / zu bestätigen: 404
        url = reverse("fleet_disinfection_level_confirm", args=[foreign_level.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)
