"""Verträge für den Docker-Installationsweg (Worker-Gesundheit, Rollen, Compose)."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError
from django.test import SimpleTestCase, TestCase

ROOT = Path(__file__).resolve().parents[1]
NOTIFY = "core.management.commands.notify_crew"


class NotifyCrewHeartbeatTests(SimpleTestCase):
    """K1: Der notify-worker darf DB-Fehler nicht still schlucken."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.heartbeat = Path(self.tmp.name) / "notify.alive"
        for target in ("signal.signal", "close_old_connections", "time.sleep"):
            patcher = patch(f"{NOTIFY}.{target}")
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_success_writes_heartbeat(self):
        with patch(f"{NOTIFY}.notify_ready_vehicles", return_value=0):
            call_command("notify_crew", heartbeat_file=str(self.heartbeat), stdout=io.StringIO())
        self.assertTrue(self.heartbeat.read_text().strip())

    def test_repeated_db_errors_exit_non_zero_without_heartbeat(self):
        error = OperationalError("could not translate host name \"db\"")
        with patch(f"{NOTIFY}.notify_ready_vehicles", side_effect=error) as notify:
            with self.assertLogs(NOTIFY, level="ERROR"), self.assertRaises(CommandError):
                call_command(
                    "notify_crew", watch=True, max_failures=3, heartbeat_file=str(self.heartbeat),
                    stdout=io.StringIO(),
                )
        self.assertEqual(notify.call_count, 3)
        self.assertFalse(self.heartbeat.exists())

    def test_single_run_reports_error(self):
        with patch(f"{NOTIFY}.notify_ready_vehicles", side_effect=OperationalError("down")):
            with self.assertLogs(NOTIFY, level="ERROR"), self.assertRaises(CommandError):
                call_command("notify_crew")

    def test_transient_error_resets_failure_counter(self):
        outcomes = [OperationalError("down"), 0, OperationalError("down"), 0, KeyboardInterrupt()]
        with patch(f"{NOTIFY}.notify_ready_vehicles", side_effect=outcomes):
            with self.assertLogs(NOTIFY, level="ERROR"), self.assertRaises(KeyboardInterrupt):
                call_command(
                    "notify_crew", watch=True, max_failures=2, heartbeat_file=str(self.heartbeat),
                    stdout=io.StringIO(),
                )
        self.assertTrue(self.heartbeat.exists())


def compose_command():
    docker = shutil.which("docker")
    if docker and subprocess.run(
        [docker, "compose", "version"], capture_output=True, timeout=15
    ).returncode == 0:
        return [docker, "compose"]
    standalone = shutil.which("docker-compose")
    return [standalone] if standalone else None


class ComposeNetworkContractTests(SimpleTestCase):
    """Jeder Dienst, der db/redis anspricht, muss ein Netz mit ihnen teilen."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        command = compose_command()
        if command is None:
            raise __import__("unittest").SkipTest("Compose CLI nicht verfügbar")
        with tempfile.TemporaryDirectory(prefix="wachbuch-compose-net-") as home:
            env = {"PATH": os.environ.get("PATH", os.defpath), "HOME": home,
                   "COMPOSE_PROFILES": "ops,https"}
            # Ohne DOCKER_CONFIG sucht die CLI Plugins unter $HOME/.docker – das
            # ist hier ein leeres Temp-Verzeichnis. Deshalb das echte durchreichen.
            env["DOCKER_CONFIG"] = os.environ.get("DOCKER_CONFIG") or os.path.expanduser("~/.docker")
            result = subprocess.run(
                command + ["--env-file", os.devnull, "-f", str(ROOT / "docker-compose.yml"),
                           "config", "--format", "json"],
                env=env, capture_output=True, text=True, timeout=45,
            )
        if result.returncode != 0:
            raise AssertionError(f"Compose-Rendering fehlgeschlagen: {result.stderr[-500:]}")
        cls.services = json.loads(result.stdout)["services"]

    def networks(self, name):
        return set((self.services[name].get("networks") or {}).keys())

    def test_db_clients_share_network_with_db(self):
        db_networks = self.networks("db")
        for name, service in self.services.items():
            env = service.get("environment") or {}
            if env.get("DB_HOST") == "db" or env.get("PGHOST") == "db":
                with self.subTest(service=name):
                    self.assertTrue(self.networks(name) & db_networks, name)

    def test_redis_clients_share_network_with_redis(self):
        redis_networks = self.networks("redis")
        for name, service in self.services.items():
            env = service.get("environment") or {}
            if "redis:" in str(env.get("REDIS_URL", "")) or env.get("REDIS_HOST") == "redis":
                with self.subTest(service=name):
                    self.assertTrue(self.networks(name) & redis_networks, name)

    def test_long_running_workers_are_hardened_and_checked(self):
        for name in ("notify-worker", "push-worker", "feed-worker", "web"):
            service = self.services[name]
            with self.subTest(service=name):
                self.assertTrue(service.get("read_only"))
                self.assertIn("ALL", service.get("cap_drop", []))
                self.assertIn("no-new-privileges:true", service.get("security_opt", []))
        self.assertFalse(self.services["notify-worker"]["healthcheck"].get("disable", False))


class LoopbackAllowedHostsTests(SimpleTestCase):
    """K3: Der Healthcheck (Host: localhost) darf nie an ALLOWED_HOSTS scheitern."""

    def test_loopback_hosts_are_always_allowed(self):
        env = dict(os.environ, ALLOWED_HOSTS="wache.example", DJANGO_SECRET_KEY="x" * 50,
                   DJANGO_DEBUG="false")
        result = subprocess.run(
            [sys.executable, "-c", "import json, config.settings as s; print(json.dumps(s.ALLOWED_HOSTS))"],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-500:])
        self.assertEqual(json.loads(result.stdout.strip().splitlines()[-1]),
                         ["wache.example", "localhost", "127.0.0.1"])

    def test_compose_healthcheck_sends_loopback_host(self):
        for path in ("docker-compose.yml", "Dockerfile"):
            with self.subTest(path=path):
                self.assertIn("headers={'Host': 'localhost'}", (ROOT / path).read_text())


class GrantCreatesMissingRolesTests(TestCase):
    """K5: Alte Volumes ohne rwsth_push dürfen grant_database_access nicht abbrechen."""

    BASE_ENV = {
        "APP_DB_USER": "rwsth_app", "FEED_DB_USER": "rwsth_feed",
        "BACKUP_DB_USER": "rwsth_backup", "POSTGRES_USER": "rwsth_owner",
        "POSTGRES_DB": "rwsth", "APP_DB_PASSWORD": "app-pw",
        "FEED_DB_PASSWORD": "feed-pw", "BACKUP_DB_PASSWORD": "backup-pw",
    }

    def run_grant(self, **env):
        executed = []

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def execute(self, statement):
                executed.append(statement)

        with patch.dict(os.environ, dict(self.BASE_ENV, **env)), patch(
            "core.management.commands.grant_database_access.connection.cursor",
            return_value=Cursor(),
        ):
            for key in ("PUSH_DB_USER", "PUSH_DB_PASSWORD"):
                if key not in env:
                    os.environ.pop(key, None)
            call_command("grant_database_access", stdout=io.StringIO())
        return executed

    def test_missing_roles_are_created_before_grants(self):
        executed = self.run_grant(PUSH_DB_PASSWORD="it's-secret")
        creates = executed[:4]
        for role in ("rwsth_app", "rwsth_feed", "rwsth_backup", "rwsth_push"):
            with self.subTest(role=role):
                self.assertTrue(any(f"rolname = '{role}'" in s and f"CREATE ROLE {role} " in s
                                    for s in creates), creates)
        self.assertIn("LOGIN PASSWORD 'it''s-secret'", creates[3])
        self.assertTrue(all(s.startswith("DO $rwsth_role$") for s in creates))
        self.assertTrue(executed[4].startswith("REVOKE"))

    def test_role_without_password_is_nologin(self):
        executed = self.run_grant()
        push = [s for s in executed if "CREATE ROLE rwsth_push" in s]
        self.assertEqual(len(push), 1)
        self.assertIn("CREATE ROLE rwsth_push NOLOGIN", push[0])

    def test_dollar_quote_breakout_is_rejected(self):
        with self.assertRaises(CommandError):
            self.run_grant(PUSH_DB_PASSWORD="x$rwsth_role$; DROP ROLE rwsth_owner; --")
