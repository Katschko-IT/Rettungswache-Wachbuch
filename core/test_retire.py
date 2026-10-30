"""Außer Betrieb nehmen statt löschen: Fahrzeug und Medizingerät (0.27).

Ein außer Betrieb genommenes Objekt verschwindet aus den Übersichten, nimmt
keine neuen Nachweise an und behält alle bisherigen. Wieder in Betrieb geht es
fail-safe: das Fahrzeug auf „Außer Dienst“, das Gerät gesperrt bis zur Freigabe.
"""
from __future__ import annotations

import csv
import io
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.display import display_payload
from core.fleet_models import DisinfectantMaster, DisinfectionProtocol, Vehicle, VehicleHandover
from core.models import ApiToken, AuditEvent, Membership, Station
from core.mpg_models import DeviceRoutineCheck, DeviceTrainingRecord, MaintenanceLog, MedicalDevice
from core.notification_models import UserNotification
from core.wachalltag_models import Defect, StationAsset

PW = "x-test-pass-123"
CHECKS_YES = {"btm_seal_intact": "yes", "medical_devices_checked": "yes", "vehicle_clean": "yes"}


class RetireFixture(TestCase):
    def setUp(self):
        self.station = Station.objects.create(
            name="RW Außer Betrieb", slug="rw-ausser-betrieb", mpg_enabled=True, fleet_enabled=True, display_enabled=True,
        )
        self.users = {}
        for role in (Membership.Role.ADMIN, Membership.Role.SHIFT_LEAD, Membership.Role.MEMBER,
                     Membership.Role.CASHIER, Membership.Role.AUDITOR):
            user = User.objects.create_user(username=f"ab-{role}", password=PW, first_name=role)
            Membership.objects.create(user=user, station=self.station, role=role)
            self.users[role] = user
        self.lead = self.users[Membership.Role.SHIFT_LEAD]
        self.member = self.users[Membership.Role.MEMBER]
        # Gleicher Slug in einer anderen Wache: Slugs sind nur je Wache eindeutig.
        self.other_station = Station.objects.create(
            name="RW Nachbar", slug="rw-nachbar", mpg_enabled=True, fleet_enabled=True,
        )
        self.other_lead = User.objects.create_user(username="ab-nachbar", password=PW)
        Membership.objects.create(user=self.other_lead, station=self.other_station, role=Membership.Role.SHIFT_LEAD)

    def login(self, role):
        self.client.force_login(self.users[role] if isinstance(role, str) else role)

    def counts(self, *models):
        return [model.objects.count() for model in models]


class DeviceRetireTests(RetireFixture):
    def setUp(self):
        super().setUp()
        self.device = MedicalDevice.objects.create(
            station=self.station, slug="defi-1", name="Defibrillator RTW 1", location="RTW 1",
            next_stk_date=timezone.localdate() + timedelta(days=200),
        )
        self.twin = MedicalDevice.objects.create(station=self.other_station, slug="defi-1", name="Defi Nachbar")
        MaintenanceLog.objects.create(device=self.device, station=self.station, kind=MaintenanceLog.Kind.STK,
                                      performed_by="Service", created_by=self.lead,
                                      next_due_date=self.device.next_stk_date)
        DeviceRoutineCheck.objects.create(station=self.station, device=self.device, performed_by=self.member)
        DeviceTrainingRecord.objects.create(station=self.station, device=self.device, trainee=self.member,
                                            instructor="Nora")
        self.evidence = (MaintenanceLog, DeviceRoutineCheck, DeviceTrainingRecord, Defect)

    def retire(self, slug="defi-1"):
        return self.client.post(reverse("mpg_device_retire", args=[slug]))

    def test_lead_retires_device_and_evidence_stays(self):
        before = self.counts(*self.evidence)
        self.login(self.lead)
        response = self.retire()
        self.assertRedirects(response, reverse("mpg_device_detail", args=["defi-1"]))
        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.DECOMMISSIONED)
        self.assertEqual(self.device.decommissioned_at, timezone.localdate())
        event = AuditEvent.objects.get(action="mpg.device_retired")
        self.assertEqual(event.metadata, {"fields": ["current_status"], "from": "ready", "to": "decommissioned"})
        self.assertEqual(event.actor, self.lead)
        self.assertEqual(self.counts(*self.evidence), before)
        # Nicht mehr in Übersicht, Gerätepass und Display; in der Liste „Außer Betrieb genommen“.
        # (Der Verlauf „Letzte Kontrollen“ der Übersicht nennt es weiter.)
        self.assertNotIn(self.device, self.client.get(reverse("mpg_dashboard")).context["devices"])
        self.assertNotContains(self.client.get(reverse("mpg_geraetepass")), "Defibrillator RTW 1")
        self.login(self.member)
        self.assertNotContains(self.client.get(reverse("mpg_geraetepass")), "Defibrillator RTW 1")
        retired = self.client.get(reverse("mpg_retired_list"))
        self.assertContains(retired, "Defibrillator RTW 1")
        self.assertContains(retired, timezone.localdate().strftime("%d.%m.%Y"))
        self.assertNotContains(retired, "Defi Nachbar")
        detail = self.client.get(reverse("mpg_device_detail", args=["defi-1"]))
        self.assertContains(detail, "Außer Betrieb genommen am")
        self.assertContains(detail, "Nora")  # Einweisung bleibt sichtbar
        # Zweites Absenden ändert nichts und schreibt kein zweites Audit.
        self.login(self.lead)
        self.retire()
        self.assertEqual(AuditEvent.objects.filter(action="mpg.device_retired").count(), 1)

    def test_retired_device_leaves_the_display(self):
        MedicalDevice.objects.filter(pk=self.device.pk).update(current_status=MedicalDevice.Status.OOB)
        self.assertIn("Defibrillator RTW 1", [a["name"] for a in display_payload(self.station)["mpg_alerts"]])
        self.login(self.lead)
        self.retire()
        self.assertNotIn("Defibrillator RTW 1", [a["name"] for a in display_payload(self.station)["mpg_alerts"]])

    def test_other_roles_cannot_retire_or_reactivate(self):
        """NEGATIV: Mitglied und Kasse nicht, Auditor gar nicht (403)."""
        for role in (Membership.Role.MEMBER, Membership.Role.CASHIER):
            with self.subTest(role=role):
                self.login(role)
                self.retire()
                self.device.refresh_from_db()
                self.assertEqual(self.device.current_status, MedicalDevice.Status.READY)
        self.login(Membership.Role.AUDITOR)
        self.assertEqual(self.retire().status_code, 403)
        MedicalDevice.objects.filter(pk=self.device.pk).update(current_status=MedicalDevice.Status.DECOMMISSIONED)
        for role in (Membership.Role.MEMBER, Membership.Role.CASHIER):
            with self.subTest(role=role, action="reactivate"):
                self.login(role)
                self.client.post(reverse("mpg_device_reactivate", args=["defi-1"]))
                self.device.refresh_from_db()
                self.assertEqual(self.device.current_status, MedicalDevice.Status.DECOMMISSIONED)
        self.assertFalse(AuditEvent.objects.filter(action__startswith="mpg.device_re").exists())

    def test_only_the_own_station_is_affected(self):
        """NEGATIV: gleicher Slug in einer anderen Wache bleibt unberührt; fremde Slugs ergeben 404."""
        self.login(self.other_lead)
        self.retire()
        self.device.refresh_from_db()
        self.twin.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.READY)
        self.assertEqual(self.twin.current_status, MedicalDevice.Status.DECOMMISSIONED)
        self.login(self.lead)
        MedicalDevice.objects.create(station=self.other_station, slug="nur-nachbar", name="Nur Nachbar")
        self.assertEqual(self.retire("nur-nachbar").status_code, 404)
        self.assertEqual(self.client.post(reverse("mpg_device_reactivate", args=["nur-nachbar"])).status_code, 404)

    def test_module_off_and_wrong_method(self):
        """NEGATIV: Modul aus → 404; GET auf die Aktionen → 405."""
        self.login(self.lead)
        for name in ("mpg_device_retire", "mpg_device_reactivate"):
            self.assertEqual(self.client.get(reverse(name, args=["defi-1"])).status_code, 405, name)
        Station.objects.filter(pk=self.station.pk).update(mpg_enabled=False)
        self.assertEqual(self.retire().status_code, 404)
        self.assertEqual(self.client.post(reverse("mpg_device_reactivate", args=["defi-1"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("mpg_retired_list")).status_code, 404)
        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.READY)

    def test_retired_device_accepts_no_new_records(self):
        """NEGATIV: Kontrolle, Schnellkontrolle, Prüfung, Einweisung, Mangel und Freigabe werden abgewiesen."""
        self.login(self.lead)
        self.retire()
        before = self.counts(*self.evidence)
        audits = AuditEvent.objects.count()
        slug = "defi-1"
        posts = [
            ("mpg_routine_check", {"quick_pass": "1"}),
            ("mpg_routine_check", {"battery_ok": "yes", "visual_ok": "yes", "function_ok": "no", "notes": ""}),
            ("mpg_maintenance_create", {"kind": "stk", "performed_at": date.today().isoformat(),
                                        "performed_by": "Service", "passed": "yes"}),
            ("mpg_training_create", {"trainee": self.lead.pk, "instructor": "Nora",
                                     "trained_at": date.today().isoformat()}),
            ("mpg_device_defect", {"title": "Defekt", "description": "kaputt", "priority": "urgent"}),
            ("mpg_device_release", {"battery_ok": "on", "visual_ok": "on", "function_ok": "on"}),
        ]
        for name, data in posts:
            with self.subTest(view=name, data=data):
                response = self.client.post(reverse(name, args=[slug]), data, follow=True)
                self.assertContains(response, "Dieses Gerät ist außer Betrieb genommen.")
                self.device.refresh_from_db()
                self.assertEqual(self.device.current_status, MedicalDevice.Status.DECOMMISSIONED)
        self.assertEqual(self.counts(*self.evidence), before)
        self.assertEqual(AuditEvent.objects.count(), audits)
        detail = self.client.get(reverse("mpg_device_detail", args=[slug])).content.decode()
        for marker in ('data-modal-open="check-modal"', 'name="quick_pass"', 'data-modal-open="defect-modal"',
                       'data-modal-open="maint-modal"', 'data-modal-open="training-modal"', 'id="check-modal"'):
            self.assertNotIn(marker, detail)

    def test_reactivated_device_stays_locked_until_release(self):
        self.login(self.lead)
        self.retire()
        response = self.client.post(reverse("mpg_device_reactivate", args=["defi-1"]))
        self.assertRedirects(response, reverse("mpg_device_detail", args=["defi-1"]))
        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.OOB)
        self.assertIsNone(self.device.decommissioned_at)
        self.assertIn("freigeben", self.device.status_note)
        event = AuditEvent.objects.get(action="mpg.device_reactivated")
        self.assertEqual(event.metadata, {"fields": ["current_status"], "from": "decommissioned", "to": "oob"})
        detail = self.client.get(reverse("mpg_device_detail", args=["defi-1"])).content.decode()
        self.assertNotIn('name="quick_pass"', detail)
        self.assertIn('data-modal-open="release-modal"', detail)
        # Freigabe wie immer: als Funktionskontrolle dokumentiert.
        checks = DeviceRoutineCheck.objects.count()
        self.client.post(reverse("mpg_device_release", args=["defi-1"]),
                         {"battery_ok": "on", "visual_ok": "on", "function_ok": "on"})
        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.READY)
        self.assertEqual(DeviceRoutineCheck.objects.count(), checks + 1)

    def test_edit_form_never_offers_decommissioned(self):
        """NEGATIV: Außer Betrieb genommen wird nur über die eigene Aktion (mit Datum und Audit)."""
        self.login(self.lead)
        url = reverse("mpg_device_edit", args=["defi-1"])
        self.assertNotContains(self.client.get(url), 'value="decommissioned"')
        data = {"name": self.device.name, "category": self.device.category, "risk_class": self.device.risk_class,
                "location": "RTW 1", "current_status": "decommissioned", "stk_interval_months": 24,
                "dguv_interval_months": 12}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.READY)
        # Gesperrt: nur „gesperrt“ bleibt wählbar.
        MedicalDevice.objects.filter(pk=self.device.pk).update(current_status=MedicalDevice.Status.OOB)
        page = self.client.get(url)
        self.assertNotContains(page, 'value="decommissioned"')
        self.assertNotContains(page, 'value="ready"')
        # Außer Betrieb genommen: kein Statusfeld, ein mitgeschicktes wird ignoriert.
        MedicalDevice.objects.filter(pk=self.device.pk).update(current_status=MedicalDevice.Status.DECOMMISSIONED)
        self.assertContains(self.client.get(url), "Wieder in Betrieb nehmen")
        self.client.post(url, {**data, "current_status": "ready", "location": "Lager"})
        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.DECOMMISSIONED)
        self.assertEqual(self.device.location, "Lager")

    def test_bestandsverzeichnis_lists_decommission_date(self):
        self.login(self.lead)
        self.retire()
        # Altbestand: früher über das Formular gesetzt, ohne Datum.
        MedicalDevice.objects.create(station=self.station, slug="alt", name="Altgerät",
                                     current_status=MedicalDevice.Status.DECOMMISSIONED)
        response = self.client.get(reverse("mpg_export_bestandsverzeichnis"))
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
        column = rows[0].index("Außerbetriebnahme")
        values = {row[1]: row[column] for row in rows[1:]}
        self.assertEqual(values["Defibrillator RTW 1"], timezone.localdate().isoformat())
        self.assertEqual(values["Altgerät"], "")
        statuses = {row[1]: row[rows[0].index("Status")] for row in rows[1:]}
        self.assertEqual(statuses["Altgerät"], "Außer Betrieb genommen")
        detail = self.client.get(reverse("mpg_device_detail", args=["alt"]))
        self.assertContains(detail, "Außer Betrieb genommen.")
        self.assertEqual(self.client.get(reverse("mpg_retired_list")).status_code, 200)


class DeviceLockMirrorTests(RetireFixture):
    """NEGATIV: „Geräte & Fahrzeuge“ hebt keine Sperre ohne dokumentierte Freigabe auf."""

    def setUp(self):
        super().setUp()
        self.device = MedicalDevice.objects.create(station=self.station, slug="absaugung", name="Absaugung",
                                                   current_status=MedicalDevice.Status.OOB)
        self.asset = StationAsset.objects.create(station=self.station, asset_id="absaugung", label="Absaugung",
                                                 kind=StationAsset.Kind.DEVICE, status=StationAsset.Status.OOB)

    def test_web_asset_status_cannot_lift_a_lock(self):
        self.login(self.lead)
        for status in ("ready", "limited", "workshop"):
            with self.subTest(status=status):
                response = self.client.post(reverse("assets_inventory_web"), {
                    "action": "asset-status", "asset_id": "absaugung", "status": status,
                }, follow=True)
                self.assertContains(response, "nur dort, mit einer Funktionskontrolle")
                self.device.refresh_from_db()
                self.asset.refresh_from_db()
                self.assertEqual(self.device.current_status, MedicalDevice.Status.OOB)
                self.assertEqual(self.asset.status, StationAsset.Status.OOB)
        self.assertFalse(DeviceRoutineCheck.objects.exists())

    def test_api_asset_status_cannot_lift_a_lock_or_decommissioning(self):
        from core.api.views import hash_api_token

        raw = "wb_test_ausser_betrieb_token_123456"
        ApiToken.objects.create(
            user=self.lead, label="Tests", token_prefix=raw[:11], token_hash=hash_api_token(raw),
            scopes=["read:me", "read:handovers", "write:handovers"], expires_at=timezone.now() + timedelta(days=1),
        )
        for current in (MedicalDevice.Status.OOB, MedicalDevice.Status.DECOMMISSIONED):
            MedicalDevice.objects.filter(pk=self.device.pk).update(current_status=current)
            for status in ("ready", "workshop"):
                with self.subTest(current=current, status=status):
                    response = self.client.post(
                        reverse("api_v1_asset_status", args=["absaugung"]), data=f'{{"status": "{status}"}}',
                        content_type="application/json", HTTP_AUTHORIZATION=f"Token {raw}",
                    )
                    self.assertEqual(response.status_code, 409)
                    self.device.refresh_from_db()
                    self.asset.refresh_from_db()
                    self.assertEqual(self.device.current_status, current)
                    self.assertEqual(self.asset.status, StationAsset.Status.OOB)

    def test_mirror_never_changes_locked_or_decommissioned_devices(self):
        from core.device_status import mirror_to_device

        for current in (MedicalDevice.Status.OOB, MedicalDevice.Status.DECOMMISSIONED):
            MedicalDevice.objects.filter(pk=self.device.pk).update(current_status=current)
            for status in ("ready", "workshop", "limited"):
                with self.subTest(current=current, status=status):
                    self.asset.status = status
                    mirror_to_device(self.asset)
                    self.device.refresh_from_db()
                    self.assertEqual(self.device.current_status, current)
        # Ein einsatzklares Gerät folgt weiterhin („Werkstatt“ → Wartung).
        MedicalDevice.objects.filter(pk=self.device.pk).update(current_status=MedicalDevice.Status.READY)
        self.asset.status = "workshop"
        mirror_to_device(self.asset)
        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.MAINTENANCE)


class VehicleRetireTests(RetireFixture):
    def setUp(self):
        super().setUp()
        self.agent = DisinfectantMaster.objects.create(station=self.station, name="Wischtücher")
        self.vehicle = Vehicle.objects.create(station=self.station, slug="rtw-1", call_sign="RTW 1/83-1",
                                              license_plate="MU-RD 1")
        self.twin = Vehicle.objects.create(station=self.other_station, slug="rtw-1", call_sign="RTW Nachbar",
                                           license_plate="MU-RD 1")
        VehicleHandover.objects.create(station=self.station, vehicle=self.vehicle, crew_member=self.member,
                                       mileage=45000)
        DisinfectionProtocol.objects.create(station=self.station, vehicle=self.vehicle, performed_by=self.member,
                                            disinfectant=self.agent, lock_timer_applied=False)
        self.evidence = (VehicleHandover, DisinfectionProtocol, Defect)

    def retire(self, slug="rtw-1"):
        return self.client.post(reverse("fleet_vehicle_retire", args=[slug]))

    def test_lead_retires_vehicle_and_records_stay(self):
        before = self.counts(*self.evidence)
        handovers = list(VehicleHandover.objects.values())
        UserNotification.objects.create(
            station=self.station, user=self.member, kind=UserNotification.Kind.VEHICLE_READY,
            title="RTW 1/83-1", body="Freigeben", dedupe_key=f"vehicle_ready:{self.vehicle.pk}:x",
        )
        self.login(self.lead)
        response = self.retire()
        self.assertRedirects(response, reverse("fleet_vehicle_detail", args=["rtw-1"]))
        self.vehicle.refresh_from_db()
        self.assertFalse(self.vehicle.is_active)
        event = AuditEvent.objects.get(action="fleet.vehicle_retired")
        self.assertEqual(event.metadata, {"fields": ["is_active"], "from": True, "to": False})
        self.assertEqual(self.counts(*self.evidence), before)
        self.assertEqual(list(VehicleHandover.objects.values()), handovers)
        self.assertFalse(UserNotification.objects.filter(read_at__isnull=True).exists())
        self.assertNotIn(self.vehicle, self.client.get(reverse("fleet_dashboard")).context["vehicles"])
        self.assertNotIn("RTW 1/83-1", [v["call_sign"] for v in display_payload(self.station)["fleet_vehicles"]])
        retired = self.client.get(reverse("fleet_retired_list"))
        self.assertContains(retired, "RTW 1/83-1")
        self.assertNotContains(retired, "RTW Nachbar")
        detail = self.client.get(reverse("fleet_vehicle_detail", args=["rtw-1"])).content.decode()
        self.assertIn("Außer Betrieb genommen.", detail)
        self.assertIn("45000 km", detail)  # Verlauf bleibt sichtbar
        for name in ("fleet_vehicle_handover_create", "fleet_vehicle_disinfection_create",
                     "fleet_vehicle_defect_report", "fleet_vehicle_status_change", "fleet_vehicle_retire"):
            self.assertNotIn(reverse(name, args=["rtw-1"]), detail, name)
        self.assertIn(reverse("fleet_vehicle_reactivate", args=["rtw-1"]), detail)

    def test_other_roles_cannot_retire_or_reactivate(self):
        """NEGATIV: Mitglied und Kasse nicht, Auditor gar nicht (403)."""
        for role in (Membership.Role.MEMBER, Membership.Role.CASHIER):
            with self.subTest(role=role):
                self.login(role)
                self.retire()
                self.vehicle.refresh_from_db()
                self.assertTrue(self.vehicle.is_active)
        self.login(Membership.Role.AUDITOR)
        self.assertEqual(self.retire().status_code, 403)
        Vehicle.objects.filter(pk=self.vehicle.pk).update(is_active=False)
        for role in (Membership.Role.MEMBER, Membership.Role.CASHIER):
            self.login(role)
            self.client.post(reverse("fleet_vehicle_reactivate", args=["rtw-1"]))
            self.vehicle.refresh_from_db()
            self.assertFalse(self.vehicle.is_active)
        self.assertFalse(AuditEvent.objects.filter(action__startswith="fleet.vehicle_re").exists())

    def test_only_the_own_station_is_affected(self):
        """NEGATIV: gleicher Slug in einer anderen Wache bleibt unberührt; fremde Slugs ergeben 404."""
        self.login(self.other_lead)
        self.retire()
        self.vehicle.refresh_from_db()
        self.twin.refresh_from_db()
        self.assertTrue(self.vehicle.is_active)
        self.assertFalse(self.twin.is_active)
        self.login(self.lead)
        Vehicle.objects.create(station=self.other_station, slug="nur-nachbar", call_sign="X", license_plate="X-2")
        self.assertEqual(self.retire("nur-nachbar").status_code, 404)
        self.assertEqual(self.client.post(reverse("fleet_vehicle_reactivate", args=["nur-nachbar"])).status_code, 404)

    def test_module_off_and_wrong_method(self):
        """NEGATIV: Modul aus → 404; GET auf die Aktionen → 405."""
        self.login(self.lead)
        for name in ("fleet_vehicle_retire", "fleet_vehicle_reactivate"):
            self.assertEqual(self.client.get(reverse(name, args=["rtw-1"])).status_code, 405, name)
        Station.objects.filter(pk=self.station.pk).update(fleet_enabled=False)
        self.assertEqual(self.retire().status_code, 404)
        self.assertEqual(self.client.get(reverse("fleet_retired_list")).status_code, 404)
        self.vehicle.refresh_from_db()
        self.assertTrue(self.vehicle.is_active)

    def test_retired_vehicle_accepts_no_new_records(self):
        """NEGATIV: Übernahme, Desinfektion, Status und Mangel werden abgewiesen."""
        self.login(self.lead)
        self.retire()
        before = self.counts(*self.evidence)
        audits = AuditEvent.objects.count()
        posts = [
            ("fleet_vehicle_handover_create", {"mileage": 45100, "fuel_percent": "75", "adblue_percent": "50",
                                               "o2_pressure_bar": 190, **CHECKS_YES, "notes": ""}),
            ("fleet_vehicle_disinfection_create", {"disinfectant": self.agent.pk, "kind": "routine",
                                                   "exposure_minutes": 15, "lock_timer_applied": "on"}),
            ("fleet_vehicle_status_change", {"status": "workshop"}),
            ("fleet_vehicle_defect_report", {"title": "Blaulicht", "priority": "urgent"}),
        ]
        for name, data in posts:
            with self.subTest(view=name):
                response = self.client.post(reverse(name, args=["rtw-1"]), data, follow=True)
                self.assertContains(response, "Dieses Fahrzeug ist außer Betrieb genommen.")
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.tactical_status, Vehicle.TacticalStatus.STATUS_1)
        self.assertEqual(self.vehicle.current_mileage, 45000)
        self.assertEqual(self.counts(*self.evidence), before)
        self.assertEqual(AuditEvent.objects.count(), audits)

    def test_reactivation_sets_out_of_service(self):
        Vehicle.objects.filter(pk=self.vehicle.pk).update(is_active=False, status_note="alt")
        self.login(self.lead)
        response = self.client.post(reverse("fleet_vehicle_reactivate", args=["rtw-1"]))
        self.assertRedirects(response, reverse("fleet_vehicle_detail", args=["rtw-1"]))
        self.vehicle.refresh_from_db()
        self.assertTrue(self.vehicle.is_active)
        self.assertEqual(self.vehicle.tactical_status, Vehicle.TacticalStatus.STATUS_6)
        self.assertEqual(self.vehicle.status_note, "")
        event = AuditEvent.objects.get(action="fleet.vehicle_reactivated")
        self.assertEqual(event.metadata["changes"]["tactical_status"], {"from": "1", "to": "6"})
        self.assertIn(self.vehicle, self.client.get(reverse("fleet_dashboard")).context["vehicles"])

    def test_disinfectant_not_in_use_is_not_offered_and_rejected(self):
        """NEGATIV: Ein Mittel, das nicht mehr in Gebrauch ist, steht nicht zur Wahl."""
        DisinfectantMaster.objects.create(station=self.station, name="Sprühdesinfektion")
        DisinfectantMaster.objects.filter(pk=self.agent.pk).update(is_active=False)
        self.login(self.member)
        detail = self.client.get(reverse("fleet_vehicle_detail", args=["rtw-1"]))
        offered = list(detail.context["disinfection_form"].fields["disinfectant"].queryset)
        self.assertEqual([agent.name for agent in offered], ["Sprühdesinfektion"])
        before = DisinfectionProtocol.objects.count()
        self.client.post(reverse("fleet_vehicle_disinfection_create", args=["rtw-1"]), {
            "disinfectant": self.agent.pk, "kind": "routine", "exposure_minutes": 15, "lock_timer_applied": "on",
        })
        self.assertEqual(DisinfectionProtocol.objects.count(), before)
        # Das alte Protokoll behält sein Mittel.
        self.assertTrue(DisinfectionProtocol.objects.filter(disinfectant=self.agent).exists())

    def test_hint_when_no_disinfectant_is_in_use(self):
        DisinfectantMaster.objects.filter(pk=self.agent.pk).update(is_active=False)
        self.login(self.member)
        detail = self.client.get(reverse("fleet_vehicle_detail", args=["rtw-1"]))
        self.assertContains(detail, "Kein Desinfektionsmittel in Gebrauch.")

    def test_fleet_csv_has_in_service_column(self):
        Vehicle.objects.filter(pk=self.vehicle.pk).update(is_active=False)
        Vehicle.objects.create(station=self.station, slug="nef-1", call_sign="NEF 1", license_plate="MU-RD 2")
        self.login(self.lead)
        response = self.client.get(reverse("fleet_export_csv"))
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
        column = rows[0].index("In Betrieb")
        values = {row[0].lstrip("\ufeff"): row[column] for row in rows[1:]}
        self.assertEqual(values, {"NEF 1": "Ja", "RTW 1/83-1": "Nein"})
