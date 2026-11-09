# Mitwirken

## Entwicklung

1. Einen Fork oder Branch anlegen.
2. Keine echten Wach-, Mitarbeiter-, Einsatz- oder Zugangsdaten verwenden.
3. Änderungen klein halten und durch Tests absichern.
4. Vor dem Pull Request Tests und Docker-Build ausführen.

```bash
docker compose build web
docker compose run --rm --no-deps \
  -e DJANGO_SECRET_KEY=test-only \
  -e DJANGO_DEBUG=false \
  -e DATABASE_URL=sqlite:////tmp/test.sqlite3 \
  web python manage.py test --settings=config.test_settings
```

Bei Migrationen zusätzlich gegen PostgreSQL in der Version des db-Images
(lokale Python-Umgebung; Variante ohne Docker und Regeln in
[`AGENTS.md`](AGENTS.md) § 6):

```bash
docker run --rm -d --name wachwerk-pg -p 127.0.0.1:5432:5432 \
  -e POSTGRES_USER=rwsth_owner -e POSTGRES_PASSWORD=dev -e POSTGRES_DB=rwsth \
  -v "$PWD/config/postgresql.conf:/etc/postgresql/postgresql.conf:ro" \
  "$(sed -n 's/^FROM \(postgres:[^ ]*\) AS pgbase$/\1/p' Dockerfile.backup)" \
  postgres -c config_file=/etc/postgresql/postgresql.conf
DJANGO_SECRET_KEY=test-only DATABASE_URL=postgres://rwsth_owner:dev@127.0.0.1:5432/rwsth \
  python manage.py test --settings=config.test_settings
```

Die CI führt die Tests mit SQLite und mit PostgreSQL aus, PostgreSQL in Version
und Konfiguration des db-Images. Dazu kommen die Migration von null mit den
echten Datenbankrollen (Job `docker`) und ein Update vom letzten Release mit
Musterdaten (Job `django-postgres`).

### Mobile-Client (AGPL)

```bash
cd clients/wachbuch-mobile
flutter pub get
flutter test
flutter analyze
```

Der Client spricht nur `/api/v1/` an; siehe [`docs/CLIENT.md`](docs/CLIENT.md).

Pull Requests sollen Zweck, Verhaltensänderung, Tests und mögliche
Datenschutz- oder Migrationsfolgen beschreiben. Neue Abhängigkeiten brauchen
eine Begründung und kompatible Lizenz (Server und Client: AGPL-kompatibel).

## Abhängigkeiten und Hashes

`requirements.txt` führt die direkten Produktionsabhängigkeiten.
`requirements.lock` enthält die aufgelösten direkten und transitiven
Abhängigkeiten mit SHA256-Hashes und ist der Installationsweg in CI und im
Docker-Builder:

```bash
./scripts/update-hashes.sh   # erzeugt requirements.lock via pip-compile --generate-hashes
pip install --require-hashes -r requirements.lock   # Installation mit Hash-Verifikation
docker build --tag rettungswache-wachbuch:test .  # Builder erzwingt denselben Lockfile-Pfad
```

Für reproduzierbare CI-Qualitätswerkzeuge gilt derselbe Fail-Closed-Grundsatz:
`requirements-ci.in` beschreibt Ruff; `requirements-ci.lock` enthält die
aufgelöste Version und SHA256-Hashes. Der separate Audit-Scanner steht in
`requirements-audit.in`/`requirements-audit.lock`, damit seine transitiven
Werkzeuge die Produktions-/Lint-Umgebung nicht verändern. Die CI verwendet
Ruff für den Baseline-Gate (E4/E7/E9 sowie F63/F7/F82: fehlerhafte Vergleiche,
Syntaxfehler und undefinierte Namen wie ein fehlender Import) und `pip-audit` für den reproduzierbaren
Dependency-Vulnerability-Scan. Die vollständige Formatpruefung und eine
breitere Regelmenge bleiben wegen des bestehenden Altbestands bewusst separate
Folge-Schritte.

```bash
uv pip compile --generate-hashes --python-version 3.13 \
  requirements-ci.in --output-file requirements-ci.lock
uv pip compile --generate-hashes --python-version 3.13 \
  requirements-audit.in --output-file requirements-audit.lock
pip install --require-hashes -r requirements.lock -r requirements-ci.lock
pip install --require-hashes -r requirements-audit.lock  # in isolierter Audit-venv
pip-audit --strict --requirement requirements.lock
ruff check config core --select E4,E7,E9,F63,F7,F82 --output-format=concise
```

Die CI verweigert die Installation, wenn ein Paket oder Hash in der Lock-Datei
fehlt oder nicht zum heruntergeladenen Artefakt passt. Bei jeder Änderung an
`requirements.txt` die Lock-Datei neu erzeugen, die Hash-Verifikation lokal
prüfen und beide Dateien committen.

## Barrierefreiheit und Wand-Display prüfen (Job `a11y`)

Der CI-Job `a11y` startet die App wie im Container (DEBUG aus, Gunicorn mit
WhiteNoise nach `collectstatic`, echte CSP) mit Musterdaten und prüft mit
axe-core und Playwright (gesperrt in `tests/a11y/package-lock.json`):

- die Hauptseiten jeder Rolle (auch Wachenterminal) in vier Darstellungen:
  System hell und dunkel sowie der Umschalter der App gegen das System;
  jeder Fund der Schwere critical oder serious lässt den Job scheitern,
- das Wand-Display über den Display-Link bei 1920x1080 und 1280x720 (kein
  Scrollen, Raster 16:9 auf 0,02 genau, kein sichtbares Element außerhalb von
  Raster oder Bildschirm, keine abgeschnittene Spalte, keine Emojis),
- das Mangelformular bei 390x844 ohne seitliches Scrollen.

Bericht und Bildschirmfotos liegen als Artefakt `a11y-report` am Lauf. Lokal
(SQLite in einem eigenen Verzeichnis, nie `runserver --insecure`, sonst fehlen
die gehashten CSS-Dateien):

```bash
export DJANGO_SECRET_KEY=test-only DJANGO_DEBUG=false DEMO_MODE=true   TERMINAL_ENABLED=true TERMINAL_CODE=1234 SECURE_COOKIES=false   BASE_URL=http://127.0.0.1:8765 DATABASE_URL=sqlite:////tmp/a11y/db.sqlite3
python manage.py migrate --noinput && python manage.py load_demo_data
python manage.py collectstatic --noinput
python tests/a11y/seed.py > /tmp/a11y/seed.json
GUNICORN_BIND=127.0.0.1:8765 gunicorn --config config/gunicorn.py --daemon   --pid /tmp/a11y/gunicorn.pid config.wsgi:application
cd tests/a11y && npm ci --ignore-scripts && npx playwright install chromium
SEED_JSON=/tmp/a11y/seed.json OUT_DIR=/tmp/a11y/out node run-axe.js
```

`A11Y_ROLES` und `A11Y_THEMES` schränken einen lokalen Lauf ein (z. B.
`A11Y_ROLES=none` prüft nur das Wand-Display).

## Datenschutz

Issues, Tests, Screenshots und Commits dürfen keine personenbezogenen Daten,
Session-Cookies, `.env`-Inhalte, Datenbank-Dumps oder Tailnet-Details enthalten.
