#!/usr/bin/env python3
"""Folien als MP4 mit eigener Ambient-Spur.

    python3 docs/praesentation/render_video.py --capture [--theme dark] [OUT.mp4]
        nimmt die acht Folien aus index.html selbst auf (Playwright/Chromium,
        1920 × 1080, ?record=1 ohne Steuerleiste) und erzeugt das Video.

    python3 docs/praesentation/render_video.py FRAMES_DIR [OUT.mp4]
        nutzt bereits vorhandene Bilder slide-1.png … slide-8.png.

Benötigt ffmpeg; für --capture zusätzlich `pip install playwright` und
`playwright install chromium`.
"""

from __future__ import annotations

import math
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

SLIDES = 8
SECONDS = 5
RATE = 44100
WIDTH = 1920
HEIGHT = 1080


def write_music(path: Path, seconds: int) -> None:
    n = RATE * seconds
    melody = [196.0, 246.94, 293.66, 329.63, 392.0, 329.63, 293.66, 246.94]
    with wave.open(str(path), "w") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        for i in range(n):
            t = i / RATE
            pad = 0.11 * math.sin(2 * math.pi * 98 * t) * math.exp(-0.015 * (t % 8))
            idx = int(t / 0.85) % len(melody)
            env = max(0.0, 1.0 - ((t % 0.85) / 0.85))
            tone = 0.16 * math.sin(2 * math.pi * melody[idx] * t) * env
            sample = max(-1.0, min(1.0, pad + tone))
            wav.writeframes(struct.pack("<h", int(sample * 22000)))


def capture(frames_dir: Path, theme: str) -> None:
    """Nimmt jede Folie einzeln auf (index.html#n?record=1)."""
    from playwright.sync_api import sync_playwright

    index = (Path(__file__).resolve().parent / "index.html").as_uri()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, color_scheme=theme)
        for n in range(1, SLIDES + 1):
            page.goto("about:blank")
            page.goto(f"{index}?record=1&theme={theme}#{n}", wait_until="load")
            page.evaluate("Promise.all([...document.images].map(i => i.decode().catch(() => {})))")
            page.wait_for_timeout(200)
            page.screenshot(path=str(frames_dir / f"slide-{n}.png"))
        browser.close()


def main() -> int:
    args = sys.argv[1:]
    theme = "light"
    if "--theme" in args:
        pos = args.index("--theme")
        theme = args[pos + 1]
        del args[pos:pos + 2]
    do_capture = "--capture" in args
    if do_capture:
        args.remove("--capture")
    if not args and not do_capture:
        print("Usage: render_video.py --capture [--theme dark] [OUT.mp4] | FRAMES_DIR [OUT.mp4]", file=sys.stderr)
        return 2
    default_out = Path(__file__).resolve().parent / "wachbuch-vorfuehrung.mp4"
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        if do_capture:
            frames_dir = tmp_path
            capture(frames_dir, theme)
            out = Path(args[0]) if args else default_out
        else:
            frames_dir = Path(args[0])
            out = Path(args[1]) if len(args) > 1 else default_out
        files = sorted(frames_dir.glob("slide-*.png"), key=lambda p: int(p.stem.split("-")[-1]))
        if len(files) < SLIDES:
            print(f"Need {SLIDES} slides, found {len(files)}", file=sys.stderr)
            return 2
        music = tmp_path / "bed.wav"
        write_music(music, SLIDES * SECONDS + 2)
        concat = tmp_path / "list.txt"
        concat.write_text(
            "".join(f"file '{p.resolve()}'\nduration {SECONDS}\n" for p in files[:SLIDES])
            + f"file '{files[SLIDES - 1].resolve()}'\n",
            encoding="utf-8",
        )
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat),
                "-i",
                str(music),
                "-vf",
                f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
                f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                "-movflags",
                "+faststart",
                str(out),
            ],
            check=True,
        )
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
