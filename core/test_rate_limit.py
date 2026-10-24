import json

from django.test import RequestFactory, TestCase, override_settings

from .api.views import _token_rate_limit_key
from .middleware import ClientIPMiddleware
from .rate_limit import consume, hash_key


class ClientIPMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _request(self, **meta):
        return self.factory.get("/", **meta)

    @override_settings(TRUSTED_PROXY=False)
    def test_no_proxy_uses_remote_addr(self):
        request = self._request(REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="1.2.3.4")
        ClientIPMiddleware(lambda r: r)(request)
        self.assertEqual(request.client_ip, "10.0.0.1")

    @override_settings(TRUSTED_PROXY=True)
    def test_trusted_proxy_uses_x_forwarded_for(self):
        # Der Proxy hängt die echte Client-IP rechts an; links stehende
        # Einträge stammen vom Client und werden ignoriert.
        request = self._request(REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="1.2.3.4, 203.0.113.7")
        ClientIPMiddleware(lambda r: r)(request)
        self.assertEqual(request.client_ip, "203.0.113.7")

    @override_settings(TRUSTED_PROXY=True)
    def test_trusted_proxy_with_oversize_ip_falls_back(self):
        request = self._request(REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="x" * 200)
        ClientIPMiddleware(lambda r: r)(request)
        self.assertEqual(request.client_ip, "unknown")

    def test_missing_remote_addr_returns_unknown(self):
        request = self._request()
        ClientIPMiddleware(lambda r: r)(request)
        self.assertIn(request.client_ip, ["unknown", "127.0.0.1"])


class RateLimitConsumeTests(TestCase):
    @override_settings(RATELIMIT_KEY_SALT="test-salt")
    def test_consume_returns_true_within_limit(self):
        for _ in range(3):
            self.assertTrue(consume("test-bucket", "k1", limit=3, window_seconds=60))

    @override_settings(RATELIMIT_KEY_SALT="test-salt")
    def test_consume_returns_false_over_limit(self):
        for _ in range(2):
            consume("test-bucket-over", "k1", limit=2, window_seconds=60)
        self.assertFalse(consume("test-bucket-over", "k1", limit=2, window_seconds=60))

    @override_settings(RATELIMIT_KEY_SALT="test-salt")
    def test_consume_isolates_per_key(self):
        for _ in range(2):
            consume("test-bucket-isolate", "kA", limit=2, window_seconds=60)
        self.assertTrue(consume("test-bucket-isolate", "kB", limit=2, window_seconds=60))

    @override_settings(RATELIMIT_KEY_SALT="test-salt")
    def test_consume_isolates_per_bucket(self):
        consume("test-bucket-X", "k1", limit=1, window_seconds=60)
        self.assertTrue(consume("test-bucket-Y", "k1", limit=1, window_seconds=60))

    def test_hash_key_uses_salt(self):
        with override_settings(RATELIMIT_KEY_SALT="salt-A"):
            hash_a = hash_key("k1")
        with override_settings(RATELIMIT_KEY_SALT="salt-B"):
            hash_b = hash_key("k1")
        self.assertNotEqual(hash_a, hash_b)
        self.assertEqual(len(hash_a), 64)


class TokenRateLimitKeyTests(TestCase):
    """Regression: /token/ is documented (openapi_v1.yaml) as a JSON POST, but
    the key used request.POST, which is empty for JSON bodies, so the
    per-username bucket silently collapsed to IP-only."""

    def setUp(self):
        self.factory = RequestFactory()

    def _json_post(self, payload, ip="10.0.0.9"):
        request = self.factory.post(
            "/api/v1/token/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        request.client_ip = ip
        return request

    def test_json_body_username_is_part_of_key(self):
        key = _token_rate_limit_key(self._json_post({"username": "alice", "password": "x"}))
        self.assertEqual(key, "10.0.0.9|alice")

    def test_distinct_usernames_from_same_ip_get_distinct_keys(self):
        alice = _token_rate_limit_key(self._json_post({"username": "alice"}))
        bob = _token_rate_limit_key(self._json_post({"username": "bob"}))
        self.assertNotEqual(alice, bob)

    def test_form_encoded_username_still_works(self):
        request = self.factory.post("/api/v1/token/", data={"username": "carol"})
        request.client_ip = "10.0.0.9"
        self.assertEqual(_token_rate_limit_key(request), "10.0.0.9|carol")

    def test_missing_username_is_empty_component(self):
        key = _token_rate_limit_key(self._json_post({"password": "x"}))
        self.assertEqual(key, "10.0.0.9|")
