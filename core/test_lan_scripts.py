"""Überwachung im Wachen-Netz: deploy/lan/setup-monitoring.sh und deploy/pi/setup-pi.sh.

Die Funktionen des Installers laufen einzeln im Bibliotheksmodus gegen
Attrappen in einem Temp-Ordner; das System bleibt unberührt.
"""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
import tempfile

from django.test import SimpleTestCase

from core.test_hetzner_scripts import PI_SERVICES, HealthSandbox, linux_only, write_sh_stub

ROOT = Path(__file__).resolve().parents[1]
MONITORING = ROOT / "deploy" / "lan" / "setup-monitoring.sh"
SETUP_PI = ROOT / "deploy" / "pi" / "setup-pi.sh"
PI_COMPOSE_FILE = "docker-compose.yml:compose.build.yml:deploy/pi/docker-compose.pi.yml"
MOUNT_LINE = "      - ${WACHWERK_HEALTH_DIR:-health-status}:/run/wachwerk-health:ro\n"


@linux_only
class MonitoringInstallerTests(SimpleTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="wachwerk-lan-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()

    def call(self, snippet: str, env: dict | None = None):
        base = {"PATH": f"{self.bin}:/usr/bin:/bin", "HOME": str(self.root), "LC_ALL": "C.UTF-8",
                "WACHWERK_MONITORING_LIB": "1", "SCRIPT": str(MONITORING)}
        base.update(env or {})
        return subprocess.run(["sh", "-c", f'. "$SCRIPT"; {snippet}'], env=base, capture_output=True,
                              text=True, timeout=30)

    def install(self, layout: str, *, mounted: bool = True) -> Path:
        """Wachwerk-Ordner wie nach setup-pi.sh (pi) bzw. install.sh (lan/local/domain)."""
        target = self.root / f"install-{layout}"
        target.mkdir()
        compose = "services:\n  web:\n    image: app\n" + (MOUNT_LINE if mounted else "")
        if layout == "pi":
            (target / "deploy" / "pi").mkdir(parents=True)
            (target / "deploy" / "pi" / "docker-compose.pi.yml").write_text("services: {}\n")
            (target / "docker-compose.yml").write_text(compose)
            env = "PI_TLS_DIR=/etc/wachbuch/tls\nALLOWED_HOSTS=10.42.0.1\n"
        else:
            (target / "compose.yml").write_text(compose)
            env = f"WACHBUCH_MODE={layout}\nWACHBUCH_HOSTNAME=wachbuch.lan\nHTTP_PORT=8091\n"
        (target / ".env").write_text(env)
        (target / ".env").chmod(0o600)
        return target

    def test_library_mode_runs_nothing(self):
        result = self.call("echo geladen")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "geladen")
        self.assertEqual(result.stderr, "")

    def test_detect_layout_pi_lan_local(self):
        for layout in ("pi", "lan", "local"):
            with self.subTest(layout=layout):
                result = self.call(f'detect_layout "{self.install(layout)}"')
                self.assertEqual(result.stdout.strip(), layout, result.stderr)

    def test_internet_layout_is_refused_with_hint(self):
        result = self.call(f'detect_layout "{self.install("domain")}"')
        self.assertEqual(result.returncode, 1)
        self.assertIn("harden-host.sh", result.stderr)
        result = self.call(f'detect_layout "{self.root}"')
        self.assertEqual(result.returncode, 1)
        self.assertIn(".env fehlt", result.stderr)

    def test_pi_health_env_uses_local_certificate_and_pi_services(self):
        target = self.install("pi")
        health = self.root / "health.env"
        result = self.call(f'umask 022; write_lan_health_env "{health}" pi "{target}" https://hc-ping.example/x')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(health.stat().st_mode & 0o777, 0o600)
        text = health.read_text()
        self.assertIn(f"WACHWERK_DIR={target}\n", text)
        self.assertIn("PING_URL=https://hc-ping.example/x\n", text)
        self.assertIn("HEALTH_URL=https://localhost/healthz/\n", text)
        self.assertIn("HEALTH_CA_FILE=/etc/wachbuch/tls/wachbuch.crt\n", text)
        self.assertIn(f"HEALTH_SERVICES='{PI_SERVICES}'\n", text)
        self.assertIn("FAILS_BEFORE_ALERT=2\n", text)
        self.assertEqual(list(self.root.glob("health.env.tmp*")), [])

    def test_lan_health_env_keeps_the_resolve_path(self):
        target = self.install("lan")
        health = self.root / "health.env"
        self.call(f'write_lan_health_env "{health}" lan "{target}" "" /etc/wachwerk/lan-ca.crt')
        text = health.read_text()
        self.assertIn("HEALTH_CA_FILE=/etc/wachwerk/lan-ca.crt\n", text)
        self.assertIsNone(re.search(r"^HEALTH_URL=", text, re.M), "LAN braucht --resolve über WACHBUCH_HOSTNAME")
        self.call(f'write_lan_health_env "{health}" lan "{target}"')
        self.assertIn("HEALTH_URL=http://127.0.0.1:8091/healthz/\n", health.read_text())

    def test_local_health_env_uses_the_web_port(self):
        target = self.install("local")
        health = self.root / "health.env"
        self.call(f'write_lan_health_env "{health}" local "{target}"')
        text = health.read_text()
        self.assertIn("HEALTH_URL=http://127.0.0.1:8091/healthz/\n", text)
        self.assertNotIn("HEALTH_CA_FILE", text)

    def test_rerun_keeps_existing_ping_url(self):
        target = self.install("pi")
        health = self.root / "health.env"
        self.call(f'write_lan_health_env "{health}" pi "{target}" https://hc-ping.example/alt')
        self.call(f'write_lan_health_env "{health}" pi "{target}"')
        self.assertIn("PING_URL=https://hc-ping.example/alt\n", health.read_text())
        self.call(f'write_lan_health_env "{health}" pi "{target}" https://hc-ping.example/neu')
        self.assertIn("PING_URL=https://hc-ping.example/neu\n", health.read_text())

    def test_higher_alert_threshold_is_kept_with_warning(self):
        target = self.install("pi")
        health = self.root / "health.env"
        health.write_text("FAILS_BEFORE_ALERT=4\n")
        result = self.call(f'write_lan_health_env "{health}" pi "{target}"')
        self.assertIn("FAILS_BEFORE_ALERT=4\n", health.read_text())
        self.assertIn("nicht in unter 15 Minuten", result.stderr)

    def test_env_set_adds_health_dir_once_and_keeps_other_values(self):
        env = self.root / ".env"
        env.write_text("A=1\nWACHWERK_HEALTH_DIR=\nB='zwei worte'\nWACHWERK_HEALTH_DIR=/alt\n")
        env.chmod(0o600)
        result = self.call(f'env_set "{env}" WACHWERK_HEALTH_DIR /var/lib/wachwerk-health')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(env.read_text(), "A=1\nWACHWERK_HEALTH_DIR=/var/lib/wachwerk-health\nB='zwei worte'\n")
        self.assertEqual(env.stat().st_mode & 0o777, 0o600)
        self.call(f'env_set "{env}" NEU wert')
        self.assertTrue(env.read_text().endswith("NEU=wert\n"))
        self.assertEqual(list(self.root.glob(".env.tmp*")), [])

    def test_configure_compose_env_sets_pi_values_once(self):
        target = self.install("pi")
        snippet = f'configure_compose_env "{target}" pi /var/lib/wachwerk-health; echo "$ENV_CHANGED $APP_DISPLAY"'
        first = self.call(snippet)
        self.assertEqual(first.stdout.strip(), "1 1", first.stderr)
        text = (target / ".env").read_text()
        self.assertIn("WACHWERK_HEALTH_DIR=/var/lib/wachwerk-health\n", text)
        self.assertIn(f"COMPOSE_FILE={PI_COMPOSE_FILE}\n", text)
        self.assertIn("PI_TLS_DIR=/etc/wachbuch/tls\n", text)
        self.assertEqual(self.call(snippet).stdout.strip(), "0 1", "zweiter Lauf ändert nichts")

    def test_existing_compose_file_on_the_pi_is_kept(self):
        target = self.install("pi")
        with (target / ".env").open("a") as handle:
            handle.write("COMPOSE_FILE=docker-compose.yml:eigene.yml\n")
        self.call(f'configure_compose_env "{target}" pi /var/lib/wachwerk-health')
        self.assertIn("COMPOSE_FILE=docker-compose.yml:eigene.yml\n", (target / ".env").read_text())

    def test_old_installation_gets_hint_not_recreate(self):
        target = self.install("lan", mounted=False)
        before = (target / ".env").read_text()
        result = self.call(f'configure_compose_env "{target}" lan /var/lib/wachwerk-health; '
                           'echo "$ENV_CHANGED $APP_DISPLAY"')
        self.assertEqual(result.stdout.strip(), "0 0")
        self.assertIn("erst ab Version 0.27", result.stderr)
        self.assertEqual((target / ".env").read_text(), before)

    def test_lan_ca_is_copied_from_caddy_or_falls_back(self):
        target = self.install("lan")
        ca = self.root / "etc" / "lan-ca.crt"
        write_sh_stub(self.bin, "docker", 'eval "last=\\${$#}"; printf "CA" >"$last"')
        result = self.call(f'copy_lan_ca "{target}" "{ca}" && echo kopiert')
        self.assertEqual(result.stdout.strip(), "kopiert", result.stderr)
        self.assertEqual(ca.read_text(), "CA")
        self.assertEqual(ca.stat().st_mode & 0o777, 0o644)
        ca.unlink()
        write_sh_stub(self.bin, "docker", "exit 1")
        result = self.call(f'copy_lan_ca "{target}" "{ca}" || echo ohne')
        self.assertEqual(result.stdout.strip(), "ohne")
        self.assertIn("127.0.0.1", result.stderr)
        self.assertFalse(ca.exists())

    def test_pi_health_env_works_with_the_health_check(self):
        """Die erzeugte health.env passt zu wachwerk-health (Anführungszeichen, Dienste, CA)."""
        box = HealthSandbox(self)
        (box.dir / ".env").write_text("PI_TLS_DIR=/etc/wachbuch/tls\n")
        box.state["containers"] = [
            c for c in box.state["containers"]
            if c["service"] not in ("feed-worker", "push-worker", "caddy", "demo-cleaner")
        ] + [{"id": "id-proxy", "service": "proxy"}]
        result = self.call(f'write_lan_health_env "{box.conf / "health.env"}" pi "{box.dir}"')
        self.assertEqual(result.returncode, 0, result.stderr)
        result = box.run("--verbose", write_settings=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Dienst proxy läuft", result.stdout)
        args = next(c["args"] for c in box.calls("curl") if "/healthz/" in c["url"])
        self.assertEqual(args[-1], "https://localhost/healthz/")
        self.assertEqual(args[args.index("--cacert") + 1], "/etc/wachbuch/tls/wachbuch.crt")

    def test_installer_reuses_the_units_of_harden_host(self):
        script = MONITORING.read_text(encoding="utf-8")
        self.assertIn('. "$HETZNER_DIR/harden-host.sh"', script)
        self.assertIn("write_units /etc/systemd/system", script)
        self.assertIn('install -m 0755 "$HETZNER_DIR/wachwerk-health.sh" /usr/local/bin/wachwerk-health', script)
        for timer in ("wachwerk-health.timer", "wachwerk-restore-test.timer"):
            self.assertIn(f"systemctl enable --now {timer}", script)
        self.assertIn(f'PI_COMPOSE_FILE="{PI_COMPOSE_FILE}"', script)


class SetupPiMonitoringTests(SimpleTestCase):
    """Vertrag mit deploy/pi/setup-pi.sh: Compose-Dateien in .env, Überwachung nach dem Start."""

    def test_setup_pi_sets_compose_file_and_installs_monitoring(self):
        script = SETUP_PI.read_text(encoding="utf-8")
        compose_file = f'set_env COMPOSE_FILE "{PI_COMPOSE_FILE}"'
        health_dir = "set_env WACHWERK_HEALTH_DIR /var/lib/wachwerk-health"
        start = '"${COMPOSE[@]}" up -d --build'
        monitoring = 'sh "$REPO_DIR/deploy/lan/setup-monitoring.sh" --dir "$REPO_DIR" --yes'
        for snippet in (compose_file, health_dir, start, monitoring):
            self.assertIn(snippet, script)
        self.assertLess(script.index(compose_file), script.index(start))
        self.assertLess(script.index(health_dir), script.index(start))
        self.assertLess(script.index(start), script.index(monitoring))
        self.assertIn("sudo wachwerk-health --verbose", script)

    def test_setup_pi_avoids_and_or_chains(self):
        script = SETUP_PI.read_text(encoding="utf-8")
        self.assertNotIn('[[ -n "$KIOSK_USER" ]] && id', script)
