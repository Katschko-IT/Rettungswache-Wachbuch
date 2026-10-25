#!/usr/bin/env python3
"""App-Icons für Wachwerk erzeugen: blaues Feld, weißes kursives „W“.

Das W ist die Glyphe aus *Inter Display SemiBold Italic* (Rasmus Andersson,
SIL Open Font License 1.1) als Vektorpfad – die Schrift selbst wird nicht
gebraucht. Farbe wie im Wachwerk-Logo (core/static/core/brand-wachwerk.png).

    pip install cairosvg pillow
    python scripts/make_app_icons.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import cairosvg
from PIL import Image

BLUE = "#0D4693"
WHITE = "#FFFFFF"
# Glyphe „W“, Schriftkoordinaten (y nach oben), Einheiten pro Geviert 2048.
W_PATH = "M327 0H627L997 862C1032 944 1066 1033 1103 1132C1108 1033 1113 944 1121 862L1206 0H1505L2155 1490H1869L1539 687C1488 558 1439 429 1392 301C1386 429 1379 558 1368 687L1298 1490H1019L681 687C627 557 577 427 528 296C524 427 519 557 510 687L446 1490H172Z"
W_BOUNDS = (172, 0, 2155, 1490)


def icon_svg(size: int, glyph_width: float, *, background: bool = True, radius: float = 0.0) -> str:
    """SVG mit dem W zentriert; glyph_width = Breite des W relativ zur Kantenlänge."""
    xmin, ymin, xmax, ymax = W_BOUNDS
    scale = glyph_width * size / (xmax - xmin)
    cx = cy = size / 2
    tx = cx - (xmin + xmax) / 2 * scale
    ty = cy + (ymin + ymax) / 2 * scale
    rect = ""
    if background:
        r = radius * size
        rect = f'<rect width="{size}" height="{size}" rx="{r}" ry="{r}" fill="{BLUE}"/>'
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
        f'{rect}<path d="{W_PATH}" fill="{WHITE}" transform="translate({tx:.3f} {ty:.3f}) scale({scale:.6f} {-scale:.6f})"/></svg>'
    )


def render(svg: str, target: Path, size: int, *, opaque: bool = False) -> None:
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=size, output_height=size)
    image = Image.open(io.BytesIO(png)).convert("RGBA")
    if opaque:
        # App Store und apple-touch-icon: keine Transparenz.
        flat = Image.new("RGB", image.size, BLUE)
        flat.paste(image, mask=image.split()[3])
        image = flat
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, "PNG", optimize=True)
    print(target)


ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / "core" / "static" / "core" / "icons"


def main() -> None:
    # Volle Fläche: Betriebssysteme runden selbst ab (iOS, Android, Desktop).
    full = icon_svg(1024, 0.58)
    render(full, ICONS / "icon-192.png", 192, opaque=True)
    render(full, ICONS / "icon-512.png", 512, opaque=True)
    # Maskable: das W bleibt innerhalb der sicheren Zone (Kreis mit 80 %).
    render(icon_svg(1024, 0.50), ICONS / "icon-maskable-512.png", 512, opaque=True)
    # Favicon der Projektseite (site/) als Vektor.
    favicon = ROOT / "site" / "assets" / "favicon.svg"
    favicon.write_text(icon_svg(64, 0.58, radius=0.1875) + "\n")
    print(favicon)


if __name__ == "__main__":
    sys.exit(main())
