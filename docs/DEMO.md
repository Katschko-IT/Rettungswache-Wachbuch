# Demo-Modus mit Musterdaten

Stand: 2. August 2026 (Server ≥ **0.15.0**).

Für lokale Tests und Vorführungen kann Wachbuch mit fiktiven Musterdaten
gestartet werden. **Nicht für Produktivsysteme.**

## Einschalten

In `.env`:

```bash
DEMO_MODE=true
DEMO_PASSWORD=Demo-Passwort-12345
MFA_ENABLED=false
MFA_REQUIRED=false
DEFAULT_STATION_NAME=Demo-Wache Musterstadt
```

Dann:

```bash
docker compose up --build -d
# migrate führt automatisch load_demo_data aus, wenn DEMO_MODE=true
```

Oder manuell:

```bash
docker compose exec web python manage.py load_demo_data
docker compose exec web python manage.py load_demo_data --reset   # neu befüllen
```

Ohne `DEMO_MODE` (nur lokal mit Debug):

```bash
python manage.py load_demo_data --force
```

## Demo-Konten

Gemeinsames Passwort: Wert von `DEMO_PASSWORD` (Standard `Demo-Passwort-12345`).

| Benutzer | Rolle |
| --- | --- |
| `demo-admin` | Master-Admin |
| `demo-schicht` | Schichtleitung |
| `demo-kasse` | Kassenwart |
| `demo-mitglied` | Mitglied |
| `demo-audit` | Auditor |

Auf der Startseite erscheinen die Konten, solange `DEMO_MODE=true` ist.
Unter `/vorfuehrung/` gibt es denselben One-Click-Einstieg, ohne Fachdaten.
Ein gelbes Banner „Demo-Modus“ ist überall sichtbar.

## Was wird angelegt?

- Module (Kalender, Aufgaben, Kasse, Feiertage, Checklisten, Pinnwand,
  Medizinprodukte, Fuhrpark, Lager, Organisation)
- Offene / laufende / erledigte **Übergaben** aus den letzten Schichten, mit
  Lesebestätigungen
- Termine tagsüber an Werktagen (relativ zum Besuch), Geburtstag in Kürze
- Kaffeekasse mit drei Monaten Verlauf: Beiträge, Einzahlungen, Einkäufe und
  Kassensturz
- Neuigkeiten mit Lesebestätigung, Pinnwand-Aushänge, Wiki-Artikel, Mängel
  mit Frist und Verlauf
- Fuhrpark (RTW, NEF, KTW) mit laufender Desinfektion, Medizinprodukte mit
  stimmigen STK/MTK/DGUV-Nachweisen, Lager mit Chargen und einem Rückruf,
  Schlüssel und Poolgeräte
- Erledigte Tagesaufgaben und Checklisten von heute

In der geteilten Demo trägt jeder Titel den Marker `[Demo]`, damit
`load_demo_data --reset` die Zeilen findet. Die Demo-Wache je Besuch kommt
ohne Marker aus, weil sie als Ganzes gelöscht wird; dort arbeiten zusätzlich
vier Kolleginnen und Kollegen ohne Zugang mit (Team, Lesebestätigungen,
Kaffeekasse).

Keine Patienten-, Alarm- oder Dienstplandaten.

## Sicherheit

- Standard ist `DEMO_MODE=false`
- Passwörter sind öffentlich dokumentiert – nur Loopback/Test
- Beim gemeinsamen Demo-Modus wird `MFA_REQUIRED` automatisch abgeschaltet.
  In der öffentlichen Demo (`DEMO_SANDBOX=true`) bleibt es wirksam: echte
  Konten brauchen den zweiten Faktor, Demo-Besuche nicht.

## Öffentliche Demo im Internet (z. B. `demo.rwsth.de`)

Für eine Demo, die jeder im Internet ausprobieren kann, taugt der gemeinsame
Demo-Modus oben nicht: Alle Besucher würden dieselben Daten sehen und ändern.
Dafür gibt es die **Demo-Wache je Besuch** (`DEMO_SANDBOX=true`):

- Auf der Anmeldeseite sind Benutzername **Demo** und Passwort **Demo** schon
  eingetragen. Wer sich so anmeldet (oder auf der Startseite „Demo starten“
  klickt), bekommt eine **eigene, neue Wache** mit Musterdaten und ist dort
  Master-Admin. Andere Besucher sehen davon nichts.
- Auf der Übersicht führt ein **Rundgang „Dein erster Schichtwechsel“** durch
  sechs kurze Aufgaben und hakt sie automatisch ab (Konzept und Recherche:
  [DEMO-KONZEPT.md](DEMO-KONZEPT.md)). Jeder Schritt führt direkt an die
  richtige Stelle – das Übergabeformular ist vorausgefüllt, für das Quittieren
  wechselt der Rundgang selbst in die Rolle „Mitglied“. Nach jedem Schritt
  bestätigt eine Meldung den Fortschritt, das Banner nennt auf jeder Seite den
  nächsten Schritt. Am Ende geht es zur leicht verständlichen Anleitung
  **„Selbst betreiben“** (`/selbst-betreiben/`) oder als Auditor ins Audit-Log.
- Die **Feedback-Seite** (`/feedback/`, [FEEDBACK.md](FEEDBACK.md)) ist in
  der öffentlichen Demo eingeschaltet; Rückmeldungen liest der Betreiber unter
  Einstellungen → Rückmeldungen.
- Ein Banner zeigt, wann die Demo endet, und wechselt die Rolle
  (Master-Admin, Schichtleitung, Kassenwart, Mitglied, Auditor) innerhalb
  derselben Demo-Wache. Auditoren landen dabei im Audit-Log. Formulare in
  anderen offenen Tabs bleiben nach einem Rollenwechsel gültig.
- **Abmelden beendet die Demo:** Die Demo-Konten werden sofort gesperrt, die
  Demo-Wache mit allen Eingaben wird gelöscht. Die Startseite bestätigt das.
- **Browser geschlossen?** Das Sitzungs-Cookie endet mit dem Browser. Die
  Demo-Wache wird nach `DEMO_SANDBOX_IDLE_MINUTES` (Standard 30) ohne
  Aktivität gelöscht, spätestens nach `DEMO_SANDBOX_MAX_MINUTES` (Standard 120).
  Ein zuverlässiges Signal „Tab geschlossen“ gibt es im Browser nicht; deshalb
  diese Fristen.
- Gesperrt sind Bereiche, die über die eigene Demo-Wache hinaus wirken:
  Impressum und Datenschutz der Installation, öffentliche Display-Links,
  Wachenterminal-Registrierung und Handy-Kopplung, App-Zugänge (API-Tokens),
  E-Mail-Einladungen und das Freigeben bestehender Konten der Installation.
  E-Mail- und Signal-Versand sind in diesem Modus ganz abgeschaltet,
  öffentliche Registrierung ebenso.
- Den **Sperrbildschirm des Touch-Terminals** zeigt die Demo trotzdem: als
  Vorschau unter Mehr → „Touch-Terminal (Vorschau)“ (`/demo/sperrbildschirm/`)
  mit den Daten der eigenen Demo-Wache – ohne Terminal-Registrierung, ohne
  Dienstkonto „Wachenterminal“ und ohne Absenden des Wachen-Codes.
- **Konten der Installation bleiben unberührt:** Gesperrt und gelöscht werden
  nur Konten, die in der Demo-Wache entstanden sind und nirgends sonst
  Mitglied sind – nie ältere Konten, nie Staff- oder Superuser-Konten.
  Anmeldeprotokolle der Demo-Konten (mit IP-Adresse) werden mitgelöscht.
- Schutz vor Missbrauch:
  - höchstens `DEMO_SANDBOX_MAX_ACTIVE` (Standard 100) laufende Demos,
  - `DEMO_SANDBOX_PER_IP_HOUR` (Standard 30) neue Demos je Anschluss und
    Stunde (IPv6 je /64-Netz). Eine Wache, ein Kreisverband oder ein
    Schulungsraum geht oft über eine einzige Adresse ins Netz; 30 reicht für
    eine Gruppe, die die Demo gemeinsam ausprobiert. Für Vorträge oder
    Messen vor großem Publikum höher setzen (z. B. 60). Wer schon in einer
    laufenden Demo ist, verbraucht beim erneuten Start nichts, und wer die
    Grenze erreicht, wird zur Vorführung ohne Anmeldung geleitet,
  - je Demo höchstens `DEMO_SANDBOX_MAX_WRITES` (Standard 400) Änderungen und
    `DEMO_SANDBOX_MAX_UPLOAD_MB` (Standard 25) MB an Dateien.

  Gezählt wird mit einem gesalzenen Hash der IP im Cache, nicht mit der IP
  selbst.

### Wer löscht?

Kassen- und Audit-Einträge sind append-only: Der Web-Prozess darf sie in
PostgreSQL nicht löschen (`grant_database_access`). Deshalb gibt es den Dienst
**`demo-cleaner`** (Compose-Profil `demo`). Er läuft mit den Rechten des
Datenbank-Eigentümers und löscht jede Minute beendete und abgelaufene
Demo-Wachen samt Konten und aller Einträge, die auf sie verweisen. Andere
Wachen bleiben unberührt. Er läuft als ein Prozess
(`purge_demo_sandboxes --watch`); sein Healthcheck prüft das Lebenszeichen,
das er nach jedem gelungenen Durchlauf schreibt. Von Hand:
`python manage.py purge_demo_sandboxes` (`--all` löscht auch laufende Demos).
Abgelaufene Sitzungen verlassener Demos löscht der Dienst `housekeeping`
(stündlich, in jedem Profil).

Ohne `demo-cleaner` sind beendete Demos zwar sofort unbrauchbar (Konten
gesperrt), die Daten bleiben aber liegen.

### Einrichten auf einem eigenen Server mit Subdomain

Ein Webhosting-Paket (z. B. Hetzner konsoleH) kann keine Docker-Container
ausführen. Wachwerk braucht einen kleinen eigenen Server, etwa eine
Hetzner-Cloud-Instanz mit Ubuntu 24.04 und 2 GB RAM. Die Domain bleibt beim
bisherigen Anbieter; nur eine Subdomain zeigt auf den neuen Server. So bleiben
bestehende Webseite und E-Mail-Postfächer der Domain unverändert.

Die vollständige Anleitung mit Härtung des Servers, Überwachung,
verschlüsselten Backups außer Haus und einem Betriebstest steht in
[HETZNER.md](HETZNER.md). In Kurzform:

1. **Server anlegen** und die öffentliche IPv4- (und IPv6-)Adresse notieren.
   Welche Hardware reicht: [HARDWARE.md](HARDWARE.md).
2. **DNS:** Beim Domain-Anbieter für `demo` einen A-Eintrag (und AAAA-Eintrag)
   auf diese Adresse anlegen. Prüfen: `dig +short demo.rwsth.de`.
3. **Server härten:** `deploy/hetzner/harden-host.sh` (SSH nur mit Schlüssel,
   Firewall, fail2ban, automatische Updates, Überwachung).
4. **Installieren** mit eingeschalteter Demo (auf dem Server):
   ```bash
   curl -fsSLO https://raw.githubusercontent.com/Katschko-IT/Rettungswache-Wachbuch/main/install.sh
   sudo sh install.sh --yes --name "Wachwerk Demo" --mode domain \
     --domain demo.rwsth.de --email postmaster@rwsth.de --demo --auto-update alle
   ```
   `--demo` setzt `DEMO_MODE=true`, `DEMO_SANDBOX=true`, das Profil `demo`
   (Aufräumdienst) und `MFA_REQUIRED=true`: Echte Konten brauchen einen
   zweiten Faktor, Demo-Besuche nicht.
5. **Einrichtungsassistent** unter `https://demo.rwsth.de/setup/` mit dem
   Einrichtungscode durchlaufen. Das Admin-Konto dort ist **dein eigenes**
   Betreiberkonto (nicht „Demo“), mit zweitem Faktor. Im Schritt Impressum
   „Öffentlich im Internet erreichbar“ ankreuzen und die Anbieterangaben
   vollständig eintragen – eine öffentliche Seite braucht ein Impressum
   (§ 5 DDG) und eine Datenschutz-Information.
6. Ausprobieren: Startseite → „Demo starten“, oder Anmelden mit Demo / Demo.

Auf der Hauptdomain kann ein Link oder eine Weiterleitung auf
`https://demo.rwsth.de` gesetzt werden.
