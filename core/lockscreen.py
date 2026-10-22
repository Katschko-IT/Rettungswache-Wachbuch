"""Hintergrund des Terminal-Sperrbildschirms: ein Bild pro Tag.

Bilder und Nachweise: ``core/lockscreen_credits.json`` (freie Lizenzen von
Wikimedia Commons), erzeugt mit ``scripts/build_lockscreen_backgrounds.py``.
Alle Terminals einer Wache zeigen am selben Tag dasselbe Bild.
"""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

CREDITS_FILE = Path(__file__).resolve().parent / "lockscreen_credits.json"


@lru_cache(maxsize=1)
def backgrounds() -> tuple[dict, ...]:
    try:
        return tuple(json.loads(CREDITS_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return ()


def background_for(day: date) -> dict:
    """Bild des Tages mit CSS-Klasse und kurzem Bildnachweis."""
    items = backgrounds()
    if not items:
        return {"css_class": "", "credit": ""}
    index = day.toordinal() % len(items)
    item = items[index]
    return {
        "css_class": f"lock-bg-{index + 1:02d}",
        "credit": f"{item['artist']} · {item['license']} · Wikimedia Commons",
        **item,
    }
