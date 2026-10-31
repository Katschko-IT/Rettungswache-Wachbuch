# OFFLINE-BETRIEB — lokaler Wachenserver ohne WAN

Stand 2026-10-19. Gilt für den Slice „Erstinstallations-Wizard, Konten, Aktivierung“.
Kein Commit, kein Push, kein Deployment.

## 1. Architektur und Vertrauensgrenze

Der Wachenserver (Django + SQLite/PostgreSQL) ist die Autorität. Alle Seiten,
Assets, Formulare und die Authentifizierung werden lokal ausgeliefert. Es gibt
im geprüften Kernpfad **keine** Cloud-Anmeldung, kein CDN, keinen externen
Font-/Skript-/Telemetrie-Aufruf und keine Internetpflicht.

- Statische Assets: `core/static/core/…` über WhiteNoise, gleiche Origin.
- Anmeldung: Django-Session + lokale Passwortprüfung, optional TOTP/Passkey.
- Rollen/Stationen: `core/access.py`, unverändert; offline wird **nichts** davon
  abgeschaltet.
- QR-Aktivierung: Link zeigt auf den lokalen Origin; QR-Erzeugung läuft im
  Prozess (`qrcode`, keine Netzverbindung).
- Daten: Wachendaten und Konten liegen lokal. Die Anschrift wird immer lokal
  gespeichert; Geocoding ist ein separater, ausdrücklich bestätigter Vorgang.

### Zwei verschiedene Ausfallszenarien

| Szenario | Erwartung | Status |
|---|---|---|
| **WAN-Ausfall, LAN + Server erreichbar** | Wizard, Login, MFA, Rollen, Aktivierung, Kernbetrieb funktionieren vollständig | **durch Tests belegt** (siehe §3) |
| **Handy ohne Netz oder Server aus** | Client-Offlinecache, Outbox und Sync-Konfliktbehandlung nötig | **NICHT umgesetzt und nicht bewiesen** — offene Grenze |

Für Szenario 2 existiert keine Offline-Datenbank im Browser und keine Outbox.
Die PWA liefert lediglich eine Offline-Fehlerseite. Aussagen über „Offline-Betrieb
des Clients“ wären derzeit falsch.

## 2. Voraussetzungen für den lokalen Betrieb

1. **Lokale Origin korrekt konfigurieren** (nicht Auth abschalten):
   - `ALLOWED_HOSTS` enthält den lokalen Hostnamen/IP der Wache.
   - `CSRF_TRUSTED_ORIGINS` enthält die tatsächlich genutzte lokale Origin
     (z. B. `https://wachbuch.wache.lan`).
   - Empfohlen: lokales TLS mit interner CA, dann bleiben
     `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` und HSTS aktiv.
   - Nur falls bewusst ohne TLS betrieben: `SECURE_COOKIES=false` setzen und
     dokumentieren. CSRF, Sessions, Rollen und MFA bleiben davon unberührt.
2. **Kein Tailscale/Internetzwang** im lokalen Ablauf. VPN ist optional für
   Fernzugriff, nicht Voraussetzung für den Wachenbetrieb.
3. `SETUP_BOOTSTRAP_TOKEN` einmalig außerhalb der Anwendung setzen; danach
   wieder entfernen. Ohne Token ist `/setup/` nicht vorhanden.
4. Zeit synchron halten (NTP im LAN oder manuell), sonst driften
   Aktivierungsablauf und TOTP.

## 3. Echte Prüfgates

Ausgeführt mit eigenem SQLite-Testziel, nicht mit einer geteilten DB:

```bash
DJANGO_SECRET_KEY=ci-only-secret DJANGO_DEBUG=false \
REDIS_URL='' REDIS_HOST='' \
DATABASE_URL='sqlite:////…/setup-test.sqlite3' \
python manage.py test core.test_setup_wizard --settings=config.test_settings
```

Belegte Fälle (`core/test_setup_wizard.py`, Klasse `WanOutageTests`):

- `socket.getaddrinfo`, `socket.create_connection` und `urllib.request.urlopen`
  werden auf `OSError` gepatcht (DNS und ausgehendes HTTP verweigert).
- Trotzdem: Bootstrap-Token, Abschluss der Installation, Admin-Passwortlogin,
  Anlage eines Mitarbeiterkontos, Aktivierungslink und Passwortsetzung — alles 302/200.
- Ein zweiter Test verbietet jeden Aufruf von `core.weather._urlopen` während
  der Installation.
- Der Wizard ruft Wetter **nicht** beim Abschluss auf; Wetter ist ein separater
  POST (`/setup/wetter/`) mit Einwilligung.

Zusätzlich: vollständige Suite 344 Tests OK (skipped=1), siehe
`evidence/worker-full-tests-wizard.log`; Migrationsprüfung `No changes detected`.

**Grenze der Gates:** Die Tests beweisen den Django-Pfad ohne ausgehende
Netzverbindung. Sie beweisen nicht die physische LAN-Konfiguration, DNS-Ausfall
im Browser, TLS-Zertifikatsverteilung oder ein reales Gerät im Flugmodus.

## 4. Wetter und Geocoding (optional)

- Standard: aus. Ohne `weather_enabled` und ohne `geo_consent` wird keine
  Anschrift übermittelt; die Wachendaten bleiben lokal.
- Feste HTTPS-Allowlist: `geocoding-api.open-meteo.com`, `api.open-meteo.com`.
  Kein benutzerdefinierter Endpunkt, keine Redirects, 3 s Timeout,
  200 kB Antwortlimit.
- Circuit Breaker: nach 3 Fehlern 120 s Pause; währenddessen wird nur ein
  vorhandener Cache verwendet.
- Cache: 1 h pro gerundeter Koordinate. Bei fehlgeschlagener Aktualisierung
  werden die **alten echten Werte** mit `stale=True`, Abrufzeit und Alter
  angezeigt. Es werden niemals Dummy-Livewerte erzeugt. Ohne Cache und ohne
  Netz: sichtbarer Hinweis, kein Wetterblock, Installation läuft weiter.
- Live-Prüfung nur mit synthetischen Koordinaten (52.2787/8.0479), als
  synthetisch gekennzeichnet; keine echten Wachenadressen im Test.

## 5. Was offline ausdrücklich nicht gilt

- Kein Bypass von Login, MFA, Passkey, CSRF oder Rollen „weil offline“.
- Kein wiederholbarer QR-Login (Restpunkt, siehe `docs/SETUP-WIZARD-PLAN.md` §6).
- Keine automatische Anmeldung nach Aktivierung.
- Keine Client-Outbox, kein Konfliktauflösungsmodell, keine Offline-Schreibvorgänge.

## 6. Offene Grenzen / Restpunkte

1. Client-Offlinebetrieb (Szenario 2) inkl. Outbox und Sync-Konflikten ist offen.
2. Reale LAN-/TLS-Abnahme auf Zielhardware und realem Mobilgerät steht aus.
3. Reverse-Proxy-/Gunicorn-Access-Logs müssen Aktivierungstokens ebenfalls
   redigieren; die Anwendung redigiert ihren eigenen Request-Log
   (`/aktivieren/[redacted]/`), kontrolliert aber nicht vorgelagerte Logger.
4. Serverseitige Uhrzeit muss für Ablauf/TOTP synchron sein.
5. Wetter ist ein optionaler externer Dienst; seine Verfügbarkeit ist keine
   Betriebsvoraussetzung.

## 7. Papier-Rückfallebene

Fällt der Wachenserver aus, arbeitet die Wache mit vorab gedruckten Blättern
weiter (Roadmap 0.27, Baustein 8). Die Druckansichten liegen unter `/papier/`;
Einstieg über Einstellungen → „Papier-Rückfall“ (Master-Admin) oder über die
Hilfe (alle Rollen außer Auditor).

| Ansicht | Pfad | Inhalt |
| --- | --- | --- |
| Deckblatt | `/papier/` | fünf Schritte für den Ausfall, leere Zeilen für Ansprechperson Technik und Telefon |
| Fristen der Woche | `/papier/fristen/` | HU, SP, UVV und Tragentisch der aktiven Fahrzeuge; STK (Anlage 1), MTK (Anlage 2) und DGUV V3 der Medizingeräte; Überprüfung aktiver Dienstanweisungen; Verfall von Chargen mit Bestand (ohne Rückruf); auch schon Überfälliges |
| Telefonbuch | `/papier/telefonbuch/` | Notfall-Schnellwahl, Kontakte nach Kategorie, leere Zeilen für Nachträge von Hand |
| Checklisten | `/papier/checklisten/` | ein Blatt je aktiver Checkliste |
| Fahrzeugübernahme | `/papier/fahrzeuguebernahme/` | ein Blatt je aktivem Fahrzeug, 12 Zeilen, Prüfpunkte wie im Formular |
| Desinfektion | `/papier/desinfektion/` | ein Blatt je aktivem Fahrzeug, 14 Zeilen mit Datum, Beginn, Mittel, „Frei ab“ und Kürzeln; darüber die Mittel der Wache mit ihrer hinterlegten Standard-Einwirkzeit |
| Funktionskontrolle | `/papier/funktionskontrolle/` | ein Blatt je Gerätestandort, Prüfpunkte wie im Formular; gesperrte Geräte ohne Ankreuzfelder |

- **Wer druckt:** alle Rollen mit fachlichem Zugriff (Mitglied, Schichtleitung,
  Kassenwart, Master-Admin), jeweils nur für die eigene Wache. Auditoren
  erhalten 403. Das Wachenterminal erreicht die Ansichten nicht: `/papier/`
  liegt außerhalb des Terminal-Modus, und jede Ansicht weist das Dienstkonto
  zusätzlich ab. Ansichten abgeschalteter Module fehlen (404).
- **Wann:** vor dem Pilotstart Deckblatt, Formulare und Telefonbuch; die
  Fristenliste jede Woche neu, am besten montags; nach Änderungen an
  Fahrzeugen, Geräten, Mitteln, Checklisten oder Kontakten erneut. Jedes Blatt
  zeigt „Stand: Datum Uhrzeit“. Die Fristenliste gilt nur für die Woche, die sie
  zeigt; wählbar sind die aktuelle und kommende Wochen, denn eine vergangene
  Woche lässt sich nach erledigten Prüfungen nicht mehr rekonstruieren.
- **Wo:** ein Ordner an der Wache; zusätzlich je Fahrzeug ein Blatt
  Fahrzeugübernahme und ein Blatt Desinfektion im Fahrzeug.
- **Drucken:** Browserdruck (`@media print`), keine PDF-Bibliothek. Im
  Druckdialog A4 hochkant wählen und Kopf- und Fußzeilen des Browsers
  ausschalten. Geprüft in Chromium, dem Kiosk-Browser des Pi; andere Browser
  können Ränder anders setzen.
- **Inhalt:**
  - Leere Formulare und Fristenliste enthalten nur Konfiguration und Fristen:
    keine Namen, keine früheren Ergebnisse, keine Freitexte aus Nachweisen.
  - Das Telefonbuch enthält die Kontakte so, wie sie in der App stehen, also
    auch Ansprechpersonen und Rufnummern, zum Beispiel der Wachleitung.
  - Das Desinfektionsblatt liegt offen im Fahrzeug; was darauf steht, kann
    jeder lesen. Es hat deshalb nur Spalten für das, was nach Entscheidung D2
    alle sehen: Datum, Beginn, Mittel, „Frei ab“ und Kürzel. Es fehlen Art und
    Stufe, die Einwirkzeit je Durchgang und eine Bemerkung, denn Minuten und
    Bemerkung können die Stufe verraten. Erreger nennt das Blatt nicht. Der
    Hinweis unten auf dem Blatt bittet, Stufe und Einwirkzeit nicht von Hand
    nachzutragen.
  - Was bleibt: Beginn und „Frei ab“ zeigen zusammen, wie lange das Fahrzeug
    gesperrt war, so wie die Sperre „Desinfektion bis …“ in der App. Daraus
    lässt sich wie dort ablesen, dass nach einer Einwirkzeit freigegeben wurde.
    Das ist für den Betrieb nötig und bewusst so belassen. Die Minuten in der
    Zeile „Mittel der Wache“ sind die hinterlegte Standard-Einwirkzeit des
    Mittels, keine Angabe zu einer einzelnen Desinfektion.
  - Keine Patienten- oder Einsatzangaben auf den Blättern.
  - Ausdrucke sind intern: Sie bleiben im Ordner der Wache. Beim Neudruck
    werden die alten Blätter vernichtet.
- **Nach dem Ausfall:** Version 0.27 übernimmt nichts von Papier ins System.
  Die heutigen Formulare stempeln die Zeit der Eingabe: Eine nachträglich
  erfasste Desinfektion würde das Fahrzeug ab jetzt sperren, eine
  Fahrzeugübernahme mit älterem km-Stand wird abgelehnt, Funktionskontrollen
  und Checklisten bekämen die falsche Zeit. Deshalb wird nach dem Ausfall nur
  der aktuelle Stand erfasst (je Fahrzeug eine neue Fahrzeugübernahme, offene
  Mängel). Die ausgefüllten Blätter sind der Nachweis für die Ausfallzeit und
  bleiben als Original bei der Wachleitung. Nachträge mit Ereigniszeit und
  Eingabezeit sind für 0.28 geplant.
- **Offen:** Aufbewahrung und Vernichtung der ausgefüllten Blätter
  (handschriftliche Kürzel und Zeiten sind personenbezogene Daten) regelt das
  Löschkonzept (Datenschutzunterlagen 0.27, Entscheidung von Betreiber und
  Datenschutzbeauftragten). Bis dahin bleiben die Originale bei der
  Wachleitung.
- Kategorien des Telefonbuchs, der Rhythmus einer Checkliste und der
  Gerätestatus kommen aus Auswahlwerten ohne Übersetzung; sie erscheinen auch
  in der englischen Oberfläche deutsch (siehe `docs/UX-PLAN.md`, B4).
- Einmal geöffnete Seiten können im Seitencache des Service Workers mit ihrem
  alten Stand liegen. Verlässlich ist nur der vorab gedruckte Ausdruck.

## Raspberry Pi mit eigenem WLAN

Einrichtung eines Pi als Wachen-Server mit eigenem WLAN, lokalem Zertifikat und
Touch-Terminal: [`PI-WACHENTERMINAL.md`](PI-WACHENTERMINAL.md).
