# Changelog

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
