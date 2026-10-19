# Statische Projektwebseite – Rettungswache-Wachbuch (Wachwerk)

Quelldateien der öffentlichen Projektseite. Die Seite beschreibt den tatsächlichen
Funktionsstand, die Betriebsgrenzen und die Installation. Sie ist keine
Produktionsfreigabe und enthält keine erfundenen Betreiber- oder Compliance-Angaben.

## GitHub Pages

Projektadresse: https://katschko-it.github.io/Rettungswache-Wachbuch/

Die Veröffentlichung erfolgt über `.github/workflows/pages.yml`. Dazu muss im
kanonischen Repository `Katschko-IT/Rettungswache-Wachbuch` unter Settings → Pages
**GitHub Actions** als Quelle aktiviert sein. Ein Quellordner `/site` wird bei
„Deploy from a branch“ nicht unterstützt; dort sind nur `/` oder `/docs` möglich.

Der Workflow prüft `site/`, stellt ausschließlich `index.html`, `styles.css`,
`.nojekyll` und `assets/` als Artefakt bereit und veröffentlicht über die
Pages-Actions. Tests und dieses README werden nicht mit ausgeliefert.
Relative Assetpfade unterstützen den Repository-Unterpfad. Keine `CNAME`-Datei,
keine eigene Domain, keine Datenbank und kein Backend gehören zum Pages-Artefakt.
Die tatsächlich veröffentlichte URL und der Deploymentstatus sind im Workflow
und in den Repository-Pages-Einstellungen zu prüfen.

## Inhalte und Richtlinien

- HTML/CSS ohne JavaScript, CDN oder Analytics.
- Lokale Source-Sans-3-Schriften unter `assets/fonts/`, mit SIL-OFL-Lizenztext.
- Designregeln aus `docs/DESIGN-SYSTEM.md`.
- Funktionsaussagen aus README, Architektur, Betriebs- und Sicherheitsdokumentation.
- Keine Demo-Werbeaufmachung und keine erfundenen Rechts-/Zertifizierungszusagen.
- Servergetrenntes Handy, Client-Outbox und Synchronisierung sind nicht implementiert.

## Screenshots

Die WebP-Bilder unter `assets/screenshots/` stammen aus der lokal gestarteten App
mit synthetischen Konten und einer getrennten Testdatenbank. Es sind keine Montagen
oder fremden Bildschirmbilder. Personen, Wachen und Vorgänge sind frei erfunden.
Anmeldetoken, QR-Geheimnisse, Einladungslinks und die Testdatenbank werden nicht
veröffentlicht. Aufnahme- und Browserprüfprotokolle werden lokal aufbewahrt.

## Lokale Prüfung

```bash
python3 site/tests/check_site.py
python3 -m http.server --bind 127.0.0.1 --directory site 8899
```

Zusätzlich im Browser Desktop und echte 390-CSS-Pixel-Breite prüfen: Layout,
Tastatur-/Touchbedienung, lokale Assets, Links und Konsolenfehler. Eine
Browseremulation ersetzt keine Abnahme auf realen Geräten.
