# Bereitstellung – Rettungswache-Wachbuch

*Stand: Oktober 2026*

## Inhalt

1. [Wege im Überblick](#wege-im-überblick)
2. [Voraussetzungen](#voraussetzungen)
3. [Installation mit install.sh](#installation-mit-installsh)
4. [Ersteinrichtung](#ersteinrichtung)
5. [Betrieb mit wachbuch](#betrieb-mit-wachbuch)
6. [Manuelle Installation mit Docker Compose](#manuelle-installation-mit-docker-compose)
7. [Aus dem Quellcode bauen](#aus-dem-quellcode-bauen)
8. [Reverse-Proxy und TLS](#reverse-proxy-und-tls)
9. [Konfiguration](#konfiguration)
10. [Sicherheitshärtung](#sicherheitshärtung)

## Wege im Überblick

| Weg | Für wen | Images |
| --- | --- | --- |
| `install.sh` (empfohlen) | jede Wache, Linux oder macOS | vorgefertigt aus `ghcr.io` |
| manuelle Compose-Installation | Betreiber mit eigener Automatisierung | vorgefertigt aus `ghcr.io` |
| aus dem Quellcode (`compose.build.yml`) | Entwicklung, eigene Änderungen | lokal gebaut |
| Raspberry Pi mit WLAN und Touch-Terminal | Wache ohne vorhandene IT | lokal gebaut, siehe [PI-WACHENTERMINAL.md](PI-WACHENTERMINAL.md) |

Alle Wege nutzen dieselbe `docker-compose.yml`. Für Endnutzer ist kein Git-Checkout
nötig: Rollen-Init und PostgreSQL-Konfiguration stecken im db-Image
(`ghcr.io/katschko-it/rettungswache-wachbuch-db`), nicht in Bind-Mounts.

## Voraussetzungen

- Linux (Debian, Ubuntu, Raspberry Pi OS 64-bit u. a.) oder macOS
- Docker Engine bzw. Docker Desktop, OrbStack oder Colima, mit **Compose v2 ab 2.20**
- 64-Bit-System: amd64 oder arm64 (32-Bit-Raspberry-Pi-OS wird nicht unterstützt)
- mindestens 1 GB RAM für Docker (empfohlen 2 GB), rund 3 GB freier Speicher
- freier Port 8090 (Betriebsart `local`) bzw. 80 und 443 (`lan`, `domain`)
- für `domain`: DNS-Eintrag auf den Server und Ports 80/443 aus dem Internet erreichbar

## Installation mit install.sh

```bash
curl -fsSL https://raw.githubusercontent.com/Katschko-IT/Rettungswache-Wachbuch/main/install.sh | sh
```

oder erst herunterladen, lesen und dann ausführen:

```bash
curl -fsSLO https://raw.githubusercontent.com/Katschko-IT/Rettungswache-Wachbuch/main/install.sh
sh install.sh
```

Auf Linux liegt die Installation unter `/opt/wachbuch`; dafür `sudo sh install.sh`
oder `--dir "$HOME/wachbuch"` verwenden. Auf macOS ist der Standard `~/wachbuch`
(Docker Desktop und Colima geben nur das Benutzerverzeichnis für Bind-Mounts frei).

Ablauf:

1. **Vorprüfung**: Docker erreichbar, Compose-Version, Architektur, RAM,
   Speicherplatz, freie Ports.
2. **Dateien**: `compose.yml`, `deploy/caddy/Caddyfile` und die Verwaltung
   `wachbuch` für die neueste Veröffentlichung (oder `--version`).
3. **`.env`**: wird nur angelegt, wenn sie fehlt; sonst werden fehlende Schlüssel
   ergänzt (Kopie `.env.bak`). Alle Geheimnisse sind unabhängige Zufallswerte
   (`openssl rand -hex 32`), darunter `CRYPTO_MASTER_KEY` und `RATELIMIT_KEY_SALT`.
   Der Einrichtungscode hat 24 Zeichen in Vierergruppen. Rechte `600`.
4. **Betriebsart** bestimmt Adresse, Cookies, Proxy und Passkeys (siehe unten).
5. **Start**: `docker compose pull` und `up -d --wait`; der Installer wartet, bis
   alle Dienste gesund sind und `/healthz/` antwortet.
6. **Ausgabe**: Adresse, Einrichtungscode, Hinweis zur Sicherung der `.env`.

Ein erneuter Lauf ist gefahrlos: Geheimnisse und von Hand angepasste Werte bleiben
erhalten. Nur wenn Betriebsart, Adresse oder Port per Option geändert werden, setzt
der Installer die davon abgeleiteten Werte neu.

### Betriebsarten

| | `local` | `lan` | `domain` |
| --- | --- | --- | --- |
| Adresse | `http://localhost:8090` | `https://<Name oder IP>` | `https://<Domain>` |
| TLS | keins (nur Loopback) | Caddy, eigene CA (`tls internal`) | Caddy, Let's Encrypt |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Name + Loopback | Domain + Loopback |
| `SECURE_COOKIES` / `TRUSTED_PROXY` | `false` / `false` | `true` / `true` | `true` / `true` |
| Passkeys (`WEBAUTHN_*`) | `localhost` | aus (Zertifikat nicht vertraut) | Domain |
| `COMPOSE_PROFILES` | – | `https` | `https` |

Im LAN-Modus zeigen Geräte eine Zertifikatswarnung, bis die Caddy-CA importiert ist:

```bash
cd /opt/wachbuch
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt wachbuch-ca.crt
```

### Optionen

| Option | Bedeutung |
| --- | --- |
| `--dir PFAD` | Zielordner |
| `--name NAME` | Name der Wache (Standardwache vor dem Assistenten) |
| `--mode local\|lan\|domain` | Betriebsart |
| `--domain NAME` | Hostname, Domain oder IP-Adresse (`lan`, `domain`) |
| `--email ADRESSE` | Kontakt für Let's Encrypt (`domain`) |
| `--port PORT` | lokaler HTTP-Port (Standard 8090) |
| `--https-port` / `--http-port` | Ports des Proxys (Standard 443/80) |
| `--version X.Y.Z` | bestimmte Version statt der neuesten |
| `--source PFAD` / `--base-url URL` | andere Quelle für die Dateien (lokaler Checkout bzw. Spiegel) |
| `--build` | Images lokal aus `--source` bauen |
| `--project NAME` | eigener Compose-Projektname |
| `--auto-update sicherheit\|alle\|aus` | nächtliche Updates (siehe OPERATIONS.md) |
| `--demo` | öffentliche Demo (docs/DEMO.md); braucht Version 0.26.0 oder neuer, ohne ermittelbare Version bricht der Installer ab |
| `--no-start` | nur Dateien und `.env` anlegen |
| `-y`, `--yes` | ohne Rückfragen |

Alle Optionen gibt es auch als Umgebungsvariablen (`WACHBUCH_DIR`, `WACHBUCH_MODE`,
`WACHBUCH_DOMAIN`, …), siehe `sh install.sh --help`.

## Ersteinrichtung

Der **Setup-Assistent ist der einzige reguläre Weg** zum ersten Konto:

1. `https://<Adresse>/setup/` öffnen (der Installer zeigt die Adresse).
2. Einrichtungscode eingeben (`wachbuch setup-code` zeigt ihn erneut).
3. Wache, Anschrift, Zeitzone, erstes Admin-Konto, Rollen und Module festlegen.

Mit dem Abschluss ist der Assistent gesperrt (`/setup/` antwortet mit 404), auch
wenn `SETUP_BOOTSTRAP_TOKEN` in `.env` stehen bleibt; der Code muss nicht von
Hand entfernt werden. Er wirkt erst wieder bei einer leeren Datenbank.

Weitere Konten legt der Master-Admin unter `/team/anlegen/` oder per Einladung an.

Notfallzugang (nur wenn kein Admin-Konto mehr nutzbar ist):

```bash
cd /opt/wachbuch
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py grant_station_admin BENUTZERNAME
```

## Betrieb mit wachbuch

| Befehl | Wirkung |
| --- | --- |
| `wachbuch status` | Dienste, Gesundheit, Version, Adresse |
| `wachbuch logs [dienst]` | Logs, z. B. `web`, `notify-worker`, `backup`, `caddy` |
| `wachbuch backup` | sofortiger Dump, Kopie nach `./backups/` |
| `wachbuch restore DATEI` | Wiederherstellung mit Rückfrage; vorher Sicherheits-Backup, Einspielen in einer Transaktion, danach Migrationen und Rechte |
| `wachbuch update [X.Y.Z]` | neue `compose.yml`/Caddyfile/`wachbuch`, `pull`, dann Anwendung anhalten, Backup, `up --wait`; startet die neue Fassung nicht, Rollback wie beim Auto-Update |
| `wachbuch auto-update an [sicherheit\|alle] [--zeit HH:MM]` / `aus` / `status` | nächtliche Updates mit Backup und Rollback (siehe OPERATIONS.md) |
| `wachbuch setup-code` | Einrichtungscode anzeigen |
| `wachbuch stop` / `start` | anhalten / starten |
| `wachbuch uninstall [--purge]` | Container entfernen; mit `--purge` auch alle Volumes |

`DATEI` bei `restore` ist ein Pfad auf dem Rechner (z. B. aus `./backups/`) oder der
Name eines Dumps im Backup-Volume. Backups, Offsite-Kopie und Verschlüsselung:
[OPERATIONS.md](OPERATIONS.md#backup-und-restore).

## Manuelle Installation mit Docker Compose

Ohne Installer, z. B. für eigene Automatisierung:

```bash
VERSION=X.Y.Z   # neueste Veröffentlichung, siehe GitHub-Releases
mkdir -p /opt/wachbuch/deploy/caddy && cd /opt/wachbuch
BASE="https://raw.githubusercontent.com/Katschko-IT/Rettungswache-Wachbuch/v$VERSION"
curl -fsSL -o compose.yml "$BASE/docker-compose.yml"
curl -fsSL -o .env "$BASE/.env.example"
curl -fsSL -o deploy/caddy/Caddyfile "$BASE/deploy/caddy/Caddyfile"   # nur für Profil https
chmod 600 .env
echo "WACHBUCH_VERSION=$VERSION" >> .env
```

In `.env` jeden `replace-…`-Platzhalter durch einen eigenen Wert aus
`openssl rand -hex 32` ersetzen sowie `CRYPTO_MASTER_KEY` und
`SETUP_BOOTSTRAP_TOKEN` setzen. Compose-Datei und Images sollten aus derselben
Version stammen.
Dann:

```bash
docker compose up -d --wait
```

Migrationen, Bootstrap und Datenbankrechte erledigt der Dienst `migrate`
automatisch vor dem Start von `web`; ein manuelles `manage.py migrate` ist nicht
nötig. Die Dumps liegen im Named Volume `backups-data`; es gibt keinen
`./backups`-Ordner, dessen Besitzer man setzen müsste (`backup-init` setzt die
Rechte im Volume).

## Aus dem Quellcode bauen

```bash
git clone https://github.com/Katschko-IT/Rettungswache-Wachbuch.git
cd Rettungswache-Wachbuch
sh install.sh --source . --build --mode local --dir "$HOME/wachbuch-dev"
```

oder direkt im Checkout (mit eigener `.env` aus `.env.example`):

```bash
docker compose -f docker-compose.yml -f compose.build.yml up -d --build --wait
```

`compose.build.yml` baut `rettungswache-wachbuch:local`, `-backup:local` und
`-db:local` (`Dockerfile`, `Dockerfile.backup` mit den Zielen `backup` und `db`).

Veröffentlichte Images entstehen beim Git-Tag `vX.Y.Z` über
`.github/workflows/publish-image.yml` für linux/amd64 und linux/arm64 mit den Tags
`X.Y.Z`, `X.Y` und `latest`.

## Reverse-Proxy und TLS

### Mitgelieferter Caddy (empfohlen)

`install.sh --mode lan` bzw. `--mode domain` aktiviert das Compose-Profil `https`.
Caddy (`deploy/caddy/Caddyfile`) terminiert TLS auf 443, leitet 80 auf HTTPS um und
spricht `web:8000` im internen Netz an. Werte in `.env`:

```dotenv
COMPOSE_PROFILES=https
WACHBUCH_HOSTNAME=wache.example.org
CADDY_TLS=ops@example.org        # oder: internal
HTTPS_PORT=443
HTTP_REDIRECT_PORT=80
```

Caddy verwirft von Clients gesendete `X-Forwarded-*`-Header und setzt sie selbst;
deshalb ist `TRUSTED_PROXY=true` hier sicher. Zertifikate und die interne CA liegen
im Volume `caddy-data`.

### Eigener Proxy

Der Web-Port bindet nur an `127.0.0.1:${HTTP_PORT:-8090}`. Ein eigener Proxy auf
demselben Host leitet dorthin weiter, **überschreibt** `X-Forwarded-For` mit der
Client-Adresse (das Wachbuch wertet bei `TRUSTED_PROXY=true` den ersten Eintrag aus)
und setzt `X-Forwarded-Proto: https`. Statische Dateien liefert die Anwendung selbst
aus (WhiteNoise); ein `alias` auf einen Host-Pfad ist weder nötig noch möglich, weil
sie nur im Image liegen.

Caddy auf dem Host:

```caddy
wache.example.org {
	reverse_proxy 127.0.0.1:8090
}
```

nginx (Datei in `/etc/nginx/conf.d/`, deren Inhalt im `http`-Kontext steht):

```nginx
# limit_req_zone ist nur im http-Kontext erlaubt, nicht im server-Block.
limit_req_zone $binary_remote_addr zone=wachbuch:10m rate=10r/s;

server {
    listen 80;
    server_name wache.example.org;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    http2 on;
    server_name wache.example.org;

    ssl_certificate     /etc/letsencrypt/live/wache.example.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/wache.example.org/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    client_max_body_size 12m;

    location / {
        limit_req zone=wachbuch burst=40 nodelay;
        proxy_pass http://127.0.0.1:8090;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 75s;
    }
}
```

Sicherheitsheader (CSP, HSTS, `X-Frame-Options` usw.) setzt die Anwendung selbst;
der Proxy soll sie nicht doppelt oder abweichend setzen. Das Live-Display
(`/display/stream/`) sendet `X-Accel-Buffering: no`, nginx puffert es deshalb nicht.
TLS-Vorgaben: [CRYPTO-BSI.md](CRYPTO-BSI.md).

In `.env` passend:

```dotenv
SECURE_COOKIES=true
TRUSTED_PROXY=true
ALLOWED_HOSTS=wache.example.org,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://wache.example.org
SITE_URL=https://wache.example.org
WEBAUTHN_RP_ID=wache.example.org
WEBAUTHN_ORIGIN=https://wache.example.org
```

`localhost` und `127.0.0.1` ergänzt die Anwendung ohnehin, damit der
Container-Healthcheck nie an `ALLOWED_HOSTS` scheitert.

## Konfiguration

Alle Werte stehen kommentiert in [`.env.example`](../.env.example); Betriebsdetails
in [OPERATIONS.md](OPERATIONS.md). Häufig angepasst:

| Variable | Standard | Wirkung |
| --- | --- | --- |
| `WACHBUCH_VERSION` | `latest` | Image-Version (`install.sh`/`wachbuch update` setzen sie) |
| `WACHBUCH_REGISTRY` | `ghcr.io/katschko-it` | Herkunft der Images, z. B. ein Spiegel im Wachen-Netz |
| `WACHBUCH_AUTO_UPDATE` / `_TIME` | `aus` / `03:30` | nächtliche Updates (`wachbuch auto-update` setzt sie) |
| `HTTP_BIND_ADDRESS` / `HTTP_PORT` | `127.0.0.1` / `8090` | lokaler Web-Port |
| `GUNICORN_WORKERS` / `_THREADS` / `_TIMEOUT` | `2` / `4` / `60` | Gunicorn im `web`-Container |
| `POSTGRES_SHARED_BUFFERS` u. a. | `128MB` … | PostgreSQL-Speicher, siehe OPERATIONS.md |
| `BACKUP_RETENTION_DAYS` | `7` | lokale Aufbewahrung der Dumps |
| `BACKUP_OFFSITE_DIR` / `BACKUP_OFF_TARGET` | leer | Offsite-Kopie (Host-Ordner als `/offsite`) |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | leer, 587 | SMTP für E-Mails (Kaffeekassen-Erinnerung mit GiroCode); 587 = STARTTLS, 465 = SSL; leer = keine E-Mails |
| `SIGNAL_API_URL` / `SIGNAL_NUMBER` | leer | Signal-Benachrichtigungen (Profil `signal`, `docs/SIGNAL.md`) |
| `MFA_REQUIRED` | `false` | Zweitfaktor erzwingen (alternativ im Assistenten bzw. unter Einstellungen → Impressum & Datenschutz) |
| `FEED_ALLOWED_HOSTS` | leer | erlaubte HTTPS-Feedquellen |

## Sicherheitshärtung

- [ ] `.env` offline gesichert, Rechte `600`, nicht im Git
- [ ] TLS aktiv (`lan`/`domain` oder eigener Proxy), `SECURE_COOKIES=true`
- [ ] `DJANGO_DEBUG=false`, `DEMO_MODE=false`
- [ ] Einrichtungscode nach der Ersteinrichtung aus `.env` entfernt
- [ ] Zwei-Faktor-Pflicht aktiv (`MFA_REQUIRED=true` oder Häkchen im Assistenten)
- [ ] Impressum und Datenschutz unter Einstellungen → Impressum & Datenschutz vollständig und rechtlich geprüft (bei öffentlicher Domain Pflicht)
- [ ] Firewall: nur 80/443 (bzw. nichts bei `local`); Port 8090 bleibt auf Loopback
- [ ] Backups geprüft: `wachbuch backup`, `docker compose run --rm restore-test`,
      Offsite-Kopie eingerichtet
- [ ] Updates eingeplant: `wachbuch auto-update an` (oder regelmäßig `wachbuch update`), Host-Updates (`apt upgrade`)
- [ ] Zugriff von außen nur über VPN oder bewusst über `domain`

## Weiterführende Dokumentation

- [Betrieb](OPERATIONS.md) – Backup, Restore, Rotation, Updates
- [Architektur](ARCHITECTURE.md) – Vertrauensgrenzen und Datenfluss
- [Sicherheit & Datenschutz](SECURITY-PRIVACY.md)
- [Raspberry Pi als Wachen-Server](PI-WACHENTERMINAL.md)
- [Go-Live-Checkliste](GO-LIVE-CHECKLIST.md)
