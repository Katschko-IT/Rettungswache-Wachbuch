# Abnahme-Checkliste: erster Aufbau des Pi-Wachenterminals

Zum Abhaken beim ersten echten Aufbau (Raspberry Pi 4, Touch-Monitor, eigenes WLAN).
Was nicht klappt: Punkt-Nummer notieren, Foto vom Bildschirm oder die Ausgabe der
Diagnose-Befehle (Abschnitt 9) mitschicken. Anleitung: `docs/PI-WACHENTERMINAL.md`.

Befehle laufen im Repository-Ordner auf dem Pi. Abkürzung für die Compose-Befehle
(`setup-pi.sh` trägt die Compose-Dateien als `COMPOSE_FILE` in `.env` ein, damit
alle Befehle die lokal gebauten Images nutzen):

```bash
cd ~/Rettungswache-Wachbuch
alias wb='sudo docker compose'
```

## 1. Hardware und System

- [ ] 1.1 Raspberry Pi OS **64-bit mit Desktop** (Bookworm), `uname -m` zeigt `aarch64`
- [ ] 1.2 System läuft von der **SSD** (`findmnt /` zeigt kein `mmcblk`)
- [ ] 1.3 Offizielles Netzteil; `vcgencmd get_throttled` zeigt `throttled=0x0`
- [ ] 1.4 Touch-Monitor: Bild über HDMI, Touch über separates USB-Kabel, eigenes Netzteil
- [ ] 1.5 RTC-Modul (DS3231): `dtoverlay=i2c-rtc,ds3231` in `/boot/firmware/config.txt`,
      neu starten, `sudo hwclock -r` zeigt die richtige Zeit
- [ ] 1.6 Kühlung: unter Last `vcgencmd measure_temp` unter 70 °C

## 2. Installation

- [ ] 2.1 LAN-Kabel mit Internet steckt
- [ ] 2.2 `sudo WLAN_SSID="Wachbuch RW1" deploy/pi/setup-pi.sh` läuft ohne Fehler durch
      (beim ersten Mal 10–20 Minuten)
- [ ] 2.3 Am Ende stehen WLAN-Name, WLAN-Passwort, Adresse und **Einrichtungscode** –
      abfotografieren
- [ ] 2.4 `wb ps` zeigt `web`, `db`, `redis`, `proxy`, `backup`, `notify-worker` als „running“/„healthy“

## 3. Erster Start und Ersteinrichtung

- [ ] 3.1 `sudo reboot`; der Touch-Bildschirm startet im Vollbild mit der **Ersteinrichtung**
- [ ] 3.2 Schrift und Tasten wirken passend groß
      (`python3 /usr/local/lib/wachbuch/kiosk-scale.py` zeigt den Zoom; bei 14″ Full-HD `1.5`)
- [ ] 3.3 Feld antippen: die **Bildschirmtastatur** erscheint von selbst
      (falls nicht: erscheint unten rechts die runde ⌨-Taste? → notieren)
- [ ] 3.4 Einrichtungscode klein und ohne Bindestriche eintippen → wird angenommen
- [ ] 3.5 Wache, Admin-Konto, Wachen-Code eingeben; „Dieses Gerät als Wachenterminal“ ist angekreuzt
- [ ] 3.6 Zahlenfelder (Wachen-Code, PLZ) zeigen den Ziffernblock
- [ ] 3.7 Abschlussseite → „Zum Sperrbildschirm“ zeigt Uhr, Karten, Foto und zwei QR-Codes oben rechts
- [ ] 3.8 USB-Tastatur anstecken und tippen: die Bildschirmtastatur verschwindet
- [ ] 3.9 `SETUP_BOOTSTRAP_TOKEN` in `.env` leeren, `sudo touch /etc/wachbuch/setup-done`

## 4. Wachenterminal

- [ ] 4.1 Antippen → runder Ziffernblock; falscher Code lässt die Punkte wackeln
- [ ] 4.2 Richtiger Code → Alltagsseite mit Kacheln, Übergaben, Kalender, Müll, Aufgaben
- [ ] 4.3 Übergabe am Bildschirm schreiben (Bildschirmtastatur), erscheint auf dem Sperrbildschirm
- [ ] 4.4 Nach 2 Minuten ohne Eingabe sperrt das Terminal von selbst
- [ ] 4.5 Pi neu starten → Sperrbildschirm erscheint wieder ohne Eingriff

## 5. Handys im Wachen-WLAN

Je ein **iPhone** und ein **Android-Handy**, mobile Daten zunächst **aus**.

- [ ] 5.1 QR ① „WLAN verbinden“ mit der Kamera-App scannen → Handy tritt dem WLAN bei
      (iPhone: ___ / Android: ___)
- [ ] 5.2 Android: Meldung „kein Internet“ → „Verbunden bleiben“
- [ ] 5.3 Wachbuch-App: QR ② „App verbinden“ scannen → Server wird ohne Zertifikatsfehler angenommen
- [ ] 5.4 iPhone fragt nach „Lokales Netzwerk“ → erlauben
- [ ] 5.5 Mit eigenem Konto anmelden; Übergaben und Fahrzeuge werden geladen
- [ ] 5.6 Team → Wachenterminal → „Handy-QR zeigen“ (als Admin am Laptop/Handy): App koppelt ohne Passwort
- [ ] 5.7 Mobile Daten **einschalten** und 5.5 wiederholen: lädt die App weiter? (iPhone: ___ / Android: ___)
- [ ] 5.8 Browser auf dem Handy: `https://10.42.0.1` öffnet nach einmaliger Zertifikatswarnung

## 6. Besatzung erfassen

- [ ] 6.1 Team → Einladungen: Einladung mit QR anlegen
- [ ] 6.2 Zweites Handy im WLAN scannt den QR, setzt eigenes Passwort, kann sich anmelden
- [ ] 6.3 Neues Konto erscheint unter Team; Rolle passt

## 7. Insel-Betrieb (ohne Internet)

- [ ] 7.1 LAN-Kabel abziehen; Terminal, App und Browser arbeiten weiter
- [ ] 7.2 Fahrzeug desinfizieren mit Einwirkzeit 1 Minute: Fahrzeug ist gesperrt,
      nach Ablauf Hinweis an die Besatzung (Posteingang „Für dich“, App-Erinnerung)
- [ ] 7.3 Mangel an einem Fahrzeug melden → Fahrzeug gesperrt; Freigabe nur durch Leitung
- [ ] 7.4 **Mit** LAN-Kabel: bekommt ein Handy im Wachen-WLAN Internet über den Pi?
      (ja / nein – wichtig für die Entscheidung, ob das WLAN Insel bleiben soll)

## 8. Strom, Zeit und Backup

- [ ] 8.1 Strom 10 Sekunden trennen: Pi startet, Wachbuch läuft, Uhrzeit stimmt (RTC)
- [ ] 8.2 Nächster Tag: ein Dump liegt im Backup-Volume
      ```bash
      sudo ls -l "$(sudo docker volume inspect -f '{{ .Mountpoint }}' $(sudo docker volume ls -q | grep backups-data))"
      ```
- [ ] 8.3 Dump auf USB-Stick kopieren (siehe `docs/PI-WACHENTERMINAL.md`, Abschnitt Betrieb)
- [ ] 8.4 Wiederherstellung prüfen: `wb run --rm restore-test` endet ohne Fehler

## 8a. Überwachung (Ziel: Ausfall eines Dienstes im Hintergrund in unter 15 Minuten gemeldet)

Anleitung und Grenzen: `docs/BETRIEB-PI-LAN.md`. Das Ziel gilt ohne Internet für
Backup-Dienst, Worker und `housekeeping` (notify-worker über den eigenen Lauf
der Prüfung), Backupalter, Kopie außer Haus, Wiederherstellungsprobe,
automatisches Update, Serverfehler und Plattenplatz, solange `web`, `proxy` und
Datenbank laufen. Ob auch ein Ausfall von `web`, `proxy` oder Datenbank ohne
Internet gemeldet werden muss, ist eine offene Entscheidung der Betreiber
(Alternative: eine eigene Fehlerseite im `proxy`; `docs/BETRIEB-PI-LAN.md`,
„Offene Fragen“). 8a.7 hält diese Grenze fest.

- [ ] 8a.1 `sudo wachwerk-health --verbose` zeigt nur `OK`-Zeilen (direkt nach der
      Einrichtung kann „noch kein Backup“ stehen – dann am nächsten Tag wiederholen)
- [ ] 8a.2 `systemctl list-timers 'wachwerk-*'` zeigt `wachwerk-health.timer` (alle
      5 Minuten) und `wachwerk-restore-test.timer` (sonntags)
- [ ] 8a.3 `sudo wachwerk-health --test`: als Master-Admin erscheinen nach dem Neuladen
      der Übersicht das Banner „Technische Störung“ und die Nachricht
      „Wachwerk: technische Störung“; spätestens 6 Minuten später „Störung behoben“
- [ ] 8a.4 Mitglied, Schichtleitung und das Wachenterminal sehen kein Banner
- [ ] 8a.5 Ausfallprobe: `date; sudo docker stop rettungswache-wachbuch-backup-1`, Zeit
      bis Banner bzw. Nachricht messen (unter 15 Minuten): ___ Minuten; danach
      `sudo docker start rettungswache-wachbuch-backup-1` → „Störung behoben“
- [ ] 8a.6 Wie 8a.5 mit `rettungswache-wachbuch-notify-worker-1`: die Nachricht kommt
      trotzdem (Journal: „Meldung an die Master-Admins in Wachwerk zugestellt“):
      ___ Minuten; danach wieder starten
- [ ] 8a.7 Grenze notieren: `sudo docker stop rettungswache-wachbuch-web-1` – ohne
      Internet zeigt nur das Terminal die Fehlerseite (kein Banner; die Nachricht im
      Posteingang ist erst sichtbar, wenn `web` wieder läuft); danach wieder starten.
      Nicht Teil des 15-Minuten-Ziels, solange die Betreiber das nicht anders
      entscheiden

## 9. Diagnose (bei Problemen mitschicken)

```bash
wb ps
wb logs --tail=80 web proxy
free -h; vcgencmd measure_temp; vcgencmd get_throttled
nmcli connection show wachbuch-ap | grep -E 'ssid|mode|ipv4.method'
journalctl --user -b | grep -i wachbuch-kiosk | tail -20
```

Geschätzter Speicherbedarf im Normalbetrieb: 1,3–2 GB von 4 GB (`free -h`, Zeile „Mem“, Spalte „used“).
