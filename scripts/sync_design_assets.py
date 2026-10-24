#!/usr/bin/env python3
"""Kopiert die gemeinsamen Design-Dateien in die statischen Auftritte.

Quelle ist die App (core/static/core/). Projektseite (site/) und Folien
(docs/praesentation/) laufen ohne Django und brauchen eigene Kopien – sie
sollen aber dieselbe Design-Sprache sprechen. core/test_design_assets.py
schlägt fehl, sobald eine Kopie abweicht.

    python scripts/sync_design_assets.py
"""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "core" / "static" / "core"
TARGETS = [ROOT / "site" / "assets" / "design", ROOT / "docs" / "praesentation" / "design"]
FILES = ["tokens.css", "fonts.css", "public.css", "icons.svg"]


def design_files() -> list[Path]:
    fonts = sorted((SOURCE / "fonts").glob("atkinson-hyperlegible-next-*.woff2"))
    # Screenshots der Oberfläche (scripts/capture_screens.py, nur Demodaten).
    screens = sorted((SOURCE / "screens").glob("*.webp"))
    return ([SOURCE / name for name in FILES] + fonts
            + [SOURCE / "fonts" / "LICENSE-AtkinsonHyperlegibleNext.txt"] + screens)


def relative(path: Path) -> Path:
    return path.relative_to(SOURCE)


def main() -> None:
    for target in TARGETS:
        if target.exists():
            shutil.rmtree(target)
        for source in design_files():
            destination = target / relative(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        print(f"{target.relative_to(ROOT)}: {len(design_files())} Dateien")


if __name__ == "__main__":
    main()
