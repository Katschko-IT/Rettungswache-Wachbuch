"""Regressionstests zu den Befunden aus docs/REVIEW-2026-10-24.md."""
import json
import re
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import ApiToken, Membership, NewsAcknowledgement, NewsPost, Station, TotpDevice
from core.news import acknowledgement_status
from core.terminal import COOKIE_NAME, hash_secret, set_station_code, verify_code
from core.terminal_models import StationTerminal

PASSWORD = "x-test-pass-123"
CODE = "4827"


@override_settings(MFA_ENABLED=True, MFA_REQUIRED=True)
class MfaRequiredEnforcementTests(TestCase):
    """S1: MFA_REQUIRED muss nach dem Passwort-Login wirklich greifen."""

    def setUp(self):
        self.station = Station.objects.create(name="RW", slug="rw")
        self.user = User.objects.create_user(username="nomfa", password=PASSWORD)
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.MEMBER)
        self.client.post(reverse("login"), {"username": "nomfa", "password": PASSWORD})

    def test_content_pages_redirect_to_mfa_setup(self):
        response = self.client.get(reverse("handover_list"))
        self.assertRedirects(response, reverse("mfa_setup"), fetch_redirect_response=False)

    def test_api_token_cannot_be_created_without_mfa(self):
        response = self.client.post(reverse("api_tokens_manage"), {"action": "create", "label": "x"})
        self.assertNotEqual(response.status_code, 200)
        self.assertFalse(ApiToken.objects.filter(user=self.user).exists())

    def test_mfa_setup_and_logout_stay_reachable(self):
        self.assertEqual(self.client.get(reverse("mfa_setup")).status_code, 200)
        response = self.client.post(reverse("logout"))
        self.assertIn(response.status_code, (200, 302))

    def test_confirmed_mfa_user_is_not_blocked(self):
        TotpDevice.objects.create(user=self.user, secret="x", is_confirmed=True)
        self.assertEqual(self.client.get(reverse("handover_list")).status_code, 200)

    @override_settings(MFA_REQUIRED=False)
    def test_optional_mfa_does_not_block(self):
        self.assertEqual(self.client.get(reverse("handover_list")).status_code, 200)


@override_settings(TERMINAL_ENABLED=True)
class TerminalServiceAccountTests(TestCase):
    """S2–S4: Grenzen des Dienstkontos und der Kopplung."""

    def setUp(self):
        self.station = Station.objects.create(name="RW", slug="rw")
        self.admin = User.objects.create_user(username="admin1", password=PASSWORD)
        Membership.objects.create(user=self.admin, station=self.station, role=Membership.Role.ADMIN)
        self.member = User.objects.create_user(username="m1", password=PASSWORD)
        self.member_ms = Membership.objects.create(
            user=self.member, station=self.station, role=Membership.Role.MEMBER
        )
        self.raw = "terminal-secret"
        self.terminal = StationTerminal.objects.create(
            station=self.station, label="T", token_hash=hash_secret(self.raw), created_by=self.admin
        )
        set_station_code(self.station, CODE, set_by=self.admin)

    def _unlock_terminal(self):
        self.client.cookies[COOKIE_NAME] = self.raw
        response = self.client.post(reverse("terminal_home"), {"code": CODE})
        self.assertEqual(response.status_code, 302)

    def test_service_account_is_not_news_audience(self):
        post = NewsPost.objects.create(station=self.station, title="x", body="y", created_by=self.admin)
        NewsAcknowledgement.objects.create(post=post, user=self.admin)
        NewsAcknowledgement.objects.create(post=post, user=self.member)
        self.assertTrue(acknowledgement_status(post)["complete"])

    def test_service_account_cannot_acknowledge_news(self):
        post = NewsPost.objects.create(station=self.station, title="x", body="y", created_by=self.admin)
        self._unlock_terminal()
        response = self.client.post(reverse("news_detail", args=[post.pk]), {"action": "acknowledge"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            NewsAcknowledgement.objects.filter(post=post, user__username__startswith="wachenterminal-").exists()
        )
        post.refresh_from_db()
        self.assertIsNone(post.archived_at)

    def test_admin_cannot_pair_member_with_mfa(self):
        TotpDevice.objects.create(user=self.member, secret="x", is_confirmed=True)
        self.client.force_login(self.admin)
        self.client.post(reverse("terminal_admin"), {"action": "pair-member", "membership_id": self.member_ms.pk})
        self.assertNotIn("terminal_pair_link", self.client.session)

    @override_settings(MFA_ENABLED=True, MFA_REQUIRED=True)
    def test_pairing_exchange_respects_mfa_required(self):
        self.client.force_login(self.admin)
        TotpDevice.objects.create(user=self.admin, secret="x", is_confirmed=True)
        self.client.post(reverse("terminal_admin"), {"action": "pair-member", "membership_id": self.member_ms.pk})
        link = self.client.session.get("terminal_pair_link")
        if link:
            code = parse_qs(urlparse(link).query)["pair"][0]
            response = Client().post(
                "/api/v1/token/kopplung/", data=json.dumps({"code": code}), content_type="application/json"
            )
            self.assertEqual(response.status_code, 403)
        self.assertFalse(ApiToken.objects.filter(user=self.member).exists())

    def test_parallel_failures_are_all_counted(self):
        stale = [StationTerminal.objects.get(pk=self.terminal.pk) for _ in range(10)]
        for terminal in stale:
            verify_code(terminal, "0000")
        self.terminal.refresh_from_db()
        self.assertEqual(self.terminal.failed_attempts, 10)
        self.assertIsNotNone(self.terminal.locked_until)
        self.assertGreater(self.terminal.locked_until, timezone.now() - timedelta(seconds=1))


def _make_token(user, raw):
    from core.api.views import DEFAULT_MOBILE_SCOPES, hash_api_token

    ApiToken.objects.create(
        user=user,
        label="t",
        token_prefix=raw[:11],
        token_hash=hash_api_token(raw),
        scopes=list(DEFAULT_MOBILE_SCOPES),
        expires_at=timezone.now() + timedelta(days=1),
    )
    return {"HTTP_AUTHORIZATION": f"Token {raw}"}


class ClientIpAndRateLimitTests(TestCase):
    """S5: Client-IP hinter dem Proxy und Rate-Limit pro Nutzer."""

    def setUp(self):
        self.station = Station.objects.create(name="RW", slug="rw")
        self.user = User.objects.create_user(username="a", password=PASSWORD)
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.ADMIN)
        self.auth = _make_token(self.user, "wb_review_token_aaaaaaaaaaaaaaaaaa")

    @override_settings(TRUSTED_PROXY=True)
    def test_proxy_appended_entry_wins_over_spoofed_header(self):
        from django.test import RequestFactory

        from core.middleware import client_ip_from_request

        request = RequestFactory().get(
            "/", HTTP_X_FORWARDED_FOR="6.6.6.6, 203.0.113.9", REMOTE_ADDR="10.0.0.2"
        )
        self.assertEqual(client_ip_from_request(request), "203.0.113.9")

    @override_settings(TRUSTED_PROXY=False)
    def test_forwarded_header_ignored_without_trusted_proxy(self):
        from django.test import RequestFactory

        from core.middleware import client_ip_from_request

        request = RequestFactory().get("/", HTTP_X_FORWARDED_FOR="6.6.6.6", REMOTE_ADDR="10.0.0.2")
        self.assertEqual(client_ip_from_request(request), "10.0.0.2")

    def test_authenticated_users_have_separate_buckets(self):
        other = User.objects.create_user(username="b", password=PASSWORD)
        Membership.objects.create(user=other, station=self.station, role=Membership.Role.MEMBER)
        other_auth = _make_token(other, "wb_review_token_bbbbbbbbbbbbbbbbbb")
        for _ in range(60):
            self.client.get("/api/v1/me/", **self.auth)
        self.assertEqual(self.client.get("/api/v1/me/", **other_auth).status_code, 200)

    def test_rate_limited_response_has_retry_after(self):
        for _ in range(60):
            self.client.get("/api/v1/me/", **self.auth)
        response = self.client.get("/api/v1/me/", **self.auth)
        self.assertEqual(response.status_code, 429)
        self.assertTrue(response.get("Retry-After", "").isdigit())


class WebWachalltagTests(TestCase):
    """S6, S7, S9: Web-Abläufe verhalten sich wie die API."""

    def setUp(self):
        self.station = Station.objects.create(name="RW", slug="rw", checklists_enabled=True)
        self.user = User.objects.create_user(username="lead", password=PASSWORD)
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.ADMIN)
        self.client.force_login(self.user)

    def test_web_completion_advances_schedule(self):
        from core.models import Checklist
        from core.wachalltag_models import ChecklistSchedule

        checklist = Checklist.objects.create(station=self.station, title="c")
        due = timezone.now() - timedelta(hours=1)
        schedule = ChecklistSchedule.objects.create(
            checklist=checklist, station=self.station, interval="daily", due_next=due
        )
        self.client.post(reverse("checklist_complete", args=[checklist.pk]))
        schedule.refresh_from_db()
        self.assertGreater(schedule.due_next, timezone.now())

    def test_web_attachment_count_is_limited(self):
        import io

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        from core.api.wachalltag import MAX_ATTACHMENTS_PER_DEFECT
        from core.wachalltag_models import Defect, DefectAttachment

        defect = Defect.objects.create(station=self.station, title="d", created_by=self.user)
        buffer = io.BytesIO()
        Image.new("RGB", (10, 10)).save(buffer, "PNG")
        for index in range(MAX_ATTACHMENTS_PER_DEFECT + 2):
            upload = SimpleUploadedFile(f"a{index}.png", buffer.getvalue(), content_type="image/png")
            self.client.post(reverse("defect_detail_web", args=[defect.pk]), {"action": "upload", "attachment": upload})
        self.assertEqual(DefectAttachment.objects.filter(defect=defect).count(), MAX_ATTACHMENTS_PER_DEFECT)

    def test_impossible_dates_are_form_errors_not_500(self):
        from core.models import Checklist

        client = Client(raise_request_exception=False)
        client.force_login(self.user)
        response = client.post(reverse("defect_create_web"), {"title": "x", "due_at": "2026-02-30T10:00"})
        self.assertLess(response.status_code, 500)
        checklist = Checklist.objects.create(station=self.station, title="c")
        response = client.post(
            reverse("checklist_schedules_web"),
            {"checklist_id": checklist.pk, "interval": "daily", "due_next": "2026-02-30T10:00"},
        )
        self.assertLess(response.status_code, 500)


class ApiJsonBodyTests(TestCase):
    """S8: JSON-Körper, die kein Objekt sind, ergeben 400 statt 500."""

    def setUp(self):
        self.station = Station.objects.create(
            name="RW", slug="rw", checklists_enabled=True, calendar_enabled=True,
            coffee_enabled=True, pinboard_enabled=True,
        )
        self.user = User.objects.create_user(username="lead", password=PASSWORD)
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.ADMIN)
        self.auth = _make_token(self.user, "wb_review_token_cccccccccccccccccc")

    def test_non_object_bodies(self):
        from core.models import Checklist

        client = Client(raise_request_exception=False)
        checklist = Checklist.objects.create(station=self.station, title="c")
        cases = [
            ("/api/v1/token/", "[]", {}),
            ("/api/v1/handovers/", "[1]", self.auth),
            ("/api/v1/kalender/", "[1]", self.auth),
            ("/api/v1/kaffeekasse/", '"x"', self.auth),
            ("/api/v1/pinnwand/", "[1]", self.auth),
            (f"/api/v1/checklisten/{checklist.pk}/erledigt/", "[1]", self.auth),
        ]
        for url, body, extra in cases:
            with self.subTest(url=url):
                response = client.post(url, data=body, content_type="application/json", **extra)
                self.assertLess(response.status_code, 500)


@override_settings(TERMINAL_ENABLED=True)
class TerminalAuditTests(TestCase):
    """S10: Freitext-Bezeichnungen landen nicht im Audit."""

    def test_terminal_label_not_in_audit(self):
        from core.models import AuditEvent

        station = Station.objects.create(name="RW", slug="rw")
        admin = User.objects.create_user(username="admin1", password=PASSWORD)
        Membership.objects.create(user=admin, station=station, role=Membership.Role.ADMIN)
        self.client.force_login(admin)
        self.client.post(reverse("terminal_admin"), {"action": "create", "label": "Flur bei Herrn Müller"})
        for event in AuditEvent.objects.filter(action="terminal.created"):
            self.assertNotIn("Müller", json.dumps(event.metadata, ensure_ascii=False))


class ApiListContractTests(TestCase):
    """S11–S13: Mängelliste, Kalender und Kaffeekasse liefern, was der Client braucht."""

    def setUp(self):
        self.station = Station.objects.create(name="RW", slug="rw", calendar_enabled=True, coffee_enabled=True)
        self.user = User.objects.create_user(username="lead", password=PASSWORD)
        Membership.objects.create(user=self.user, station=self.station, role=Membership.Role.ADMIN)
        self.member = User.objects.create_user(username="m", password=PASSWORD)
        Membership.objects.create(user=self.member, station=self.station, role=Membership.Role.MEMBER)
        self.auth = _make_token(self.user, "wb_review_token_dddddddddddddddddd")
        self.member_auth = _make_token(self.member, "wb_review_token_eeeeeeeeeeeeeeeeee")

    def _defect(self, title, status, priority):
        from core.wachalltag_models import Defect

        return Defect.objects.create(
            station=self.station, title=title, status=status, priority=priority, created_by=self.user
        )

    def test_defects_sorted_by_workflow_and_priority(self):
        self._defect("done", "done", "urgent")
        self._defect("open-normal", "open", "normal")
        self._defect("waiting", "waiting", "urgent")
        self._defect("open-important", "open", "important")
        self._defect("progress", "in_progress", "normal")
        self._defect("open-urgent", "open", "urgent")
        data = self.client.get("/api/v1/defects/", **self.auth).json()
        titles = [item["title"] for item in data["results"]]
        self.assertEqual(
            titles, ["open-urgent", "open-important", "open-normal", "progress", "waiting", "done"]
        )

    def test_many_done_defects_do_not_hide_open_ones(self):
        from core.wachalltag_models import Defect

        Defect.objects.bulk_create([
            Defect(station=self.station, title=f"d{i}", status="done", priority="normal", created_by=self.user)
            for i in range(250)
        ])
        self._defect("offen", "open", "normal")
        data = self.client.get("/api/v1/defects/", **self.auth).json()
        self.assertEqual(data["results"][0]["title"], "offen")
        self.assertEqual(data["count"], 251)
        self.assertIsNotNone(data["next"])

    def test_defects_pagination_and_active_filter(self):
        for index in range(5):
            self._defect(f"o{index}", "open", "normal")
        self._defect("fertig", "done", "normal")
        first = self.client.get("/api/v1/defects/?limit=2&active=1", **self.auth).json()
        self.assertEqual(first["count"], 5)
        self.assertEqual(len(first["results"]), 2)
        self.assertIsNone(first["previous"])
        second = self.client.get(first["next"], **self.auth).json()
        self.assertEqual(len(second["results"]), 2)
        self.assertIsNotNone(second["previous"])
        last = self.client.get(second["next"], **self.auth).json()
        self.assertEqual(len(last["results"]), 1)
        self.assertIsNone(last["next"])
        titles = {i["title"] for page in (first, second, last) for i in page["results"]}
        self.assertNotIn("fertig", titles)

    def test_calendar_includes_running_events_and_description(self):
        from core.models import CalendarEvent

        now = timezone.now()
        CalendarEvent.objects.create(
            station=self.station, title="läuft", description="Treffpunkt Halle",
            starts_at=now - timedelta(hours=1), ends_at=now + timedelta(hours=1), created_by=self.user,
        )
        CalendarEvent.objects.create(
            station=self.station, title="vorbei", starts_at=now - timedelta(hours=3),
            ends_at=now - timedelta(hours=2), created_by=self.user,
        )
        results = self.client.get("/api/v1/kalender/", **self.auth).json()["results"]
        self.assertEqual([item["title"] for item in results], ["läuft"])
        self.assertEqual(results[0]["description"], "Treffpunkt Halle")

    def test_coffee_reports_scope(self):
        self.assertEqual(self.client.get("/api/v1/kaffeekasse/", **self.auth).json()["scope"], "station")
        self.assertEqual(self.client.get("/api/v1/kaffeekasse/", **self.member_auth).json()["scope"], "own")


class NoMembershipErrorCodeTests(TestCase):
    """Entzogene Mitgliedschaft hat einen eigenen Fehlercode für Clients."""

    def test_token_without_membership_reports_specific_code(self):
        station = Station.objects.create(name="RW", slug="rw")
        user = User.objects.create_user(username="ex", password=PASSWORD)
        membership = Membership.objects.create(user=user, station=station, role=Membership.Role.MEMBER)
        auth = _make_token(user, "wb_review_token_ffffffffffffffffff")
        membership.is_active = False
        membership.save(update_fields=["is_active"])
        response = self.client.get("/api/v1/me/", **auth)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "no_active_membership")


class ActivationFormRefererPolicyTests(TestCase):
    """E2E-Befund: no-referrer lässt Browser Origin: null senden → CSRF 403.

    Formularseiten mit Einmal-Token brauchen same-origin: kein Referer an
    fremde Seiten, aber ein gültiger Origin für das eigene Formular.
    """

    def setUp(self):
        from core.setup_wizard import create_activation

        self.station = Station.objects.create(name="RW", slug="rw")
        self.admin = User.objects.create_user(username="admin1", password=PASSWORD)
        Membership.objects.create(user=self.admin, station=self.station, role=Membership.Role.ADMIN)
        self.employee = User.objects.create_user("neu1", password=None)
        self.employee.set_unusable_password()
        self.employee.is_active = False
        self.employee.save()
        Membership.objects.create(user=self.employee, station=self.station, role=Membership.Role.MEMBER)
        _, self.raw = create_activation(user=self.employee, station=self.station, created_by=self.admin)

    def test_activation_form_sends_same_origin_policy(self):
        response = self.client.get(reverse("activate_account", kwargs={"token": self.raw}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Referrer-Policy"], "same-origin")

    @override_settings(CSRF_TRUSTED_ORIGINS=["https://wache.example"], ALLOWED_HOSTS=["wache.example"])
    def test_browser_post_with_real_origin_activates(self):
        client = Client(enforce_csrf_checks=True)
        url = reverse("activate_account", kwargs={"token": self.raw})
        page = client.get(url, secure=True, HTTP_HOST="wache.example")
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.content.decode()).group(1)
        response = client.post(
            url,
            {"password1": "Lang-und-Sicher-2026!x", "password2": "Lang-und-Sicher-2026!x", "csrfmiddlewaretoken": token},
            secure=True,
            HTTP_HOST="wache.example",
            HTTP_ORIGIN="https://wache.example",
        )
        self.assertEqual(response.status_code, 302)
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.is_active)

    def test_invite_result_page_sends_same_origin_policy(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("team_invite_create"), {"username": "kim", "role": Membership.Role.MEMBER}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Referrer-Policy"], "same-origin")


class RateLimitRaceTests(TestCase):
    """E2E-Befund: zwei gleichzeitige erste Anfragen im Zeitfenster → IntegrityError/500."""

    def test_concurrent_first_insert_is_counted_not_raised(self):
        from unittest import mock

        from django.db.models.query import QuerySet

        from core.models import RateLimit
        from core.rate_limit import consume

        # Die parallele Anfrage hat ihre Zeile schon angelegt; unser erstes
        # Lesen lief davor und fand nichts. Das Anlegen trifft dann den echten
        # Unique-Index.
        consume("race", "key", limit=5, window_seconds=60)
        real_get = QuerySet.get
        calls = {"n": 0}

        def first_get_misses(qs, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RateLimit.DoesNotExist
            return real_get(qs, *args, **kwargs)

        with mock.patch.object(QuerySet, "get", autospec=True, side_effect=first_get_misses):
            allowed = consume("race", "key", limit=5, window_seconds=60)
        self.assertTrue(allowed)
        self.assertEqual(RateLimit.objects.get(bucket="race").count, 2)


class TokenLastUsedThrottleTests(TestCase):
    """Optimierung: „zuletzt genutzt“ höchstens einmal pro Minute schreiben."""

    def setUp(self):
        station = Station.objects.create(name="RW", slug="rw")
        self.user = User.objects.create_user(username="u", password=PASSWORD)
        Membership.objects.create(user=self.user, station=station, role=Membership.Role.MEMBER)
        self.auth = _make_token(self.user, "wb_review_token_gggggggggggggggggg")
        self.token = ApiToken.objects.get(user=self.user)

    def _token_writes(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(self.client.get("/api/v1/me/", **self.auth).status_code, 200)
        return [q for q in ctx.captured_queries if q["sql"].startswith("UPDATE") and "core_apitoken" in q["sql"]]

    def test_first_use_is_recorded(self):
        self.assertEqual(len(self._token_writes()), 1)
        self.token.refresh_from_db()
        self.assertIsNotNone(self.token.last_used_at)

    def test_repeated_use_within_a_minute_does_not_write(self):
        self._token_writes()
        self.assertEqual(self._token_writes(), [])

    def test_use_after_a_minute_writes_again(self):
        self._token_writes()
        ApiToken.objects.filter(pk=self.token.pk).update(last_used_at=timezone.now() - timedelta(minutes=2))
        self.assertEqual(len(self._token_writes()), 1)
