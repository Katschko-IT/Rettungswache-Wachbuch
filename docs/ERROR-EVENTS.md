# Bereinigte Fehlerereignisse und Supportbericht (H4)

Die Anwendung erfasst serverseitige 5xx-Fehler als eng definierte technische
Ereignisse. Die Erfassung ist **best effort**: Sie darf den ursprünglichen Fehler
nicht verstärken, keine Schleife auslösen und die Antwort nicht blockieren.

## Gespeicherte Felder (vollständige Allowlist)

| Feld | Inhalt |
|---|---|
| `occurred_at` | Zeitpunkt der Erfassung |
| `correlation_id` | Vorhandene `X-Correlation-ID` nur bei Regex-Treffer `^[A-Za-z0-9_-]{1,128}$`, sonst frische UUID4 (hex) |
| `route_name` | Stabiler Django-View-Name (`resolver_match.view_name`), sonst `unmatched`; niemals der Rohpfad |
| `category` | `database`, `template`, `permission`, `validation`, `http`, `server` – ausschließlich aus der Exception-Klasse abgeleitet |
| `http_status` | 500–599 (DB-Check-Constraint) |
| `app_version` | `APP_VERSION` |
| `station` | nur gesetzt, wenn `request.membership` bereits sicher aufgelöst war; sonst `NULL` |

**Niemals gespeichert:** Exception-Meldungen, Tracebacks, Roh-URLs, Querystrings,
Request-/Response-Bodies, Cookies, Header, Tokens, Mitglieder-, Artikel- oder
Patientendaten. Das Modell besitzt für diese Inhalte bewusst keine Felder.

## Erfassungspfad

`core.diagnostics.ErrorEventMiddleware` verbindet `got_request_exception`
(unbehandelte Exception, Kategorie aus der Klasse) und prüft zusätzlich die
fertige Antwort auf Status ≥ 500 (z. B. bewusst erzeugte 503). Ein Request
erzeugt höchstens ein Ereignis (`request._error_event_recorded`). Schlägt das
Schreiben fehl (DB nicht erreichbar), wird das geschluckt und nur
`error_event_not_recorded` ohne Details geloggt.

Audit (`AuditEvent`) und Diagnose (`ErrorEvent`) bleiben getrennt; es werden keine
Audit-Einträge für technische Fehler erzeugt.

## Zugriff und Wachentrennung

- Liste und Export sind ausschließlich für Master-Admins (`Membership.Role.ADMIN`)
  der eigenen Wache. Mitglieder, Auditor und Anonyme erhalten `403` bzw. Redirect.
- Abgefragt wird immer `station=request.membership.station`. Globale Ereignisse
  (`station IS NULL`) und fremde Wachen werden weder angezeigt noch exportiert.
- Eine Korrelations-ID ist **keine Berechtigung**: Der optionale Filter
  `?korrelation=…` wird erst nach der Wachenfilterung angewandt und liefert für
  fremde IDs keine Zeile.

## Liste, Export, Grenzen

- Liste: 25 Ereignisse pro Seite (`?seite=`), nur innerhalb der Aufbewahrung.
- Supportbericht: `GET /system/supportbericht/`, Admin-only, `text/plain;
  charset=utf-8`, `Content-Disposition: attachment` mit festem Namen
  `wachbuch-support-YYYYmmdd-HHMMSS.txt`, `Cache-Control: no-store, private`,
  `X-Content-Type-Options: nosniff`.
- Exportfelder: Zeitpunkt, Korrelations-ID, Route, Kategorie, HTTP-Status,
  Softwareversion – plus minimale Checkzustände (Version, Build-Kennung,
  DB-Erreichbarkeit, Migrationszähler, Cachetyp). Keine Cache-Pfade, keine
  Umgebungsvariablen, keine Rohlogs.
- Obergrenze: `ERROR_EVENT_EXPORT_LIMIT` (Standard 200) Ereignisse pro Bericht.

## Aufbewahrung (technische Policy, keine Rechtsfrist)

Die Aufbewahrung ist eine konfigurierbare Betriebsrichtlinie und ausdrücklich
**keine gesetzliche Frist**:

```bash
ERROR_EVENT_RETENTION_DAYS=30          # Standard
python manage.py purge_error_events --dry-run
python manage.py purge_error_events    # löscht Ereignisse älter als die Policy
python manage.py purge_error_events --days 14
```

Der Befehl löscht ausschließlich bereinigte Ereignisse anhand von `occurred_at`.
In Compose erledigt das der Dienst `housekeeping` stündlich von selbst
(`core/management/commands/housekeeping.py`); ein Cron auf dem Host ist nicht
nötig.
Inhalts- und Löschrichtlinien für Fachdaten bleiben Betreiberentscheidung.

## Tests

`core/test_diagnostics.py` deckt echte 5xx-Erfassung, Feld-Allowlist, Leak-Test mit
synthetischen Tokens/URLs/Stacktraces, Rekursionsfreiheit bei Schreibfehlern,
Wachentrennung, globale Ereignisse, Korrelations-ID als Nicht-Berechtigung,
Pagination, Export-Header/-Allowlist, Limit und Aufbewahrungsbefehl ab.
