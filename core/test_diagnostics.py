"""Abnahmetests fuer bereinigte Fehlerereignisse und Supportexport (H4).

Deckt Erfassung echter 5xx-Fehler, Feld-Allowlist, Leak-Test mit synthetischen
Geheimnissen/URLs/Stacktraces, Rekursionsfreiheit, Wachentrennung, globale
Ereignisse, Pagination, Export-Header und Aufbewahrungspolicy ab.
"""

from __future__ import annotations

import re
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import OperationalError
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import include, path, reverse
from django.utils import timezone

from core.access import CONTENT_ROLES, membership_required
from core.diagnostics import CORRELATION_ID_RE, ErrorEventMiddleware
from core.diagnostics_models import ErrorEvent
from core.models import Membership, Station

SYNTHETIC_SECRET = "SYNTHETIC-TOKEN-9f3a"
SYNTHETIC_QUERY = "?token=SYNTHETIC-TOKEN-9f3a&mail=secret@example.org"


def boom_view(request):
    raise RuntimeError(f"stacktrace intern {SYNTHETIC_SECRET} /pfad/{SYNTHETIC_QUERY}")


def boom_detail(request, pk):
    raise RuntimeError(f"detail failure {SYNTHETIC_SECRET}")


def boom_db(request):
    raise OperationalError(f"database unavailable {SYNTHETIC_SECRET}")


@membership_required(CONTENT_ROLES)
def boom_authorized(request):
    raise RuntimeError(f"authorized failure {SYNTHETIC_SECRET}")


urlpatterns = [
    path("boom/", boom_view, name="boom_view"),
    path("boom/<int:pk>/", boom_detail, name="boom_detail"),
    path("boom-db/", boom_db, name="boom_db"),
    path("boom-auth/", boom_authorized, name="boom_authorized"),
    path("", include("core.urls")),
]


class DiagnosticsBase(TestCase):
    def setUp(self):
        super().setUp()
        self.station_a = Station.objects.create(name="Wache Alpha", slug="wache-alpha")
        self.station_b = Station.objects.create(name="Wache Beta", slug="wache-beta")
        self.admin = self._user("admin_a", self.station_a, Membership.Role.ADMIN)
        self.member = self._user("member_a", self.station_a, Membership.Role.MEMBER)
        self.auditor = self._user("auditor_a", self.station_a, Membership.Role.AUDITOR)
        self.foreign_admin = self._user("admin_b", self.station_b, Membership.Role.ADMIN)

    def _user(self, username, station, role):
        user = User.objects.create_user(
            username=username,
            password="x" * 12,
            first_name="Mara",
            email=f"{username}@example.org",
        )
        Membership.objects.create(user=user, station=station, role=role)
        return user

    def _client(self, user=None):
        client = Client()
        if user is not None:
            client.force_login(user)
        return client

    def _event(self, **overrides):
        values = {
            "correlation_id": "corr-abc123",
            "route_name": "handover_list",
            "category": ErrorEvent.Category.SERVER,
            "http_status": 500,
            "app_version": "0.17.0",
            "station": self.station_a,
        }
        values.update(overrides)
        return ErrorEvent.objects.create(**values)

    def _boom(self, url="/boom/", **extra):
        client = Client(raise_request_exception=False)
        return client.get(url, **extra)


class ErrorCaptureTests(DiagnosticsBase):
    @override_settings(ROOT_URLCONF=__name__)
    def test_unhandled_500_is_recorded_with_safe_fields(self):
        response = self._boom(f"/boom/{SYNTHETIC_QUERY}", HTTP_X_CORRELATION_ID="corr-request-1")
        self.assertEqual(response.status_code, 500)
        event = ErrorEvent.objects.get()
        self.assertEqual(event.correlation_id, "corr-request-1")
        self.assertEqual(event.route_name, "boom_view")
        self.assertEqual(event.category, ErrorEvent.Category.SERVER)
        self.assertEqual(event.http_status, 500)
        self.assertEqual(event.app_version, "0.17.0")
        self.assertIsNone(event.station)
        self.assertEqual(ErrorEvent.objects.count(), 1)

    @override_settings(ROOT_URLCONF=__name__)
    def test_exception_text_urls_and_tokens_are_never_persisted(self):
        self._boom(f"/boom/{SYNTHETIC_QUERY}", HTTP_AUTHORIZATION=f"Bearer {SYNTHETIC_SECRET}")
        event = ErrorEvent.objects.get()
        serialized = " ".join(
            str(value)
            for value in ErrorEvent.objects.values(
                "correlation_id", "route_name", "category", "http_status", "app_version"
            ).get()
        )
        for secret in (
            SYNTHETIC_SECRET,
            "stacktrace",
            "secret@example.org",
            "token=",
            "Bearer",
            "/pfad/",
        ):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, serialized)
        self.assertNotIn("/", event.route_name)

    @override_settings(ROOT_URLCONF=__name__)
    def test_route_name_is_the_view_name_not_the_raw_url(self):
        self._boom("/boom/4711/")
        event = ErrorEvent.objects.get()
        self.assertEqual(event.route_name, "boom_detail")
        self.assertNotIn("4711", event.route_name)

    @override_settings(ROOT_URLCONF=__name__)
    def test_database_error_is_categorised_without_message(self):
        self._boom("/boom-db/")
        event = ErrorEvent.objects.get()
        self.assertEqual(event.category, ErrorEvent.Category.DATABASE)
        self.assertNotIn(SYNTHETIC_SECRET, event.route_name)

    @override_settings(ROOT_URLCONF=__name__)
    def test_station_is_recorded_only_when_membership_is_known(self):
        client = Client(raise_request_exception=False)
        client.force_login(self.member)
        response = client.get("/boom-auth/")
        self.assertEqual(response.status_code, 500)
        event = ErrorEvent.objects.get()
        self.assertEqual(event.station, self.station_a)

    @override_settings(ROOT_URLCONF=__name__)
    def test_404_is_not_recorded(self):
        response = self._boom("/gibt-es-nicht/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(ErrorEvent.objects.count(), 0)

    @override_settings(ROOT_URLCONF=__name__)
    def test_invalid_correlation_header_is_replaced_not_stored(self):
        self._boom("/boom/", HTTP_X_CORRELATION_ID="bad id with spaces")
        event = ErrorEvent.objects.get()
        self.assertNotEqual(event.correlation_id, "bad id with spaces")
        self.assertRegex(event.correlation_id, CORRELATION_ID_RE)

    @override_settings(ROOT_URLCONF=__name__)
    def test_recording_failure_does_not_change_response(self):
        with mock.patch.object(
            ErrorEvent.objects, "create", side_effect=RuntimeError("insert failed")
        ):
            response = self._boom("/boom/")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(ErrorEvent.objects.count(), 0)

    @override_settings(ROOT_URLCONF=__name__)
    def test_no_duplicate_event_for_one_failure(self):
        self._boom("/boom/")
        self.assertEqual(ErrorEvent.objects.count(), 1)

    def test_record_server_error_ignores_non_5xx(self):
        from core.diagnostics import record_server_error

        request = mock.Mock(spec=[])
        self.assertIsNone(record_server_error(request, status=404))

    def test_middleware_handles_5xx_response_without_exception(self):
        from django.http import HttpResponse

        def handler(request):
            return HttpResponse(status=503)

        middleware = ErrorEventMiddleware(handler)
        request = RequestFactory().get("/ausfall/")
        request.correlation_id = "corr-503"
        request.membership = None
        response = middleware(request)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(ErrorEvent.objects.get().http_status, 503)


class DiagnosticsModelTests(DiagnosticsBase):
    def test_status_outside_5xx_is_rejected(self):
        for status in (200, 404, 499, 600):
            with self.subTest(status=status):
                event = ErrorEvent(
                    correlation_id="corr-1",
                    route_name="landing",
                    category=ErrorEvent.Category.SERVER,
                    http_status=status,
                    app_version="0.17.0",
                )
                with self.assertRaises(ValidationError):
                    event.full_clean()

    def test_invalid_correlation_and_route_are_rejected(self):
        event = ErrorEvent(
            correlation_id="bad id",
            route_name="pfad/mit/slash",
            category=ErrorEvent.Category.SERVER,
            http_status=500,
            app_version="0.17.0",
        )
        with self.assertRaises(ValidationError) as caught:
            event.full_clean()
        self.assertIn("correlation_id", caught.exception.message_dict)
        self.assertIn("route_name", caught.exception.message_dict)


class DiagnosticsAccessTests(DiagnosticsBase):
    def test_anonymous_is_redirected(self):
        for name in ("error_events", "support_export"):
            with self.subTest(name=name):
                response = self._client().get(reverse(name))
                self.assertEqual(response.status_code, 302)

    def test_member_and_auditor_are_forbidden(self):
        for user in (self.member, self.auditor):
            for name in ("error_events", "support_export"):
                with self.subTest(user=user.username, name=name):
                    self.assertEqual(self._client(user).get(reverse(name)).status_code, 403)

    def test_admin_sees_only_own_station_events(self):
        own = self._event(correlation_id="corr-own")
        self._event(correlation_id="corr-foreign", station=self.station_b)
        self._event(correlation_id="corr-global", station=None)
        response = self._client(self.admin).get(reverse("error_events"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, own.correlation_id)
        self.assertNotContains(response, "corr-foreign")
        self.assertNotContains(response, "corr-global")

    def test_correlation_id_is_not_a_permission(self):
        self._event(correlation_id="corr-foreign", station=self.station_b)
        self._event(correlation_id="corr-global", station=None)
        for correlation in ("corr-foreign", "corr-global"):
            with self.subTest(correlation=correlation):
                response = self._client(self.admin).get(
                    reverse("error_events"), {"korrelation": correlation}
                )
                self.assertEqual(response.status_code, 200)
                # Die Eingabe wird im Filterfeld gespiegelt; entscheidend ist,
                # dass keine fremde Zeile geliefert wird.
                self.assertEqual(response.context["page_obj"].object_list.count(), 0)

    def test_invalid_correlation_filter_is_ignored(self):
        own = self._event(correlation_id="corr-own")
        response = self._client(self.admin).get(
            reverse("error_events"), {"korrelation": "bad id /../"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, own.correlation_id)
        self.assertFalse(response.context["correlation"])

    def test_pagination_limits_to_twenty_five(self):
        for index in range(30):
            self._event(correlation_id=f"corr-{index:02d}")
        client = self._client(self.admin)
        page_one = client.get(reverse("error_events"))
        page_two = client.get(reverse("error_events"), {"seite": 2})
        self.assertEqual(len(page_one.context["page_obj"].object_list), 25)
        self.assertEqual(len(page_two.context["page_obj"].object_list), 5)
        self.assertContains(page_one, "Seite 1 von 2")
        self.assertContains(page_two, "Seite 2 von 2")

    def test_post_is_not_allowed(self):
        self.assertEqual(self._client(self.admin).post(reverse("support_export")).status_code, 405)
        self.assertEqual(self._client(self.admin).post(reverse("error_events")).status_code, 405)

    def test_system_status_links_to_diagnostics_for_admin(self):
        response = self._client(self.admin).get(reverse("system_status"))
        self.assertContains(response, reverse("error_events"))
        self.assertContains(response, reverse("support_export"))


class SupportExportTests(DiagnosticsBase):
    def test_export_headers_and_safe_filename(self):
        self._event()
        response = self._client(self.admin).get(reverse("support_export"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/plain"))
        self.assertRegex(
            response["Content-Disposition"],
            r'^attachment; filename="wachbuch-support-\d{8}-\d{6}\.txt"$',
        )
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_export_uses_allowlist_and_no_member_or_content_data(self):
        article = self._event(correlation_id="corr-export")
        response = self._client(self.admin).get(reverse("support_export"))
        text = response.content.decode()
        self.assertIn("corr-export", text)
        self.assertIn("handover_list", text)
        self.assertIn("0.17.0", text)
        self.assertIn("Server", text)
        for forbidden in (
            self.member.username,
            self.member.email,
            "Mara",
            SYNTHETIC_SECRET,
            "Traceback",
            "RuntimeError",
            "?token=",
            "http://",
            "https://",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)
        self.assertNotIn("Wache Beta", text)

    def test_export_excludes_foreign_and_global_events(self):
        self._event(correlation_id="corr-own")
        self._event(correlation_id="corr-foreign", station=self.station_b)
        self._event(correlation_id="corr-global", station=None)
        text = self._client(self.admin).get(reverse("support_export")).content.decode()
        self.assertIn("corr-own", text)
        self.assertNotIn("corr-foreign", text)
        self.assertNotIn("corr-global", text)

    @override_settings(ERROR_EVENT_EXPORT_LIMIT=5)
    def test_export_limit_is_enforced(self):
        for index in range(8):
            self._event(correlation_id=f"corr-limit-{index}")
        text = self._client(self.admin).get(reverse("support_export")).content.decode()
        self.assertEqual(sum(text.count(f"corr-limit-{index}") for index in range(8)), 5)

    @override_settings(ERROR_EVENT_RETENTION_DAYS=7)
    def test_export_respects_retention_window(self):
        old = self._event(correlation_id="corr-old")
        ErrorEvent.objects.filter(pk=old.pk).update(occurred_at=timezone.now() - timedelta(days=30))
        self._event(correlation_id="corr-new")
        text = self._client(self.admin).get(reverse("support_export")).content.decode()
        self.assertNotIn("corr-old", text)
        self.assertIn("corr-new", text)


class ErrorRetentionCommandTests(DiagnosticsBase):
    def test_command_deletes_only_events_older_than_policy(self):
        old = self._event(correlation_id="corr-old")
        fresh = self._event(correlation_id="corr-fresh")
        ErrorEvent.objects.filter(pk=old.pk).update(
            occurred_at=timezone.now() - timedelta(days=40)
        )
        call_command("purge_error_events", days=30, verbosity=0)
        self.assertFalse(ErrorEvent.objects.filter(pk=old.pk).exists())
        self.assertTrue(ErrorEvent.objects.filter(pk=fresh.pk).exists())

    def test_dry_run_keeps_events(self):
        old = self._event(correlation_id="corr-old")
        ErrorEvent.objects.filter(pk=old.pk).update(
            occurred_at=timezone.now() - timedelta(days=40)
        )
        call_command("purge_error_events", days=30, dry_run=True, verbosity=0)
        self.assertTrue(ErrorEvent.objects.filter(pk=old.pk).exists())
