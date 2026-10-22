#!/usr/bin/env python3
"""Erzeugt die Hintergrundbilder des Terminal-Sperrbildschirms.

Quelle der Wahrheit ist ``core/lockscreen_credits.json``: Datei, Commons-Titel,
Urheber und Lizenz je Bild (nur CC0, gemeinfrei, CC BY, CC BY-SA). Das Skript

1. lädt jedes Bild als 1280-px-Vorschau von Wikimedia Commons (oder nimmt es
   aus ``--from-dir``; dort heißen die Dateien wie in der JSON-Datei),
2. schneidet mittig auf 16:9 zu, verkleinert auf 1280×720, zeichnet leicht weich
   (der Sperrbildschirm blendet ohnehin unscharf ein) und speichert ohne
   Metadaten nach ``core/static/core/lockscreen/``,
3. schreibt die CSS-Klassen ``.lock-bg-NN`` in ``core/static/core/lockscreen.css``.

Bearbeitete Bilder unter CC BY-SA bleiben CC BY-SA; Nachweise stehen auf dem
Sperrbildschirm (Bild des Tages) und vollständig in docs/BILDNACHWEISE.md.

    python scripts/build_lockscreen_backgrounds.py [--from-dir PFAD]
"""
from __future__ import annotations

import argparse
import io
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
CREDITS = ROOT / "core" / "lockscreen_credits.json"
OUT_DIR = ROOT / "core" / "static" / "core" / "lockscreen"
CSS = ROOT / "core" / "static" / "core" / "lockscreen.css"
CSS_START = "/* --- Hintergründe (generiert) --- */"
UA = "Wachbuch-Hintergrundbilder/1.0 (https://github.com/Katschko-IT/Rettungswache-Wachbuch)"
SIZE = (1280, 720)


def download(title: str) -> bytes:
    query = urllib.parse.urlencode({
        "action": "query", "titles": f"File:{title}", "prop": "imageinfo",
        "iiprop": "url", "iiurlwidth": "1280", "format": "json",
    })
    request = urllib.request.Request(f"https://commons.wikimedia.org/w/api.php?{query}", headers={"User-Agent": UA})
    pages = json.load(urllib.request.urlopen(request, timeout=30))["query"]["pages"]
    url = next(iter(pages.values()))["imageinfo"][0]["thumburl"]
    time.sleep(2)
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60).read()


def process(raw: bytes) -> bytes:
    image = Image.open(io.BytesIO(raw)).convert("RGB")
    width, height = image.size
    target = SIZE[0] / SIZE[1]
    if width / height > target:
        new_width = int(height * target)
        left = (width - new_width) // 2
        image = image.crop((left, 0, left + new_width, height))
    else:
        new_height = int(width / target)
        top = (height - new_height) // 2
        image = image.crop((0, top, width, top + new_height))
    image = image.resize(SIZE, Image.LANCZOS).filter(ImageFilter.GaussianBlur(1.0))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=78, optimize=True, progressive=True)
    return buffer.getvalue()


def write_css(credits: list[dict]) -> None:
    text = CSS.read_text(encoding="utf-8")
    head = text.split(CSS_START)[0].rstrip() + "\n\n" + CSS_START + "\n"
    rules = [
        f'.lock-bg-{n:02d} {{ background-image: url("lockscreen/{item["file"]}"); }}'
        for n, item in enumerate(credits, 1)
    ]
    CSS.write_text(head + "\n".join(rules) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from-dir", type=Path, help="bereits geladene Originale (Dateinamen wie in der JSON)")
    args = parser.parse_args()
    credits = json.loads(CREDITS.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for item in credits:
        source = args.from_dir / item["file"] if args.from_dir else None
        raw = source.read_bytes() if source and source.exists() else download(item["title"])
        (OUT_DIR / item["file"]).write_bytes(process(raw))
        print(item["file"], item["license"], item["artist"][:40])
    write_css(credits)


if __name__ == "__main__":
    main()
