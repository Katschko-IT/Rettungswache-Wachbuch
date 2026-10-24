# Changelog

## Unveröffentlicht

Docker-Installation für alle: `install.sh`, vorgefertigte Images, `wachbuch`-CLI.

- **Installation mit einem Befehl**: `curl -fsSL …/install.sh | sh` prüft Docker,
  Compose (ab 2.20), Architektur (amd64/arm64), RAM und Ports, legt
  `/opt/wachbuch` bzw. `~/wachbuch` an, erzeugt eine `.env` mit unabhängigen
  Zufallswerten (inkl. `CRYPTO_MASTER_KEY`, `RATELIMIT_KEY_SALT`,
  Einrichtungscode) und startet alles mit `up --wait`. Betriebsarten `local`,
  `lan` (Caddy mit eigener CA) und `domain` (Let's Encrypt); wiederholbar ohne
  Verlust von Geheimnissen.
- **Vorgefertigte Images** `ghcr.io/katschko-it/rettungswache-wachbuch`,
  `-backup` und neu `-db` (PostgreSQL mit eingebautem Rollen-Init und
  `postgresql.conf`) für amd64 und arm64; kein Git-Checkout und keine
  Bind-Mounts mehr nötig. Lokaler Build über `compose.build.yml`.
- **`wachbuch`-CLI** im Installationsordner: `status`, `logs`, `backup`,
  `restore`, `update`, `setup-code`, `start`, `stop`, `uninstall`.
- Optionaler **Caddy-TLS-Proxy** im Compose-Profil `https`.
- **notify-worker** lag in keinem Netz mit der Datenbank und wirkte trotzdem
  gesund; jetzt im Netz `app-db`, gehärtet, mit Heartbeat-Healthcheck und
  Fehlercode nach wiederholten Datenbankfehlern.
- **PostgreSQL** startet auf 1–2-GB-Systemen: kleine Standardwerte
  (128MB/50/64MB), Tuning über `.env`, `shm_size` 256 MB.
- **Healthcheck** scheitert nicht mehr an einem eingeschränkten
  `ALLOWED_HOSTS` (Host `localhost`, Loopback immer erlaubt).
- **Backup**: Offsite-Ziel als Host-Ordner (`BACKUP_OFFSITE_DIR`), GnuPG im
  read-only Container (öffentlicher Schlüssel aus `BACKUP_GPG_KEY_DIR`), kein
  Klartext-Offsite ohne Schlüssel, keine Dump-Serien nach Fehlern oder Neustarts.
- `grant_database_access` legt fehlende Rollen (z. B. `rwsth_push` auf alten
  Volumes) an; Push-Rollen-Defaults einheitlich.
- `.env`-Werte, die bisher nicht ankamen, werden durchgereicht
  (`PUSH_ALLOWED_ENDPOINT_HOSTS`, `RATELIMIT_KEY_SALT`, `ERROR_EVENT_*`,
  `APP_VERSION`, `GUNICORN_*`); Gunicorn nutzt `config/gunicorn.py`.
- Doku: „In 5 Minuten installieren“ im README, `docs/DEPLOYMENT.md` neu
  (Setup-Assistent als einziger Erstadmin-Weg, korrigierte nginx-/Caddy-Beispiele,
  Traefik-/Helm-Beispiele mit nie veröffentlichtem Tag entfernt).
- CI startet alle Dienste mit `up --wait`, prüft Worker-Gesundheit, Backup und
  Restore-Probe, führt `install.sh` zweimal aus und prüft Skripte mit shellcheck.

Gesamtreview vom 24.10.2026 (Details: `docs/REVIEW-2026-10-24.md`).

- Kontoaktivierung im Browser repariert: Die Seite sendete
  `Referrer-Policy: no-referrer`, Browser schickten daraufhin `Origin: null`
  und die CSRF-Prüfung lehnte das Formular ab – neue Konten ließen sich nicht
  aktivieren. Jetzt `same-origin` (kein Referer an fremde Seiten).

- Sicherheit: `MFA_REQUIRED` wird jetzt durchgesetzt; das Dienstkonto
  „Wachenterminal“ kann keine Neuigkeiten mehr quittieren; Admins koppeln keine
  Handys für Personen mit Zwei-Faktor-Anmeldung; Terminal-Fehlversuche werden
  zuverlässig gezählt; Client-IP hinter dem Reverse-Proxy aus dem vom Proxy
  angehängten Eintrag (auch für die Anmeldesperre).
- API: Mängelliste fachlich sortiert (offen vor erledigt, dringend vor normal)
  und paginiert (`limit`, `offset`, `next`, `active=1`); Kalender liefert
  laufende Termine und die Beschreibung; Kaffeekasse liefert `scope`;
  Rate-Limits pro Person mit `Retry-After`; JSON ohne Objekt ergibt 400 statt 500.
- Web: Checklisten-Abschluss schaltet das Prüfintervall weiter; Anhänge an
  Mängeln mit denselben Grenzen wie in der App; unmögliche Datumswerte ergeben
  eine Fehlermeldung statt eines Serverfehlers.

Verkehrslage je Wache konfigurierbar statt fest auf Gütersloh/Steinhagen
verdrahtet (portiert aus Draft-PR #116). Autobahnen, Umkreis, Warngebiete
(BBK/NINA), kommunale Quellen und Koordinaten der Wache stehen in den
Einstellungen, Straßen, Umkreis und Warngebiete auch in der Ersteinrichtung.
Ohne Koordinaten keine Autobahnquelle, ohne Warngebiet oder Ort keine Warnungen;
Straßen werden auf `A2`/`B61`-Form geprüft (höchstens 6); der Cache-Schlüssel
enthält einen Konfigurations-Hash. Die Parser für Steinhagen und den Kreis
Gütersloh sind nur noch je Wache zuschaltbar (Standard aus). Bestehende Wachen
mit Verkehrslage behalten ihre bisherigen Werte (Migrationen 0055/0056); der
feste Ersatzstandort entfällt, fehlende Koordinaten müssen nachgetragen werden.

Abhängigkeiten und Basis-Images auf den Stand vom 24.10.2026 gebracht.

- Python-Pakete: Django 6.1.2, psycopg 3.3.6, cryptography 50.0.2,
  pywebpush 2.5.0, webauthn 3.0.1, certifi 2026.10.23, Ruff 0.17.2; alle
  Lockfiles mit Hashes per `uv pip compile` neu erzeugt.
- Images: Python 3.14.9 auf Debian 13 (`slim-trixie`), PostgreSQL 17.11,
  Redis 8.8.3. Das Backup-Image nutzt jetzt dieselbe PostgreSQL-Hauptversion
  (17) wie die Datenbank, damit Dumps mit `pg_restore` der Datenbank
  zurückspielbar sind. Die Datenbank bleibt bewusst auf Version 17; ein Sprung
  auf 18 braucht einen eigenen Upgrade-Weg für bestehende Volumes.
- GitHub Actions auf aktuelle Releases mit SHA-Pin, `setup-uv` und
  `setup-node` erstmals gepinnt, CodeQL-Upload auf v4; die CI testet mit
  Python 3.14 wie das ausgelieferte Image.
- Test `test_display_data_collects_urgent_tasks` hing an einem festen Datum und
  schlug ab dem 24.10.2026 fehl.

Ersteinrichtung für den Raspberry Pi überarbeitet.

- Der Touch-Bildschirm öffnet vor der Einrichtung direkt den Assistenten statt
  einer Textmeldung „nicht registriert“; ein nicht registriertes Gerät nach der
  Einrichtung zeigt eine Anleitung.
- Einrichtungscode statt „Bootstrap-Token“: `setup-pi.sh` erzeugt einen
  abtippbaren Code in Vierergruppen; Groß-/Kleinschreibung, Leerzeichen und
  Bindestriche werden bei der Prüfung ignoriert.
- Assistent mit optionalem Schritt *Wachenterminal*: Wachen-Code festlegen und
  dieses Gerät als Terminal einrichten (am Kiosk vorbelegt).
- Neue Abschlussseite mit den nächsten Schritten (Besatzung einladen, Terminal,
  Handys, Ausstattung, Einrichtungscode entfernen).
- Team → Wachenterminal: „Dieses Gerät als Terminal einrichten“ für den Browser,
  in dem man gerade angemeldet ist.
- Startseite und Anmeldung weisen auf eine ausstehende Ersteinrichtung hin.
- Klarere Texte ohne Fachjargon; der Benutzername `wachenterminal-…` ist für das
  Dienstkonto reserviert.
- Eigene Bildschirmtastatur für den Kiosk (QWERTZ, Umlaute, Ziffernblock für
  Zahlenfelder): erscheint nur beim Antippen eines Eingabefelds, nicht bei
  angeschlossener Tastatur oder Maus; nur am Kiosk und auf registrierten Terminals.
- Sperrbildschirm: WLAN-QR-Code („① WLAN verbinden“) neben dem App-QR, oben rechts
  (überdeckte auf 14″ die Karten); `setup-pi.sh` trägt SSID und Passwort ein.
- Kiosk-Zoom passend zur Bildschirmgröße (EDID, Ziel ≈ 110 CSS-Pixel pro Zoll;
  `KIOSK_SCALE` überschreibt).
- Neue Abhak-Liste für den ersten Pi-Aufbau (`docs/PI-ABNAHME.md`). Korrektur der
  Pi-Doku: Backups liegen im Docker-Volume `backups-data`, nicht in `backups/`;
  Befehl zum Kopieren auf einen USB-Stick ergänzt.
- Marktvergleich mit RETTpro und Optimierungsbedarf (`docs/MARKTVERGLEICH-RETTPRO.md`).
- Touch-Audit über 70 Seiten auf Handy, Tablet, 14″ und 22″: Modulzeilen und
  zweispaltige Formulare laufen auf dem Handy nicht mehr seitlich aus dem Bild;
  Felder, kleine Knöpfe, Sortierknöpfe, Sprachwahl, Kästchen-Zeilen und
  Tabellen-Links haben mindestens 44 px Trefferfläche; „Zurück“-Links sind Knöpfe.

## 0.24.0 - 2026-10-22

Review-, Debugging- und UX-Release nach dem Zwei-Repo-Review (R-025, Details in
`docs/REVIEW-2026-10-22.md`). Keine Produktionsfreigabe.

- Betrieb: Jede Seite lud bisher im Hintergrund die Display-Daten und hielt einen
  Livestream (Server-Thread) offen; entfernt.
- Datumsfelder in Bearbeitungsformularen erschienen leer und löschten beim
  Speichern HU-/STK-/UVV-Fristen; behoben.
- Sperr- und Exportzeiten werden in Ortszeit statt UTC angezeigt.
- Die Orga-Seite legt keine medizinischen Muster-SOPs mit Dosierungen und keine
  regional falschen Notrufnummern mehr an; der Fuhrpark erfindet keine Kennzeichen.
- Dienstanweisungen wurden als „quittiert“ angezeigt, obwohl sie es nicht waren.
- Fuhrpark: Fahrzeuge werden nach der Desinfektions-Einwirkzeit nicht mehr
  automatisch auf Status 1 gesetzt. Die Besatzung (Schichtübernahme der letzten
  24 h und die desinfizierende Person) wird benachrichtigt und gibt selbst frei.
  Neuer Dienst `notify-worker`, persönlicher Posteingang („Für dich“), Web-Push
  und App-Schnittstellen (`/api/v1/benachrichtigungen/`, `/api/v1/fahrzeuge/sperren/`,
  `/api/v1/push/geraete/`); natives Push-Relay vorbereitet (`docs/PUSH-RELAY.md`).
- Übersicht zeigt den Handlungsbedarf aller aktiven Fachmodule.
- Modulseiten nutzen ein einheitliches Komponentenvokabular (Kacheln, Tabellen,
  Hinweise, Buttons) und klare Beschreibungen.
- Neue öffentliche Startseite mit allen Modulen, Grundsätzen und Einstiegsschritten.
- Demo-Daten umfassen jetzt auch Fahrzeuge, Medizingeräte, Material und eine
  Dienstanweisung.
- Medizingeräte: Gescannte Selbsttest-Texte werden nicht mehr „ausgewertet“
  (ein „OK“ im Text galt als bestandene Kontrolle). Jeder Prüfpunkt wird von der
  prüfenden Person bestätigt. Eine bestandene Kontrolle hebt keine Sperre mehr
  auf; freigegeben wird nach Abschluss aller verknüpften Mängel durch
  Schichtleitung/Admin. Der Status im Medizinproduktebuch und unter „Geräte &
  Fahrzeuge“ ist identisch. Migration `0052_mpg_device_locks`.
- Wachenterminal: Touch-Bildschirm auf der Wache. Gesperrt läuft das
  Wachen-Display; Antippen öffnet einen runden Ziffernblock für den
  gemeinsamen vierstelligen Wachen-Code (nur an registrierten Terminals,
  stufenweise Sperre nach Fehlversuchen). Der Alltagsmodus zeigt Übergaben,
  Termine, Müllabfuhr, Wetter, Tages-, Wochen- und Monatsaufgaben und erreicht
  nur Alltagsbereiche; Einträge stehen unter dem Dienstkonto „Wachenterminal“.
  Sperren nach Inaktivität. Admins verbinden Handys der Besatzung per
  Einmal-QR mit dem persönlichen Konto (`/api/v1/token/kopplung/`). Aus, bis
  `TERMINAL_ENABLED=true`. Migration `0053_wachenterminal`.
- Sperrbildschirm im iOS-Stil: große Uhr, Glas-Karten (Wetter, Übergaben,
  Aufgaben, Termine, Müll) und Fahrzeug-Statuszeile; täglich wechselndes,
  leicht unscharfes Rettungsdienst-Foto aus 36 frei lizenzierten Bildern
  (CC0/CC BY/CC BY-SA, Wikimedia Commons; `docs/BILDNACHWEISE.md`,
  `scripts/build_lockscreen_backgrounds.py`).
- Raspberry Pi 4 als Wachen-Server: `deploy/pi/` (eigenes WLAN, lokales
  Zertifikat mit Fingerabdruck im Verbindungs-QR, TLS-Proxy, Speichergrenzen,
  Kiosk-Browser). arm64-Image jetzt mit QEMU gebaut; fehlende arm64-Hashes
  für `multidict` ergänzt. Anleitung `docs/PI-WACHENTERMINAL.md`.

- Fachmodule funktionieren unter der eigenen CSP: Modals, Scanner, Live-Suche,
  Filter, Druck und Löschrückfragen laufen über `core/static/core/ui.js`;
  Layout liegt in `core/static/core/modules.css`. Die Reihenfolge der
  Navigationsleiste greift jetzt auch im Browser.
- Scanner öffnen nur Adressen derselben Origin; Kamera nur auf den
  Scanner-Seiten erlaubt.
- Wachen-Display: Livestream endet nach fünf Minuten oder bei Widerruf.
- Fahrzeug-Auto-Freigabe nach Einwirkzeit atomar und im Audit-Log.
- Geocoding fällt bei Netzausfall sofort auf Standardkoordinaten zurück.
- API: Fehlercodes `conflict`, `payload_too_large`,
  `unsupported_media_type`; Token-Widerruf auch ohne aktive Mitgliedschaft;
  PDF-Anhänge für Mängel.
- „Mehr“: deaktivierte Module erscheinen nicht mehr (auch nicht im Quelltext),
  Texte ohne Einsatz-/Leitstellen-Versprechen.
- Englischer Katalog vollständig; zerlegte Sätze als `blocktranslate`.
- Tests laufen ohne externe Netzverbindungen (`core/test_runner.py`).
- Client-Spiegel `clients/wachbuch-mobile/` auf den aktuellen Client-Stand
  gebracht.

## 0.23.0 - 2026-10-22

Großes Modul- und Automatisierungs-Release für den Rettungsdienstbetrieb. Neue Fachmodule (Fuhrpark, Lager, MPG, Organisation, Wachen-Display), intelligente Daten-Automatisierung und komplett überarbeitetes „Mehr“-Menü. Keine Produktionsfreigabe.

- **Rettungsdienst-Fachmodule**:
  - **🚑 Fuhrpark & Hygiene**: Mobiles Fahrzeug-Cockpit mit taktischem BOS-Status (1–6), Telemetrie (Kraftstoff %, AdBlue %, O₂-Druck in bar), Express-Schichtübernahme (3 Min.), VAH-Wischdesinfektion, Mängeleskalation in Werkstattstatus sowie Fristenüberwachung (HU § 29 StVZO, UVV DGUV 70, 10g-Tragentisch nach DIN EN 1789).
  - **📦 Lager & Material (FEFO-Apotheke)**: Chargenverfolgung (Lot, PZN, GTIN), Verfallsüberwachung nach First-Expired-First-Out, dynamische Kühlketten-Regel (2–8 °C mit Out-of-Fridge Timer, z. B. 12 Wochen für Rocuronium) und sofortige Quarantäne gesperrter Chargen bei BfArM-Rückrufen.
  - **🩺 MPG & Medizingeräte**: Digitales Medizinproduktebuch nach § 13 MPBetreibV mit Risikoklassen (I bis III), automatischer STK/MTK-Fristenampel (Anlage 1 & 2), 1-Tap Funktionskontrollen, revisionssicheren Wartungsnachweisen und digitaler § 10 MPBetreibV Einweisungsmatrix (inkl. Gruppenschulungen).
  - **🏢 Organisation & Desk**: Revisionssichere Dienstanweisungen, Hygienepläne und medizinische SOPs mit Versionskontrolle (`vX.Y`), SHA-256 Integritätsprüfung und persönlicher Mitarbeiter-Lesequittierung sowie Notfall-Kurzwahlliste.
  - **🖥️ Wachen-Display**: Vollbild-Dashboard für Monitore/TV in Bereitschaftsraum und Fahrzeughalle mit Live-Uhrzeit, Wetter, aktuellen Terminen, BOS-Fahrzeugstatus, MPG-Warnungen und konfigurierbarem Live-Ticker.
- **Intelligente Software-Automatisierung**:
  - **Auto-Desinfektionsfreigabe**: Entsperrt Fahrzeuge nach Ablauf der VAH-Einwirkzeit vollautomatisch und setzt sie ohne manuellen Klick auf Status 1 (Frei Wache).
  - **Automatischer Nachbestellschein & Wachbuch-Task**: Erkennt Unterschreitungen des Mindestbestands, berechnet die Differenz zum Sollbestand, generiert einen Apotheken-Bestellschein (CSV) und legt auf Knopfdruck eine synchronisierte Tagesaufgabe im Wachbuch an.
  - **1-Scan Express-Umlagerung**: Bucht Material aus dem Zentrallager per Scan direkt auf ein Zielfahrzeug um; aktualisiert bei kühlpflichtigen Medikamenten automatisch das Out-of-Fridge Datum und das berechnete Verfallsdatum.
  - **QR-Selbsttest-Ingest (corpuls3 & Weinmann MEDUMAT)**: Liest den Prüfcode vom Gerätedisplay ein, prüft Baugruppen und Defibrillationsenergie (200 J) und dokumentiert die Funktionskontrolle ohne Formularausfüllen.
- **Wachenzentrale & Redesign des „Mehr“-Menüs**:
  - Das Menü `/mehr/` wurde von einer unstrukturierten Liste in eine moderne, responsive 4-Kategorien-Wachenzentrale mit Card-Grids umgebaut:
    1. *🚑 Einsatz & Rettungsdienst-Fachmodule*
    2. *📋 Wachbetrieb & Alltagsorganisation*
    3. *📢 Kommunikation & Wissen*
    4. *⚙️ Wachenverwaltung & Sicherheit*
  - Schnelle Live-Suche mit Client-Filterung zur sofortigen Auffindbarkeit aller 28 Module und Funktionen.
  - Kennzeichnung von Modulen mit Status-Badges („In Leiste“).
- **Einheiten-Konsistenz & Robustheit**:
  - Konsistente Ausrichtung aller physikalischen Maßeinheiten (`km`, `%`, `bar`, `Min.`, `Joule`, `mbar/hPa`, `°C`, `mm`, `d`, `PZN`, `GTIN`).
  - Crash-resistenter Kontext-Prozessor `current_membership` bei fehlerhaften Host-Headern.
- **Tests**: Über 49 Modultests für Navigation, Fuhrpark, Lager, MPG, Organisation und Dashboards erfolgreich validiert.

## 0.22.0 - 2026-10-22

Pilotstand mit bundesweiten Feiertagen, Wettermodul in den Einstellungen und bereinigter Navigationsleiste. Keine Produktionsfreigabe.

- Navigation: Monitor-Button aus der Kopfleiste entfernt; Wachen-Display bleibt unter „Mehr“ und über Display-Tokens erreichbar.
- Feiertage: Gesetzliche Feiertage für alle 16 deutschen Bundesländer im Wachenkalender und ICS-Export wählbar (Baden-Württemberg, Bayern, Berlin, Brandenburg, Bremen, Hamburg, Hessen, Mecklenburg-Vorpommern, Niedersachsen, Nordrhein-Westfalen, Rheinland-Pfalz, Saarland, Sachsen, Sachsen-Anhalt, Schleswig-Holstein, Thüringen).
- Wetter: Modul „Wettervorhersage aktiviert“ in den Wacheneinstellungen ergänzt; Adresse (Straße, PLZ, Ort) wird hinterlegt und per Open-Meteo geocodiert.
- Tests: Neue Testsuite für Feiertage aller Bundesländer, Navigation und Wetter-Konfiguration (core.test_settings_holidays_weather).

## 0.21.0 - 2026-10-20

Pilotstand mit Verkehrslage auf dem Wachen-Display. Keine Produktionsfreigabe.

- Verkehrslage: Das Display zeigt Baustellen und Sperrungen rund um die Wache
  in einer eigenen Leiste – mit Quelle, Abschnitt, Zeitraum von Anfang bis Ende
  und Entfernung in Kilometern. Vollsperrungen tragen ein rotes Kennzeichen,
  Einschränkungen eine orange Kante.
- Quellen ohne Schlüssel: Autobahn GmbH (A2/A33 im Umkreis), Gemeinde
  Steinhagen (Straßenbau im Ortsgebiet), Kreis Gütersloh (Bauabschnitte an
  Kreisstraßen) und die Bevölkerungswarnungen des BBK.
- Zeiträume werden aus dem Fließtext gelesen, weil die Quellen keine
  strukturierten Datumsfelder liefern; Jahreswechsel und Tagesüberlauf sind
  berücksichtigt.
- Fällt eine Quelle aus, zeigt die Anzeige die übrigen Quellen. Es werden keine
  Ersatzdaten erfunden. Ergebnisse werden zehn Minuten zwischengespeichert.
- Einschaltbar über die Wachen-Einstellungen (Verkehrslage).
- Tests: 22 neue Prüfungen für Parser, Sperrerkennung, Radiusfilter,
  Quellenausfall und Zwischenspeicher (Gesamt 790).

## 0.20.0 - 2026-10-20

Pilotstand mit Wachen-Display für Monitor und Fernseher. Keine
Produktionsfreigabe.

- Wachen-Display: Vollbildansicht mit Uhrzeit, Datum, Wachenname, heutigen
  Terminen, Tagesaufgaben mit Fortschritt, Wetter, Geburtstagen und der Zahl
  dringender Übergaben. Auf einen Blick lesbar aus mehreren Metern Entfernung.
- Display-Start über ein Monitor-Symbol in der Kopfleiste; Esc beendet die
  Anzeige, ein Knopf startet das echte Vollbild. Der Bildschirm bleibt über die
  Wake-Lock-Schnittstelle aktiv, solange der Browser das zulässt.
- Anzeigelinks: In den Einstellungen lassen sich benannte Display-Token
  erzeugen und jederzeit widerrufen. Gespeichert wird nur ein SHA-256-Hash, der
  Klartextlink erscheint genau einmal. Der Zugang ist rein lesend und liefert
  ausschließlich aggregierte Daten ohne Personendetails aus Übergaben.
- Hintergründe: achtzehn ruhige Full-HD-Motive in unterschiedlichen Farbtönen,
  auf gleichmäßige Helligkeit kalibriert und im Wechsel alle fünf Minuten.
- Sprache: Das Display folgt der eingestellten Sprache (Deutsch/Englisch).
- Tests: Wetterdaten und die Sichtbarkeit der Tagesaufgaben werden
  zeitunabhängig geprüft; die Wettertests hingen zuvor an festen Kalenderdaten.

Ausdrücklich nicht enthalten: schreibfähiger Offlinebetrieb ohne Server,
vollständige Übersetzung von Datenbank-Altbeständen sowie reale Warenbetriebs-,
TLS- und Geräteabnahme.

## 0.19.0 - 2026-10-19

Pilotstand mit Anhängen, Neuigkeiten und konfigurierbarer Navigation. Keine
Produktionsfreigabe.

- Anhänge: Übergaben, Fehlermeldungen, Pinnwand und Neuigkeiten nehmen Bilder
  (JPEG/PNG/WebP) und PDF bis 5 MiB auf; Dateien bleiben unverändert,
  wachengebunden und unveränderlich abgelegt.
- Neuigkeiten: eigener Bereich mit Anhang, persönlicher Quittung je Person und
  automatischer Archivierung, sobald alle aktiven Personen gelesen haben.
- Wachenchat: Einladungslink zur Signal-Gruppe samt QR-Code, je Aufruf neu
  erzeugt; die App speichert keine Chatnachrichten.
- Darstellung: eine einzige sortierbare Liste aller Bereiche. Ein Häkchen holt
  einen Bereich in die obere Leiste, ohne Häkchen bleibt er unter „Mehr“ – in
  derselben Reihenfolge. Übersicht, Übergaben, Mehr und Hilfe sind fest.
- Kopfzeile und Marke: Wachwerk-Logo, Wachenname mittig, Sprachwahl in den
  Kontoeinstellungen.
- Installationshinweis erscheint nur bei Bedarf und lässt sich dauerhaft
  schließen.
- Kalender: farbige Balken liegen außerhalb des Datumsfelds, Agenda-Zeilen
  brechen bei schmalen Anzeigen sauber um.
- Wiederholte Vorlagenaufgaben erzeugen wieder die vorgesehene Anzahl je Tag.

Ausdrücklich nicht enthalten: schreibfähiger Offlinebetrieb ohne Server,
vollständige Übersetzung von Datenbank-Altbeständen sowie reale Warenbetriebs-,
TLS- und Geräteabnahme.

## 0.18.0 - 2026-10-19

Pilotstand für lokalen Betrieb und Praxistest. Keine Produktionsfreigabe.

- Hilfe & System: lokale, offline mitgelieferte Produkthilfe mit Suche (de/en)
  und rollenbeschränkte Systemseite mit Version, Datenbankstatus und Cache-Hinweisen.
- Wachen-Wiki mit unveränderlichen Revisionen, Konfliktschutz und rollenbasierter
  Bearbeitung; gleichzeitige Titel-Kollisionen und fehlende Revisionsangaben
  werden kontrolliert als Konflikt beantwortet.
- Diagnose und Supportexport: bereinigte Fehlerereignisse (Zeit, Korrelations-ID,
  stabiler Routenname, Kategorie, Status, Version) ohne URLs, Abfrageparameter,
  Exception-Texte oder Zugangsdaten; einheitliche Aufbewahrungsgrenze.
- Zweisprachigkeit über Templates, Fachmodule, JavaScript und sichtbare
  Python-Texte; Sprachumschaltung ohne Änderung der Adressen.
- Englische Projektseite neben der deutschen Fassung; Pages liefert beide aus.

Ausdrücklich nicht enthalten: schreibfähiger Offlinebetrieb ohne Server,
vollständige Übersetzung von Datenbank-Altbeständen und Modell-Labels, reale
Warenbetriebs-, TLS- und Geräteabnahme. Details: docs/RELEASE-0.18.0.md

## 0.17.0 - 2026-10-19

Zwischenrelease für Entwicklung und Präsentation, keine Produktionsfreigabe.

- Einrichtungsassistent mit Wachendaten, persönlichen Konten und optionalem Fünf-Tage-Wetter.
- Wiederholbarer QR-Login mit Gerätebestätigung, MFA-Anforderungen und Schutz gegen Wiederverwendung.
- Lokaler Betrieb bei WAN-Ausfall, wenn Server und LAN/WLAN erreichbar bleiben; keine Client-Outbox.
- Deutsche Textkorrekturen und de/en-Sprachfundament für Anmeldung, Einrichtung und Meldungen; Fachmodule noch nicht vollständig übersetzt.
- Token-Redaktion in Accesslogs und zusätzliche Funktions-, Berechtigungs- und Offline-Regressionstests.
- Statische Projektwebseite mit lokalen Assets und ausschließlich synthetischen Bildschirmaufnahmen.
- Nicht Bestandteil: integriertes Hilfe-/Wiki-/Diagnosezentrum, vollständige Mehrsprachigkeit und reale Geräte-/Produktionsabnahme.

## 0.16.0 - 2026-08-20

- Öffentliche Vorführungsseite unter `/vorfuehrung/` in der Web-PWA (Folien,
  Original-Ambient nach Klick, CSP ohne Inline-Skript/-CSS). One-Click-Demo
  bleibt nur bei `DEMO_MODE`.

- Vorführ-Folien unter `docs/praesentation/` (Live-HTML plus optionales lokales MP4).
  Ambient-Musik ist original erzeugt, keine fremden Titel.

- Web folgt `prefers-contrast: more` mit derselben Schwarz/Weiß-Palette wie
  die Flutter-HighContrast-Themes.

- **R-024 CSP- und Registrierungs-Nachzügler** – Push-Konfiguration über
  `json_script`; CSP `connect-src` nur `'self'` plus `PUSH_ALLOWED_ENDPOINT_HOSTS`;
  Wunschwache bei der Selbstregistrierung Pflicht.

- **R-023 Review-Findings 2026-08-20** – Vibe-P0-P3-Commits von `main`
  zurückgenommen (Alpine-Digest, unauthentisierte Metriken, django-ratelimit).
  Registrierungen sind stationsgebunden; Audit speichert bei Zahlungsfeldern
  nur `changed`, keine Werte; Müllkalender-Hosts brauchen
  `FEED_ALLOWED_HOSTS`; `DELETE /api/v1/token/` widerruft das aktuelle
  App-Token.

- **R-022 Web-Design-Parität Client/BOS** – Web-PWA übernimmt die kanonischen
  Client-Tokens (Primary `#0D47A1`, Prioritätsfarben, 48px Touch-Ziele, ruhige
  Flächen mit Rand); lokale Source Sans 3 (OFL); Landing und Manifest auf
  öffentlicher-Dienst-Ästhetik; Doku in `docs/DESIGN-SYSTEM.md`
- **Sicherheitshärtung R-021** – `obtain_token` verweigert API-Tokens, wenn
  `MFA_REQUIRED=true` gilt und das Konto keine bestätigte MFA hat
  (Fehlercode `mfa_setup_required`); Push-Subscription-Endpoints werden vor dem
  Speichern gegen eine HTTPS-Host-Allowlist geprüft (`PUSH_ALLOWED_ENDPOINT_HOSTS`,
  SSRF-Schutz); IBAN-Kopie-Handler aus der Kaffeeseite in `app.js` verschoben,
  damit `script-src 'self'` die Funktion nicht mehr blockiert; MFA-Fehlercodes
  in der kanonischen Fehlertabelle registriert
- **Muellkalender-ICS-Fallback (Roadmap Schritt 3)** – optionale, stationsspezifische
  Felder `waste_calendar_url` + `waste_calendar_enabled`; neues `WasteCollection`-Modell
  speichert die aus der ICS-Quelle importierten Abfuhrtermine; Management-Befehl
  `sync_waste_calendar` importiert sie mit demselben Haertungsprofil wie die
  Feed-Sync (HTTPS-only, Port 443, keine Weiterleitungen, DNS-Pinning auf globale
  Adressen, 1-MB-Limit); Abfuhrtermine erscheinen im Kalender, Dashboard und ICS-Abo
  mit Kennzeichnung „Müll“; HTTP- und private-IP-Quellen werden abgewiesen
- Doku-Sync: Versionspaarung Server ↔ Client dokumentiert
- **Kaffeekasse: Zahlungsweg-Hinweise** – optionale Felder `paypal_me_url`,
  `wero_link`, `iban`, `bic`, `payment_note` in den Stationseinstellungen;
  Anzeige als Links (`target="_blank" rel="noopener"`), kopierbare IBAN und
  Datenschutzhinweis auf der Kaffeeseite; HTTPS-/IBAN-/BIC-Validierung
- Krypto-Schlüsselrotation: optionaler `CRYPTO_MASTER_KEY` (Hex, 32 Byte)
  entkoppelt die TOTP-Verschlüsselung von `SECRET_KEY`; neuer Management-Befehl
  `rotate_crypto_key` re-verschlüsselt alle TOTP-Secrets, `CRYPTO_PREVIOUS_MASTER_KEY`
  sichert das Migrationsfenster (#20)
- Fahrplan für Kaffeekasse-Zahlungshinweise (PayPal.me, Wero, IBAN) und
  Müllkalender Kreis Gütersloh in `docs/ROADMAP.md`

## 0.15.0 - 2026-08-02

- Demo-Modus mit Musterbefüllung (`DEMO_MODE=true`, `load_demo_data`)
- Demo-Konten, Banner, Landing-Hinweise; Doku `docs/DEMO.md`

## 0.14.2 - 2026-08-02

- Datenschutzseite nennt Rechtsgrundlage, reale Laufzeiten und HTTPS-Attribute
  der ausschließlich technisch notwendigen Session- und CSRF-Cookies
- Login verlinkt die Cookie-Information transparent, ohne irreführendes Opt-in

## 0.14.1 - 2026-08-02

- Review-Härtung API: Passwortwechsel widerruft App-Tokens; Scope-Checks auf `/me/` und `/uebersicht/`
- App-Tokens mit Default-Ablauf (90 Tage); Axes-Reset nach Token-Mint; API-404 als JSON
- Checklisten-Abschluss prüft Stationskonsistenz; Compose-Log-Rotation für web/worker/backup

## 0.14.0 - 2026-08-01

- API v1 vereinheitlicht: widerrufbare `wb_`-App-Tokens plus deutsche Alias-Pfade
  (`anmeldung/`, `status/`, `uebersicht/`, `uebergaben/`, `kalender/`, `kaffeekasse/`, `checklisten/`)
- Schreibende API: Übergaben anlegen/Status, Kalender, Kaffeekasse, Checklisten-Abschluss
- Checklisten-Modul (Admin-Schalter, HTML `/checklisten/`, append-only Completions, DB-REVOKE)
- Multi-Stage-Dockerfile und Compose-Log-Rotation; OpenAPI/Doku aktualisiert

## 0.13.0 - 2026-07-31

- Krypto-Profil an BSI TR-02102 angelehnt (`docs/CRYPTO-BSI.md`): AES-256-GCM, ECDH P-256, TLS 1.3
- Login-Passwörter bevorzugt **Argon2id**; TOTP-Geheimnisse AES-256-GCM at rest
- E2EE Private-Key-Umschlag: PBKDF2-SHA-256 mit 600 000 Iterationen (bestehende Umschläge weiter lesbar)

## 0.12.1 - 2026-07-31

- Server und Client-Repo aufeinander abgestimmt (`Wachbuch-Client` ↔ `clients/wachbuch-mobile/`)
- Pull-Skript `scripts/pull-mobile-client-repo.sh`; Publish mit klarer 403-Hilfe (GitHub-App)
- Client-Doku: Startflow Adresse/QR → Login, Versions-Paarung App 0.2.x / Server ≥ 0.12

## 0.12.0 - 2026-07-31

- Mobile-Startflow: nur Server-Adresse oder QR-Scan → Bestätigen → Login (User/Passwort)
- Play-Store-Vorbereitung (Material 3, Target API 36, Kamera nur QR, kein Cleartext in Release)
- Web-QR unter `/konto/api/` zum Scannen der Server-Adresse
- Doku an offizielle Google-Play-/Android-Richtlinien angelehnt (`docs/PLAY-STORE.md`)

## 0.11.0 - 2026-07-31

- Android-APK sideloadbar (FOSS, Package `de.wachbuch.mobile`, minSdk 24)
- Tablet-/Smartphone-Layout: NavigationRail bzw. Bottom-Nav, Übergaben-Grid
- Build-Skript `clients/wachbuch-mobile/scripts/build-apk.sh`, Install-Doku
- Client-CI baut Release-APK als Artifact

## 0.10.1 - 2026-07-31

- Client für separates Repo vorbereitet: `Wachbuch-Client` (Publish-Skript, CI, volle AGPL-LICENSE)
- Doku zum einmaligen Anlegen des zweiten GitHub-Repos und Spiegeln per Skript

## 0.10.0 - 2026-07-31

- AGPL Flutter-Client unter `clients/wachbuch-mobile/` (iOS/Android)
- Login per Server-URL + Passwort-Token oder App-Token; wachenspezifisch via `/me/`
- Client-Doku in `docs/CLIENT.md` inkl. Vorbilder (Paperless/Nextcloud)

## 0.9.0 - 2026-07-31

- API-Fundament `/api/v1/` für spätere Open-Source-iOS-/Android-Clients
- App-Tokens (Paperless/Nextcloud-Stil) unter `/konto/api/` und `POST /api/v1/token/`
- Discovery, OpenAPI, `me`, lesende Übergaben; Doku in `docs/API.md`

## 0.8.0 - 2026-07-31

- Ende-zu-Ende-Verschlüsselung für Wachenchat (Ciphertext auf dem Server)
- private 1:1-Chats nur für Teilnehmer; Master-Admin ohne Teilnahme sieht nichts
- interne verschlüsselte Post (`/post/`); nur Absender/Empfänger lesen Klartext
- Chat-Schlüssel unter `/konto/crypto/` (Passphrase-umschlossener Private Key)

## 0.7.0 - 2026-07-31

- Master-Admin legt Nutzer an und gibt Wachenzugaenge frei (`/team/anlegen/`)
- öffentliche Selbstregistrierung standardmaessig aus (optional per Env)
- persönlicher Bereich: Profilbild, Passwort, Zwei-Faktor, Link zum Wachenchat
- Wachenchat als kurze Kollegennachrichten mit Avatar/Initialen (Facebook light)
- Rolle `admin` heißt sichtbar **Master-Admin**

## 0.6.1 - 2026-07-31

- gesetzliche Feiertage NRW im fortlaufenden Wachenkalender und ICS-Feed
- Modulschalter `holidays_enabled` in den Stationseinstellungen

## 0.6.0 - 2026-07-31

- Selbstregistrierung mit Admin-Freigabe und Ablehnung
- persönlicher Kontbereich (`/konto/`) für Profil und Passwort
- stationsbezogener Wachenchat (ohne Uploads, moderierbar)
- Modulschalter `chat_enabled` in den Stationseinstellungen

## 0.5.0 - 2026-07-31

- Passkeys (WebAuthn) für Anmeldung und als zweiter Faktor neben TOTP
- Web-Push für dringende Übergaben (opt-in, VAPID)
- Stationsweiter ICS-Feed und widerrufbare Kalender-Abo-Links
- ASVS-L2-Abdeckungsmatrix und Permissions-Policy für WebAuthn
- MFA-Fehlversuche begrenzt; CSP `connect-src` für Push-Dienste

## 0.4.0 - 2026-07-31

- Austritt: Deaktivierung einer Mitgliedschaft zieht Geburtstags-Opt-in zurück
- Audit-Diffs für Rollen, Modulschalter und Übergabe-Status (ohne Freitexte)
- kontrollierte Übergabe-Korrektur mit neuer Revision (`/uebergaben/<id>/bearbeiten/`)
- Feed-Felder `first_imported_at` / `last_seen_at` und Null-sichere Sortierung
- Retention-Kommando `apply_retention` (`RETENTION_FEED_DAYS`, optional Audit)
- optionale TOTP-Zwei-Faktor-Anmeldung (`MFA_ENABLED` / `MFA_REQUIRED`)
- Skript und Ablauf zur Rotation der App-/Feed-DB-Passwörter
- Touchziele für Footer-, Sektions- und Kassen-Aktionslinks nachgezogen

## 0.3.0 - 2026-07-31

- Compliance-Doku zu DSGVO, TDDDG-Cookies, EU AI Act und NRW öffentlichem Dienst
- Datenschutz-/Cookie-Transparenzseite unter `/datenschutz/` ohne Tracking-Banner
- öffentliche Startseite unter `/` präsentiert das Projekt; Fachfunktionen erst nach Login
- Dashboard unter `/uebersicht/`; Logout und unauthentifizierte App-Routen führen zu Startseite bzw. Anmeldung
- sichtbare Produktmarke einheitlich `Wachbuch`; Header-Unterzeile zeigt den Stationsnamen
- sichtbare SemVer-Version in Footer, `/healthz/` und Image-Label
- dokumentierter Versions- und Update-/Rollback-Ablauf
- Tagesaufgaben-Modul nach Wandbogen: grün täglich, gelb Wochentag, blau zusätzlich
- Heute-Liste, Wochenbogen, Vorlagenverwaltung und Audit für Erledigungen
- installierbare PWA mit Manifest, Service Worker, Icons und Offline-Hinweis
- App-Shell mit Safe Areas, Installationshinweis, Dringend-Badge und Schnellzugriff
- ICS-Export für einzelne Wachentermine
- Design der Oberfläche für Standalone-Nutzung aufpoliert
- Tailscale-Header-Login und zugehörige Konfiguration vollständig entfernt
- Authentifizierung nur noch über lokale Django-Konten hinter Docker/Reverse-Proxy
- Docker-Image mit Labels, ausführbaren Startskripten und Healthcheck gestrafft
- Compose-Projektname und Image-Name vereinheitlicht; Stack-Dokumentation bereinigt
- Geburtstage speichern Tag/Monat nur noch bei aktivem Opt-in und prüfen echte Kalenderdaten
- Geburtstagsliste blendet inaktive Mitglieder aus
- erneute Teamfreigabe reaktiviert bestehende Mitgliedschaften statt in einen 500-Fehler zu laufen
- Kaffeekorrekturen sperren die Originalbuchung und fangen parallele Doppelkorrekturen ab
- Feedansicht zeigt nur aktivierte Quellen und benennt die Gütersloh-Datenlücke
- Migration setzt externe Meldungen nach dem Modul-Upgrade wieder auf Opt-in
- Audit-Dokument mit Funktionsüberblick und Folgeplan ergänzt

## Unreleased - Open-Source-Basis

- portable Docker-Konfiguration ohne servergebundene Hosts und Datenbank-URLs
- sichere, stationsbezogene Einstellungsseite für Name und optionale Module
- lokaler Login und reproduzierbarer Erstadmin-Workflow ergänzt
- Migrationen vom dauerhaften Webprozess getrennt
- Build-Kontext gegen Backups, Datenbanken und Bytecode abgesichert
- Adminzugriff auf fachliche und unveränderliche Datensätze eingeschränkt
- GitHub-CI, Beitrags- und Sicherheitsrichtlinie vorbereitet
- Lizenz auf GNU AGPL v3 umgestellt

## 2026-07-28 - UI 0.2.0

- Dashboard auf aktive Übergaben und die nächsten drei Termine reduziert
- globale Navigation auf Übersicht, Übergaben, Kalender und Mehr vereinfacht
- Schreibformulare auf eigene, lineare Seiten verschoben
- Übergaben fachlich nach Dringlichkeit sortiert und Archiv getrennt
- Feedansicht nach Meldungen und Verkehr getrennt sowie paginiert
- Kassenbuch und Audit als semantische responsive Tabellen umgesetzt
- mobile Navigation, 768-Pixel-Tablet-Reflow und 44-Pixel-Touchziele eingeführt
- offene Designquellen und zehn verbindliche UX-Regeln dokumentiert

## 2026-07-28 - Tailnet-Pilot 0.1.0

- Django/PostgreSQL-Projektbasis und eigenes Git-Repository angelegt
- Übergaben, Kalender, Geburtstage, Kaffeekasse, Teamrollen und Audit umgesetzt
- offizielle Guetersloh-/Bielefeld-Feeds und Bielefelder Verkehrsdaten integriert
- Tailscale-Identitaet, Loopback-Bindung und getrennte Docker-Netze eingerichtet
- eingeschränkte PostgreSQL-Rollen und Append-only-Rechte gesetzt
- tägliches lokales Backup, Restic-Offsite-Pfad und Restore-Test eingerichtet
- 21 automatisierte Tests, Deployment-Checks und Trivy-Scans bestanden
- Pilot ausschließlich im Tailnet bereitgestellt; öffentliche Domain bleibt offline
