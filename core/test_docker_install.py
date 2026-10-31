"""Verträge für den Docker-Installationsweg (Worker-Gesundheit, Rollen, Compose)."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import re
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
        # Kaffeekasse-Erinnerungen und Meldungen der Host-Überwachung laufen im
        # selben Durchlauf; hier ohne Datenbank.
        for target in ("remind_open_fees", "deliver_signal", "notify_host_health"):
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

    def test_sigterm_ends_the_wait_within_a_second(self):
        import signal as signal_module

        with patch(f"{NOTIFY}.notify_ready_vehicles", return_value=0), \
                patch(f"{NOTIFY}.signal.signal") as register, patch(f"{NOTIFY}.time.sleep") as sleep:
            def stop_on_first_sleep(_seconds):
                handlers = {call.args[0]: call.args[1] for call in register.call_args_list}
                handlers[signal_module.SIGTERM](signal_module.SIGTERM, None)
            sleep.side_effect = stop_on_first_sleep
            call_command("notify_crew", watch=True, interval=30, stdout=io.StringIO())
        self.assertEqual(sleep.call_count, 1)


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
        # Healthcheck von `wachbuch status` beantworten, alles andere (file://) echt.
        curl = self.bin / "curl"
        curl.write_text(
            '#!/bin/sh\ncase "$*" in *127.0.0.1:18090/healthz/*) echo \'{"status": "ok"}\'; exit 0 ;; esac\n'
            f'exec {shutil.which("curl")} "$@"\n',
            encoding="utf-8",
        )
        curl.chmod(0o755)
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
        # Eigene Sitzung ohne Terminal: Rückfragen können nicht hängen bleiben.
        return subprocess.run(
            ["sh", str(self.dir / "wachbuch"), *args],
            cwd=self.dir, env=environment, capture_output=True, text=True, timeout=60,
            stdin=subprocess.DEVNULL, start_new_session=True, check=False,
        )

    def compose_calls(self, command):
        return [c for c in self.calls() if c[:2] == ["compose", command]]

    def resets(self):
        return [c for c in self.compose_calls("run") if any("pg_restore" in arg for arg in c)]

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
        self.assertFalse([c for c in self.compose_calls("exec") if "once" in c], "kein Backup")
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
        self.assertEqual(self.resets(), [], "ohne neue Migrationen kein Zurücksetzen der Datenbank")

    # --- Rollback nach eingespielten Migrationen --------------------------------
    def failing_version_update(self, **state):
        self.write_env(WACHBUCH_VERSION="0.25.0", WACHBUCH_AUTO_UPDATE="alle")
        self.publish_release("0.26.0")
        self.set_state(images=self.images("0.25.0", self.OLD), remote=self.images("0.26.0", self.NEW),
                       fail_up_ids=[self.NEW["app"]], migrations=88,
                       up_migrations={self.NEW["app"]: 94}, **state)

    def test_rollback_after_migrations_restores_pre_update_dump(self):
        # migrate der neuen Version ist durch, web startet nicht: Ohne
        # Zurücksetzen liefe 0.25.0 auf dem Schema von 0.26.0.
        self.failing_version_update()
        result = self.run_cli("auto-update", "run")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.state()["migrations"], 88)
        self.assertEqual(len(self.resets()), 1)
        calls = self.calls()

        def positions(match):
            return [index for index, call in enumerate(calls) if match(call)]

        ups = positions(lambda c: c[:2] == ["compose", "up"])
        stops = positions(lambda c: c[:2] == ["compose", "stop"] and "web" in c and "migrate" in c)
        reset = positions(lambda c: c[:2] == ["compose", "run"] and any("pg_restore" in a for a in c))
        self.assertEqual(len(ups), 2)
        self.assertTrue(stops, "Anwendung und migrate vor dem Zurücksetzen anhalten")
        self.assertLess(ups[0], stops[0])
        self.assertLess(stops[0], reset[0])
        self.assertLess(reset[0], ups[1], "erst Datenbank, dann alte Fassung")
        self.assertEqual(self.env("WACHBUCH_VERSION"), "0.25.0")
        self.assertEqual((self.dir / "compose.yml").read_text(encoding="utf-8"), "# alt\n")
        log = self.log()
        self.assertIn("zurückgesetzt", log)
        self.assertIn("Rollback erfolgreich", log)

    def test_failed_reset_keeps_new_version_instead_of_old_code(self):
        self.failing_version_update(reset_fails=True)
        result = self.run_cli("auto-update", "run")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.state()["migrations"], 94)
        self.assertEqual(self.env("WACHBUCH_VERSION"), "0.26.0")
        self.assertEqual((self.dir / "compose.yml").read_text(encoding="utf-8"), "# 0.26.0\n")
        log = self.log()
        self.assertIn("FEHLER", log)
        self.assertNotIn("Rollback erfolgreich", log)
        # Vorherige Images bleiben für einen Rollback von Hand erhalten.
        self.assertTrue(any(name.endswith("-wb-rollback") for name in self.state()["images"]))

    def test_failed_host_copy_aborts_instead_of_restoring_an_older_dump(self):
        # set -e greift in `if ! (cmd_backup)` nicht: Früher lief das Update
        # weiter, und der Rollback nahm die neueste *ältere* Kopie.
        self.failing_version_update(cp_fails=True)
        backups = self.dir / "backups"
        backups.mkdir()
        (backups / "rwsth-20261020T033000Z.dump").write_text("PGDMP migrations=70\n", encoding="utf-8")
        result = self.run_cli("auto-update", "run")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.resets(), [], "nie auf eine andere Kopie zurücksetzen")
        self.assertEqual(self.state()["migrations"], 88)
        self.assertFalse([c for c in self.compose_calls("up") if "--wait" in c], "neue Version nie gestartet")
        self.assertEqual(self.env("WACHBUCH_VERSION"), "0.25.0")
        self.assertEqual((self.dir / "compose.yml").read_text(encoding="utf-8"), "# alt\n")
        self.assertIn("Backup fehlgeschlagen", self.log())
        self.assertFalse(list(backups.glob("*.tmp")))
        # Die für das Backup angehaltene Anwendung läuft wieder wie vorher.
        self.assertEqual(self.state()["running"], self.images("0.25.0", self.OLD))

    def test_rollback_restores_the_dump_of_this_update_not_the_newest_name(self):
        self.failing_version_update()
        backups = self.dir / "backups"
        backups.mkdir()
        # Von Hand angelegt; sortiert hinter den Zeitstempel-Namen.
        (backups / "rwsth-vor-umzug.dump").write_text("PGDMP migrations=70\n", encoding="utf-8")
        result = self.run_cli("auto-update", "run")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.state()["restored"], "PGDMP migrations=88\n")
        self.assertEqual(self.state()["migrations"], 88)

    def test_rollback_keeps_a_dump_of_what_the_new_version_wrote(self):
        self.failing_version_update()
        result = self.run_cli("auto-update", "run")
        self.assertNotEqual(result.returncode, 0)
        calls = self.calls()
        dumps = [i for i, c in enumerate(calls) if c[:2] == ["compose", "exec"] and "once" in c]
        reset = [i for i, c in enumerate(calls) if c[:2] == ["compose", "run"] and any("pg_restore" in a for a in c)]
        self.assertEqual(len(dumps), 2, "vor dem Update und vor dem Zurücksetzen")
        self.assertLess(dumps[1], reset[0])
        saved = self.dir / "backups" / "rwsth-test-2.dump"
        self.assertEqual(saved.read_text(encoding="utf-8"), "PGDMP migrations=94\n")
        self.assertEqual(self.state()["restored"], "PGDMP migrations=88\n")
        self.assertIn("gesichert: backups/rwsth-test-2.dump", self.log())
        self.assertIn("Rollback erfolgreich", self.log())

    def assert_backup_after_pull_with_app_stopped(self):
        calls = self.calls()
        pull = calls.index(self.compose_calls("pull")[0])
        stops = [i for i, c in enumerate(calls) if c[:2] == ["compose", "stop"] and "web" in c]
        dump = next(i for i, c in enumerate(calls) if c[:2] == ["compose", "exec"] and "once" in c)
        up = calls.index(self.compose_calls("up")[0])
        self.assertTrue(stops, "Anwendung vor dem Backup anhalten")
        self.assertLess(pull, stops[0], "erst laden (kann dauern), dann anhalten")
        self.assertLess(stops[0], dump, "nach dem Backup schreibt niemand mehr")
        self.assertLess(dump, up)

    def test_manual_update_backs_up_after_pull_with_app_stopped(self):
        self.publish_release("0.26.0")
        self.set_state(images=self.images("0.25.0", self.OLD), remote=self.images("0.26.0", self.NEW))
        result = self.run_cli("-y", "update", "0.26.0")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assert_backup_after_pull_with_app_stopped()

    def test_auto_update_backs_up_with_app_stopped(self):
        self.write_env(WACHBUCH_VERSION="0.25.0", WACHBUCH_AUTO_UPDATE="sicherheit")
        self.set_state(images=self.images("0.25.0", self.OLD), remote=self.images("0.25.0", self.NEW))
        result = self.run_cli("auto-update", "run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_backup_after_pull_with_app_stopped()

    def fail_awk_for_value(self, value):
        """awk scheitert wie auf voller Platte, wenn env_set VALUE schreibt."""
        awk = self.bin / "awk"
        awk.write_text(f'#!/bin/sh\nif [ "${{V:-}}" = "{value}" ]; then\n'
                       '    echo "awk: write failure (No space left on device)" >&2; exit 2\nfi\n'
                       f'exec {shutil.which("awk")} "$@"\n', encoding="utf-8")
        awk.chmod(0o755)

    def test_failed_env_write_in_rollback_keeps_env_and_starts_nothing(self):
        self.failing_version_update()
        self.fail_awk_for_value("0.25.0")
        result = self.run_cli("auto-update", "run")
        self.assertNotEqual(result.returncode, 0)
        env = (self.dir / ".env").read_text(encoding="utf-8")
        self.assertIn("POSTGRES_DB=rwsth\n", env, "Geheimnisse in .env bleiben")
        self.assertEqual(self.env("WACHBUCH_VERSION"), "0.26.0")
        self.assertFalse(list(self.dir.glob(".env.tmp.*")))
        log = self.log()
        self.assertIn("nicht zurückgesetzt", log)
        self.assertNotIn("Rollback erfolgreich", log)
        self.assertEqual(len([c for c in self.compose_calls("up") if "--wait" in c]), 1, "kein Start im Mischstand")

    def test_failed_file_restore_keeps_rollback_copies(self):
        self.failing_version_update()
        # cp auf voller Platte: Ziel schon gekürzt, dann Fehler.
        cp = self.bin / "cp"
        cp.write_text('#!/bin/sh\nfor last; do :; done\ncase "$*" in\n'
                      '    "-p logs/rollback/compose.yml "*) : >"$last"; echo "cp: No space left on device" >&2; exit 1 ;;\n'
                      f'esac\nexec {shutil.which("cp")} "$@"\n', encoding="utf-8")
        cp.chmod(0o755)
        result = self.run_cli("auto-update", "run")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.dir / "compose.yml").read_text(encoding="utf-8"), "# 0.26.0\n")
        self.assertEqual((self.dir / "logs" / "rollback" / "compose.yml").read_text(encoding="utf-8"), "# alt\n")
        self.assertEqual(self.env("WACHBUCH_VERSION"), "0.26.0", "Version passt weiter zu den Dateien")
        self.assertNotIn("Rollback erfolgreich", self.log())
        self.assertEqual(len([c for c in self.compose_calls("up") if "--wait" in c]), 1)

    def test_unreadable_migration_state_aborts_version_update(self):
        self.write_env(WACHBUCH_VERSION="0.25.0", WACHBUCH_AUTO_UPDATE="alle")
        self.publish_release("0.26.0")
        self.set_state(images=self.images("0.25.0", self.OLD), remote=self.images("0.26.0", self.NEW),
                       migrations="")
        result = self.run_cli("auto-update", "run")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.compose_calls("up"))
        self.assertEqual(self.env("WACHBUCH_VERSION"), "0.25.0")
        self.assertEqual((self.dir / "compose.yml").read_text(encoding="utf-8"), "# alt\n")

    def test_missing_current_images_block_unprotected_update(self):
        self.write_env(WACHBUCH_VERSION="0.25.0", WACHBUCH_AUTO_UPDATE="sicherheit")
        self.set_state(images={}, remote=self.images("0.25.0", self.NEW))
        result = self.run_cli("auto-update", "run")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.compose_calls("pull"))
        self.assertIn("fehlen lokal", self.log())

    # --- Aufräumen und Caddy ------------------------------------------------------
    def test_version_update_prunes_old_images_and_old_host_dumps(self):
        self.write_env(WACHBUCH_VERSION="0.25.0", WACHBUCH_AUTO_UPDATE="alle")
        self.publish_release("0.26.0")
        self.set_state(images=self.images("0.25.0", self.OLD), remote=self.images("0.26.0", self.NEW))
        backups = self.dir / "backups"
        backups.mkdir()
        old_dump, note = backups / "rwsth-20260901T000000Z.dump", backups / "notiz.txt"
        for path in (old_dump, note):
            path.write_text("x", encoding="utf-8")
            os.utime(path, (1, 1))
        result = self.run_cli("auto-update", "run")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(self.state()["images"], self.images("0.26.0", self.NEW), "0.25.0-Images entfernt")
        prune = [c for c in self.calls() if c[:2] == ["image", "prune"]]
        self.assertTrue(any("-af" in c and any("org.opencontainers.image.source=" in a for a in c) for c in prune))
        self.assertFalse(old_dump.exists())
        self.assertTrue((backups / "rwsth-test.dump").exists(), "frisches Backup bleibt")
        self.assertTrue(note.exists(), "fremde Dateien bleiben")

    def test_retention_zero_keeps_host_dumps(self):
        self.write_env(WACHBUCH_VERSION="0.25.0", WACHBUCH_AUTO_UPDATE="sicherheit", BACKUP_RETENTION_DAYS="0")
        self.set_state(images=self.images("0.25.0", self.OLD), remote=self.images("0.25.0", self.NEW))
        (self.dir / "backups").mkdir()
        old_dump = self.dir / "backups" / "rwsth-20260901T000000Z.dump"
        old_dump.write_text("x", encoding="utf-8")
        os.utime(old_dump, (1, 1))
        result = self.run_cli("auto-update", "run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(old_dump.exists())

    def caddy_recreates(self):
        return [c for c in self.compose_calls("up") if c[-1] == "caddy" and "--force-recreate" in c]

    def test_changed_caddyfile_recreates_caddy(self):
        self.write_env(WACHBUCH_VERSION="0.25.0", WACHBUCH_AUTO_UPDATE="alle")
        self.publish_release("0.26.0")
        self.set_state(images=self.images("0.25.0", self.OLD), remote=self.images("0.26.0", self.NEW),
                       caddy_config="# alt\n")
        result = self.run_cli("auto-update", "run")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(len(self.caddy_recreates()), 1)
        self.assertEqual(self.state()["caddy_config"], "# 0.26.0\n")

    def test_stale_caddy_is_recreated_even_without_new_images(self):
        # Update mit einer älteren CLI: Datei neu, Caddy läuft noch mit der alten.
        self.write_env(WACHBUCH_VERSION="0.25.0", WACHBUCH_AUTO_UPDATE="sicherheit")
        self.set_state(images=self.images("0.25.0", self.OLD), remote=self.images("0.25.0", self.OLD),
                       caddy_config="# noch aelter\n")
        result = self.run_cli("auto-update", "run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.caddy_recreates()), 1)
        self.assertIn("aktuell", self.log())

    def test_unchanged_caddyfile_leaves_caddy_alone(self):
        self.write_env(WACHBUCH_VERSION="0.25.0", WACHBUCH_AUTO_UPDATE="sicherheit")
        self.set_state(images=self.images("0.25.0", self.OLD), remote=self.images("0.25.0", self.NEW))
        result = self.run_cli("auto-update", "run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.caddy_recreates(), [])

    # --- wachbuch update (von Hand) --------------------------------------------
    def test_manual_update_with_failed_pull_changes_nothing(self):
        self.publish_release("0.26.0")
        self.set_state(images=self.images("0.25.0", self.OLD), remote=self.images("0.26.0", self.NEW),
                       pull_fails=True)
        result = self.run_cli("-y", "update", "0.26.0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("nicht ladbar", result.stderr)
        self.assertEqual(self.env("WACHBUCH_VERSION"), "0.25.0")
        self.assertEqual((self.dir / "compose.yml").read_text(encoding="utf-8"), "# alt\n")
        self.assertEqual((self.dir / "deploy" / "caddy" / "Caddyfile").read_text(encoding="utf-8"), "# alt\n")
        self.assertFalse(self.compose_calls("up"))
        self.assertFalse(list(self.dir.rglob("*.download.*")))

    def test_manual_update_with_failed_start_rolls_back(self):
        self.publish_release("0.26.0")
        self.set_state(images=self.images("0.25.0", self.OLD), remote=self.images("0.26.0", self.NEW),
                       fail_up_ids=[self.NEW["app"]], migrations=88, up_migrations={self.NEW["app"]: 94})
        result = self.run_cli("-y", "update", "0.26.0")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.env("WACHBUCH_VERSION"), "0.25.0")
        self.assertEqual((self.dir / "compose.yml").read_text(encoding="utf-8"), "# alt\n")
        self.assertEqual(self.state()["migrations"], 88)
        self.assertEqual(len(self.compose_calls("up")), 2)
        self.assertIn("Rollback erfolgreich", result.stdout)

    def test_manual_update_success_cleans_up(self):
        self.publish_release("0.26.0")
        self.set_state(images=self.images("0.25.0", self.OLD), remote=self.images("0.26.0", self.NEW))
        result = self.run_cli("-y", "update", "0.26.0")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(self.env("WACHBUCH_VERSION"), "0.26.0")
        self.assertEqual(self.state()["images"], self.images("0.26.0", self.NEW))
        self.assertFalse((self.dir / "logs" / "rollback").exists())

    def test_downgrade_needs_confirmation(self):
        self.write_env(WACHBUCH_VERSION="0.26.0")
        self.publish_release("0.25.0")
        self.set_state(images=self.images("0.26.0", self.NEW), remote=self.images("0.25.0", self.OLD))
        result = self.run_cli("update", "0.25.0")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.compose_calls("pull"))
        self.assertEqual(self.env("WACHBUCH_VERSION"), "0.26.0")

    def test_build_mode_rollback_restores_build_override(self):
        # Sonst bliebe das neue compose.build.yml (housekeeping: *app-build)
        # neben dem alten compose.yml: ein Dienst ohne Befehl und Umgebung.
        self.write_env(WACHBUCH_VERSION="0.25.0", COMPOSE_FILE="compose.yml:compose.build.yml")
        (self.dir / "compose.build.yml").write_text("# alt build\n", encoding="utf-8")
        self.publish_release("0.26.0")
        (self.remote / "v0.26.0" / "compose.build.yml").write_text("# 0.26.0 build\n", encoding="utf-8")
        self.set_state(images=self.images("0.25.0", self.OLD), build_fails=True)
        result = self.run_cli("-y", "update", "0.26.0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Bauen fehlgeschlagen", result.stderr)
        self.assertEqual((self.dir / "compose.build.yml").read_text(encoding="utf-8"), "# alt build\n")
        self.assertEqual((self.dir / "compose.yml").read_text(encoding="utf-8"), "# alt\n")
        self.assertEqual(self.env("WACHBUCH_VERSION"), "0.25.0")

    def test_restore_from_volume_keeps_an_old_chosen_dump(self):
        # Das Sicherheits-Backup dünnt das Volume nicht aus: Der gewählte Dump
        # ist älter als BACKUP_RETENTION_DAYS (Standard 7).
        chosen = "rwsth-20261021T013000Z.dump"
        self.set_state(images=self.images("0.25.0", self.OLD), migrations=94,
                       volume={chosen: {"migrations": 88, "age_days": 8}})
        result = self.run_cli("-y", "restore", chosen)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("Wiederherstellung abgeschlossen", result.stdout)
        self.assertEqual(self.state()["migrations"], 88)
        self.assertIn(chosen, self.state()["volume"])
        self.assertEqual((self.dir / "backups" / "rwsth-test.dump").read_text(encoding="utf-8"),
                         "PGDMP migrations=94\n", "Sicherheits-Backup des Stands davor")

    def test_uninstall_covers_every_compose_profile(self):
        # Mit --profile ersetzt Compose COMPOSE_PROFILES; Dienste fehlender
        # Profile (demo-cleaner, signal) blieben sonst samt Netz und Volume.
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        profiles = set(re.findall(r'^    profiles: \["([a-z-]+)"\]$', compose, flags=re.M))
        self.assertTrue({"ops", "https", "demo", "signal"} <= profiles, profiles)
        self.write_env(WACHBUCH_VERSION="0.26.0", COMPOSE_PROFILES="https,demo")
        for args in (("uninstall",), ("uninstall", "--purge")):
            with self.subTest(args=args):
                result = self.run_cli("-y", *args)
                self.assertEqual(result.returncode, 0, result.stderr)
                down = [c for c in self.calls() if c[:1] == ["compose"] and "down" in c][-1]
                used = {down[i + 1] for i, arg in enumerate(down[:-1]) if arg == "--profile"}
                self.assertEqual(used, profiles)
                self.assertEqual("--volumes" in down, "--purge" in args)

    def test_public_demo_refuses_versions_without_sandbox(self):
        self.write_env(WACHBUCH_VERSION="0.26.0", DEMO_MODE="true", DEMO_SANDBOX="true")
        self.set_state(images=self.images("0.26.0", self.NEW), remote=self.images("0.26.0", self.NEW))
        for version in ("0.25.0", "latest"):
            with self.subTest(version=version):
                result = self.run_cli("-y", "update", version)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("0.26.0", result.stderr)
        self.assertFalse(self.compose_calls("pull"))
        self.assertEqual(self.env("WACHBUCH_VERSION"), "0.26.0")

    def test_setup_code_hidden_after_setup(self):
        self.write_env(WACHBUCH_VERSION="0.25.0", SETUP_BOOTSTRAP_TOKEN="ABCD-EFGH")
        self.assertIn("ABCD-EFGH", self.run_cli("setup-code").stdout)
        self.set_state(images=self.images("0.25.0", self.OLD), setup_completed=True)
        result = self.run_cli("setup-code")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("ABCD-EFGH", result.stdout)
        self.assertIn("abgeschlossen", result.stdout)

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


class InstallDemoOptionTests(SimpleTestCase):
    """install.sh --demo schreibt die Schalter der öffentlichen Demo in .env."""

    FAKE_DOCKER = """#!/bin/sh
case "$*" in
    *Architecture*) echo x86_64 ;;
    *MemTotal*) echo 4294967296 ;;
    "compose version --short") echo 2.29.0 ;;
    *Server.Version*) echo 27.0.0 ;;
esac
exit 0
"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        docker = self.bin / "docker"
        docker.write_text(self.FAKE_DOCKER, encoding="utf-8")
        docker.chmod(0o755)
        self.dir = self.tmp / "wachwerk"

    def install(self, *args):
        environment = {
            "PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', os.defpath)}",
            "HOME": str(self.tmp),
        }
        return subprocess.run(
            ["sh", str(ROOT / "install.sh"), "--yes", "--no-start", "--source", str(ROOT),
             "--dir", str(self.dir), "--name", "Demo", *args],
            capture_output=True, text=True, env=environment, timeout=60, check=False,
        )

    def env(self):
        values = {}
        for line in (self.dir / ".env").read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                values[key] = value
        return values

    DEMO = ("--mode", "domain", "--domain", "demo.example.org", "--email", "ops@example.org", "--demo")

    def test_demo_sets_sandbox_profile_and_mfa(self):
        result = self.install(*self.DEMO, "--version", "0.26.0")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        env = self.env()
        self.assertEqual(env["DEMO_MODE"], "true")
        self.assertEqual(env["DEMO_SANDBOX"], "true")
        self.assertEqual(env["MFA_REQUIRED"], "true")
        self.assertEqual(env["COMPOSE_PROFILES"], "https,demo")
        self.assertEqual(env["TRUSTED_PROXY"], "true")
        self.assertEqual(env["ALLOWED_HOSTS"], "demo.example.org,localhost,127.0.0.1")
        # Nie das veröffentlichte Standardpasswort der gemeinsamen Demo-Konten.
        self.assertRegex(env["DEMO_PASSWORD"], r"^[0-9a-f]{64}$")

    def test_rerun_with_new_mode_keeps_demo_profile(self):
        self.install(*self.DEMO, "--version", "0.26.0")
        result = self.install("--mode", "domain", "--domain", "neu.example.org", "--email", "ops@example.org")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(self.env()["COMPOSE_PROFILES"], "https,demo")

    def test_demo_refuses_releases_without_sandbox(self):
        # 0.25.0 legt mit DEMO_MODE gemeinsame Konten mit öffentlichem Passwort an;
        # "latest" (z. B. nach gescheiterter GitHub-Abfrage) ist das letzte Release.
        for args in (("--version", "0.25.0"), ("--version", "v0.9.9"), ()):
            with self.subTest(args=args):
                result = self.install(*self.DEMO, *args)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("0.26.0", result.stderr)
                self.assertFalse((self.dir / ".env").exists())

    def test_rerun_on_demo_install_refuses_old_version(self):
        self.install(*self.DEMO, "--version", "0.26.0")
        result = self.install("--version", "0.25.0")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.env()["WACHBUCH_VERSION"], "0.26.0")

    def test_demo_with_local_build_needs_no_version(self):
        result = self.install(*self.DEMO, "--build")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(self.env()["DEMO_SANDBOX"], "true")

    def test_rerun_with_new_address_keeps_extra_profiles(self):
        self.install("--mode", "domain", "--domain", "a.example.org", "--email", "ops@example.org")
        env_file = self.dir / ".env"
        env_file.write_text(env_file.read_text(encoding="utf-8").replace(
            "COMPOSE_PROFILES=https\n", "COMPOSE_PROFILES=https,signal\n"), encoding="utf-8")
        self.assertEqual(self.env()["COMPOSE_PROFILES"], "https,signal")
        result = self.install("--mode", "domain", "--domain", "b.example.org", "--email", "ops@example.org")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(self.env()["COMPOSE_PROFILES"], "https,signal")
        self.install("--mode", "local")
        self.assertEqual(self.env()["COMPOSE_PROFILES"], "signal")
        self.install("--mode", "domain", "--domain", "b.example.org", "--email", "ops@example.org")
        self.assertEqual(self.env()["COMPOSE_PROFILES"], "https,signal")

    def test_without_demo_no_sandbox(self):
        result = self.install("--mode", "domain", "--domain", "wache.example.org", "--email", "ops@example.org")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        env = self.env()
        self.assertEqual(env["DEMO_MODE"], "false")
        self.assertNotIn("DEMO_SANDBOX", env)
        self.assertEqual(env["COMPOSE_PROFILES"], "https")


class MigrateScriptDemoTests(SimpleTestCase):
    """scripts/migrate.sh: öffentliche Demo sperrt gemeinsame Demo-Konten statt sie anzulegen."""

    def run_migrate(self, **env):
        with tempfile.TemporaryDirectory() as tmp:
            python = Path(tmp) / "python"
            python.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >>"$CALLS"\n', encoding="utf-8")
            python.chmod(0o755)
            calls = Path(tmp) / "calls"
            environment = {"PATH": f"{tmp}{os.pathsep}{os.environ.get('PATH', os.defpath)}",
                           "CALLS": str(calls), **env}
            result = subprocess.run(["sh", str(ROOT / "scripts" / "migrate.sh")], env=environment,
                                    capture_output=True, text=True, timeout=30, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            return calls.read_text(encoding="utf-8").splitlines()

    def test_sandbox_disables_shared_accounts(self):
        calls = self.run_migrate(DEMO_MODE="true", DEMO_SANDBOX="true")
        self.assertIn("manage.py disable_shared_demo_accounts", calls)
        self.assertNotIn("manage.py load_demo_data", calls)

    def test_local_demo_loads_sample_data(self):
        calls = self.run_migrate(DEMO_MODE="true")
        self.assertIn("manage.py load_demo_data", calls)
        self.assertNotIn("manage.py disable_shared_demo_accounts", calls)

    def test_production_runs_neither(self):
        calls = self.run_migrate(DEMO_MODE="false", DEMO_SANDBOX="false")
        self.assertEqual(calls[0], "manage.py migrate --noinput")
        self.assertFalse([c for c in calls if "demo" in c])


class DisableSharedDemoAccountsTests(TestCase):
    """Konten einer früheren gemeinsamen Demo dürfen sich in der öffentlichen Demo nicht anmelden."""

    PASSWORD = "Demo-Passwort-12345"

    def setUp(self):
        from core.models import Membership, Station, User

        station = Station.get_default()
        self.legacy = User.objects.create_user("demo-admin", password=self.PASSWORD)
        Membership.objects.create(user=self.legacy, station=station, role=Membership.Role.ADMIN, is_active=True)
        self.sandbox_user = User.objects.create_user("demo-a1b2c3d4-admin", password=self.PASSWORD)
        self.operator = User.objects.create_user("betreiber", password=self.PASSWORD)

    def login(self, username):
        self.client.post("/anmelden/", {"username": username, "password": self.PASSWORD})
        logged_in = "_auth_user_id" in self.client.session
        self.client.logout()
        return logged_in

    def test_shared_accounts_are_locked_and_others_untouched(self):
        self.assertTrue(self.login("demo-admin"))
        with self.settings(DEMO_MODE=True, DEMO_SANDBOX=True):
            call_command("disable_shared_demo_accounts", stdout=io.StringIO())
            self.assertFalse(self.login("demo-admin"))
        self.legacy.refresh_from_db()
        self.assertFalse(self.legacy.is_active)
        self.assertFalse(self.legacy.has_usable_password())
        self.assertTrue(self.legacy.station_memberships.exists(), "Daten bleiben")
        for user in (self.sandbox_user, self.operator):
            user.refresh_from_db()
            self.assertTrue(user.is_active)
            self.assertTrue(user.check_password(self.PASSWORD))
        out = io.StringIO()
        call_command("disable_shared_demo_accounts", stdout=out)
        self.assertEqual(out.getvalue(), "", "zweiter Lauf ändert nichts")

    def test_open_session_of_shared_account_ends(self):
        self.client.force_login(self.legacy)
        call_command("disable_shared_demo_accounts", stdout=io.StringIO())
        response = self.client.get("/einstellungen/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/anmelden/", response["Location"])

    def test_load_demo_data_refuses_in_public_demo(self):
        from core.models import User

        with self.settings(DEMO_MODE=True, DEMO_SANDBOX=True), self.assertRaises(CommandError):
            call_command("load_demo_data", stdout=io.StringIO())
        self.assertFalse(User.objects.filter(username="demo-schicht").exists())
