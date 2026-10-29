#!/usr/bin/env python3
"""Kopiert die gemeinsamen Design-Dateien in die statischen Auftritte.

Quelle ist die App (core/static/core/). Projektseite (site/) und Folien
(docs/praesentation/) laufen ohne Django und brauchen eigene Kopien – sie
sollen aber dieselbe Design-Sprache sprechen. core/test_design_assets.py
schlägt fehl, sobald eine Kopie abweicht.

    python scripts/sync_design_assets.py          # Kopien neu schreiben
    python scripts/sync_design_assets.py --check  # nur prüfen, Exit 1 bei Abweichung
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "core" / "static" / "core"
TARGETS = [ROOT / "site" / "assets" / "design", ROOT / "docs" / "praesentation" / "design"]
FILES = ["tokens.css", "fonts.css", "public.css", "icons.svg", "brand-wachwerk.png"]


def design_files() -> list[Path]:
    fonts = sorted((SOURCE / "fonts").glob("atkinson-hyperlegible-next-*.woff2"))
    # Screenshots der Oberfläche (scripts/capture_screens.py, nur Demodaten).
    screens = sorted((SOURCE / "screens").glob("*.webp"))
    return ([SOURCE / name for name in FILES] + fonts
            + [SOURCE / "fonts" / "LICENSE-AtkinsonHyperlegibleNext.txt"] + screens)


def relative(path: Path) -> Path:
    return path.relative_to(SOURCE)


def drift() -> list[str]:
    """Fehlende, abweichende und überzählige Dateien in den Kopien."""
    expected = {relative(source): source for source in design_files()}
    problems = []
    for target in TARGETS:
        for rel, source in expected.items():
            copy = target / rel
            if not copy.is_file():
                problems.append(f"fehlt: {copy.relative_to(ROOT)}")
            elif copy.read_bytes() != source.read_bytes():
                problems.append(f"weicht ab: {copy.relative_to(ROOT)}")
        if target.exists():
            for copy in sorted(path for path in target.rglob("*") if path.is_file()):
                if copy.relative_to(target) not in expected:
                    problems.append(f"überzählig: {copy.relative_to(ROOT)}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Design-Dateien der App nach site/ und docs/praesentation/ kopieren.")
    parser.add_argument("--check", action="store_true", help="nur prüfen, nichts schreiben (Exit 1 bei Abweichung)")
    args = parser.parse_args(argv)
    if args.check:
        problems = drift()
        for problem in problems:
            print(problem)
        if problems:
            print("Abhilfe: python scripts/sync_design_assets.py", file=sys.stderr)
            return 1
        print("Design-Kopien sind aktuell.")
        return 0
    for target in TARGETS:
        if target.exists():
            shutil.rmtree(target)
        for source in design_files():
            destination = target / relative(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        print(f"{target.relative_to(ROOT)}: {len(design_files())} Dateien")
    return 0


if __name__ == "__main__":
    sys.exit(main())
