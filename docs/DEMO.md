# Demo-Modus mit Musterdaten

Stand: 2. August 2026 (Server ≥ **0.15.0**); öffentliche Demo ergänzt.

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
Ein gelber Banner „Demo-Modus“ ist überall sichtbar.

## Was wird angelegt?

- Module (Kalender, Aufgaben, Kasse, Chat, Feiertage, Checklisten)
- Offene / laufende / erledigte **Übergaben** (Marker `[Demo]`)
- Termine, Kaffeekassen-Buchungen, Checklisten, Chat-Nachrichten (Klartext)
- Ein erledigter Tagesaufgaben-Eintrag
- **Mängel** in allen Statusstufen (Fahrzeug, Gerät, Gebäude, Schlüssel)
- **Fuhrpark/Gerätestatus** (`StationAsset` mit Einsatzklar/Eingeschränkt/Werkstatt)
- **Inventar/Ausgabe** (`InventoryItem` mit Ausgabe an ein Demo-Konto)
- **Wiederkehrende Prüfungen** (`ChecklistSchedule`: ein überfälliger und ein anstehender Lauf)

Keine Patienten-, Alarm- oder Dienstplandaten. Alle Zeilen tragen den Marker
`[Demo]` in Titel/ID/Label und werden bei `--reset` gezielt — auch in den
append-only Ereignistabellen — wieder entfernt.

## Öffentliche Demo (`DEMO_PUBLIC_MODE`)

Für eine öffentlich erreichbare Vorführung (eigene Instanz, eigene Datenbank,
nur fiktive Daten) gibt es `DEMO_PUBLIC_MODE`. Es ist ein striktes Superset von
`DEMO_MODE`: Musterdaten und Banner sind aktiv, zusätzlich greifen harte,
**nicht abschaltbare** Schutzregeln und ein festes Zugangsverfahren.

```bash
DEMO_PUBLIC_MODE=true
DEMO_PASSWORD=Demo-Passwort-12345
DEFAULT_STATION_NAME=Demo-Wache Musterstadt
```

### Zugang über das Anmeldeformular

Der öffentliche Zugang erfolgt **ausschließlich über das Anmeldeformular**
(`/anmelden/`). Der passwortlose Ein-Klick-Einstieg (`/demo-einstieg/`,
`demo_login`) ist im öffentlichen Modus deaktiviert und liefert HTTP 404 –
sowohl über die Guard-Middleware als auch direkt in der View. Für Besucher
gibt es einen einzelnen, dokumentierten Sammelzugang:

| Feld | Wert |
| --- | --- |
| Benutzername | `Demo` |
| Passwort | `Demo` |

Beide Werte sind **groß-/kleinschreibungssensitiv** und fest in `core/demo.py`
hinterlegt (`DEMO_PUBLIC_USERNAME` / `DEMO_PUBLIC_PASSWORD`). Der Zugang wird
nur im öffentlichen Modus angelegt; er besitzt eine aktive Admin-Mitgliedschaft
auf der Musterwache, ist aber **kein** Django-`is_staff`/`is_superuser`-Konto.
Die Zugangsdaten und ein kurzer Hinweis stehen auf der Startseite, unter
`/vorfuehrung/` und direkt auf der Anmeldeseite.

Außerhalb von `DEMO_PUBLIC_MODE` (reiner `DEMO_MODE`) bleibt der
Ein-Klick-Einstieg wie bisher verfügbar; der `Demo`-Zugang wird dann nicht
angelegt.

Beim Aktivieren erzwingt die Konfiguration unabhängig von anderen Variablen:
`REGISTRATION_ENABLED=false`, `WEB_PUSH_ENABLED=false` (VAPID-Schlüssel leer),
`FEED_ALLOWED_HOSTS` leer und `MFA_REQUIRED=false`. Die öffentliche Demo bleibt
eine getrennte Instanz ohne Produktivdaten; sie ersetzt keinen Go-live.

Zusätzlich blockiert eine serverseitige Guard-Middleware
(`core.middleware.PublicDemoGuardMiddleware`) **bestehende Routen** anhand ihres
URL-Namens mit HTTP 404. Besucher können damit nicht:

- Django-Admin (`/django-admin/`) öffnen,
- sich registrieren (`/registrieren/`) oder Konten anlegen/freigeben
  (`/team/anlegen/`, `/team/freigeben/`, Ablehnung),
- Rollen/Status einer Mitgliedschaft ändern (`/team/<id>/`),
- Wach-Einstellungen ändern (`/einstellungen/`),
- MFA/Passkeys einrichten, ändern oder entfernen (`/konto/mfa/…`),
- API-Tokens erzeugen (`/konto/api/`, `/api/v1/token/`, `/api/v1/anmeldung/`),
- Push abonnieren (`/benachrichtigungen/`) oder Kalender-Abo-Links erzeugen
  (`/kalender/abo/`),
- auf `/konto/` das Passwort eines Demo-Kontos ändern,
- den passwortlosen Ein-Klick-Einstieg (`/demo-einstieg/`, `demo_login`)
  verwenden.

Interaktiv bleiben die operativen Kernabläufe: Übergaben, Kalender, Aufgaben,
Mängel, Fuhrpark/Gerätestatus, Checklisten/Prüfintervalle und Kaffeekasse.
Der Normalbetrieb (ohne `DEMO_PUBLIC_MODE`) ist unverändert; allgemeine
Security/MFA-Einstellungen werden nicht abgeschwächt.

## Sicherheit

- Standard ist `DEMO_MODE=false` und `DEMO_PUBLIC_MODE=false`
- Passwörter sind öffentlich dokumentiert – nur Loopback/Test bzw. die
  abgesonderte öffentliche Demo
- Bei `DEMO_MODE`/`DEMO_PUBLIC_MODE` wird `MFA_REQUIRED` automatisch abgeschaltet
- Die öffentliche Demo nutzt bewusst ein **gemeinsames, dokumentiertes Konto**
  (`Demo`/`Demo`) als eng begrenzte Ausnahme zur Regel „keine gemeinsam
  genutzten Konten“ – nur auf der isolierten Demoinstanz, nie im
  Produktivbetrieb
- `DEMO_PUBLIC_MODE` ist ausschließlich für eine isolierte Instanz mit fiktiven
  Daten gedacht und darf nie auf einer Produktivdatenbank aktiviert werden
