"""Design-Tokens: Jede benutzte Variable ist definiert, die Schriftskala wird genutzt.

Auslöser war das Audit vom 2026-11-03: ``--text-muted`` und ``--text-dim`` wurden
verwendet, aber nie definiert und fielen still auf Browser-Standards zurück.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

CSS_DIR = Path(settings.BASE_DIR) / "core" / "static" / "core"
# Werden zur Laufzeit gesetzt (ui.js: data-band) und haben bewusst keine Vorgabe.
RUNTIME_VARIABLES = {"--band", "--band-soft"}


def _css():
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(CSS_DIR.glob("*.css"))}


class DesignTokenTests(SimpleTestCase):
    def test_every_used_variable_is_defined(self):
        files = _css()
        defined = set(RUNTIME_VARIABLES)
        for text in files.values():
            defined |= set(re.findall(r"(--[\w-]+)\s*:", text))
        missing = {}
        for name, text in files.items():
            for variable in re.findall(r"var\((--[\w-]+)", text):
                if variable not in defined:
                    missing.setdefault(variable, set()).add(name)
        self.assertEqual(missing, {})

    def test_type_scale_is_defined_and_used(self):
        files = _css()
        for step in ("xs", "sm", "base", "md", "lg", "xl", "2xl", "3xl"):
            self.assertIn(f"--fs-{step}:", files["tokens.css"])
        self.assertGreater(files["app.css"].count("font-size: var(--fs-"), 50)

    def test_hidden_inputs_cannot_widen_the_page(self):
        self.assertIn("input.visually-hidden", _css()["app.css"])
