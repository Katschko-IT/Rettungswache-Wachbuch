# Demo-Modus mit Musterdaten

Stand: 2. August 2026 (Server ≥ **0.15.0**).

Für lokale Tests und Vorführungen kann Wachbuch mit fiktiven Musterdaten
gestartet werden. **Nicht für Produktivsysteme.**

## Einschalten

In `.env`:

```bash
DEMO_MODE=true
DEMO_PASSWORD=Demo-Passwort-12345
MFA_ENABLED=false
MFA_REQUIRED=false
DEFAULT_STATION_NAME=Demo-Wache Musterstadt
```

Dann:

```bash
docker compose up --build -d
# migrate führt automatisch load_demo_data aus, wenn DEMO_MODE=true
```

Oder manuell:

```bash
docker compose exec web python manage.py load_demo_data
docker compose exec web python manage.py load_demo_data --reset   # neu befüllen
```

Ohne `DEMO_MODE` (nur lokal mit Debug):

```bash
python manage.py load_demo_data --force
```

## Demo-Konten

Gemeinsames Passwort: Wert von `DEMO_PASSWORD` (Standard `Demo-Passwort-12345`).

| Benutzer | Rolle |
| --- | --- |
| `demo-admin` | Master-Admin |
| `demo-schicht` | Schichtleitung |
| `demo-kasse` | Kassenwart |
| `demo-mitglied` | Mitglied |
| `demo-audit` | Auditor |

Auf der Startseite erscheinen die Konten, solange `DEMO_MODE=true` ist.
Unter `/vorfuehrung/` gibt es denselben One-Click-Einstieg, ohne Fachdaten.
Ein gelbes Banner „Demo-Modus“ ist überall sichtbar.

## Was wird angelegt?

- Module (Kalender, Aufgaben, Kasse, Chat, Feiertage, Checklisten)
- Offene / laufende / erledigte **Übergaben** (Marker `[Demo]`)
- Termine, Kaffeekassen-Buchungen, Checklisten, Chat-Nachrichten (Klartext)
- Ein erledigter Tagesaufgaben-Eintrag

Keine Patienten-, Alarm- oder Dienstplandaten.

## Sicherheit

- Standard ist `DEMO_MODE=false`
- Passwörter sind öffentlich dokumentiert – nur Loopback/Test
- Bei `DEMO_MODE` wird `MFA_REQUIRED` automatisch abgeschaltet
