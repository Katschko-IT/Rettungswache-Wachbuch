# Wachwerk-Vorführung (Folien)

Die Vorführung in der Web-App liegt unter **`/vorfuehrung/`** (CSP-konform,
Musik nur nach Klick). Dieses Verzeichnis ist die eigenständige Fassung
derselben acht Folien für Video-Export und Vorträge ohne laufenden
Django-Prozess. Sie wird **nicht** über die App ausgeliefert.

## Aufbau

- `index.html` – acht Folien, 16:9, ohne Inline-Skripte und -Styles
- `slides.css` – nur die Bühne; Maßstab 80 × 45 rem (bei 1920 × 1080 ist 1 rem = 24 px)
- `slides.js` – Blättern, Fortschritt, Musik
- `design/` – Kopien von `tokens.css`, `fonts.css`, `public.css`, Schrift und
  Aufnahmen aus `core/static/core/`. Nicht von Hand ändern, sondern
  `python scripts/sync_design_assets.py` ausführen.

Die Folien folgen der Design-Sprache „Wachbuch Klar 2“: echte Aufnahmen der
Oberfläche (synthetische Daten der „Rettungswache Nord“) statt Stockfotos,
Warnmarkierung nur als Kante oben und als Rahmen der Produktgrenze, Farbe nur
für Zustand.

## Live zeigen

```bash
python3 -m http.server 8772 --directory docs/praesentation
```

Dann `http://127.0.0.1:8772/` öffnen. Die Datei funktioniert auch direkt per
Doppelklick (`file://`).

- Pfeiltasten, Leertaste oder **Weiter** / **Zurück**
- `#3` öffnet Folie 3
- `?autoplay=1` blättert automatisch
- `?theme=dark` oder `?theme=light` erzwingt Nacht- bzw. Tagansicht
  (sonst folgt die Ansicht dem System)
- `?record=1` blendet die Steuerleiste aus
- **Musik** startet eine kurze, eigens erzeugte Ambient-Figur (keine fremden
  Aufnahmen, keine GEMA-pflichtigen Titel)

## Video erzeugen

```bash
pip install playwright && playwright install chromium   # einmalig
python3 docs/praesentation/render_video.py --capture                # hell
python3 docs/praesentation/render_video.py --capture --theme dark   # Nachtdienst
```

nimmt jede Folie in 1920 × 1080 auf und schreibt
`docs/praesentation/wachbuch-vorfuehrung.mp4` (5 s je Folie, lokal, nicht für
Git vorgesehen). Benötigt `ffmpeg`. Mit eigenen Bildern:
`render_video.py FRAMES_DIR [OUT.mp4]` (erwartet `slide-1.png` … `slide-8.png`).

## Inhaltliche Grenze

Die Folien nennen ausdrücklich: internes Wachbuch, kein Einsatzleit-,
Patientendokumentations- oder Dienstplanungssystem, Vorproduktion ohne
Produktionsfreigabe.
