# Finale Deployment-Abnahme

## Laufender Stand

- Echte Demo: https://wachbuch-demo.46-225-106-237.sslip.io/ , App-Commit `a69c8d385b4db234a24233ecc509921d46eb5387`.
- Separate Produktvorschau: https://wachbuch-preview.46-225-106-237.sslip.io/ , Export aus demselben Commit; zusätzlich explizite Les-/Verzeichnisrechte für den rootless Caddy.
- Keine Branch-Protection-, Firewall- oder globalen Proxy-Änderungen. Demo-Sicherheitsmiddleware und Loginformular bleiben aktiv.

## Nachweise

- Django: 325 Tests erfolgreich, ein Skip. Log: `/opt/data/cache/presentation-qa/demo-upgrade-tests.log`.
- Beide öffentlichen Seiten: sieben Viewports, Smartphone-Wechsel, Kenntnisnahme/Aufgaben-Trennung, Reset, Tastatur, 200 % Textgröße, reduzierte Bewegung und No-JS bestanden. Logs: `demo-public-browser.log`, `preview-public-browser.log` im selben QA-Verzeichnis.
- Vorschau: 19 veröffentlichte Dateien inkl. HTML, CSS, JavaScript, SVG-Icons und Fonts mit HTTP 200 und Hashgleichheit zu den geprüften lokalen Dateien. Nachweis: `public-preview-hashes.json`.
- Echte Demo: normaler HTTPS-Formularlogin mit CSRF; neun authentifizierte Lesepfade HTTP 200. Keine fachlichen Datensätze angelegt oder geändert. Nachweis: `demo-public-auth-proof.log`.
- Vor Neustart nachgewiesen: 47 bestehende Tabellen mit identischen Werten in allen bisherigen Spalten, sechs Nutzer, SQLite-Integrität `ok`. Kein erneuter Seed-Lauf. Betriebsnachweis: `/opt/data/apps/wachbuch-demo/deployment-evidence.json`.

## Sicherungen

- Echte Demo: `/opt/data/apps/wachbuch-demo/backups/deployment-20261011T071059Z`.
- Vorschau-Deployment: `/opt/wachbuch-presentation-preview/backups/20261011T071308Z` auf Hetzner.
- Vorschau-Rechtereparatur: `/opt/wachbuch-presentation-preview/backups/asset-permissions-20261011T080013Z` auf Hetzner.

## Fehlerursache und dauerhafte Korrektur

`/srv/static` war im extrahierten Build-Verzeichnis mit Modus 750 angelegt. Der Caddy-Prozess läuft als UID/GID 65532 und konnte dort nicht hinein: HTTP 403 für Bootstrap und Icons. Der Docker-Build setzt jetzt `RUN chmod -R a+rX /srv` vor `USER 65532:65532`. Es wurden nur öffentliche statische Dateien lesbar gemacht; read-only rootfs, cap_drop ALL und no-new-privileges bleiben unverändert.

Hermes-Freigabefenster im aktiven Standardprofil: `approvals.timeout` von 60 auf 600 Sekunden erhöht. `approvals.mode: manual` und alle übrigen Einstellungen unverändert. Offizielle Konfigurations-CLI, Datenvergleich und Runtime-Leser bestätigten die Änderung; keine Deaktivierung von Sicherheitsprüfungen.

Diese Abnahme betrifft Demo und Präsentation, nicht Storepublishing oder eine Produktiv-/medizinische Sicherheitsfreigabe.
