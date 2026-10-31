# Rettungswache-Wachbuch (Wachwerk)

[![CI](https://github.com/Katschko-IT/Rettungswache-Wachbuch/actions/workflows/ci.yml/badge.svg)](https://github.com/Katschko-IT/Rettungswache-Wachbuch/actions/workflows/ci.yml)
[![License: AGPL v3](https://img.shields.io/badge/License:AGPL_v3-blue.svg)](LICENSE)

Ein selbst gehostetes, mobiles **Wachbuch** für die interne Organisation einer
Rettungswache. Die Anwendung organisiert den Wachenalltag und ist **kein**
Einsatzleit-, Alarmierungs-, Dienstplanungs- oder Patientendokumentationssystem.

> **Live ausprobieren: [demo.rwsth.de](https://demo.rwsth.de/)** – anmelden mit
> **Demo** / **Demo**. Jeder Besuch bekommt eine eigene Wache mit erfundenen
> Daten und einen kurzen Rundgang; beim Abmelden (spätestens nach zwei Stunden)
> wird sie gelöscht. Wie die Demo betrieben wird: [`docs/DEMO.md`](docs/DEMO.md).

[Projektwebseite](https://katschko-it.github.io/Rettungswache-Wachbuch/) ·
[Quellcode der Webseite](site/index.html). Die Projektseite ist statisch, ohne
JavaScript und ohne externe Ressourcen. Veröffentlichung und Konfiguration sind in
[`site/README.md`](site/README.md) beschrieben.

## In 5 Minuten installieren

Voraussetzung ist ein Linux-Rechner (auch Raspberry Pi OS 64-bit) oder ein Mac mit
[Docker](https://docs.docker.com/engine/install/) und Compose v2 (ab 2.20), 64-Bit
(amd64 oder arm64), mindestens 1 GB, besser 2 GB RAM. Dann genügt ein Befehl:

```bash
curl -fsSL https://raw.githubusercontent.com/Katschko-IT/Rettungswache-Wachbuch/main/install.sh | sh
```

Wer das Skript vorher lesen möchte:

```bash
curl -fsSLO https://raw.githubusercontent.com/Katschko-IT/Rettungswache-Wachbuch/main/install.sh
less install.sh
sh install.sh
```

Der Installer prüft Docker, Architektur, Speicher und freie Ports, fragt nach dem
Namen der Wache und der Betriebsart und richtet alles in `/opt/wachbuch` (Linux,
dafür `sudo sh install.sh`) bzw. `~/wachbuch` (macOS) ein:

| Betriebsart | Erreichbar unter | Zertifikat |
| --- | --- | --- |
| `local` | `http://localhost:8090` auf diesem Rechner | keins (nur Loopback) |
| `lan` | `https://<Name oder IP>` im Netz der Wache | eigene Caddy-CA (`tls internal`) |
| `domain` | `https://wache.example.org` | Let's Encrypt |

Ohne Rückfragen, z. B. für Skripte:

```bash
sh install.sh --yes --name "RW Musterstadt" --mode domain \
  --domain wache.example.org --email ops@example.org
```

Am Ende zeigt der Installer die Adresse und den **Einrichtungscode**. Unter
`/setup/` legt der Assistent mit diesem Code die Wache und das erste Admin-Konto an.
Die erzeugte `.env` enthält alle Schlüssel: **offline sichern** (z. B. USB-Stick im
Tresor) – ohne sie sind Datenbank und Backups nicht mehr nutzbar.

Im Installationsordner liegt die kleine Verwaltung `wachbuch`:

```bash
/opt/wachbuch/wachbuch status          # Dienste und Gesundheit
/opt/wachbuch/wachbuch update          # Backup, neue Version laden, neu starten
/opt/wachbuch/wachbuch auto-update an  # nachts Sicherheitsupdates einspielen
/opt/wachbuch/wachbuch backup          # sofortiges Backup nach /opt/wachbuch/backups
/opt/wachbuch/wachbuch restore DATEI   # Wiederherstellung (mit Rückfrage)
/opt/wachbuch/wachbuch setup-code      # Einrichtungscode erneut anzeigen
/opt/wachbuch/wachbuch uninstall       # Container entfernen (Daten nur mit --purge)
```

**Updates im Alltag:** Die Images der neuesten Version und ihrer Vorgängerin
(jeweils der neueste Patch, z. B. 0.26.1 und 0.25.3) werden jede Woche neu
gebaut und enthalten so die Sicherheitsupdates von Debian/Alpine. Mit
`wachbuch auto-update an` holt die Installation sie nachts selbst (der Installer
fragt danach). Vorher entsteht ein Backup; startet die neue Fassung nicht,
läuft automatisch wieder die vorherige. `auto-update an alle` übernimmt
zusätzlich neue Versionen derselben Hauptversion – das empfiehlt sich für
Server im Internet: Ältere Versionen erhalten keine Neubauten mehr, und
Caddy und Redis wechseln nur mit einer neuen Version.

Alle Optionen, manuelle Installation und Reverse-Proxy-Varianten:
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

Eigener Server im Internet (z. B. Hetzner Cloud) mit Härtung, Überwachung,
verschlüsselten Backups außer Haus und Betriebstest:
[`docs/HETZNER.md`](docs/HETZNER.md).

Überwachung im Wachen-Netz und auf dem Raspberry Pi (Banner und Posteingang
für die Master-Admins, auch ohne Internet):
[`docs/BETRIEB-PI-LAN.md`](docs/BETRIEB-PI-LAN.md).

## Funktionen

Jede Wache schaltet nur die Module ein, die sie nutzt. Die **Übersicht** zeigt
anschließend gesammelt, wo Handlungsbedarf besteht: dringende Übergaben, offene
Mängel, Fahrzeuge, die nicht einsatzbereit sind, fällige Medizingeräte,
Unterschreitungen des Mindestbestands und ungelesene Dienstanweisungen.

### Wachalltag

- **Übergaben** mit Kategorie, Priorität, Status, Quittierung und Revisionen
- **Tagesaufgaben** als digitale Wandtafel (täglich, Wochentag, Zusatzaufgaben)
- **Checklisten** mit Einzelpunkten, Prüfintervall und Abschlussvermerk
- **Mängel** mit Frist, Foto und verantwortlicher Person; **Ausstattung**
  (Geräte, Schlüssel, Pools) mit Ausgabe und Rückgabe
- **Wachenkalender** mit Terminen, Feiertagen aller 16 Bundesländer und ICS-Abo
- **Pinnwand, Neuigkeiten** mit Lesebestätigung, **Wachen-Wiki**
- **Kaffeekasse** mit Monatsbeitrag: digitale „Mappe“ (bezahlt/offen/befreit),
  selbst abhaken, Kassensturz, Einkäufe für alle sichtbar, Erinnerung und
  GiroCode; Einzelstände nur für den Kassenwart ([Konzept](docs/KAFFEEKASSE.md)).
  Dazu Geburtstage

### Fachmodule

| Modul | Inhalt |
| --- | --- |
| 🚑 Fuhrpark | Fahrzeugzustand (Einsatzbereit, Eingeschränkt, Desinfektion, Werkstatt, Außer Dienst), Übernahme zu Schichtbeginn (Kilometer, Füllstände, Checkpunkte), Desinfektionsprotokoll nach Stufen mit Einwirkzeit-Sperre, Fristen für HU, UVV und Tragentisch, Fahrzeugmängel |
| 🩺 Medizingeräte | Bestandsverzeichnis nach MPBetreibV, STK-/MTK-/DGUV-Fristen mit Ampel, Funktionskontrollen mit Sperre bis zur Freigabe, Wartungen und Einweisungsnachweise |
| 📦 Lager & Material | Bestand je Lagerort, Chargen mit Verfallsdatum (First Expired, First Out), Kühlware mit verkürzter Haltbarkeit außerhalb des Kühlschranks, Mindestbestand, Bestellvorschlag, Sperren einer Charge nach Rückruf |
| 📖 Organisation | Dienstanweisungen mit Versionen, SHA-256-Prüfsumme und persönlicher Lesebestätigung; Telefonbuch der Wache |
| 🖥️ Wachen-Display | Vollbildanzeige für Monitor oder Fernseher über widerrufbare Display-Links |

Mustertexte oder Telefonnummern legt die Anwendung **nicht** selbst an.
Medizinische Inhalte und regionale Notrufnummern pflegt jede Wache eigenverantwortlich.

### Team, Sicherheit und Betrieb

- persönliche Konten mit stationsbezogenen Rollen (Mitglied, Schichtleitung,
  Kassenwart, Master-Admin, Auditor), Einladungen und Aktivierungslinks
- optional TOTP und Passkeys; QR-Login mit Bestätigung auf dem Mitarbeitergerät
- Audit-Log, das Auditoren ohne fachliche Freitexte einsehen
- strikte Content-Security-Policy, alle Skripte und Schriften lokal, keine Tracking-Cookies
- Einrichtungsassistent, installierbare Web-App (PWA), optional WebPush
- versionierte JSON-API (`/api/v1/`) für den quelloffenen
  [Wachbuch-Client](https://github.com/Katschko-IT/Wachbuch-Client) (iOS/Android)
- tägliche lokale PostgreSQL-Dumps mit Wiederherstellungsprobe

## Stack

Ein Docker-Compose-Projekt startet alles:

| Dienst | Aufgabe |
| --- | --- |
| `db` | PostgreSQL 17 mit getrennten App-/Feed-Rollen |
| `redis` | Cache und Rate-Limit-Zähler |
| `migrate` | einmalige Schema- und Bootstrap-Migration |
| `web` | Gunicorn/Django hinter Loopback-Port |
| `feed-worker` | periodischer Abruf freigegebener HTTPS-Quellen |
| `notify-worker` | benachrichtigt die Besatzung, wenn Desinfektions-Einwirkzeiten ablaufen |
| `push-worker` | Versand von Web-Push (und optional App-Push über ein Relay) aus der Outbox |
| `backup` | tägliche lokale PostgreSQL-Dumps, `restore-test` für die Probe |
| `caddy` | optionaler TLS-Proxy (Compose-Profil `https`, Betriebsarten `lan`/`domain`) |

Die Images (`ghcr.io/katschko-it/rettungswache-wachbuch`, `-backup`, `-db`) werden
für amd64 und arm64 veröffentlicht; `WACHBUCH_VERSION` in `.env` wählt die Version.
Authentifizierung läuft ausschließlich über lokale Django-Konten. TLS und
Netzfreigabe liegen beim Reverse-Proxy vor dem Container. Die Oberfläche kann über
den Browser als App installiert werden; Schreibvorgänge brauchen eine Verbindung
zum Wachenserver.

## Aus dem Quellcode starten (Entwicklung)

Für eigene Änderungen baut `compose.build.yml` die Images lokal. Am einfachsten
übernimmt der Installer auch hier `.env` und Start:

```bash
git clone https://github.com/Katschko-IT/Rettungswache-Wachbuch.git
cd Rettungswache-Wachbuch
sh install.sh --source . --build --mode local --dir "$HOME/wachbuch-dev"
```

Ohne Installer: `cp .env.example .env`, alle `replace-…`-Platzhalter durch
unabhängige Werte aus `openssl rand -hex 32` ersetzen, `SETUP_BOOTSTRAP_TOKEN`
setzen und

```bash
docker compose -f docker-compose.yml -f compose.build.yml up -d --build --wait
```

Die Startseite liegt dann unter `http://127.0.0.1:8090/`; der Port bindet
absichtlich nur an Loopback. `SECURE_COOKIES=false` ist ausschließlich für diesen
lokalen HTTP-Betrieb vorgesehen.

### Erstinstallation

Die Ersteinrichtung läuft **immer über den Assistenten** unter `/setup/`: Er fragt
den Einrichtungscode (`SETUP_BOOTSTRAP_TOKEN`) ab und führt durch Wachenname,
Anschrift, Zeitzone, erstes Admin-Konto, Rollen und Module; ohne Code existiert die
Route nicht. Nach dem Abschluss ist der Assistent gesperrt (404), der Code also
wertlos; leeren kann man ihn trotzdem. Details: [`docs/PILOT-HTTPS-LOCAL.md`](docs/PILOT-HTTPS-LOCAL.md).

Weitere Teamkonten legt der **Master-Admin** unter `/team/anlegen/` an oder per
Einladung; Freigaben bleiben stationsbezogen. Optional kann
`REGISTRATION_ENABLED=true` eine öffentliche Kontoanfrage erlauben; die Freigabe
bleibt beim Master-Admin. Technische Systemkonten bleiben unter `/django-admin/`.

Nur im Notfall (z. B. alle Admin-Konten gesperrt) legt
`docker compose exec web python manage.py createsuperuser` einen globalen
technischen Administrator an; `grant_station_admin BENUTZERNAME` gibt ihm danach die
Master-Admin-Rolle einer Wache. Dieser Weg ersetzt nicht den Assistenten.

### Test- und Vorführdaten (nur lokal)

Für lokale Tests befüllt `load_demo_data` eine separate Testdatenbank mit fiktiven
Konten, Übergaben, Terminen und Buchungen. Die Daten sind synthetisch und dürfen
nicht in einer Produktivinstanz verwendet werden:

```bash
DEMO_MODE=true python manage.py migrate
DEMO_MODE=true python manage.py load_demo_data --reset
```

Der Demo-Modus ist eine reine Testfunktion, keine Produkteigenschaft. In einer
Produktivinstanz bleibt `DEMO_MODE=false`; die Kennzeichnung der Testdaten erfolgt
über eigene Testkonten und eine separate Datenbank. Details:
[`docs/DEMO.md`](docs/DEMO.md).

Tests laufen in einer lokalen Python-Umgebung (wie in der CI):

```bash
pip install --require-hashes -r requirements.lock -r requirements-ci.lock
DJANGO_SECRET_KEY=ci-only-secret python manage.py test --settings=config.test_settings
```

Die CI führt dieselbe Suite zusätzlich gegen PostgreSQL in der Version des
db-Images aus (Job `django-postgres`, mit Update-Probe vom letzten Release).
Das Rezept für einen lokalen Lauf gegen PostgreSQL steht in
[`AGENTS.md`](AGENTS.md) § 6.

## Anmeldung per QR-Code

Der Browser zeigt unter `/anmelden/qr/` eine kurzlebige Anfrage. Ein bereits
angemeldetes Mitarbeitergerät bestätigt sie mit frischer Anmeldung, TOTP oder
Passkey. Der QR-Code enthält kein Passwort und kein dauerhaftes Token; das Secret
liegt nur im URL-Fragment, der Server speichert einen Hash. Bestätigen darf nur eine
aktive Mitgliedschaft derselben Wache. Der QR-Login ersetzt keine
Zwei-Faktor-Anmeldung, sondern verlagert die Bestätigung auf das Gerät.
Verbindlicher Vertrag: [`docs/QR-LOGIN-SECURITY-CONTRACT.md`](docs/QR-LOGIN-SECURITY-CONTRACT.md).

## Lokaler Betrieb und WAN-Ausfall

Der Wachenserver ist die Autorität: Anmeldung, Rollen, Formulare und Assets werden
lokal ausgeliefert. Es gibt im geprüften Kernpfad keine Cloud-Anmeldung, kein CDN,
keinen externen Font- oder Telemetrie-Aufruf.

| Szenario | Verhalten |
| --- | --- |
| WAN-Ausfall, LAN und Server erreichbar | Kernbetrieb funktioniert; durch Tests mit blockierten externen Socket-, DNS- und URL-Aufrufen belegt |
| Handy ohne Netz oder Server aus | **nicht umgesetzt**: keine Client-Datenbank, keine Outbox, keine Offline-Anmeldung; die PWA zeigt eine Offline-Seite |
| Server aus (Pilot) | Papier-Rückfallebene: vorab gedruckte Formulare, Fristenliste und Telefonbuch unter `/papier/`; danach nur den aktuellen Stand erfassen, die Blätter bleiben als Nachweis bei der Wachleitung |

Der Entwurf in [`docs/CLIENT-OFFLINE-CONTRACT.md`](docs/CLIENT-OFFLINE-CONTRACT.md)
ist **keine Funktion** und enthält offene Fachentscheidungen. Aussagen über einen
„Offline-Betrieb des Clients“ wären derzeit falsch. Details:
[`docs/OFFLINE-BETRIEB.md`](docs/OFFLINE-BETRIEB.md).

## Raspberry Pi mit eigenem WLAN und Touch-Terminal

Ein Raspberry Pi 4 (4 GB) kann das Wachbuch direkt auf der Wache betreiben: Er
spannt ein eigenes WLAN auf, ein Touch-Bildschirm daran ist das
**Wachenterminal**. Gesperrt zeigt es das Wachen-Display; Antippen öffnet einen
runden Ziffernblock für den vierstelligen Wachen-Code. Danach zeigt es alles für
den Tagesablauf (Übergaben, Kalender, Müll, Wetter, Tages-, Wochen- und
Monatsaufgaben) und sperrt sich nach Inaktivität wieder. Handys verbinden die App
per QR-Code über das WLAN, ohne Passwort und ohne Zertifikat auf dem Handy.

```bash
sudo WLAN_SSID="Wachbuch RW1" deploy/pi/setup-pi.sh
```

Soll der Pi nur als Server im vorhandenen Netz laufen (ohne eigenes WLAN und
Touch-Terminal), genügt der Installer oben mit `--mode lan`.

Hardware, Einrichtung, Sicherheitsmodell und Grenzen:
[`docs/PI-WACHENTERMINAL.md`](docs/PI-WACHENTERMINAL.md). Die Hintergrundfotos des
Sperrbildschirms stehen unter freien Lizenzen: [`docs/BILDNACHWEISE.md`](docs/BILDNACHWEISE.md).

## Reverse-Proxy mit TLS

Für Handys oder gemeinsame Wachenterminale steht vor dem Loopback-Port ein
Reverse-Proxy mit TLS. Der Installer richtet dafür den mitgelieferten Caddy ein
(`--mode lan` oder `--mode domain`) und setzt die passenden Werte. Bei einem eigenen
Proxy in `.env` mindestens:

```dotenv
SECURE_COOKIES=true
TRUSTED_PROXY=true
ALLOWED_HOSTS=wache.example.org
CSRF_TRUSTED_ORIGINS=https://wache.example.org
SITE_URL=https://wache.example.org
```

Der Proxy leitet auf `127.0.0.1:8090` weiter und setzt `X-Forwarded-Proto=https`.
Details stehen in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## Administration

Stations-Master-Admins legen unter `/einstellungen/` den Namen der Wache und die
sichtbaren Module fest. Unter `/team/` verwalten sie Nutzer, Einladungen, Freigaben
und Rollen. Technische Administratoren konfigurieren unter `/django-admin/`
Systemkonten und externe Quellen. Fachliche Datensätze sind dort bewusst nur
lesbar, damit Versionierung und Audit nicht umgangen werden.

## Externe Quellen

Zulässige Quellhosts werden zuerst kommasepariert mit `FEED_ALLOWED_HOSTS` in `.env`
freigegeben (Feeds und optionaler Müllkalender). Anschließend können HTTPS-RSS-Quellen
unter `/django-admin/core/feedsource/` angelegt werden. Der CSV-Importer unterstützt
das dokumentierte Bielefelder Verkehrsmeldungsformat. Private Zieladressen,
Weiterleitungen, andere Ports und Antworten über 2 MB werden abgewiesen. Bei einem
Upgrade von Version 0.2 müssen die Hosts bereits vorhandener Quellen vor dem Neustart
explizit in diese Liste übernommen werden.

## Datenschutz und Datengrenzen

Nicht in das Wachbuch gehören:

- Patienten-, Gesundheits-, Einsatz- oder Alarmierungsdaten
- Krankheitsgründe, Leistungsbewertungen oder private Konflikte
- gemeinsam genutzte Konten

Ein technischer Betrieb ersetzt keine Datenschutzprüfung, Mitbestimmung,
Löschfristen oder organisatorische Freigabe. Details stehen in
[`docs/SECURITY-PRIVACY.md`](docs/SECURITY-PRIVACY.md) und
[`docs/COMPLIANCE.md`](docs/COMPLIANCE.md).

## Projektstand

Version **0.26.1** ist ein Pilotstand für Entwicklung, Erprobung und
Präsentation, **keine Produktionsfreigabe**. Alle Seiten werden automatisiert und
per Browserlauf über alle Rollen geprüft (siehe
[`docs/REVIEW-2026-10-24.md`](docs/REVIEW-2026-10-24.md)); das ersetzt keine reale
Geräte- und Betriebsabnahme.

Vor einem Produktivbetrieb bleiben offen: Hardware- und Netzbetrieb in der Wache,
TLS/Reverse-Proxy im Dauerbetrieb, Kamera-Scanner, Passkeys und WebPush auf echten
Geräten, Wiederherstellung mit echten Backup-Daten, Datenschutzfolgenabschätzung
und Mitbestimmung sowie eine unabhängige Sicherheitsprüfung. Übersicht:
[`docs/GO-LIVE-CHECKLIST.md`](docs/GO-LIVE-CHECKLIST.md).

## Dokumentation

- [Projektwebseite](https://katschko-it.github.io/Rettungswache-Wachbuch/) · [Quellseite](site/index.html)
- [Review und Debugging 2026-10-22](docs/REVIEW-2026-10-22.md)
- [Roadmap](docs/ROADMAP.md) · [Konkurrenzanalyse](docs/KONKURRENZANALYSE.md) · [Funktionsvorschläge](docs/FUNKTIONSVORSCHLAEGE.md) · [UX-Plan](docs/UX-PLAN.md) · [Remediation-Roadmap](docs/REMEDIATION-ROADMAP-2026-08.md)
- [Fachmodule](docs/MODULES-RETTUNGSDIENST.md) · [Push-Relay für die App](docs/PUSH-RELAY.md)
- [Architektur](docs/ARCHITECTURE.md)
- [Betrieb, Backup und Updates](docs/OPERATIONS.md) · [Release veröffentlichen](docs/RELEASE-0.26.0.md)
- [Öffentliche Demo](docs/DEMO.md) – live unter [demo.rwsth.de](https://demo.rwsth.de/)
- [Lokaler Betrieb ohne WAN](docs/OFFLINE-BETRIEB.md)
- [API für Mobile-/Drittclients](docs/API.md)
- [Krypto nach BSI TR-02102](docs/CRYPTO-BSI.md)
- [QR-Login-Sicherheitsvertrag](docs/QR-LOGIN-SECURITY-CONTRACT.md)
- [AGPL-Client iOS/Android](docs/CLIENT.md) → [Wachbuch-Client](https://github.com/Katschko-IT/Wachbuch-Client)
- [Android-APK installieren](clients/wachbuch-mobile/docs/INSTALL-ANDROID.md) (`./clients/wachbuch-mobile/scripts/build-apk.sh`)
- [Datenschutz und Sicherheit](docs/SECURITY-PRIVACY.md)
- [Designregeln](docs/DESIGN-SYSTEM.md)

## Weiterentwicklung

Für Beiträge gelten gezielte Regressionstests, die vollständige Django-Suite,
Migrationprüfungen sowie die statischen Tests unter `site/tests/`. Testdatenbanken,
Zugangsdaten und lokale Arbeitsprotokolle gehören nicht in Veröffentlichungen.

## Mitwirken

Beiträge sind willkommen. Vor einem Pull Request bitte
[`CONTRIBUTING.md`](CONTRIBUTING.md) und für vertrauliche Meldungen
[`SECURITY.md`](SECURITY.md) beachten.

## Lizenz

Copyright (C) 2026 Darkspike1988. Veröffentlicht unter der GNU Affero General
Public License v3.0 oder später. Wer eine geänderte Fassung als Netzwerkdienst
betreibt, muss den Benutzern den zugehörigen Quellcode anbieten.
