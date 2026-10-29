"""Host-Skripte für den Internetbetrieb (deploy/hetzner, scripts/backup-loop.sh).

Die Skripte laufen gegen Attrappen (docker, curl, openssl, ssh, rsync, sshd,
sudo, passwd, pg_dump) in einem Temp-Ordner; das System bleibt unberührt.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import fnmatch
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[1]
HETZNER = ROOT / "deploy" / "hetzner"
HEALTH = HETZNER / "wachwerk-health.sh"
HARDEN = HETZNER / "harden-host.sh"
OFFSITE_SYNC = HETZNER / "wachwerk-offsite-sync.sh"
BACKUP_LOOP = ROOT / "scripts" / "backup-loop.sh"
WACHBUCH = ROOT / "scripts" / "wachbuch"
PING = "https://hc-ping.example/uuid"
# Die Skripte zielen auf Debian/Ubuntu (GNU date/find/stat, coreutils timeout).
linux_only = unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("timeout"),
                                 "nur unter Linux mit GNU-Werkzeugen")

FAKE_DOCKER = r'''
import json, os, sys, time
state_path = os.environ["FAKE_STATE"]
with open(state_path, encoding="utf-8") as handle:
    state = json.load(handle)
args = sys.argv[1:]
with open(state_path + ".docker", "a", encoding="utf-8") as log:
    log.write(json.dumps(args) + "\n")
command = args[0] if args else ""
if state.get("hang") == command:
    time.sleep(3600)
if command == "ps":
    print("\n".join(c["id"] for c in state["containers"]))
elif command == "inspect":
    known = {c["id"]: c for c in state["containers"]}
    for cid in args[1:]:
        if cid in known:
            c = known[cid]
            print(c["service"], c.get("restart", "unless-stopped"), c.get("status", "running"),
                  c.get("health", "-"), cid)
elif command == "volume":
    print(state["backups_dir"])
elif command == "exec":
    print(state.get("errors", "0"))
elif command == "compose":
    print(state.get("compose_output", "Restore-Test erfolgreich: /backups/rwsth-x.dump"))
    sys.exit(state.get("compose_rc", 0))
'''

FAKE_CURL = r'''
import json, os, sys
state_path = os.environ["FAKE_STATE"]
with open(state_path, encoding="utf-8") as handle:
    state = json.load(handle)
args = sys.argv[1:]
body = sys.stdin.read() if "@-" in args else ""
with open(state_path + ".curl", "a", encoding="utf-8") as log:
    log.write(json.dumps({"url": args[-1], "body": body}) + "\n")
if "/healthz/" in args[-1]:
    sys.exit(state.get("healthz_rc", 0))
'''

FAKE_OPENSSL = r'''
import datetime, sys
if sys.argv[1:2] == ["x509"]:
    sys.stdin.read()
    end = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=60)
    print("notAfter=" + end.strftime("%b %d %H:%M:%S %Y GMT"))
'''


def write_stub(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
    path.chmod(0o755)


def write_sh_stub(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def set_age(path: Path, seconds: float) -> None:
    stamp = time.time() - seconds
    os.utime(path, (stamp, stamp))


def log_stamp(delta: timedelta = timedelta()) -> str:
    return (datetime.now() - delta).strftime("%Y-%m-%d %H:%M:%S")


SERVICES = [
    ("db", "healthy"), ("redis", "healthy"), ("web", "healthy"), ("feed-worker", "healthy"),
    ("notify-worker", "healthy"), ("push-worker", "healthy"), ("housekeeping", "healthy"), ("backup", "-"), ("caddy", "-"),
    ("demo-cleaner", "-"),
]


class HealthSandbox:
    """Ein installierter Demo-Server mit gesunden Diensten (alles per Attrappe)."""

    def __init__(self, test: SimpleTestCase):
        tmp = tempfile.TemporaryDirectory(prefix="wachwerk-health-")
        test.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.bin = self.root / "bin"
        self.conf = self.root / "etc"
        self.state_dir = self.root / "state"
        self.dir = self.root / "opt" / "wachbuch"
        self.backups = self.root / "backups"
        for path in (self.bin, self.conf, self.dir / "logs", self.backups):
            path.mkdir(parents=True)
        write_stub(self.bin, "docker", FAKE_DOCKER)
        write_stub(self.bin, "curl", FAKE_CURL)
        write_stub(self.bin, "openssl", FAKE_OPENSSL)
        (self.dir / ".env").write_text(
            "WACHBUCH_HOSTNAME=demo.example.org\nCOMPOSE_PROFILES=https,demo\n"
            "DEMO_SANDBOX=true\nWACHBUCH_AUTO_UPDATE=sicherheit\nWACHBUCH_VERSION=0.26.0\n",
            encoding="utf-8",
        )
        self.write_update_log(f"{log_stamp(timedelta(hours=3))} Alles aktuell (Version 0.26.0).")
        (self.backups / "rwsth-20261029T000000Z.dump").write_bytes(b"PGDMP")
        self.settings = {"WACHWERK_DIR": str(self.dir), "PING_URL": PING,
                         "DISK_MAX_PERCENT": "100", "FAILS_BEFORE_ALERT": "1"}
        self.state = {
            "backups_dir": str(self.backups),
            "containers": [
                {"id": f"id-{name}", "service": name, "health": health} for name, health in SERVICES
            ] + [
                {"id": "id-migrate", "service": "migrate", "restart": "no", "status": "exited"},
                {"id": "id-backup-init", "service": "backup-init", "restart": "no", "status": "exited"},
            ],
        }
        self.state_path = self.root / "fake-state.json"

    def container(self, service: str) -> dict:
        return next(c for c in self.state["containers"] if c["service"] == service)

    def write_update_log(self, *lines: str) -> None:
        (self.dir / "logs" / "auto-update.log").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def run(self, *args: str, env: dict | None = None, timeout: int = 60):
        self.state_path.write_text(json.dumps(self.state), encoding="utf-8")
        (self.conf / "health.env").write_text(
            "".join(f"{key}={value}\n" for key, value in self.settings.items()), encoding="utf-8"
        )
        # Wie nach sudo: keine PING_URL & Co. in der Umgebung.
        base = {
            "PATH": f"{self.bin}:/usr/bin:/bin", "HOME": str(self.root), "LC_ALL": "C.UTF-8",
            "WACHWERK_CONF_DIR": str(self.conf), "WACHWERK_STATE_DIR": str(self.state_dir),
            "FAKE_STATE": str(self.state_path),
        }
        base.update(env or {})
        return subprocess.run(["sh", str(HEALTH), *args], env=base, capture_output=True,
                              text=True, timeout=timeout)

    def calls(self, suffix: str) -> list:
        path = Path(f"{self.state_path}.{suffix}")
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def pings(self) -> list:
        return [call for call in self.calls("curl") if "/healthz/" not in call["url"]]

    def reset_calls(self) -> None:
        for suffix in ("curl", "docker"):
            Path(f"{self.state_path}.{suffix}").unlink(missing_ok=True)


@linux_only
class HealthCheckTests(SimpleTestCase):
    def setUp(self):
        self.box = HealthSandbox(self)

    def assert_alert(self, result, text):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(text, result.stderr)
        fails = [p for p in self.box.pings() if p["url"] == PING + "/fail"]
        self.assertEqual(len(fails), 1, self.box.pings())
        self.assertIn(text, fails[0]["body"])

    def test_healthy_server_sends_success_ping(self):
        result = self.box.run("--verbose")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("FEHLER", result.stdout + result.stderr)
        self.assertEqual([p["url"] for p in self.box.pings()], [PING])

    def test_not_installed_sends_nothing(self):
        (self.box.dir / ".env").unlink()
        result = self.box.run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.box.calls("curl"), [])
        self.assertEqual(self.box.calls("docker"), [])

    def test_test_flag_uses_ping_url_from_settings_file(self):
        result = self.box.run("--test")
        self.assert_alert(result, "Testmeldung")
        self.assertIn("gesendet", result.stdout)

    def test_environment_wins_over_settings_file(self):
        self.box.run("--test", env={"PING_URL": "https://other.example/x"})
        self.assertEqual([p["url"] for p in self.box.pings()], ["https://other.example/x/fail"])

    def test_every_long_running_service_is_checked(self):
        self.box.container("feed-worker").update(status="exited", health="-")
        self.box.state["containers"] = [c for c in self.box.state["containers"] if c["service"] != "redis"]
        result = self.box.run()
        self.assert_alert(result, "Dienst feed-worker: exited")
        self.assertIn("Dienst redis fehlt", result.stderr)

    def test_alert_only_after_consecutive_failures(self):
        del self.box.settings["FAILS_BEFORE_ALERT"]  # Standard: 2
        self.box.state["healthz_rc"] = 22
        first = self.box.run()
        self.assertEqual(first.returncode, 1)
        self.assertEqual(self.box.pings(), [])
        self.box.state["healthz_rc"] = 0
        self.assertEqual(self.box.run().returncode, 0)
        self.assertEqual([p["url"] for p in self.box.pings()], [PING])
        self.box.reset_calls()
        self.box.state["healthz_rc"] = 22
        self.box.run()
        self.assertEqual(self.box.pings(), [], "Zähler muss nach Erfolg zurückgesetzt sein")
        self.assert_alert(self.box.run(), "antwortet nicht mit 200")

    def test_running_auto_update_pauses_service_checks(self):
        lock = self.box.dir / "logs" / "auto-update.lock"
        lock.mkdir()
        self.box.write_update_log(f"{log_stamp()} Neustart mit Version 0.26.0")
        self.box.state["healthz_rc"] = 22
        self.box.container("web").update(status="exited", health="-")
        result = self.box.run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([p["url"] for p in self.box.pings()], [PING])
        self.assertNotIn("ps", [call[0] for call in self.box.calls("docker")])

    def test_stale_auto_update_lock_is_reported(self):
        lock = self.box.dir / "logs" / "auto-update.lock"
        lock.mkdir()
        set_age(lock, 2 * 3600)
        self.assert_alert(self.box.run(), "Sperre des automatischen Updates")

    def test_failed_auto_update_is_reported(self):
        self.box.write_update_log(
            f"{log_stamp()} Start fehlgeschlagen – Rollback auf den vorherigen Stand.",
            " Container rettungswache-wachbuch-web-1  Error",
            f"{log_stamp()} Rollback erfolgreich; es läuft wieder Version 0.26.0.",
        )
        self.assert_alert(self.box.run(), "Rollback erfolgreich")

    def test_missing_auto_update_runs_are_reported(self):
        self.box.write_update_log(f"{log_stamp(timedelta(days=3))} Alles aktuell (Version 0.26.0).")
        self.assert_alert(self.box.run(), "automatisches Update lief zuletzt vor")

    def test_auto_update_messages_of_wachbuch_are_classified(self):
        """Vertrag mit scripts/wachbuch: jede auto_log-Meldung richtig einordnen."""
        text = WACHBUCH.read_text(encoding="utf-8")
        messages = [re.sub(r"\$\{[^}]*\}|\$[A-Za-z_][A-Za-z0-9_]*", "0.26.0", m)
                    for m in re.findall(r'(?:auto_log|note) "((?:[^"\\]|\\.)*)"', text)]
        healthy = ("Update erfolgreich", "Alles aktuell", "Übersprungen", "Neue Hauptversion")
        self.assertTrue(any(m.startswith("Update erfolgreich") for m in messages), messages)
        self.assertTrue(any(m.startswith("Alles aktuell") for m in messages), messages)
        self.assertTrue(any("Rollback" in m for m in messages), messages)
        for message in messages:
            with self.subTest(message=message):
                self.box.write_update_log(f"{log_stamp()} {message}")
                result = self.box.run("--verbose")
                lines = [line for line in (result.stdout + result.stderr).splitlines()
                         if "automatisches Update (" in line]
                self.assertEqual(len(lines), 1, result.stdout + result.stderr)
                expected = "OK" if message.startswith(healthy) else "FEHLER"
                self.assertTrue(lines[0].startswith(expected), lines[0])

    def test_unhealthy_app_container_is_restarted(self):
        self.box.container("notify-worker")["health"] = "unhealthy"
        result = self.box.run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(["restart", "-t", "30", "id-notify-worker"], self.box.calls("docker"))
        pings = self.box.pings()
        self.assertEqual([p["url"] for p in pings], [PING])
        self.assertIn("notify-worker war unhealthy", pings[0]["body"])

    def test_restarts_are_limited_per_hour(self):
        self.box.container("web")["health"] = "unhealthy"
        self.box.state_dir.mkdir()
        now = int(time.time())
        (self.box.state_dir / "restarts").write_text(
            "".join(f"{now - 600 * i} web\n" for i in range(3)) + f"{now - 7200} web\n", encoding="utf-8"
        )
        result = self.box.run()
        self.assert_alert(result, "Dienst web bleibt unhealthy, schon 3 Neustarts")
        self.assertNotIn("restart", [call[0] for call in self.box.calls("docker")])
        self.assertEqual(len((self.box.state_dir / "restarts").read_text().splitlines()), 3)

    def test_database_and_disabled_restart_only_alert(self):
        self.box.container("db")["health"] = "unhealthy"
        self.assert_alert(self.box.run(), "Dienst db ist unhealthy")
        self.box.reset_calls()
        self.box.container("db")["health"] = "healthy"
        self.box.container("web")["health"] = "unhealthy"
        self.box.settings["AUTO_RESTART"] = "false"
        self.assert_alert(self.box.run(), "Dienst web ist unhealthy")
        self.assertNotIn("restart", [call[0] for call in self.box.calls("docker")])

    def test_server_errors_are_reported(self):
        self.box.state["errors"] = "7"
        self.assert_alert(self.box.run(), "7 Serverfehler (5xx)")

    def test_offsite_needs_a_fresh_encrypted_copy(self):
        offsite = self.box.root / "offsite"
        offsite.mkdir()
        old = offsite / "rwsth-20261024T000000Z.dump.gpg"
        old.write_bytes(b"x")
        set_age(old, 5 * 86400)
        (self.box.conf / "offsite.env").write_text(f"OFFSITE_DIR={offsite}\n", encoding="utf-8")
        self.box.state_dir.mkdir()
        (self.box.state_dir / "offsite-sync.ok").touch()
        self.assert_alert(self.box.run(), "neueste verschlüsselte Kopie ist 120 Stunden alt")

    def test_hanging_docker_does_not_stall_the_check(self):
        self.box.state["hang"] = "ps"
        started = time.monotonic()
        result = self.box.run(env={"HEALTH_CMD_TIMEOUT": "2"}, timeout=40)
        self.assertLess(time.monotonic() - started, 30)
        self.assertIn("keine Container", result.stderr)

    def test_restore_test_result_is_monitored(self):
        result = self.box.run("--restore-test")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(["compose", "run", "--rm", "-T", "restore-test"], self.box.calls("docker"))
        self.assertEqual(self.box.run().returncode, 0)
        self.box.state.update(compose_rc=1, compose_output="Kein Wachbuch-Backup fuer den Restore-Test gefunden.")
        self.assertEqual(self.box.run("--restore-test").returncode, 1)
        self.box.reset_calls()
        self.box.state["compose_rc"] = 0
        self.assert_alert(self.box.run(), "Wiederherstellungsprobe fehlgeschlagen: Kein Wachbuch-Backup")
        (self.box.state_dir / "restore-test.status").write_text("ok\n", encoding="utf-8")
        set_age(self.box.state_dir / "restore-test.status", 9 * 86400)
        self.box.reset_calls()
        self.assert_alert(self.box.run(), "letzte Wiederherstellungsprobe vor 9 Tagen")


@linux_only
class HardenHostTests(SimpleTestCase):
    """Die Aussperr-Schutzfunktionen von harden-host.sh einzeln (Bibliotheksmodus)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="wachwerk-harden-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()

    def call(self, snippet: str, env: dict | None = None, **kwargs):
        base = {"PATH": f"{self.bin}:/usr/bin:/bin", "HOME": str(self.root), "LC_ALL": "C",
                "WACHWERK_HARDEN_LIB": "1", "HARDEN": str(HARDEN)}
        base.update(env or {})
        return subprocess.run(["sh", "-c", f'. "$HARDEN"; {snippet}'], env=base,
                              capture_output=True, text=True, timeout=30, **kwargs)

    def test_library_mode_runs_nothing(self):
        result = self.call("echo geladen")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "geladen")

    def test_ufw_and_fail2ban_use_the_real_ssh_ports(self):
        write_sh_stub(self.bin, "sshd", 'printf "port 2222\\nlistenaddress 0.0.0.0:2222\\n"')
        self.assertEqual(self.call("ssh_ports").stdout.strip(), "2222")
        session = {"SSH_CONNECTION": "203.0.113.5 50000 198.51.100.7 22"}
        self.assertEqual(self.call("ssh_ports", env=session).stdout.strip(), "22 2222")
        write_sh_stub(self.bin, "sshd", "exit 1")
        self.assertEqual(self.call("ssh_ports").stdout.strip(), "22")
        script = HARDEN.read_text(encoding="utf-8")
        self.assertNotIn("ufw limit 22/tcp", script)

    def test_keys_come_from_the_sudo_user(self):
        home = self.root / "home" / "debian"
        (home / ".ssh").mkdir(parents=True)
        (home / ".ssh" / "authorized_keys").write_text("ssh-ed25519 AAAA debian@laptop\n")
        write_sh_stub(self.bin, "getent", f'echo "debian:x:1000:1000::{home}:/bin/bash"')
        result = self.call("admin_key_source michael", env={"SUDO_USER": "debian"})
        self.assertEqual(result.stdout.strip(), str(home / ".ssh" / "authorized_keys"))
        self.assertEqual(self.call("admin_key_source michael").stdout.strip(), "/root/.ssh/authorized_keys")

    def test_cloud_init_forced_command_is_no_login_key(self):
        keys = self.root / "authorized_keys"
        cloud = ('no-port-forwarding,no-agent-forwarding,no-X11-forwarding,command="echo \'Please login '
                 'as the user \\"debian\\" rather than the user \\"root\\".\';echo;sleep 10;exit 142" '
                 "ssh-ed25519 AAAA root@cloud\n")
        keys.write_text(cloud)
        self.assertEqual(self.call(f'has_login_key "{keys}"').returncode, 1)
        keys.write_text("# Kommentar\n\n" + cloud + "ssh-ed25519 BBBB michael@laptop\n")
        self.assertEqual(self.call(f'has_login_key "{keys}"').returncode, 0)

    def test_sudo_counts_only_with_password_or_nopasswd(self):
        allowed = "User michael may run the following commands on host:\n    (ALL : ALL) ALL"
        cases = [
            (allowed, "P", 0),
            (allowed, "L", 1),
            (allowed + "\n    (ALL) NOPASSWD: ALL", "L", 0),
            ("User michael is not allowed to run sudo on host.", "P", 1),
        ]
        for listing, status, expected in cases:
            with self.subTest(listing=listing, status=status):
                write_sh_stub(self.bin, "sudo", f"cat <<'EOF'\n{listing}\nEOF")
                write_sh_stub(self.bin, "passwd", f'echo "michael {status} 2026-10-29 0 99999 7 -1"')
                self.assertEqual(self.call("sudo_ready michael").returncode, expected)

    def test_no_terminal_means_no_password_prompt(self):
        # Ohne steuerndes Terminal ist /dev/tty lesbar, aber nicht zu öffnen.
        result = self.call("if tty_usable; then echo frage; else echo still; fi",
                           stdin=subprocess.DEVNULL, start_new_session=True)
        self.assertEqual(result.stdout.strip(), "still", result.stderr)

    def test_ssh_is_hardened_only_after_sudo_works(self):
        script = HARDEN.read_text(encoding="utf-8")
        self.assertIn("sudo_ready \"$ADMIN_USER\" \\\n    || die", script)
        self.assertLess(script.index('sudo_ready "$ADMIN_USER"'), script.index("10-wachwerk.conf <<EOF"))
        self.assertIn("apt_install ca-certificates curl gnupg sudo ", script)

    def test_units_stay_readable_under_strict_umask(self):
        units = self.root / "units"
        units.mkdir()
        env_file = self.root / "health.env"
        result = self.call(f'umask 077; write_units "{units}"; WACHWERK_DIR=/opt/wachbuch PING_URL={PING} '
                           f'write_health_env "{env_file}"')
        self.assertEqual(result.returncode, 0, result.stderr)
        names = sorted(p.name for p in units.iterdir())
        self.assertEqual(names, ["wachwerk-health.service", "wachwerk-health.timer",
                                 "wachwerk-restore-test.service", "wachwerk-restore-test.timer"])
        for path in units.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o644, path.name)
        self.assertEqual(env_file.stat().st_mode & 0o777, 0o600)
        self.assertIn(f"PING_URL={PING}\n", env_file.read_text())
        self.assertIn("TimeoutStartSec=", (units / "wachwerk-health.service").read_text())

    def test_docker_packages_match_unattended_upgrades_pattern(self):
        """Origins-Pattern wie unattended-upgrades auswerten (match_whitelist_string)."""
        script = HARDEN.read_text(encoding="utf-8")
        block = script.split("Unattended-Upgrade::Origins-Pattern {", 1)[1].split("};", 1)[0]
        patterns = [p.replace("$CODENAME", "bookworm") for p in re.findall(r'"([^"]+)"', block)]
        # Release-Datei von download.docker.com: Origin, Label, Suite – kein Codename.
        docker = {"o": "Docker", "l": "Docker CE", "a": "bookworm", "n": "", "c": "stable",
                  "site": "download.docker.com"}
        fields = {"origin": "o", "o": "o", "label": "l", "l": "l", "archive": "a", "a": "a",
                  "suite": "a", "codename": "n", "n": "n", "component": "c", "c": "c", "site": "site"}

        def matches(pattern):
            for token in re.split(r"(?<!\\),", pattern):
                key, _, value = token.partition("=")
                if not fnmatch.fnmatch(docker[fields[key]], value.replace("\\,", ",")):
                    return False
            return True

        self.assertTrue(patterns)
        self.assertTrue(any(matches(p) for p in patterns), patterns)


@linux_only
class OffsiteSyncTests(SimpleTestCase):
    """wachwerk-offsite-sync löscht außer Haus nur nach Alter, nie per Abgleich."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="wachwerk-offsite-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.bin = self.root / "bin"
        self.conf = self.root / "etc"
        self.local = self.root / "offsite"
        for path in (self.bin, self.conf, self.local):
            path.mkdir()
        self.log = self.root / "calls"
        self.listing = self.root / "listing"
        self.listing.write_text("")
        write_sh_stub(self.bin, "rsync", f'echo "rsync $*" >>"{self.log}"')
        write_stub(self.bin, "ssh", f'''
import sys
args = sys.argv[1:]
host = next(i for i, a in enumerate(args) if "@" in a)
remote = args[host + 1:]
with open("{self.log}", "a", encoding="utf-8") as log:
    log.write("ssh " + " ".join(remote) + "\\n")
if remote[0] == "ls":
    listing = open("{self.listing}", encoding="utf-8").read()
    if listing == "FAIL":
        sys.exit(1)
    sys.stdout.write(listing)
''')
        (self.conf / "offsite.env").write_text(
            f"OFFSITE_DIR={self.local}\nOFFSITE_KEEP_DAYS=30\n"
            f"OFFSITE_TARGET=u1@u1.your-storagebox.de:wachwerk/\nOFFSITE_SSH_KEY={self.root}/key\n",
            encoding="utf-8",
        )

    def remote(self, *days_ago: int) -> list[str]:
        now = datetime.now(timezone.utc)
        names = [f"rwsth-{(now - timedelta(days=d)).strftime('%Y%m%dT%H%M%SZ')}.dump.gpg" for d in days_ago]
        self.listing.write_text("\n".join(names + ["README.txt"]) + "\n")
        return names

    def run_sync(self):
        env = {"PATH": f"{self.bin}:/usr/bin:/bin", "HOME": str(self.root),
               "WACHWERK_CONF_DIR": str(self.conf), "WACHWERK_STATE_DIR": str(self.root / "state")}
        result = subprocess.run(["sh", str(OFFSITE_SYNC)], env=env, capture_output=True, text=True, timeout=30)
        calls = self.log.read_text().splitlines() if self.log.exists() else []
        removed = [c.split("/", 1)[1] for c in calls if c.startswith("ssh rm ")]
        return result, calls, removed

    def test_empty_server_never_deletes_the_offsite_history(self):
        self.remote(40, 41, 42, 43, 44)  # nur alte Kopien, hier nichts
        result, calls, removed = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        rsync = [c for c in calls if c.startswith("rsync ")]
        self.assertEqual(len(rsync), 1)
        self.assertNotIn("--delete", rsync[0])
        self.assertEqual(removed, [], "die 7 neuesten bleiben immer")
        self.assertTrue((self.root / "state" / "offsite-sync.ok").exists())

    def test_only_expired_copies_are_pruned(self):
        names = self.remote(*range(0, 10), 40, 41, 42)
        result, _, removed = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(removed), sorted(names[10:]))

    def test_unreadable_box_skips_pruning(self):
        self.listing.write_text("FAIL")
        result, _, removed = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(removed, [])
        self.assertIn("alte Kopien bleiben liegen", result.stderr)


@linux_only
@unittest.skipUnless(shutil.which("gpg") and shutil.which("gpgconf"), "GnuPG nicht verfügbar")
class BackupEncryptionTests(SimpleTestCase):
    """Der Backup-Dienst warnt, wenn der Schlüssel AEAD (nur GnuPG >= 2.3) erzwingt."""

    PLAIN_PREFS = "AES256 AES192 AES SHA512 SHA384 SHA256 ZLIB BZIP2 ZIP Uncompressed"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = tempfile.TemporaryDirectory(prefix="wachwerk-gpg-")
        cls.root = Path(cls.tmp.name)
        cls.keys = {}
        for name, prefs in (("aead", []), ("plain", ["--default-preference-list", cls.PLAIN_PREFS])):
            home = cls.root / f"home-{name}"
            home.mkdir(mode=0o700)
            env = {**os.environ, "GNUPGHOME": str(home)}
            subprocess.run(["gpg", "--batch", "--passphrase", "", *prefs, "--quick-generate-key",
                            f"Wachwerk Backup {name} <{name}@example.org>", "future-default", "default", "never"],
                           env=env, check=True, capture_output=True, timeout=60)
            exported = subprocess.run(["gpg", "--batch", "--armor", "--export"], env=env, check=True,
                                      capture_output=True, timeout=30).stdout
            listing = subprocess.run(["gpg", "--batch", "--with-colons", "--list-keys"], env=env, check=True,
                                     capture_output=True, text=True, timeout=30).stdout
            fpr = next(line.split(":")[9] for line in listing.splitlines() if line.startswith("fpr:"))
            key_dir = cls.root / f"keys-{name}"
            key_dir.mkdir()
            (key_dir / "backup.asc").write_bytes(exported)
            packets = subprocess.run(["gpg", "--batch", "--list-packets", str(key_dir / "backup.asc")], env=env,
                                     capture_output=True, text=True, timeout=30).stdout
            cls.keys[name] = {"dir": key_dir, "fpr": fpr, "aead": bool(re.search(
                r"\(features: [0-9A-Fa-f][2367ABEFabef]", packets))}
            subprocess.run(["gpgconf", "--kill", "gpg-agent"], env=env, capture_output=True, timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        super().tearDownClass()

    def backup_once(self, key: dict):
        work = Path(tempfile.mkdtemp(prefix="run-", dir=self.root))
        bin_dir = work / "bin"
        bin_dir.mkdir()
        write_sh_stub(bin_dir, "pg_dump", 'while [ $# -gt 0 ]; do [ "$1" = --file ] && printf PGDMP >"$2"; shift; done')
        (work / "offsite").mkdir()
        env = {
            "PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(work), "PGHOST": "db", "PGUSER": "u",
            "PGDATABASE": "d", "BACKUP_DIR": str(work / "backups"), "BACKUP_OFF_TARGET": f"file://{work}/offsite",
            "BACKUP_ENCRYPT_REMOTE": "true", "BACKUP_GPG_RECIPIENT": key["fpr"],
            "BACKUP_GPG_KEY_DIR": str(key["dir"]), "GNUPGHOME": str(work / "gnupg"),
        }
        result = subprocess.run(["sh", str(BACKUP_LOOP), "once"], env=env, capture_output=True, text=True,
                                timeout=60)
        subprocess.run(["gpgconf", "--kill", "gpg-agent"], env=env, capture_output=True, timeout=30)
        encrypted = list((work / "offsite").glob("rwsth-*.dump.gpg"))
        return result, encrypted, env

    def test_plain_key_gives_widely_readable_packets_without_hint(self):
        result, encrypted, env = self.backup_once(self.keys["plain"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(encrypted), 1)
        self.assertNotIn("AEAD", result.stdout + result.stderr)
        packets = subprocess.run(["gpg", "--batch", "--list-packets", str(encrypted[0])], env=env,
                                 capture_output=True, text=True, timeout=30).stdout
        self.assertIn("encrypted data packet", packets)
        self.assertNotIn("aead encrypted packet", packets)

    def test_aead_key_is_pointed_out(self):
        if not self.keys["aead"]["aead"]:
            self.skipTest("Diese GnuPG-Version erzeugt keine Schlüssel mit AEAD-Merkmal")
        result, encrypted, _ = self.backup_once(self.keys["aead"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(encrypted), 1)
        self.assertIn("kündigt AEAD an", result.stdout)
        self.assertIn("docs/HETZNER.md", result.stdout)


class ComposeNoNewPrivilegesTests(SimpleTestCase):
    """harden-host.sh setzt no-new-privileges als Docker-Standard (daemon.json).

    Jeder Dienst legt es deshalb selbst fest; signal (s6-overlay, setuid)
    braucht ausdrücklich false, sonst startet er auf gehärteten Servern nicht.
    """

    def services(self) -> dict[str, str]:
        text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        body = text.split("\nservices:\n", 1)[1].split("\nnetworks:\n", 1)[0]
        parts = re.split(r"^  ([a-z0-9-]+):\n", body, flags=re.M)
        return dict(zip(parts[1::2], parts[2::2]))

    def test_every_service_sets_no_new_privileges_itself(self):
        services = self.services()
        self.assertIn("signal", services)
        for name, block in services.items():
            with self.subTest(service=name):
                self.assertRegex(block, r"- no-new-privileges:(true|false)\n")
        self.assertIn("- no-new-privileges:false", services["signal"])


@unittest.skipUnless(shutil.which("shellcheck"), "shellcheck nicht installiert")
class HostScriptLintTests(SimpleTestCase):
    def test_shellcheck(self):
        scripts = sorted(HETZNER.glob("*.sh")) + [BACKUP_LOOP]
        result = subprocess.run(["shellcheck", *map(str, scripts)], capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
