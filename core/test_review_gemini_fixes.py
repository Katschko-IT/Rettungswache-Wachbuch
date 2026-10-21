"""Regression tests for Gemini security and reliability fixes (R1 and R2).

Verifies:
- R1: HTTP redirects blocked without secondary transport, port and userinfo
      validation prior to transport in core/traffic.py.
- R2: Non-dict JSON bodies and invalid kdf_iterations rejected with 400 instead
      of 500 in core/secure_views.py.
"""

from __future__ import annotations

import json
from email.message import Message
from io import BytesIO
from unittest.mock import patch
from urllib.response import addinfourl

from django.contrib.auth.models import User
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from core.models import UserCryptoIdentity
from core.traffic import (
    TrafficUnavailable,
    _guarded_request,
    _guarded_request_nina,
    _urlopen,
)


def _make_response(body: bytes, code: int = 200, headers: dict | None = None, url: str = "https://verkehr.autobahn.de/test"):
    h = Message()
    if headers:
        for k, v in headers.items():
            h[k] = v
    r = addinfourl(BytesIO(body), h, url, code)
    r.msg = "OK" if code == 200 else "Redirect/Error"
    return r


class TrafficHardeningTests(SimpleTestCase):
    def test_redirects_blocked_in_guarded_request(self):
        for code in (301, 302, 303, 307, 308):
            with self.subTest(code=code):
                seen = []

                def https_open(handler, request):
                    seen.append(request.full_url)
                    return _make_response(b"", code=code, headers={"Location": "http://127.0.0.1:54321/evil"}, url=request.full_url)

                def http_open(handler, request):
                    seen.append(request.full_url)
                    return _make_response(b"EVIL", code=200, url=request.full_url)

                with patch("urllib.request.HTTPSHandler.https_open", new=https_open), \
                     patch("urllib.request.HTTPHandler.http_open", new=http_open):
                    with self.assertRaises(TrafficUnavailable):
                        _guarded_request("https://verkehr.autobahn.de/test", accept="text/plain")
                self.assertEqual(len(seen), 1, "Redirect target must not be contacted")

    def test_redirects_blocked_in_guarded_request_nina(self):
        seen = []

        def https_open(handler, request):
            seen.append(request.full_url)
            return _make_response(b"", code=302, headers={"Location": "http://127.0.0.1:54321/evil"}, url=request.full_url)

        def http_open(handler, request):
            seen.append(request.full_url)
            return _make_response(b"EVIL", code=200, url=request.full_url)

        with patch("urllib.request.HTTPSHandler.https_open", new=https_open), \
             patch("urllib.request.HTTPHandler.http_open", new=http_open):
            with self.assertRaises(TrafficUnavailable):
                _guarded_request_nina()
        self.assertEqual(len(seen), 1, "Redirect target must not be contacted")

    def test_invalid_ports_rejected_before_transport(self):
        invalid_urls = [
            "https://verkehr.autobahn.de:8443/test",
            "https://verkehr.autobahn.de:80/test",
            "https://verkehr.autobahn.de:8080/test",
            "https://verkehr.autobahn.de:abc/test",
        ]
        def forbidden(*args, **kwargs):
            raise AssertionError("Transport reached despite invalid port")

        for url in invalid_urls:
            with self.subTest(url=url), patch("urllib.request.HTTPSHandler.https_open", side_effect=forbidden):
                with self.assertRaises(TrafficUnavailable):
                    _guarded_request(url, accept="text/plain")

    def test_userinfo_in_url_rejected_before_transport(self):
        userinfo_urls = [
            "https://user:pass@verkehr.autobahn.de/test",
            "https://user@verkehr.autobahn.de/test",
            "https://:pass@verkehr.autobahn.de/test",
        ]
        def forbidden(*args, **kwargs):
            raise AssertionError("Transport reached despite userinfo")

        for url in userinfo_urls:
            with self.subTest(url=url), patch("urllib.request.HTTPSHandler.https_open", side_effect=forbidden):
                with self.assertRaises(TrafficUnavailable):
                    _guarded_request(url, accept="text/plain")

    def test_disallowed_hosts_and_schemes_rejected_before_transport(self):
        bad_urls = [
            "http://verkehr.autobahn.de/test",
            "https://untrusted-host.example.com/test",
            "ftp://verkehr.autobahn.de/test",
        ]
        def forbidden(*args, **kwargs):
            raise AssertionError("Transport reached despite disallowed host/scheme")

        for url in bad_urls:
            with self.subTest(url=url), patch("urllib.request.HTTPSHandler.https_open", side_effect=forbidden):
                with self.assertRaises(TrafficUnavailable):
                    _guarded_request(url, accept="text/plain")

    def test_response_size_exceeded_raises_traffic_unavailable(self):
        huge_body = b"X" * (3 * 1024 * 1024 + 2)
        with patch("core.traffic._urlopen", return_value=_make_response(huge_body)):
            with self.assertRaises(TrafficUnavailable):
                _guarded_request("https://verkehr.autobahn.de/test", accept="text/plain")

    def test_guarded_request_happy_path(self):
        valid_body = b"valid traffic content"
        with patch("core.traffic._urlopen", return_value=_make_response(valid_body)):
            result = _guarded_request("https://verkehr.autobahn.de/test", accept="text/plain")
        self.assertEqual(result, valid_body)

    def test_guarded_request_standard_port_443_accepted(self):
        valid_body = b"port 443 content"
        with patch("core.traffic._urlopen", return_value=_make_response(valid_body)):
            result = _guarded_request("https://verkehr.autobahn.de:443/test", accept="text/plain")
        self.assertEqual(result, valid_body)

    def test_guarded_request_nina_happy_path(self):
        nina_data = [{"id": "warn-1", "title": "Testwarnung"}]
        encoded = json.dumps(nina_data).encode("utf-8")
        with patch("core.traffic._urlopen", return_value=_make_response(encoded)):
            result = _guarded_request_nina()
        self.assertEqual(result, nina_data)

    def test_guarded_request_nina_rejects_non_list_json(self):
        encoded = json.dumps({"error": "not a list"}).encode("utf-8")
        with patch("core.traffic._urlopen", return_value=_make_response(encoded)):
            with self.assertRaises(TrafficUnavailable):
                _guarded_request_nina()


class CryptoHardeningTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="gemini-tester", password="secure-test-password")
        self.client = Client(raise_request_exception=False)
        self.client.force_login(self.user)
        self.valid_payload = {
            "public_jwk": {
                "kty": "EC",
                "crv": "P-256",
                "x": "dGVzdF94X2Nvb3JkaW5hdGVfYmFzZTY0",
                "y": "dGVzdF95X2Nvb3JkaW5hdGVfYmFzZTY0",
            },
            "wrapped_private_jwk": "W" * 64,
            "kdf_salt": "S" * 32,
            "kdf_iterations": 210000,
        }

    def test_non_dict_json_bodies_return_400(self):
        for payload in (["list", "of", "items"], "just-a-string", 12345, True):
            with self.subTest(payload=payload):
                response = self.client.post(
                    reverse("crypto_setup"),
                    json.dumps(payload),
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 400)
                data = response.json()
                self.assertFalse(data.get("ok"))
                self.assertEqual(data.get("error"), "Ungültige Anfrage.")
        self.assertFalse(UserCryptoIdentity.objects.filter(user=self.user).exists())

    def test_bad_iterations_types_return_400(self):
        bad_types = ["not-an-integer", {"bad": "dict"}, [210000]]
        for val in bad_types:
            with self.subTest(val=val):
                payload = dict(self.valid_payload)
                payload["kdf_iterations"] = val
                response = self.client.post(
                    reverse("crypto_setup"),
                    json.dumps(payload),
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 400)
                data = response.json()
                self.assertFalse(data.get("ok"))
                self.assertEqual(data.get("error"), "KDF-Iterationen ungültig.")
        self.assertFalse(UserCryptoIdentity.objects.filter(user=self.user).exists())

    def test_iterations_out_of_range_return_400(self):
        for val in (99999, 1000001, 0, -10):
            with self.subTest(val=val):
                payload = dict(self.valid_payload)
                payload["kdf_iterations"] = val
                response = self.client.post(
                    reverse("crypto_setup"),
                    json.dumps(payload),
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 400)
                data = response.json()
                self.assertFalse(data.get("ok"))
                self.assertEqual(data.get("error"), "KDF-Iterationen ungültig.")
        self.assertFalse(UserCryptoIdentity.objects.filter(user=self.user).exists())

    def test_crypto_setup_happy_path_with_explicit_iterations(self):
        payload = dict(self.valid_payload)
        payload["kdf_iterations"] = 350000
        response = self.client.post(
            reverse("crypto_setup"),
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get("ok"))
        identity = UserCryptoIdentity.objects.filter(user=self.user).first()
        self.assertIsNotNone(identity)
        self.assertEqual(identity.kdf_iterations, 350000)

    def test_crypto_setup_happy_path_with_default_iterations(self):
        payload = dict(self.valid_payload)
        del payload["kdf_iterations"]
        response = self.client.post(
            reverse("crypto_setup"),
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get("ok"))
        identity = UserCryptoIdentity.objects.filter(user=self.user).first()
        self.assertIsNotNone(identity)
        self.assertEqual(identity.kdf_iterations, 210000)

    def test_crypto_setup_happy_path_with_empty_string_iterations_uses_default(self):
        payload = dict(self.valid_payload)
        payload["kdf_iterations"] = ""
        response = self.client.post(
            reverse("crypto_setup"),
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get("ok"))
        identity = UserCryptoIdentity.objects.filter(user=self.user).first()
        self.assertIsNotNone(identity)
        self.assertEqual(identity.kdf_iterations, 210000)

    def test_crypto_setup_rejection_when_keys_already_exist_without_replace(self):
        self.client.post(
            reverse("crypto_setup"),
            json.dumps(self.valid_payload),
            content_type="application/json",
        )
        second_response = self.client.post(
            reverse("crypto_setup"),
            json.dumps(self.valid_payload),
            content_type="application/json",
        )
        self.assertEqual(second_response.status_code, 400)
        self.assertEqual(second_response.json().get("error"), "Schlüssel existieren bereits.")

    def test_crypto_setup_replace_existing_keys_happy_path(self):
        self.client.post(
            reverse("crypto_setup"),
            json.dumps(self.valid_payload),
            content_type="application/json",
        )
        replace_payload = dict(self.valid_payload)
        replace_payload["replace"] = True
        replace_payload["kdf_iterations"] = 400000
        response = self.client.post(
            reverse("crypto_setup"),
            json.dumps(replace_payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        identity = UserCryptoIdentity.objects.filter(user=self.user).first()
        self.assertEqual(identity.kdf_iterations, 400000)
