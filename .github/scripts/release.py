#!/usr/bin/env python3
"""Hilfen für publish-image.yml und refresh-images.yml (nur Standardbibliothek).

RELEASES ist die Antwort von ``gh api repos/OWNER/REPO/releases?per_page=100``
als Datei (Liste mit tag_name, draft, prerelease).

  release.py refresh-targets RELEASES [ANZAHL]
      JSON-Liste der Releases, deren Images jede Woche neu gebaut werden:
      der neueste Patch jeder der ANZAHL (Standard 2) neuesten
      Minor-Versionen. Nur die neueste Version bekommt das Image-Tag
      „latest“. So erhalten Server im Modus „sicherheit“ auch nach der
      nächsten Version noch Sicherheits-Neubauten.
  release.py is-newest TAG RELEASES
      „true“, wenn TAG keine Vorabversion und mindestens so neu wie jede
      veröffentlichte Version ist, sonst „false“ (z. B. 0.25.1 nach 0.26.0).
  release.py check-tag TAG
      Bricht ab, wenn TAG nicht zu core/version.py passt oder CHANGELOG.md
      keinen Abschnitt „## X.Y.Z - Datum“ dafür hat.
  release.py notes VERSION
      Gibt den CHANGELOG-Abschnitt dieser Version aus (Release-Text).
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)(-[0-9A-Za-z.-]+)?$")


def parse_tag(tag):
    """(major, minor, patch, vorab) oder None für fremde Tags."""
    match = TAG_RE.match(tag or "")
    if not match:
        return None
    major, minor, patch, pre = match.groups()
    return int(major), int(minor), int(patch), bool(pre)


def published_versions(releases):
    """Veröffentlichte, endgültige Releases als [(Version, Tag)]."""
    found = []
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        parsed = parse_tag(release.get("tag_name", ""))
        if parsed and not parsed[3]:
            found.append((parsed[:3], release["tag_name"]))
    return found


def refresh_targets(releases, count=2):
    newest_per_minor = {}
    for version, tag in published_versions(releases):
        key = version[:2]
        if key not in newest_per_minor or version > newest_per_minor[key][0]:
            newest_per_minor[key] = (version, tag)
    chosen = sorted(newest_per_minor.values(), reverse=True)[:count]
    return [{"tag": tag, "latest": index == 0} for index, (_, tag) in enumerate(chosen)]


def is_newest(tag, releases):
    parsed = parse_tag(tag)
    if not parsed or parsed[3]:
        return False
    return all(parsed[:3] >= version for version, _ in published_versions(releases))


def changelog_section(version, changelog):
    lines = changelog.splitlines()
    heading = re.compile(rf"^## {re.escape(version)}(\s+-\s+.*)?\s*$")
    for start, line in enumerate(lines):
        if heading.match(line):
            body = []
            for text in lines[start + 1:]:
                if text.startswith("## "):
                    break
                body.append(text)
            return "\n".join(body).strip()
    return ""


def check_tag(tag, root=ROOT):
    """Fehlermeldungen; leer, wenn Tag, core/version.py und CHANGELOG passen."""
    if not parse_tag(tag):
        return [f"Tag {tag!r} hat nicht die Form vX.Y.Z"]
    version = tag[1:]
    errors = []
    source = (root / "core" / "version.py").read_text(encoding="utf-8")
    match = re.search(r'^APP_VERSION = "([^"]+)"$', source, re.MULTILINE)
    if not match or match.group(1) != version:
        found = match.group(1) if match else "?"
        errors.append(f"core/version.py nennt {found}, der Tag {tag}")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    if not changelog_section(version, changelog):
        errors.append(f"CHANGELOG.md hat keinen Abschnitt '## {version} - Datum'")
    return errors


def load(path):
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise SystemExit(f"{path}: erwartet eine JSON-Liste von Releases")
    return data


def main(argv):
    command, args = (argv[0], argv[1:]) if argv else ("", [])
    if command == "refresh-targets" and len(args) in (1, 2):
        count = int(args[1]) if len(args) == 2 else 2
        print(json.dumps(refresh_targets(load(args[0]), count), separators=(",", ":")))
    elif command == "is-newest" and len(args) == 2:
        print("true" if is_newest(args[0], load(args[1])) else "false")
    elif command == "check-tag" and len(args) == 1:
        errors = check_tag(args[0])
        for error in errors:
            print(f"::error::{error}", file=sys.stderr)
        return 1 if errors else 0
    elif command == "notes" and len(args) == 1:
        notes = changelog_section(args[0], (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
        if not notes:
            print(f"::error::CHANGELOG.md hat keinen Abschnitt '## {args[0]} - Datum'", file=sys.stderr)
            return 1
        print(notes)
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
