#!/usr/bin/env python3
"""Screenshots der Oberfläche für Startseite, Vorführung, Projektseite und Folien.

Nur synthetische Demodaten: Läuft gegen einen lokalen Server mit
`DEMO_MODE=true` und `manage.py load_demo_data`. Braucht Playwright
(`pip install playwright && playwright install chromium`).

    python scripts/capture_screens.py [http://127.0.0.1:8765]
    python scripts/sync_design_assets.py   # Kopien für site/ und docs/praesentation/
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "core" / "static" / "core" / "screens"
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
LOGIN = ("demo-admin", "Demo-Passwort-12345")

PHONE = {"width": 390, "height": 844}
DESKTOP = {"width": 1440, "height": 900}

# Name, Pfad, Gerät, Farbschema
SHOTS = [
    ("overview-desktop-light", "/uebersicht/", DESKTOP, "light"),
    ("overview-desktop-dark", "/uebersicht/", DESKTOP, "dark"),
    ("overview-phone-light", "/uebersicht/", PHONE, "light"),
    ("overview-phone-dark", "/uebersicht/", PHONE, "dark"),
    ("handovers-phone-light", "/uebergaben/", PHONE, "light"),
    ("warehouse-desktop-light", "/lager/", DESKTOP, "light"),
    ("fleet-desktop-light", "/fuhrpark/", DESKTOP, "light"),
    ("mpg-desktop-dark", "/mpg/", DESKTOP, "dark"),
    ("more-phone-dark", "/mehr/", PHONE, "dark"),
    ("tasks-phone-light", "/aufgaben/", PHONE, "light"),
]


def save_webp(png: bytes, target: Path, width: int) -> None:
    image = Image.open(io.BytesIO(png)).convert("RGB")
    if image.width > width:
        image = image.resize((width, round(image.height * width / image.width)), Image.LANCZOS)
    image.save(target, "WEBP", quality=82, method=6)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for name, path, viewport, scheme in SHOTS:
            context = browser.new_context(viewport=viewport, color_scheme=scheme, device_scale_factor=2)
            page = context.new_page()
            page.goto(BASE + "/anmelden/")
            page.fill("input[name=username]", LOGIN[0])
            page.fill("input[name=password]", LOGIN[1])
            page.click("main form button[type=submit]")
            page.wait_for_load_state("networkidle")
            page.goto(BASE + path, wait_until="networkidle")
            # Sichtbarer Bildschirmausschnitt wie auf dem Gerät, keine Ganzseite.
            png = page.screenshot(full_page=False)
            save_webp(png, OUT / f"{name}.webp", viewport["width"] * 2)
            print(f"{name}.webp")
            context.close()
        browser.close()


if __name__ == "__main__":
    main()
