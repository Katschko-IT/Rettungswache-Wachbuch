# AGENTS.md

Arbeitsanleitung fuer Coding-, Review- und Operations-Agenten in diesem Repository.

## 1. Produktgrenze

Das Wachbuch organisiert interne Wachenablaeufe. Es ist **kein** System fuer
Patienten-, Einsatz-, Alarmierungs-, Diagnose-, Krankheits- oder Leistungsdaten.
Neue Funktionen duerfen diese Grenze weder durch Felder noch durch freie
Standardtexte, Telemetrie oder Exporte aufweichen.

## 2. Quellen der Wahrheit

Vor einer Aenderung mindestens lesen:

1. `README.md` – Produkt, Schnellstart und Betriebsmodell
2. `docs/ARCHITECTURE.md` – Vertrauensgrenzen und Datenfluss
3. `docs/SECURITY-PRIVACY.md` – Sicherheits- und Datenschutzinvarianten
4. `docs/DESIGN-SYSTEM.md` – UI-, Responsive- und Accessibility-Regeln
5. `docs/REMEDIATION-ROADMAP-2026-08.md` – offene Review-Massnahmen
6. `docs/GO-LIVE-CHECKLIST.md` – Freigabekriterien

Status in der Remediation-Roadmap:

- `[ ]` offen
- `[~]` begonnen / nicht vollstaendig abgenommen
- `[x]` umgesetzt und durch die dort genannten Checks belegt
- `[!]` blockiert; Grund und naechste Aktion muessen daneben stehen

## 3. Repository-Karte

- `config/` – Django-Konfiguration, URLs und WSGI
- `core/models.py` – Datenmodell und Datenbankinvarianten
- `core/services.py` – transaktionale Fachoperationen und Audit
- `core/access.py` – stationsbezogene Rollen- und Objektgrenzen
- `core/api/` – versionierte Token-API
- `core/static/core/` – lokale CSS-/JavaScript-Assets, keine CDN-Abhaengigkeiten
- `templates/` – serverseitig gerenderte Oberflaeche
- `scripts/` – Start, Migration, Backup und Restore
- `docs/` – Architektur, Betrieb, Compliance, Tests und Roadmaps

## 4. Nicht verhandelbare Invarianten

- Jede fachliche Abfrage bleibt an `request.membership.station` gebunden.
- Auditoren erhalten keine fachlichen Freitexte.
- Audit, Kaffeekasse, Checklisten-Abschluesse und Uebergaberevisionen bleiben
  append-only; Korrekturen erfolgen durch neue Datensaetze.
- Keine allgemeinen Datei-Uploads; Avatare bleiben typ- und groessenbegrenzt.
- Externe Feedziele bleiben HTTPS-Allowlist, Port 443, ohne Redirects/private IPs.
- CSP bleibt ohne `unsafe-inline` und ohne `unsafe-eval`.
- Benutzerkontrollierte Daten duerfen nie mit `|safe`, `innerHTML` oder
  aehnlichen HTML-Sinks in die Seite gelangen. Fuer JSON `json_script` nutzen.
- Keine gemeinsam genutzten Konten; keine Umgehung von MFA/Rollen im Mobile-API.
  Einzige eng begrenzte Ausnahme: das dokumentierte Sammelkonto `Demo`/`Demo` der
  isolierten öffentlichen Demo (`DEMO_PUBLIC_MODE`), nie im Produktivbetrieb.
- Die öffentliche Demo bleibt hinter dem Login-Formular: kein passwortloser
  Einstieg (`demo_login`) und keine Verwaltungs-/Registrierungsrouten.
- E2EE-Aussagen muessen das reale Vertrauensmodell nennen: gespeicherter
  Ciphertext ist geschuetzt, der ausgelieferte Webclient und Server bleiben
  bei der Web-PWA Teil des Vertrauensmodells.

## 5. Arbeitsablauf

1. Passende Roadmap-ID waehlen und Status auf `[~]` setzen.
2. Eine kleine, zusammenhaengende Aenderung umsetzen.
3. Negative Tests fuer den urspruenglichen Fehler hinzufuegen.
4. Dokumentation und Betriebsauswirkungen im selben PR aktualisieren.
5. Relevante Checks ausfuehren.
6. Roadmap erst nach belegter Abnahme auf `[x]` setzen.
7. Im PR die Roadmap-ID, Ursache, Risiko, Tests und verbleibende Grenzen nennen.

Keine grossen Sicherheits-, Krypto-, Auth-, Backup- oder Datenmodellumbauten mit
unverbundenen UX-Funktionen in denselben PR mischen.

## 6. Standardpruefungen

```bash
python manage.py makemigrations --check --dry-run --settings=config.test_settings
python manage.py test --settings=config.test_settings
python manage.py check --deploy --settings=config.settings

docker compose config --quiet
docker build --tag rettungswache-wachbuch:test .
```

Fuer Frontend-Aenderungen zusaetzlich:

```bash
node --check core/static/core/app.js
node --check core/static/core/json_data.js
```

Vor Produktion bleiben Browser-, Screenreader-, Last-, Restore- und externe
Sicherheitstests gemaess Roadmap und Go-live-Checkliste erforderlich.

## 7. Handoff fuer den naechsten Agenten

Jeder unvollstaendige Arbeitsstand dokumentiert:

```text
Roadmap-ID:
Branch/PR:
Bereits geaendert:
Ausgefuehrte Checks und Ergebnis:
Offene Risiken/Blocker:
Naechste kleinste Aktion:
```

Keine Aufgabe als erledigt markieren, wenn nur Dokumentation, Mock oder ein
nicht ausgefuehrter Test vorliegt.
