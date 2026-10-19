"""Phase-1 M1: activation-token redaction for development and access logs.

These tests exercise the *configured* handlers (real Django logging config),
real request paths and the real formatter. Synthetic tokens only.
"""

from __future__ import annotations

import io
import logging
from contextlib import ExitStack
from datetime import timedelta
from unittest.mock import patch

from django.test import Client, TestCase
from django.test.client import Client as CSRFClient
from django.utils import timezone

from core.logging_redaction import ActivationRedactingFormatter
from core.models import Station, User
from core.setup_wizard import create_activation

TOKEN = "SYNTHETIC-phase1-m1-token-not-a-credential"


def _console_streams(stack):
    """Redirect every configured console handler to one StringIO."""
    stream = io.StringIO()
    handlers = list(logging.getLogger().handlers)
    for name in ("django.request", "django.server", "wachbuch.errors"):
        handlers.extend(logging.getLogger(name).handlers)
    for handler in {id(h): h for h in handlers}.values():
        stack.enter_context(patch.object(handler, "stream", stream))
    return stream


class DjangoServerLoggerConfigTests(TestCase):
    def test_django_server_uses_redacting_formatter(self):
        logger = logging.getLogger("django.server")
        self.assertFalse(logger.propagate)
        self.assertEqual(logger.level, logging.INFO)
        self.assertTrue(logger.handlers)
        for handler in logger.handlers:
            self.assertIsInstance(handler.formatter, ActivationRedactingFormatter)


class PathRedactionUnitTests(TestCase):
    def test_redaction_is_idempotent(self):
        from core.errors import redact_request_path

        once = redact_request_path(f"/aktivieren/{TOKEN}/")
        self.assertEqual(redact_request_path(once), once)
        self.assertEqual(once, "/aktivieren/[redacted]/")

    def test_punctuation_is_preserved(self):
        from core.errors import redact_request_path

        for punct in (",", ";", ")", "]", "}"):
            with self.subTest(punct=punct):
                self.assertEqual(
                    redact_request_path(f"/aktivieren/{TOKEN}{punct} method=GET"),
                    f"/aktivieren/[redacted]{punct} method=GET",
                )
        self.assertEqual(
            redact_request_path(f"/aktivieren/{TOKEN}/, method=GET"),
            "/aktivieren/[redacted]/, method=GET",
        )

    def test_query_string_does_not_leak_token(self):
        from core.errors import redact_request_path

        self.assertEqual(
            redact_request_path(f"/aktivieren/{TOKEN}?next=/, "),
            "/aktivieren/[redacted]?next=/, ",
        )

    def test_formatter_redacts_percent_mapping_and_traceback(self):
        formatter = ActivationRedactingFormatter("%(message)s")
        record = logging.LogRecord(
            "wachbuch.errors", logging.WARNING, __file__, 1,
            "Path: %(path)s", ({"path": f"/aktivieren/{TOKEN}/"},), None,
        )
        self.assertNotIn(TOKEN, formatter.format(record))

        try:
            raise ValueError(f"failed at /aktivieren/{TOKEN}/")
        except ValueError:
            record = logging.LogRecord(
                "wachbuch.errors", logging.ERROR, __file__, 1,
                "boom %s", (f"/aktivieren/{TOKEN}/",), __import__("sys").exc_info(),
            )
        output = formatter.format(record)
        self.assertIn("[redacted]", output)
        self.assertNotIn(TOKEN, output)


class RealRequestRedactionTests(TestCase):
    """Each status is produced by a real request, then the configured handler
    output is checked. django.server records mirror runserver's format."""

    def setUp(self):
        self.station = Station.objects.create(name="Wache Log", slug="wache-log")
        self.user = User.objects.create_user("loguser", password=None)
        self.user.set_unusable_password()
        self.user.save()
        self.activation, self.raw = create_activation(
            user=self.user, station=self.station, created_by=None
        )

    def _capture(self, path, *, method="get", status=200, client=None, **kwargs):
        client = client or Client()
        with ExitStack() as stack:
            stream = _console_streams(stack)
            response = getattr(client, method)(path, **kwargs)
            self.assertEqual(response.status_code, status)
            # runserver-style access record through the real configured logger
            logging.getLogger("django.server").info(
                '%s "%s" %s %s', "127.0.0.1", f"GET {path} HTTP/1.1", status, "-"
            )
        return response, stream.getvalue()

    def test_200_activation_form(self):
        _response, output = self._capture(f"/aktivieren/{self.raw}/", status=200)
        self.assertIn("[redacted]", output)
        self.assertNotIn(self.raw, output)
        self.assertIn("200", output)

    def test_301_missing_trailing_slash(self):
        _response, output = self._capture(f"/aktivieren/{self.raw}", status=301)
        self.assertIn("[redacted]", output)
        self.assertNotIn(self.raw, output)

    def test_403_csrf_failure(self):
        client = CSRFClient(enforce_csrf_checks=True)
        _response, output = self._capture(
            f"/aktivieren/{self.raw}/", method="post", status=403, client=client,
            data={"password1": "x", "password2": "x"},
        )
        self.assertIn("[redacted]", output)
        self.assertNotIn(self.raw, output)
        self.assertIn("403", output)

    def test_410_unknown_token(self):
        _response, output = self._capture(f"/aktivieren/{TOKEN}/", status=410)
        self.assertIn("[redacted]", output)
        self.assertNotIn(TOKEN, output)
        self.assertIn("410", output)

    def test_429_rate_limited(self):
        fixed = timezone.now().replace(second=30, microsecond=0)
        with patch("core.rate_limit.timezone.now", return_value=fixed):
            for index in range(60):
                Client().get(f"/aktivieren/unbekannt-{index}/")
            _response, output = self._capture(f"/aktivieren/{TOKEN}/", status=429)
        self.assertIn("[redacted]", output)
        self.assertNotIn(TOKEN, output)
        self.assertIn("429", output)

    def test_500_server_error(self):
        with patch("core.setup_views.find_activation", side_effect=RuntimeError("boom")):
            _response, output = self._capture(
                f"/aktivieren/{self.raw}/", status=500,
                client=Client(raise_request_exception=False),
            )
        self.assertIn("[redacted]", output)
        self.assertNotIn(self.raw, output)
        self.assertIn("500", output)


class GunicornLoggerTests(TestCase):
    def test_access_atoms_redact_token_and_keep_fields(self):
        from core.gunicorn_logging import RedactingGunicornLogger

        from gunicorn import glogging

        logger = RedactingGunicornLogger.__new__(RedactingGunicornLogger)
        with patch.object(
            glogging.Logger,
            "atoms",
            return_value={
                "r": f'GET /aktivieren/{TOKEN}/ HTTP/1.1',
                "U": f"/aktivieren/{TOKEN}/",
                "s": "200",
                "m": "GET",
            },
        ):
            atoms = logger.atoms(None, None, {}, timedelta(seconds=1))
        self.assertNotIn(TOKEN, atoms["r"])
        self.assertNotIn(TOKEN, atoms["U"])
        self.assertIn("[redacted]", atoms["r"])
        self.assertEqual(atoms["s"], "200")
        self.assertEqual(atoms["m"], "GET")
