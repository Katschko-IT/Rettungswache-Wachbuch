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
