from datetime import timedelta
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.display import display_payload
from core.models import AuditEvent, Membership, Station
from core.mpg_models import DeviceRoutineCheck, DeviceTrainingRecord, MaintenanceLog, MedicalDevice
from core.notification_models import UserNotification
from core.wachalltag_models import Defect, DefectEvent


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


class MPGTrainingAppendOnlyTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache Schulung", slug="wache-schulung", mpg_enabled=True)
        self.user = User.objects.create_user(username="retter", password="pw-123456789")
        self.lead = User.objects.create_user(username="mpg-lead", password="pw-123456789")
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.MEMBER)
        Membership.objects.create(user=self.lead, station=self.station, role=Membership.Role.SHIFT_LEAD)
        self.device = MedicalDevice.objects.create(station=self.station, slug="medumat-1", name="MEDUMAT Standard")
        self.client.force_login(self.lead)

    def test_training_record_cannot_be_updated_or_deleted(self):
        record = DeviceTrainingRecord.objects.create(
            station=self.station,
            device=self.device,
            trainee=self.user,
            instructor="Gerätebeauftragter",
            notes="Erstunterweisung",
        )
        record.notes = "Korrekturversuch"
        with self.assertRaisesMessage(ValidationError, "Einweisungsnachweise dürfen nicht verändert werden."):
            record.save()

        with self.assertRaisesMessage(ValidationError, "Einweisungsnachweise dürfen nicht gelöscht werden."):
            record.delete()

    def test_multiple_trainings_can_be_appended_for_same_user_and_device(self):
        # 1. Manuell angelegt
        DeviceTrainingRecord.objects.create(
            station=self.station,
            device=self.device,
            trainee=self.user,
            instructor="Erstschulung",
            trained_at=timezone.localdate() - timedelta(days=365),
        )
        # 2. Einzelschulung per Formular
        resp = self.client.post(
            reverse("mpg_training_create", args=[self.device.slug]),
            data={
                "trainee": self.user.id,
                "instructor": "Auffrischung",
                "trained_at": (timezone.localdate() - timedelta(days=30)).isoformat(),
                "notes": "Re-Zertifizierung",
            },
        )
        self.assertEqual(resp.status_code, 302)

        # 3. Gruppenschulung per Formular
        resp = self.client.post(
            reverse("mpg_training_create", args=[self.device.slug]),
            data={
                "trainees": [self.user.id],
                "instructor": "Jahresunterweisung",
                "trained_at": timezone.localdate().isoformat(),
                "notes": "Gruppenfortbildung",
            },
        )
        self.assertEqual(resp.status_code, 302)

        records = DeviceTrainingRecord.objects.filter(device=self.device, trainee=self.user)
        self.assertEqual(records.count(), 3)
        self.assertEqual(records.first().instructor, "Jahresunterweisung")

    def test_validity_and_expiration(self):
        today = timezone.localdate()
        rec_unlimited = DeviceTrainingRecord.objects.create(
            station=self.station, device=self.device, trainee=self.user, instructor="X", valid_until=None
        )
        self.assertTrue(rec_unlimited.is_valid)

        rec_future = DeviceTrainingRecord.objects.create(
            station=self.station, device=self.device, trainee=self.user, instructor="X",
            valid_until=today + timedelta(days=30),
        )
        self.assertTrue(rec_future.is_valid)

        rec_expired = DeviceTrainingRecord.objects.create(
            station=self.station, device=self.device, trainee=self.user, instructor="X",
            valid_until=today - timedelta(days=1),
        )
        self.assertFalse(rec_expired.is_valid)

    def test_geraetepass_displays_validity_and_latest_record(self):
        today = timezone.localdate()
        # Frühere abgelaufene Schulung
        DeviceTrainingRecord.objects.create(
            station=self.station, device=self.device, trainee=self.user, instructor="Alt",
            trained_at=today - timedelta(days=400),
            valid_until=today - timedelta(days=35),
        )
        # Neuere gültige Schulung
        DeviceTrainingRecord.objects.create(
            station=self.station, device=self.device, trainee=self.user, instructor="Neu",
            trained_at=today - timedelta(days=30),
            valid_until=today + timedelta(days=330),
        )
        self.client.force_login(self.user)
        resp = self.client.get(reverse("mpg_geraetepass"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Gültig")
        self.assertContains(resp, "Neu")


class MPG5MinRoutineCheckStornoTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache Storno", slug="wache-storno", mpg_enabled=True)
        self.user = User.objects.create_user(username="pruefer", password="pw-123456789")
        self.other_user = User.objects.create_user(username="fremder", password="pw-123456789")
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.MEMBER)
        Membership.objects.create(user=self.other_user, station=self.station, role=Membership.Role.MEMBER)
        self.device = MedicalDevice.objects.create(station=self.station, slug="defi-storno", name="Defi Storno")
        self.client.force_login(self.user)

    def test_storno_within_5_minutes_creates_append_only_record(self):
        check = DeviceRoutineCheck.objects.create(
            station=self.station,
            device=self.device,
            performed_by=self.user,
            battery_ok=True,
            visual_ok=True,
            function_ok=True,
            notes="Erste Kontrolle",
        )
        url = reverse("mpg_routine_check_storno", args=[self.device.slug, check.pk])
        resp = self.client.post(url, data={"reason": "Verklickt"})
        self.assertEqual(resp.status_code, 302)

        # Original unverändert
        check_fresh = DeviceRoutineCheck.objects.get(pk=check.pk)
        self.assertFalse(check_fresh.is_cancellation)
        self.assertTrue(check_fresh.is_cancelled)

        # Neuer Storno-Datensatz
        storno = DeviceRoutineCheck.objects.filter(cancels_check=check).get()
        self.assertTrue(storno.is_cancellation)
        self.assertEqual(storno.performed_by, self.user)
        self.assertIn("5-Minuten-Storno", storno.notes)
        self.assertIn("Verklickt", storno.notes)

        # Audit Event
        event = AuditEvent.objects.filter(action="mpg.routine_check_cancelled").latest("created_at")
        self.assertEqual(event.actor, self.user)
        self.assertEqual(event.metadata["cancelled_check_id"], check.pk)
        self.assertEqual(event.metadata["storno_check_id"], storno.pk)

    def test_storno_by_pk_url_works(self):
        check = DeviceRoutineCheck.objects.create(
            station=self.station, device=self.device, performed_by=self.user,
        )
        url = reverse("mpg_routine_check_storno_by_pk", kwargs={"pk": self.device.pk, "check_id": check.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(DeviceRoutineCheck.objects.filter(cancels_check=check).exists())

    def test_storno_reverts_failed_check_defect_and_status(self):
        # Kontrolle nicht bestanden -> Gerät gesperrt und Defect erstellt
        check = DeviceRoutineCheck(
            station=self.station,
            device=self.device,
            performed_by=self.user,
            battery_ok=False,
            visual_ok=True,
            function_ok=True,
            notes="Akku leer",
        )
        check.save()
        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.OOB)
        defect = Defect.objects.filter(medical_device=self.device, status=Defect.Status.OPEN).get()

        # Storno
        resp = self.client.post(reverse("mpg_routine_check_storno", args=[self.device.slug, check.pk]))
        self.assertEqual(resp.status_code, 302)

        defect.refresh_from_db()
        self.assertEqual(defect.status, Defect.Status.DONE)
        self.assertTrue(DefectEvent.objects.filter(defect=defect, to_status=Defect.Status.DONE).exists())

        self.device.refresh_from_db()
        self.assertEqual(self.device.current_status, MedicalDevice.Status.READY)

    def test_storno_rejected_after_5_minutes(self):
        check = DeviceRoutineCheck.objects.create(
            station=self.station, device=self.device, performed_by=self.user,
        )
        # 6 Minuten in die Vergangenheit datieren
        DeviceRoutineCheck.objects.filter(pk=check.pk).update(
            checked_at=timezone.now() - timedelta(minutes=6)
        )
        resp = self.client.post(reverse("mpg_routine_check_storno", args=[self.device.slug, check.pk]))
        self.assertEqual(resp.status_code, 302)
        messages = [m.message for m in get_messages(resp.wsgi_request)]
        self.assertTrue(any("5 Minuten" in m for m in messages))
        self.assertFalse(DeviceRoutineCheck.objects.filter(is_cancellation=True).exists())

    def test_storno_rejected_for_different_user(self):
        check = DeviceRoutineCheck.objects.create(
            station=self.station, device=self.device, performed_by=self.user,
        )
        self.client.force_login(self.other_user)
        resp = self.client.post(reverse("mpg_routine_check_storno", args=[self.device.slug, check.pk]))
        self.assertEqual(resp.status_code, 302)
        messages = [m.message for m in get_messages(resp.wsgi_request)]
        self.assertTrue(any("eigene Kontrolle" in m for m in messages))
        self.assertFalse(DeviceRoutineCheck.objects.filter(is_cancellation=True).exists())

    def test_storno_rejected_if_already_cancelled_or_cancellation_itself(self):
        check = DeviceRoutineCheck.objects.create(
            station=self.station, device=self.device, performed_by=self.user,
        )
        # Erste Storno
        self.client.post(reverse("mpg_routine_check_storno", args=[self.device.slug, check.pk]))
        storno = DeviceRoutineCheck.objects.get(cancels_check=check)

        # Zweite Storno auf dieselbe Kontrolle
        resp = self.client.post(reverse("mpg_routine_check_storno", args=[self.device.slug, check.pk]))
        messages = [m.message for m in get_messages(resp.wsgi_request)]
        self.assertTrue(any("bereits storniert" in m for m in messages))

        # Storno auf den Storno-Eintrag selbst
        resp = self.client.post(reverse("mpg_routine_check_storno", args=[self.device.slug, storno.pk]))
        messages = [m.message for m in get_messages(resp.wsgi_request)]
        self.assertTrue(any("Storno-Eintrag kann nicht storniert werden" in m for m in messages))


class MPGTrainingRequirementWarningTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(
            name="Wache Einweisungspflicht",
            slug="wache-pflicht",
            mpg_enabled=True,
            mpg_training_required=True,
        )
        self.admin = User.objects.create_user(username="station-admin", password="pw-123456789")
        self.mpg_lead = User.objects.create_user(username="mpg-beauftragter", password="pw-123456789")
        self.regular = User.objects.create_user(username="sanitaeter", password="pw-123456789")
        self.untrained = User.objects.create_user(username="neuling", password="pw-123456789")

        Membership.objects.create(user=self.admin, station=self.station, role=Membership.Role.ADMIN)
        Membership.objects.create(user=self.mpg_lead, station=self.station, role=Membership.Role.MEMBER, is_mpg_lead=True)
        Membership.objects.create(user=self.regular, station=self.station, role=Membership.Role.MEMBER)
        Membership.objects.create(user=self.untrained, station=self.station, role=Membership.Role.MEMBER)

        self.device = MedicalDevice.objects.create(
            station=self.station, slug="defi-pflicht", name="Defi Pflicht", requires_training=True,
        )
        self.check_url = reverse("mpg_routine_check", args=[self.device.slug])

    def test_routine_check_without_training_warns_user_and_notifies_leads(self):
        self.client.force_login(self.untrained)
        resp = self.client.post(self.check_url, data={"quick_pass": "1"})
        self.assertEqual(resp.status_code, 302)

        messages = [m.message for m in get_messages(resp.wsgi_request)]
        self.assertTrue(any("keine gültige Geräteeinweisung" in m for m in messages))

        # Check wurde trotzdem angelegt (append-only)
        self.assertTrue(DeviceRoutineCheck.objects.filter(device=self.device, performed_by=self.untrained).exists())

        # Benachrichtigung an Admin und MPG-Beauftragten
        notes = UserNotification.objects.filter(kind=UserNotification.Kind.MPG_TRAINING_MISSING)
        recipient_ids = set(notes.values_list("user_id", flat=True))
        self.assertEqual(recipient_ids, {self.admin.id, self.mpg_lead.id})
        self.assertNotIn(self.regular.id, recipient_ids)

    def test_routine_check_with_valid_training_produces_no_warning_or_notification(self):
        DeviceTrainingRecord.objects.create(
            station=self.station, device=self.device, trainee=self.regular, instructor="Dozent",
            valid_until=timezone.localdate() + timedelta(days=180),
        )
        self.client.force_login(self.regular)
        resp = self.client.post(self.check_url, data={"quick_pass": "1"})
        self.assertEqual(resp.status_code, 302)

        messages = [m.message for m in get_messages(resp.wsgi_request)]
        self.assertFalse(any("keine gültige Geräteeinweisung" in m for m in messages))
        self.assertFalse(UserNotification.objects.filter(kind=UserNotification.Kind.MPG_TRAINING_MISSING).exists())

    def test_routine_check_with_expired_training_warns_and_notifies(self):
        DeviceTrainingRecord.objects.create(
            station=self.station, device=self.device, trainee=self.regular, instructor="Dozent",
            valid_until=timezone.localdate() - timedelta(days=1),
        )
        self.client.force_login(self.regular)
        resp = self.client.post(self.check_url, data={"quick_pass": "1"})
        self.assertEqual(resp.status_code, 302)

        messages = [m.message for m in get_messages(resp.wsgi_request)]
        self.assertTrue(any("keine gültige Geräteeinweisung" in m for m in messages))
        self.assertTrue(UserNotification.objects.filter(kind=UserNotification.Kind.MPG_TRAINING_MISSING).exists())

    def test_routine_check_with_station_switch_disabled_no_warning(self):
        self.station.mpg_training_required = False
        self.station.save(update_fields=["mpg_training_required"])

        self.client.force_login(self.untrained)
        resp = self.client.post(self.check_url, data={"quick_pass": "1"})
        self.assertEqual(resp.status_code, 302)

        messages = [m.message for m in get_messages(resp.wsgi_request)]
        self.assertFalse(any("keine gültige Geräteeinweisung" in m for m in messages))
        self.assertFalse(UserNotification.objects.filter(kind=UserNotification.Kind.MPG_TRAINING_MISSING).exists())

    def test_routine_check_with_device_requires_training_false_no_warning(self):
        self.device.requires_training = False
        self.device.save(update_fields=["requires_training"])

        self.client.force_login(self.untrained)
        resp = self.client.post(self.check_url, data={"quick_pass": "1"})
        self.assertEqual(resp.status_code, 302)

        messages = [m.message for m in get_messages(resp.wsgi_request)]
        self.assertFalse(any("keine gültige Geräteeinweisung" in m for m in messages))
        self.assertFalse(UserNotification.objects.filter(kind=UserNotification.Kind.MPG_TRAINING_MISSING).exists())
