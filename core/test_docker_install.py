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
        # Kaffeekasse-Erinnerungen laufen im selben Durchlauf; hier ohne Datenbank.
        for target in ("remind_open_fees", "deliver_signal"):
            patcher = patch(f"{NOTIFY}.{target}", return_value=0)
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


class FeedWorkerHeartbeatTests(SimpleTestCase):
    """feed-worker braucht einen echten Healthcheck (CI: `up --wait` verlangt ihn)."""

    def test_wait_writes_heartbeat_every_minute(self):
        from core.management.commands.sync_feeds import wait_with_heartbeat

        writes, sleeps = [], []
        wait_with_heartbeat(900, "/tmp/feed.alive", sleep=sleeps.append, beat=writes.append)
        self.assertEqual(sum(sleeps), 900)
        self.assertTrue(all(chunk <= 60 for chunk in sleeps))
        self.assertGreaterEqual(len(writes), 15)

    def test_compose_has_feed_worker_healthcheck(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        block = compose.split("  feed-worker:", 1)[1].split("\n  notify-worker:", 1)[0]
        self.assertNotIn("disable: true", block)
        self.assertIn("feed_worker.alive", block)


class AutoUpdateCliTests(SimpleTestCase):
    """`wachbuch auto-update`: nächtliche Updates mit Backup und Rollback.

    Läuft gegen Attrappen für docker und crontab (scripts/tests/fake_docker.py),
    damit die Abläufe ohne Docker-Daemon in der CI prüfbar sind.
    """

    OLD = {"app": "sha256:app-old", "backup": "sha256:backup-old", "db": "sha256:db-old"}
    NEW = {"app": "sha256:app-new", "backup": "sha256:backup-new", "db": "sha256:db-new"}

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wachbuch-auto-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.dir = self.tmp / "install"
        (self.dir / "deploy" / "caddy").mkdir(parents=True)
        shutil.copy(ROOT / "scripts" / "wachbuch", self.dir / "wachbuch")
        (self.dir / "compose.yml").write_text("# alt\n", encoding="utf-8")
        (self.dir / "deploy" / "caddy" / "Caddyfile").write_text("# alt\n", encoding="utf-8")
        self.remote = self.tmp / "remote"
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        (self.bin / "docker").symlink_to(ROOT / "scripts" / "tests" / "fake_docker.py")
        crontab = self.bin / "crontab"
        crontab.write_text(
            '#!/bin/sh\nf="$FAKE_CRONTAB"\n'
            'if [ "$1" = "-l" ]; then [ -f "$f" ] && cat "$f" || exit 1;\n'
            'elif [ "$1" = "-" ]; then cat >"$f"; fi\n',
            encoding="utf-8",
        )
        crontab.chmod(0o755)
        self.state_file = self.tmp / "docker.json"
        self.write_env(WACHBUCH_VERSION="0.25.0")
        self.set_state(images=self.images("0.25.0", self.OLD), remote=self.images("0.25.0", self.OLD))

    # --- Hilfen -------------------------------------------------------------
    def images(self, version, ids):
        base = "ghcr.io/katschko-it/rettungswache-wachbuch"
        return {f"{base}:{version}": ids["app"], f"{base}-backup:{version}": ids["backup"],
                f"{base}-db:{version}": ids["db"]}

    def write_env(self, **values):
        lines = [f"{k}={v}" for k, v in {"POSTGRES_DB": "rwsth", "HTTP_PORT": "18090", **values}.items()]
        (self.dir / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def env(self, key):
        found = ""
        for line in (self.dir / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith(key + "="):
                found = line.split("=", 1)[1]
        return found

    def set_state(self, **state):
        self.state_file.write_text(json.dumps({"images": {}, "remote": {}, **state}), encoding="utf-8")

    def state(self):
        return json.loads(self.state_file.read_text(encoding="utf-8"))

    def calls(self):
        path = Path(str(self.state_file) + ".calls")
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def publish_release(self, version):
        """Release-Dateien und releases/latest wie auf GitHub, per file://."""
        for name, content in (("docker-compose.yml", f"# {version}\n"),
                              ("deploy/caddy/Caddyfile", f"# {version}\n"),
                              ("scripts/wachbuch", (ROOT / "scripts" / "wachbuch").read_text(encoding="utf-8"))):
            target = self.remote / f"v{version}" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        (self.remote / "latest.json").write_text(json.dumps({"tag_name": f"v{version}"}), encoding="utf-8")
        with open(self.dir / ".env", "a", encoding="utf-8") as handle:
            handle.write(f"WACHBUCH_BASE_URL=file://{self.remote}\n")
            handle.write(f"WACHBUCH_RELEASES_API=file://{self.remote}/latest.json\n")

    def run_cli(self, *args):
        environment = {
            "PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', os.defpath)}",
            "HOME": str(self.tmp),
            "FAKE_DOCKER_STATE": str(self.state_file),
            "FAKE_CRONTAB": str(self.tmp / "crontab.txt"),
        }
        return subprocess.run(
            ["sh", str(self.dir / "wachbuch"), *args],
            cwd=self.dir, env=environment, capture_output=True, text=True, timeout=60,
        )

    def compose_calls(self, command):
        return [c for c in self.calls() if c[:2] == ["compose", command]]

    def log(self):
        path = self.dir / "logs" / "auto-update.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    # --- Ablauf ---------------------------------------------------------------
    def test_without_new_images_nothing_restarts(self):
        self.write_env(WACHBUCH_VERSION="0.25.0", WACHBUCH_AUTO_UPDATE="sicherheit")
        result = self.run_cli("auto-update", "run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.compose_calls("pull"))
        self.assertFalse(self.compose_calls("up"))
        self.assertFalse(self.compose_calls("exec"))
        self.assertIn("aktuell", self.log())

    def test_refreshed_images_are_backed_up_and_started(self):
        self.write_env(WACHBUCH_VERSION="0.25.0", WACHBUCH_AUTO_UPDATE="sicherheit")
        self.set_state(images=self.images("0.25.0", self.OLD), remote=self.images("0.25.0", self.NEW))
        result = self.run_cli("auto-update", "run")
        self.assertEqual(result.returncode, 0, result.stderr)
        exec_calls = self.compose_calls("exec")
        up_calls = self.compose_calls("up")
        self.assertTrue(exec_calls and up_calls)
        self.assertLess(self.calls().index(exec_calls[0]), self.calls().index(up_calls[0]), "Backup vor Neustart")
        self.assertTrue((self.dir / "backups" / "rwsth-test.dump").exists())
        self.assertEqual(self.state()["images"], self.images("0.25.0", self.NEW))

    def test_failed_start_rolls_back_to_previous_images(self):
        self.write_env(WACHBUCH_VERSION="0.25.0", WACHBUCH_AUTO_UPDATE="sicherheit")
        self.set_state(images=self.images("0.25.0", self.OLD), remote=self.images("0.25.0", self.NEW),
                       fail_up_ids=[self.NEW["app"]])
        result = self.run_cli("auto-update", "run")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.state()["images"], self.images("0.25.0", self.OLD))
        self.assertEqual(len(self.compose_calls("up")), 2, "Neustart und Rollback-Start")
        self.assertIn("Rollback", self.log())

    def test_containers_on_outdated_images_are_restarted(self):
        # Images wurden schon (z. B. manuell) geladen, die Container laufen aber
        # noch mit dem alten Stand: auch das ist ein fälliges Update.
        self.write_env(WACHBUCH_VERSION="0.25.0", WACHBUCH_AUTO_UPDATE="sicherheit")
        self.set_state(images=self.images("0.25.0", self.NEW), remote=self.images("0.25.0", self.NEW),
                       running=self.images("0.25.0", self.OLD))
        result = self.run_cli("auto-update", "run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.compose_calls("up"))
        self.assertEqual(self.state()["running"], self.images("0.25.0", self.NEW))

    def test_all_mode_takes_new_minor_version(self):
        self.write_env(WACHBUCH_VERSION="0.25.0", WACHBUCH_AUTO_UPDATE="alle")
        self.publish_release("0.26.0")
        self.set_state(images=self.images("0.25.0", self.OLD), remote=self.images("0.26.0", self.NEW))
        result = self.run_cli("auto-update", "run")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(self.env("WACHBUCH_VERSION"), "0.26.0")
        self.assertEqual((self.dir / "compose.yml").read_text(encoding="utf-8"), "# 0.26.0\n")

    def test_all_mode_never_jumps_major_version(self):
        self.write_env(WACHBUCH_VERSION="0.25.0", WACHBUCH_AUTO_UPDATE="alle")
        self.publish_release("1.0.0")
        result = self.run_cli("auto-update", "run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.env("WACHBUCH_VERSION"), "0.25.0")
        self.assertIn("Hauptversion", self.log())

    def test_failed_version_update_restores_files_and_version(self):
        self.write_env(WACHBUCH_VERSION="0.25.0", WACHBUCH_AUTO_UPDATE="alle")
        self.publish_release("0.26.0")
        self.set_state(images=self.images("0.25.0", self.OLD), remote=self.images("0.26.0", self.NEW),
                       fail_up_ids=[self.NEW["app"]])
        result = self.run_cli("auto-update", "run")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.env("WACHBUCH_VERSION"), "0.25.0")
        self.assertEqual((self.dir / "compose.yml").read_text(encoding="utf-8"), "# alt\n")
        self.assertIn("Rollback", self.log())

    def test_development_install_is_not_auto_updated(self):
        self.write_env(WACHBUCH_VERSION="0.25.0", WACHBUCH_AUTO_UPDATE="sicherheit",
                       COMPOSE_FILE="compose.yml:compose.build.yml")
        result = self.run_cli("auto-update", "run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.compose_calls("pull"))

    def test_switched_off_does_nothing(self):
        self.write_env(WACHBUCH_VERSION="0.25.0", WACHBUCH_AUTO_UPDATE="aus")
        result = self.run_cli("auto-update", "run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [])

    # --- Zeitplan -------------------------------------------------------------
    def test_schedule_on_and_off_via_crontab(self):
        result = self.run_cli("auto-update", "an", "alle", "--zeit", "04:10")
        self.assertEqual(result.returncode, 0, result.stderr)
        crontab = (self.tmp / "crontab.txt").read_text(encoding="utf-8")
        self.assertIn("10 4 * * *", crontab)
        self.assertIn(f"{self.dir}/wachbuch", crontab)
        self.assertIn("auto-update run", crontab)
        self.assertEqual(self.env("WACHBUCH_AUTO_UPDATE"), "alle")
        # Erneutes Einschalten ersetzt den Eintrag statt ihn zu verdoppeln.
        self.run_cli("auto-update", "an", "--zeit", "02:05")
        crontab = (self.tmp / "crontab.txt").read_text(encoding="utf-8")
        self.assertEqual(crontab.count("auto-update run"), 1)
        self.assertIn("5 2 * * *", crontab)
        self.assertEqual(self.env("WACHBUCH_AUTO_UPDATE"), "sicherheit")
        result = self.run_cli("auto-update", "aus")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("auto-update run", (self.tmp / "crontab.txt").read_text(encoding="utf-8"))
        self.assertEqual(self.env("WACHBUCH_AUTO_UPDATE"), "aus")

    def test_invalid_mode_and_time_are_rejected(self):
        self.assertNotEqual(self.run_cli("auto-update", "an", "irgendwas").returncode, 0)
        self.assertNotEqual(self.run_cli("auto-update", "an", "--zeit", "25:00").returncode, 0)
        self.assertFalse((self.tmp / "crontab.txt").exists())

    def test_concurrent_run_is_skipped(self):
        self.write_env(WACHBUCH_VERSION="0.25.0", WACHBUCH_AUTO_UPDATE="sicherheit")
        (self.dir / "logs" / "auto-update.lock").mkdir(parents=True)
        result = self.run_cli("auto-update", "run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.compose_calls("pull"))
        self.assertIn("läuft bereits", self.log())
