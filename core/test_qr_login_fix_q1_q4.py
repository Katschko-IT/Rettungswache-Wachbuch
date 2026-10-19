"""Regressionstests fuer die bestaetigten QR-Reviewbefunde Q1-Q4.

Deckt ausschliesslich die vier bestaetigten Grenzen ab:

- Q1: Eine per QR eingeloeste Session ist kein frischer Primaernachweis und
  darf weder sich selbst noch weitere QR-Anmeldungen bestaetigen.
- Q2: ``SITE_URL=https://...`` allein ist kein TLS-Nachweis; ohne sicheren
  Request bzw. ausdruecklich vertrauenswuerdigen Proxy bleibt das Gate zu.
- Q3: Abgelaufene/terminale QR-Anforderungen verbrauchen keinen TOTP-Zeitschritt;
  Approval und TOTP-Verbrauch sind atomar.
- Q4: Passkey-Reauth ist an genau eine gueltige ``login_id`` gebunden, die
  Challenge ist nach jedem Versuch verbraucht und rate-limitiert.

Alle Konten, Secrets und Schluessel sind synthetisch. Es werden keine
Produktionssettings abgeschwaecht.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pyotp
from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.crypto_at_rest import encrypt_secret
from core.models import (
    Membership,
    QrLoginRequest,
    QrTotpUse,
    Station,
    TotpDevice,
    WebAuthnCredential,
)
from core.qr_login import get_canonical_origin, is_qr_login_enabled

QR_SETTINGS = {
    "QR_LOGIN_ENABLED": True,
    "QR_LOGIN_ALLOW_INSECURE_TEST_ORIGIN": True,
    "SITE_URL": "https://testserver",
    "MFA_ENABLED": True,
    "MFA_REQUIRED": False,
    "WEBAUTHN_ENABLED": True,
    "WEBAUTHN_RP_ID": "testserver",
    "WEBAUTHN_ORIGIN": "https://testserver",
}


class QrFixBase(TestCase):
    def setUp(self):
        self.station = Station.objects.create(
            name="Hauptwache",
            slug=getattr(settings, "DEFAULT_STATION_SLUG", "rettungswache"),
            is_active=True,
        )
        self.other_station = Station.objects.create(
            name="Nebenwache", slug="nebenwache", is_active=True
        )

        self.user_mfa = User.objects.create_user(
            username="fix_mfa", password="synthetic-pass-1", first_name="Mfa"
        )
        Membership.objects.create(
            user=self.user_mfa,
            station=self.station,
            role=Membership.Role.MEMBER,
            is_active=True,
        )
        self.totp_secret = pyotp.random_base32()
        TotpDevice.objects.create(
            user=self.user_mfa,
            secret=encrypt_secret(self.totp_secret),
            is_confirmed=True,
            confirmed_at=timezone.now(),
        )

        self.user_simple = User.objects.create_user(
            username="fix_simple", password="synthetic-pass-2", first_name="Simple"
        )
        Membership.objects.create(
            user=self.user_simple,
            station=self.station,
            role=Membership.Role.MEMBER,
            is_active=True,
        )

        self.user_passkey = User.objects.create_user(
            username="fix_passkey", password="synthetic-pass-3", first_name="Passkey"
        )
        Membership.objects.create(
            user=self.user_passkey,
            station=self.station,
            role=Membership.Role.MEMBER,
            is_active=True,
        )
        WebAuthnCredential.objects.create(
            user=self.user_passkey,
            credential_id="c3ludGhldGljLWNyZWQtMQ",
            public_key="synthetic-public-key",
            sign_count=1,
            device_name="Synthetisches Geraet",
        )

        self.user_foreign = User.objects.create_user(
            username="fix_foreign", password="synthetic-pass-4", first_name="Foreign"
        )
        Membership.objects.create(
            user=self.user_foreign,
            station=self.other_station,
            role=Membership.Role.MEMBER,
            is_active=True,
        )
        WebAuthnCredential.objects.create(
            user=self.user_foreign,
            credential_id="c3ludGhldGljLWNyZWQtMg",
            public_key="synthetic-public-key-2",
            sign_count=1,
            device_name="Synthetisches Fremdgeraet",
        )

    def _stamp(self, client, user, auth_method="password", age_seconds=10):
        session = client.session
        session["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
        session["auth_time"] = int(timezone.now().timestamp()) - age_seconds
        session["auth_user_id"] = user.pk
        session["auth_method"] = auth_method
        session.save()

    def _start(self, client):
        resp = client.post(reverse("qr_login_start"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        return data["login_id"], data["qr_url"].split("#secret=", 1)[1]

    def _phone(self, user, auth_method="password", age_seconds=10):
        phone = Client()
        phone.force_login(user)
        self._stamp(phone, user, auth_method=auth_method, age_seconds=age_seconds)
        return phone

    def _approve(self, client, login_id, secret, **extra):
        payload = {"qr_secret": secret}
        payload.update(extra)
        return client.post(
            reverse("qr_login_confirm", args=[login_id]),
            data=payload,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )


@override_settings(**QR_SETTINGS)
class Q1QrSessionIsNotFreshTests(QrFixBase):
    def test_qr_stamped_session_cannot_approve(self):
        login_id, secret = self._start(Client())
        phone = self._phone(self.user_mfa, auth_method="qr", age_seconds=10)
        self.assertEqual(phone.get(reverse("qr_login_confirm", args=[login_id])).status_code, 200)
        resp = self._approve(phone, login_id, secret)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(QrLoginRequest.objects.get(pk=login_id).state, QrLoginRequest.State.SCANNED)

    def test_qr_stamped_non_mfa_session_cannot_approve(self):
        login_id, secret = self._start(Client())
        phone = self._phone(self.user_simple, auth_method="qr", age_seconds=10)
        resp = self._approve(phone, login_id, secret)
        self.assertEqual(resp.status_code, 403)

    def test_exchanged_session_cannot_approve_next_qr_login(self):
        browser = Client()
        first_id, first_secret = self._start(browser)
        phone = self._phone(self.user_mfa, age_seconds=10)
        self.assertEqual(self._approve(phone, first_id, first_secret).status_code, 200)
        exchange = browser.post(
            reverse("qr_login_exchange", args=[first_id]), HTTP_X_QR_SECRET=first_secret
        )
        self.assertEqual(exchange.status_code, 200)
        self.assertEqual(browser.session["auth_method"], "qr")

        second_id, second_secret = self._start(browser)
        browser.get(reverse("qr_login_confirm", args=[second_id]))
        resp = self._approve(browser, second_id, second_secret)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(
            QrLoginRequest.objects.get(pk=second_id).state, QrLoginRequest.State.SCANNED
        )

    def test_same_session_cannot_approve_its_own_qr_request(self):
        client = Client()
        client.force_login(self.user_mfa)
        self._stamp(client, self.user_mfa, age_seconds=10)
        login_id, secret = self._start(client)
        resp = self._approve(client, login_id, secret)
        self.assertEqual(resp.status_code, 403)


class Q2TlsGateTests(TestCase):
    def _request(self, secure=False, forwarded=None):
        factory = RequestFactory()
        extra = {}
        if forwarded is not None:
            extra["HTTP_X_FORWARDED_PROTO"] = forwarded
        return factory.post("/anmelden/qr/start/", secure=secure, **extra)

    @override_settings(
        QR_LOGIN_ENABLED=True,
        QR_LOGIN_ALLOW_INSECURE_TEST_ORIGIN=False,
        SITE_URL="https://wachbuch.example",
        TRUSTED_PROXY=False,
    )
    def test_https_site_url_does_not_secure_plain_http_request(self):
        request = self._request(secure=False)
        self.assertIsNone(get_canonical_origin(request))
        self.assertFalse(is_qr_login_enabled(request))

    @override_settings(
        QR_LOGIN_ENABLED=True, QR_LOGIN_ALLOW_INSECURE_TEST_ORIGIN=False,
        SITE_URL="https://wachbuch.example", TRUSTED_PROXY=False,
    )
    def test_forwarded_proto_ignored_without_explicit_trusted_proxy(self):
        request = self._request(secure=False, forwarded="https")
        self.assertIsNone(get_canonical_origin(request))

    @override_settings(
        QR_LOGIN_ENABLED=True, QR_LOGIN_ALLOW_INSECURE_TEST_ORIGIN=False,
        SITE_URL="https://wachbuch.example", TRUSTED_PROXY=True,
    )
    def test_forwarded_proto_accepted_with_explicit_trusted_proxy(self):
        request = self._request(secure=False, forwarded="https")
        self.assertEqual(get_canonical_origin(request), "https://wachbuch.example")
        self.assertTrue(is_qr_login_enabled(request))

    @override_settings(
        QR_LOGIN_ENABLED=True, QR_LOGIN_ALLOW_INSECURE_TEST_ORIGIN=False,
        SITE_URL="https://wachbuch.example", TRUSTED_PROXY=False,
    )
    def test_secure_request_uses_https_origin(self):
        request = self._request(secure=True)
        self.assertEqual(get_canonical_origin(request), "https://wachbuch.example")


@override_settings(**QR_SETTINGS)
class Q3TotpOrderingTests(QrFixBase):
    def _denied_request(self):
        login_id, secret = self._start(Client())
        phone = self._phone(self.user_mfa, age_seconds=10)
        deny = phone.post(reverse("qr_login_deny", args=[login_id]), HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(deny.status_code, 200)
        return login_id, secret

    def test_terminal_request_does_not_consume_totp_step(self):
        login_id, secret = self._denied_request()
        phone = self._phone(self.user_mfa, age_seconds=400)
        otp = pyotp.TOTP(self.totp_secret).now()
        resp = self._approve(phone, login_id, secret, totp_code=otp)
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(QrTotpUse.objects.filter(user=self.user_mfa).count(), 0)

    def test_expired_request_does_not_consume_totp_step(self):
        login_id, secret = self._start(Client())
        QrLoginRequest.objects.filter(pk=login_id).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        phone = self._phone(self.user_mfa, age_seconds=400)
        otp = pyotp.TOTP(self.totp_secret).now()
        resp = self._approve(phone, login_id, secret, totp_code=otp)
        self.assertEqual(resp.status_code, 410)
        self.assertEqual(QrTotpUse.objects.filter(user=self.user_mfa).count(), 0)

    def test_already_used_totp_step_rolls_back_approval(self):
        login_id, secret = self._start(Client())
        step = pyotp.TOTP(self.totp_secret).timecode(timezone.now())
        QrTotpUse.objects.create(user=self.user_mfa, time_step=step)
        phone = self._phone(self.user_mfa, age_seconds=400)
        self.assertEqual(phone.get(reverse("qr_login_confirm", args=[login_id])).status_code, 200)
        otp = pyotp.TOTP(self.totp_secret).now()
        resp = self._approve(phone, login_id, secret, totp_code=otp)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(
            QrLoginRequest.objects.get(pk=login_id).state, QrLoginRequest.State.SCANNED
        )

    def test_expired_request_reports_no_approval(self):
        login_id, secret = self._start(Client())
        QrLoginRequest.objects.filter(pk=login_id).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        phone = self._phone(self.user_mfa, age_seconds=10)
        resp = self._approve(phone, login_id, secret)
        self.assertEqual(resp.status_code, 410)


@override_settings(**QR_SETTINGS)
class Q4PasskeyBindingTests(QrFixBase):
    def _options(self, client, login_id):
        return client.post(reverse("qr_login_passkey_options", args=[login_id]))

    def _verify(self, client, login_id, credential=None):
        return client.post(
            reverse("qr_login_passkey_verify", args=[login_id]),
            data=json.dumps({"credential": credential or {"id": "synthetic", "response": {}}}),
            content_type="application/json",
        )

    def test_options_reject_foreign_station(self):
        login_id, _ = self._start(Client())
        foreign = self._phone(self.user_foreign, age_seconds=10)
        self.assertEqual(self._options(foreign, login_id).status_code, 403)

    def test_options_reject_terminal_request(self):
        login_id, _ = self._start(Client())
        phone = self._phone(self.user_mfa, age_seconds=10)
        self.assertEqual(phone.post(reverse("qr_login_deny", args=[login_id]), HTTP_X_REQUESTED_WITH="XMLHttpRequest").status_code, 200)
        passkey_phone = self._phone(self.user_passkey, age_seconds=10)
        self.assertEqual(self._options(passkey_phone, login_id).status_code, 409)

    def test_options_reject_unknown_login_id(self):
        phone = self._phone(self.user_passkey, age_seconds=10)
        self.assertEqual(
            self._options(phone, "00000000-0000-4000-8000-000000000000").status_code, 404
        )

    def test_challenge_bound_to_login_id_and_consumed_on_failure(self):
        first_id, _ = self._start(Client())
        second_id, _ = self._start(Client())
        phone = self._phone(self.user_passkey, age_seconds=400)
        self.assertEqual(self._options(phone, first_id).status_code, 200)
        self.assertIn("qr_passkey_challenge", phone.session)

        resp = self._verify(phone, second_id)
        self.assertIn(resp.status_code, (400, 403))
        self.assertNotIn("qr_passkey_challenge", phone.session)

    def test_challenge_consumed_after_failed_assertion(self):
        login_id, _ = self._start(Client())
        phone = self._phone(self.user_passkey, age_seconds=400)
        self.assertEqual(self._options(phone, login_id).status_code, 200)
        self.assertEqual(self._verify(phone, login_id).status_code, 403)
        self.assertNotIn("qr_passkey_challenge", phone.session)

    @override_settings(QR_LOGIN_RATE_LIMITS={"qr_passkey": (1, 300)})
    def test_passkey_options_are_rate_limited(self):
        login_id, _ = self._start(Client())
        phone = self._phone(self.user_passkey, age_seconds=400)
        self.assertEqual(self._options(phone, login_id).status_code, 200)
        self.assertEqual(self._options(phone, login_id).status_code, 429)

    def test_passkey_reauth_stamp_is_bound_to_login_id(self):
        first_id, first_secret = self._start(Client())
        second_id, second_secret = self._start(Client())
        phone = self._phone(self.user_passkey, age_seconds=400)
        session = phone.session
        session["qr_passkey_reauth_user_id"] = self.user_passkey.pk
        session["qr_passkey_reauth_time"] = int(timezone.now().timestamp()) - 10
        session["qr_passkey_reauth_login_id"] = str(first_id)
        session.save()

        self.assertEqual(self._approve(phone, second_id, second_secret).status_code, 403)
        self.assertEqual(self._approve(phone, first_id, first_secret).status_code, 200)
