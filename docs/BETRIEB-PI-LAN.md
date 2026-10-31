# Betrieb im Wachen-Netz und auf dem Raspberry Pi: Überwachung

Diese Anleitung gilt für Wachwerk auf dem Raspberry Pi (`deploy/pi/setup-pi.sh`)
und auf einem Thin Client oder PC im Wachen-Netz (`install.sh --mode lan` oder
`--mode local`). Für einen Server im Internet gilt [`HETZNER.md`](HETZNER.md);
dort läuft dieselbe Prüfung.

Ziel (Roadmap 0.27, R-016): Ein Ausfall auf dem Pi wird in **unter 15 Minuten**
gemeldet – auch ohne Internet, im Browser im Wachen-Netz.

## 1. Überblick

Alle 5 Minuten prüft `wachwerk-health` auf dem Gerät selbst (systemd-Timer, als
root):

- Wachwerk antwortet über die Adresse der Wache (`/healthz/`)
- alle Dienste laufen; keiner ist „unhealthy“ oder startet ständig neu. Einen
  hängenden Dienst startet die Prüfung selbst neu (höchstens dreimal je Stunde,
  nie die Datenbank)
- höchstens 5 Serverfehler in 15 Minuten
- das neueste Backup ist jünger als 30 Stunden
- die Kopie außer Haus ist aktuell (wenn eingerichtet)
- die wöchentliche Wiederherstellungsprobe ist gelungen (sonntags automatisch)
- das automatische Update ist gelungen (wenn eingeschaltet)
- die Systemplatte ist zu weniger als 85 % belegt

**Wer es erfährt:** die Master-Admins aller echten Wachen dieser Installation
(nie Demo-Wachen, nie die gemeinsame Vorführ-Demo), dazu auf Wunsch eine feste
Betriebsadresse per E-Mail (`HEALTH_ALERT_EMAIL`). Andere Rollen, das
Wachenterminal und das Wachen-Display zeigen nichts davon.

**Wie es gemeldet wird:**

| Weg | Braucht Internet? | Was erscheint |
| --- | --- | --- |
| Banner im Browser | nein | „Technische Störung. …“ bzw. „Überwachung meldet sich nicht.“ über dem Inhalt, mit Link zu den Details |
| Posteingang „Für dich“ auf der Übersicht | nein | eine Nachricht je Störung („Wachwerk: technische Störung“), nach dem Beheben „Wachwerk: Störung behoben“ |
| System → „Betrieb und Datensicherung“ | nein | letzte Prüfung, alle Meldungen, neuestes Backup, Kopie außer Haus, Wiederherstellungsprobe |
| E-Mail | ja (SMTP) | dieselbe Nachricht an Master-Admins mit E-Mail-Adresse und an `HEALTH_ALERT_EMAIL`; nur mit `EMAIL_HOST` |
| Signal | ja | dieselbe Nachricht an selbst bestätigte persönliche Nummern, nie an die Gruppe der Wache |
| Web-Push | ja (Push-Dienst des Browsers) | nur mit `WEB_PUSH_ENABLED` und laufendem push-worker (auf dem Pi aus) |
| `PING_URL` (z. B. healthchecks.io) | ja | meldet auch, wenn das Gerät ganz aus ist oder kein Netz hat |

Die App 1.1 zeigt nur Meldungsarten, die sie kennt; technische Hinweise zum
Server erscheinen dort noch nicht. Für den Pilot ohne Internet gelten Banner und
Posteingang im Browser im Wachen-Netz als „gemeldet“ (Betreiberentscheidung
0.27). E-Mail, Signal und `PING_URL` sind optional.

**Was übertragen wird:** Die Prüfung schreibt `/var/lib/wachwerk-health/status.json`.
Die Datei enthält nur Codes, Zeiten und Zahlen – keine Texte, Hostnamen, Pfade
oder Geheimnisse. `web` und `notify-worker` binden den Ordner nur lesend ein;
Wachwerk übersetzt die Codes selbst. Die Nachrichten nennen nur den technischen
Zustand des Servers, keine Inhalte der Wache. Ein Ping an `PING_URL` enthält
dagegen den Hostnamen und die Fehlertexte; er geht an den Dienst, den die
Betreiber dort eintragen (Datenfluss an Dritte, im VVT aufführen).

**Wann gemeldet wird:** Ein Fehler wird gemeldet, wenn er bei zwei Prüfungen in
Folge besteht (`FAILS_BEFORE_ALERT=2`): ein Neustart oder ein kurzer Aussetzer
löst so nichts aus. Rechnerisch liegen zwischen Ausfall und Nachricht höchstens
zwei Prüfabstände (je 5 Minuten plus bis zu 35 Sekunden Versatz), die Dauer der
Prüfung und bis zu 30 Sekunden bis zum notify-worker – in der Regel 6 bis
12 Minuten, mit hängenden Aufrufen knapp 14. Die Abnahme misst das (Abschnitt 3).
Während eines automatischen Updates ruhen Erreichbarkeit und Dienste.

**Grenzen:** Fallen Datenbank, `web` oder `proxy` aus oder das ganze Gerät,
kann Wachwerk selbst nichts anzeigen: Banner und Posteingang brauchen `web`.
Läuft die Datenbank noch, verschickt der notify-worker E-Mail und Signal (mit
Internet); die Nachricht im Posteingang ist sichtbar, sobald `web` wieder läuft.
Ohne Internet bemerkt die Wache einen Ausfall von `web` nur am Gerät selbst
(Fehlerseite am Terminal) – dann gilt die Papier-Rückfallebene. Wer das
vermeiden will, richtet `PING_URL` mit Internet ein.

## 2. Einrichten

### Raspberry Pi

`setup-pi.sh` richtet die Überwachung ab 0.27 selbst ein (Schritt „Überwachung
einrichten“). Auf einem Pi, der vor 0.27 eingerichtet wurde, im
Repository-Ordner:

```bash
cd ~/Rettungswache-Wachbuch
git pull
sudo sh deploy/lan/setup-monitoring.sh
```

Das Skript trägt `COMPOSE_FILE` und `WACHWERK_HEALTH_DIR` in `.env` ein und
baut die Dienste aus dem Checkout neu (`docker compose up -d --build`). Danach
genügt im Repository-Ordner `sudo docker compose …` ohne `-f`-Angaben.

### Thin Client oder PC (`install.sh --mode lan` oder `--mode local`)

Die Installation muss Version 0.27 oder neuer haben (`wachbuch update`), sonst
richtet das Skript nur die Prüfung auf dem Gerät ein und meldet „Anzeige in
Wachwerk erst ab Version 0.27“.

```bash
sudo git clone https://github.com/Katschko-IT/Rettungswache-Wachbuch /root/wachwerk-src
sudo sh /root/wachwerk-src/deploy/lan/setup-monitoring.sh --dir /opt/wachbuch
```

Optional mit Ping nach außen (braucht Internet):
`--ping-url https://hc-ping.com/<uuid>`. Ein erneuter Aufruf ist gefahrlos und
behält eine eingetragene `PING_URL`. Neue Fassung der Prüfung später:
`sudo git -C /root/wachwerk-src pull` und das Skript erneut starten.

### Was das Skript tut

- installiert `deploy/hetzner/wachwerk-health.sh` als `/usr/local/bin/wachwerk-health`
- schreibt `/etc/wachwerk/health.env` (nur root):
  - Pi: `HEALTH_URL=https://localhost/healthz/`, `HEALTH_CA_FILE` = Zertifikat
    aus `setup-pi.sh`, `HEALTH_SERVICES` ohne feed- und push-worker, mit `proxy`
  - `--mode lan`: das Wurzelzertifikat von Caddy nach `/etc/wachwerk/lan-ca.crt`;
    geprüft wird `https://<WACHBUCH_HOSTNAME>/healthz/` lokal aufgelöst. Ist
    Caddy nicht erreichbar, prüft es `web` direkt über `http://127.0.0.1:<HTTP_PORT>`
  - `--mode local`: `http://127.0.0.1:<HTTP_PORT>/healthz/`
  - `FAILS_BEFORE_ALERT=2` (ein höherer Wert bleibt, das Skript warnt dann)
- legt dieselben systemd-Timer an wie `harden-host.sh`: Prüfung alle 5 Minuten,
  Wiederherstellungsprobe sonntags um 05:10
- setzt `WACHWERK_HEALTH_DIR=/var/lib/wachwerk-health` in `.env` und startet die
  geänderten Dienste neu, damit Wachwerk den Zustand anzeigt
- prüft einmal und zeigt das Ergebnis

**E-Mail und Signal:** E-Mail kommt, wenn `EMAIL_HOST` (und die übrigen
`EMAIL_*`-Werte) in `.env` stehen; eine feste Betriebsadresse zusätzlich mit
`HEALTH_ALERT_EMAIL=betrieb@example.org`. Danach die Dienste neu starten
(`wachbuch start` bzw. auf dem Pi `sudo docker compose up -d`). Signal: siehe
[`SIGNAL.md`](SIGNAL.md); die Master-Admins bestätigen ihre Nummer selbst.

### Befehle

```bash
sudo wachwerk-health --verbose              # jede Prüfung anzeigen
sudo wachwerk-health --test                 # Probemeldung
sudo journalctl -u wachwerk-health -n 50    # letzte Prüfungen
systemctl list-timers 'wachwerk-*'          # nächste Läufe
```

## 3. Meldungen prüfen

### Probemeldung

`sudo wachwerk-health --test` meldet sofort eine Störung „Testmeldung der
Überwachung“. Innerhalb einer Minute sehen die Master-Admins das Banner und die
Nachricht „Wachwerk: technische Störung“ (Übersicht neu laden). Bei der nächsten
regulären Prüfung (spätestens nach 5 Minuten) folgt „Wachwerk: Störung behoben“.

### Ausfallprobe (Abnahme: unter 15 Minuten)

Namen der Container: `sudo docker ps --format '{{.Names}}'`.

1. Uhrzeit notieren und den Backup-Dienst anhalten:
   `date; sudo docker stop rettungswache-wachbuch-backup-1`
2. Als Master-Admin die Übersicht alle paar Minuten neu laden. Uhrzeit notieren,
   wann Banner und Nachricht im Posteingang erscheinen
   (`sudo journalctl -u wachwerk-health -f` zeigt die Prüfungen mit).
3. Wieder starten: `sudo docker start rettungswache-wachbuch-backup-1`. Nach der
   nächsten Prüfung verschwindet das Banner, es folgt „Störung behoben“.
4. Dasselbe mit dem notify-worker (er stellt die Nachrichten sonst zu):
   `sudo docker stop rettungswache-wachbuch-notify-worker-1`. Die Prüfung stellt
   die Nachricht dann einmal über einen eigenen Lauf zu (im Journal „Meldung an
   die Master-Admins in Wachwerk zugestellt“). Danach wieder starten:
   `sudo docker start rettungswache-wachbuch-notify-worker-1` (ein von Hand
   angehaltener Dienst bleibt sonst auch nach einem Neustart aus).

| Datum | angehaltener Dienst | angehalten um | Banner/Nachricht um | Dauer | behoben um | Name |
| --- | --- | --- | --- | --- | --- | --- |
| | backup | | | | | |
| | notify-worker | | | | | |

### Überwachung schweigt

Kommt 20 Minuten lang kein neuer Stand (Timer aus, Gerät hängt, Platte voll),
zeigt Wachwerk „Überwachung meldet sich nicht“ mit der Zeit der letzten Prüfung
und schickt den Master-Admins einmal eine Nachricht. Nach einem Neustart des
Geräts wartet der notify-worker damit 20 Minuten, bis die Prüfung wieder lief.
Prüfen: `systemctl status wachwerk-health.timer` und
`sudo wachwerk-health --verbose`.

## 4. Überwachung abschalten

```bash
sudo systemctl disable --now wachwerk-health.timer wachwerk-restore-test.timer
```

Danach in `.env` `WACHWERK_HEALTH_DIR=` leeren und die Dienste neu starten
(`wachbuch start` bzw. auf dem Pi `sudo docker compose up -d`). Sonst zeigt
Wachwerk nach 20 Minuten dauerhaft „Überwachung meldet sich nicht“. Der Ordner
`/var/lib/wachwerk-health` kann dann weg.

## Kopie außer Haus und Wiederherstellung

Die Überwachung meldet auch eine fehlende oder veraltete Kopie außer Haus, sobald
eine eingerichtet ist (`/etc/wachwerk/offsite.env`). Für den Pi steht der Weg
dafür bis auf Weiteres in [`PI-WACHENTERMINAL.md`](PI-WACHENTERMINAL.md),
Abschnitt „Betrieb“; die Wiederherstellung in [`OPERATIONS.md`](OPERATIONS.md).
