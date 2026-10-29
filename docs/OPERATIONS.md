# Betrieb

## Endpunkte

- Anwendung: `http://127.0.0.1:${HTTP_PORT:-8090}/` (öffentliche Projektseite)
- Übersicht (nach Login): `/uebersicht/`
- Healthcheck: `/healthz/` (JSON mit `status` und `version`)
- Datenschutz/Cookies: `/datenschutz/`
- Anmeldung: `/anmelden/` (optional TOTP unter `/anmelden/mfa/` und `/konto/mfa/`)
- Stationsverwaltung: `/einstellungen/`
- Teamfreigaben: `/team/`
- technische Verwaltung: `/django-admin/`

Der Standard-Port ist nicht öffentlich gebunden. `HTTP_BIND_ADDRESS=0.0.0.0`
sollte nur in einem kontrollierten Netz hinter einem Reverse-Proxy verwendet
werden. Für jeden TLS-Betrieb muss `SECURE_COOKIES=true` gesetzt sein; `false`
ist nur für lokalen HTTP-Zugriff über Loopback vorgesehen.

## Standardbefehle

Im Installationsordner (`/opt/wachbuch` bzw. `~/wachbuch`, siehe
[DEPLOYMENT.md](DEPLOYMENT.md)); `docker compose` liest dort `.env` mit
`COMPOSE_FILE`/`COMPOSE_PROFILES`:

```bash
./wachbuch status
./wachbuch logs web
docker compose logs --since 30m web migrate notify-worker feed-worker backup
./wachbuch update
docker compose exec -T web python manage.py apply_retention
curl -fsS http://127.0.0.1:8090/healthz/
```

Die Testsuite läuft nicht im Produktionscontainer (die App-Rolle darf keine
Testdatenbank anlegen), sondern lokal bzw. in der CI.

Healthchecks: `web` prüft `/healthz/` (mit `Host: localhost`, Loopback ist immer
in `ALLOWED_HOSTS`), `notify-worker` das Alter seiner Heartbeat-Datei (< 180 s),
`push-worker` seine Lebenszeichen-Datei. `notify-worker` beendet sich nach zehn
Fehlversuchen in Folge (`NOTIFY_MAX_FAILURES`) mit Fehlercode, damit Docker ihn neu
startet und der Fehler in `wachbuch status` sichtbar wird.

## Benutzer und Rollen

Das erste Konto entsteht ausschließlich im Setup-Assistenten unter `/setup/`
(Einrichtungscode: `./wachbuch setup-code`). Nur als Notfallzugang, wenn kein
Admin-Konto mehr nutzbar ist:

```bash
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py grant_station_admin BENUTZERNAME
```

Weitere persönliche Konten legt der Master-Admin unter `/team/anlegen/` oder per
Einladung an und setzt dort die Rolle. Gemeinschaftskonten sind nicht vorgesehen. Unter **Mehr → Zwei-Faktor
/ Passkeys** können TOTP und Passkeys eingerichtet werden. Mit
`MFA_REQUIRED=true` wird die Einrichtung nach dem Passwort-Login erzwungen.

Passkeys brauchen `WEBAUTHN_RP_ID` (Hostname) und `WEBAUTHN_ORIGIN` (z. B.
`https://wache.example`). Web-Push braucht `WEB_PUSH_ENABLED=true` sowie
VAPID-Schluessel (`VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`).

## Reverse-Proxy

TLS nach **BSI TR-02102-2**: bevorzugt TLS 1.3 mit AEAD (z. B. AES-256-GCM).
Details: [`CRYPTO-BSI.md`](CRYPTO-BSI.md).

Empfohlen ist der mitgelieferte Caddy (Compose-Profil `https`, eingerichtet von
`install.sh --mode lan|domain`). Für einen eigenen Proxy auf dem Host genügt mit
Caddy:

```caddy
wache.example.org {
        reverse_proxy 127.0.0.1:8090
}
```

Ein nginx-Beispiel steht in [DEPLOYMENT.md](DEPLOYMENT.md#eigener-proxy).
Hostname und HTTPS-Origin müssen in `ALLOWED_HOSTS` und
`CSRF_TRUSTED_ORIGINS` stehen. Der Proxy muss `X-Forwarded-Proto` setzen und
`X-Forwarded-For` überschreiben (nicht anhängen), wenn `TRUSTED_PROXY=true` gilt.
Für jeden TLS-Betrieb muss `SECURE_COOKIES=true` gesetzt sein.
Django wertet `SECURE_PROXY_SSL_HEADER` aus und erzwingt sichere Cookies, wenn
`SECURE_COOKIES=true` gesetzt ist.

## Feeds

Der Worker aktualisiert aktivierte Quellen alle 15 Minuten. Ein manueller Lauf:

```bash
docker compose exec -T feed-worker python manage.py sync_feeds
```

Neue Hosts werden zuerst in `FEED_ALLOWED_HOSTS` freigegeben. Das gilt für
RSS-/CSV-Feeds und den optionalen Muellkalender-ICS-Fallback. Quellen können
danach im Django-Admin erstellt, deaktiviert oder korrigiert werden. Fehler und
der letzte erfolgreiche Abruf stehen direkt am `FeedSource`.

Vor dem Upgrade einer 0.2-Installation müssen die Hosts aller bestehenden
Quellen aus dem Django-Admin in `FEED_ALLOWED_HOSTS` übernommen werden. Eine
leere Allowlist deaktiviert Abrufe absichtlich.

## Verkehrslage

Die Verkehrslage (Baustellen, Sperrungen, Bevölkerungswarnungen) auf dem
Wachen-Display ist je Wache unter *Einstellungen* konfigurierbar; Straßen,
Umkreis und Warngebiete auch in der Ersteinrichtung. Es gibt keine festen
Standort- oder Regionswerte:

| Einstellung | Wirkung |
| --- | --- |
| `traffic_enabled` | Schaltet die Leiste auf dem Display ein (Standard aus). |
| `traffic_roads` | Autobahnen, z. B. `A2, A33` (höchstens 6, Format `^[AB]\d{1,3}$`). Abgefragt wird `verkehr.autobahn.de`; die Autobahn GmbH liefert nur Bundesautobahnen, B-Kennungen bleiben dort in der Regel leer. Braucht Koordinaten der Wache. |
| `traffic_radius_km` | Umkreis um die Koordinaten (1–200 km, Standard 25). |
| `latitude`/`longitude` | Koordinaten der Wache; bei aktivierter Wettervorhersage aus der Anschrift ermittelt oder direkt eintragbar. Ohne Koordinaten entfällt die Autobahnquelle (kein Ersatzstandort). |
| `traffic_warning_areas` | Orts- oder Kreisnamen für BBK/NINA-Warnungen (`warnung.bund.de`, höchstens 8). Leer: Ort der Wache; ohne beides werden keine Warnungen abgerufen. Meldungen ohne Gebietsangabe werden nicht angezeigt. |
| `traffic_local_sources` | Ortsspezifische HTML-Auswertung der Gemeinde Steinhagen und des Kreises Gütersloh. Nur für Wachen dort sinnvoll, Standard aus, nur in den Einstellungen wählbar. |

Bestehende Wachen mit eingeschalteter Verkehrslage behalten beim Update
(Migration `0056`) die bisherigen Werte: `A2, A33`, 25 km, Warngebiete
„Gütersloh, Bielefeld, Steinhagen, Kreis Gütersloh“ und kommunale Quellen an.
Der frühere feste Ersatzstandort entfällt; Wachen ohne gespeicherte Koordinaten
müssen sie nachtragen, sonst bleibt die Autobahnquelle leer.

Ergebnisse werden zehn Minuten zwischengespeichert; der Cache-Schlüssel enthält
einen Hash der Konfiguration, Änderungen greifen also sofort. Fällt eine Quelle
aus, bleiben die übrigen sichtbar und die Quelle steht in `failed_sources`.
Alle Abrufe laufen über eine feste HTTPS-Allowlist (`core/traffic.py`,
`ALLOWED_HOSTS`), nur Port 443, ohne Weiterleitungen und mit Größenlimit. Die
kommunalen Quellen werten HTML aus und können bei Layoutänderungen der Seiten
leer werden.

## Push-Outbox

Dringende Übergaben schreiben innerhalb der Handover-Transaktion einen
`PushOutbox`-Eintrag pro aktivem Abo. Der `push-worker`-Service liest die
Tabelle, sendet über `pywebpush` und löscht das Abo bei HTTP 404/410.
Der Gunicorn-Request selbst macht **keinen** externen Netzaufruf.

Die Browser-CSP `connect-src` erlaubt nur `'self'` und die Hosts aus
`PUSH_ALLOWED_ENDPOINT_HOSTS` (Standard: FCM, Mozilla Autopush, Apple, WNS).
Ein Override dieser Variable gilt gemeinsam für das Speichern von
Subscriptions und für die CSP.

Der Container läuft mit dedizierter DB-Rolle `PUSH_DB_USER` (Least Privilege)
und eigenem `PUSH_WORKER_SECRET_KEY`. Erreichbar nur über `worker-db` und
`egress`, kein direkter App-DB-User.

### Retry und Backoff

Bei Netzwerkfehlern oder 5xx-Antworten bleibt der Eintrag `pending` und der
Worker plant den nächsten Versuch mit exponentiellem Backoff:

| Versuch | Wartezeit |
|--------:|----------:|
| 1       | 60 s      |
| 2       | 5 min     |
| 3       | 15 min    |
| 4       | 1 h       |
| 5+      | 6 h       |

Nach `MAX_ATTEMPTS = 10` Versuchen wird der Eintrag auf `discarded` gesetzt
und ein `push.outbox_failed` Audit-Event geschrieben. Die Idempotenz wird
über den HTTP-Header `X-Idempotency-Key` (UUID der Outbox-Zeile) an den
Push-Provider übertragen.

### Aufbewahrung

Abgeschlossene Zeilen (`sent`, `discarded`, `failed`) werden nach 30 Tagen
gelöscht. Aufrufbar als eigenständiger Befehl oder Bestandteil der
täglichen Retention:

```bash
docker compose exec -T web python manage.py cleanup_pushoutbox
docker compose exec -T web python manage.py cleanup_pushoutbox --days 7 --dry-run
```

`apply_retention` ruft `apply_pushoutbox_retention` ebenfalls auf, sodass der
bestehende Retention-Cron-Pfad die Outbox mitraeumt.

## Backup und Restore

### Rollenmodell (R-010, Least-Privilege)

Die Datenbank unterscheidet fünf Rollen mit klar getrennten Aufgaben:

- `rwsth_owner` (entspricht `POSTGRES_USER`): ausschließlich für Init,
  Migration, manuelle Restore-Skripte und die Passwortrotation. Wird im
  laufenden Betrieb von keinem dauerhaften Container benutzt.
- `rwsth_app` (entspricht `APP_DB_USER`): Web- und Migrationscontainer. Volle
  CRUD-Rechte auf das Schema, aber kein `UPDATE`/`DELETE` auf den
  append-only-Tabellen `core_coffeeentry`, `core_auditevent`,
  `core_handoverrevision` und `core_checklistcompletion`.
- `rwsth_feed` (entspricht `FEED_DB_USER`): ausschließlich `FeedSource`-
  Status- und `FeedItem`-CRUD.
- `rwsth_push` (entspricht `PUSH_DB_USER`): `SELECT`/`UPDATE` auf der
  Push-Outbox, `SELECT`/`DELETE` auf Push-Subscriptions sowie ausschließlich
  `INSERT` in das append-only Audit-Log. Der Worker erhält keine allgemeinen
  Schema- oder Fachdatentabellenrechte.
- `rwsth_backup` (entspricht `BACKUP_DB_USER`): ausschließlich `SELECT` plus
  `pg_read_all_data`. Wird vom dauerhaften `backup`-Container für
  `pg_dump` benutzt. Kann weder `INSERT`, `UPDATE` noch `DELETE` auf
  Fach-Tabellen ausführen.

### Tagesbackup

Der `backup`-Container läuft standardmaessig als PostgreSQL-UID/GID 70 und
nutzt die `rwsth_backup`-Rolle. Die Dumps liegen im persistenten Named Volume
`backups-data`. Der kurzlebige `backup-init`-Container setzt vor dem Start
mit ausschließlich `CAP_CHOWN` und `CAP_FOWNER` die Volume-Rechte auf `0700`;
der dauerhafte Backup-Prozess bleibt non-root und hat keine Capabilities.
Abweichende Images können `BACKUP_UID` und `BACKUP_GID` in `.env` anpassen.

`pg_dump` läuft mit `--no-owner --no-acl --format custom`. Der lokale
Ring bleibt im Volume `backups-data` und wird pro Durchlauf um Dumps
älter als `BACKUP_RETENTION_DAYS` ausgedünnt.

Der Abstand der Dumps ist `BACKUP_INTERVAL_SECONDS` (Standard 86400). Fehler
beenden den Dienst nicht: nach `BACKUP_RETRY_SECONDS` (Standard 3600) folgt ein
neuer Versuch. Nach einem Neustart des Containers wird erst gedumpt, wenn der
letzte Dump älter als das Intervall ist; Neustarts lösen also keine Dump-Serie aus.

Sofortiges Backup mit Kopie auf den Host (`./backups/` im Installationsordner):

```bash
./wachbuch backup
# ohne CLI:
docker compose exec -T backup /bin/sh /usr/local/bin/rwsth-backup-loop once
```

Wiederherstellung (fragt nach, legt vorher ein Sicherheits-Backup an, hält
Anwendung und Worker an, ersetzt das Schema `public` in einer Transaktion
vollständig durch den Dump und setzt danach Migrationen und Rollenrechte neu).
Weil das ganze Schema ersetzt wird, klappt das auch mit einem Dump von vor
einem Update, dessen Migrationen neue Tabellen angelegt haben (daran scheitert
`pg_restore --clean`). Scheitert etwas, bleibt die Datenbank unverändert:

```bash
./wachbuch restore backups/rwsth-20261024T120517Z.dump
```

### Aufbewahrung alter Dumps

`BACKUP_RETENTION_DAYS` (Standard `7`) steuert, wie viele Tage alte Dumps
im `backup`-Container behalten werden. Jeder Durchlauf löscht Dateien
(`rwsth-*.dump`, `rwsth-*.dump.gpg`), deren Modifikationszeit älter ist.
Der Wert `0` deaktiviert das Löschen; der lokale Ring wächst dann
unbegrenzt und muss von Hand gepflegt werden. Die Einstellung wirkt nur
auf die lokalen Dumps im Container, nicht auf das Offsite-Ziel. Die Kopien
unter `./backups/` im Installationsordner dünnen `wachbuch update` und das
Auto-Update nach jedem erfolgreichen Update nach demselben Wert aus (`0` = nie).

```bash
# in .env
BACKUP_RETENTION_DAYS=14   # zwei Wochen behalten
BACKUP_RETENTION_DAYS=0    # nie automatisch loeschen
```

### Offsite-Kopie und Verschlüsselung

Der `backup`-Container ist read-only. Das Offsite-Ziel ist deshalb ein
Host-Ordner (z. B. NAS-Mount oder USB-Platte), den Compose als `/offsite`
einbindet; `BACKUP_OFF_TARGET` zeigt auf diesen Pfad im Container. Der Ordner
muss UID/GID 70 (`BACKUP_UID`/`BACKUP_GID`) gehören; `backup-init` versucht das
beim Start zu setzen (bei NFS mit `root_squash` vorher von Hand).

Wenn `BACKUP_ENCRYPT_REMOTE=true` gesetzt ist, wird jeder Dump vor der Kopie
asymmetrisch mit GnuPG für `BACKUP_GPG_RECIPIENT` (Fingerprint oder E-Mail)
verschlüsselt (AES-256). Den **öffentlichen** Schlüssel als `*.asc` in den
Host-Ordner `BACKUP_GPG_KEY_DIR` legen; er wird read-only eingebunden und beim
Start in einen Schlüsselbund im tmpfs (`GNUPGHOME=/tmp/gnupg`) importiert. Fehlt
der Schlüssel, protokolliert der Dienst einen Fehler und überspringt die
Offsite-Kopie – Klartext wird nie ausgelagert, der lokale Dump bleibt erhalten.

```bash
# in .env
BACKUP_OFFSITE_DIR=/srv/wachbuch-offsite
BACKUP_OFF_TARGET=file:///offsite
BACKUP_ENCRYPT_REMOTE=true
BACKUP_GPG_RECIPIENT=ops-backup@example.org
BACKUP_GPG_KEY_DIR=/etc/wachbuch/backup-keys   # enthält ops-backup.asc
```

```bash
sudo install -d -o 70 -g 70 -m 0700 /srv/wachbuch-offsite
./wachbuch start && ./wachbuch backup && ls -l /srv/wachbuch-offsite
```

Die Aufbewahrung im Offsite-Ordner regelt `BACKUP_RETENTION_DAYS` nicht; dort
gelten die Regeln des Zielsystems.

### Was gehört zur Sicherung

- die Dumps (Volume `backups-data`, Kopien in `./backups/` bzw. `/offsite`),
- die `.env` (alle Schlüssel; ohne `CRYPTO_MASTER_KEY` und `DJANGO_SECRET_KEY`
  sind verschlüsselte Felder nicht lesbar),
- bei `--mode lan` das Volume `caddy-data` (interne CA, sonst müssen Geräte eine
  neue CA importieren).

### Restore-Test

Der Restore-Test benötigt Owner-Rechte (`createdb`/`dropdb`) und wird daher
über den nur manuell gestarteten `restore-test`-Service ausgeführt. Die
Owner-Credentials werden nur diesem Einmal-Container übergeben; der dauerhafte
`backup`-Container behält ausschließlich die Read-only-Backup-Rolle.

```bash
docker compose run --rm restore-test
```

Der Restore-Test erstellt kurzzeitig `rwsth_restore_test`, spielt den
neuesten Dump ein, prüft Schlüsseltabellen und entfernt die Testdatenbank
wieder.

## Aufbewahrung (Retention)

- `RETENTION_FEED_DAYS` (Standard `90`): entfernt Feed-Einträge, deren
  `last_seen_at` älter ist. `0` deaktiviert die Feed-Löschung.
- `RETENTION_AUDIT_DAYS` (Standard `0`): Audit-Purge bleibt absichtlich aus, bis
  organisatorische Fristen freigegeben sind. Nur mit Owner-Rechten und klarer
  Freigabe setzen.
- Kommando: `docker compose exec -T web python manage.py apply_retention`
  (z. B. täglich per Host-Cron).

## Datenbank-Passwortrotation

App-, Feed-, Backup- und Push-Rollenpasswörter rotieren (Owner-Passwort bleibt
unangetastet):

```bash
./scripts/rotate-db-passwords.sh                                  # im Repository-Checkout
WACHBUCH_DIR=/opt/wachbuch sh rotate-db-passwords.sh              # bei install.sh-Installationen
```

Das Skript setzt neue Zufallswerte in PostgreSQL und `.env` und erstellt `web`,
`notify-worker`, `feed-worker`, `backup` und `push-worker` neu. Anschließend
`./wachbuch status` prüfen. Das Owner-Passwort (`POSTGRES_PASSWORD`) nur mit
Dump/Restore und Neuinitialisierung rotieren.

Ältere Volumes ohne Rolle `rwsth_push` ergänzt `grant_database_access` beim nächsten
Start (`migrate`) automatisch. Wurde die Rolle früher mit dem alten Standardpasswort
`disabled` angelegt und `.env` enthält jetzt ein anderes `PUSH_DB_PASSWORD`, meldet
der `push-worker` Anmeldefehler; die Rotation oben gleicht Datenbank und `.env` an.

## Datenbank-Tuning

`config/postgresql.conf` (im db-Image) ist für 1–2 GB RAM ausgelegt:
`shared_buffers=128MB`, `max_connections=50`, `maintenance_work_mem=64MB`, dazu
`shm_size: 256mb` für den Container. Auf größeren Servern in `.env` anheben, ohne
eigene Datei:

```dotenv
POSTGRES_SHARED_BUFFERS=1GB          # ca. 25 % des RAM
POSTGRES_EFFECTIVE_CACHE_SIZE=3GB    # ca. 50-75 % des RAM
POSTGRES_WORK_MEM=8MB
POSTGRES_MAINTENANCE_WORK_MEM=256MB
POSTGRES_MAX_CONNECTIONS=100         # > GUNICORN_WORKERS x GUNICORN_THREADS + 10
POSTGRES_SHM_SIZE=1gb                # mindestens shared_buffers
```

Danach `./wachbuch start` (der db-Container wird neu erstellt) und mit
`docker compose exec db psql -U rwsth_owner -d rwsth -c 'SHOW shared_buffers'`
prüfen. Für weitere Parameter eine eigene Konfigurationsdatei per
`compose.override.yml` einhängen:

```yaml
services:
  db:
    volumes:
      - ./postgresql.conf:/etc/postgresql/postgresql.conf:ro
```

Werte aus `.env` (`-c` auf der Kommandozeile) haben Vorrang vor der Datei.

## Krypto-Schlüsselrotation (TOTP-Secrets)

Die TOTP-Geheimnisse liegen AES-256-GCM-verschluesselt in der Datenbank. Der
Master-Key stammt Vorgabe aus `HKDF(SECRET_KEY)`. Da eine `SECRET_KEY`-Rotation
damit alle Umschläge unlesbar machen würde, kann der Master-Key unabhängig
von `SECRET_KEY` konfiguriert und rotiert werden:

- `CRYPTO_MASTER_KEY` – 32 Byte hex-codiert (z. B. `openssl rand -hex 32`).
  Wenn gesetzt, ersetzt er die `HKDF(SECRET_KEY)`-Ableitung. Wenn nicht gesetzt,
  gilt das alte Verfahren (Rueckwaertskompatibilitaet).
- `CRYPTO_PREVIOUS_MASTER_KEY` – optionaler Fallback-Schlüssel, der während
  eines Rotationsfensters **zusätzlich** zum Entschlüsseln akzeptiert wird.
  Er erlaubt das Betreiben der App mit dem neuen Key, während noch alte
  Umschläge in der Datenbank stehen.

### Rotationsablauf

```bash
# 0. Backup erstellen und App weiterhin mit dem ALTEN Key betreiben.

# 1. Den aktuell aktiven Master-Key als Hex anzeigen (fuer den Fallback):
docker compose exec -T web python manage.py rotate_crypto_key --show-current-key
#   -> <alter-key-hex>

# 2. Neuen Key erzeugen:
NEW_KEY=$(openssl rand -hex 32)

# 3. In .env eintragen (app danach neu starten):
#    CRYPTO_MASTER_KEY=$NEW_KEY
#    CRYPTO_PREVIOUS_MASTER_KEY=<alter-key-hex aus Schritt 1>

# 4. App neu starten, dann Re-Verschluesselung testen und ausfuehren:
docker compose up -d web
docker compose exec -T web python manage.py rotate_crypto_key --dry-run
docker compose exec -T web python manage.py rotate_crypto_key

# 5. Nach erfolgreicher Rotation CRYPTO_PREVIOUS_MASTER_KEY aus .env entfernen
#    und erneut neu starten. Healthcheck und TOTP-Anmeldung verifizieren.
```

`--dry-run` ändert nichts, zählt aber wie viele Datensätze neu
verschlüsselt würden. Während des Rotationsfensters (Schritt 3–4) kann die
App sowohl alte als auch neue Umschläge lesen, sodass TOTP-Anmeldungen nicht
ausfallen. Erst nach Entfernen von `CRYPTO_PREVIOUS_MASTER_KEY` (Schritt 5)
akzeptiert das System ausschließlich den neuen Key.

## Versionierung und Updates

Canonical Version steht in `core/version.py` und kann mit `APP_VERSION` in `.env`
überschrieben werden. Die Version erscheint im Footer und unter `/healthz/`.
`WACHBUCH_VERSION` in `.env` wählt die Image-Version
(`ghcr.io/katschko-it/rettungswache-wachbuch[-backup|-db]:X.Y.Z`).

### Update einer Installation

```bash
./wachbuch update            # neueste Veröffentlichung
./wachbuch update 0.25.0     # bestimmte Version
```

`update` erstellt zuerst ein Backup (Abbruch, wenn es scheitert), lädt
`compose.yml`, Caddyfile und `wachbuch` passend zur Version, setzt
`WACHBUCH_VERSION`, zieht die Images und startet mit `up -d --wait` neu.
Migrationen laufen dabei automatisch im Dienst `migrate`. Lassen sich die
Images nicht laden, gehen Dateien und Version zurück und der laufende Stand
bleibt; startet die neue Fassung nicht, folgt derselbe Rollback wie beim
Auto-Update (Schritt 5 unten). Nach einem erfolgreichen Update entfernt
`update` ältere Images des Wachbuchs (nur die mit dem Label
`org.opencontainers.image.source` dieses Repositorys) und startet Caddy neu,
wenn sich das Caddyfile geändert hat (Caddy liest es nur beim Start).

Die öffentliche Demo (`DEMO_SANDBOX=true`) nimmt nur feste Versionen ab
0.26.0 an; ältere Versionen kennen keine Demo-Wache je Besuch.

### Automatische Updates

```bash
./wachbuch auto-update an                     # sicherheit, täglich 03:30
./wachbuch auto-update an alle --zeit 04:15   # auch neue Versionen (gleiche Hauptversion)
./wachbuch auto-update status                 # Einstellung und letzte Läufe
./wachbuch auto-update aus
```

| Modus | Was passiert |
| --- | --- |
| `sicherheit` | bleibt bei `WACHBUCH_VERSION`, lädt die wöchentlich neu gebauten Images (Debian-/Alpine-Sicherheitsupdates) |
| `alle` | wie `sicherheit`, zusätzlich neue Versionen derselben Hauptversion (z. B. 0.25 → 0.26, nie 0 → 1) |

Ablauf jedes Laufs (Protokoll: `logs/auto-update.log`):

1. Sperre gegen parallele Läufe; Entwicklungsinstallationen (`--build`,
   `WACHBUCH_SOURCE`) werden übersprungen.
2. Laufende Images unter `…-wb-rollback` sichern, dann `pull`.
3. Nichts Neues und alle Container auf dem aktuellen Stand → Ende ohne Neustart.
4. Sonst Backup (Abbruch ohne Änderung, wenn es scheitert), dann `up --wait`.
5. Startet die neue Fassung nicht, werden Images, `compose.yml`, Caddyfile,
   `wachbuch` und `WACHBUCH_VERSION` zurückgesetzt und die vorherige Fassung
   gestartet. Django schreibt jede Migration einzeln fest: Hat die neue
   Version schon Migrationen eingespielt (Zahl der Zeilen in
   `django_migrations` vor und nach dem Start), werden vorher Anwendung und
   Worker angehalten und die Datenbank aus dem Backup von Schritt 4
   zurückgesetzt – alter Code läuft nie auf einem neueren Datenbankstand.
   Änderungen zwischen Backup und Rollback (nachts meist keine) gehen dabei
   verloren. Gelingt das Zurücksetzen nicht, bleibt die neue Version
   eingestellt und wird erneut gestartet; das Protokoll nennt die nächsten
   Schritte.
6. Nach Erfolg: Caddy neu starten, falls sich das Caddyfile geändert hat
   (auch nach einem Update mit einer älteren CLI), ältere eigene Images und alte
   Dumps unter `./backups/` entfernen.

Zeitplan: als root mit systemd ein Timer `wachbuch-auto-update-<id>.timer`
(`Persistent=true` holt verpasste Läufe nach), sonst ein crontab-Eintrag des
aufrufenden Nutzers. Unter macOS braucht cron Zugriff auf Docker
(Docker Desktop/Colima müssen laufen).

Neu gebaut werden die Images vom Workflow `refresh-images.yml` (montags
02:17 UTC): aktuelles Release ohne Cache, Sicherheitsscan (HIGH/CRITICAL mit
verfügbarem Fix) und Starttest als Sperre, erst dann Veröffentlichung für
amd64 und arm64. Scheitert etwas, bleiben die bisherigen Images und es entsteht
ein Issue.

### Eigener Image-Spiegel

Ohne Internetzugang der Wache: Images in eine Registry im Wachen-Netz spiegeln
und in `.env` `WACHBUCH_REGISTRY=registry.wache.lan:5000/katschko-it` setzen.
`update` und `auto-update` laden dann von dort.

### Release vorbereiten

1. SemVer in `core/version.py` setzen und `CHANGELOG.md` aktualisieren.
2. Migrationshinweise und Breaking Changes dokumentieren.
3. Backup und Restore-Test ausführen.
4. Abhängigkeiten und Image-Digests kontrolliert aktualisieren.
5. Lokal bauen: `docker compose -f docker-compose.yml -f compose.build.yml build --no-cache`.
6. Images auf HIGH/CRITICAL-Schwachstellen scannen.
7. Tests ausführen und den Stack mit `up -d --wait` starten.
8. Healthcheck inkl. Versionsfeld, Anmeldung, Rollen, Tagesaufgaben und optionale
   Feeds prüfen.
9. Tag `vX.Y.Z` pushen: `publish-image.yml` baut App-, Backup- und db-Image für
   amd64/arm64 und taggt `X.Y.Z`, `X.Y` und `latest`.
10. Service-Worker-Caches leeren bzw. einmal ab-/anmelden, falls Shell-Assets
    geändert wurden.

### Rollback

1. Vorherige Version wieder aktivieren: `./wachbuch update <alte Version>`
   (fragt nach, weil die Datenbank die neueren Migrationen behält), danach
   `./wachbuch restore <Backup vor dem Update>`. Diese Reihenfolge ist wichtig:
   `restore` lässt danach `migrate` der gerade eingestellten Version laufen;
   mit der neuen Version würden die Migrationen sofort wieder eingespielt.
2. Bei scheiternder Migration nur dokumentierte Reverse-Migrationen oder
   Dump-Restore nutzen.
3. Keine Tabellen manuell „reparieren“.
4. Incident, Root Cause und erneuten Release-Versuch dokumentieren.

Bei Störungen zuerst Logs und letzten Dump sichern, dann die Ursache
reproduzierbar über Anwendung oder Migration beheben.

Siehe auch [`COMPLIANCE.md`](COMPLIANCE.md).

## Korrelations-IDs und Fehlerkanone (R-014)

Jeder Request trägt eine Korrelations-ID, die Antworten, JSON-Fehler und
Logeinträge miteinander verknüpft. Sie ist die wichtigste Information für
den Support, weil personenbezogene Daten bewusst nicht geloggt werden.

* Eingehender Header `X-Correlation-ID` wird übernommen, wenn er dem Muster
  `[A-Za-z0-9_-]{1,128}` entspricht. Andernfalls erzeugt der Server eine
  frische UUID4 (hex, 32 Zeichen).
* Die ID wird in jeder Antwort als `X-Correlation-ID` mitgesendet und auf
  `request.correlation_id` abgelegt.
* Logs (Logger `wachbuch.requests` und `wachbuch.errors`) erhalten die ID
  als strukturiertes Feld `extra={"correlation_id": ...}`. Request-Bodies,
  Formularfelder und Auth-Header werden nie geloggt.
* Fehlerseiten (HTML und JSON) zeigen die Korrelations-ID für den
  Support-Vorgang an.

### JSON-Fehlerstruktur

Alle JSON-Fehlerantworten folgen demselben Schema:

```json
{
  "ok": false,
  "error": {
    "code": "validation_error",
    "message": "Eingaben sind ungueltig.",
    "correlation_id": "8b4f1e0b..."
  },
  "fields": {"title": ["Pflichtfeld."]}
}
```

Das `fields`-Objekt ist optional und enthält Formularfehler bei
`validation_error`.

### Eindeutige Fehler-Codes

| Code | HTTP | Bedeutung |
|------|------|-----------|
| `validation_error` | 400 | Eingaben oder Formular ungueltig (auch 422 bei API). |
| `auth_required` | 401 | Anmeldung oder API-Token fehlt/ungueltig. |
| `forbidden` | 403 | Rolle oder Station erlaubt den Zugriff nicht. |
| `not_found` | 404 | Objekt, Pfad oder Modul nicht vorhanden. |
| `rate_limit` | 429 | Zu viele Anfragen (Axes, R-011). |
| `server_error` | 500 | Unerwarteter interner Fehler. |

Stabile Codes gehören zum öffentlichen API-Versprechen. Änderungen
erfordern ein neues Mapping in `core.errors.ERROR_CODES`.

### Verhalten nach Modus

* `DEBUG=true`: Django zeigt die Standard-Traceback-Seiten. Für den
  Pilotbetrieb zulässig, für Produktion aus.
* `DEBUG=false`: Eigene Templates (`templates/errors/400-500.html`) und
  kanonische JSON-Antworten werden ausgeliefert. 500-Fehler loggen den
  vollständigen Stacktrace intern, die Antwort enthält nur die
  Korrelations-ID.
