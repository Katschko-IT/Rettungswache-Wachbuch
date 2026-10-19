"""Comprehensive test suite for QR-Code Login.
Covers the entire verification matrix from docs/QR-LOGIN-SECURITY-CONTRACT.md Section 10.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import timedelta
from unittest.mock import patch

import pyotp
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from webauthn.helpers import bytes_to_base64url

from core.crypto_at_rest import encrypt_secret
from core.models import (
    AuditEvent,
    Membership,
    QrLoginRequest,
    QrTotpUse,
    Station,
    TotpDevice,
    WebAuthnCredential,
)
from core.qr_login import (
    approve_qr_request,
    check_approval_freshness,
    consume_totp_step,
    create_qr_login_request,
    exchange_qr_request,
    get_canonical_origin,
    hash_manual_code,
    hash_secret,
    is_qr_login_enabled,
    revoke_open_requests_for_user,
    verify_possession,
    verify_secret,
    verify_totp_with_time_step,
)


@override_settings(
    QR_LOGIN_ENABLED=True,
    QR_LOGIN_ALLOW_INSECURE_TEST_ORIGIN=True,
    SITE_URL="https://testserver",
    MFA_ENABLED=True,
    MFA_REQUIRED=False,
    WEBAUTHN_ENABLED=True,
    WEBAUTHN_RP_ID="testserver",
    WEBAUTHN_ORIGIN="https://testserver",
)
class QrLoginBaseTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.station = Station.objects.create(
            name="Hauptwache",
            slug=getattr(settings, "DEFAULT_STATION_SLUG", "rettungswache"),
            is_active=True,
        )
        self.other_station = Station.objects.create(
            name="Nebenwache",
            slug="nebenwache",
            is_active=True,
        )

        # Non-MFA user
        self.user_simple = User.objects.create_user(
            username="retter_einfach",
            password="secure-password-123",
            first_name="Einfach",
        )
        self.member_simple = Membership.objects.create(
            user=self.user_simple,
            station=self.station,
            role=Membership.Role.MEMBER,
            is_active=True,
        )

        # MFA user (TOTP)
        self.user_mfa = User.objects.create_user(
            username="retter_mfa",
            password="secure-password-456",
            first_name="MfaUser",
        )
        self.member_mfa = Membership.objects.create(
            user=self.user_mfa,
            station=self.station,
            role=Membership.Role.SHIFT_LEAD,
            is_active=True,
        )
        self.totp_secret = pyotp.random_base32()
        self.totp_device = TotpDevice.objects.create(
            user=self.user_mfa,
            secret=encrypt_secret(self.totp_secret),
            is_confirmed=True,
            confirmed_at=timezone.now(),
        )

        # Passkey user
        self.user_passkey = User.objects.create_user(
            username="retter_passkey",
            password="secure-password-789",
            first_name="PasskeyUser",
        )
        self.member_passkey = Membership.objects.create(
            user=self.user_passkey,
            station=self.station,
            role=Membership.Role.MEMBER,
            is_active=True,
        )
        self.passkey_cred = WebAuthnCredential.objects.create(
            user=self.user_passkey,
            credential_id="test-cred-id-12345",
            public_key="test-public-key-base64url",
            sign_count=1,
            device_name="Diensthandy",
        )

        # Admin user
        self.user_admin = User.objects.create_user(
            username="station_admin",
            password="secure-admin-pass",
            first_name="Admin",
        )
        self.member_admin = Membership.objects.create(
            user=self.user_admin,
            station=self.station,
            role=Membership.Role.ADMIN,
            is_active=True,
        )

    def _stamp_session_auth(self, client, user, auth_method="password", age_seconds=10):
        session = client.session
        session["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
        session["auth_time"] = int(timezone.now().timestamp()) - age_seconds
        session["auth_user_id"] = user.pk
        session["auth_method"] = auth_method
        session.save()


class QrLoginPositiveFlowTests(QrLoginBaseTestCase):
    def test_positive_flow_totp_fresh(self):
        """Positiv-Flow 1: Start -> Scan -> Approve (TOTP frisch) -> Exchange -> Eingeloggt."""
        browser_client = Client()
        phone_client = Client()

        # 1. Browser starts QR login
        start_resp = browser_client.post(reverse("qr_login_start"))
        self.assertEqual(start_resp.status_code, 200)
        start_data = start_resp.json()
        self.assertTrue(start_data["ok"])
        login_id = start_data["login_id"]
        qr_url = start_data["qr_url"]
        self.assertIn("#secret=", qr_url)
        secret = qr_url.split("#secret=")[1]
        self.assertTrue(start_data["check_word"])
        self.assertTrue(start_data["manual_code"])
        self.assertTrue(start_data["qr_image"].startswith("data:image/png;base64,"))

        # Check browser session has nonces
        self.assertIn(login_id, browser_client.session.get("qr_browser_nonces", {}))

        # 2. Status initially pending
        status_resp = browser_client.post(
            reverse("qr_login_status", args=[login_id]),
            HTTP_X_QR_SECRET=secret,
        )
        self.assertEqual(status_resp.status_code, 200)
        self.assertEqual(status_resp.json()["state"], "pending")

        # 3. Phone user logs in and confirms
        phone_client.force_login(self.user_mfa)
        self._stamp_session_auth(phone_client, self.user_mfa, auth_method="password", age_seconds=400)
        # Login is 400s old (> 300s), so TOTP code is required

        # GET confirm page
        confirm_get = phone_client.get(reverse("qr_login_confirm", args=[login_id]))
        self.assertEqual(confirm_get.status_code, 200)
        self.assertContains(confirm_get, self.station.name)
        self.assertContains(confirm_get, start_data["check_word"])

        # Check request transitioned to SCANNED
        req = QrLoginRequest.objects.get(pk=login_id)
        self.assertEqual(req.state, QrLoginRequest.State.SCANNED)

        # POST approve with fresh TOTP code
        totp = pyotp.TOTP(self.totp_secret)
        otp = totp.now()

        approve_resp = phone_client.post(
            reverse("qr_login_confirm", args=[login_id]),
            data={"qr_secret": secret, "totp_code": otp},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(approve_resp.status_code, 200)
        self.assertEqual(approve_resp.json()["state"], "approved")

        # Check DB state
        req.refresh_from_db()
        self.assertEqual(req.state, QrLoginRequest.State.APPROVED)
        self.assertEqual(req.approved_by, self.user_mfa)

        # 4. Browser polls status -> approved
        status_resp2 = browser_client.post(
            reverse("qr_login_status", args=[login_id]),
            HTTP_X_QR_SECRET=secret,
        )
        self.assertEqual(status_resp2.status_code, 200)
        self.assertEqual(status_resp2.json()["state"], "approved")

        # 5. Browser exchanges
        old_session_key = browser_client.session.session_key
        exchange_resp = browser_client.post(
            reverse("qr_login_exchange", args=[login_id]),
            data={"qr_secret": secret},
            HTTP_X_QR_SECRET=secret,
        )
        self.assertEqual(exchange_resp.status_code, 200)
        exchange_data = exchange_resp.json()
        self.assertTrue(exchange_data["ok"])
        self.assertEqual(exchange_data["redirect"], reverse("landing"))

        # Verify browser is logged in as user_mfa
        self.assertEqual(int(browser_client.session["_auth_user_id"]), self.user_mfa.pk)
        self.assertEqual(browser_client.session["auth_method"], "qr")
        self.assertNotEqual(browser_client.session.session_key, old_session_key)

        # Verify audit trail
        events = list(AuditEvent.objects.filter(object_id=str(login_id)).order_by("created_at"))
        actions = [e.action for e in events]
        self.assertIn("qr_login.created", actions)
        self.assertIn("qr_login.approved", actions)
        self.assertIn("qr_login.consumed", actions)

    def test_positive_flow_passkey_fresh(self):
        """Positiv-Flow 2: Start -> Scan -> Passkey-Reauth -> Approve -> Exchange."""
        browser_client = Client()
        phone_client = Client()

        start_resp = browser_client.post(reverse("qr_login_start"))
        start_data = start_resp.json()
        login_id = start_data["login_id"]
        secret = start_data["qr_url"].split("#secret=")[1]

        phone_client.force_login(self.user_passkey)
        # Login is older than 300s, but fresh passkey assert in session
        self._stamp_session_auth(phone_client, self.user_passkey, age_seconds=500)
        session = phone_client.session
        session["qr_passkey_reauth_user_id"] = self.user_passkey.pk
        session["qr_passkey_reauth_time"] = int(timezone.now().timestamp()) - 20
        # Vertrag 0.3/Q4: Reauth-Stempel ist an genau diese login_id gebunden.
        session["qr_passkey_reauth_login_id"] = str(login_id)
        session.save()

        approve_resp = phone_client.post(
            reverse("qr_login_confirm", args=[login_id]),
            data={"qr_secret": secret},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(approve_resp.status_code, 200)
        self.assertEqual(approve_resp.json()["state"], "approved")

        exchange_resp = browser_client.post(
            reverse("qr_login_exchange", args=[login_id]),
            HTTP_X_QR_SECRET=secret,
        )
        self.assertEqual(exchange_resp.status_code, 200)
        self.assertEqual(int(browser_client.session["_auth_user_id"]), self.user_passkey.pk)

    def test_positive_flow_non_mfa_fresh(self):
        """Positiv-Flow 3: User ohne MFA mit frischer Session (<=600s)."""
        browser_client = Client()
        phone_client = Client()

        start_resp = browser_client.post(reverse("qr_login_start"))
        start_data = start_resp.json()
        login_id = start_data["login_id"]
        secret = start_data["qr_url"].split("#secret=")[1]

        phone_client.force_login(self.user_simple)
        self._stamp_session_auth(phone_client, self.user_simple, age_seconds=120)

        approve_resp = phone_client.post(
            reverse("qr_login_confirm", args=[login_id]),
            data={"qr_secret": secret},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(approve_resp.status_code, 200)
        self.assertEqual(approve_resp.json()["state"], "approved")

        exchange_resp = browser_client.post(
            reverse("qr_login_exchange", args=[login_id]),
            HTTP_X_QR_SECRET=secret,
        )
        self.assertEqual(exchange_resp.status_code, 200)
        self.assertEqual(int(browser_client.session["_auth_user_id"]), self.user_simple.pk)

    def test_deny_flow(self):
        """Positiv-Flow 4: Ablehnung durch das Mobilgeraet."""
        browser_client = Client()
        phone_client = Client()

        start_resp = browser_client.post(reverse("qr_login_start"))
        login_id = start_resp.json()["login_id"]
        secret = start_resp.json()["qr_url"].split("#secret=")[1]

        phone_client.force_login(self.user_simple)
        self._stamp_session_auth(phone_client, self.user_simple, age_seconds=30)

        deny_resp = phone_client.post(
            reverse("qr_login_deny", args=[login_id]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(deny_resp.status_code, 200)
        self.assertEqual(deny_resp.json()["state"], "denied")

        # Status on browser
        status_resp = browser_client.post(
            reverse("qr_login_status", args=[login_id]),
            HTTP_X_QR_SECRET=secret,
        )
        self.assertEqual(status_resp.json()["state"], "denied")

        # Exchange fails with 409 conflict
        exchange_resp = browser_client.post(
            reverse("qr_login_exchange", args=[login_id]),
            HTTP_X_QR_SECRET=secret,
        )
        self.assertEqual(exchange_resp.status_code, 409)

        # Audit event created
        self.assertTrue(
            AuditEvent.objects.filter(object_id=str(login_id), action="qr_login.denied").exists()
        )

    def test_manual_code_approval(self):
        """Positiv-Flow 5: Genehmigung via manuellem Code statt URL-Fragment."""
        browser_client = Client()
        phone_client = Client()

        start_resp = browser_client.post(reverse("qr_login_start"))
        start_data = start_resp.json()
        login_id = start_data["login_id"]
        secret = start_data["qr_url"].split("#secret=")[1]
        manual_code = start_data["manual_code"]

        phone_client.force_login(self.user_simple)
        self._stamp_session_auth(phone_client, self.user_simple, age_seconds=50)

        # Approve using manual_code and NO qr_secret
        approve_resp = phone_client.post(
            reverse("qr_login_confirm", args=[login_id]),
            data={"manual_code": manual_code.lower()},  # Case-insensitive
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(approve_resp.status_code, 200)
        self.assertEqual(approve_resp.json()["state"], "approved")

        exchange_resp = browser_client.post(
            reverse("qr_login_exchange", args=[login_id]),
            HTTP_X_QR_SECRET=secret,
        )
        self.assertEqual(exchange_resp.status_code, 200)
        self.assertEqual(int(browser_client.session["_auth_user_id"]), self.user_simple.pk)

    def test_status_without_secret_header(self):
        """Vertrag Abschn. 5: Status-Polling verlangt Session-Bindung + X-QR-Secret."""
        browser_client = Client()
        start_resp = browser_client.post(reverse("qr_login_start"))
        login_id = start_resp.json()["login_id"]
        secret = start_resp.json()["qr_url"].split("#secret=")[1]

        # Status without X-QR-Secret must fail with 403 (Contract Sec. 5)
        status_resp = browser_client.post(reverse("qr_login_status", args=[login_id]))
        self.assertEqual(status_resp.status_code, 403)

        # Status with secret and valid browser session succeeds
        status_valid = browser_client.post(
            reverse("qr_login_status", args=[login_id]),
            HTTP_X_QR_SECRET=secret,
        )
        self.assertEqual(status_valid.status_code, 200)
        self.assertEqual(status_valid.json(), {"ok": True, "state": "pending"})

    def test_session_key_rotation_on_exchange(self):
        """Positiv-Flow 7: Session-Fixation-Schutz (Session-Key wechselt beim Login)."""
        browser_client = Client()
        start_resp = browser_client.post(reverse("qr_login_start"))
        login_id = start_resp.json()["login_id"]
        secret = start_resp.json()["qr_url"].split("#secret=")[1]
        initial_key = browser_client.session.session_key

        phone_client = Client()
        phone_client.force_login(self.user_simple)
        self._stamp_session_auth(phone_client, self.user_simple, age_seconds=10)
        phone_client.post(
            reverse("qr_login_confirm", args=[login_id]),
            data={"qr_secret": secret},
        )

        browser_client.post(
            reverse("qr_login_exchange", args=[login_id]),
            HTTP_X_QR_SECRET=secret,
        )
        new_key = browser_client.session.session_key
        self.assertNotEqual(initial_key, new_key)


class QrLoginNegativeTests(QrLoginBaseTestCase):
    def test_replay_after_consumed_fails(self):
        """Negativ 1: Replay von Secret und login_id nach CONSUMED (409)."""
        browser_client = Client()
        start_resp = browser_client.post(reverse("qr_login_start"))
        login_id = start_resp.json()["login_id"]
        secret = start_resp.json()["qr_url"].split("#secret=")[1]

        phone_client = Client()
        phone_client.force_login(self.user_simple)
        self._stamp_session_auth(phone_client, self.user_simple, age_seconds=10)
        phone_client.post(
            reverse("qr_login_confirm", args=[login_id]),
            data={"qr_secret": secret},
        )

        # First exchange succeeds
        ex1 = browser_client.post(
            reverse("qr_login_exchange", args=[login_id]),
            HTTP_X_QR_SECRET=secret,
        )
        self.assertEqual(ex1.status_code, 200)

        # Replay attempt fails with 409
        ex2 = browser_client.post(
            reverse("qr_login_exchange", args=[login_id]),
            HTTP_X_QR_SECRET=secret,
        )
        self.assertEqual(ex2.status_code, 409)

    def test_foreign_browser_session_rejected(self):
        """Negativ 2: Fremde Browser-Session wird abgewiesen (403)."""
        browser_client = Client()
        start_resp = browser_client.post(reverse("qr_login_start"))
        login_id = start_resp.json()["login_id"]
        secret = start_resp.json()["qr_url"].split("#secret=")[1]

        attacker_client = Client()
        # Attacker tries polling status
        att_status = attacker_client.post(
            reverse("qr_login_status", args=[login_id]),
            HTTP_X_QR_SECRET=secret,
        )
        self.assertEqual(att_status.status_code, 403)

        # Attacker tries exchange
        att_exchange = attacker_client.post(
            reverse("qr_login_exchange", args=[login_id]),
            HTTP_X_QR_SECRET=secret,
        )
        self.assertEqual(att_exchange.status_code, 403)

    def test_wrong_station_membership_rejected(self):
        """Negativ 3: Bestaetigung mit Mitgliedschaft einer fremden Wache wird abgewiesen (403)."""
        browser_client = Client()
        start_resp = browser_client.post(reverse("qr_login_start"))
        login_id = start_resp.json()["login_id"]
        secret = start_resp.json()["qr_url"].split("#secret=")[1]

        # User belongs to other_station only
        other_user = User.objects.create_user("fremder", "pass")
        Membership.objects.create(user=other_user, station=self.other_station, is_active=True)

        phone_client = Client()
        phone_client.force_login(other_user)
        self._stamp_session_auth(phone_client, other_user, age_seconds=10)

        resp = phone_client.post(
            reverse("qr_login_confirm", args=[login_id]),
            data={"qr_secret": secret},
        )
        self.assertEqual(resp.status_code, 403)

    def test_inactive_membership_rejected(self):
        """Negativ 4: Inaktive Mitgliedschaft darf nicht bestaetigen (403)."""
        browser_client = Client()
        start_resp = browser_client.post(reverse("qr_login_start"))
        login_id = start_resp.json()["login_id"]
        secret = start_resp.json()["qr_url"].split("#secret=")[1]

        self.member_simple.is_active = False
        self.member_simple.save()

        phone_client = Client()
        phone_client.force_login(self.user_simple)
        self._stamp_session_auth(phone_client, self.user_simple, age_seconds=10)

        resp = phone_client.post(
            reverse("qr_login_confirm", args=[login_id]),
            data={"qr_secret": secret},
        )
        self.assertEqual(resp.status_code, 403)

    def test_stale_freshness_rejected(self):
        """Negativ 5: Veraltete oder fehlende Frische wird abgewiesen (403)."""
        browser_client = Client()
        start_resp = browser_client.post(reverse("qr_login_start"))
        login_id = start_resp.json()["login_id"]
        secret = start_resp.json()["qr_url"].split("#secret=")[1]

        # Case 1: Non-MFA user older than 600s
        phone_client = Client()
        phone_client.force_login(self.user_simple)
        self._stamp_session_auth(phone_client, self.user_simple, age_seconds=601)
        resp1 = phone_client.post(
            reverse("qr_login_confirm", args=[login_id]),
            data={"qr_secret": secret},
        )
        self.assertEqual(resp1.status_code, 403)

        # Case 2: MFA user older than 300s without TOTP
        phone_client.force_login(self.user_mfa)
        self._stamp_session_auth(phone_client, self.user_mfa, age_seconds=301)
        resp2 = phone_client.post(
            reverse("qr_login_confirm", args=[login_id]),
            data={"qr_secret": secret},
        )
        self.assertEqual(resp2.status_code, 403)

        # Case 3: Unstamped legacy session (no auth_time)
        phone_client.force_login(self.user_simple)
        session = phone_client.session
        session.pop("auth_time", None)
        session.pop("auth_user_id", None)
        session.save()
        resp3 = phone_client.post(
            reverse("qr_login_confirm", args=[login_id]),
            data={"qr_secret": secret},
        )
        self.assertEqual(resp3.status_code, 403)

    def test_totp_replay_rejected(self):
        """Negativ 6: Zweimalige Bestaetigung mit demselben TOTP-Zeitschritt schlaegt fehl (403)."""
        browser_client1 = Client()
        start1 = browser_client1.post(reverse("qr_login_start")).json()
        login_id1 = start1["login_id"]
        secret1 = start1["qr_url"].split("#secret=")[1]

        browser_client2 = Client()
        start2 = browser_client2.post(reverse("qr_login_start")).json()
        login_id2 = start2["login_id"]
        secret2 = start2["qr_url"].split("#secret=")[1]

        phone_client = Client()
        phone_client.force_login(self.user_mfa)
        self._stamp_session_auth(phone_client, self.user_mfa, age_seconds=400)

        totp = pyotp.TOTP(self.totp_secret)
        otp = totp.now()

        # First approval with this OTP succeeds
        resp1 = phone_client.post(
            reverse("qr_login_confirm", args=[login_id1]),
            data={"qr_secret": secret1, "totp_code": otp},
        )
        self.assertEqual(resp1.status_code, 302)  # HTML redirect on success

        # Second approval with the EXACT SAME OTP in the same time step fails
        resp2 = phone_client.post(
            reverse("qr_login_confirm", args=[login_id2]),
            data={"qr_secret": secret2, "totp_code": otp},
        )
        self.assertEqual(resp2.status_code, 403)

    def test_csrf_enforced_on_mutating_endpoints(self):
        """Negativ 7: CSRF-Schutz auf allen mutierenden POSTs."""
        csrf_client = Client(enforce_csrf_checks=True)

        # POST start without CSRF -> 403
        r_start = csrf_client.post(reverse("qr_login_start"))
        self.assertEqual(r_start.status_code, 403)

        # Obtain CSRF cookie by visiting GET wait
        r_get = csrf_client.get(reverse("qr_login_wait"))
        self.assertEqual(r_get.status_code, 200)
        csrf_token = csrf_client.cookies["rwsth_csrf"].value

        # POST start with CSRF token -> 200
        r_start_ok = csrf_client.post(
            reverse("qr_login_start"),
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(r_start_ok.status_code, 200)
        login_id = r_start_ok.json()["login_id"]

        # POST confirm without CSRF -> 403
        csrf_client.force_login(self.user_simple)
        r_confirm = csrf_client.post(reverse("qr_login_confirm", args=[login_id]))
        self.assertEqual(r_confirm.status_code, 403)

        # POST deny without CSRF -> 403
        r_deny = csrf_client.post(reverse("qr_login_deny", args=[login_id]))
        self.assertEqual(r_deny.status_code, 403)

        # POST exchange without CSRF -> 403
        r_exchange = csrf_client.post(reverse("qr_login_exchange", args=[login_id]))
        self.assertEqual(r_exchange.status_code, 403)

    @override_settings(
        QR_LOGIN_RATE_LIMITS={
            "qr_start": (2, 60),
            "qr_status": (2, 60),
            "qr_approve": (2, 60),
            "qr_exchange": (2, 60),
        }
    )
    def test_rate_limits(self):
        """Negativ 8: Rate-Limit (429) bei Ueberschreitung."""
        client = Client()
        r1 = client.post(reverse("qr_login_start"))
        self.assertEqual(r1.status_code, 200)
        r2 = client.post(reverse("qr_login_start"))
        self.assertEqual(r2.status_code, 200)

        # 3rd request exceeds limit of 2
        r3 = client.post(reverse("qr_login_start"))
        self.assertEqual(r3.status_code, 429)
        self.assertEqual(r3.json()["error"], "qr_rate_limited")

    def test_controlled_clock_expiry_119s_and_121s(self):
        """Negativ 9: TTL-Ablauf bei 119s (noch gueltig) und 121s (abgelaufen)."""
        browser_client = Client()
        start_time = timezone.now()

        with patch("django.utils.timezone.now", return_value=start_time):
            start_resp = browser_client.post(reverse("qr_login_start"))
            login_id = start_resp.json()["login_id"]
            secret = start_resp.json()["qr_url"].split("#secret=")[1]

        phone_client = Client()
        phone_client.force_login(self.user_simple)
        self._stamp_session_auth(phone_client, self.user_simple, age_seconds=10)

        # At 119s: still valid
        with patch("django.utils.timezone.now", return_value=start_time + timedelta(seconds=119)):
            status_resp = browser_client.post(
                reverse("qr_login_status", args=[login_id]),
                HTTP_X_QR_SECRET=secret,
            )
            self.assertEqual(status_resp.status_code, 200)
            self.assertEqual(status_resp.json()["state"], "pending")

        # At 121s: expired!
        with patch("django.utils.timezone.now", return_value=start_time + timedelta(seconds=121)):
            status_expired = browser_client.post(
                reverse("qr_login_status", args=[login_id]),
                HTTP_X_QR_SECRET=secret,
            )
            self.assertEqual(status_expired.status_code, 200)
            self.assertEqual(status_expired.json()["state"], "expired")

            approve_expired = phone_client.post(
                reverse("qr_login_confirm", args=[login_id]),
                data={"qr_secret": secret},
            )
            self.assertEqual(approve_expired.status_code, 410)

    def test_revocation_between_approval_and_exchange(self):
        """Negativ 10: Mitgliedschaftsentzug zwischen Approval und Exchange (403, REVOKED)."""
        browser_client = Client()
        start_resp = browser_client.post(reverse("qr_login_start"))
        login_id = start_resp.json()["login_id"]
        secret = start_resp.json()["qr_url"].split("#secret=")[1]

        phone_client = Client()
        phone_client.force_login(self.user_simple)
        self._stamp_session_auth(phone_client, self.user_simple, age_seconds=10)
        phone_client.post(
            reverse("qr_login_confirm", args=[login_id]),
            data={"qr_secret": secret},
        )

        # Revoke user's membership
        self.member_simple.is_active = False
        self.member_simple.save()

        # Browser tries exchange -> rejected, marked REVOKED
        ex_resp = browser_client.post(
            reverse("qr_login_exchange", args=[login_id]),
            HTTP_X_QR_SECRET=secret,
        )
        self.assertEqual(ex_resp.status_code, 403)
        self.assertNotIn("_auth_user_id", browser_client.session)

        req = QrLoginRequest.objects.get(pk=login_id)
        self.assertEqual(req.state, QrLoginRequest.State.REVOKED)

    def test_logout_revokes_open_approvals(self):
        """Negativ 11: Logout widerruft offene QR-Freigaben des Nutzers."""
        browser_client = Client()
        start_resp = browser_client.post(reverse("qr_login_start"))
        login_id = start_resp.json()["login_id"]
        secret = start_resp.json()["qr_url"].split("#secret=")[1]

        phone_client = Client()
        phone_client.force_login(self.user_simple)
        self._stamp_session_auth(phone_client, self.user_simple, age_seconds=10)
        phone_client.post(
            reverse("qr_login_confirm", args=[login_id]),
            data={"qr_secret": secret},
        )

        req = QrLoginRequest.objects.get(pk=login_id)
        self.assertEqual(req.state, QrLoginRequest.State.APPROVED)

        # Phone user logs out
        phone_client.post(reverse("logout"))

        # QR request must now be REVOKED
        req.refresh_from_db()
        self.assertEqual(req.state, QrLoginRequest.State.REVOKED)

        # Exchange fails
        ex_resp = browser_client.post(
            reverse("qr_login_exchange", args=[login_id]),
            HTTP_X_QR_SECRET=secret,
        )
        self.assertEqual(ex_resp.status_code, 409)

    def test_membership_update_revokes_open_approvals(self):
        """Negativ 12: membership_update widerruft offene QR-Freigaben."""
        browser_client = Client()
        start_resp = browser_client.post(reverse("qr_login_start"))
        login_id = start_resp.json()["login_id"]
        secret = start_resp.json()["qr_url"].split("#secret=")[1]

        phone_client = Client()
        phone_client.force_login(self.user_simple)
        self._stamp_session_auth(phone_client, self.user_simple, age_seconds=10)
        phone_client.post(
            reverse("qr_login_confirm", args=[login_id]),
            data={"qr_secret": secret},
        )

        admin_client = Client()
        admin_client.force_login(self.user_admin)

        # Change role via membership_update
        admin_client.post(
            reverse("membership_update", args=[self.member_simple.pk]),
            data={
                "role": Membership.Role.CASHIER,
                "is_active": "on",
            },
        )

        req = QrLoginRequest.objects.get(pk=login_id)
        self.assertEqual(req.state, QrLoginRequest.State.REVOKED)

    def test_secrets_and_pii_not_leaked(self):
        """Negativ 13: Kein Leak von Secrets, User-IDs oder Hash-Werten in Status/Audit/Headers."""
        browser_client = Client()
        start_resp = browser_client.post(reverse("qr_login_start"))
        login_id = start_resp.json()["login_id"]
        secret = start_resp.json()["qr_url"].split("#secret=")[1]
        manual_code = start_resp.json()["manual_code"]

        # Check status response content
        status_resp = browser_client.post(
            reverse("qr_login_status", args=[login_id]),
            HTTP_X_QR_SECRET=secret,
        )
        status_text = status_resp.content.decode("utf-8")
        self.assertNotIn(secret, status_text)
        self.assertNotIn(manual_code, status_text)
        self.assertNotIn("user_id", status_text)
        self.assertEqual(set(status_resp.json().keys()), {"ok", "state"})

        # Check response security headers
        self.assertEqual(status_resp.headers.get("Cache-Control"), "no-store")
        self.assertEqual(status_resp.headers.get("Pragma"), "no-cache")
        self.assertEqual(status_resp.headers.get("Referrer-Policy"), "no-referrer")
        self.assertEqual(status_resp.headers.get("X-Robots-Tag"), "noindex")

        # Check audit event metadata
        events = AuditEvent.objects.filter(object_id=str(login_id))
        for ev in events:
            ev_str = json.dumps(ev.metadata)
            self.assertNotIn(secret, ev_str)
            self.assertNotIn(manual_code, ev_str)
            self.assertNotIn("session_key", ev_str)

    def test_parallel_approvals_cas(self):
        """Negativ 14: CAS-Rennen bei Approvals – genau einer gewinnt."""
        req, secret, code, cw, url, img = create_qr_login_request(
            Client().request().wsgi_request, station=self.station
        )
        res1 = approve_qr_request(req, self.user_simple, self.member_simple)
        res2 = approve_qr_request(req, self.user_simple, self.member_simple)
        self.assertTrue(res1)
        self.assertFalse(res2)

    def test_parallel_exchanges_cas(self):
        """Negativ 15: CAS-Rennen bei Exchange – genau einer gewinnt."""
        req, secret, code, cw, url, img = create_qr_login_request(
            Client().request().wsgi_request, station=self.station
        )
        approve_qr_request(req, self.user_simple, self.member_simple)
        res1 = exchange_qr_request(req)
        res2 = exchange_qr_request(req)
        self.assertTrue(res1)
        self.assertFalse(res2)

    def test_referrer_policy_headers(self):
        """Formular-HTML-Seiten senden same-origin, API und Warteseite weiterhin no-referrer."""
        browser_client = Client()
        start_resp = browser_client.post(reverse("qr_login_start"))
        self.assertEqual(start_resp.status_code, 200)
        login_id = start_resp.json()["login_id"]
        secret = start_resp.json()["qr_url"].split("#secret=")[1]

        phone_client = Client()
        phone_client.force_login(self.user_simple)
        self._stamp_session_auth(phone_client, self.user_simple, age_seconds=10)

        # qr_login_manual GET (authentifiziertes Mitglied) -> Referrer-Policy: same-origin
        resp_manual = phone_client.get(reverse("qr_login_manual"))
        self.assertEqual(resp_manual.status_code, 200)
        self.assertEqual(resp_manual.headers.get("Referrer-Policy"), "same-origin")

        # qr_login_manual POST error render -> same-origin
        resp_manual_post = phone_client.post(
            reverse("qr_login_manual"), {"manual_code": "INVALID123"}
        )
        self.assertEqual(resp_manual_post.status_code, 400)
        self.assertEqual(resp_manual_post.headers.get("Referrer-Policy"), "same-origin")

        # qr_login_confirm GET (nach Start, Mitglied, frische Session) -> same-origin
        resp_confirm = phone_client.get(reverse("qr_login_confirm", args=[login_id]))
        self.assertEqual(resp_confirm.status_code, 200)
        self.assertEqual(resp_confirm.headers.get("Referrer-Policy"), "same-origin")

        # qr_login_status POST -> weiterhin no-referrer
        resp_status = browser_client.post(
            reverse("qr_login_status", args=[login_id]),
            HTTP_X_QR_SECRET=secret,
        )
        self.assertEqual(resp_status.status_code, 200)
        self.assertEqual(resp_status.headers.get("Referrer-Policy"), "no-referrer")

        # qr_login_wait GET -> weiterhin no-referrer
        resp_wait = browser_client.get(reverse("qr_login_wait"))
        self.assertEqual(resp_wait.status_code, 200)
        self.assertEqual(resp_wait.headers.get("Referrer-Policy"), "no-referrer")



class QrLoginBackendAndCleanupTests(QrLoginBaseTestCase):
    def test_session_persists_after_mfa_login_model_backend(self):
        """Backend-Fix: Session bleibt nach mfa_verify mit ModelBackend gueltig."""
        client = Client()
        # Set pending user in session
        session = client.session
        session["mfa_pending_user_id"] = self.user_mfa.pk
        session["mfa_next"] = reverse("landing")
        session.save()

        totp = pyotp.TOTP(self.totp_secret)
        otp = totp.now()

        resp = client.post(reverse("mfa_verify"), data={"token": otp})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("landing"))

        # Subsequent request with authenticated user succeeds
        home_resp = client.get(reverse("landing"), follow=True)
        self.assertEqual(home_resp.status_code, 200)
        self.assertEqual(int(client.session["_auth_user_id"]), self.user_mfa.pk)
        self.assertEqual(client.session["_auth_user_backend"], "django.contrib.auth.backends.ModelBackend")

    def test_qr_login_cleanup_command(self):
        """Management-Command qr_login_cleanup loescht terminale Datensaetze aelter 24h."""
        now = timezone.now()
        old_time = now - timedelta(hours=25)

        # Create old terminal request
        old_req = QrLoginRequest.objects.create(
            secret_hash="hash1",
            manual_code_hash="mhash1",
            browser_session_hash="bshash1",
            browser_nonce_hash="bnhash1",
            station=self.station,
            origin="https://testserver",
            state=QrLoginRequest.State.CONSUMED,
            expires_at=old_time,
            check_word="TEST-WORD",
        )
        QrLoginRequest.objects.filter(pk=old_req.pk).update(created_at=old_time)

        # Create recent terminal request
        recent_req = QrLoginRequest.objects.create(
            secret_hash="hash2",
            manual_code_hash="mhash2",
            browser_session_hash="bshash2",
            browser_nonce_hash="bnhash2",
            station=self.station,
            origin="https://testserver",
            state=QrLoginRequest.State.CONSUMED,
            expires_at=now,
            check_word="TEST-WORD",
        )

        # Create old TOTP step and recent TOTP step
        old_totp = QrTotpUse.objects.create(user=self.user_mfa, time_step=111111)
        QrTotpUse.objects.filter(pk=old_totp.pk).update(created_at=old_time)
        recent_totp = QrTotpUse.objects.create(user=self.user_mfa, time_step=222222)

        # Dry-run does not delete
        call_command("qr_login_cleanup", "--dry-run")
        self.assertTrue(QrLoginRequest.objects.filter(pk=old_req.pk).exists())
        self.assertTrue(QrTotpUse.objects.filter(pk=old_totp.pk).exists())

        # Real cleanup deletes old, keeps recent
        call_command("qr_login_cleanup")
        self.assertFalse(QrLoginRequest.objects.filter(pk=old_req.pk).exists())
        self.assertTrue(QrLoginRequest.objects.filter(pk=recent_req.pk).exists())
        self.assertFalse(QrTotpUse.objects.filter(pk=old_totp.pk).exists())
        self.assertTrue(QrTotpUse.objects.filter(pk=recent_totp.pk).exists())

    @override_settings(QR_LOGIN_ENABLED=False)
    def test_feature_gate_disabled(self):
        """Feature-Gate deaktiviert -> 503 bzw 404."""
        client = Client()
        r_start = client.post(reverse("qr_login_start"))
        self.assertEqual(r_start.status_code, 503)
        self.assertEqual(r_start.json()["error"], "qr_disabled")

        r_wait = client.get(reverse("qr_login_wait"))
        self.assertEqual(r_wait.status_code, 404)


class QrLoginManualFallbackTests(QrLoginBaseTestCase):
    """Manueller Code als echter Ersatz, wenn keine Kamera verfuegbar ist."""

    def test_manual_code_entry_approves_and_exchanges(self):
        browser_client = Client()
        start = browser_client.post(reverse("qr_login_start"))
        self.assertEqual(start.status_code, 200)
        data = start.json()
        login_id = data["login_id"]
        manual_code = data["manual_code"]
        secret = data["qr_url"].split("#secret=")[1]

        phone = Client()
        phone.force_login(self.user_simple)
        self._stamp_session_auth(phone, self.user_simple, age_seconds=10)

        page = phone.get(reverse("qr_login_manual"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "10-stelliger Code")

        wrong = phone.post(reverse("qr_login_manual"), {"manual_code": "AAAAAAAAAA"})
        self.assertEqual(wrong.status_code, 400)

        entry = phone.post(reverse("qr_login_manual"), {"manual_code": manual_code.lower()})
        self.assertEqual(entry.status_code, 302)
        self.assertEqual(
            entry.url, reverse("qr_login_confirm", kwargs={"login_id": login_id})
        )

        confirm = phone.get(entry.url)
        self.assertEqual(confirm.status_code, 200)
        self.assertContains(confirm, "Anmeldung bestätigen")

        approved = phone.post(entry.url, data={}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["state"], "approved")

        exchanged = browser_client.post(
            reverse("qr_login_exchange", kwargs={"login_id": login_id}),
            HTTP_X_QR_SECRET=secret,
        )
        self.assertEqual(exchanged.status_code, 200)
        self.assertTrue(exchanged.json()["ok"])

    def test_manual_code_of_other_station_is_rejected(self):
        browser_client = Client()
        start = browser_client.post(reverse("qr_login_start"))
        manual_code = start.json()["manual_code"]

        other_user = User.objects.create_user(
            username="retter_nebenwache", password="secure-password-999"
        )
        Membership.objects.create(
            user=other_user,
            station=self.other_station,
            role=Membership.Role.MEMBER,
            is_active=True,
        )
        phone = Client()
        phone.force_login(other_user)
        self._stamp_session_auth(phone, other_user, age_seconds=10)

        response = phone.post(reverse("qr_login_manual"), {"manual_code": manual_code})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "unbekannt oder abgelaufen", status_code=400)

    def test_manual_code_expired_is_rejected(self):
        browser_client = Client()
        start = browser_client.post(reverse("qr_login_start"))
        data = start.json()
        QrLoginRequest.objects.filter(pk=data["login_id"]).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        phone = Client()
        phone.force_login(self.user_simple)
        self._stamp_session_auth(phone, self.user_simple, age_seconds=10)
        response = phone.post(
            reverse("qr_login_manual"), {"manual_code": data["manual_code"]}
        )
        self.assertEqual(response.status_code, 400)
