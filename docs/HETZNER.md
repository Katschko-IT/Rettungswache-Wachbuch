# Wachwerk sicher im Internet: Betrieb auf einem Hetzner-Server

Diese Anleitung bringt Wachwerk auf einen eigenen Cloud-Server, z. B. als
öffentliche Demo unter `demo.rwsth.de`. Sie gilt genauso für jede andere
Domain und jeden anderen Anbieter mit Debian oder Ubuntu.

Was am Ende steht:

- Wachwerk unter `https://<deine-domain>` mit Let's-Encrypt-Zertifikat
- Server gehärtet: nur SSH-Schlüssel, Firewall, fail2ban, automatische
  Sicherheitsupdates
- Überwachung alle 5 Minuten mit E-Mail bei Ausfall
- tägliches Backup, verschlüsselt auf einer Storage Box außer Haus
- ein geübter Ablauf für Update, Rückkehr zur alten Version und
  Wiederherstellung

Zeitbedarf: etwa eine Stunde. Kosten: rund 4–6 € im Monat für den Server,
etwa 3–4 € für die Storage Box.

> **Grundregel für eine öffentliche Instanz:** Keine echten Daten von
> Kolleginnen, Kollegen, Patientinnen oder Patienten. Die Demo arbeitet mit
> Musterdaten, die beim Abmelden gelöscht werden (docs/DEMO.md).

---

## 0. Vorbereitung auf deinem Rechner

1. **SSH-Schlüssel** (falls noch keiner da ist):
   ```bash
   ssh-keygen -t ed25519 -C "dein-name@laptop"
   cat ~/.ssh/id_ed25519.pub    # diesen Text bei Hetzner hinterlegen
   ```
2. **Überwachung:** kostenloses Konto bei [healthchecks.io](https://healthchecks.io)
   (Betreiber in der EU) anlegen, einen Check „Wachwerk“ mit
   *Period 5 minutes* und *Grace 10 minutes* erstellen und die Ping-Adresse
   kopieren (`https://hc-ping.com/…`). Bleibt der Ping aus oder meldet der
   Server einen Fehler, kommt eine E-Mail.
3. **Externe Prüfung** (empfohlen): healthchecks.io bekommt nur die Meldungen
   des Servers selbst, und der prüft sich über `127.0.0.1`. Falsches DNS, eine
   falsch eingestellte Hetzner-Firewall oder ein Zertifikat, das nur von
   außen scheitert, bleiben dort grün. Deshalb zusätzlich einen
   unabhängigen Dienst (z. B. Uptime Kuma auf einem anderen Rechner oder ein
   kostenloser Uptime-Monitor) alle 5 Minuten
   `https://demo.rwsth.de/healthz/` abrufen lassen, mit Stichwortprüfung auf
   `"status": "ok"` und E-Mail bei Ausfall.
4. **Backup-Schlüssel** (für Schritt 6), einmalig auf deinem Rechner:
   ```bash
   gpg --default-preference-list "AES256 AES192 AES SHA512 SHA384 SHA256 ZLIB BZIP2 ZIP Uncompressed" \
       --quick-generate-key "Wachwerk Backup <deine@adresse.de>" rsa4096 encr never
   gpg --armor --export "Wachwerk Backup" > wachwerk-backup.asc
   ```
   Die Liste der Voreinstellungen sorgt dafür, dass sich die Backups mit
   **jeder** GnuPG-Version entschlüsseln lassen. Ohne sie kündigen Schlüssel
   aus GnuPG 2.3 oder neuer (Ubuntu 24.04, aktuelle macOS- und
   Windows-Pakete) das AEAD-Format an; solche Backups öffnet erst GnuPG 2.3,
   Debian 12 (GnuPG 2.2) und andere OpenPGP-Programme nicht. Einen schon
   vorhandenen Schlüssel stellst du so um (Rückfrage mit „j“ bestätigen) und
   exportierst ihn danach neu:
   ```bash
   gpg --edit-key "Wachwerk Backup" "setpref AES256 AES192 AES SHA512 SHA384 SHA256 ZLIB BZIP2 ZIP Uncompressed" save
   ```
   `offsite-storagebox.sh` und der Backup-Dienst weisen auf einen solchen
   Schlüssel hin.

   Auf den Server kommt nur `wachwerk-backup.asc` (öffentlich). Den privaten
   Schlüssel sicherst du zusätzlich offline
   (`gpg --armor --export-secret-keys "Wachwerk Backup" > privat.asc`, z. B. auf
   einen USB-Stick im Schrank). Ohne ihn lassen sich die Backups nicht öffnen.

## 1. Server anlegen (Hetzner Cloud Console)

| Einstellung | Wert |
| --- | --- |
| Standort | Nürnberg oder Falkenstein (Deutschland) |
| Image | Debian 12 oder Ubuntu 24.04 |
| Typ | 2 vCPU, 4 GB RAM, 40 GB Platte – z. B. CX22 (Intel/AMD) oder CAX11 (ARM, Images gibt es für beide) |
| Netzwerk | öffentliche IPv4 und IPv6 |
| SSH-Schlüssel | deinen öffentlichen Schlüssel aus Schritt 0 |
| Backups | optional (Hetzner-Snapshots, +20 %); ersetzt nicht Schritt 6 |

**Firewall** (Cloud Console > Firewalls, dem Server zuweisen). Sie wirkt vor
dem Server und schützt auch dann, wenn auf dem Server etwas falsch
eingestellt ist:

| Richtung | Protokoll | Port | Quelle |
| --- | --- | --- | --- |
| eingehend | TCP | 22 | am besten nur deine IP-Adresse, sonst „Any“ |
| eingehend | TCP | 80 | Any IPv4, Any IPv6 |
| eingehend | TCP | 443 | Any IPv4, Any IPv6 |
| eingehend | ICMP | – | Any (für `ping`) |

Ausgehend bleibt alles offen (Updates, Let's Encrypt, Storage Box).

**Auftragsverarbeitung:** Sobald personenbezogene Daten auf dem Server liegen
(Konten, Feedback mit Name oder E-Mail), brauchst du mit Hetzner einen
Vertrag zur Auftragsverarbeitung (AVV). Hetzner bietet ihn im Kundenkonto
(accounts.hetzner.com) zum Abschluss online an.

## 2. DNS-Eintrag (konsoleH bei Hetzner)

In konsoleH die Domain `rwsth.de` öffnen > *DNS-Verwaltung*:

| Name | Typ | Wert |
| --- | --- | --- |
| `demo` | A | IPv4 des Servers |

Prüfen (nach ein paar Minuten): `dig +short demo.rwsth.de` zeigt die IPv4.

**Keinen AAAA-Eintrag (IPv6) anlegen.** Das Wachbuch veröffentlicht Caddy
nur über IPv4. Besucher mit IPv6 kommen trotzdem an: Ohne AAAA-Eintrag
nehmen ihre Geräte IPv4. Mit AAAA-Eintrag und IPv6-Port reichte Docker
IPv6-Verbindungen über seinen Hilfsprozess `docker-proxy` weiter, und das
Wachbuch sähe alle IPv6-Besucher unter derselben internen Adresse. Die
Anmeldesperre nach Fehlversuchen und die Grenzen je Anschluss (Demo-Starts,
Feedback) träfen dann alle IPv6-Besucher gemeinsam. Sinnvoll ist ein
AAAA-Eintrag erst, wenn der Docker-Daemon IPv6 mit `ip6tables` weiterleitet
(`"ipv6": true` in `/etc/docker/daemon.json`, `ip6tables` ist ab Docker 27
Standard) und eine eigene Compose-Ergänzung dem Netz `web-ingress` IPv6 gibt
(`enable_ipv6: true`) und Caddy zusätzlich auf `[::]` veröffentlicht. Ob dann
die echten Adressen ankommen, zeigt Test 16 in Abschnitt 7.

## 3. Server härten

Als root anmelden und das Härtungsskript ausführen:

```bash
ssh root@<IPv4>
apt-get update && apt-get install -y git
git clone --depth 1 https://github.com/Katschko-IT/Rettungswache-Wachbuch.git /root/wachwerk-src
sh /root/wachwerk-src/deploy/hetzner/harden-host.sh --user michael \
   --ping-url https://hc-ping.com/<deine-uuid>
```

Das Skript (`deploy/hetzner/harden-host.sh`, wiederholbar):

- installiert Docker und Compose aus dem offiziellen Docker-Repository,
- legt den Benutzer `michael` mit sudo an und übernimmt den SSH-Schlüssel
  (von root oder, bei `sudo sh …`, vom aufrufenden Benutzer),
- prüft, dass `michael` einen nutzbaren Schlüssel hat und sudo wirklich geht
  (Passwort oder, ohne Passwort, sudo ohne Passwort) – sonst bricht es ab,
  **bevor** es SSH verändert,
- stellt SSH auf „nur Schlüssel, kein root, nur dieser Benutzer“ um,
- schaltet die Firewall `ufw` ein (SSH gedrosselt auf dem Port, auf dem sshd
  lauscht, dazu 80 und 443) und fail2ban für SSH,
- spielt Sicherheitsupdates täglich ein, auch für Docker (bei Bedarf Neustart
  um 04:30),
- setzt Docker auf `live-restore`, Log-Rotation und `no-new-privileges` (nur
  der optionale Signal-Dienst hebt es für sich auf, sein Image braucht setuid),
- legt auf Servern mit weniger als 4 GB RAM 2 GB Swap an,
- richtet die Überwachung `wachwerk-health` ein (alle 5 Minuten) und eine
  Wiederherstellungsprobe des neuesten Backups (sonntags 05:10).

**Wichtig:** Bevor du die root-Sitzung schließt, in einem **zweiten**
Terminal `ssh michael@<IPv4>` und dort `sudo -v` testen. Klappt das nicht, in
der ersten Sitzung `rm /etc/ssh/sshd_config.d/10-wachwerk.conf && systemctl reload ssh`.

- Bietet dein ssh-agent viele Schlüssel an, scheitert die Anmeldung nach fünf
  Versuchen („Too many authentication failures“), und fail2ban sperrt deine
  Adresse für eine Stunde. Dann den Schlüssel direkt angeben:
  `ssh -o IdentitiesOnly=yes -i ~/.ssh/id_ed25519 michael@<IPv4>`.
- Die Konsole der Hetzner Cloud Console (Server > Konsole) braucht ein
  Konto **mit Passwort**. Ohne Passwort (sudo ohne Passwort) bleibt im Notfall
  nur das Rettungssystem (Server > Rescue). Wer die Konsole als Notzugang
  will: `sudo passwd michael`.
- Läuft sshd auf einem anderen Port als 22, den Port auch in der
  Hetzner-Firewall (Schritt 1) freigeben.

## 4. Wachwerk installieren

Ab jetzt als `michael`:

```bash
ssh michael@<IPv4>
curl -fsSL https://raw.githubusercontent.com/Katschko-IT/Rettungswache-Wachbuch/main/install.sh \
  | sudo sh -s -- --mode domain --domain demo.rwsth.de --email deine@adresse.de \
       --name "Wachwerk Demo" --demo --auto-update alle
```

- `--mode domain` holt das Zertifikat von Let's Encrypt (DNS aus Schritt 2
  muss stimmen, Ports 80/443 offen sein).
- `--demo` schaltet die öffentliche Demo ein: `DEMO_MODE=true`,
  `DEMO_SANDBOX=true`, Profil `demo` (Aufräumdienst) und Pflicht zur
  Zwei-Faktor-Anmeldung für alle echten Konten. Ohne `--demo` entsteht eine
  normale Installation für eine Wache.
- `--auto-update alle` spielt nachts neu gebaute Images und neue Versionen
  derselben Hauptversion ein (mit Backup vorher und automatischer Rückkehr,
  falls der Start scheitert). Für einen Server im Internet ist das die
  richtige Wahl: Mit `sicherheit` bliebe er auf seiner Version und bekäme
  nach zwei neueren Versionen keine neu gebauten Images mehr.
- `--demo` setzt Version 0.26.0 oder neuer voraus; ältere lehnt der
  Installer ab.

Am Ende stehen Adresse und **Einrichtungscode** auf dem Bildschirm.

## 5. Ersteinrichtung

1. `https://demo.rwsth.de/setup/` öffnen, den Einrichtungscode eingeben.
2. **Dein eigenes Betreiber-Konto** anlegen: langes Passwort
   (Passwort-Manager) und direkt danach den zweiten Faktor (App oder Passkey).
   Auf einer öffentlichen Instanz ist er Pflicht.
3. **Impressum und Datenschutz** im Assistenten vollständig ausfüllen
   (Name, ladungsfähige Anschrift, E-Mail). Eine öffentlich erreichbare Seite
   braucht ein Impressum (§ 5 DDG).
4. Der Einrichtungscode ist danach von selbst wertlos: Nach dem Abschluss
   antwortet `/setup/` nicht mehr (404).
5. Abmelden, auf der Anmeldeseite **Demo / Demo** ausprobieren.

## 6. Backups außer Haus (Hetzner Storage Box)

1. In der Hetzner Console eine **Storage Box** (kleinste Größe reicht)
   bestellen, Standort Deutschland. Unter *Einstellungen* „SSH-Support“ und
   „Externe Erreichbarkeit“ einschalten, Passwort setzen.
2. Öffentlichen Backup-Schlüssel auf den Server kopieren:
   ```bash
   scp wachwerk-backup.asc michael@<IPv4>:
   ```
3. Auf dem Server:
   ```bash
   sudo sh /root/wachwerk-src/deploy/hetzner/offsite-storagebox.sh \
      --storagebox u123456 --gpg-key ~/wachwerk-backup.asc
   ```
   Das Skript fragt einmal nach dem Storage-Box-Passwort, hinterlegt danach
   einen eigenen SSH-Schlüssel und legt sofort das erste verschlüsselte
   Backup an. Erst danach schaltet es den stündlichen Timer ein.
4. **Snapshots der Storage Box einschalten** (Hetzner Console > Storage Box >
   Snapshots > automatische Snapshots): täglich, so viele behalten, wie der
   Tarif erlaubt. Der SSH-Schlüssel des Servers darf Dateien auf der Box
   löschen – wer den Server übernimmt, könnte also auch die Kopien dort
   entfernen. Snapshots lassen sich nur in der Hetzner Console löschen, nicht
   vom Server aus; sie sind die Kopie, die einen kompromittierten Server
   übersteht.

Danach gilt:

- Der Backup-Dienst legt täglich einen Dump an (7 Tage auf dem Server).
- Jeder Dump wird mit deinem öffentlichen Schlüssel verschlüsselt und
  stündlich auf die Storage Box kopiert. Dort bleibt jede Kopie 30 Tage,
  mindestens aber die sieben neuesten (`OFFSITE_KEEP_MIN` in
  `/etc/wachwerk/offsite.env`).
- Auf der Storage Box wird nie etwas gelöscht, nur weil es auf dem Server
  fehlt. Ein neu aufgesetzter oder geleerter Server lässt die älteren Kopien
  dort also stehen – genau die braucht man nach einem Totalausfall.
- `wachwerk-health` meldet, wenn die letzte Kopie scheiterte oder seit mehr
  als 30 Stunden keine neue verschlüsselte Datei entstanden ist (z. B. weil
  der Schlüssel im Backup-Dienst fehlt).
- Auf der Storage Box liegt nichts im Klartext. Der private Schlüssel ist
  nur bei dir.

Ältere Installationen (vor Version 0.26.0) spiegelten den Ordner mit
`rsync --delete`. Das Skript einfach noch einmal mit denselben Angaben
starten; es ersetzt das Kopierskript und behält Schlüssel und Ordner.

## 7. Betriebstest: einmal alles durchspielen

Erst wenn diese Tabelle abgehakt ist, ist der Betrieb erprobt.

| # | Test | So geht's | Erwartet |
| --- | --- | --- | --- |
| 1 | Zustand | `sudo wachwerk-health --verbose` | alle Zeilen `OK` |
| 2 | Alarm | `sudo wachwerk-health --test` | Ausgabe „Meldung an …/fail gesendet“, E-Mail von healthchecks.io in wenigen Minuten |
| 3 | Ausfall | `sudo /opt/wachbuch/wachbuch stop`, 15 Minuten warten, dann `… start` | E-Mail „down“, danach „up“ |
| 4 | Offene Ports | von deinem Rechner: `nmap -Pn demo.rwsth.de` | nur 22, 80, 443 |
| 5 | TLS | [SSL Labs](https://www.ssllabs.com/ssltest/) mit `demo.rwsth.de` | Note A oder A+ |
| 6 | Sicherheits-Header | `curl -sI https://demo.rwsth.de/` oder [securityheaders.com](https://securityheaders.com) | `Strict-Transport-Security`, `Content-Security-Policy`, `X-Frame-Options: DENY`, kein `Server`-Header (die Umleitung auf Port 80 nennt noch „Caddy“) |
| 7 | SSH-Sperre | fünfmal mit falschem Benutzer anmelden, dann `sudo fail2ban-client status sshd` | deine IP steht unter „Banned“ (`sudo fail2ban-client unban <IP>`) |
| 8 | Demo | Demo/Demo anmelden, etwas anlegen, abmelden | Startseite meldet „Demo beendet“, `wachbuch logs demo-cleaner` zeigt die Löschung |
| 9 | Backup | `sudo /opt/wachbuch/wachbuch backup` | neue Datei, verschlüsselte Kopie in `/var/lib/wachwerk-offsite` |
| 10 | Wiederherstellungsprobe | `sudo systemctl start wachwerk-restore-test`, dann `sudo journalctl -u wachwerk-restore-test -n 5` | „Restore-Test erfolgreich“: Dump in Testdatenbank eingespielt, Tabellen geprüft, Testdatenbank entfernt |
| 11 | Wiederherstellen aus der Storage Box | Datei mit `sftp -P 23 u123456@u123456.your-storagebox.de` holen, **auf einem zweiten Rechner** `gpg --output rwsth.dump --decrypt <datei>.gpg`, auf den Server kopieren, `sudo /opt/wachbuch/wachbuch restore ~/rwsth.dump` | Stand des Backups ist wieder da (vorher wird automatisch ein Sicherheits-Backup erstellt); ohne die Voreinstellungen aus Schritt 0 braucht das Entschlüsseln GnuPG 2.3 oder neuer |
| 12 | Update | `sudo /opt/wachbuch/wachbuch update` | Backup, neue Version, alle Dienste gesund |
| 13 | Zurück zur alten Version | `sudo /opt/wachbuch/wachbuch update <alte-version>` | alte Version läuft wieder |
| 14 | Neustart | `sudo reboot`, 3 Minuten warten | Seite erreichbar, Test 1 grün |
| 15 | Automatische Updates | `sudo /opt/wachbuch/wachbuch auto-update status` | Zeitplan aktiv, letzter Lauf ohne Fehler; Test 1 zeigt „automatisches Update (…): Alles aktuell“ |
| 16 | IPv6 | `dig +short AAAA demo.rwsth.de` und `sudo ss -ltn 'sport = :443'` | keine AAAA-Adresse, Port 443 nur auf `0.0.0.0` (Schritt 2). Nur wer IPv6 wie dort beschrieben eingerichtet hat: von einem Rechner mit IPv6 einmal falsch anmelden; unter `/django-admin/` bei den Anmeldeversuchen (Axes) steht dessen IPv6-Adresse, nicht `172.…` – sonst AAAA-Eintrag wieder entfernen |
| 17 | Externe Prüfung | Server in der Hetzner Cloud Console ausschalten, 10 Minuten warten | E-Mail vom externen Dienst aus Schritt 0 **und** von healthchecks.io |

> Test 13 nur zurück auf eine Version **ohne** neuere Datenbank-Migrationen
> (`wachbuch update` fragt sonst nach); sonst Test 11 mit dem Backup von vor
> dem Update verwenden. Eine Demo-Installation lehnt Versionen unter 0.26.0 ab.

## 8. Laufender Betrieb

| Wann | Was |
| --- | --- |
| automatisch, 5 Minuten | `wachwerk-health` prüft Erreichbarkeit, Zertifikat, alle Dienste, Serverfehler, Backup, Offsite-Kopie, Wiederherstellungsprobe, das letzte automatische Update und den Plattenplatz |
| automatisch, täglich | Sicherheitsupdates des Systems und der Wachwerk-Images, Backup |
| automatisch, sonntags | Wiederherstellungsprobe des neuesten Backups (`wachwerk-restore-test`) |
| monatlich | kurzer Blick in `wachbuch status` |
| vierteljährlich | Test 11 (Wiederherstellen aus der Storage Box) |
| bei neuer Version | `wachbuch update`, CHANGELOG lesen. Nennt er Änderungen an den Host-Skripten (`deploy/hetzner`): `sudo git -C /root/wachwerk-src pull` und `harden-host.sh` (ggf. `offsite-storagebox.sh`) wie in Schritt 3 und 6 erneut starten – `wachbuch update` erneuert sie nicht |

So verhält sich die Überwachung (`/usr/local/bin/wachwerk-health`,
Einstellungen in `/etc/wachwerk/health.env`):

- **Alarm erst bei Bestand:** Ein Fehler geht erst an healthchecks.io, wenn
  er zwei Läufe in Folge (rund 10 Minuten) besteht. Ein Neustart des Servers
  oder ein kurzer Aussetzer löst so keine E-Mail aus (`FAILS_BEFORE_ALERT`).
  `--test` meldet sofort.
- **Selbstheilung:** Ein Dienst, den Docker als „unhealthy“ führt (z. B. ein
  hängender Worker), wird neu gestartet – höchstens dreimal je Stunde, danach
  kommt der Alarm. Die Datenbank startet die Prüfung nie selbst neu.
  `AUTO_RESTART=false` schaltet das ab.
- **Vor der Installation** prüft und meldet sie nichts; der Check bei
  healthchecks.io bleibt bis dahin „new“.
- **Während des nächtlichen Updates** (Sperre `logs/auto-update.lock`)
  ruhen Erreichbarkeit, Zertifikat und Container; besteht die Sperre länger
  als eine Stunde, kommt ein Alarm.
- **Gescheitertes Update:** Endet `wachbuch auto-update` mit Fehler oder
  Rückkehr zur alten Version (Rollback), meldet die Prüfung das, bis ein Lauf
  wieder gelingt. Nach dem Beheben: `sudo /opt/wachbuch/wachbuch auto-update run`.
  Läuft das Update länger als zwei Tage gar nicht, kommt ebenfalls ein Alarm.
- **Gescheiterte Wiederherstellungsprobe:** bleibt gemeldet bis zur nächsten
  gelungenen; neu anstoßen mit `sudo systemctl start wachwerk-restore-test`.

Nützliche Befehle:

```bash
sudo /opt/wachbuch/wachbuch status          # Dienste und Version
sudo /opt/wachbuch/wachbuch logs web        # Protokoll der Anwendung
sudo journalctl -u wachwerk-health -n 50    # letzte Prüfungen
sudo journalctl -u wachwerk-offsite -n 20   # letzte Offsite-Kopien
sudo journalctl -u wachwerk-restore-test    # Wiederherstellungsproben
sudo fail2ban-client status sshd            # gesperrte Adressen
sudo ufw status verbose                     # Firewall
```

## 9. Was die Software für den Internetbetrieb mitbringt

- **Verschlüsselung:** HTTPS mit HSTS (ein Jahr), Cookies nur über HTTPS
  (`Secure`, `HttpOnly`, `SameSite=Lax`).
- **Strenge Browser-Regeln:** Content-Security-Policy ohne `unsafe-inline`,
  `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`, `nosniff`.
- **Anmeldung:**
  - Sperre nach Fehlversuchen (django-axes), Begrenzungen je Anschluss und
    Person.
  - Zwei-Faktor-Anmeldung und Passkeys; mit `--demo` Pflicht für alle echten
    Konten.
- **Getrennte Netze:** Datenbank und Redis liegen in internen
  Docker-Netzen ohne Internet. Nach außen offen ist nur Caddy (80/443); die
  Anwendung selbst lauscht nur auf `127.0.0.1`.
- **Container:** schreibgeschützte Dateisysteme, keine Linux-Capabilities,
  `no-new-privileges`. Datenbankrollen mit minimalen Rechten (die Anwendung
  darf Protokolle nicht löschen).
- **Proxy (Caddy):**
  - verwirft gefälschte `X-Forwarded-*`-Header,
  - begrenzt Anfragen auf 20 MB,
  - schließt langsame Verbindungen (Schutz vor Slowloris),
  - zeigt in HTTPS-Antworten keine Server-Kennung.
- **Demo:**
  - Jeder Besuch hat eine eigene Wache, die beim Abmelden, nach 30 Minuten
    Leerlauf oder spätestens nach 2 Stunden gelöscht wird.
  - Begrenzt auf 100 gleichzeitige Demos und 10 neue je Anschluss und Stunde.
  - Kein E-Mail- und Signal-Versand, keine Einladungen, keine
    Geräte-Kopplung.
- **Prüfungen:** Sicherheitstests als CI-Pflicht, wöchentlich neu gebaute
  Images mit Sicherheitsscan (Trivy).

Was die Software **nicht** ersetzt: einen externen Sicherheitstest vor dem
Echtbetrieb mit echten Daten (docs/ASVS-L2.md, docs/GO-LIVE-CHECKLIST.md).
