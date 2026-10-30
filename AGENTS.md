# AGENTS.md

Arbeitsanleitung für Coding-, Review- und Operations-Agenten in diesem Repository.

## 1. Produktgrenze

Das Wachbuch organisiert interne Wachenablaeufe. Es ist **kein** System für
Patienten-, Einsatz-, Alarmierungs-, Diagnose-, Krankheits- oder Leistungsdaten.
Neue Funktionen dürfen diese Grenze weder durch Felder noch durch freie
Standardtexte, Telemetrie oder Exporte aufweichen.

## 2. Quellen der Wahrheit

Vor einer Änderung mindestens lesen:

1. `README.md` – Produkt, Schnellstart und Betriebsmodell
2. `docs/ARCHITECTURE.md` – Vertrauensgrenzen und Datenfluss
3. `docs/SECURITY-PRIVACY.md` – Sicherheits- und Datenschutzinvarianten
4. `docs/DESIGN-SYSTEM.md` – UI-, Responsive- und Accessibility-Regeln
5. `docs/REMEDIATION-ROADMAP-2026-08.md` – offene Review-Maßnahmen
6. `docs/GO-LIVE-CHECKLIST.md` – Freigabekriterien

Status in der Remediation-Roadmap:

- `[ ]` offen
- `[~]` begonnen / nicht vollständig abgenommen
- `[x]` umgesetzt und durch die dort genannten Checks belegt
- `[!]` blockiert; Grund und nächste Aktion müssen daneben stehen

## 3. Repository-Karte

- `config/` – Django-Konfiguration, URLs und WSGI
- `core/models.py` – Datenmodell und Datenbankinvarianten
- `core/services.py` – transaktionale Fachoperationen und Audit
- `core/access.py` – stationsbezogene Rollen- und Objektgrenzen
- `core/api/` – versionierte Token-API
- `core/static/core/` – lokale CSS-/JavaScript-Assets, keine CDN-Abhaengigkeiten
- `templates/` – serverseitig gerenderte Oberfläche
- `scripts/` – Start, Migration, Backup und Restore
- `docs/` – Architektur, Betrieb, Compliance, Tests und Roadmaps

## 4. Nicht verhandelbare Invarianten

- Jede fachliche Abfrage bleibt an `request.membership.station` gebunden.
- Auditoren erhalten keine fachlichen Freitexte.
- Audit, Kaffeekasse, Checklisten-Abschlüsse und Übergaberevisionen bleiben
  append-only; Korrekturen erfolgen durch neue Datensätze.
- Keine allgemeinen Datei-Uploads; Avatare bleiben typ- und groessenbegrenzt.
- Externe Feedziele bleiben HTTPS-Allowlist, Port 443, ohne Redirects/private IPs.
- CSP bleibt ohne `unsafe-inline` und ohne `unsafe-eval`.
- Benutzerkontrollierte Daten dürfen nie mit `|safe`, `innerHTML` oder
  ähnlichen HTML-Sinks in die Seite gelangen. Für JSON `json_script` nutzen.
- Keine gemeinsam genutzten Konten; keine Umgehung von MFA/Rollen im Mobile-API.
  Einzige, vom Betreiber entschiedene Ausnahme: das Dienstkonto „Wachenterminal“
  (`core/terminal.py`) – ohne Passwort und App-Token, nur an registrierten
  Terminals, Rolle Mitglied, beschränkt auf die Alltagsbereiche des
  Terminal-Modus. Es darf nicht erweitert werden (keine Medizingeräte,
  Fahrzeugübernahme, Lesebestätigungen, Verwaltung).
- E2EE-Aussagen müssen das reale Vertrauensmodell nennen: gespeicherter
  Ciphertext ist geschützt, der ausgelieferte Webclient und Server bleiben
  bei der Web-PWA Teil des Vertrauensmodells.

## 5. Arbeitsablauf

1. Passende Roadmap-ID wählen und Status auf `[~]` setzen.
2. Eine kleine, zusammenhängende Änderung umsetzen.
3. Negative Tests für den ursprünglichen Fehler hinzufügen.
4. Dokumentation und Betriebsauswirkungen im selben PR aktualisieren.
5. Relevante Checks ausführen.
6. Roadmap erst nach belegter Abnahme auf `[x]` setzen.
7. Im PR die Roadmap-ID, Ursache, Risiko, Tests und verbleibende Grenzen nennen.

Keine großen Sicherheits-, Krypto-, Auth-, Backup- oder Datenmodellumbauten mit
unverbundenen UX-Funktionen in denselben PR mischen.

## 6. Standardprüfungen

```bash
python manage.py makemigrations --check --dry-run --settings=config.test_settings
python manage.py test --settings=config.test_settings
python manage.py check --deploy --settings=config.settings

docker compose config --quiet
docker build --tag rettungswache-wachbuch:test .
```

Gegen PostgreSQL (Pflicht für jede Migration). Die CI prüft das im Job
`django-postgres` mit Version und Konfiguration des db-Images und einer
Update-Probe vom letzten Release mit Musterdaten:

```bash
docker run --rm -d --name wachwerk-pg -p 127.0.0.1:5432:5432 \
  -e POSTGRES_USER=rwsth_owner -e POSTGRES_PASSWORD=dev -e POSTGRES_DB=rwsth \
  -v "$PWD/config/postgresql.conf:/etc/postgresql/postgresql.conf:ro" \
  "$(sed -n 's/^FROM \(postgres:[^ ]*\) AS pgbase$/\1/p' Dockerfile.backup)" \
  postgres -c config_file=/etc/postgresql/postgresql.conf
DJANGO_SECRET_KEY=test-only DATABASE_URL=postgres://rwsth_owner:dev@127.0.0.1:5432/rwsth \
  python manage.py test --settings=config.test_settings
```

Ohne Docker (z. B. in einer Agenten-Sandbox): ein vorhandenes PostgreSQL ab
Version 16 und ein Konto mit dem Recht `CREATEDB`, mit denselben Grenzen wie
`config/postgresql.conf`:

```bash
DJANGO_SECRET_KEY=test-only DATABASE_URL=postgres://BENUTZER@127.0.0.1:5432/rwsth \
PGOPTIONS='-c statement_timeout=60s -c lock_timeout=30s -c idle_in_transaction_session_timeout=10s -c timezone=Europe/Berlin' \
  python manage.py test --settings=config.test_settings
```

Regeln, damit beide Datenbanken grün bleiben:

- Datenmigrationen in Abschnitten schreiben: keine Abfrage über 60 s, keine
  Pause über 10 s in einer offenen Transaktion. Die CI hat nur Musterdaten und
  findet deshalb nur grobe Fehler; Datenmigrationen und Importe zusätzlich mit
  einer realistischen Datenmenge prüfen.
- `RunSQL` und andere datenbankabhängige Zweige brauchen einen Weg für
  PostgreSQL und einen für SQLite.
- In einem `TestCase` nie `response.close()` direkt aufrufen: Gegen PostgreSQL
  schließt das die Testverbindung. Streams so schließen wie `close_stream` in
  `core/test_display_security.py`.
- In ein `GenericIPAddressField` (PostgreSQL: `inet`) nur eine gültige Adresse
  oder `None` schreiben, nie einen Platzhalter wie „unknown“.
- Mergen erst, wenn `django-postgres` grün ist, einschließlich der Update-Probe.

Für Frontend-Änderungen zusätzlich:

```bash
node --check core/static/core/app.js
node --check core/static/core/json_data.js
node --check core/static/core/ui.js
```

Templates enthalten keine Inline-Skripte, keine `on…=`-Handler und keine
`style`-Attribute (CSP ohne `unsafe-inline`; geprüft durch
`core/test_csp_templates.py`). Verhalten über `data-*`-Attribute in
`core/static/core/ui.js`, Gestaltung über `app.css`/`modules.css`.

Vor Produktion bleiben Browser-, Screenreader-, Last-, Restore- und externe
Sicherheitstests gemaess Roadmap und Go-live-Checkliste erforderlich.

## 7. Handoff für den nächsten Agenten

Jeder unvollständige Arbeitsstand dokumentiert:

```text
Roadmap-ID:
Branch/PR:
Bereits geaendert:
Ausgefuehrte Checks und Ergebnis:
Offene Risiken/Blocker:
Naechste kleinste Aktion:
```

Keine Aufgabe als erledigt markieren, wenn nur Dokumentation, Mock oder ein
nicht ausgeführter Test vorliegt.
