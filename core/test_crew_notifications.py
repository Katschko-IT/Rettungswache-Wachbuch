import json
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.api.views import hash_api_token
from core.crew_notifications import crew_for_vehicle, notify_ready_vehicles
from core.fleet_models import DisinfectantMaster, DisinfectionProtocol, Vehicle, VehicleHandover
from core.models import ApiToken, AuditEvent, Membership, PushOutbox, PushSubscription, Station
from core.notification_models import MobilePushDevice, UserNotification


class CrewNotificationTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache Crew", slug="wache-crew", fleet_enabled=True)
        self.crew = self._member("besatzung")
        self.disinfector = self._member("desinfektion")
        self.other = self._member("unbeteiligt")
        self.vehicle = Vehicle.objects.create(
            station=self.station, slug="rtw-c", call_sign="RTW C", license_plate="C-1",
        )
        self.agent = DisinfectantMaster.objects.create(station=self.station, name="Mittel")
        VehicleHandover.objects.create(station=self.station, vehicle=self.vehicle, crew_member=self.crew, mileage=1000)
        DisinfectionProtocol.objects.create(
            station=self.station, vehicle=self.vehicle, performed_by=self.disinfector,
            disinfectant=self.agent, exposure_minutes=15,
            started_at=timezone.now() - timedelta(minutes=20),
        )
        self.vehicle.refresh_from_db()

    def _member(self, username, role=Membership.Role.MEMBER):
        user = User.objects.create_user(username, password="pw-123456789")
        Membership.objects.create(user=user, station=self.station, role=role)
        return user

    def test_crew_is_recent_handover_plus_disinfector(self):
        crew = {user.username for user in crew_for_vehicle(self.vehicle)}
        self.assertEqual(crew, {"besatzung", "desinfektion"})

    def test_old_handover_and_inactive_member_are_not_crew(self):
        VehicleHandover.objects.filter(crew_member=self.crew).update(
            performed_at=timezone.now() - timedelta(hours=30),
        )
        Membership.objects.filter(user=self.disinfector).update(is_active=False)
        self.assertEqual(crew_for_vehicle(self.vehicle), [])

    def test_expired_lock_notifies_crew_once_without_status_change(self):
        self.assertEqual(notify_ready_vehicles(), 2)
        self.assertEqual(notify_ready_vehicles(), 0)  # idempotent
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.tactical_status, Vehicle.TacticalStatus.DISINFECTION)
        recipients = set(UserNotification.objects.values_list("user__username", flat=True))
        self.assertEqual(recipients, {"besatzung", "desinfektion"})
        note = UserNotification.objects.first()
        self.assertIn("RTW C", note.title)
        self.assertIn("selbst freigeben", note.body)
        self.assertEqual(AuditEvent.objects.filter(action="fleet.disinfection_crew_notified").count(), 1)

    def test_running_lock_does_not_notify_yet(self):
        self.vehicle.disinfection_locked_until = timezone.now() + timedelta(minutes=5)
        self.vehicle.save(update_fields=["disinfection_locked_until"])
        self.assertEqual(notify_ready_vehicles(), 0)

    def test_new_disinfection_produces_a_new_notification(self):
        notify_ready_vehicles()
        DisinfectionProtocol.objects.create(
            station=self.station, vehicle=self.vehicle, performed_by=self.disinfector,
            disinfectant=self.agent, exposure_minutes=10,
            started_at=timezone.now() - timedelta(minutes=11),
        )
        self.assertEqual(notify_ready_vehicles(), 2)

    @override_settings(WEB_PUSH_ENABLED=True, PUSH_RELAY_URL="https://relay.example.org/v1/push")
    def test_channels_are_queued_for_web_and_app(self):
        PushSubscription.objects.create(
            user=self.crew, station=self.station, endpoint="https://fcm.googleapis.com/x",
            p256dh="k", auth="a",
        )
        MobilePushDevice.objects.create(user=self.crew, station=self.station, platform="ios", token="t1")
        notify_ready_vehicles()
        rows = PushOutbox.objects.filter(user=self.crew)
        self.assertEqual(rows.filter(subscription__isnull=False).count(), 1)
        self.assertEqual(rows.filter(device__isnull=False).count(), 1)
        self.assertFalse(PushOutbox.objects.filter(user=self.other).exists())

    def test_no_push_rows_without_configured_channels(self):
        MobilePushDevice.objects.create(user=self.crew, station=self.station, platform="ios", token="t1")
        notify_ready_vehicles()
        self.assertFalse(PushOutbox.objects.exists())
        self.assertTrue(UserNotification.objects.filter(user=self.crew).exists())

    def test_manual_release_marks_notifications_done(self):
        notify_ready_vehicles()
        Membership.objects.filter(user=self.crew).update(role=Membership.Role.SHIFT_LEAD)
        self.client.force_login(self.crew)
        self.client.post(reverse("fleet_vehicle_status_change", args=[self.vehicle.slug]), {"status": "1"})
        self.assertFalse(UserNotification.objects.filter(read_at__isnull=True).exists())

    def test_dashboard_shows_personal_notification(self):
        notify_ready_vehicles()
        self.client.force_login(self.crew)
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn("Für dich", html)
        self.assertIn("RTW C: Einwirkzeit abgelaufen", html)
        self.client.force_login(self.other)
        self.assertNotIn("Für dich", self.client.get(reverse("dashboard")).content.decode())


class CrewNotificationApiTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache API", slug="wache-api", fleet_enabled=True)
        self.user = User.objects.create_user("api-crew", password="pw-123456789")
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.MEMBER)
        raw = "wb_test_crew_token_1234567890"
        ApiToken.objects.create(
            user=self.user, label="t", token_prefix=raw[:11], token_hash=hash_api_token(raw),
            scopes=["read:me"], expires_at=timezone.now() + timedelta(days=1),
        )
        self.auth = {"HTTP_AUTHORIZATION": f"Token {raw}"}
        self.vehicle = Vehicle.objects.create(
            station=self.station, slug="rtw-a", call_sign="RTW A", license_plate="A-1",
        )
        VehicleHandover.objects.create(station=self.station, vehicle=self.vehicle, crew_member=self.user, mileage=1000)

    def test_vehicle_locks_list_only_own_running_locks(self):
        until = timezone.now() + timedelta(minutes=10)
        Vehicle.objects.filter(pk=self.vehicle.pk).update(
            tactical_status=Vehicle.TacticalStatus.DISINFECTION, disinfection_locked_until=until,
        )
        other = Vehicle.objects.create(
            station=self.station, slug="rtw-b", call_sign="RTW B", license_plate="B-1",
            tactical_status=Vehicle.TacticalStatus.DISINFECTION, disinfection_locked_until=until,
        )
        data = self.client.get("/api/v1/fahrzeuge/sperren/", **self.auth).json()
        self.assertEqual([item["call_sign"] for item in data["results"]], ["RTW A"])
        self.assertNotIn(other.call_sign, json.dumps(data))
        self.assertIn("key", data["results"][0])

    def test_inbox_and_mark_read(self):
        Vehicle.objects.filter(pk=self.vehicle.pk).update(
            tactical_status=Vehicle.TacticalStatus.DISINFECTION,
            disinfection_locked_until=timezone.now() - timedelta(minutes=1),
        )
        notify_ready_vehicles()
        data = self.client.get("/api/v1/benachrichtigungen/", **self.auth).json()
        self.assertEqual(data["unread_count"], 1)
        note_id = data["results"][0]["id"]
        read = self.client.post(f"/api/v1/benachrichtigungen/{note_id}/gelesen/", **self.auth)
        self.assertTrue(read.json()["read"])
        self.assertEqual(self.client.get("/api/v1/benachrichtigungen/", **self.auth).json()["unread_count"], 0)

    def test_foreign_notification_is_not_found(self):
        stranger = User.objects.create_user("fremd", password="pw-123456789")
        note = UserNotification.objects.create(
            station=self.station, user=stranger, kind="vehicle_ready", title="x", dedupe_key="k",
        )
        resp = self.client.post(f"/api/v1/benachrichtigungen/{note.pk}/gelesen/", **self.auth)
        self.assertEqual(resp.status_code, 404)

    def test_push_device_registration(self):
        body = json.dumps({"platform": "android", "token": "fcm-token-1", "app_version": "1.0.1"})
        created = self.client.post("/api/v1/push/geraete/", body, content_type="application/json", **self.auth)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(MobilePushDevice.objects.get().user, self.user)
        bad = self.client.post(
            "/api/v1/push/geraete/", json.dumps({"platform": "symbian", "token": "x"}),
            content_type="application/json", **self.auth,
        )
        self.assertEqual(bad.status_code, 400)
        removed = self.client.delete("/api/v1/push/geraete/", body, content_type="application/json", **self.auth)
        self.assertFalse(removed.json()["registered"])
        self.assertFalse(MobilePushDevice.objects.exists())


@override_settings(PUSH_RELAY_URL="https://relay.example.org/v1/push", PUSH_RELAY_TOKEN="secret")
class PushRelayDeliveryTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache Relay", slug="wache-relay")
        self.user = User.objects.create_user("relay", password="pw-123456789")
        self.device = MobilePushDevice.objects.create(
            user=self.user, station=self.station, platform="ios", token="apns-1",
        )
        self.row = PushOutbox.objects.create(
            station=self.station, user=self.user, device=self.device,
            payload={"title": "RTW: Einwirkzeit abgelaufen", "body": "Bitte freigeben", "url": "/x/"},
        )

    def _response(self, status):
        response = mock.MagicMock()
        response.status = status
        response.__enter__.return_value = response
        return response

    def test_relay_success_marks_sent_and_sends_minimal_payload(self):
        from core.management.commands.push_worker import process_once

        with mock.patch("urllib.request.urlopen", return_value=self._response(202)) as urlopen:
            process_once()
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, PushOutbox.Status.SENT)
        request = urlopen.call_args[0][0]
        sent = json.loads(request.data)
        self.assertEqual(set(sent), {"platform", "token", "title", "body", "url"})
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")

    def test_gone_token_removes_device(self):
        import urllib.error

        from core.management.commands.push_worker import process_once

        error = urllib.error.HTTPError("https://relay.example.org", 410, "gone", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=error):
            process_once()
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, PushOutbox.Status.DISCARDED)
        self.assertFalse(MobilePushDevice.objects.exists())
