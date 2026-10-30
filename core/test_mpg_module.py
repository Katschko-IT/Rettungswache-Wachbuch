from datetime import timedelta
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.display import display_payload
from core.models import Membership, Station
from core.mpg_models import DeviceRoutineCheck, DeviceTrainingRecord, MaintenanceLog, MedicalDevice
from core.wachalltag_models import Defect


class MPGModuleTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(
            name="Rettungswache Test",
            slug="rw-test-mpg",
            mpg_enabled=True,
            tasks_enabled=True,
        )
        self.user = User.objects.create_user(
            username="notfallsanitaeter",
            first_name="Max",
            last_name="Mustermann",
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
        self.device = MedicalDevice.objects.create(
            station=self.station,
            slug="corpuls3-test",
            name="corpuls3 Defibrillator/Monitor",
            category=MedicalDevice.Category.DEFIBRILLATOR,
            risk_class=MedicalDevice.RiskClass.IIB,
            manufacturer="GS Elektromedizinische Geräte",
            model_type="corpuls3",
            serial_number="SN-12345",
            inventory_number="INV-001",
            location="RTW 01/83-01",
            current_status=MedicalDevice.Status.READY,
            is_anlage_1=True,
            next_stk_date=today + timedelta(days=20),  # Critical (<= 30 days)
        )

    def test_urgency_calculation(self):
        today = timezone.localdate()
        # Critical test
        urg = self.device.urgency
        self.assertEqual(urg["level"], "critical")
        self.assertEqual(urg["type"], "STK")

        # Overdue test
        self.device.next_stk_date = today - timedelta(days=5)
        self.device.save()
        urg_overdue = self.device.urgency
        self.assertEqual(urg_overdue["level"], "overdue")

        # Warning test (40 days)
        self.device.next_stk_date = today + timedelta(days=40)
        self.device.save()
        self.assertEqual(self.device.urgency["level"], "warning")

        # OK test (100 days)
        self.device.next_stk_date = today + timedelta(days=100)
        self.device.save()
        self.assertEqual(self.device.urgency["level"], "ok")

    def test_maintenance_log_updates_device_deadline_and_status(self):
        today = timezone.localdate()
        new_due = today + timedelta(days=730)  # 2 years

        self.device.current_status = MedicalDevice.Status.MAINTENANCE
        self.device.save()

        log = MaintenanceLog.objects.create(
            device=self.device,
            station=self.station,
            kind=MaintenanceLog.Kind.STK,
            performed_at=today,
            performed_by="Medizintechnik Nord",
            passed=True,
            next_due_date=new_due,
            created_by=self.user,
        )

        self.device.refresh_from_db()
        self.assertEqual(self.device.next_stk_date, new_due)
        self.assertEqual(self.device.current_status, MedicalDevice.Status.READY)

    def test_routine_check_updates_status(self):
        # Schnellkontrolle: alle Prüfpunkte bestätigt
        resp = self.client.post(
            reverse("mpg_routine_check", args=[self.device.slug]),
            data={"quick_pass": "1"},
        )
        self.assertEqual(resp.status_code, 302)
        self.device.refresh_from_db()
        self.assertIsNotNone(self.device.last_routine_check)
        self.assertEqual(self.device.current_status, MedicalDevice.Status.READY)

        # Ein „Nein“ sperrt das Gerät und legt einen Mangel an
        resp_fail = self.client.post(
            reverse("mpg_routine_check", args=[self.device.slug]),
            data={"battery_ok": "yes", "visual_ok": "yes", "function_ok": "no", "notes": "Defektes EKG-Kabel"},
        )
        self.assertEqual(resp_fail.status_code, 302)
        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.OOB)
        check = DeviceRoutineCheck.objects.filter(device=self.device).latest("checked_at")
        self.assertFalse(check.passed)
        defect = Defect.objects.get(medical_device=self.device)
        self.assertEqual(defect.status, Defect.Status.OPEN)
        self.assertIn("Selbsttest/Funktion", defect.description)

    def test_passed_flag_cannot_contradict_check_items(self):
        self.client.post(
            reverse("mpg_routine_check", args=[self.device.slug]),
            data={"passed": "on", "battery_ok": "yes", "visual_ok": "yes", "function_ok": "no"},
        )
        check = DeviceRoutineCheck.objects.filter(device=self.device).latest("checked_at")
        self.assertFalse(check.passed)

    def test_defect_escalation_creates_defect_and_locks_device(self):
        resp = self.client.post(
            reverse("mpg_device_defect", args=[self.device.slug]),
            data={
                "title": "Monitor-Display flackert",
                "description": "Während der Anfahrt Ausfall der EKG-Anzeige",
                "priority": "urgent",
            },
        )
        self.assertEqual(resp.status_code, 302)

        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.OOB)
        self.assertIn("flackert", self.device.status_note)

        # Check Defect in Wachalltag
        defect = Defect.objects.filter(station=self.station, category=Defect.Category.DEVICE).first()
        self.assertIsNotNone(defect)
        self.assertEqual(defect.priority, Defect.Priority.URGENT)
        self.assertIn("Monitor-Display flackert", defect.title)

    def test_device_training_single_and_group(self):
        other_user = User.objects.create_user(username="kollege", password="pw")
        Membership.objects.create(user=other_user, station=self.station, role=Membership.Role.MEMBER)

        # Single training
        resp_single = self.client.post(
            reverse("mpg_training_create", args=[self.device.slug]),
            data={
                "trainee": self.user.id,
                "instructor": "Dr. MPG",
                "trained_at": timezone.localdate().isoformat(),
                "notes": "Einweisung corpuls3",
            },
        )
        self.assertEqual(resp_single.status_code, 302)
        self.assertTrue(DeviceTrainingRecord.objects.filter(device=self.device, trainee=self.user).exists())

        # Group training
        resp_group = self.client.post(
            reverse("mpg_training_create", args=[self.device.slug]),
            data={
                "trainees": [self.user.id, other_user.id],
                "instructor": "Medizingerätebeauftragter",
                "trained_at": timezone.localdate().isoformat(),
                "notes": "Gruppenfortbildung",
            },
        )
        self.assertEqual(resp_group.status_code, 302)
        self.assertTrue(DeviceTrainingRecord.objects.filter(device=self.device, trainee=other_user).exists())

    def test_mpg_dashboard_and_filters(self):
        resp = self.client.get(reverse("mpg_dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "corpuls3")

        # Filter by category
        resp_cat = self.client.get(reverse("mpg_dashboard") + "?category=defi")
        self.assertEqual(resp_cat.status_code, 200)
        self.assertContains(resp_cat, "corpuls3")

        # Search query
        resp_search = self.client.get(reverse("mpg_dashboard") + "?q=SN-12345")
        self.assertEqual(resp_search.status_code, 200)
        self.assertContains(resp_search, "corpuls3")

    def test_mpg_device_detail(self):
        resp = self.client.get(reverse("mpg_device_detail", args=[self.device.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "GS Elektromedizinische Geräte")
        self.assertContains(resp, "RTW 01/83-01")

    def test_device_qr_endpoint(self):
        resp = self.client.get(reverse("mpg_device_qr", args=[self.device.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "image/png")

    def test_export_bestandsverzeichnis_csv(self):
        resp = self.client.get(reverse("mpg_export_bestandsverzeichnis"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp["Content-Type"])
        content = resp.content.decode("utf-8-sig")
        self.assertIn("corpuls3 Defibrillator/Monitor", content)
        self.assertIn("GS Elektromedizinische Geräte", content)

    def test_geraetepass_view(self):
        resp = self.client.get(reverse("mpg_geraetepass"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Einweisungsmatrix")

    def test_display_payload_includes_mpg_alerts(self):
        payload = display_payload(self.station)
        self.assertIn("mpg_alerts", payload)
        # Device has STK in 20 days -> critical alert
        self.assertEqual(len(payload["mpg_alerts"]), 1)
        alert = payload["mpg_alerts"][0]
        self.assertEqual(alert["level"], "critical")
        self.assertIn("corpuls3", alert["name"])

    def test_selftest_protocol_is_stored_but_not_evaluated(self):
        # Ein „PASS“ im gescannten Text ersetzt keine bestätigten Prüfpunkte.
        self.client.post(
            reverse("mpg_routine_check", args=[self.device.slug]),
            data={
                "battery_ok": "yes",
                "visual_ok": "yes",
                "function_ok": "no",
                "selftest_protocol": "CP3;SELFTEST:PASS;DEF:200J;BAT:98%",
            },
        )
        check = DeviceRoutineCheck.objects.filter(device=self.device).latest("checked_at")
        self.assertFalse(check.passed)
        self.assertIn("CP3;SELFTEST:PASS", check.notes)
        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.OOB)

        # Umgekehrt sperrt ein „FAIL“-Text kein Gerät, wenn alles bestätigt ist.
        device = MedicalDevice.objects.create(station=self.station, slug="medumat", name="MEDUMAT")
        self.client.post(
            reverse("mpg_routine_check", args=[device.slug]),
            data={
                "battery_ok": "yes",
                "visual_ok": "yes",
                "function_ok": "yes",
                "selftest_protocol": "WEINMANN;SELFTEST:FAIL",
            },
        )
        device.refresh_from_db()
        self.assertEqual(device.current_status, MedicalDevice.Status.READY)
        self.assertIn("WEINMANN;SELFTEST:FAIL", device.routine_checks.get().notes)


class MPGDeviceLockTests(TestCase):
    """Eine Sperre endet nur durch Freigabe nach Abschluss aller Mängel."""

    def setUp(self):
        self.station = Station.objects.create(name="RW Sperre", slug="rw-sperre", mpg_enabled=True)
        self.lead = User.objects.create_user(username="lead", password="x-test-pass-123")
        Membership.objects.create(user=self.lead, station=self.station, role=Membership.Role.SHIFT_LEAD)
        self.member = User.objects.create_user(username="member", password="x-test-pass-123")
        Membership.objects.create(user=self.member, station=self.station, role=Membership.Role.MEMBER)
        self.device = MedicalDevice.objects.create(station=self.station, slug="defi-1", name="Defi 1")

    def _lock(self):
        self.client.force_login(self.member)
        self.client.post(
            reverse("mpg_device_defect", args=[self.device.slug]),
            data={"title": "Display dunkel", "description": "startet nicht", "priority": "urgent"},
        )
        self.device.refresh_from_db()
        return Defect.objects.get(medical_device=self.device)

    def _close(self, defect):
        self.client.force_login(self.lead)
        self.client.post(
            reverse("defect_detail_web", args=[defect.pk]),
            data={"action": "status", "status": Defect.Status.DONE},
        )

    def _release(self, user, **extra):
        self.client.force_login(user)
        data = {"battery_ok": "on", "visual_ok": "on", "function_ok": "on", "notes": "Akku getauscht"}
        data.update(extra)
        return self.client.post(reverse("mpg_device_release", args=[self.device.slug]), data=data)

    def test_quick_check_does_not_lift_a_lock(self):
        self._lock()
        self.client.post(reverse("mpg_routine_check", args=[self.device.slug]), data={"quick_pass": "1"})
        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.OOB)

    def test_release_requires_closed_defects_and_lead(self):
        defect = self._lock()
        self._release(self.lead)
        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.OOB)

        self._close(defect)
        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.OOB)

        self._release(self.member)
        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.OOB)

        self._release(self.lead, function_ok="")
        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.OOB)

        self._release(self.lead)
        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.READY)
        release_check = self.device.routine_checks.latest("checked_at")
        self.assertTrue(release_check.passed)
        self.assertEqual(release_check.performed_by, self.lead)
        self.assertIn("Akku getauscht", release_check.notes)

    def test_edit_form_cannot_unlock(self):
        self._lock()
        self.client.force_login(self.lead)
        form_data = {
            "name": self.device.name,
            "category": self.device.category,
            "risk_class": self.device.risk_class,
            "location": "Wache",
            "current_status": MedicalDevice.Status.READY,
            "stk_interval_months": 24,
            "dguv_interval_months": 12,
        }
        resp = self.client.post(reverse("mpg_device_edit", args=[self.device.slug]), data=form_data)
        self.assertEqual(resp.status_code, 200)
        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.OOB)

    def test_status_is_mirrored_to_station_asset(self):
        from core.wachalltag_models import StationAsset

        asset = StationAsset.objects.create(
            station=self.station, asset_id=self.device.slug, label="Defi 1", kind=StationAsset.Kind.DEVICE,
        )
        defect = self._lock()
        asset.refresh_from_db()
        self.assertEqual(asset.status, StationAsset.Status.OOB)

        # Freigabe über „Geräte & Fahrzeuge“ ist bei offenem Mangel blockiert.
        self.client.force_login(self.lead)
        self.client.post(
            reverse("assets_inventory_web"),
            data={"action": "asset-status", "asset_id": asset.asset_id, "status": "ready"},
        )
        asset.refresh_from_db()
        self.device.refresh_from_db()
        self.assertEqual(asset.status, StationAsset.Status.OOB)
        self.assertEqual(self.device.current_status, MedicalDevice.Status.OOB)

        self._close(defect)
        self._release(self.lead)
        asset.refresh_from_db()
        self.assertEqual(asset.status, StationAsset.Status.READY)

        # Werkstatt im Wachalltag erscheint im Medizinproduktebuch als Wartung.
        self.client.post(
            reverse("assets_inventory_web"),
            data={"action": "asset-status", "asset_id": asset.asset_id, "status": "workshop"},
        )
        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.MAINTENANCE)
