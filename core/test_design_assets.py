"""Projektseite und Folien nutzen exakt die Design-Dateien der App."""
import importlib.util
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sync_design_assets", ROOT / "scripts" / "sync_design_assets.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class DesignAssetCopiesTests(SimpleTestCase):
    def test_copies_match_app_sources(self):
        for target in sync.TARGETS:
            for source in sync.design_files():
                copy = target / sync.relative(source)
                with self.subTest(copy=str(copy.relative_to(ROOT))):
                    self.assertTrue(copy.is_file(), "fehlt – python scripts/sync_design_assets.py ausführen")
                    self.assertEqual(copy.read_bytes(), source.read_bytes(),
                                     "weicht ab – python scripts/sync_design_assets.py ausführen")


class SyncCheckModeTests(SimpleTestCase):
    """--check prüft nur; vorher löschte und kopierte jeder Aufruf die Ordner."""

    def test_check_reports_drift_without_writing(self):
        import contextlib
        import io
        import tempfile
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "design"
            target.mkdir()
            (target / "tokens.css").write_text("/* alt */")
            (target / "veraltet.css").write_text("")
            out = io.StringIO()
            with mock.patch.object(sync, "TARGETS", [target]), mock.patch.object(sync, "ROOT", Path(tmp)), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(sync.main(["--check"]), 1)
            self.assertEqual((target / "tokens.css").read_text(), "/* alt */")
            self.assertTrue((target / "veraltet.css").exists())
            self.assertIn("weicht ab: design/tokens.css", out.getvalue())
            self.assertIn("überzählig: design/veraltet.css", out.getvalue())
            self.assertIn("fehlt: design/public.css", out.getvalue())

    def test_check_passes_on_current_copies_and_rejects_unknown_arguments(self):
        import contextlib
        import io

        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sync.main(["--check"]), 0)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            sync.main(["--chek"])
