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
