# E2E-Abnahme Wachalltag 0.6.x

Diese Checkliste prüft **denselben fachlichen Ablauf in Demo und gegen einen echten Server**. Für die Produktionsabnahme muss der Server `0.16.x` mit dem aktuellen `/api/v1/`-Vertrag verwendet werden.

## Voraussetzungen

- aktueller Client-Build `0.6.x`
- Server `0.16.x` mit HTTPS
- Testkonto mit App-Token und aktiver Wachen-Mitgliedschaft
- für Stammdaten-/Statusänderungen eine Rolle mit Schreibberechtigung
- keine Patienten-, Einsatz-, Alarmierungs- oder ePCR-Daten als Testinhalt

## Pflichtpfad

| # | Schritt | Erwartung |
| --- | --- | --- |
| 1 | Demo starten | Station, Module und Demo-Banner erscheinen ohne Serverzugriff |
| 2 | Echten Server verbinden und anmelden | `/api/v1/`, Token und `/me/` funktionieren; kein Demo-Banner |
| 3 | Mängel öffnen und Mangel anlegen | Eintrag wird serverseitig gespeichert und nach Reload erneut geladen |
| 4 | Mangelstatus ändern | Status wird gespeichert; Verlauf/Audit erzeugt keinen doppelten Eintrag bei identischem Status |
| 5 | Foto per Kamera oder Mediathek hinzufügen | JPEG/PNG/WebP wird authentifiziert gespeichert und wieder geladen; >2 MiB wird abgewiesen |
| 6 | Foto-Kontingent prüfen | Maximal 8 Fotos bzw. 12 MiB Gesamtmenge pro Mangel; weiterer Upload wird abgewiesen |
| 7 | Geräte & Status öffnen und Asset antippen | Status/Notiz lässt sich bei berechtigter Rolle ändern und bleibt nach Reload erhalten |
| 8 | Schlüssel/Pool ausgeben und zurückgeben | Holder/Since wechseln korrekt; konkurrierende Ausgabe wird nicht überschrieben |
| 9 | Übergabe öffnen und quittieren | Quittierung erscheint; wiederholtes Quittieren erzeugt keinen zweiten Datensatz |
| 10 | In derselben Übergabe „Mangel anlegen“ wählen | Titel, Details und Priorität werden einmalig als echter Server-Mangel übernommen |
| 11 | Wiederkehrende Checkliste abschließen | nächste Fälligkeit wird täglich/wöchentlich/monatlich weitergesetzt |
| 12 | Auswertung öffnen | offene/überfällige Mängel, Checks, Einsatzklarquote, ausgegebene Pools und unquittierte Übergaben entsprechen dem Serverstand |
| 13 | Nach erfolgreichem Online-Laden offline gehen | lesbare Cache-Daten bleiben verfügbar; 401/403 werden niemals durch Cache verdeckt |
| 14 | Logout / Serverwechsel | `DELETE /api/v1/token/` wird best-effort aufgerufen; Token wird lokal entfernt; Cache darf nicht in eine andere Server-/Token-Sitzung hineinlecken |

## Fehlervertrag

Mindestens einmal gezielt prüfen:

- `401 auth_required`
- `403 forbidden`
- `403 mfa_required` bzw. `mfa_setup_required`
- `404 not_found`
- `409` bei fachlichem Konflikt, z. B. bereits ausgegebenem Pool
- `413` bei Foto-Limit
- `415` bei nicht erlaubtem Bildtyp
- `422 validation_error`
- `429 rate_limit`
- `500 server_error`

Der Client muss `error.code`, `error.message` und `error.correlation_id` verarbeiten; ältere flache Fehlerantworten bleiben nur aus Rückwärtskompatibilität unterstützt.

## Wiederholungs-/Retry-Regel

Automatisch wiederholt werden nur sichere bzw. serverseitig idempotente Vorgänge. Insbesondere **Token-Erzeugung, Mangelanlage, Übergabe→Mangel, Foto-Upload, Asset-/Inventar-Stammdaten und Checklistenabschluss dürfen nicht automatisch erneut gesendet werden**, wenn eine Antwort verloren geht.

## Abnahmekriterium

Freigabe nur, wenn Flutter-Analyse, Flutter-Tests, Android-Build/Lint/Sicherheitsgates, iOS-CI und Dependency-Security grün sind und der Server zusätzlich Django-, Migrations-, Deployment- und isolierte PostgreSQL/Docker-Tests besteht.
