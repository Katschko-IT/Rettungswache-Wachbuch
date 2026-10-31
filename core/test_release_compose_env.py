"""Release contract for explicitly passed, opt-in Docker setup/QR settings."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = {
    "SETUP_BOOTSTRAP_TOKEN": "",
    "QR_LOGIN_ENABLED": "false",
    "QR_LOGIN_TTL_SECONDS": "120",
    "SITE_URL": "",
    "TRUSTED_PROXY": "false",
}


def compose_command():
    standalone = shutil.which("docker-compose")
    if standalone:
        return [standalone]
    docker = shutil.which("docker")
    if docker and subprocess.run(
        [docker, "compose", "version"], capture_output=True, timeout=15
    ).returncode == 0:
        return [docker, "compose"]
    fallback = Path("/opt/data/bin/docker-compose")
    return [str(fallback)] if fallback.is_file() else None


class ReleaseComposeContractTests(unittest.TestCase):
    def test_web_has_explicit_safe_mapping(self):
        source = (ROOT / "docker-compose.yml").read_text()
        web = source.split("\n  web:\n", 1)[1].split("\n  feed-worker:\n", 1)[0]
        for key, default in DEFAULTS.items():
            with self.subTest(key=key):
                expected = f"      {key}: ${{{key}:-{default}}}"
                self.assertIn(expected, web.splitlines())
        self.assertNotIn("QR_LOGIN_ALLOW_INSECURE_TEST_ORIGIN:", web)

    def test_example_has_opt_in_defaults(self):
        source = (ROOT / ".env.example").read_text()
        assignments = dict(re.findall(r"^([A-Z_]+)=(.*)$", source, re.MULTILINE))
        for key, default in DEFAULTS.items():
            with self.subTest(key=key):
                self.assertEqual(assignments.get(key), default)
        self.assertEqual(assignments["MFA_ENABLED"], "true")

    def render(self, extra):
        command = compose_command()
        if command is None:
            self.skipTest("Compose CLI unavailable; static mapping contracts still run")
        with tempfile.TemporaryDirectory(prefix="wachbuch-compose-contract-") as home:
            env = {"PATH": os.environ.get("PATH", os.defpath), "HOME": home}
            env.update(extra)
            result = subprocess.run(
                command + ["--env-file", os.devnull, "-f", str(ROOT / "docker-compose.yml"),
                           "config", "--format", "json"],
                env=env, capture_output=True, text=True, timeout=45,
            )
            self.assertEqual(result.returncode, 0, "Synthetic Compose rendering failed")
            return json.loads(result.stdout)["services"]

    def test_real_compose_defaults_fail_closed(self):
        web = self.render({})["web"]["environment"]
        for key, default in DEFAULTS.items():
            with self.subTest(key=key):
                self.assertIn(key, web)
                self.assertEqual(str(web[key]), default)
        self.assertEqual(web["MFA_ENABLED"], "true")

    def test_real_compose_opt_in_reaches_only_web(self):
        values = dict(DEFAULTS, SETUP_BOOTSTRAP_TOKEN="synthetic-review-bootstrap-only-0123456789",
                      QR_LOGIN_ENABLED="true", QR_LOGIN_TTL_SECONDS="90",
                      SITE_URL="https://wache.example", TRUSTED_PROXY="true")
        services = self.render(dict(values, UNRELATED_SECRET_SENTINEL="not-for-web"))
        web = services["web"]["environment"]
        for key, value in values.items():
            with self.subTest(key=key):
                self.assertEqual(str(web.get(key)), value)
        self.assertNotIn("UNRELATED_SECRET_SENTINEL", web)
        for service, config in services.items():
            if service != "web":
                self.assertNotIn("SETUP_BOOTSTRAP_TOKEN", config.get("environment", {}))


class ComposeNetworkContractTests(unittest.TestCase):
    """Jeder Dienst mit DB_HOST: db muss ein Netz mit der Datenbank teilen."""

    @staticmethod
    def services(source):
        body = source.split("\nservices:\n", 1)[1].split("\nnetworks:\n", 1)[0]
        blocks = re.split(r"\n  (?=[a-z][a-z0-9-]*:\n)", "\n" + body)
        return {block.split(":", 1)[0].strip(): block for block in blocks if block.strip()}

    @staticmethod
    def networks(block):
        match = re.search(r"\n    networks:\n((?:      - [a-z-]+\n?)+)", block)
        return set(re.findall(r"- ([a-z-]+)", match.group(1))) if match else set()

    def test_database_clients_share_a_network_with_db(self):
        services = self.services((ROOT / "docker-compose.yml").read_text())
        db_networks = self.networks(services["db"])
        self.assertTrue(db_networks)
        clients = [name for name, block in services.items() if "DB_HOST: db" in block or "PGHOST: db" in block]
        self.assertIn("notify-worker", clients)
        for name in clients:
            with self.subTest(service=name):
                self.assertTrue(self.networks(services[name]) & db_networks, f"{name} erreicht db nicht")


class HealthStatusMountTests(unittest.TestCase):
    """Zustand der Host-Überwachung: nur web und notify-worker, nur lesend."""

    MOUNT = "${WACHWERK_HEALTH_DIR:-health-status}:/run/wachwerk-health:ro"

    def test_only_web_and_notify_worker_mount_health_status_read_only(self):
        source = (ROOT / "docker-compose.yml").read_text()
        services = ComposeNetworkContractTests.services(source)
        mounting = {name for name, block in services.items() if "wachwerk-health" in block}
        self.assertEqual(mounting, {"web", "notify-worker"})
        for name in mounting:
            with self.subTest(service=name):
                self.assertIn(f"      - {self.MOUNT}\n", services[name])
        for name in ("housekeeping", "push-worker", "feed-worker", "demo-cleaner", "backup", "restore-test"):
            self.assertIn(name, services)
        volumes = source.split("\nvolumes:\n", 1)[1]
        self.assertIn("\n  health-status:\n", "\n" + volumes)

    def test_rendered_mount_is_read_only_with_and_without_host_dir(self):
        contract = ReleaseComposeContractTests()
        for extra, kind, source in (
            ({"WACHWERK_HEALTH_DIR": "/var/lib/wachwerk-health"}, "bind", "/var/lib/wachwerk-health"),
            ({}, "volume", "health-status"),
        ):
            with self.subTest(kind=kind):
                if compose_command() is None:
                    self.skipTest("Compose CLI unavailable; static mapping contract still runs")
                services = contract.render(extra)
                for name in ("web", "notify-worker"):
                    mounts = [m for m in services[name].get("volumes", []) if m["target"] == "/run/wachwerk-health"]
                    self.assertEqual(len(mounts), 1, name)
                    self.assertEqual(mounts[0]["type"], kind)
                    self.assertTrue(mounts[0]["source"].endswith(source), mounts[0])
                    self.assertTrue(mounts[0].get("read_only"), mounts[0])
                for name, config in services.items():
                    if name not in ("web", "notify-worker"):
                        targets = [m.get("target") for m in config.get("volumes", [])]
                        self.assertNotIn("/run/wachwerk-health", targets, name)
