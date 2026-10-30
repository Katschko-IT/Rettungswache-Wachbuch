"""Wachen-Display und App-Zugang: Thread-Grenzen, Rollen, Demo und Rückweg."""
from __future__ import annotations

import hashlib
import itertools
import json
import re
import secrets
import time
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.signals import request_finished
from django.db import close_old_connections
from django.test import TestCase, override_settings
from django.urls import reverse

from core import display_views
from core.display_models import DisplayToken
from core.models import ApiToken, Membership, PinboardNote, Station

DEMO = {"username": "Demo", "password": "Demo"}
SANDBOX_ON = dict(DEMO_MODE=True, DEMO_SANDBOX=True, MFA_REQUIRED=False)


def close_stream(response):
    """Stream schließen wie der Test-Client selbst (ohne close_old_connections).

    ``response.close()`` sendet ``request_finished``; dort hängt
    ``close_old_connections`` und schlösse mitten in der Testtransaktion die
    echte PostgreSQL-Verbindung. SQLite ignoriert ``close()`` auf der
    In-Memory-Testdatenbank, deshalb fiel das nur gegen PostgreSQL auf.
    """
    request_finished.disconnect(close_old_connections)
    try:
        response.close()
    finally:
        request_finished.connect(close_old_connections)


class StreamSlotMixin:
    """Jeder Test beginnt ohne offene Streams und schließt seine eigenen."""

    def setUp(self):
        super().setUp()
        cache.clear()
        display_views._open_streams.clear()
        self.addCleanup(display_views._open_streams.clear)

    def stream(self, client=None):
        response = (client or self.client).get(reverse("display_stream"))
        self.addCleanup(close_stream, response)
        return response


def _station(slug="wache-sicher"):
    return Station.objects.create(name=f"Wache {slug}", slug=slug, display_enabled=True, pinboard_enabled=True)


def _member(station, username, role=Membership.Role.MEMBER):
    user = User.objects.create_user(username, password="ein-langes-Passwort-42")
    Membership.objects.create(user=user, station=station, role=role)
    return user


def _display_token(station, user):
    raw = secrets.token_urlsafe(32)
    DisplayToken.objects.create(
        station=station,
        label="Halle",
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        created_by=user,
    )
    return raw


@override_settings(**SANDBOX_ON)
class DemoDisplayStreamTests(StreamSlotMixin, TestCase):
    def setUp(self):
        super().setUp()
        response = self.client.post(reverse("login"), DEMO)
        self.assertEqual(response.status_code, 302)

    def test_demo_visit_gets_no_thread_holding_stream(self):
        for _ in range(10):
            response = self.stream()
            self.assertEqual(response.status_code, 204)
            self.assertFalse(response.streaming)
        self.assertEqual(display_views._open_streams, {})

    def test_demo_display_polls_instead(self):
        page = self.client.get(reverse("display_home"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'data-stream-url="none"')
        self.assertEqual(self.client.get(reverse("display_data")).status_code, 200)

    def test_demo_auditor_reads_no_display_texts(self):
        response = self.client.post(reverse("demo_switch_role"), {"role": "audit"})
        self.assertEqual(response.status_code, 302)
        for name in ("display_home", "display_data", "display_stream"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)


class DisplayStreamCapTests(StreamSlotMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.station = _station()
        self.user = _member(self.station, "nina", Membership.Role.SHIFT_LEAD)
        self.client.force_login(self.user)

    def test_session_viewer_holds_one_stream_at_a_time(self):
        first = self.stream()
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.streaming)
        for _ in range(5):
            self.assertEqual(self.stream().status_code, 204)
        close_stream(first)
        self.assertEqual(self.stream().status_code, 200)

    def test_closed_stream_keeps_the_database_usable(self):
        # Gegen PostgreSQL schloss ein bloßes response.close() die
        # Testverbindung („the connection is closed“).
        close_stream(self.stream())
        self.assertTrue(Station.objects.filter(pk=self.station.pk).exists())

    @override_settings(DISPLAY_STREAM_MAX_PER_PROCESS=2)
    def test_streams_never_take_more_than_the_process_share(self):
        clients = []
        for index in range(4):
            client = self.client_class()
            client.force_login(_member(self.station, f"crew-{index}"))
            clients.append(client)
        statuses = [self.stream(client).status_code for client in clients]
        self.assertEqual(statuses, [200, 200, 204, 204])

    def test_default_share_is_half_of_the_gunicorn_threads(self):
        with mock.patch.dict("os.environ", {"GUNICORN_THREADS": "4"}):
            self.assertEqual(display_views._stream_limit_per_process(), 2)
        with mock.patch.dict("os.environ", {"GUNICORN_THREADS": "1"}):
            self.assertEqual(display_views._stream_limit_per_process(), 1)

    def test_finished_stream_frees_its_slot(self):
        response = self.stream()
        clock = itertools.count(int(time.time()), 7)
        with mock.patch("time.time", side_effect=lambda: next(clock)), mock.patch("time.sleep"):
            list(response.streaming_content)
        self.assertEqual(display_views._open_streams, {})
        self.assertEqual(self.stream().status_code, 200)

    def test_leaked_slot_expires_after_the_stream_lifetime(self):
        self.assertEqual(self.stream().status_code, 200)
        later = time.monotonic() + display_views.STREAM_MAX_SECONDS + 61
        with mock.patch("core.display_views.time.monotonic", return_value=later):
            self.assertIsNotNone(display_views._acquire_stream_slot(f"user:{self.user.pk}"))

    def test_wall_display_token_has_its_own_slot(self):
        self.assertEqual(self.stream().status_code, 200)
        tv = self.client_class()
        tv.cookies[display_views.COOKIE_NAME] = _display_token(self.station, self.user)
        self.assertEqual(self.stream(tv).status_code, 200)


class DisplayAuditorTests(StreamSlotMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.station = _station()
        self.admin = _member(self.station, "admin", Membership.Role.ADMIN)
        self.auditor = _member(self.station, "pruefer", Membership.Role.AUDITOR)
        PinboardNote.objects.create(
            station=self.station, title="GEHEIM-PIN", body="x", is_pinned=True, author=self.admin,
        )

    def test_auditor_session_gets_no_display_payload(self):
        self.client.force_login(self.auditor)
        for name in ("display_home", "display_data", "display_stream"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 403, name)
            self.assertNotIn(b"GEHEIM-PIN", response.content)

    def test_content_roles_keep_the_display(self):
        self.client.force_login(self.admin)
        data = self.client.get(reverse("display_data"))
        self.assertEqual(data.status_code, 200)
        self.assertIn("GEHEIM-PIN", data.content.decode())

    def test_wall_display_cookie_still_works_on_an_auditor_device(self):
        self.client.force_login(self.auditor)
        self.client.cookies[display_views.COOKIE_NAME] = _display_token(self.station, self.admin)
        self.assertEqual(self.client.get(reverse("display_data")).status_code, 200)

    def test_running_stream_ends_when_role_becomes_auditor(self):
        self.client.force_login(self.admin)
        response = self.stream()
        iterator = iter(response.streaming_content)
        self.assertIn(b"event: update", next(iterator))
        self.assertIn(b"retry:", next(iterator))
        Membership.objects.filter(user=self.admin).update(role=Membership.Role.AUDITOR)
        clock = itertools.count(int(time.time()) + 60, 31)
        with mock.patch("time.time", side_effect=lambda: next(clock)), mock.patch("time.sleep"):
            rest = b"".join(iterator)
        self.assertIn(b"event: revoked", rest)
        self.assertNotIn(b"GEHEIM-PIN", rest)


class DisplayWayBackTests(StreamSlotMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.station = _station()
        self.user = _member(self.station, "nina")

    def test_session_view_offers_a_way_back(self):
        self.client.force_login(self.user)
        page = self.client.get(reverse("display_home"))
        self.assertContains(page, f'class="display-exit-link" href="{reverse("dashboard")}"')
        self.assertNotContains(page, 'data-stream-url="none"')

    def test_wall_display_shows_no_app_link(self):
        self.client.cookies[display_views.COOKIE_NAME] = _display_token(self.station, self.user)
        page = self.client.get(reverse("display_home"))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "display-exit-link")


class DisplayPhoneLayoutTests(TestCase):
    """Schmale Bildschirme: nichts darf die Spalte über die Breite aufweiten."""

    css = (Path(__file__).resolve().parent / "static" / "core" / "display.css").read_text(encoding="utf-8")

    def _narrow_blocks(self):
        return re.findall(r"@media \(max-width: 900px\) \{(.*?)\n\}", self.css, flags=re.S)

    def test_single_column_may_shrink_below_its_content(self):
        grid_rules = [block for block in self._narrow_blocks() if ".display-grid" in block]
        self.assertTrue(grid_rules)
        self.assertIn("grid-template-columns: minmax(0, 1fr);", grid_rules[0])

    def test_ticker_wraps_after_its_base_rule(self):
        base = self.css.index(".display-ticker {")
        narrow = [m.start() for m in re.finditer(r"@media \(max-width: 900px\) \{\s*\.display-ticker", self.css)]
        self.assertTrue(narrow, "Ticker braucht eine Regel für schmale Bildschirme")
        self.assertGreater(narrow[0], base, "sonst überschreibt die Grundregel den Umbruch")
        self.assertIn("white-space: normal;", self.css[narrow[0]:])

    def test_esc_hint_is_hidden_without_keyboard(self):
        self.assertRegex(self.css, r"@media \(hover: none\), \(pointer: coarse\) \{\s*\.display-hint \{ display: none; \}")


@override_settings(**SANDBOX_ON)
class DemoAppTokenTests(TestCase):
    password = "ein-langes-Passwort-42"

    def setUp(self):
        cache.clear()
        response = self.client.post(reverse("login"), DEMO)
        self.assertEqual(response.status_code, 302)
        self.demo_user = User.objects.get(pk=self.client.session["_auth_user_id"])

    def _create_member(self):
        response = self.client.post(reverse("team_user_create"), {
            "username": "neu-im-team", "first_name": "Neu", "password1": self.password,
            "password2": self.password, "role": Membership.Role.MEMBER,
        })
        self.assertEqual(response.status_code, 302)
        return User.objects.get(username="neu-im-team")

    def test_member_created_in_the_demo_gets_no_app_token(self):
        self._create_member()
        response = self.client_class().post(
            reverse("api_v1_token"),
            data=json.dumps({"username": "neu-im-team", "password": self.password}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "forbidden")
        self.assertFalse(ApiToken.objects.exists())

    def test_existing_token_of_a_demo_account_is_refused(self):
        from core.api.views import generate_api_token

        raw, token_hash, prefix = generate_api_token()
        ApiToken.objects.create(
            user=self.demo_user, label="alt", token_prefix=prefix, token_hash=token_hash, scopes=["read:me"],
        )
        response = self.client_class().get(reverse("api_v1_me"), HTTP_AUTHORIZATION=f"Token {raw}")
        self.assertEqual(response.status_code, 403)

    @override_settings(TERMINAL_ENABLED=True)
    def test_pairing_code_of_a_demo_account_gives_no_token(self):
        from core.terminal import create_pairing

        code = create_pairing(Membership.objects.get(user=self._create_member()))
        response = self.client_class().post(
            reverse("api_v1_token_pairing"), data=json.dumps({"code": code}), content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ApiToken.objects.exists())


class RealStationAppTokenTests(TestCase):
    """Ohne Demo-Sandbox bleibt der Passwort-Tausch unverändert."""

    @override_settings(DEMO_SANDBOX=False, MFA_REQUIRED=False)
    def test_regular_account_still_gets_a_token(self):
        cache.clear()
        _member(_station("echt"), "echt")
        response = self.client.post(
            reverse("api_v1_token"),
            data=json.dumps({"username": "echt", "password": "ein-langes-Passwort-42"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
