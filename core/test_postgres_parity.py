"""Gleiches Verhalten unter SQLite und PostgreSQL (ROADMAP 0.27 Nr. 1).

PostgreSQL prüft Spaltentypen streng: Ein ``GenericIPAddressField`` ist dort
``inet`` und nimmt keinen Platzhalter wie „unknown“ an. SQLite speichert ihn
als Text, deshalb fiel der Fehler nur gegen PostgreSQL auf: Jede Anmeldung
ohne gültige Client-Adresse (auch jedes ``Client.force_login`` in den Tests)
brach mit einem Fehler ab. Die CI prüft beide Datenbanken (Jobs ``django`` und
``django-postgres``).
"""
from axes.models import AccessAttempt, AccessLog
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.test import Client, RequestFactory, TestCase, override_settings

from core.middleware import axes_client_ip, client_ip_from_request, rate_limit_ip

PASSWORD = "x-test-pass-123"


def _request(**meta):
    """POST an die Anmeldung; ohne REMOTE_ADDR, wenn keine angegeben ist."""
    request = RequestFactory().post("/anmelden/", **meta)
    if "REMOTE_ADDR" not in meta:
        request.META.pop("REMOTE_ADDR", None)
    return request


class AxesClientIpTests(TestCase):
    def test_valid_addresses_are_returned(self):
        self.assertEqual(axes_client_ip(_request(REMOTE_ADDR="192.0.2.10")), "192.0.2.10")
        self.assertEqual(axes_client_ip(_request(REMOTE_ADDR="2001:db8::1")), "2001:db8::1")
        # Den Zonen-Index nimmt inet nicht an.
        self.assertEqual(axes_client_ip(_request(REMOTE_ADDR="fe80::1%eth0")), "fe80::1")

    @override_settings(TRUSTED_PROXY=True)
    def test_trusted_proxy_rightmost_entry_is_used(self):
        request = _request(REMOTE_ADDR="10.0.0.2", HTTP_X_FORWARDED_FOR="6.6.6.6, 203.0.113.9")
        self.assertEqual(axes_client_ip(request), "203.0.113.9")

    @override_settings(TRUSTED_PROXY=True)
    def test_placeholder_and_garbage_become_none(self):
        self.assertIsNone(axes_client_ip(_request()))
        self.assertIsNone(axes_client_ip(_request(REMOTE_ADDR="10.0.0.2", HTTP_X_FORWARDED_FOR="unknown")))
        self.assertIsNone(axes_client_ip(_request(REMOTE_ADDR="10.0.0.2", HTTP_X_FORWARDED_FOR="x" * 200)))

    def test_rate_limit_keys_keep_the_placeholder(self):
        # Nur axes bekommt None; Rate-Limits zählen Anfragen ohne Adresse
        # weiter gemeinsam unter „unknown“.
        request = _request()
        self.assertEqual(client_ip_from_request(request), "unknown")
        self.assertEqual(rate_limit_ip(request), "unknown")
        self.assertIsNone(axes_client_ip(request))


class LoginWithoutAddressTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ohne-adresse", password=PASSWORD)

    def fail_five_times_without_address(self):
        for _ in range(5):  # AXES_FAILURE_LIMIT
            self.assertIsNone(authenticate(request=_request(), username="ohne-adresse", password="falsch"))

    def test_force_login_without_remote_addr_logs_null_ip(self):
        Client().force_login(self.user)
        self.assertIsNone(AccessLog.objects.get(username="ohne-adresse").ip_address)

    def test_failed_logins_without_address_still_lock_out(self):
        self.fail_five_times_without_address()
        self.assertEqual(
            list(AccessAttempt.objects.filter(username="ohne-adresse").values_list("ip_address", flat=True)),
            [None],
        )
        self.assertIsNone(authenticate(request=_request(), username="ohne-adresse", password=PASSWORD))

    def test_lockout_without_address_does_not_block_a_real_address(self):
        # Gesperrt wird je Benutzername und Adresse (AXES_LOCKOUT_PARAMETERS);
        # Anfragen ohne Adresse bilden einen eigenen Topf.
        self.fail_five_times_without_address()
        request = _request(REMOTE_ADDR="192.0.2.10")
        self.assertEqual(authenticate(request=request, username="ohne-adresse", password=PASSWORD), self.user)
