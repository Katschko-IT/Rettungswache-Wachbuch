import base64
import json
from datetime import timedelta
from io import BytesIO

from PIL import Image
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from core.api.views import hash_api_token
from core.errors import build_error_payload
from core.models import ApiToken, Checklist, HandoverEntry, Membership, Station
from core.wachalltag_models import (
    AssetEvent,
    ChecklistSchedule,
    Defect,
    DefectEvent,
    HandoverAck,
    InventoryEvent,
    InventoryItem,
    StationAsset,
)


class WachalltagApiTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Wache Nord", slug="wache-nord", checklists_enabled=True)
        self.user = User.objects.create_user(username="michael", password="secret-test-password")
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.SHIFT_LEAD)
        self.raw_token = "wb_test_wachalltag_token_1234567890"
        ApiToken.objects.create(
            user=self.user,
            label="Tests",
            token_prefix=self.raw_token[:11],
            token_hash=hash_api_token(self.raw_token),
            scopes=[
                "read:me",
                "read:handovers",
                "write:handovers",
                "read:calendar",
                "write:calendar",
                "read:coffee",
                "write:coffee",
                "read:checklists",
                "write:checklists",
            ],
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.auth = {"HTTP_AUTHORIZATION": f"Token {self.raw_token}"}

    def _json(self, method, path, body=None):
        return getattr(self.client, method)(
            path,
            data=json.dumps(body or {}),
            content_type="application/json",
            **self.auth,
        )

    def _image_bytes(self, image_format="JPEG"):
        output = BytesIO()
        mode = "RGBA" if image_format == "PNG" else "RGB"
        Image.new(mode, (4, 4), color="white").save(output, format=image_format)
        return output.getvalue()

    def test_canonical_errors_and_mfa_code_are_stable(self):
        response = self.client.get("/api/v1/me/")
        self.assertEqual(response.status_code, 401)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "auth_required")
        self.assertTrue(payload["error"]["correlation_id"])
        self.assertEqual(build_error_payload("mfa_required")["error"]["code"], "mfa_required")
        self.assertEqual(build_error_payload("mfa_setup_required")["error"]["code"], "mfa_setup_required")

    def test_discovery_and_me_advertise_real_capabilities(self):
        discovery = self.client.get("/api/v1/").json()
        self.assertTrue(discovery["capabilities"]["defects"])
        self.assertEqual(discovery["endpoints"]["inventory"], "/api/v1/inventory/")
        response = self.client.get("/api/v1/me/", **self.auth)
        self.assertEqual(response.status_code, 200)
        modules = response.json()["membership"]["station"]["modules"]
        self.assertTrue(modules["defects"])
        self.assertTrue(modules["assets"])
        self.assertTrue(modules["inventory"])
        self.assertTrue(modules["reports"])

    def test_defect_workflow_is_persistent_audited_and_station_scoped(self):
        create = self._json(
            "post",
            "/api/v1/defects/",
            {
                "title": "Defi-Akku prüfen",
                "description": "Kapazität auffällig",
                "asset_ref": "RTW 1 / Defi",
                "priority": "urgent",
                "category": "device",
                "owner": "michael",
                "due_at": (timezone.now() + timedelta(hours=4)).isoformat(),
            },
        )
        self.assertEqual(create.status_code, 201)
        defect_id = create.json()["id"]
        self.assertEqual(DefectEvent.objects.filter(defect_id=defect_id).count(), 1)

        update = self._json("post", f"/api/v1/defects/{defect_id}/status/", {"status": "done"})
        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.json()["status"], "done")
        self.assertEqual(DefectEvent.objects.filter(defect_id=defect_id).count(), 2)

        other = Station.objects.create(name="Wache Süd", slug="wache-sued")
        Defect.objects.create(
            station=other,
            title="Unsichtbar",
            created_by=self.user,
        )
        listed = self.client.get("/api/v1/defects/", **self.auth).json()["results"]
        self.assertFalse(any(row["title"] == "Unsichtbar" for row in listed))

    def test_assets_inventory_and_ack_workflows(self):
        asset = self._json(
            "post",
            "/api/v1/assets/",
            {"id": "rtw-1", "label": "RTW 1", "kind": "vehicle"},
        )
        self.assertEqual(asset.status_code, 201)
        changed = self._json(
            "post",
            "/api/v1/assets/rtw-1/status/",
            {"status": "limited", "note": "Klimaanlage prüfen"},
        )
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.json()["status"], "limited")
        self.assertGreaterEqual(AssetEvent.objects.count(), 2)

        inventory = self._json(
            "post",
            "/api/v1/inventory/",
            {"id": "funk-a", "label": "Funkgerät A", "kind": "device"},
        )
        self.assertEqual(inventory.status_code, 201)
        checkout = self._json("post", "/api/v1/inventory/funk-a/checkout/")
        self.assertEqual(checkout.status_code, 200)
        self.assertEqual(checkout.json()["holder"], "michael")
        checkin = self._json("post", "/api/v1/inventory/funk-a/checkin/")
        self.assertEqual(checkin.status_code, 200)
        self.assertIsNone(checkin.json()["holder"])
        self.assertEqual(InventoryEvent.objects.filter(item__item_id="funk-a").count(), 2)

        handover = HandoverEntry.objects.create(
            station=self.station,
            category=HandoverEntry.Category.MATERIAL,
            priority=HandoverEntry.Priority.IMPORTANT,
            status=HandoverEntry.Status.OPEN,
            title="Materialübergabe",
            details="Bitte prüfen",
            author=self.user,
        )
        first = self._json("post", f"/api/v1/handovers/{handover.pk}/ack/")
        second = self._json("post", f"/api/v1/handovers/{handover.pk}/ack/")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(HandoverAck.objects.filter(handover=handover, user=self.user).count(), 1)

    def test_recurring_checklist_is_returned_and_advanced(self):
        checklist = Checklist.objects.create(station=self.station, title="Fahrzeugcheck")
        due = timezone.now() - timedelta(hours=1)
        schedule_response = self._json(
            "put",
            f"/api/v1/checklisten/{checklist.pk}/schedule/",
            {"interval": "daily", "due_next": due.isoformat()},
        )
        self.assertEqual(schedule_response.status_code, 200)
        listed = self.client.get("/api/v1/checklisten/", **self.auth).json()["results"]
        row = next(item for item in listed if item["id"] == checklist.pk)
        self.assertEqual(row["interval"], "daily")
        self.assertTrue(row["overdue"])

        complete = self._json("post", f"/api/v1/checklisten/{checklist.pk}/abschluss/")
        self.assertEqual(complete.status_code, 201)
        schedule = ChecklistSchedule.objects.get(checklist=checklist)
        self.assertGreater(schedule.due_next, timezone.now())
        self.assertEqual(complete.json()["interval"], "daily")

    def test_very_overdue_recurring_check_fast_forwards_to_future(self):
        checklist = Checklist.objects.create(station=self.station, title="Monatscheck")
        due = timezone.now() - timedelta(days=95)
        schedule_response = self._json(
            "put",
            f"/api/v1/checklisten/{checklist.pk}/schedule/",
            {"interval": "monthly", "due_next": due.isoformat()},
        )
        self.assertEqual(schedule_response.status_code, 200)

        complete = self._json("post", f"/api/v1/checklisten/{checklist.pk}/abschluss/")
        self.assertEqual(complete.status_code, 201)
        schedule = ChecklistSchedule.objects.get(checklist=checklist)
        self.assertGreater(schedule.due_next, timezone.now())
        self.assertFalse(complete.json()["overdue"])

    def test_defect_photo_roundtrip_with_size_type_and_decode_guard(self):
        defect = Defect.objects.create(station=self.station, title="Foto-Test", created_by=self.user)
        jpeg = self._image_bytes("JPEG")
        upload = self._json(
            "post",
            f"/api/v1/defects/{defect.pk}/attachments/",
            {
                "filename": "mangel.jpg",
                "content_type": "image/jpeg",
                "data_base64": base64.b64encode(jpeg).decode("ascii"),
            },
        )
        self.assertEqual(upload.status_code, 201)
        payload = upload.json()
        self.assertEqual(payload["content_type"], "image/jpeg")
        self.assertTrue(payload["filename"].endswith(".jpg"))
        self.assertLessEqual(payload["size"], 2 * 1024 * 1024)
        attachment_id = payload["id"]
        download = self.client.get(f"/api/v1/attachments/{attachment_id}/", **self.auth)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download["Content-Type"], "image/jpeg")
        self.assertNotEqual(download.content, jpeg)
        with Image.open(BytesIO(download.content)) as sanitized:
            sanitized.load()
            self.assertEqual(sanitized.format, "JPEG")
            self.assertEqual(sanitized.size, (4, 4))
            self.assertEqual(len(sanitized.getexif()), 0)

        bad = self._json(
            "post",
            f"/api/v1/defects/{defect.pk}/attachments/",
            {
                "filename": "fake.jpg",
                "content_type": "image/jpeg",
                "data_base64": base64.b64encode(b"\xff\xd8\xffnot-a-real-jpeg").decode("ascii"),
            },
        )
        self.assertEqual(bad.status_code, 415)

    def test_defect_photo_count_quota_prevents_unbounded_database_growth(self):
        defect = Defect.objects.create(station=self.station, title="Foto-Kontingent", created_by=self.user)
        jpeg = self._image_bytes("JPEG")
        payload = {
            "filename": "mangel.jpg",
            "content_type": "image/jpeg",
            "data_base64": base64.b64encode(jpeg).decode("ascii"),
        }
        for index in range(8):
            response = self._json(
                "post",
                f"/api/v1/defects/{defect.pk}/attachments/",
                {**payload, "filename": f"mangel-{index}.jpg"},
            )
            self.assertEqual(response.status_code, 201)
        ninth = self._json(
            "post",
            f"/api/v1/defects/{defect.pk}/attachments/",
            {**payload, "filename": "mangel-9.jpg"},
        )
        self.assertEqual(ninth.status_code, 409)
        self.assertEqual(ninth.json()["error"]["code"], "conflict")
        self.assertEqual(defect.attachments.count(), 8)

    def test_defect_pdf_attachment_is_accepted_and_spoofed_pdf_rejected(self):
        defect = Defect.objects.create(station=self.station, title="PDF-Test", created_by=self.user)
        pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
        upload = self._json("post", f"/api/v1/defects/{defect.pk}/attachments/", {
            "filename": "pruefbericht.pdf",
            "content_type": "application/pdf",
            "data_base64": base64.b64encode(pdf).decode("ascii"),
        })
        self.assertEqual(upload.status_code, 201)
        spoofed = self._json("post", f"/api/v1/defects/{defect.pk}/attachments/", {
            "filename": "fake.pdf",
            "content_type": "application/pdf",
            "data_base64": base64.b64encode(b"<html>kein pdf</html>").decode("ascii"),
        })
        self.assertEqual(spoofed.status_code, 415)
        self.assertEqual(spoofed.json()["error"]["code"], "unsupported_media_type")

    def test_token_can_be_revoked_after_membership_was_removed(self):
        Membership.objects.filter(user=self.user).update(is_active=False)
        self.assertEqual(self.client.get("/api/v1/me/", **self.auth).status_code, 403)
        response = self.client.delete("/api/v1/token/", **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ApiToken.objects.get(token_hash=hash_api_token(self.raw_token)).is_active)
        self.assertEqual(self.client.delete("/api/v1/token/", **self.auth).status_code, 401)

    def test_reports_aggregate_real_station_state(self):
        Defect.objects.create(station=self.station, title="Offen", created_by=self.user, due_at=timezone.now() - timedelta(days=1))
        StationAsset.objects.create(station=self.station, asset_id="rtw-1", label="RTW 1", kind="vehicle", status="ready")
        StationAsset.objects.create(station=self.station, asset_id="rtw-2", label="RTW 2", kind="vehicle", status="limited")
        InventoryItem.objects.create(station=self.station, item_id="key-1", label="Schlüssel 1", kind="key")
        response = self.client.get("/api/v1/reports/", **self.auth)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["open_defects"], 1)
        self.assertEqual(data["overdue_defects"], 1)
        self.assertEqual(data["asset_ready_percent"], 50)

    def test_server_rendered_wachalltag_pages_are_available(self):
        self.client.force_login(self.user)
        for path in ["/maengel/", "/geraete/", "/checklisten/intervalle/", "/auswertung/"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
