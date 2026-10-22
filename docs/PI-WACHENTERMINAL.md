# Raspberry Pi als Wachen-Server mit Touch-Terminal

Ein Raspberry Pi 4 (4 GB) betreibt das Wachbuch direkt auf der Wache. Er spannt
ein eigenes WLAN auf. Ein Touch-Bildschirm am Pi ist das **Wachenterminal**:
Gesperrt zeigt es das Wachen-Display; mit dem gemeinsamen vierstelligen
Wachen-Code öffnet es alles für den Tagesablauf (Übergaben, Kalender, Müll, Wetter,
Tages-, Wochen- und Monatsaufgaben) – ohne Handy. Wer möchte, verbindet
zusätzlich die Wachbuch-App auf dem eigenen Handy über dasselbe WLAN.

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
   - richtet den Kiosk-Browser ein, der beim Anmelden des Desktop-Benutzers startet,
   - stellt den Zoom des Kiosk-Browsers passend zur Bildschirmgröße ein (aus den
     EDID-Angaben des Monitors, z. B. 14″ Full-HD → 150 %; fest vorgeben mit `KIOSK_SCALE=1.25`),
   - trägt Name und Passwort des WLANs für den WLAN-QR-Code ein (`TERMINAL_WIFI_SSID`,
     `TERMINAL_WIFI_PASSWORD`) und erzeugt einen gut abtippbaren
     **Einrichtungscode** (`XXXX-XXXX-XXXX-XXXX-XXXX-XXXX`, ohne 0/O/1/I/L), den es am Ende anzeigt.
3. `sudo reboot`. Der Touch-Bildschirm öffnet jetzt **direkt die Ersteinrichtung**
   (`/terminal/` leitet dorthin, solange es noch keine Wache gibt).
   - Tastatur: Das Wachbuch bringt eine eigene **Bildschirmtastatur** mit (QWERTZ mit
     Umlauten, Ziffernblock für Zahlenfelder). Sie erscheint nur, wenn ein Eingabefeld
     angetippt wird, und verschwindet, sobald auf einer angeschlossenen Tastatur getippt
     oder eine Maus bewegt wird (dann 10 Minuten Pause; eine runde Taste unten rechts
     holt sie jederzeit zurück). Sie läuft nur am Kiosk (`localhost`) und auf
     registrierten Terminals – Handys und Laptops behalten ihre eigene Tastatur.
     Alternativ geht die Einrichtung auch vom Laptop/Handy im WLAN unter
     `https://10.42.0.1/setup/`.
   - **Schritt 1:** Einrichtungscode eingeben. Groß-/Kleinschreibung, Leerzeichen und
     Bindestriche spielen keine Rolle.
   - **Schritt 2:** Wache (Name, Anschrift, optional Wetter), eigenes Admin-Konto und –
     im Abschnitt *Wachenterminal* – den vierstelligen Wachen-Code. Das Häkchen
     „Dieses Gerät als Wachenterminal einrichten“ ist am Touch-Bildschirm vorbelegt
     (Adresse `localhost`) und auf Laptop/Handy leer.
   - Die Abschlussseite nennt die nächsten Schritte; mit „Zum Sperrbildschirm“ zeigt der
     Bildschirm sofort das Wachen-Display.
4. Danach `SETUP_BOOTSTRAP_TOKEN` in `.env` leeren und `sudo touch /etc/wachbuch/setup-done`.
   Der Assistent ist nach dem Abschluss ohnehin gesperrt (404).
5. Nur falls die Einrichtung über Laptop/Handy lief: den Touch-Bildschirm als Terminal
   einrichten – entweder dort als Admin anmelden und unter **Team → Wachenterminal**
   „Dieses Gerät als Terminal einrichten“ tippen, oder
   `sudo deploy/pi/register-terminal.sh "Fahrzeughalle"` und `sudo reboot`.
   Ein nicht registriertes Gerät zeigt unter `/terminal/` genau diese Anleitung.

Weitere Terminals (z. B. ein Tablet an der Wand) registriert ein Admin unter
**Team → Wachenterminal**; den angezeigten Link einmal auf dem Gerät öffnen.

## 3. Wachen-Code und Besatzung

1. **Team → Wachenterminal → Wachen-Code**: vierstelligen Code festlegen oder
   zufällig erzeugen lassen und persönlich an die Besatzung weitergeben (nicht aushängen).
2. Einträge im Alltagsmodus stehen unter dem Dienstkonto **„Wachenterminal“**.
   Wer etwas persönlich verantworten muss (Medizingeräte-Kontrollen,
   Fahrzeugübernahme und Desinfektion, Lesebestätigungen), nutzt das eigene Konto
   am Handy oder Rechner.
3. Handys verbinden (freiwillig): **Team → Wachenterminal → Handy-QR zeigen** bei der
   Person, die den Code mit der Wachbuch-App scannt. Die App ist danach ohne Passwort
   mit dem **eigenen** Konto angemeldet. Alternativ unter Konto → „Handy verbinden“.

## 4. Bedienung am Terminal

- **Sperrbildschirm**: großes Uhr-/Datumsfeld, darunter Glas-Karten für Wetter,
  offene und dringende Übergaben, Aufgaben des Tages (mit Fortschritt), heutige
  Termine und Müllabfuhr sowie eine Statuszeile der Fahrzeuge. Die Karten
  aktualisieren sich jede Minute. Im Hintergrund läuft leicht unscharf ein Foto aus
  dem Rettungsdienst – jeden Tag ein anderes aus 36 frei lizenzierten Bildern
  (Wikimedia Commons, Nachweis unten links, vollständig in `docs/BILDNACHWEISE.md`).
  Unten „Zum Entsperren antippen“, oben rechts zwei QR-Codes: **① WLAN verbinden**
  (Handy-Kamera öffnen, Code scannen, beitreten – Android und iOS) und
  **② App verbinden** (Serveradresse und Zertifikat für die Wachbuch-App).
- **Entsperren**: irgendwo antippen, der runde Ziffernblock erscheint; vier Ziffern
  eingeben. Ein falscher Code lässt die Punkte wackeln.
- **Alltagsmodus (Startseite)**: Wetter, offene Übergaben, heutige Termine,
  Müllabfuhr der nächsten 7 Tage, Tagesaufgaben zum Abhaken, Wochenübersicht und
  Monatsaufgaben; Kacheln für Übergabe schreiben, Übergabebuch, Kalender,
  Tagesaufgaben, Wochenplan, Mangel melden, Checklisten, Pinnwand, Neuigkeiten.
- **Sperren**: Taste „Sperren“ oder automatisch nach 2 Minuten ohne Eingabe
  (`TERMINAL_IDLE_SECONDS`). Die Restzeit steht oben im Balken.

Bewusst **nicht** im Alltagsmodus: Fuhrpark, Medizingeräte, Lager, Dienstanweisungen
(persönliche Verantwortung), Verwaltung von Aufgaben, Team, Einstellungen, Konto,
Chat und Post.

## 5. Sicherheitsmodell

| Schutz | Umsetzung |
| --- | --- |
| Code gilt nur am Terminal | Entsperren braucht das Gerätegeheimnis (HttpOnly-Cookie, `SameSite=Strict`, gespeichert nur als SHA-256) **und** den Wachen-Code. Über App oder Internet gibt es keinen Code-Zugang. |
| Durchprobieren | Nach je 5 Fehlversuchen sperrt das Terminal: 1 min, 5 min, 30 min, danach jeweils 24 h. Alle 10.000 Codes durchzuprobieren dauert damit Monate. Admins sehen die Sperre und können sie aufheben. Keine Folgen wie 1234 oder 1111. |
| Gemeinsamer Bildschirm | Sperren nach Inaktivität (Server und Browser), `Clear-Site-Data` beim Sperren, kein Seitencache (`Cache-Control: no-store`), kein Service Worker. |
| Eingeschränkte Bereiche | Der Alltagsmodus erreicht nur die oben genannten Bereiche; alles andere leitet zur Startseite zurück. |
| Dienstkonto | „Wachenterminal“ hat kein Passwort, kann kein App-Token erhalten, bleibt Rolle „Mitglied“ und funktioniert nur zusammen mit einem registrierten Terminal. |
| Nachvollziehbarkeit | Audit `terminal.unlocked_by_code`, `terminal.code_failed`, `terminal.code_changed`, `terminal.created/revoked/unlocked`. Personenbezogen ist im Alltagsmodus nur das Terminal, nicht die Person. |
| Verlust/Diebstahl | Terminal unter **Team → Wachenterminal** widerrufen; Code ändern, wenn er die Wache verlassen hat. |
| WLAN | WPA2-PSK (CCMP), AP-Isolation; das WLAN-Passwort liegt in `/etc/wachbuch/wlan-psk`. |
| TLS ohne Internet | Eigenes Zertifikat. Die App vertraut genau diesem Zertifikat über den Fingerabdruck im QR-Code (kein Installieren einer Zertifizierungsstelle auf den Handys). Der Kiosk-Browser vertraut ihm über `--ignore-certificate-errors-spki-list`. |
| Kopplung Handy | Kopplungscode nur aus einer persönlichen Sitzung oder von Admins, 120 s gültig, genau einmal einlösbar, gespeichert nur als Hash; das Handy erhält ein persönliches App-Token (90 Tage, widerrufbar unter Konto → App-Tokens). Für das Dienstkonto gibt es keine Kopplung. |

**Abwägung:** Ein gemeinsamer Code ist schneller als persönliche Anmeldungen, macht
Einträge aber nicht einer Person zuordenbar. Für Übergaben, Aufgaben und Hinweise ist
das auf Wunsch der Wache so gewollt; für alles mit persönlicher Verantwortung bleibt
der Bereich am Terminal gesperrt.

## 6. App im WLAN der Wache

- **WLAN beitreten**: QR-Code ① auf dem Sperrbildschirm mit der Kamera scannen
  (Format `WIFI:`; Android ab 10, iOS ab 11). Das Bild liefert der Server nur an
  registrierte Terminals aus. Wer den Bildschirm sieht, kann dem WLAN beitreten –
  Zugriff auf Daten gibt es trotzdem nur mit eigenem Konto; die Geräte im WLAN sehen
  sich gegenseitig nicht (AP-Isolation). Nach einem Passwortwechsel (`WLAN_PSK=… setup-pi.sh`)
  zeigt der QR-Code automatisch das neue Passwort.
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
