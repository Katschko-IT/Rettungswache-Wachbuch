"""Regression tests for security, worker, and API contract fixes (EGM review).

Covers:
1. push_worker: Transaction split & lock avoidance during network I/O, SSRF protection, redirect rejection (D-01, D-05).
2. Image normalization & EXIF stripping: normalize_image_to_jpeg, DefectAttachment API & Web (D-02).
3. API MFA enforcement & Token expiry: 403 mfa_setup_required on api_token_required, expires_at in me() (D-04, D-07).
4. Station module flags: me() and overview() reflect disabled station module flags (D-10).
"""
from __future__ import annotations

import base64
import ipaddress
import json
from io import BytesIO
from unittest.mock import MagicMock, patch
import urllib.error
import urllib.request

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from core.attachments import normalize_image_to_jpeg
from core.management.commands.push_worker import (
    RejectRedirectHandler,
    _claim_batch,
    _deliver_relay,
    _resolve_public_ips,
    process_once,
)
from core.models import ApiToken, Membership, PushOutbox, Station, TotpDevice
from core.notification_models import MobilePushDevice
from core.test_review_2026_10_24 import _make_token
from core.wachalltag_models import Defect, DefectAttachment


WEB_PUSH_SETTINGS = {
    "VAPID_PRIVATE_KEY": (
        "-----BEGIN EC PRIVATE KEY-----\n"
        "MHcCAQEEIPZ6wz8N5kZ4WjW7qL6tX9sR0yB2pM4aV7eK1wY3oQ0hoAoGCCqGSM49\n"
        "AwEHoUQDQgAE7c+4Ff4NqI1Z8l9aV+mQ6yC4uD1pI8wP0l2hL3tN4sW9yB2pM4aV\n"
        "7eK1wY3oQ0h=\n"
        "-----END EC PRIVATE KEY-----\n"
    ),
    "VAPID_ADMIN_EMAIL": "test@example.com",
    "PUSH_RELAY_ALLOW_LOOPBACK": True,
}


class PushWorkerSecurityTests(TransactionTestCase):
    """D-01 & D-05: Push worker transaction isolation, SSRF checks, and redirect rejection."""

    def setUp(self):
        self.station = Station.objects.create(name="Wache Push", slug="wache-push")
        self.user = User.objects.create_user("pushuser")
        self.device = MobilePushDevice.objects.create(
            station=self.station,
            user=self.user,
            platform="ios",
            token="test-token-123",
            app_version="1.0.0",
        )

    @override_settings(**WEB_PUSH_SETTINGS)
    def test_process_once_does_not_hold_atomic_block_during_delivery(self):
        """Worker must not hold DB transaction locks while making network requests."""
        outbox = PushOutbox.objects.create(
            station=self.station,
            user=self.user,
            device=self.device,
            payload={"title": "Test", "body": "Body"},
            status=PushOutbox.Status.PENDING,
            next_attempt_at=timezone.now() - timezone.timedelta(seconds=1),
        )

        in_atomic_during_delivery = None

        def fake_deliver_relay(row):
            nonlocal in_atomic_during_delivery
            in_atomic_during_delivery = connection.in_atomic_block
            row.status = PushOutbox.Status.SENT
            row.save()

        with patch("core.management.commands.push_worker._deliver_relay", side_effect=fake_deliver_relay):
            count = process_once(batch_size=5)

        self.assertEqual(count, 1)
        self.assertFalse(in_atomic_during_delivery, "Network delivery executed inside transaction.atomic()!")

    def test_claim_batch_sets_lease_timestamp(self):
        """_claim_batch bumps next_attempt_at into future to reserve rows without long locks."""
        now = timezone.now()
        outbox = PushOutbox.objects.create(
            station=self.station,
            user=self.user,
            device=self.device,
            payload={"title": "Test", "body": "Body"},
            status=PushOutbox.Status.PENDING,
            next_attempt_at=now - timezone.timedelta(seconds=10),
        )

        claimed = _claim_batch(now, batch_size=10, lease_seconds=120)
        self.assertEqual(len(claimed), 1)
        self.assertEqual(claimed[0].id, outbox.id)

        # In DB, next_attempt_at should now be >= now + 100s
        outbox.refresh_from_db()
        self.assertGreaterEqual(outbox.next_attempt_at, now + timezone.timedelta(seconds=100))

        # A concurrent worker claiming at 'now' should see 0 rows
        second_claim = _claim_batch(now, batch_size=10)
        self.assertEqual(len(second_claim), 0)

    def test_reject_redirect_handler_blocks_all_redirect_codes(self):
        """RejectRedirectHandler must reject 301, 302, 303, 307, 308."""
        handler = RejectRedirectHandler()
        req = urllib.request.Request("https://example.com/api")
        for code in (301, 302, 303, 307, 308):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                handler.redirect_request(req, None, code, "Redirect", {}, "https://internal.local")
            self.assertEqual(ctx.exception.code, code)

    @override_settings(
        PUSH_RELAY_URL="https://relay.example.com/v1/push",
        PUSH_RELAY_TOKEN="secret-token",
        PUSH_RELAY_ALLOW_LOOPBACK=False,
        DEBUG=False,
    )
    def test_deliver_relay_blocks_private_ip_ssrf(self):
        """_deliver_relay must reject hosts resolving to private/internal IPs."""
        outbox = PushOutbox.objects.create(
            station=self.station,
            user=self.user,
            device=self.device,
            payload={"title": "Test", "body": "Body"},
            status=PushOutbox.Status.PENDING,
            next_attempt_at=timezone.now(),
        )

        # Mock socket.getaddrinfo to return a private IP (e.g. 10.0.0.1)
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("10.0.0.1", 443))]):
            _deliver_relay(outbox)

        outbox.refresh_from_db()
        self.assertEqual(outbox.status, PushOutbox.Status.PENDING)
        self.assertIn("relay address disallowed", outbox.error_message)
        self.assertEqual(outbox.attempts, 1)

    @override_settings(
        PUSH_RELAY_URL="https://relay.example.com/v1/push",
        PUSH_RELAY_TOKEN="secret-token",
        PUSH_RELAY_ALLOW_LOOPBACK=True,
    )
    def test_deliver_relay_rejects_redirect_response(self):
        """When the relay returns a redirect HTTP 302, it is rejected and retried with backoff."""
        outbox = PushOutbox.objects.create(
            station=self.station,
            user=self.user,
            device=self.device,
            payload={"title": "Test", "body": "Body"},
            status=PushOutbox.Status.PENDING,
            next_attempt_at=timezone.now(),
        )

        redirect_error = urllib.error.HTTPError(
            "https://relay.example.com/v1/push", 302, "HTTP redirect 302 denied", {}, None
        )

        with patch("core.management.commands.push_worker._resolve_public_ips", return_value=["93.184.216.34"]):
            with patch("urllib.request.OpenerDirector.open", side_effect=redirect_error):
                _deliver_relay(outbox)

        outbox.refresh_from_db()
        self.assertEqual(outbox.status, PushOutbox.Status.PENDING)
        self.assertIn("relay HTTP 302", outbox.error_message)


class ImageNormalizationSecurityTests(TestCase):
    """D-02: Normalization to JPEG, EXIF stripping, and attachment handling."""

    def setUp(self):
        self.station = Station.objects.create(name="Wache Foto", slug="wache-foto")
        self.user = User.objects.create_user("fotouser", password="password123")
        self.membership = Membership.objects.create(
            user=self.user, station=self.station, role=Membership.Role.MEMBER
        )
        self.defect = Defect.objects.create(
            station=self.station,
            title="Defekt mit Bild",
            created_by=self.user,
        )
        self.auth = _make_token(self.user, "wb_sec_img_token_1111111111111")
        self.client.force_login(self.user)

    def _sample_jpeg_with_exif(self) -> bytes:
        img = Image.new("RGB", (40, 40), color="red")
        exif = Image.Exif()
        exif[0x010E] = "SENSITIVE_LOCATION_GPS"
        exif[0x010F] = "CONFIDENTIAL_DEVICE"
        buf = BytesIO()
        img.save(buf, format="JPEG", exif=exif)
        return buf.getvalue()

    def _sample_png_rgba(self) -> bytes:
        img = Image.new("RGBA", (30, 30), color=(0, 128, 255, 128))
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def _sample_webp(self) -> bytes:
        img = Image.new("RGB", (25, 25), color="green")
        buf = BytesIO()
        img.save(buf, format="WEBP")
        return buf.getvalue()

    def test_normalize_image_to_jpeg_strips_exif(self):
        """normalize_image_to_jpeg must strip all EXIF tags."""
        raw = self._sample_jpeg_with_exif()
        # Ensure source has exif
        with Image.open(BytesIO(raw)) as source:
            self.assertGreater(len(source.getexif()), 0)

        normalized = normalize_image_to_jpeg(raw)
        with Image.open(BytesIO(normalized)) as result:
            self.assertEqual(result.format, "JPEG")
            self.assertEqual(len(result.getexif()), 0)
            self.assertNotIn("SENSITIVE_LOCATION_GPS", repr(result.info))

    def test_normalize_image_to_jpeg_converts_rgba_png_and_webp(self):
        """normalize_image_to_jpeg converts transparent PNG and WebP to RGB JPEG."""
        png_raw = self._sample_png_rgba()
        normalized_png = normalize_image_to_jpeg(png_raw)
        with Image.open(BytesIO(normalized_png)) as result:
            self.assertEqual(result.format, "JPEG")
            self.assertEqual(result.mode, "RGB")

        webp_raw = self._sample_webp()
        normalized_webp = normalize_image_to_jpeg(webp_raw)
        with Image.open(BytesIO(normalized_webp)) as result:
            self.assertEqual(result.format, "JPEG")
            self.assertEqual(result.mode, "RGB")

    def test_api_defect_attachment_normalizes_png_to_jpeg(self):
        """Uploading a PNG via API must save as image/jpeg with .jpg filename and stripped metadata."""
        png_raw = self._sample_png_rgba()
        b64_data = base64.b64encode(png_raw).decode("ascii")

        response = self.client.post(
            f"/api/v1/defects/{self.defect.pk}/attachments/",
            data=json.dumps({
                "filename": "screenshot.png",
                "content_type": "image/png",
                "data_base64": b64_data,
            }),
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["content_type"], "image/jpeg")
        self.assertTrue(data["filename"].endswith(".jpg"))

        attachment = DefectAttachment.objects.get(pk=data["id"])
        self.assertEqual(attachment.content_type, "image/jpeg")
        self.assertTrue(attachment.filename.endswith(".jpg"))
        with Image.open(BytesIO(bytes(attachment.data))) as check:
            self.assertEqual(check.format, "JPEG")
            self.assertEqual(len(check.getexif()), 0)

    def test_web_defect_attachment_upload_normalizes_to_jpeg(self):
        """Uploading via web interface normalizes images to JPEG."""
        raw_jpeg = self._sample_jpeg_with_exif()
        upload = SimpleUploadedFile("kamera.original.jpg", raw_jpeg, content_type="image/jpeg")

        response = self.client.post(
            f"/maengel/{self.defect.pk}/",
            {"action": "upload", "attachment": upload},
        )
        self.assertEqual(response.status_code, 302)

        attachment = DefectAttachment.objects.get()
        self.assertEqual(attachment.content_type, "image/jpeg")
        with Image.open(BytesIO(bytes(attachment.data))) as check:
            self.assertEqual(check.format, "JPEG")
            self.assertEqual(len(check.getexif()), 0)


class ApiMfaAndTokenSecurityTests(TestCase):
    """D-04 & D-07: API token MFA enforcement and token expires_at field."""

    def setUp(self):
        self.station = Station.objects.create(name="Wache MFA", slug="wache-mfa")
        self.user = User.objects.create_user("mfauser", password="password123")
        self.membership = Membership.objects.create(
            user=self.user, station=self.station, role=Membership.Role.MEMBER
        )
        self.auth = _make_token(self.user, "wb_sec_mfa_token_2222222222222")

    @override_settings(MFA_ENABLED=True, MFA_REQUIRED=True)
    def test_api_token_blocked_when_mfa_required_and_user_unconfirmed(self):
        """Token requests must be blocked with 403 code=mfa_setup_required if user has no confirmed MFA."""
        response = self.client.get("/api/v1/me/", **self.auth)
        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertFalse(data.get("ok"))
        self.assertEqual(data.get("error", {}).get("code"), "mfa_setup_required")

    @override_settings(MFA_ENABLED=True, MFA_REQUIRED=True)
    def test_api_token_allowed_when_user_has_confirmed_mfa(self):
        """Confirmed TOTP device allows token authentication even when MFA_REQUIRED=True."""
        TotpDevice.objects.create(user=self.user, secret="test-secret", is_confirmed=True)
        response = self.client.get("/api/v1/me/", **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get("ok"))

    @override_settings(MFA_ENABLED=True, MFA_REQUIRED=False)
    def test_api_token_allowed_when_mfa_not_required(self):
        """When MFA is not mandatory, unconfirmed users can use API tokens normally."""
        response = self.client.get("/api/v1/me/", **self.auth)
        self.assertEqual(response.status_code, 200)

    @override_settings(MFA_ENABLED=True, MFA_REQUIRED=False)
    def test_me_endpoint_includes_token_expires_at(self):
        """D-07: /api/v1/me/ response must include expires_at in the token dictionary."""
        response = self.client.get("/api/v1/me/", **self.auth)
        self.assertEqual(response.status_code, 200)
        token_info = response.json().get("token", {})
        self.assertIn("expires_at", token_info)
        token_obj = ApiToken.objects.get(user=self.user)
        self.assertEqual(token_info["expires_at"], token_obj.expires_at.isoformat())


class StationModuleFlagsTests(TestCase):
    """D-10: me() and overview() respect disabled station module flags."""

    def setUp(self):
        self.station = Station.objects.create(
            name="Wache Module",
            slug="wache-module",
            warehouse_enabled=False,
            fleet_enabled=False,
            mpg_enabled=False,
        )
        self.user = User.objects.create_user("moduser", password="password123")
        self.membership = Membership.objects.create(
            user=self.user, station=self.station, role=Membership.Role.MEMBER
        )
        self.auth = _make_token(self.user, "wb_sec_mod_token_3333333333333")

    @override_settings(MFA_ENABLED=False)
    def test_wachalltag_modules_reflect_disabled_station_flags(self):
        """Disabled warehouse and fleet/mpg flags must produce False in modules dict."""
        response = self.client.get("/api/v1/me/", **self.auth)
        self.assertEqual(response.status_code, 200)
        modules = response.json()["membership"]["station"]["modules"]
        self.assertFalse(modules["inventory"])
        self.assertFalse(modules["assets"])
        self.assertTrue(modules["defects"])
        self.assertTrue(modules["reports"])
        self.assertTrue(modules["attachments"])

    @override_settings(MFA_ENABLED=False)
    def test_overview_modules_reflect_disabled_station_flags(self):
        """Overview endpoint also reflects disabled modules without overwriting to True."""
        response = self.client.get("/api/v1/uebersicht/", **self.auth)
        self.assertEqual(response.status_code, 200)
        modules = response.json()["modules"]
        self.assertFalse(modules["inventory"])
        self.assertFalse(modules["assets"])
        self.assertTrue(modules["defects"])
        self.assertTrue(modules["reports"])
        self.assertTrue(modules["attachments"])

    @override_settings(MFA_ENABLED=False)
    def test_assets_enabled_when_either_fleet_or_mpg_is_active(self):
        """assets is True if fleet_enabled=True even when mpg_enabled=False."""
        self.station.fleet_enabled = True
        self.station.save()

        response = self.client.get("/api/v1/me/", **self.auth)
        self.assertEqual(response.status_code, 200)
        modules = response.json()["membership"]["station"]["modules"]
        self.assertTrue(modules["assets"])
        self.assertFalse(modules["inventory"])
