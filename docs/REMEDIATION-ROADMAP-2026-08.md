# Review-Remediation-Roadmap

Stand: 21. Oktober 2026 (Gesamtreview, siehe unten). Grundlage: technische, Sicherheits-, Design- und Integrationsreviews bis Server `0.21.0`; Client-Stand siehe `clients/`. Diese Roadmap ist die operative Quelle für Folgeagenten. Sie ersetzt keine externe Sicherheits-, Datenschutz- oder Barrierefreiheitsprüfung.

## Statuslegende

- `[x]` umgesetzt und durch vorhandene Regressionstests/CI abgesichert
- `[~]` wesentliche Teile umgesetzt, externe/manuelle Abnahme oder Restarbeit offen
- `[ ]` offen

## Zielzustand

Das Wachbuch erreicht einen reproduzierbar getesteten Pilotstand mit klarer Produktgrenze, sicherer Webausgabe, belastbaren Betriebsprozessen, zugänglichen Kernabläufen und nachvollziehbarer Lieferkette. Produktionsfreigabe erfolgt erst, wenn die technischen Gates grün sind und `GO-LIVE-CHECKLIST.md` sowie die externen Wave-3-Abnahmen abgeschlossen sind.

## Reihenfolge

```text
Wave 0  Sofortige Web-Sicherheitsfehler
Wave 1  Code-, UX- und Dokumentationshärtung
Wave 2  Betrieb, Lieferkette und asynchrone Verarbeitung
Wave 3  Unabhängige Abnahme und Produktionsfreigabe
Wave 4  Stärkeres E2EE-Vertrauensmodell
```

## Wave 0 – P0 Web-Sicherheit

### [~] R-001 CSP-kompatible verschlüsselte Post

Empfängerauswahl und JSON-Einbettung wurden CSP-kompatibel auf DOM-APIs/`json_script` umgestellt. Offen bleibt die vollständige manuelle Browser-/Screenreader-Abnahme des gesamten E2EE-Flows.

### [x] R-002 Sichere JSON-Einbettung

Betroffene Chat-/Post-Templates und die Push-Einstellungen verwenden Djangos
`json_script`; unsichere `|safe`-JSON-Sinks wurden entfernt und Benutzerwerte
werden nicht als HTML interpretiert.

### [x] R-003 Sicherheitsregressionstests

`core/test_security_regressions.py` prüft JSON-Sinks, CSP, Script-Reihenfolge, Navigation und Redirect-Schutz. Die Gates laufen in der regulären CI.

### [x] R-021 MFA-Durchsetzung, Push-Endpoint-Allowlist, CSP-Kaffeekasse

Umgesetzt und in den 0.16-Integrationsstand übernommen:

- Token-Ausgabe respektiert die MFA-Pflicht und unterscheidet `mfa_required` / `mfa_setup_required`.
- Push-Subscriptions akzeptieren nur HTTPS/443 ohne Credentials und nur Hosts aus `PUSH_ALLOWED_ENDPOINT_HOSTS` bzw. zulässige Host-Suffixe.
- IBAN-Kopie-Handler liegt in `core/static/core/app.js`; kein CSP-blockiertes Inline-Skript.
- MFA-Fehlercodes sind Teil des kanonischen API-Fehlervertrags.

**Restgrenze:** Web-MFA-Setup/Durchsetzung weiterhin separat im manuellen Auth-Review prüfen.

## Wave 1 – Anwendung und UX

### [x] R-004 E2EE-Versprechen an Bedrohungsmodell angleichen

UI- und Sicherheitsdokumentation unterscheiden Schutz gespeicherter Daten von einem aktiv kompromittierten Server/Webclient. Stärkeres Vertrauensmodell bleibt R-020.

### [~] R-005 Aufgaben-Race-Conditions schließen

Initialisierung und Abschluss/Wiedereröffnung verwenden Datenbanksperren. Parallele Last-/Resilienzabnahme bleibt Teil R-019.

### [x] R-006 Scheme-relative Redirects blockieren

Security-Middleware neutralisiert `Location: //…`; Regressionstest und CI sind vorhanden. Direkte Zielvalidierung mit `url_has_allowed_host_and_scheme` bleibt Best Practice bei künftigen View-Refactorings.

### [~] R-007 Vier globale Navigationsziele

Mobile/Desktop-Hauptnavigation folgt `Übersicht`, `Übergaben`, `Kalender`, `Mehr`. Reale Nutzerabnahme bleibt Wave 3.

### [~] R-008 Fokus und mobile Wochenansicht

Fokusindikator, Forced-Colors-Fallback, ausreichende Zielgrößen und mobile Wochenliste sind implementiert. 400-%-Zoom/Screenreader-Abnahme bleibt R-018.

### [x] R-009 Zugänglicher Entsperrdialog statt `window.prompt`

Der Entsperrflow verwendet einen eigenen zugänglichen Dialog mit beschriftetem Eingabefeld, Fehlerstatus, Anzeigen/Verbergen, Abbrechen, Fokusmanagement und Session-Lock. `window.prompt` wurde aus diesem Kernpfad entfernt. Regressionstests sichern den Flow ab.

### [x] R-014 Fehlerseiten und API-Konsistenz

Umgesetzt:

- zentrale strukturierte JSON-Fehlerantworten
- stabile Fehlercodes einschließlich MFA-Codes
- Korrelations-ID in API-Antworten/Logging
- eigene Fehlerhandler statt Stacktrace-Ausgabe an Clients
- Client kann neuen Vertrag und Legacy-Fehler lesen

Kanonischer Vertrag ist in `docs/API.md` und `core/api/openapi_v1.yaml` dokumentiert.

### [x] R-022 Web-Design-Parität mit Client (BOS/öffentlicher Dienst)

Web-PWA übernimmt die kanonischen Client-Design-Tokens (Blau-Identität,
Prioritäts-/Statusfarben, 48px Touch-Ziele, ruhige Flächen mit Rand statt
schwerer Schatten). Orientierung: Rettungsdienst / Feuerwehr / Polizei /
öffentlicher Dienst – feldlesbar, nicht marketinglastig. Manuelle
Umgesetzt in PR #62 (CI Django/Docker grün). Browser-/Kontrastabnahme bleibt Teil R-018.

## Wave 2 – Betrieb und Lieferkette

### [~] R-010 Least-Privilege-Backuprolle

Dauerhafte Rolle `rwsth_backup` besitzt nur die für Dumps notwendigen Leserechte; Web läuft als `rwsth_app`. Restore mit Owner-Rechten ist explizit/kurzlebig. Offen bleiben verschlüsseltes Offsite-Ziel und regelmäßig nachgewiesener Restore (R-017).

### [x] R-011 Gemeinsames Rate Limiting und Proxy-Vertrauen

DB-basiertes `RateLimit`-Model mit `select_for_update`, gehashte Schlüssel über `RATELIMIT_KEY_SALT` und explizites `TRUSTED_PROXY` für `X-Forwarded-For`. Regressionstests verhindern triviale Proxy-/Worker-Umgehung.

### [~] R-012 CI-/Supply-Chain-Gates

Vorhanden sind u. a. Python-Compile, JavaScript-Syntax, Django-Migrationscheck, `check --deploy`, Tests und isolierter PostgreSQL/Docker-Pfad. Clientseitig existieren Flutter-/Android-/iOS-/Dependency-Security-Gates und SBOM-Artefakte. Die Server-CI installiert nun ausschließlich `requirements.lock` mit verpflichtender SHA256-Hash-Verifikation; ein fehlender oder nicht passender Lock-Eintrag bricht den Job ab. Der Docker-Builder nutzt denselben Lockfile-Pfad und verweigert Installationen ohne passende Hashes.

Noch offen/zu vertiefen:

1. Ruff Format/Lint mit dokumentierter Baseline. Der erste abgegrenzte Gate-Schritt
   ist umgesetzt: Ruff `0.16.3` wird aus `requirements-ci.lock` mit SHA256-Hashes
   installiert und erzwingt die fehlerkritische E4/E7/E9-Baseline. Eine vollständige
   Formatprüfung und breitere Regelmenge bleiben wegen des bestehenden Altbestands
   ein separater Folge-Schritt.
2. Ein reproduzierbarer Python-Dependency-Scan ist umgesetzt: `pip-audit` wird
   als CI-Werkzeug über `requirements-audit.lock` mit SHA256-Hashes installiert und
   mit `--strict` gegen die CI-Umgebung ausgeführt. Container-Scan sowie
   CodeQL/SAST, Secret-Scanning und SBOM-/Provenance-Artefakte bleiben getrennte
   Folge-Gates; dieser Schritt behauptet deren Abdeckung nicht.
3. Der CI-Docker-Job scannt das gebaute Server-Image nun mit einer auf Commit-SHA
   fixierten Trivy-Action auf HIGH/CRITICAL-Schwachstellen. Ungefixte Findings
   werden nicht als behoben behauptet, sondern bleiben wegen der begrenzten
   Aussagekraft des Upstream-Fixes explizit ausgenommen.
4. CodeQL/SAST und Secret Scan
5. Server-SBOM + Build-Provenance
6. Browser-Smoke-Test, CSP-Konsole und Axe-Core

Actions und Images weiterhin auf unveränderliche SHAs/Digests pinnen.

### [x] R-013 Push-Outbox

Externe Push-Aufrufe laufen nicht mehr im Gunicorn-Fachrequest. `PushOutbox` speichert deduplizierte Jobs; der Worker verarbeitet Retry/Backoff, entfernt ungültige 404/410-Subscriptions und besitzt begrenzte Aufbewahrung/Cleanup. Betriebsmonitoring der Queue bleibt R-016.

## 0.16 Wachalltag – Integrationsstatus

### [x] Persistente Demo-Parität

Server und Client besitzen denselben produktiven Kernvertrag für:

- Mängel + Ereignis-/Audit-Verlauf
- authentifizierte Mängelfotos
- Fahrzeug-/Gerätestatus
- Schlüssel-/Pool-Ausgabe
- Übergabe-Quittierung
- wiederkehrende Checklisten
- leichte Stationsauswertung
- token-/servergebundenes Offline-Lesen im Client

### [x] Mobile Source of Truth

`darkspike1988/Wachbuch-Client` ist die kanonische Flutter-/iOS-/Android-Quelle. Der historische `clients/wachbuch-mobile/`-Spiegel im Server-Repo darf nicht zurückpubliziert werden; das frühere Force-Publish-Skript ist deaktiviert.

### [x] Request-Wiederholung / Datenintegrität

Nicht-idempotente Client-Mutationen wie Token-Erzeugung, Mangelanlage, Foto-Upload, Asset-/Inventar-Stammdaten und Checklistenabschluss werden nicht automatisch erneut gesendet. Sichere Reads bzw. serverseitig idempotente Zustandsoperationen dürfen Retry verwenden.

### [~] Post-Merge-Hardening

PR #54 schließt zwei in der Nachkontrolle gefundene Edge Cases:

- stark überfällige wiederkehrende Checks werden nach Abschluss entlang ihrer Kadenz bis zur ersten zukünftigen Fälligkeit fortgeschrieben
- Bilder werden zusätzlich zu MIME/Signatur mit Pillow vollständig validiert und auf 25 Megapixel begrenzt
- Owner-Zuordnung verlangt aktiven Django-User plus aktive Stationsmitgliedschaft

Status erst nach grünem finalem PR-Head auf `[x]` setzen.

### [x] R-023 Review-Findings 2026-08-20

Ursache: Vibe-P0-P3-Commits auf `main` (gebrochene CI, unauthentisierte Metriken)
plus offene Invarianten aus dem Dual-Repo-Review.

Umgesetzt:

- Vibe-Commits `9bfb3d8`/`a36936b` zurückgenommen (Dockerfile slim-bookworm, kein
  `/metrics/`, kein django-ratelimit neben R-011).
- **S1** Registrierungsliste, Ablehnung, Freigabe-Dropdown und Zähler bleiben an
  `request.membership.station` gebunden.
- **S2** Audit-Diffs für Zahlungs-/URL-Freitexte speichern nur `changed`.
- **S4** Müllkalender-Hosts brauchen `FEED_ALLOWED_HOSTS` (Form + Fetch).
- **C2** `DELETE /api/v1/token/` widerruft das vorgelegte App-Token.

Nachweise: `makemigrations --check`, 264 Django-Tests (darunter die neuen
Negativtests), `check --deploy` ohne neue Fehler, GitHub-Job `django` und
`docker` auf dem PR-Head grün. Client-Logout liegt im parallelen Client-PR.

### [x] R-024 CSP-/Registrierungs-Nachzügler 2026-08-20

Ursache: Review-Nachkontrolle nach R-023. `connect-src https:` erlaubte beliebige
HTTPS-Origins; Push-JSON lag ohne `json_script` im Template; Registrierungen
ohne Wunschwache erschienen in keiner Ablehnungsliste, aber im Freigabe-Dropdown
jeder Station.

Umgesetzt:

- Push-Konfiguration über Djangos `json_script:"push-config"`.
- `connect-src` nur `'self'` plus Hosts aus `PUSH_ALLOWED_ENDPOINT_HOSTS`.
- Wunschwache ist Pflicht; Pending ohne Station bleibt stationsübergreifend unsichtbar.

Nachweise: `makemigrations --check`, 269 Django-Tests (1 skipped),
`check --deploy` ohne neue Fehler, GitHub-Jobs `django` und `docker` auf dem
PR-Head grün.

## Wave 3 – Pilot- und Produktionsabnahme

### [ ] R-015 Externe ASVS-L2-Prüfung und Penetrationstest

Schwerpunkte: Rollen-/Stationsisolation, Auth/MFA/Passkeys, API-Tokens, SSRF, PWA-/Mobile-Cache, Upload, E2EE-Schnittstellen, CSP und Admin-Grenzen.

### [ ] R-016 Monitoring und Incident-Probe

Health, Fehlerquote, Queue/Worker, DB, Backupalter, Zertifikate, Speicher und ungewöhnliche Auth-Fehler alarmieren. Incident-Runbook praktisch üben.

### [ ] R-017 Verschlüsseltes Offsite-Backup und Restore-Nachweis

RPO/RTO festlegen; automatisierter Restore in isolierter Umgebung; Ergebnis und Backupalter sichtbar. Lokales Kurzzeit-Backup allein reicht nicht.

### [ ] R-018 Barrierefreiheitsabnahme

- Tastatur und 400-%-Zoom
- Reflow bei 320 CSS-Pixel
- NVDA/JAWS unter Windows
- VoiceOver auf iPhone/iPad
- Kontrast, Fokus, Fehler, Auth/MFA, Tabellen, Dialoge
- reale Nutzer aus dem Wachbetrieb

### [ ] R-019 Last- und Resilienztest

Gunicorn/DB-Grenzen, große Teams, Chat-/Auditwachstum, Feedfehler, langsame Pushziele, parallele Fachmutationen, Neustart während Migration und Wiederanlauf nach DB-Ausfall prüfen.

## Wave 4 – stärkeres E2EE-Vertrauensmodell

### [~] R-020 Schlüsselverifikation und unabhängiger Client

Teilweise umgesetzt (Fingerprint-/Sicherheitsnummern sichtbar), Rest offen:

- **umgesetzt** – sichtbare Schlüssel-Fingerprints im Chat (R-020 Teil 1) und
  eine Sicherheitsnummer im Web-Crypto-Setup (R-020 Teil 3). Vergleich „Nummern
  gleich = Schlüssel echt" ist damit möglich.
- **offen** – QR-Verifikation zwischen Kolleginnen und Kollegen (Web + App).
- **offen** – Key-Change-Warnungen und ein nachvollziehbares Schlüsselverzeichnis.
- **offen** – signierter nativer Client mit reproduzierbaren Builds.
- **offen** – Migration/Backup-Beschreibung bei Schlüsselwechsel.
- **offen/extern** – unabhängige Abnahme (siehe `docs/WAVE-3-READINESS.md`).

Erst nach diesen Restpunkten darf ein Schutzversprechen gegen einen aktiv
böswilligen Serverbetreiber erwogen werden.

## Gesamtreview Server 21. Oktober 2026 – Weg zum Projektabschluss

Geltungsbereich: nur der Django-Server (`config/`, `core/`, `templates/`,
`scripts/`, Betrieb und Doku). Die Flutter-App ist nicht Teil dieser Bewertung.
Prüfgrundlage: Vollsuite 803 Tests grün (2 übersprungen), Migrationscheck,
CI-Ruff-Baseline, `node --check`, `check --deploy` (nur die drei bewusst
offenen Betriebshinweise), Stichproben zu CSP/HTML-Sinks, Stationsbindung
(`core/access.py`), Verkehrslage und Dashboard/Display im Browser.

### Fortschrittsschätzung

Gezählt wird nach Roadmap-IDs R-001 bis R-024: 12 × `[x]`, 7 × `[~]`, 5 × `[ ]`.
Mit `[~]` zu 50 % gewichtet ergibt das rund **65 %**; funktional (Code und
Tests) liegt der Server höher, weil die fünf offenen Punkte der Wave 3
überwiegend externe Abnahmen sind und keine Programmierarbeit. Die geschätzten
**~75 %** sind für den *Funktionsumfang* plausibel, für die *Produktionsfreigabe*
aber zu hoch: `GO-LIVE-CHECKLIST.md` hat 0 von 24 Punkten abgehakt. Das ist
eine Schätzung, keine Messung.

### Befunde des Reviews

- **Keine reproduzierbaren Funktionsfehler** in Suite, Migrationen und Lint.
- **Behoben (PR #116):** Verkehrsquellen folgten HTTP-Weiterleitungen und
  umgingen damit die HTTPS-Allowlist; feste Region (Gütersloh/Steinhagen) und
  Standort-Fallback waren hartcodiert und sind jetzt je Wache einstellbar.
- **Doku veraltet:** `docs/ROADMAP.md` (Stand 3. August) führt bereits erledigte
  Punkte (Backuprolle, Rate Limiting) als `[ ]`; `docs/WAVE-3-READINESS.md`
  stammt vom 10. Oktober; Funktionsmatrix und Release-Notizen enden vor 0.21.0.
- **Datenschutz/Doku lückenhaft:** Die neuen externen Verkehrs- und
  Warnquellen (Autobahn GmbH, BBK/NINA, Gemeinde, Kreis) sind weder in
  `templates/core/privacy.html` noch in `docs/SECURITY-PRIVACY.md`,
  `docs/OPERATIONS.md` oder der VVT-Vorlage beschrieben.
- **Fragilität:** Die kommunalen Quellen werten HTML-Seiten per Textmuster aus;
  Layoutänderungen führen still zu leeren Listen. Es gibt keine Anzeige, dass
  eine Quelle ausfällt.
- **Responsive-Abnahme offen:** Wandanzeige wurde in sechs Auflösungen ohne
  Überlauf geprüft, aber nur mit leeren Daten; Übersicht bei großen Fenstern und
  volle Listen sind nicht im Browser belegt.
- **Dashboard:** `urgent_defects_count` wird berechnet, aber nicht angezeigt;
  `ensure_default_station_tasks` schreibt beim reinen Aufruf (GET).
- **Betrieb:** Redis-Volume ohne Funktion und `parsed_changelog` ohne Cache
  (siehe Backlog); Deploy-Check meldet `CRYPTO_MASTER_KEY`, `MFA_REQUIRED`,
  Audit-Aufbewahrung als noch nicht konfiguriert.

### Offene Arbeit bis zum Projektabschluss (Server)

#### Wave 2b – Code und Doku (ohne externe Abhängigkeit)

### [~] R-025 Verkehrslage: Datenschutz, Betrieb, Robustheit

Erledigt (0.22.0): Datenschutzseite (Abschnitt 5, DE/EN), `SECURITY-PRIVACY.md`
und `OPERATIONS.md` beschreiben die Quellen; Display zeigt nicht erreichbare
Quellen; Format-Tests mit Beispiel-HTML. Offen: VVT-Vorlage, Ausfallanzeige in
den Einstellungen.

- Externe Quellen in Datenschutzseite, VVT, `SECURITY-PRIVACY.md` und
  `OPERATIONS.md` dokumentieren (Zweck, übermittelte Daten = nur Serveranfrage,
  keine Personendaten).
- Ausfallanzeige je Quelle im Display/Einstellungen; Tests mit gespeicherten
  HTML-Beispielen der Quellen als Format-Regression.
- Einstellungsseite um Hinweis ergänzen, dass Autobahnen Koordinaten brauchen.

### [ ] R-026 Dashboard und Display: Browserabnahme

- Screenshots/Checks mit gefüllten Daten bei 1280×720, 1920×1080, 2560×1440,
  3840×2160, 2560×1080 und Hochkant; Übersicht ab 100rem.
- Entscheidung zu `urgent_defects_count` (anzeigen oder entfernen) und zum
  Schreibzugriff bei GET in `ensure_default_station_tasks`.

### [~] R-027 Doku- und Roadmap-Konsolidierung

Begonnen: `docs/ROADMAP.md` Backuprolle/Rate Limiting korrigiert. Offen:
`WAVE-3-READINESS.md`, Funktionsmatrix, README auf 0.21.0.

- `docs/ROADMAP.md`, `WAVE-3-READINESS.md`, Funktionsmatrix und README auf
  0.21.0 bringen; erledigte Punkte als `[x]` markieren, Doppelungen zu
  `ROADMAP-OFFENE-BAUSTELLEN.md` auflösen.

### [ ] R-028 CI-Gates aus R-012 abschließen

CodeQL/SAST, Secret-Scan, Server-SBOM/Provenance, Browser-Smoke-Test mit
CSP-Konsole und Axe-Core; Ruff-Regelmenge schrittweise erweitern.

### [ ] R-029 Betriebskonfiguration für Pilot

`CRYPTO_MASTER_KEY`, `MFA_REQUIRED=true`, `RETENTION_AUDIT_DAYS` festlegen und
in `DEPLOYMENT.md` als Pflichtwerte dokumentieren; Redis-Volume bereinigen;
Docker-Pfad (`docker compose config`, Build) in der Abnahme nachweisen.

### [ ] R-030 Offene E2EE-Teile ohne App

Web-QR-Verifikation und Web-Key-Change-Warnung (R-020, Webanteil) sowie
Migration/Backup-Beschreibung bei Schlüsselwechsel.

#### Wave 3 – externe Abnahmen (unverändert, Reihenfolge laut Readiness)

R-017 Offsite-Backup/Restore → R-016 Monitoring/Incident → R-015 Pentest/ASVS →
R-019 Last/Resilienz → R-018 Barrierefreiheit. Danach `GO-LIVE-CHECKLIST.md`
abarbeiten und formal freigeben. Diese Punkte können nicht durch Code oder
Mocks als erledigt gelten.

#### Abschlusskriterium Server

Alle `R-0xx` auf `[x]` (R-020 nur Webanteil, App separat), Go-live-Checkliste
vollständig abgehakt, finale Freigabe dokumentiert. Bis dahin: Pilotstand,
keine Produktionsfreigabe.

## Bekannter Backlog (nicht blockierend, dokumentiert)

- **Redis scheinbar ungenutzt / Volume ohne Funktion:** `docker-compose.yml`
  deklariert ein Named Volume `redis-data`, der `redis`-Service läuft aber
  bewusst nicht-persistent (`--save "" --appendonly "no"`). Das Volume hat
  damit keine Funktion und sollte entfernt **oder** mit Begründung versehen
  werden. Zusätzlich ist der diskrete `REDIS_HOST/PORT/DB/PASSWORD`-Fallback in
  `config/settings.py` nur ein Local-Dev-Pfad; in Compose wird `REDIS_URL`
  direkt gesetzt, sodass der Fallback im Betrieb nicht greift.
- **AppVersion.parsed_changelog:** Eine Umstellung auf `cached_property` ist
  ein offener Optimierungspunkt, keine Voraussetzung der Releaseabnahme.
- **Client UpdateService:** Netzwerk-Retry bleibt als nicht blockierender
  Backlog offen; das 24-Stunden-Intervall ersetzt keine Retry-Strategie.
- **R-015 bis R-019:** Pentest, Monitoring-/Incident-Probe, Offsite-Restore,
  Accessibility und Last-/Resilienztest benötigen die externen bzw. echten
  Betriebsabnahmen aus `docs/WAVE-3-READINESS.md`.
- **Client PR67 / R-020:** App-QR, persistierte Verifikation und App-Key-Change
  sind im separaten Client-PR implementiert, aber noch nicht final abgenommen.
  Web-QR und Web-Key-Change bleiben offen. Die bloße Gleichheit vom Server
  gelieferter Fingerprint-Strings ist kein unabhängiger Schlüsselnachweis.

## Agenten-Handoff

Bei jeder Fortsetzung zuerst `AGENTS.md`, diese Roadmap, `docs/API.md` und `docs/CLIENT.md` lesen. Keine Mobile-Änderung im historischen Server-Mirror beginnen. Sicherheits- oder Betriebsänderungen erhalten eine Roadmap-ID bzw. einen klar abgegrenzten PR mit Ursache, Risiko, Umsetzung, negativen Tests, Betriebsauswirkung, Rollback und verbleibenden Grenzen.
