"""Release-Pipeline: Reihenfolge Images → GitHub-Release, wöchentlicher Neubau
der zwei neuesten Minor-Versionen und die gosu-Ausnahme im Sicherheitsscan.

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
