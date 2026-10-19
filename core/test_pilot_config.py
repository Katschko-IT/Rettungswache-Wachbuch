"""Tests for the local HTTPS pilot configuration (config/pilot_settings.py).

Validates security invariants: DEBUG=False, strict fail-closed host allowlists
without wildcards, secure cookie flags, proxy SSL header, CSRF trusted origins,
and HSTS=0 for local pilot staging.
"""

from __future__ import annotations

import importlib
import os
import sys
from unittest import TestCase
from unittest.mock import patch


class PilotSettingsInvariantsTests(TestCase):
    def _load_pilot_settings(self, env_overrides=None):
        base_env = {
            "DJANGO_SECRET_KEY": "test-pilot-secret-key-not-production",
            "DJANGO_DEBUG": "0",
            "ALLOWED_HOSTS": "pilot.local,127.0.0.1",
            "CSRF_TRUSTED_ORIGINS": "https://pilot.local",
        }
        if env_overrides:
            base_env.update(env_overrides)

        with patch.dict(os.environ, base_env, clear=False):
            if "config.pilot_settings" in sys.modules:
                del sys.modules["config.pilot_settings"]
            return importlib.import_module("config.pilot_settings")

    def test_debug_is_always_false(self):
        settings = self._load_pilot_settings({"DJANGO_DEBUG": "1"})
        self.assertFalse(settings.DEBUG)

    def test_secure_cookies_enabled(self):
        settings = self._load_pilot_settings()
        self.assertTrue(settings.SESSION_COOKIE_SECURE)
        self.assertTrue(settings.CSRF_COOKIE_SECURE)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, "Lax")
        self.assertEqual(settings.CSRF_COOKIE_SAMESITE, "Lax")

    def test_proxy_ssl_header_configured(self):
        settings = self._load_pilot_settings()
        self.assertEqual(
            settings.SECURE_PROXY_SSL_HEADER,
            ("HTTP_X_FORWARDED_PROTO", "https"),
        )

    def test_hsts_disabled_for_pilot(self):
        settings = self._load_pilot_settings()
        self.assertEqual(settings.SECURE_HSTS_SECONDS, 0)
        self.assertFalse(settings.SECURE_HSTS_INCLUDE_SUBDOMAINS)
        self.assertFalse(settings.SECURE_HSTS_PRELOAD)

    def test_x_frame_options_is_deny(self):
        settings = self._load_pilot_settings()
        self.assertEqual(settings.X_FRAME_OPTIONS, "DENY")

    def test_allowed_hosts_and_csrf_loaded_from_env(self):
        settings = self._load_pilot_settings({
            "ALLOWED_HOSTS": "pilot-station.test, 192.0.2.1",
            "CSRF_TRUSTED_ORIGINS": "https://pilot-station.test",
        })
        self.assertEqual(settings.ALLOWED_HOSTS, ["pilot-station.test", "192.0.2.1"])
        self.assertEqual(settings.CSRF_TRUSTED_ORIGINS, ["https://pilot-station.test"])

    def test_wildcard_hosts_are_rejected_or_excluded(self):
        settings = self._load_pilot_settings({
            "ALLOWED_HOSTS": "*, pilot.local, *.example.test",
            "CSRF_TRUSTED_ORIGINS": "*, https://pilot.local",
        })
        self.assertNotIn("*", settings.ALLOWED_HOSTS)
        self.assertNotIn("*.example.test", settings.ALLOWED_HOSTS)
        self.assertEqual(settings.ALLOWED_HOSTS, ["pilot.local"])
        self.assertNotIn("*", settings.CSRF_TRUSTED_ORIGINS)
        self.assertEqual(settings.CSRF_TRUSTED_ORIGINS, ["https://pilot.local"])

    def test_empty_hosts_fail_closed(self):
        settings = self._load_pilot_settings({
            "ALLOWED_HOSTS": "",
            "CSRF_TRUSTED_ORIGINS": "",
        })
        self.assertEqual(settings.ALLOWED_HOSTS, [])
        self.assertEqual(settings.CSRF_TRUSTED_ORIGINS, [])
