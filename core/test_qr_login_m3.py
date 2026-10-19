"""M3 negative-test module for the QR login security contract.

Provenance: derived from the independent Mistral Large M3 review
(evidence/roadmap-phase2/mistral-M3-test-module.py, verdict "pass") and
reviewed/adapted by the orchestrator before adoption:

- missing imports for ``create_qr_login_request`` / ``approve_qr_request`` /
  ``exchange_qr_request`` added;
- the two CAS tests used a non-existent ``Client().request`` API and now build a
  real request via ``RequestFactory`` + ``SessionMiddleware``;
- added tests for missing secret, approval with login_id alone, TOTP replay in a
  second session, and the Referrer-Policy regression that blocked real browsers
  (Origin: null on normal form POST).

All accounts are synthetic. No production settings are weakened.
"""

from __future__ import annotations

from datetime import timedelta

import pyotp
from django.contrib.auth.models import User
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.crypto_at_rest import encrypt_secret
from core.models import Membership, QrLoginRequest, Station, TotpDevice
from core.qr_login import approve_qr_request, create_qr_login_request, exchange_qr_request


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
class M3QrLoginSecurityTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(name="Testwache", slug="testwache", is_active=True)
        self.user = User.objects.create_user(
            username="testuser", password="testpass123", first_name="Test"
        )
        self.membership = Membership.objects.create(
            user=self.user, station=self.station, role=Membership.Role.MEMBER, is_active=True
        )
        self.totp_secret = pyotp.random_base32()
        TotpDevice.objects.create(
            user=self.user,
            secret=encrypt_secret(self.totp_secret),
            is_confirmed=True,
            confirmed_at=timezone.now(),
        )

    def _stamp_session_auth(self, client, user, age_seconds=10):
        session = client.session
        session["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
        session["auth_time"] = int(timezone.now().timestamp()) - age_seconds
        session["auth_user_id"] = user.pk
        session["auth_method"] = "password"
        session.save()

    def _start(self, client):
        resp = client.post(reverse("qr_login_start"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        return data["login_id"], data["qr_url"].split("#secret=", 1)[1], data["manual_code"]

    def _phone(self, age_seconds=10, user=None):
        user = user or self.user
        phone = Client()
        phone.force_login(user)
        self._stamp_session_auth(phone, user, age_seconds=age_seconds)
        return phone

    def _request(self):
        request = RequestFactory().post("/anmelden/qr/start/")
        request.META["HTTP_HOST"] = "testserver"
        SessionMiddleware(lambda r: None).process_request(request)
        return request

    # --- B. Replay / Einmaligkeit -------------------------------------------------

    def test_replay_after_consumed_fails(self):
        browser = Client()
        login_id, secret, _ = self._start(browser)
        phone = self._phone()
        self.assertEqual(
            phone.post(
                reverse("qr_login_confirm", args=[login_id]), data={"qr_secret": secret}
            ).status_code,
            302,
        )
        first = browser.post(reverse("qr_login_exchange", args=[login_id]), HTTP_X_QR_SECRET=secret)
        self.assertEqual(first.status_code, 200)
        second = browser.post(reverse("qr_login_exchange", args=[login_id]), HTTP_X_QR_SECRET=secret)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(QrLoginRequest.objects.get(pk=login_id).state, QrLoginRequest.State.CONSUMED)

    def test_totp_replay_rejected(self):
        browser1 = Client()
        login_id1, secret1, _ = self._start(browser1)
        browser2 = Client()
        login_id2, secret2, _ = self._start(browser2)
        phone = self._phone(age_seconds=400)
        otp = pyotp.TOTP(self.totp_secret).now()
        self.assertEqual(
            phone.post(
                reverse("qr_login_confirm", args=[login_id1]),
                data={"qr_secret": secret1, "totp_code": otp},
            ).status_code,
            302,
        )
        self.assertEqual(
            phone.post(
                reverse("qr_login_confirm", args=[login_id2]),
                data={"qr_secret": secret2, "totp_code": otp},
            ).status_code,
            403,
        )

    def test_totp_replay_second_session_rejected(self):
        browser1 = Client()
        login_id1, secret1, _ = self._start(browser1)
        browser2 = Client()
        login_id2, secret2, _ = self._start(browser2)
        otp = pyotp.TOTP(self.totp_secret).now()
        phone1 = self._phone(age_seconds=400)
        phone2 = self._phone(age_seconds=400)
        self.assertEqual(
            phone1.post(
                reverse("qr_login_confirm", args=[login_id1]),
                data={"qr_secret": secret1, "totp_code": otp},
            ).status_code,
            302,
        )
        self.assertEqual(
            phone2.post(
                reverse("qr_login_confirm", args=[login_id2]),
                data={"qr_secret": secret2, "totp_code": otp},
            ).status_code,
            403,
        )

    def test_parallel_approvals_cas(self):
        qr_req, *_ = create_qr_login_request(self._request(), station=self.station)
        self.assertTrue(approve_qr_request(qr_req, self.user, self.membership, session_key="s1"))
        self.assertFalse(approve_qr_request(qr_req, self.user, self.membership, session_key="s2"))

    def test_parallel_exchanges_cas(self):
        qr_req, *_ = create_qr_login_request(self._request(), station=self.station)
        approve_qr_request(qr_req, self.user, self.membership, session_key="s1")
        self.assertTrue(exchange_qr_request(qr_req))
        self.assertFalse(exchange_qr_request(qr_req))

    # --- C. Bindung / Verwechslung ------------------------------------------------

    def test_foreign_browser_session_rejected(self):
        browser = Client()
        login_id, secret, _ = self._start(browser)
        attacker = Client()
        self.assertEqual(
            attacker.post(
                reverse("qr_login_status", args=[login_id]), HTTP_X_QR_SECRET=secret
            ).status_code,
            403,
        )
        self.assertEqual(
            attacker.post(
                reverse("qr_login_exchange", args=[login_id]), HTTP_X_QR_SECRET=secret
            ).status_code,
            403,
        )

    def test_wrong_station_membership_rejected(self):
        other_station = Station.objects.create(name="Other Wache", slug="other", is_active=True)
        other_user = User.objects.create_user(username="otheruser", password="testpass456")
        Membership.objects.create(
            user=other_user, station=other_station, role=Membership.Role.MEMBER, is_active=True
        )
        browser = Client()
        login_id, secret, _ = self._start(browser)
        phone = self._phone(user=other_user)
        self.assertEqual(
            phone.post(
                reverse("qr_login_confirm", args=[login_id]), data={"qr_secret": secret}
            ).status_code,
            403,
        )
        self.assertIsNone(QrLoginRequest.objects.get(pk=login_id).approved_by)

    def test_approval_with_login_id_only_rejected(self):
        browser = Client()
        login_id, _, _ = self._start(browser)
        phone = self._phone()
        self.assertEqual(
            phone.post(reverse("qr_login_confirm", args=[login_id]), data={}).status_code, 403
        )
        self.assertIsNone(QrLoginRequest.objects.get(pk=login_id).approved_by)

    def test_revocation_between_approval_and_exchange(self):
        browser = Client()
        login_id, secret, _ = self._start(browser)
        phone = self._phone()
        phone.post(reverse("qr_login_confirm", args=[login_id]), data={"qr_secret": secret})
        self.membership.is_active = False
        self.membership.save()
        resp = browser.post(reverse("qr_login_exchange", args=[login_id]), HTTP_X_QR_SECRET=secret)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(QrLoginRequest.objects.get(pk=login_id).state, QrLoginRequest.State.REVOKED)

    def test_logout_revokes_open_approvals(self):
        browser = Client()
        login_id, secret, _ = self._start(browser)
        phone = self._phone()
        phone.post(reverse("qr_login_confirm", args=[login_id]), data={"qr_secret": secret})
        phone.post(reverse("logout"))
        self.assertEqual(QrLoginRequest.objects.get(pk=login_id).state, QrLoginRequest.State.REVOKED)
        resp = browser.post(reverse("qr_login_exchange", args=[login_id]), HTTP_X_QR_SECRET=secret)
        self.assertEqual(resp.status_code, 409)

    # --- D. MFA / Frische ---------------------------------------------------------

    def test_stale_freshness_rejected(self):
        browser = Client()
        login_id, secret, _ = self._start(browser)
        phone = self._phone(age_seconds=301)
        self.assertEqual(
            phone.post(
                reverse("qr_login_confirm", args=[login_id]), data={"qr_secret": secret}
            ).status_code,
            403,
        )

    # --- E. CSRF / Transport ------------------------------------------------------

    def test_csrf_enforced_on_mutating_endpoints(self):
        csrf_client = Client(enforce_csrf_checks=True)
        self.assertEqual(csrf_client.post(reverse("qr_login_start")).status_code, 403)

        self.assertEqual(csrf_client.get(reverse("qr_login_wait")).status_code, 200)
        token = csrf_client.cookies["rwsth_csrf"].value
        start = csrf_client.post(reverse("qr_login_start"), HTTP_X_CSRFTOKEN=token)
        self.assertEqual(start.status_code, 200)
        login_id = start.json()["login_id"]

        csrf_client.force_login(self.user)
        self.assertEqual(
            csrf_client.post(reverse("qr_login_confirm", args=[login_id])).status_code, 403
        )

    def test_form_pages_use_same_origin_referrer_policy(self):
        """Regression: no-referrer made Chrome send Origin: null -> CSRF 403."""
        browser = Client()
        login_id, secret, _ = self._start(browser)
        phone = self._phone()

        manual = phone.get(reverse("qr_login_manual"))
        self.assertEqual(manual.status_code, 200)
        self.assertEqual(manual.headers["Referrer-Policy"], "same-origin")

        confirm = phone.get(reverse("qr_login_confirm", args=[login_id]))
        self.assertEqual(confirm.status_code, 200)
        self.assertEqual(confirm.headers["Referrer-Policy"], "same-origin")

        status = browser.post(reverse("qr_login_status", args=[login_id]), HTTP_X_QR_SECRET=secret)
        self.assertEqual(status.headers["Referrer-Policy"], "no-referrer")
        wait = browser.get(reverse("qr_login_wait"))
        self.assertEqual(wait.headers["Referrer-Policy"], "no-referrer")

    def test_secrets_and_pii_not_leaked(self):
        browser = Client()
        login_id, secret, manual_code = self._start(browser)
        status = browser.post(reverse("qr_login_status", args=[login_id]), HTTP_X_QR_SECRET=secret)
        body = status.content.decode()
        self.assertNotIn(secret, body)
        self.assertNotIn(manual_code, body)
        self.assertEqual(set(status.json().keys()), {"ok", "state"})
        self.assertEqual(status.headers["Cache-Control"], "no-store")
        self.assertEqual(status.headers["Pragma"], "no-cache")
        self.assertEqual(status.headers["Referrer-Policy"], "no-referrer")
        self.assertEqual(status.headers["X-Robots-Tag"], "noindex")

    def test_exchange_without_secret_rejected(self):
        browser = Client()
        login_id, secret, _ = self._start(browser)
        phone = self._phone()
        phone.post(reverse("qr_login_confirm", args=[login_id]), data={"qr_secret": secret})
        self.assertEqual(
            browser.post(reverse("qr_login_exchange", args=[login_id])).status_code, 403
        )
        self.assertEqual(QrLoginRequest.objects.get(pk=login_id).state, QrLoginRequest.State.APPROVED)

    def test_status_without_secret_rejected(self):
        browser = Client()
        login_id, _, _ = self._start(browser)
        self.assertEqual(browser.post(reverse("qr_login_status", args=[login_id])).status_code, 403)

    def test_manual_grant_not_usable_from_other_session(self):
        """M3 finding 3 counter-check: the grant lives server-side in one session."""
        browser = Client()
        login_id, _, manual_code = self._start(browser)
        phone1 = self._phone()
        self.assertEqual(
            phone1.post(reverse("qr_login_manual"), data={"manual_code": manual_code}).status_code,
            302,
        )
        phone2 = self._phone()
        self.assertEqual(
            phone2.post(reverse("qr_login_confirm", args=[login_id]), data={}).status_code, 403
        )
        self.assertIsNone(QrLoginRequest.objects.get(pk=login_id).approved_by)

    # --- F. Rate-Limit ------------------------------------------------------------

    def test_rate_limits(self):
        with override_settings(QR_LOGIN_RATE_LIMITS={"qr_start": (2, 60)}):
            client = Client()
            self.assertEqual(client.post(reverse("qr_login_start")).status_code, 200)
            self.assertEqual(client.post(reverse("qr_login_start")).status_code, 200)
            third = client.post(reverse("qr_login_start"))
            self.assertEqual(third.status_code, 429)
            self.assertEqual(third.json()["error"], "qr_rate_limited")

    # --- G. Zustandsmaschine / TTL -------------------------------------------------

    def test_ttl_expiry_119s_and_121s(self):
        browser = Client()
        start_time = timezone.now()
        with self.settings(QR_LOGIN_RATE_LIMITS={"qr_status": (120, 120)}):
            with self._patch_now(start_time):
                login_id, secret, _ = self._start(browser)
            with self._patch_now(start_time + timedelta(seconds=119)):
                ok = browser.post(reverse("qr_login_status", args=[login_id]), HTTP_X_QR_SECRET=secret)
                self.assertEqual(ok.status_code, 200)
                self.assertEqual(ok.json()["state"], "pending")
            with self._patch_now(start_time + timedelta(seconds=121)):
                expired = browser.post(
                    reverse("qr_login_status", args=[login_id]), HTTP_X_QR_SECRET=secret
                )
                self.assertEqual(expired.status_code, 200)
                self.assertEqual(expired.json()["state"], "expired")

    def _patch_now(self, value):
        from unittest.mock import patch

        return patch("django.utils.timezone.now", return_value=value)

    def test_feature_gate_disabled(self):
        with override_settings(QR_LOGIN_ENABLED=False):
            client = Client()
            start = client.post(reverse("qr_login_start"))
            self.assertEqual(start.status_code, 503)
            self.assertEqual(start.json()["error"], "qr_disabled")
            self.assertEqual(client.get(reverse("qr_login_wait")).status_code, 404)

    # --- H. Manueller Fallback ----------------------------------------------------

    def test_manual_code_fallback(self):
        browser = Client()
        login_id, secret, manual_code = self._start(browser)
        phone = self._phone()
        approve = phone.post(
            reverse("qr_login_confirm", args=[login_id]),
            data={"manual_code": manual_code.lower()},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(approve.status_code, 200)
        self.assertEqual(approve.json()["state"], "approved")
        exchange = browser.post(reverse("qr_login_exchange", args=[login_id]), HTTP_X_QR_SECRET=secret)
        self.assertEqual(exchange.status_code, 200)
        self.assertTrue(exchange.json()["ok"])
