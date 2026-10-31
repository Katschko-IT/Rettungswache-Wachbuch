# Datenflüsse an Dritte

Stand: 31. Oktober 2026 · gilt für Wachwerk 0.27

Diese Übersicht nennt jeden Weg, auf dem Daten eine Wachwerk-Installation
verlassen können. Sie ist die Grundlage für VVT (Empfänger, Drittland),
DSFA-Vorprüfung, Datenschutzinformation nach Art. 13 DSGVO und Anlage 4 der
Vereinbarung mit der Interessenvertretung (`MITBESTIMMUNG-VORLAGE.md`).

Keine Rechtsberatung. Ob ein Dienst Auftragsverarbeiter oder eigenständig
verantwortlich ist und ob ein Drittlandbezug besteht, prüft der Betreiber mit
der oder dem Datenschutzbeauftragten. Solche Stellen sind mit **[prüfen]**
markiert.

Welche Daten in welcher Tabelle liegen: [`DATENKATALOG.md`](DATENKATALOG.md).

## Grundsatz: Inselbetrieb

Wachwerk funktioniert ohne Internet. Alle Dienste unten sind abschaltbar; die
meisten sind im Standard aus. **Nicht vorhanden** sind:

- keine Kartendienste oder Kartenkacheln,
- keine CDNs, keine externen Schriften (Schriften liegen lokal unter `core/static/core/fonts/`),
- kein Analytics, kein Tracking, kein Crash-Reporting,
- keine KI-Dienste,
- keine Telemetrie an den Hersteller.

Die Content-Security-Policy erlaubt Verbindungen des Browsers nur zum eigenen
Server und zu den Push-Diensten der Browserhersteller
(`PUSH_ALLOWED_ENDPOINT_HOSTS`).

## Übersicht

| Dienst | Empfänger | Personenbezug | Schalter (Standard) | Empfehlung Pilot |
| --- | --- | --- | --- | --- |
| [Wetter](#wetter) | Open-Meteo, bei der Ortssuche OpenStreetMap | nein (Standort der Wache) | `Station.weather_enabled` (aus) | aus oder nach Entscheidung |
| [Verkehr](#verkehr) | Autobahn GmbH, BBK (NINA) | nein | `Station.traffic_enabled` (aus) | aus oder nach Entscheidung |
| [Verkehr lokal](#verkehr-lokal) | Gemeinde Steinhagen, Kreis Gütersloh | nein | `Station.traffic_local_sources` (aus) | aus |
| [Meldungen](#meldungen) | eingetragene Feed-Quellen | nein | `Station.feeds_enabled` (aus) | aus oder nach Entscheidung |
| [Müllkalender](#müllkalender) | Gemeinde bzw. Entsorger | nein | `Station.waste_calendar_enabled` (aus) | nach Entscheidung |
| [Web-Push](#web-push) | Push-Dienst des Browserherstellers | ja | `WEB_PUSH_ENABLED` (aus) | aus |
| [Push-Relay](#push-relay) | Betreiber des Relays, Apple, Google | ja | `PUSH_RELAY_URL` (leer) | aus |
| [Signal](#signal) | Signal Messenger LLC (USA) | ja | `SIGNAL_API_URL`, `SIGNAL_NUMBER` (leer) | aus |
| [E-Mail](#e-mail) | SMTP-Anbieter des Betreibers | ja | `EMAIL_HOST` (leer) | nach Entscheidung |
| [Images und Updates](#images-und-updates) | GitHub (ghcr.io, api.github.com) | nein (IP des Servers) | Update-Modus der Installation | manuell, Wartungsfenster |
| [Healthcheck-Ping](#healthcheck-ping) | Dienst hinter `PING_URL` | gering (Hostname, Fehlertexte) | `PING_URL` (leer) | aus |
| [Offsite-Sicherung](#offsite-sicherung) | Speicherziel des Betreibers | ja (verschlüsselt) | `BACKUP_OFF_TARGET` (leer) | USB-Rotation oder NAS |
| [Zertifikate](#zertifikate) | Let's Encrypt | nein (Domainname) | Modus `domain` | nicht nötig (Modus `lan`) |
| [Betriebssystem](#betriebssystem) | Paketquellen, Zeitserver, DNS | nein (IP des Servers) | Host | nach Betreiber |
| [Hosting](#hosting) | Hoster (`SiteProfile.hosting_provider`) | ja | Betriebsweg | Pi/LAN vor Ort |
| [Links für Nutzende](#links-für-nutzende) | PayPal, Wero, Signal, Kalender-Apps | nur durch die Person selbst | einzelne Einstellungen | nach Entscheidung |
| [App-Stores](#app-stores) | Apple, Google, F-Droid | ja (Konto im Store) | Verteilung der App | nach Entscheidung |
| [Supportbericht](#supportbericht) | Empfänger, dem der Admin ihn schickt | nein | manuell | nur bei Bedarf |

## Dienste in der Anwendung

Diese Dienste startet der Wachwerk-Server selbst. Geplant ist (Paket E2),
dass die Seite `/datenschutz/` die eingeschalteten Dienste dieser Installation
aus `core/data_flows.py` anzeigt; jeder Schlüssel dort braucht hier einen
Abschnitt mit `<!-- flow: KEY -->`.

### Wetter

<!-- flow: weather -->

- **Empfänger und Rolle:** Open-Meteo (Wettervorhersage, `api.open-meteo.com`; Ortssuche `geocoding-api.open-meteo.com`); als Rückfall bei der Ortssuche OpenStreetMap Foundation (`nominatim.openstreetmap.org`). Eigenständig verantwortlich **[prüfen]**.
- **Daten:** Koordinaten der Wache, auf 4 Nachkommastellen gerundet, und die Zeitzone. Bei der einmaligen Ortssuche die eingegebene Adresse der Wache (nur nach Bestätigung im Einrichtungsassistenten). Die IP-Adresse des Servers.
- **Personenbezug:** keiner; es geht um den Standort der Wache.
- **Auslöser:** Server ruft die Vorhersage für Display, Übersicht und Terminal ab und speichert sie zwischen.
- **Schalter und Standard:** `Station.weather_enabled`, Standard aus.
- **Drittland:** Sitz der Anbieter **[prüfen]**.
- **Empfehlung Pilot:** aus, bis Betreiber und DSB den Dienst freigeben.

### Verkehr

<!-- flow: traffic -->

- **Empfänger und Rolle:** Autobahn GmbH des Bundes (`verkehr.autobahn.de`) und Bundesamt für Bevölkerungsschutz und Katastrophenhilfe (NINA, `warnung.bund.de`). Eigenständig verantwortlich **[prüfen]**.
- **Daten:** nur die Anfrage des Servers (Straßenkennungen wie A2, IP-Adresse des Servers). Koordinaten und Warngebiete bleiben auf dem Server.
- **Personenbezug:** keiner.
- **Auslöser:** Abruf für Display und Übersicht, mit Zwischenspeicher.
- **Schalter und Standard:** `Station.traffic_enabled`, Standard aus.
- **Drittland:** nein.
- **Empfehlung Pilot:** aus oder nach Entscheidung.

### Verkehr lokal

<!-- flow: traffic_local -->

- **Empfänger und Rolle:** Gemeinde Steinhagen und Kreis Gütersloh (Baustellenseiten). Eigenständig verantwortlich **[prüfen]**.
- **Daten:** Abruf einer öffentlichen Webseite durch den Server.
- **Personenbezug:** keiner.
- **Auslöser:** wie Verkehr.
- **Schalter und Standard:** `Station.traffic_local_sources`, Standard aus; nur zusammen mit Verkehr.
- **Drittland:** nein.
- **Empfehlung Pilot:** aus (nur für Wachen in diesem Gebiet sinnvoll).

### Meldungen

<!-- flow: feeds -->

- **Empfänger und Rolle:** die vom Betreiber eingetragenen Feed-Quellen (`FeedSource`, nur HTTPS auf Port 443, ohne Weiterleitungen und private Adressen). Eigenständig verantwortlich **[prüfen]**.
- **Daten:** Abruf durch den Server mit der Kennung `Wachbuch/1.0`.
- **Personenbezug:** keiner.
- **Auslöser:** Dienst `feed-worker` (`sync_feeds`) alle 15 Minuten.
- **Schalter und Standard:** `Station.feeds_enabled`, Standard aus; zusätzlich je Quelle `is_enabled`.
- **Drittland:** je Quelle **[prüfen]**.
- **Empfehlung Pilot:** aus oder nur Quellen öffentlicher Stellen.

### Müllkalender

<!-- flow: waste_calendar -->

- **Empfänger und Rolle:** der Anbieter der eingetragenen ICS-Adresse (Gemeinde oder Entsorger). Eigenständig verantwortlich **[prüfen]**.
- **Daten:** Abruf der ICS-Datei durch den Server.
- **Personenbezug:** keiner.
- **Auslöser:** Dienst `feed-worker` (`sync_waste_calendar`, aus `sync_feeds` heraus).
- **Schalter und Standard:** `Station.waste_calendar_enabled` und `Station.waste_calendar_url`, Standard aus.
- **Drittland:** nein, sofern der Anbieter in Deutschland sitzt **[prüfen]**.
- **Empfehlung Pilot:** nach Entscheidung.

### Web-Push

<!-- flow: web_push -->

- **Empfänger und Rolle:** Push-Dienst des jeweiligen Browserherstellers (z. B. Google, Mozilla, Apple). Die Person wählt das selbst, indem sie Push im Browser erlaubt **[prüfen]**.
- **Daten:** verschlüsselte Benachrichtigung (Titel, kurzer Text, Link) an die Push-Adresse des Browsers; Zeitpunkt und Größe sieht der Push-Dienst.
- **Personenbezug:** ja, über die Push-Adresse.
- **Auslöser:** Benachrichtigung im Posteingang, Dienst `push-worker`.
- **Schalter und Standard:** `WEB_PUSH_ENABLED` mit VAPID-Schlüsseln, Standard aus; je Person freiwillig.
- **Drittland:** je nach Browserhersteller USA **[prüfen]**.
- **Empfehlung Pilot:** aus; Posteingang und App genügen.

### Push-Relay

<!-- flow: push_relay -->

- **Empfänger und Rolle:** Betreiber des Relays (Entscheidung #11 offen), danach Apple (APNs) oder Google (FCM). Auftragsverarbeitung bzw. eigenständige Verantwortung **[prüfen]**.
- **Daten:** Plattform, Geräte-Token, Titel, kurzer Text und Pfad der Benachrichtigung (`docs/PUSH-RELAY.md`).
- **Personenbezug:** ja, über das Geräte-Token.
- **Auslöser:** Benachrichtigung für ein registriertes App-Gerät, Dienst `push-worker`.
- **Schalter und Standard:** `PUSH_RELAY_URL` (nur `https://`) und `PUSH_RELAY_TOKEN`, Standard leer.
- **Drittland:** Apple und Google: USA **[prüfen]**.
- **Empfehlung Pilot:** aus; die App plant Erinnerungen lokal.

### Signal

<!-- flow: signal -->

- **Empfänger und Rolle:** Signal Messenger LLC, USA, über den lokalen Container `signal-cli-rest-api` (verknüpftes Gerät eines Wachen-Handys, kein Port nach außen). Eigenständig verantwortlich **[prüfen]**.
- **Daten:** Nachrichtentext Ende-zu-Ende-verschlüsselt; Telefonnummern der Personen, die ihre Nummer selbst bestätigt haben, bzw. die ID der Wachengruppe; Metadaten (Zeitpunkt, Empfänger) beim Signal-Dienst (`docs/SIGNAL.md`).
- **Personenbezug:** ja.
- **Auslöser:** Hinweise aus dem Posteingang an bestätigte Nummern; Erinnerungen der Kaffeekasse an die Wachengruppe, wenn eingeschaltet.
- **Schalter und Standard:** `SIGNAL_API_URL` und `SIGNAL_NUMBER`, Standard leer; je Person freiwillig. In der öffentlichen Demo immer aus.
- **Drittland:** USA **[prüfen]**.
- **Empfehlung Pilot:** aus, solange nicht entschieden.

### E-Mail

<!-- flow: email -->

- **Empfänger und Rolle:** der SMTP-Anbieter des Betreibers (`EMAIL_HOST`). Auftragsverarbeiter **[prüfen]**.
- **Daten:** E-Mail-Adresse und Name der Person, offener Betrag und Zahlungsangaben der Kaffeekasse (Kontoinhaber, IBAN, Verwendungszweck, Überweisungs-QR), Name der Wache.
- **Personenbezug:** ja.
- **Auslöser:** Erinnerung der Kaffeekasse an Teilnehmende, die E-Mails gewählt haben, oder Test-E-Mail durch Kassenwart bzw. Master-Admin.
- **Schalter und Standard:** `EMAIL_HOST`, Standard leer; in der öffentlichen Demo immer aus.
- **Drittland:** je nach Anbieter **[prüfen]**.
- **Empfehlung Pilot:** nur mit einem Anbieter mit AV-Vertrag.

## Dienste außerhalb der Anwendung

Diese Wege entstehen durch den Betrieb des Servers. Die Anwendung erkennt sie
nicht selbst; sie stehen deshalb nur hier.

### Images und Updates

<!-- flow: images -->

- **Empfänger:** GitHub (Container-Registry `ghcr.io`, Release-Abfrage `api.github.com`, Installationsdateien `raw.githubusercontent.com`) bzw. ein eigener Spiegel (`WACHBUCH_REGISTRY`, `docs/OPERATIONS.md`).
- **Daten:** IP-Adresse des Servers, abgerufene Version.
- **Personenbezug:** keiner.
- **Auslöser:** Installation, `./wachbuch update` oder automatische Updates.
- **Empfehlung Pilot:** Updates im Wartungsfenster; im reinen LAN-Betrieb über einen eigenen Spiegel oder manuell.

### Healthcheck-Ping

<!-- flow: health_ping -->

- **Empfänger:** der Dienst hinter `PING_URL` (z. B. healthchecks.io) aus `deploy/hetzner/wachwerk-health.sh`.
- **Daten:** Aufruf der Adresse; bei Fehlern Hostname und Fehlerbeschreibung (z. B. „Sicherung zu alt“).
- **Personenbezug:** gering.
- **Empfehlung Pilot:** aus; Meldungen über Banner und Posteingang (Paket D).

### Offsite-Sicherung

<!-- flow: offsite -->

- **Empfänger:** das vom Betreiber gewählte Ziel: Hetzner Storage Box (`deploy/hetzner/offsite-storagebox.sh`), NAS oder USB-Datenträger (Paket D).
- **Daten:** vollständige Datenbanksicherung, mit GnuPG für den öffentlichen Schlüssel des Betreibers verschlüsselt (`BACKUP_ENCRYPT_REMOTE`); Klartext wird nie ausgelagert.
- **Personenbezug:** ja, verschlüsselt.
- **Frist:** laut Zielsystem (Storage Box: 30 Tage im Skript); siehe `LOESCHKONZEPT.md`.
- **Empfehlung Pilot:** USB-Rotation oder NAS vor Ort.

### Zertifikate

<!-- flow: acme -->

- **Empfänger:** Let's Encrypt (ACME) über Caddy, nur im Modus `domain`.
- **Daten:** Domainname; die Zertifikate stehen in öffentlichen Logs (Certificate Transparency).
- **Personenbezug:** keiner.
- **Empfehlung Pilot:** nicht nötig; im Modus `lan` stellt Caddy eine eigene CA aus.

### Betriebssystem

<!-- flow: os -->

- **Empfänger:** Paketquellen des Betriebssystems, Zeitserver (NTP), DNS-Resolver.
- **Daten:** IP-Adresse des Servers, abgefragte Namen.
- **Personenbezug:** keiner.
- **Empfehlung Pilot:** Sicherheitsupdates einschalten; Zeitserver im eigenen Netz, wenn vorhanden.

### Hosting

<!-- flow: hosting -->

- **Empfänger:** der Hoster, wenn der Server nicht vor Ort steht (`SiteProfile.hosting_provider`, erscheint in der Datenschutzinformation).
- **Daten:** alle Daten der Installation; Zugriff je nach Vertrag.
- **Personenbezug:** ja.
- **Rolle:** Auftragsverarbeiter **[prüfen]**.
- **Empfehlung Pilot:** Betrieb auf Pi oder Server im LAN der Wache, ohne Erreichbarkeit aus dem Internet (Startkriterium).

### Links für Nutzende

<!-- flow: user_links -->

- **Empfänger:** PayPal (PayPal.me-Link), Wero, Signal (Einladungslink der Wachengruppe), die Bank der Person (GiroCode), Kalender-Apps oder Kalenderdienste, in denen jemand das Kalender-Abo einträgt.
- **Daten:** Nur was die Person selbst überträgt, wenn sie den Link öffnet oder das Abo einträgt. Das Kalender-Abo enthält Termine der Wache ohne Personen; sein Link wirkt wie ein Passwort.
- **Personenbezug:** nur durch die Person selbst.
- **Empfehlung Pilot:** Kalender-Abo nur für Geräte der Wache; Zahlungslinks nach Entscheidung der Kasse.

### App-Stores

<!-- flow: app_stores -->

- **Empfänger:** Apple App Store bzw. TestFlight, Google Play, F-Droid.
- **Daten:** Download und Updates der App über das Konto der Person im jeweiligen Store; Angaben laut Data Safety der App.
- **Personenbezug:** ja, beim Store.
- **Empfehlung Pilot:** Verteilung nach Entscheidung des Betreibers; Diensthandys bevorzugen.

### Supportbericht

<!-- flow: support_report -->

- **Empfänger:** wer vom Master-Admin den Bericht bekommt (`/system/fehler/` → Supportbericht).
- **Daten:** Fehlerzeit, Korrelations-ID, Route, Kategorie, HTTP-Status, Version (`SUPPORT_EXPORT_FIELDS` in `core/diagnostics_export.py`); keine Personen, keine Inhalte.
- **Personenbezug:** keiner.
- **Empfehlung Pilot:** nur bei Bedarf und nur an die vereinbarte Ansprechperson.

## Pflege

- Jeder neue externe Dienst braucht einen Abschnitt mit `<!-- flow: KEY -->`.
- Ändert ein Paket Inhalt oder Empfänger eines Dienstes (z. B. Gesundheitsmeldungen per E-Mail oder Signal), wird dieser Abschnitt im selben PR angepasst, sobald es sie gibt auch `core/data_flows.py`.
- Bei jeder Änderung VVT, DSFA-Vorprüfung und Datenschutzinformation prüfen.
