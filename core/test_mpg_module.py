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
        # 1-Tap Quick Pass
        resp = self.client.post(
            reverse("mpg_routine_check", args=[self.device.slug]),
            data={"quick_pass": "1"},
        )
        self.assertEqual(resp.status_code, 302)
        self.device.refresh_from_db()
        self.assertIsNotNone(self.device.last_routine_check)
        self.assertEqual(self.device.current_status, MedicalDevice.Status.READY)

        # Failed routine check sets device to OOB
        resp_fail = self.client.post(
            reverse("mpg_routine_check", args=[self.device.slug]),
            data={"passed": "", "notes": "Defektes EKG-Kabel"},
        )
        self.assertEqual(resp_fail.status_code, 302)
        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.OOB)

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

    def test_qr_selftest_ingest_pass_and_fail(self):
        # 1. Successful corpuls3 self-test QR payload
        resp_pass = self.client.post(
            reverse("mpg_routine_check", args=[self.device.slug]),
            data={"qr_payload": "CP3;SELFTEST:PASS;DEF:200J;BAT:98%"},
            follow=True,
        )
        self.assertEqual(resp_pass.status_code, 200)
        check_pass = DeviceRoutineCheck.objects.filter(device=self.device, passed=True).latest("checked_at")
        self.assertTrue(check_pass.passed)
        self.assertIn("corpuls3 Selbsttest", check_pass.notes)

        # 2. Failed Weinmann MEDUMAT self-test QR payload
        resp_fail = self.client.post(
            reverse("mpg_routine_check", args=[self.device.slug]),
            data={"qr_payload": "WEINMANN;SELFTEST:FAIL;VALVE_ERROR"},
            follow=True,
        )
        self.assertEqual(resp_fail.status_code, 200)
        check_fail = DeviceRoutineCheck.objects.filter(device=self.device, passed=False).latest("checked_at")
        self.assertFalse(check_fail.passed)
        self.assertIn("FEHLER GEMELDET", check_fail.notes)
