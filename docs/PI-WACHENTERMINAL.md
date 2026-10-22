# Raspberry Pi als Wachen-Server mit Touch-Terminal

Ein Raspberry Pi 4 (4 GB) betreibt das Wachbuch direkt auf der Wache. Er spannt
ein eigenes WLAN auf. Ein Touch-Bildschirm am Pi ist das **Wachenterminal**: Die
Besatzung erledigt dort Übernahme, Desinfektion, Mängel, Material und Checklisten
ohne Handy. Wer möchte, verbindet zusätzlich die Wachbuch-App auf dem eigenen
Handy über dasselbe WLAN.

```
                 WLAN „Wachbuch“ (WPA2, Geräte untereinander getrennt)
   ┌──────────────┐        ┌──────────────────────────────────────────┐
   │ Handy (App)  │ ─────▶ │ Raspberry Pi 4                           │
   └──────────────┘ HTTPS  │  nginx (TLS) → Wachbuch → PostgreSQL     │
   ┌──────────────┐        │  Kiosk-Browser ──────▶ Touch-Bildschirm  │
   │ Laptop Admin │ ─────▶ │  optional: LAN-Kabel für Updates/Zeit    │
   └──────────────┘        └──────────────────────────────────────────┘
```

## 1. Hardware

| Teil | Empfehlung | Warum |
| --- | --- | --- |
| Raspberry Pi 4, 4 GB | mit aktivem Kühler | Dauerbetrieb, Datenbank |
| Speicher | **SSD über USB 3** (≥ 64 GB) | SD-Karten verschleißen durch Datenbank-Schreibzugriffe |
| Netzteil | offizielles 15 W/3 A | Spannungseinbrüche beschädigen Daten |
| Touch-Monitor | HDMI + USB-Touch, 15–22″ | große Tasten, Bedienung mit Handschuhen |
| Echtzeituhr | RTC-Modul (z. B. DS3231) | Der Pi 4 hat keine Uhr. Ohne Internet und RTC stimmen nach einem Stromausfall Einwirkzeiten, Fristen und TOTP-Codes nicht |
| Backup | USB-Stick oder zweite SSD | `backup`-Dienst schreibt nach `backups/` |
| optional | USV, LAN-Kabel | Updates und Zeitabgleich (NTP) |

## 2. Einrichtung

1. **Raspberry Pi OS (64-bit) mit Desktop** auf die SSD schreiben (Raspberry Pi Imager),
   Benutzer anlegen, einmal per LAN-Kabel ans Internet.
2. Quellcode holen und Einrichtung starten:
   ```bash
   git clone https://github.com/Katschko-IT/Rettungswache-Wachbuch.git
   cd Rettungswache-Wachbuch
   sudo WLAN_SSID="Wachbuch RW1" deploy/pi/setup-pi.sh
   ```
   Das Skript (wiederholbar):
   - installiert Docker aus dem offiziellen Docker-Repository (Schlüssel-Fingerabdruck wird geprüft) und Chromium,
   - richtet das WLAN mit NetworkManager ein: WPA2 mit zufälligem Passwort, die Geräte im WLAN sehen sich gegenseitig nicht (AP-Isolation), der Pi hat die Adresse `10.42.0.1` und den Namen `wachbuch.lan`,
   - erzeugt ein eigenes TLS-Zertifikat (10 Jahre) und trägt dessen Fingerabdruck als `LOCAL_TLS_CERT_SHA256` ein,
   - schreibt `.env` mit Zufallswerten für alle Schlüssel und Passwörter,
   - startet das Wachbuch mit `deploy/pi/docker-compose.pi.yml` (Speichergrenzen, zwei Gunicorn-Prozesse, TLS-Proxy, keine Internet-Dienste),
   - richtet den Kiosk-Browser ein, der beim Anmelden des Desktop-Benutzers startet.
3. **Ersteinrichtung**: im Browser `https://10.42.0.1/setup/` (Zertifikatswarnung einmal bestätigen)
   mit dem `SETUP_BOOTSTRAP_TOKEN` aus `.env`. Danach den Wert in `.env` leeren und
   `sudo touch /etc/wachbuch/setup-done`.
4. **Terminal registrieren**: `sudo deploy/pi/register-terminal.sh "Fahrzeughalle"`, dann `sudo reboot`.
   Der Kiosk-Browser öffnet den Registrierungslink einmal und löscht ihn danach.

Weitere Terminals (z. B. ein Tablet an der Wand) registriert ein Admin unter
**Team → Wachenterminals & PINs**; den angezeigten Link einmal auf dem Gerät öffnen.

## 3. Personal einmal erfassen

1. **Team → Benutzer anlegen** (Name, Benutzername, Rolle).
2. **Team → Wachenterminals & PINs → Start-PIN vergeben.** Die 6-stellige PIN wird
   einmal angezeigt und persönlich weitergegeben.
3. Beim ersten Anmelden am Terminal legt die Person ihre eigene PIN fest.
4. Handy (freiwillig): am Terminal **„Handy mit meinem Konto verbinden“** tippen und den
   QR-Code mit der Wachbuch-App scannen. Die App ist danach ohne Passwort angemeldet.

Ein Passwort braucht nur, wer das Wachbuch auch im Browser am eigenen Gerät nutzt.

## 4. Bedienung am Terminal

- **Ruhebildschirm**: das Wachen-Display (Uhr, Termine, Aufgaben, Fahrzeugstatus,
  Prüffristen) und unten „Antippen zum Anmelden“ sowie der QR-Code zum Verbinden der App.
- **Anmelden**: Namen antippen, PIN über den Ziffernblock eingeben.
- **Kachelmenü**: Fahrzeug übernehmen/desinfizieren, Übergabebuch, Mangel melden,
  Medizingeräte prüfen, Material, Aufgaben, Checklisten, Dienstanweisungen, Termine.
- **Abmelden**: Taste „Abmelden“ oder automatisch nach 2 Minuten ohne Eingabe
  (`TERMINAL_IDLE_SECONDS`). Die Restzeit steht oben im Balken.

## 5. Sicherheitsmodell

| Schutz | Umsetzung |
| --- | --- |
| PIN gilt nur am Terminal | Anmeldung braucht das Gerätegeheimnis (HttpOnly-Cookie, `SameSite=Strict`, gespeichert nur als SHA-256) **und** die PIN. Über App oder Internet gibt es keine PIN-Anmeldung. |
| Durchprobieren | 5 Fehlversuche sperren die PIN 15 Minuten; zusätzlich höchstens 20 Versuche je Terminal in 10 Minuten. Keine Folgen wie 123456 oder 111111. |
| Gemeinsamer Bildschirm | Abmeldung nach Inaktivität (Server und Browser), `Clear-Site-Data` beim Abmelden, kein Seitencache (`Cache-Control: no-store`), kein Service Worker. |
| Eingeschränkte Bereiche | PIN-Sitzungen erreichen nur Alltagsbereiche. Konto, Team, Einstellungen, Audit, Auswertungen, Chat/Post (Ende-zu-Ende-Schlüssel gehören nicht auf ein geteiltes Gerät), Push-Einstellungen und App-Tokens nur am eigenen Gerät. |
| Nachvollziehbarkeit | Jede Person arbeitet unter dem eigenen Konto; Audit `terminal.login`, `terminal.login_failed`, `terminal.pin_*`, `terminal.created/revoked`. |
| Verlust/Diebstahl | Terminal unter **Team → Wachenterminals** widerrufen: alle Sitzungen enden sofort. |
| WLAN | WPA2-PSK (CCMP), AP-Isolation; das WLAN-Passwort liegt in `/etc/wachbuch/wlan-psk`. |
| TLS ohne Internet | Eigenes Zertifikat. Die App vertraut genau diesem Zertifikat über den Fingerabdruck im QR-Code (kein Installieren einer Zertifizierungsstelle auf den Handys). Der Kiosk-Browser vertraut ihm über `--ignore-certificate-errors-spki-list`. |
| Kopplung Handy | Kopplungscode nur aus einer angemeldeten Sitzung, 120 s gültig, genau einmal einlösbar, gespeichert nur als Hash; das Handy erhält ein normales App-Token (90 Tage, widerrufbar unter Konto → App-Tokens). |

Die PIN ersetzt am Terminal die Zwei-Faktor-Anmeldung: Der zweite Faktor ist das
registrierte Gerät auf der Wache. Admins erledigen Verwaltungsaufgaben am eigenen
Gerät mit Passwort und MFA.

## 6. App im WLAN der Wache

- Der QR-Code auf dem Ruhebildschirm enthält `wachbuch://connect?url=https://10.42.0.1&pin=sha256/…`.
  Die App merkt sich den Fingerabdruck für diesen Server.
- Die App nutzt die Adresse `10.42.0.1` statt eines Namens: Android löst in einem
  WLAN ohne Internet keine Namen über dieses WLAN auf.
- **Android** meldet „WLAN hat keinen Internetzugriff“: „Verbunden bleiben“ wählen.
  Mit eingeschalteten mobilen Daten kann Android Verbindungen trotzdem über das
  Mobilnetz leiten; dann im WLAN-Menü „Verbindung ohne Internet beibehalten“ bzw.
  mobile Daten auf der Wache ausschalten. (Muss je Gerät getestet werden.)
- **iOS** fragt beim ersten Verbinden nach „Lokales Netzwerk“: erlauben.
- Außerhalb des WLANs ist der Server nicht erreichbar. Die App zeigt dann die
  zuletzt geladenen Daten (verschlüsselter Lesecache) und Erinnerungen an
  ablaufende Einwirkzeiten, die bereits geplant sind.

## 7. Betrieb

- **Updates**: LAN-Kabel anstecken, dann
  `git pull && docker compose -f docker-compose.yml -f deploy/pi/docker-compose.pi.yml up -d --build`.
- **Backups**: Der `backup`-Dienst sichert täglich nach `backups/`. Den Ordner auf einen
  USB-Datenträger legen und regelmäßig eine Wiederherstellung testen (`docs/OPERATIONS.md`).
- **Zeit**: RTC-Modul einbauen oder LAN mit NTP anschließen. Die Uhrzeit auf dem
  Ruhebildschirm regelmäßig prüfen.
- **Strom**: USV oder zumindest ein sauberes Herunterfahren (`sudo poweroff`) vor dem Ausstecken.
- **Ressourcen**: `docker stats` zeigt Speicher je Dienst; die Grenzen stehen in
  `deploy/pi/docker-compose.pi.yml`.

## 8. Alternativen und Grenzen

- **Öffentliches Zertifikat**: Mit eigener Domain kann ein Let's-Encrypt-Zertifikat per
  DNS-Challenge bezogen werden (braucht Internet zur Verlängerung). Dann
  `LOCAL_TLS_CERT_SHA256` leer lassen; Browser und App vertrauen ohne Zusatz.
- **Zugriff von unterwegs** nur über ein VPN der Organisation, nie durch Portfreigabe.
- **Echter Push** (Benachrichtigung bei geschlossener App) braucht Internet und das
  Push-Relay (`docs/PUSH-RELAY.md`). Im reinen WLAN-Betrieb erinnert die App lokal.
- **Nicht abgenommen**: Diese Anleitung und die Skripte sind ohne echten Pi, Touch-Monitor
  und Handys im Wachen-WLAN entstanden. Vor dem Einsatz eine Abnahme auf der Zielhardware
  durchführen (WLAN-Reichweite, Touch-Bedienung, Android/iOS im WLAN ohne Internet,
  Neustart nach Stromausfall, Wiederherstellung aus dem Backup).
