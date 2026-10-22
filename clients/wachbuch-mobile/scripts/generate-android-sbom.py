#!/usr/bin/env python3
"""Generate deterministic CycloneDX and OSV dependency documents."""

from __future__ import annotations

import argparse
import json
import re
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

GRADLE_DEPENDENCY = re.compile(
    r"[+\\]---\s+([^:\s()]+):([^:\s()]+):([^\s()]+)(?:\s+->\s+([^\s()]+))?"
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pub", required=True, type=Path)
    parser.add_argument("--gradle", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--osv-output", type=Path)
    parser.add_argument("--version", required=True)
    return parser.parse_args()


def flutter_components(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    packages = payload.get("packages")
    if not isinstance(packages, list):
        raise ValueError("flutter pub deps JSON does not contain a packages list")

    components: list[dict[str, Any]] = []
    for package in packages:
        if not isinstance(package, dict):
            continue
        name = package.get("name")
        version = package.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            continue
        components.append(
            {
                "type": "library",
                "name": name,
                "version": version,
                "purl": f"pkg:pub/{quote(name, safe='')}@{quote(version, safe='')}",
                "properties": [
                    {
                        "name": "wachbuch:dependency-kind",
                        "value": str(package.get("kind", "transitive")),
                    },
                    {
                        "name": "wachbuch:dependency-source",
                        "value": str(package.get("source", "unknown")),
                    },
                ],
            }
        )
    return components


def gradle_components(path: Path) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = GRADLE_DEPENDENCY.search(line)
        if match is None:
            continue
        group, artifact, declared_version, selected_version = match.groups()
        version = selected_version or declared_version
        if version in {"FAILED", "(*)", "(c)"} or version.startswith("{"):
            continue
        purl = (
            f"pkg:maven/{quote(group, safe='')}/{quote(artifact, safe='')}"
            f"@{quote(version, safe='')}"
        )
        component: dict[str, Any] = {
            "type": "library",
            "group": group,
            "name": artifact,
            "version": version,
            "purl": purl,
        }
        if selected_version and selected_version != declared_version:
            component["properties"] = [
                {
                    "name": "wachbuch:declared-version",
                    "value": declared_version,
                }
            ]
        components.append(component)
    return components


def dependency_kind(component: dict[str, Any]) -> str | None:
    for prop in component.get("properties", []):
        if prop.get("name") == "wachbuch:dependency-kind":
            return str(prop.get("value"))
    return None


def write_osv_document(path: Path, components: list[dict[str, Any]]) -> None:
    packages: list[dict[str, Any]] = []
    for component in components:
        if dependency_kind(component) == "root":
            continue
        purl = str(component["purl"])
        if purl.startswith("pkg:pub/"):
            package = {
                "name": component["name"],
                "version": component["version"],
                "ecosystem": "Pub",
            }
        elif purl.startswith("pkg:maven/"):
            package = {
                "name": f"{component['group']}:{component['name']}",
                "version": component["version"],
                "ecosystem": "Maven",
            }
        else:
            continue
        packages.append({"package": package})

    document = {"results": [{"packages": packages}]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(packages)} OSV packages to {path}")


def main() -> None:
    args = parse_arguments()
    all_components = flutter_components(args.pub) + gradle_components(args.gradle)
    components_by_purl = {component["purl"]: component for component in all_components}
    components = [components_by_purl[purl] for purl in sorted(components_by_purl)]

    identity = "\n".join(component["purl"] for component in components)
    serial = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"https://github.com/Katschko-IT/Wachbuch-Client/{args.version}\n{identity}",
    )
    bom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "group": "de.wachbuch",
                "name": "wachbuch-mobile-android",
                "version": args.version,
                "purl": f"pkg:generic/wachbuch-mobile-android@{quote(args.version, safe='')}",
            },
            "properties": [
                {
                    "name": "wachbuch:source-repository",
                    "value": "https://github.com/Katschko-IT/Wachbuch-Client",
                }
            ],
        },
        "components": components,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(bom, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(components)} components to {args.output}")

    if args.osv_output is not None:
        write_osv_document(args.osv_output, components)


if __name__ == "__main__":
    main()
