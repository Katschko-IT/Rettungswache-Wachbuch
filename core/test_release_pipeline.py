"""Release-Pipeline: Reihenfolge Images → GitHub-Release, wöchentlicher Neubau
der zwei neuesten Minor-Versionen, die gosu-Ausnahme im Sicherheitsscan und
der CI-Job gegen PostgreSQL mit Update-Probe vom letzten Release.

Die Workflows selbst laufen nur auf GitHub; geprüft werden hier die Hilfe
.github/scripts/release.py und die Verträge in den YAML-Dateien (als Text,
ohne YAML-Bibliothek)."""
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
HELPER = ROOT / ".github" / "scripts" / "release.py"
_SPEC = importlib.util.spec_from_file_location("wachwerk_release_helper", HELPER)
release = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(release)


def rel(tag, draft=False, prerelease=False):
    return {"tag_name": tag, "draft": draft, "prerelease": prerelease}


def jobs(workflow):
    """{Jobname: Textblock} der Jobs einer Workflow-Datei."""
    text = (WORKFLOWS / workflow).read_text(encoding="utf-8").split("\njobs:\n", 1)[1]
    parts = re.split(r"^  ([A-Za-z][\w-]*):\n", text, flags=re.MULTILINE)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def steps_of(job):
    """{Schrittname: Textblock} der benannten Schritte eines Jobs."""
    parts = re.split(r"^      - (?:name: (.+)|uses: .+)\n", job, flags=re.MULTILINE)
    return {name: body for name, body in zip(parts[1::2], parts[2::2], strict=True) if name}


def run_helper(*args):
    return subprocess.run([sys.executable, str(HELPER), *args], capture_output=True, text=True)


class RefreshTargetTests(unittest.TestCase):
    RELEASES = [
        rel("v0.27.0", draft=True),
        rel("v0.27.0-rc.1", prerelease=True),
        rel("v0.26.1"),
        rel("v0.26.0"),
        rel("v0.25.3"),
        rel("v0.25.10"),
        rel("v0.24.0"),
        rel("nightly"),
    ]

    def test_newest_patch_of_two_newest_minors(self):
        self.assertEqual(
            release.refresh_targets(self.RELEASES),
            [{"tag": "v0.26.1", "latest": True}, {"tag": "v0.25.10", "latest": False}],
        )

    def test_count_and_major_boundary(self):
        releases = [rel("v1.0.0"), rel("v0.27.2"), rel("v0.26.5")]
        self.assertEqual(release.refresh_targets(releases, 1), [{"tag": "v1.0.0", "latest": True}])
        self.assertEqual(
            [t["tag"] for t in release.refresh_targets(releases, 3)], ["v1.0.0", "v0.27.2", "v0.26.5"]
        )

    def test_no_release_means_nothing_to_do(self):
        self.assertEqual(release.refresh_targets([]), [])
        self.assertEqual(release.refresh_targets([rel("v0.1.0", draft=True)]), [])

    def test_cli_prints_compact_json_for_github_output(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(self.RELEASES, handle)
        result = subprocess.run(
            [sys.executable, str(HELPER), "refresh-targets", handle.name], capture_output=True, text=True
        )
        Path(handle.name).unlink()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), '[{"tag":"v0.26.1","latest":true},{"tag":"v0.25.10","latest":false}]')


class NewestReleaseTests(unittest.TestCase):
    RELEASES = [rel("v0.26.0"), rel("v0.25.0"), rel("v0.27.0", draft=True)]

    def test_new_version_becomes_latest(self):
        self.assertTrue(release.is_newest("v0.26.1", self.RELEASES))
        self.assertTrue(release.is_newest("v0.27.0", self.RELEASES))
        self.assertTrue(release.is_newest("v0.1.0", []))

    def test_rerun_of_newest_stays_latest(self):
        self.assertTrue(release.is_newest("v0.26.0", self.RELEASES))

    def test_backport_and_prerelease_never_latest(self):
        self.assertFalse(release.is_newest("v0.25.1", self.RELEASES))
        self.assertFalse(release.is_newest("v0.27.0-rc.1", self.RELEASES))
        self.assertFalse(release.is_newest("latest", self.RELEASES))


class PreviousReleaseTests(unittest.TestCase):
    """Ausgangspunkt der Update-Probe im CI-Job django-postgres."""

    def tags_file(self, text):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as handle:
            handle.write(text)
        self.addCleanup(Path(handle.name).unlink)
        return handle.name

    def test_newest_final_release_by_number(self):
        tags = ["v0.25.3", "v0.25.10", "v0.26.0", "v0.26.1", "v0.27.0-rc.1", "nightly", "v1"]
        self.assertEqual(release.previous_release(tags), "v0.26.1")
        self.assertEqual(release.previous_release(["v0.25.3", "v0.25.10"]), "v0.25.10")
        self.assertEqual(release.previous_release([" v0.26.0 \n", ""]), "v0.26.0")

    def test_no_release_means_none_and_cli_fails(self):
        self.assertIsNone(release.previous_release([]))
        self.assertIsNone(release.previous_release(["v0.27.0-rc.1", "nightly", "latest"]))
        result = run_helper("previous-release", self.tags_file("v0.27.0-rc.1\nnightly\n"))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("Kein früheres Release-Tag", result.stderr)

    def test_cli_prints_tag(self):
        result = run_helper("previous-release", self.tags_file("v0.25.0\nv0.26.0\n"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "v0.26.0\n")


class TagCheckTests(unittest.TestCase):
    def tree(self, version, changelog):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        (root / "core").mkdir()
        (root / "core" / "version.py").write_text(f'APP_VERSION = "{version}"\n', encoding="utf-8")
        (root / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
        return root

    def test_matching_tag_passes(self):
        root = self.tree("0.26.0", "# Changelog\n\n## 0.26.0 - 2026-11-01\n\n- Neu\n\n## 0.25.0 - 2026-10-24\n")
        self.assertEqual(release.check_tag("v0.26.0", root), [])

    def test_version_mismatch_and_missing_section_fail(self):
        root = self.tree("0.25.0", "# Changelog\n\n## Unveröffentlicht\n\n- Neu\n")
        errors = release.check_tag("v0.26.0", root)
        self.assertEqual(len(errors), 2, errors)
        self.assertIn("core/version.py", errors[0])
        self.assertIn("CHANGELOG.md", errors[1])
        self.assertTrue(release.check_tag("0.26.0", root))

    def test_real_changelog_section_for_current_version(self):
        version = re.search(r'APP_VERSION = "([^"]+)"', (ROOT / "core" / "version.py").read_text()).group(1)
        self.assertEqual(release.check_tag(f"v{version}"), [])

    def test_notes_are_exactly_the_version_section(self):
        changelog = (
            "# Changelog\n\n## Unveröffentlicht\n\n- offen\n\n## 0.26.0 - 2026-11-01\n\n"
            "Einleitung.\n\n### Upgrade-Hinweise\n\n- Backup vorher\n\n## 0.25.0 - 2026-10-24\n\n- alt\n"
        )
        notes = release.changelog_section("0.26.0", changelog)
        self.assertEqual(notes, "Einleitung.\n\n### Upgrade-Hinweise\n\n- Backup vorher")
        self.assertEqual(release.changelog_section("0.26", changelog), "")
        self.assertEqual(release.changelog_section("0.24.0", changelog), "")


class PublishWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.jobs = jobs("publish-image.yml")

    def test_release_is_created_only_after_all_images(self):
        release_job = self.jobs["release"]
        self.assertIn("needs: [prepare, publish]", release_job)
        self.assertIn("if: github.event_name == 'push'", release_job)
        self.assertIn("contents: write", release_job)
        self.assertIn('gh release create "$tag" --verify-tag', release_job)
        self.assertIn("release.py notes", release_job)
        for name, block in self.jobs.items():
            if name != "release":
                self.assertNotIn("gh release create", block, name)
        self.assertIn("needs: [prepare, verify]", self.jobs["publish"])

    def test_no_other_workflow_creates_releases(self):
        for path in WORKFLOWS.glob("*.yml"):
            if path.name != "publish-image.yml":
                self.assertNotIn("gh release create", path.read_text(encoding="utf-8"), path.name)

    def test_tag_is_checked_before_building(self):
        prepare = self.jobs["prepare"]
        self.assertIn('release.py check-tag "$GITHUB_REF_NAME"', prepare)
        self.assertIn("release.py is-newest", prepare)
        publish = self.jobs["publish"]
        self.assertIn("type=raw,value=latest,enable=${{ needs.prepare.outputs.latest == 'true' }}", publish)
        self.assertIn('flag="--latest=$LATEST"', self.jobs["release"])

    def test_security_gate_before_push(self):
        publish = self.jobs["publish"]
        gate = publish.index("aquasecurity/trivy-action@")
        self.assertLess(publish.index("load: true"), gate)
        self.assertLess(gate, publish.index("push: true"))
        self.assertIn("skip-files: ${{ matrix.trivy-skip-files }}", publish)


class RefreshWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.jobs = jobs("refresh-images.yml")

    def test_rebuilds_release_set_from_helper(self):
        self.assertIn("release.py refresh-targets", self.jobs["resolve"])
        self.assertNotIn("releases/latest", self.jobs["resolve"])
        refresh = self.jobs["refresh"]
        self.assertIn("release: ${{ fromJSON(needs.resolve.outputs.releases) }}", refresh)
        self.assertIn("ref: ${{ matrix.release.tag }}", refresh)
        self.assertIn("type=raw,value=latest,enable=${{ matrix.release.latest }}", refresh)
        self.assertIn("if: needs.resolve.outputs.releases != '[]'", refresh)
        self.assertRegex(
            (WORKFLOWS / "refresh-images.yml").read_text(encoding="utf-8"), r"REFRESH_MINOR_VERSIONS: 2\b"
        )

    def test_gosu_is_skipped_only_for_postgres_images(self):
        refresh = self.jobs["refresh"]
        self.assertIn("skip-files: ${{ matrix.trivy-skip-files }}", refresh)
        entries = re.findall(r"- target: (\w+)\n((?:            .*\n)+)", refresh)
        skips = {target: "trivy-skip-files: usr/local/bin/gosu" in body for target, body in entries}
        self.assertEqual(skips, {"runtime": False, "backup": True, "db": True})


class CiPostgresContractTests(unittest.TestCase):
    """Job django-postgres: Pflicht für jede Migration (ROADMAP 0.27 Nr. 1)."""

    START = "Start PostgreSQL like the db image (version and config from Dockerfile.backup)"
    UPDATE = "Update from the previous release with demo data"
    SUITE = "Run the full test suite against PostgreSQL"
    # Job-weites if: (vier Leerzeichen) vor den Schritten.
    JOB_LEVEL_IF = re.compile(r"(?m)^    if:")

    def setUp(self):
        self.text = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
        self.jobs = jobs("ci.yml")
        self.job = self.jobs["django-postgres"]
        self.steps = steps_of(self.job)

    def test_db_version_and_config_come_from_the_db_image(self):
        dockerfile = (ROOT / "Dockerfile.backup").read_text(encoding="utf-8")
        bases = re.findall(r"^FROM (postgres:\S+) AS pgbase$", dockerfile, flags=re.MULTILINE)
        # Sonst fände das sed-Muster im Job still nichts (oder das falsche).
        self.assertEqual(len(bases), 1, bases)
        self.assertRegex(bases[0], r"^postgres:\d+\.\d+-alpine@sha256:[0-9a-f]{64}$")
        start = self.steps[self.START]
        self.assertIn("id: postgres", start)
        self.assertIn(r"sed -n 's/^FROM \(postgres:[^ ]*\) AS pgbase$/\1/p' Dockerfile.backup", start)
        self.assertIn('"$PWD/config/postgresql.conf:/etc/postgresql/postgresql.conf:ro"', start)
        self.assertIn("postgres -c config_file=/etc/postgresql/postgresql.conf", start)
        self.assertIn("test \"$(q 'SHOW statement_timeout')\" = \"1min\"", start)
        self.assertIn("docker logs wachwerk-ci-db\n", start)
        self.assertNotIn("services:", self.job)

    def test_update_from_previous_release_with_demo_data(self):
        self.assertIn("fetch-depth: 0", self.job)
        update = self.steps[self.UPDATE]
        self.assertIn("git tag --merged HEAD --no-contains HEAD --list 'v*'", update)
        self.assertIn("release.py previous-release", update)
        self.assertIn('"$RUNNER_TEMP/previous/Dockerfile"', update)
        self.assertIn('--python "$python_version"', update)
        self.assertIn('-r "$RUNNER_TEMP/previous/requirements.lock"', update)
        old = update.index("DEMO_MODE=true sh scripts/migrate.sh)")
        head = update.index("\n          sh scripts/migrate.sh\n")
        self.assertLess(old, head)
        self.assertLess(head, update.index("python manage.py migrate --check"))
        self.assertIn("DATABASE_URL: postgres://", update)

    def test_from_zero_with_roles_stays_in_the_docker_job(self):
        # Der Job django-postgres verlässt sich darauf (kein eigener Schritt).
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        migrate = compose.split("\n  migrate:\n", 1)[1].split("\n  web:\n", 1)[0]
        self.assertIn('command: ["/app/scripts/migrate.sh"]', migrate)
        migrate_script = (ROOT / "scripts" / "migrate.sh").read_text(encoding="utf-8")
        self.assertIn("python manage.py grant_database_access", migrate_script)
        docker = self.jobs["docker"]
        self.assertIn("docker compose up --detach --wait", docker)
        self.assertIn("has_table_privilege('rwsth_app', 'core_auditevent', 'UPDATE')", docker)

    def test_full_suite_runs_against_postgresql(self):
        suite = self.steps[self.SUITE]
        self.assertIn("DATABASE_URL: postgres://", suite)
        # Ganze Suite ohne Testlabels; übersprungen werden nur Tests, die
        # selbst eine bestimmte Umgebung verlangen.
        self.assertRegex(suite, r"\n        run: python manage\.py test --settings=config\.test_settings --noinput\n")
        # Eine gescheiterte Update-Probe verdeckt das Ergebnis der Suite nicht.
        self.assertIn("if: ${{ !cancelled() && steps.postgres.outcome == 'success' }}", suite)

    def test_job_is_mandatory(self):
        self.assertTrue(self.JOB_LEVEL_IF.search("    runs-on: ubuntu-latest\n    if: false\n"))
        for name in ("django", "django-postgres", "docker"):
            head = self.jobs[name].split("\n    steps:\n", 1)[0]
            self.assertNotRegex(head, self.JOB_LEVEL_IF, name)
        self.assertNotIn("continue-on-error", self.text)
        on_block = self.text.split("\njobs:\n", 1)[0]
        self.assertNotIn("paths", on_block)
        self.assertNotIn("branches-ignore", on_block)
        publish = jobs("publish-image.yml")
        self.assertIn("uses: ./.github/workflows/ci.yml", publish["verify"])
        self.assertIn("needs: [prepare, verify]", publish["publish"])


class BackupImageTests(unittest.TestCase):
    def test_backup_image_drops_unused_gosu(self):
        source = (ROOT / "Dockerfile.backup").read_text(encoding="utf-8")
        db = source.split("FROM pgbase AS db", 1)[1].split("FROM pgbase AS backup", 1)[0]
        backup = source.split("FROM pgbase AS backup", 1)[1]
        self.assertIn("rm -f /usr/local/bin/gosu", backup)
        # Der db-Entrypoint braucht gosu für den Wechsel von root zu postgres.
        self.assertNotIn("gosu", db)


if __name__ == "__main__":
    unittest.main()
