from datetime import timedelta
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.fleet_models import DisinfectantMaster, DisinfectionProtocol, Vehicle, VehicleHandover
from core.models import Membership, Station
from core.wachalltag_models import Defect, StationAsset


class FleetModuleTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(
            name="Rettungswache Test Fuhrpark",
            slug="rw-test-fuhrpark",
            fleet_enabled=True,
        )
        self.user = User.objects.create_user(
            username="notfallsani_fleet",
            first_name="Felix",
            last_name="Retter",
            password="testpassword123",
        )
        self.membership = Membership.objects.create(
            user=self.user,
            station=self.station,
            role=Membership.Role.SHIFT_LEAD,
            is_active=True,
        )
        self.client.force_login(self.user)

        today = timezone.localdate()
        self.vehicle = Vehicle.objects.create(
            station=self.station,
            slug="rtw-01-83-01",
            call_sign="Rotkreuz 01/83-01",
            license_plate="M-RD 8301",
            vehicle_type=Vehicle.VehicleType.RTW,
            tactical_status=Vehicle.TacticalStatus.STATUS_1,
            current_mileage=45000,
            fuel_level_percent=90,
            adblue_level_percent=85,
            o2_pressure_bar=180,
            next_hu_date=today + timedelta(days=20),  # Critical: <= 30d
            next_uvv_date=today + timedelta(days=120),
            next_stretcher_service_date=today + timedelta(days=200),
        )

        self.disinfectant = DisinfectantMaster.objects.create(
            station=self.station,
            name="Incidin OxyWipe S",
            manufacturer="Ecolab",
            spectrum="Bakterizid, Levurozid",
            default_exposure_minutes=15,
            is_vah_listed=True,
        )

    def test_dashboard_renders_and_syncs_legacy_asset(self):
        StationAsset.objects.create(
            station=self.station,
            asset_id="ktw-legacy-01",
            label="Krankentransportwagen 02",
            kind=StationAsset.Kind.VEHICLE,
            status=StationAsset.Status.READY,
        )

        resp = self.client.get(reverse("fleet_dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Rotkreuz 01/83-01")
        self.assertContains(resp, "Krankentransportwagen 02")

        # Verify auto-sync created the Vehicle
        legacy_vehicle = Vehicle.objects.filter(station=self.station, slug="ktw-legacy-01").first()
        self.assertIsNotNone(legacy_vehicle)
        self.assertEqual(legacy_vehicle.tactical_status, Vehicle.TacticalStatus.STATUS_1)

    def test_dashboard_urgency_traffic_light(self):
        # vehicle has HU in 20 days -> critical
        self.assertEqual(self.vehicle.urgency["level"], "critical")
        resp = self.client.get(reverse("fleet_dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "HU (§29) fällig in 20d")

    def test_vehicle_create_and_detail(self):
        resp = self.client.post(
            reverse("fleet_vehicle_create"),
            {
                "call_sign": "Rotkreuz 01/82-01",
                "license_plate": "M-NEF 8201",
                "vehicle_type": Vehicle.VehicleType.NEF,
                "chassis_manufacturer": "Audi A6 Avant",
                "body_manufacturer": "Ambulanz Mobile",
                "tactical_status": Vehicle.TacticalStatus.STATUS_1,
                "current_mileage": 12500,
                "fuel_level_percent": 100,
                "adblue_level_percent": 100,
                "o2_pressure_bar": 200,
            },
        )
        self.assertEqual(resp.status_code, 302)
        new_vehicle = Vehicle.objects.get(license_plate="M-NEF 8201")
        self.assertTrue(new_vehicle.slug.startswith("rotkreuz"))

        # Test detail view
        detail_resp = self.client.get(reverse("fleet_vehicle_detail", args=[new_vehicle.slug]))
        self.assertEqual(detail_resp.status_code, 200)
        self.assertContains(detail_resp, "Rotkreuz 01/82-01")

    def test_vehicle_status_change(self):
        resp = self.client.post(
            reverse("fleet_vehicle_status_change", args=[self.vehicle.slug]),
            {"status": Vehicle.TacticalStatus.STATUS_6},
        )
        self.assertEqual(resp.status_code, 302)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.tactical_status, Vehicle.TacticalStatus.STATUS_6)

    def test_disinfection_protocol_and_lock_timer_enforcement(self):
        # 1. Post disinfection protocol
        resp = self.client.post(
            reverse("fleet_vehicle_disinfection_create", args=[self.vehicle.slug]),
            {
                "disinfectant": self.disinfectant.id,
                "kind": DisinfectionProtocol.Kind.ROUTINE,
                "exposure_minutes": 15,
                "lock_timer_applied": True,
                "notes": "Nach Verlegungsinfektionsfahrt",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.vehicle.refresh_from_db()

        # Sperrzeit wird in Ortszeit (Europe/Berlin) angezeigt, nicht in UTC.
        local_until = timezone.localtime(self.vehicle.disinfection_locked_until).strftime("%H:%M")
        self.assertIn(f"bis {local_until} Uhr", self.vehicle.status_note)

        # Vehicle must be in DISINFECTION status and locked
        self.assertEqual(self.vehicle.tactical_status, Vehicle.TacticalStatus.DISINFECTION)
        self.assertTrue(self.vehicle.is_disinfection_locked)
        self.assertGreater(self.vehicle.disinfection_remaining_seconds, 0)

        # 2. Try to set status back to Status 1 while locked -> MUST BE REJECTED!
        reject_resp = self.client.post(
            reverse("fleet_vehicle_status_change", args=[self.vehicle.slug]),
            {"status": Vehicle.TacticalStatus.STATUS_1},
            follow=True,
        )
        self.vehicle.refresh_from_db()
        # Status remains DISINFECTION
        self.assertEqual(self.vehicle.tactical_status, Vehicle.TacticalStatus.DISINFECTION)
        self.assertContains(reject_resp, "Das Fahrzeug ist noch in der Einwirkzeit der Desinfektion.")

        # 3. Setting to WORKSHOP or STATUS_6 is permitted even during disinfection
        allow_resp = self.client.post(
            reverse("fleet_vehicle_status_change", args=[self.vehicle.slug]),
            {"status": Vehicle.TacticalStatus.WORKSHOP},
        )
        self.assertEqual(allow_resp.status_code, 302)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.tactical_status, Vehicle.TacticalStatus.WORKSHOP)

    def test_vehicle_handover_updates_levels(self):
        resp = self.client.post(
            reverse("fleet_vehicle_handover_create", args=[self.vehicle.slug]),
            {
                "mileage": 45180,
                "fuel_percent": 75,
                "adblue_percent": 75,
                "o2_pressure_bar": 190,
                "btm_seal_intact": "yes",
                "medical_devices_checked": "yes",
                "vehicle_clean": "yes",
                "notes": "Keine Mängel festgestellt",
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.current_mileage, 45180)
        self.assertEqual(self.vehicle.fuel_level_percent, 75)
        self.assertEqual(self.vehicle.adblue_level_percent, 75)
        self.assertEqual(self.vehicle.o2_pressure_bar, 190)

        # Test warning when levels are low
        warn_resp = self.client.post(
            reverse("fleet_vehicle_handover_create", args=[self.vehicle.slug]),
            {
                "mileage": 45220,
                "fuel_percent": 25,  # Low!
                "adblue_percent": 75,
                "o2_pressure_bar": 80,  # Low!
                "btm_seal_intact": "yes",
                "medical_devices_checked": "yes",
                "vehicle_clean": "yes",
                "notes": "Sauerstoffflasche fast leer",
            },
            follow=True,
        )
        self.assertContains(warn_resp, "Sauerstoffvorrat niedrig")
        self.assertContains(warn_resp, "Kraftstoffstand niedrig")

    def test_defect_escalation_to_workshop(self):
        resp = self.client.post(
            reverse("fleet_vehicle_defect_report", args=[self.vehicle.slug]),
            {
                "title": "Bremsbelag-Verschleißanzeige aktiv",
                "priority": Defect.Priority.URGENT,
                "description": "Akustisches Schleifen beim Bremsen",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.tactical_status, Vehicle.TacticalStatus.WORKSHOP)
        self.assertTrue(Defect.objects.filter(station=self.station, category=Defect.Category.VEHICLE).exists())

    def test_fleet_csv_and_qr_export(self):
        csv_resp = self.client.get(reverse("fleet_export_csv"))
        self.assertEqual(csv_resp.status_code, 200)
        self.assertEqual(csv_resp["Content-Type"], "text/csv; charset=utf-8-sig")
        self.assertIn(self.vehicle.call_sign.encode("utf-8"), csv_resp.content)

        qr_resp = self.client.get(reverse("fleet_vehicle_qr", args=[self.vehicle.slug]))
        self.assertEqual(qr_resp.status_code, 200)
        self.assertEqual(qr_resp["Content-Type"], "image/png")

    def test_expired_contact_time_never_releases_vehicle_automatically(self):
        # Fachentscheidung: Die Besatzung prüft und gibt selbst frei.
        self.vehicle.tactical_status = Vehicle.TacticalStatus.DISINFECTION
        self.vehicle.disinfection_locked_until = timezone.now() - timedelta(minutes=1)
        self.vehicle.save()

        self.client.get(reverse("fleet_dashboard"))
        self.client.get(reverse("fleet_vehicle_detail", args=[self.vehicle.slug]))
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.tactical_status, Vehicle.TacticalStatus.DISINFECTION)
        self.assertTrue(self.vehicle.awaiting_crew_release)

        detail = self.client.get(reverse("fleet_vehicle_detail", args=[self.vehicle.slug]))
        self.assertContains(detail, "Freigabe durch die Besatzung")

    def test_manual_release_after_contact_time_is_audited(self):
        from core.models import AuditEvent

        self.vehicle.tactical_status = Vehicle.TacticalStatus.DISINFECTION
        self.vehicle.disinfection_locked_until = timezone.now() - timedelta(minutes=1)
        self.vehicle.save()
        resp = self.client.post(
            reverse("fleet_vehicle_status_change", args=[self.vehicle.slug]), {"status": "1"},
        )
        self.assertEqual(resp.status_code, 302)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.tactical_status, Vehicle.TacticalStatus.STATUS_1)
        event = AuditEvent.objects.get(action="fleet.status_changed")
        self.assertEqual(event.actor, self.user)
        self.assertEqual(event.metadata["from"], "disinfection")

    def test_station_fleet_disabled_denied(self):
        self.station.fleet_enabled = False
        self.station.save()

        resp = self.client.get(reverse("fleet_dashboard"))
        self.assertEqual(resp.status_code, 404)
