"""Betrieb ohne Eingriff: Aufräumen, Lebenszeichen und Healthchecks.

- ``housekeeping`` löscht nach den Fristen, aber nie append-only Zeilen.
- housekeeping, demo-cleaner und push-worker laufen als Dauerschleife mit
  Lebenszeichen; ohne Datenbank bleibt es aus.
- ``/healthz/`` prüft Datenbank und Cache und meldet sonst 503.
- Jeder lang laufende Compose-Dienst hat einen eigenen Healthcheck.
"""
from __future__ import annotations

import io
import json
import os
import re
import runpy
import shutil
import signal
import subprocess
import tempfile
import types
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from axes.models import AccessLog
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError, connection
from django.test import SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from core.diagnostics_models import ErrorEvent
from core.feedback_models import Feedback
from core.management.commands.grant_database_access import WASTE_STATION_COLUMNS
from core.management.commands.housekeeping import STEPS
from core.management.commands.sync_feeds import WASTE_SYNC_SECONDS, Command as SyncFeedsCommand
from core.models import AuditEvent, QrTotpUse, RateLimit, Station, WasteCollection

ROOT = Path(__file__).resolve().parents[1]
WATCH = "core.management.commands._watch"
HOUSEKEEPING = "core.management.commands.housekeeping"
PUSH = "core.management.commands.push_worker"
ICS = (
    b"BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nSUMMARY:Restmuell\r\nDTSTART;VALUE=DATE:20261105\r\n"
    b"END:VEVENT\r\nEND:VCALENDAR\r\n"
)


class LoopPatches:
    """Ersetzt Signal-Handler, Schlaf und Verbindungsabbau einer Dauerschleife.

    Nach ``stop_after`` Sekunden Wartezeit kommt ein SIGTERM wie von
    ``docker compose stop``.
    """

    def __init__(self, testcase, module, stop_after=None):
        self.handlers, self.sleeps = {}, []
        self.stop_after = stop_after
        targets = {
            "signal.signal": lambda signum, handler: self.handlers.__setitem__(signum, handler),
            "time.sleep": self.sleep,
            "close_old_connections": lambda: None,
        }
        self.mocks = {}
        for target, replacement in targets.items():
            patcher = patch(f"{module}.{target}", side_effect=replacement)
            self.mocks[target] = patcher.start()
            testcase.addCleanup(patcher.stop)

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        if self.stop_after is not None and len(self.sleeps) >= self.stop_after:
            self.handlers[signal.SIGTERM](signal.SIGTERM, None)


class HeartbeatFileMixin:
    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.heartbeat = Path(tmp.name) / "worker.alive"


class HousekeepingRetentionTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.user = User.objects.create_user("housekeeping-user")

    def backdate(self, model, obj, field, delta):
        model._base_manager.filter(pk=obj.pk).update(**{field: self.now - delta})
        return obj

    def access_log(self, username):
        return AccessLog.objects.create(
            username=username, ip_address="198.51.100.7", user_agent="Testbrowser",
            http_accept="*/*", path_info="/anmelden/",
        )

    @override_settings(FEEDBACK_RETENTION_DAYS=365, ERROR_EVENT_RETENTION_DAYS=30, RETENTION_AUDIT_DAYS=1)
    def test_deletes_expired_rows_keeps_fresh_ones_and_never_audit(self):
        old_session = Session.objects.create(
            session_key="a" * 32, session_data="x", expire_date=self.now - timedelta(hours=1))
        fresh_session = Session.objects.create(
            session_key="b" * 32, session_data="x", expire_date=self.now + timedelta(hours=11))
        old_log = self.backdate(AccessLog, self.access_log("alt"), "attempt_time", timedelta(days=31))
        fresh_log = self.access_log("neu")
        old_feedback = self.backdate(Feedback, Feedback.objects.create(message="alt", name="A", email="a@example.org"),
                                     "created_at", timedelta(days=366))
        fresh_feedback = Feedback.objects.create(message="neu")
        event = {"route_name": "landing", "http_status": 500, "app_version": "0.26.0"}
        old_event = self.backdate(ErrorEvent, ErrorEvent.objects.create(correlation_id="alt", **event),
                                  "occurred_at", timedelta(days=31))
        fresh_event = ErrorEvent.objects.create(correlation_id="neu", **event)
        old_totp = self.backdate(QrTotpUse, QrTotpUse.objects.create(user=self.user, time_step=1),
                                 "created_at", timedelta(hours=25))
        old_limit = RateLimit.objects.create(bucket="feedback", key_hash="h", window_start=self.now - timedelta(days=8))
        fresh_limit = RateLimit.objects.create(bucket="feedback", key_hash="h", window_start=self.now)
        audit = self.backdate(AuditEvent, AuditEvent.objects.create(action="test", object_type="test"),
                              "created_at", timedelta(days=400))

        out = io.StringIO()
        call_command("housekeeping", stdout=out)

        for gone in (old_session, old_log, old_feedback, old_event, old_totp, old_limit):
            with self.subTest(gone=type(gone).__name__):
                self.assertFalse(type(gone)._base_manager.filter(pk=gone.pk).exists())
        for kept in (fresh_session, fresh_log, fresh_feedback, fresh_event, fresh_limit):
            with self.subTest(kept=type(kept).__name__):
                self.assertTrue(type(kept)._base_manager.filter(pk=kept.pk).exists())
        # Append-only: auch mit RETENTION_AUDIT_DAYS nie im App-Dienst.
        self.assertTrue(AuditEvent.objects.filter(pk=audit.pk).exists())
        self.assertIn("Sitzungen: 1", out.getvalue())
        self.assertIn("Rückmeldungen: 1", out.getvalue())

    def test_push_outbox_and_feed_retention_are_part_of_the_run(self):
        with patch(f"{HOUSEKEEPING}.apply_pushoutbox_retention", return_value=3) as push, \
                patch(f"{HOUSEKEEPING}.apply_feed_retention", return_value=2) as feed:
            out = io.StringIO()
            call_command("housekeeping", stdout=out)
        push.assert_called_once()
        feed.assert_called_once()
        self.assertIn("Push-Nachrichten: 3", out.getvalue())
        self.assertIn("Feed-Einträge: 2", out.getvalue())

    def test_failing_step_does_not_stop_the_others(self):
        old = self.backdate(Feedback, Feedback.objects.create(message="alt"), "created_at", timedelta(days=400))
        with patch(f"{HOUSEKEEPING}.apply_feed_retention", side_effect=RuntimeError("kaputt")), \
                self.assertLogs(HOUSEKEEPING, level="ERROR"), self.assertRaises(CommandError) as raised:
            call_command("housekeeping", stdout=io.StringIO())
        self.assertIn("Feed-Einträge", str(raised.exception))
        self.assertFalse(Feedback.objects.filter(pk=old.pk).exists())

    def test_login_logs_can_be_kept(self):
        old_log = self.backdate(AccessLog, self.access_log("alt"), "attempt_time", timedelta(days=90))
        with patch.dict(os.environ, {"LOGIN_LOG_RETENTION_DAYS": "0"}):
            call_command("housekeeping", stdout=io.StringIO())
        self.assertTrue(AccessLog.objects.filter(pk=old_log.pk).exists())


class HousekeepingWatchTests(HeartbeatFileMixin, TestCase):
    def setUp(self):
        super().setUp()
        patcher = patch(f"{HOUSEKEEPING}.connections")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_watch_writes_heartbeat_and_stops_within_a_second(self):
        loop = LoopPatches(self, WATCH, stop_after=1)
        out = io.StringIO()
        call_command("housekeeping", watch=True, heartbeat_file=str(self.heartbeat), stdout=out)
        self.assertTrue(self.heartbeat.read_text().strip())
        self.assertIn("Datenbank erreichbar", out.getvalue())
        self.assertEqual(loop.sleeps, [1])

    def test_database_outage_exits_after_max_failures_without_heartbeat(self):
        LoopPatches(self, WATCH)
        with patch(f"{HOUSEKEEPING}.run_housekeeping", side_effect=OperationalError("db weg")) as run, \
                self.assertLogs(WATCH, level="ERROR"), self.assertRaises(CommandError):
            call_command("housekeeping", watch=True, max_failures=3,
                         heartbeat_file=str(self.heartbeat), stdout=io.StringIO())
        self.assertEqual(run.call_count, 3)
        self.assertFalse(self.heartbeat.exists())

    def test_all_steps_failing_counts_as_failure(self):
        LoopPatches(self, WATCH)
        failed_everything = ({}, [name for name, _step in STEPS])
        with patch(f"{HOUSEKEEPING}.run_housekeeping", return_value=failed_everything), \
                self.assertLogs(WATCH, level="ERROR"), self.assertRaises(CommandError):
            call_command("housekeeping", watch=True, max_failures=2,
                         heartbeat_file=str(self.heartbeat), stdout=io.StringIO())
        self.assertFalse(self.heartbeat.exists())


class DemoCleanerWatchTests(HeartbeatFileMixin, SimpleTestCase):
    PURGE = "core.management.commands.purge_demo_sandboxes.purge_expired"

    def test_watch_purges_writes_heartbeat_and_stops(self):
        LoopPatches(self, WATCH, stop_after=1)
        out = io.StringIO()
        with patch(self.PURGE, return_value=2) as purge:
            call_command("purge_demo_sandboxes", watch=True, heartbeat_file=str(self.heartbeat), stdout=out)
        purge.assert_called_once_with()
        self.assertIn("2 Demo-Wache(n) gelöscht.", out.getvalue())
        self.assertTrue(self.heartbeat.exists())

    def test_failures_exit_non_zero_without_heartbeat(self):
        LoopPatches(self, WATCH)
        with patch(self.PURGE, side_effect=OperationalError("db weg")), \
                self.assertLogs(WATCH, level="ERROR"), self.assertRaises(CommandError):
            call_command("purge_demo_sandboxes", watch=True, max_failures=2,
                         heartbeat_file=str(self.heartbeat), stdout=io.StringIO())
        self.assertFalse(self.heartbeat.exists())

    def test_watch_never_purges_running_demos(self):
        with self.assertRaises(CommandError):
            call_command("purge_demo_sandboxes", watch=True, all=True)


class PushWorkerHeartbeatTests(HeartbeatFileMixin, SimpleTestCase):
    def test_success_writes_heartbeat_reconnects_and_stops_quickly(self):
        loop = LoopPatches(self, PUSH, stop_after=1)
        with patch(f"{PUSH}.process_once", return_value=0):
            call_command("push_worker", watch=True, interval=15,
                         heartbeat_file=str(self.heartbeat), stdout=io.StringIO())
        self.assertTrue(self.heartbeat.exists())
        self.assertEqual(loop.sleeps, [1])
        self.assertTrue(loop.mocks["close_old_connections"].called)

    def test_database_error_leaves_no_heartbeat(self):
        LoopPatches(self, PUSH)
        with patch(f"{PUSH}.process_once", side_effect=OperationalError("password authentication failed")), \
                self.assertLogs(PUSH, level="ERROR"):
            call_command("push_worker", once=True, heartbeat_file=str(self.heartbeat), stdout=io.StringIO())
        self.assertFalse(self.heartbeat.exists())


class HealthzTests(TestCase):
    def test_healthy_reports_database_and_cache(self):
        response = self.client.get(reverse("healthz"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["checks"], {"database": "ok", "cache": "ok"})

    def test_cache_outage_returns_503_without_error_events(self):
        with patch("django.core.cache.backends.locmem.LocMemCache.set",
                   side_effect=ConnectionError("Redis weg")), self.assertLogs("core.views", "WARNING"):
            response = self.client.get(reverse("healthz"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "error")
        self.assertEqual(response.json()["checks"], {"database": "ok", "cache": "error"})
        self.assertFalse(ErrorEvent.objects.exists())

    def test_database_outage_returns_503_json(self):
        with patch("core.views._health_database", side_effect=OperationalError("db weg")), \
                self.assertLogs("core.views", "WARNING"):
            response = self.client.get(reverse("healthz"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["checks"]["database"], "error")


class WasteCalendarSyncTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(
            name="Wache Nord", slug="wache-nord", waste_calendar_enabled=True,
            waste_calendar_url="https://abfall.example.org/nord.ics", iban="DE02120300000000202051",
        )

    def test_reads_only_the_station_columns_granted_to_the_feed_worker(self):
        with patch("core.waste_sync.fetch_waste_calendar", return_value=ICS), \
                CaptureQueriesContext(connection) as queries:
            call_command("sync_waste_calendar", stdout=io.StringIO())
        self.assertEqual(WasteCollection.objects.filter(station=self.station).count(), 1)
        station_sql = [q["sql"] for q in queries.captured_queries if '"core_station"' in q["sql"]]
        self.assertTrue(station_sql)
        for sql in station_sql:
            with self.subTest(sql=sql):
                columns = set(re.findall(r'"core_station"\."(\w+)"', sql))
                self.assertLessEqual(columns, set(WASTE_STATION_COLUMNS))

    def test_new_only_skips_stations_that_already_have_pickups(self):
        with patch("core.waste_sync.fetch_waste_calendar", return_value=ICS) as fetch:
            call_command("sync_waste_calendar", new_only=True, stdout=io.StringIO())
            call_command("sync_waste_calendar", new_only=True, stdout=io.StringIO())
        self.assertEqual(fetch.call_count, 1)

    def test_feed_worker_fetches_all_calendars_every_six_hours_and_new_ones_in_between(self):
        command = SyncFeedsCommand(stdout=io.StringIO(), stderr=io.StringIO())
        with patch("core.management.commands.sync_feeds.call_command") as call:
            due = command.sync_waste_calendars(0.0)
            self.assertEqual(command.sync_waste_calendars(due), due)
        self.assertEqual([c.kwargs["new_only"] for c in call.call_args_list], [False, True])
        self.assertEqual(call.call_args.args, ("sync_waste_calendar",))
        self.assertGreater(due, WASTE_SYNC_SECONDS - 1)

    def test_waste_calendar_error_never_stops_the_feed_worker(self):
        err = io.StringIO()
        with patch("core.management.commands.sync_feeds.call_command", side_effect=RuntimeError("kaputt")), \
                patch("core.management.commands.sync_feeds.close_old_connections"):
            call_command("sync_feeds", stdout=io.StringIO(), stderr=err)
        self.assertIn("Muellkalender: kaputt", err.getvalue())


class GrantWasteCalendarTests(TestCase):
    ENV = {
        "APP_DB_USER": "rwsth_app", "FEED_DB_USER": "rwsth_feed", "BACKUP_DB_USER": "rwsth_backup",
        "PUSH_DB_USER": "rwsth_push", "POSTGRES_USER": "rwsth_owner", "POSTGRES_DB": "rwsth",
    }

    def statements(self):
        executed = []

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def execute(self, statement):
                executed.append(statement)

        with patch.dict(os.environ, self.ENV), patch(
            "core.management.commands.grant_database_access.connection.cursor", return_value=Cursor(),
        ):
            call_command("grant_database_access", stdout=io.StringIO())
        return executed

    def test_feed_worker_reads_only_waste_columns_of_the_station(self):
        executed = self.statements()
        self.assertIn("GRANT SELECT (id, name, is_active, waste_calendar_enabled, waste_calendar_url) "
                      "ON core_station TO rwsth_feed", executed)
        self.assertIn("GRANT SELECT, INSERT, DELETE ON core_wastecollection TO rwsth_feed", executed)
        table_wide = [s for s in executed if re.match(r"GRANT [A-Z, ]+ ON core_station TO rwsth_feed$", s)]
        self.assertEqual(table_wide, [])


class GunicornConfigTests(SimpleTestCase):
    def test_control_socket_is_off_and_every_setting_is_known(self):
        from gunicorn.config import Config

        namespace = runpy.run_path(str(ROOT / "config" / "gunicorn.py"))
        names = {name for name, value in namespace.items()
                 if name.islower() and not name.startswith("_") and not isinstance(value, types.ModuleType)}
        # Unbekannte Namen ignoriert Gunicorn still (z. B. ein Tippfehler).
        self.assertEqual(names - set(Config().settings), set())
        self.assertIs(namespace["control_socket_disable"], True)


class JavaScriptSyntaxTests(TestCase):
    """Wie der CI-Schritt, dazu der gerenderte Service Worker."""

    def test_app_scripts_and_rendered_service_worker_parse(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node nicht installiert")
        scripts = sorted((ROOT / "core" / "static" / "core").glob("*.js"))
        self.assertTrue(scripts)
        with tempfile.TemporaryDirectory() as tmp:
            worker = Path(tmp) / "service-worker.js"
            worker.write_bytes(self.client.get(reverse("service_worker")).content)
            for script in [*scripts, worker]:
                with self.subTest(script=script.name):
                    result = subprocess.run([node, "--check", str(script)], capture_output=True, text=True, timeout=60)
                    self.assertEqual(result.returncode, 0, result.stderr[-500:])


def compose_command():
    docker = shutil.which("docker")
    if docker and subprocess.run([docker, "compose", "version"], capture_output=True, timeout=15).returncode == 0:
        return [docker, "compose"]
    standalone = shutil.which("docker-compose")
    return [standalone] if standalone else None


APP_IMAGE = "/rettungswache-wachbuch:"
# Lang laufende Dienste ohne eigenen Healthcheck in Compose – mit Grund.
WITHOUT_OWN_HEALTHCHECK = {
    "backup": "eigenes Image ohne Listener; wachwerk-health prüft das Alter des neuesten Dumps",
    "caddy": "Admin-API aus; wachwerk-health prüft /healthz/ über Caddy, Caddy endet bei Konfigurationsfehlern",
    "signal": "Image bringt HEALTHCHECK mit (curl /v1/health, geprüft für 0.101)",
}


class ComposeHealthcheckContractTests(SimpleTestCase):
    """Wächter gegen geerbte oder leere Healthchecks (demo-cleaner, push-worker)."""

    ENV = {"APP_DB_USER": "rwsth_app", "POSTGRES_USER": "rwsth_owner", "FEED_DB_USER": "rwsth_feed"}

    def render(self, *files, **env):
        command = compose_command()
        if command is None:
            self.skipTest("Compose CLI nicht verfügbar")
        files = files or ("docker-compose.yml",)
        with tempfile.TemporaryDirectory(prefix="wachbuch-compose-health-") as home:
            environment = {"PATH": os.environ.get("PATH", os.defpath), "HOME": home,
                           "DOCKER_CONFIG": os.environ.get("DOCKER_CONFIG") or os.path.expanduser("~/.docker"),
                           "COMPOSE_PROFILES": "ops,https,demo,signal", **self.ENV, **env}
            arguments = [part for name in files for part in ("-f", str(ROOT / name))]
            result = subprocess.run(command + ["--env-file", os.devnull, *arguments, "config", "--format", "json"],
                                    env=environment, capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stderr[-500:])
        return json.loads(result.stdout)["services"]

    @staticmethod
    def start_script(service):
        command = service.get("command") or []
        scripts = [ROOT / part.removeprefix("/app/") for part in command if part.startswith("/app/scripts/")]
        return "".join(path.read_text(encoding="utf-8") for path in scripts)

    def test_every_long_running_service_has_its_own_healthcheck(self):
        services = self.render()
        self.assertLessEqual(set(WITHOUT_OWN_HEALTHCHECK), set(services))
        for name, service in services.items():
            if service.get("restart") in (None, "no"):
                continue
            with self.subTest(service=name):
                if name in WITHOUT_OWN_HEALTHCHECK:
                    self.assertNotIn(APP_IMAGE, service["image"])
                    continue
                check = service.get("healthcheck") or {}
                self.assertTrue(check.get("test"), "kein Healthcheck: erbt sonst den des Images")
                self.assertFalse(check.get("disable", False))
                test = " ".join(check["test"])
                self.assertNotIn("test -f", test, "Datei vorhanden heißt nicht lebendig")
                if APP_IMAGE in service["image"] and service.get("command"):
                    self.assertNotIn(":8000/healthz/", test, "Worker ohne Gunicorn")
                wiring = json.dumps(service.get("command")) + json.dumps(service.get("environment")) \
                    + self.start_script(service)
                for path in re.findall(r"/tmp/[\w.]+\.alive", test):
                    self.assertIn(path, wiring, "Healthcheck prüft eine Datei, die niemand schreibt")

    def test_housekeeping_runs_in_every_profile_as_app_role_without_internet(self):
        service = self.render(COMPOSE_PROFILES="")["housekeeping"]
        self.assertEqual(service["command"][:4], ["python", "manage.py", "housekeeping", "--watch"])
        self.assertEqual(service["environment"]["DB_USER"], "rwsth_app")
        self.assertEqual(set(service["networks"]), {"app-db"})
        self.assertNotIn("RETENTION_AUDIT_DAYS", service["environment"])
        for key in ("RETENTION_FEED_DAYS", "FEEDBACK_RETENTION_DAYS", "ERROR_EVENT_RETENTION_DAYS",
                    "LOGIN_LOG_RETENTION_DAYS"):
            self.assertIn(key, service["environment"])

    def test_demo_cleaner_is_one_long_running_process(self):
        command = self.render()["demo-cleaner"]["command"]
        self.assertEqual(command[:4], ["python", "manage.py", "purge_demo_sandboxes", "--watch"])

    def test_local_build_covers_every_app_service(self):
        services = self.render("docker-compose.yml", "compose.build.yml")
        for name, service in services.items():
            with self.subTest(service=name):
                self.assertFalse(service["image"].startswith("ghcr.io/"), "zöge sonst das Release-Image")

    def test_caddy_publishes_ipv4_only_unless_bound(self):
        # Ohne host_ip auch [::]: docker-proxy reichte IPv6-Besucher von der
        # Gateway-Adresse des IPv4-Netzes web-ingress weiter (eine Adresse für alle).
        ports = self.render()["caddy"]["ports"]
        self.assertEqual([port.get("host_ip") for port in ports], ["0.0.0.0", "0.0.0.0"])
        bound = self.render(HTTPS_BIND_ADDRESS="127.0.0.1")["caddy"]["ports"]
        self.assertEqual([port.get("host_ip") for port in bound], ["127.0.0.1", "127.0.0.1"])

    def test_settings_reach_the_services_that_read_them(self):
        services = self.render(APP_NAME="Rettungsdienst X", FEEDBACK_PER_IP_HOUR="20")
        self.assertEqual(services["web"]["environment"]["FEEDBACK_PER_IP_HOUR"], "20")
        self.assertEqual(services["notify-worker"]["environment"]["APP_NAME"], "Rettungsdienst X")
