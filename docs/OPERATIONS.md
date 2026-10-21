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

```bash
docker compose ps
docker compose logs --since 30m web migrate feed-worker backup
docker compose up -d --build
docker compose exec -T web python manage.py test --settings=config.test_settings
docker compose exec -T web python manage.py apply_retention
curl -fsS http://127.0.0.1:8090/healthz/
```

## Benutzer und Rollen

Lokaler Erstadmin:

```bash
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py grant_station_admin BENUTZERNAME
```

Weitere persönliche Konten werden unter `/django-admin/auth/user/` angelegt.
Stationsadministratoren geben sie anschließend unter `/team/` frei und setzen
die Rolle. Gemeinschaftskonten sind nicht vorgesehen. Unter **Mehr → Zwei-Faktor
/ Passkeys** können TOTP und Passkeys eingerichtet werden. Mit
`MFA_REQUIRED=true` wird die Einrichtung nach dem Passwort-Login erzwungen.

Passkeys brauchen `WEBAUTHN_RP_ID` (Hostname) und `WEBAUTHN_ORIGIN` (z. B.
`https://wache.example`). Web-Push braucht `WEB_PUSH_ENABLED=true` sowie
VAPID-Schluessel (`VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`).

## Reverse-Proxy

TLS nach **BSI TR-02102-2**: bevorzugt TLS 1.3 mit AEAD (z. B. AES-256-GCM).
Details: [`CRYPTO-BSI.md`](CRYPTO-BSI.md).

Beispiel für Caddy vor dem Loopback-Port:

```caddy
wache.example.org {
        reverse_proxy 127.0.0.1:8090
}
```

Hostname und HTTPS-Origin müssen in `ALLOWED_HOSTS` und
`CSRF_TRUSTED_ORIGINS` stehen. Der Proxy sollte `X-Forwarded-Proto` setzen.
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

## Verkehrslage (optional)

Je Wache unter Einstellungen aktivierbar (`traffic_enabled`); Straßen, Umkreis,
Warngebiete, kommunale Quellen und Koordinaten sind dort bzw. in der
Ersteinrichtung konfigurierbar. Es gibt keine festen Standort- oder Regionswerte.

- Der Server ruft die Quellen selbst ab (Autobahn GmbH, optional Gemeinde
  Steinhagen und Kreis Gütersloh, BBK-Warnungen) und cached das Ergebnis zehn
  Minuten je Konfiguration. Es werden keine Personen- oder Wachendaten gesendet.
- Zugelassen sind nur die festen HTTPS-Hosts in `core/traffic.py`
  (`ALLOWED_HOSTS`); Weiterleitungen werden nicht verfolgt. Neue Quellen
  erfordern eine Codeänderung, keine Konfiguration.
- Autobahnen benötigen Koordinaten der Wache; ohne Koordinaten werden sie
  übersprungen. Ohne Warngebiete werden keine BBK-Warnungen abgerufen, außer der
  Ort der Wache ist gesetzt.
- Ausfall einer Quelle verkleinert nur die Liste; eine Ausfallanzeige existiert
  noch nicht (Roadmap R-025). Die kommunalen Quellen werten HTML aus und können
  bei Layoutänderungen der Seiten leer werden.

## DWD-Wetterwarnungen (optional)

Je Wache unter Einstellungen (`dwd_alerts_enabled`, Standard aus) oder in der
Ersteinrichtung aktivierbar. Der Server fragt `api.brightsky.dev/alerts` mit der
auf zwei Nachkommastellen gerundeten Wachenkoordinate ab (kein API-Schlüssel),
cached zehn Minuten (bei Fehlern eine Minute) und zeigt die Warnungen auf der
Wandanzeige; ein Ausfall wird als „Warnquelle nicht erreichbar“ angezeigt. Es
gelten dieselben Grenzen wie bei der Verkehrslage (HTTPS-Allowlist, keine
Redirects, begrenzte Antwortgröße). Ohne Koordinaten der Wache findet kein Abruf
statt. Das Antwortformat wurde ohne Live-Zugriff nach der Bright-Sky-Dokumentation
umgesetzt und ist vor dem Pilot gegen den echten Dienst zu prüfen.

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

### Aufbewahrung alter Dumps

`BACKUP_RETENTION_DAYS` (Standard `7`) steuert, wie viele Tage alte Dumps
im `backup`-Container behalten werden. Jeder Durchlauf löscht Dateien
(`rwsth-*.dump`, `rwsth-*.dump.gpg`), deren Modifikationszeit älter ist.
Der Wert `0` deaktiviert das Löschen; der lokale Ring wächst dann
unbegrenzt und muss von Hand gepflegt werden. Die Einstellung wirkt nur
auf die lokalen Dumps im Container, nicht auf das Offsite-Ziel.

```bash
# in .env
BACKUP_RETENTION_DAYS=14   # zwei Wochen behalten
BACKUP_RETENTION_DAYS=0    # nie automatisch loeschen
```

### Offsite-Verschlüsselung

Wenn `BACKUP_ENCRYPT_REMOTE=true` gesetzt ist, wird jeder Dump vor dem
Offsite-Upload symmetrisch mit GnuPG gegen `BACKUP_GPG_RECIPIENT`
(AES-256, Empfänger-Fingerprint oder E-Mail) verschlüsselt. Der Klartext
verlässt den Container nie. `BACKUP_OFF_TARGET` akzeptiert `file://`-Ziele
und ist die einzige Stelle, an der das verschlüsselte Artefakt abgelegt
wird. Ein leerer Wert führt das lokale Backup weiter aus, unterdrückt
aber den Offsite-Schritt.

```bash
# in .env
BACKUP_ENCRYPT_REMOTE=true
BACKUP_GPG_RECIPIENT=ops-backup@example.org
BACKUP_OFF_TARGET=file:///srv/wachbuch-offsite
```

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

App- und Feed-Rollenpasswörter rotieren (Owner-Passwort bleibt unangetastet):

```bash
./scripts/rotate-db-passwords.sh
```

Das Skript setzt neue Zufallswerte in PostgreSQL und `.env`, startet `web` und
`feed-worker` neu. Anschließend Healthcheck und Feed-Worker-Logs prüfen. Das
Owner-Passwort (`POSTGRES_PASSWORD`) nur mit Dump/Restore und Neuinitialisierung
rotieren.

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

### Release vorbereiten

1. SemVer in `core/version.py` setzen und `CHANGELOG.md` aktualisieren.
2. Migrationshinweise und Breaking Changes dokumentieren.
3. Backup und Restore-Test ausführen.
4. Abhängigkeiten und Image-Digests kontrolliert aktualisieren.
5. `docker compose build --no-cache` ausführen.
6. Images auf HIGH/CRITICAL-Schwachstellen scannen.
7. Tests ausführen und danach `docker compose up -d` starten.
8. Healthcheck inkl. Versionsfeld, Anmeldung, Rollen, Tagesaufgaben und optionale
   Feeds prüfen.
9. Service-Worker-Caches leeren bzw. einmal ab-/anmelden, falls Shell-Assets
   geändert wurden.

### Rollback

1. Vorheriges Image-Tag bzw. Compose-Revision wieder aktivieren.
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
