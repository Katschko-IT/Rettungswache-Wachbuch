# API für Mobile- und Drittclients

Stand: 20. August 2026 · Server **0.16.x** · OpenAPI **1.2.2**.

Versionierte JSON-API unter `/api/v1/` für den AGPL-Client [Wachbuch-Client](https://github.com/Katschko-IT/Wachbuch-Client) und kontrollierte Drittclients.

## Grundsätze

- selbst gehostete Clients ohne Browser-Session
- stabile Verträge unter `/api/v1/`
- widerrufbare App-Tokens (`wb_…`, Klartext nur einmal)
- stationsbezogene Rechte über die bestehende Mitgliedschaft
- Rollen- und Modulregeln werden serverseitig erzwungen
- kanonische strukturierte JSON-Fehler mit Korrelations-ID
- keine Patienten-, Einsatz-, Alarmierungs-, ePCR- oder Personalaktendaten

## Authentifizierung

```http
Authorization: Token <geheim>
```

`Bearer <geheim>` wird ebenfalls akzeptiert.

### Token erzeugen

Bevorzugt wird ein App-Token unter **Mein Konto → App-Tokens** (`/konto/api/`). Alternativ steht `POST /api/v1/token/` beziehungsweise `/api/v1/anmeldung/` zur Verfügung.

```json
{ "username": "user@example.org", "password": "…", "label": "Android App" }
```

Die Antwort enthält das Token einmalig. Bei Konten mit verpflichtender MFA erzwingt der Server die MFA-Regeln auch am Token-Endpunkt. Relevante Fehlercodes sind `mfa_required` und `mfa_setup_required`; der Client darf diese nicht als generischen Serverfehler behandeln.

Passwortwechsel oder expliziter Widerruf deaktivieren aktive App-Tokens entsprechend den Serverregeln.

### Token widerrufen

`DELETE /api/v1/token/` (Alias `DELETE /api/v1/anmeldung/`) deaktiviert **nur** das in `Authorization` vorgelegte Token. Der native Client ruft den Endpunkt beim Logout best-effort auf und räumt den lokalen Speicher danach in jedem Fall. Ohne Authorization antwortet der Server mit `401 auth_required`.

## Kanonischer Fehlervertrag

Fehlerantworten verwenden:

```json
{
  "ok": false,
  "error": {
    "code": "validation_error",
    "message": "…",
    "correlation_id": "…"
  }
}
```

Kanonische Codes: `validation_error`, `auth_required`, `forbidden`, `no_active_membership` (Token gültig, Mitgliedschaft entzogen – Client meldet ab), `mfa_required`, `mfa_setup_required`, `not_found`, `conflict`, `payload_too_large`, `unsupported_media_type`, `rate_limit`, `server_error`.

## Endpunkte v1

| Methode | Pfad | Zweck |
| --- | --- | --- |
| GET | `/api/v1/` | Discovery + Capabilities |
| GET | `/api/v1/openapi.yaml` | OpenAPI-Schema |
| POST | `/api/v1/token/`, `/anmeldung/` | App-Token gegen Login, MFA-Regeln gelten |
| DELETE | `/api/v1/token/`, `/anmeldung/` | Vorliegendes App-Token widerrufen |
| GET | `/api/v1/status/` | Auth-/Mitgliedschaftsstatus |
| GET | `/api/v1/me/` | Nutzer, Rolle, Station, Module |
| GET | `/api/v1/uebersicht/` | Dashboard + Wachalltag-Zähler |
| GET/POST | `/api/v1/handovers/` | Übergaben lesen/anlegen |
| GET | `/api/v1/handovers/<id>/` | Übergabe-Detail |
| POST | `/api/v1/handovers/<id>/status/` | Übergabestatus |
| GET/POST | `/api/v1/uebergaben/` … | Deutsche Handovers-Aliase |
| GET | `/api/v1/handovers/<id>/acks/` | Quittierungen lesen |
| POST | `/api/v1/handovers/<id>/ack/` | Pro Benutzer idempotent quittieren |
| GET/POST | `/api/v1/defects/` | Mängel lesen/anlegen |
| GET/PATCH | `/api/v1/defects/<id>/` | Mangel + Verlauf/Fotos lesen bzw. Metadaten ändern |
| POST | `/api/v1/defects/<id>/status/` | Mangelstatus ändern |
| GET/POST | `/api/v1/defects/<id>/attachments/` | Mängelfotos lesen/hochladen |
| GET | `/api/v1/attachments/<id>/` | Authentifiziertes Foto herunterladen |
| GET/POST | `/api/v1/assets/` | Fahrzeug-/Gerätestatus und Stammdaten |
| POST | `/api/v1/assets/<asset_id>/status/` | Status/Notiz ändern |
| GET/POST | `/api/v1/inventory/` | Schlüssel-/Poolgeräte |
| POST | `/api/v1/inventory/<item_id>/checkout/` | Ausgeben |
| POST | `/api/v1/inventory/<item_id>/checkin/` | Zurückgeben |
| GET/POST | `/api/v1/kalender/` | Termine (laufende und kommende, mit `description`) |
| GET/POST | `/api/v1/kaffeekasse/` | Kasse; `scope` = `station` (Kassenwart/Admin, Wachensaldo) oder `own` (eigene Buchungen) |
| GET | `/api/v1/checklisten/` | Checklisten + Fälligkeit |
| POST | `/api/v1/checklisten/<id>/erledigt/` | Abschluss |
| POST | `/api/v1/checklisten/<id>/abschluss/` | Client-Alias des Abschlusses |
| GET/PUT/DELETE | `/api/v1/checklisten/<id>/schedule/` | tägliche/wöchentliche/monatliche Wiederholung |
| GET | `/api/v1/reports/` | leichte Stationsauswertung |

Die vollständige, maschinenlesbare Beschreibung ist `core/api/openapi_v1.yaml` und wird unter `/api/v1/openapi.yaml` ausgeliefert.

## Wachalltag-Datenmodell

### Mängel

Mängel besitzen Titel, Beschreibung, Bezug zu Fahrzeug/Gerät, Priorität, Kategorie, Zuständigkeit, Frist und Status. Änderungen erzeugen stationsbezogene Ereignisse/Audit-Einträge. Ein identischer Statuswechsel erzeugt keinen zweiten Status-Event.

`GET /api/v1/defects/` sortiert fachlich: offen → in Bearbeitung → wartend →
erledigt, innerhalb davon dringend → wichtig → normal, dann nach Frist. Die
Liste ist paginiert:

| Parameter | Bedeutung |
| --- | --- |
| `limit` | Einträge pro Seite, 1–200, Standard 100 |
| `offset` | Startposition, Standard 0 |
| `active=1` | erledigte Mängel ausblenden |
| `status`, `priority`, `overdue=1` | Filter wie bisher |

Antwort: `{"ok": true, "count": <Gesamtzahl>, "results": [...], "next": <Pfad oder null>, "previous": <Pfad oder null>}`.
`next`/`previous` sind relative Pfade mit allen Filtern; Clients folgen ihnen,
statt selbst Offsets zu berechnen.

### Fotos

Mängelfotos sind authentifiziert und stationsisoliert. Erlaubt sind JPEG, PNG, WebP und PDF. Der Server prüft MIME/Format, Signatur und die tatsächliche Decodierbarkeit, bevor Daten persistiert werden. Grenzen (Web und API gleich):

- maximal **5 MiB je Datei** (Server); der offizielle Client verkleinert Fotos vorab auf höchstens 2 MiB
- maximal **25 Megapixel je Bild**
- maximal **8 Anhänge je Mangel**
- maximal **12 MiB Gesamtgröße je Mangel**

Die Binärdaten werden als Base64 in JSON transportiert; der HTTP-Request ist dadurch rund ein Drittel größer als die Datei. Wachbuch erlaubt standardmäßig **10 MiB** Request-Body (`DATA_UPLOAD_MAX_MEMORY_SIZE`); ein vorgeschalteter Reverse Proxy muss mindestens 8 MiB zulassen. Lehnt der Proxy vorher ab, liefert er oft HTML statt JSON – Clients werten dann den Statuscode (413) aus.

Die Limits schützen vor manipulierten/defekten Dateien, Dekompressionsrisiken und ungebremstem Datenbankwachstum. Fotos dürfen keine Patienten-/Einsatzdaten enthalten.

### Assets und Inventar

Fahrzeuge/Geräte besitzen einen operationalen Status (`ready`, `limited`, `workshop`, `oob`) mit Ereignisverlauf. Schlüssel und Poolgeräte werden transaktional ausgegeben/zurückgenommen; eine bestehende Ausgabe wird nicht still überschrieben.

### Quittierungen und Checklisten

Eine Übergabe kann pro Benutzer einmal quittiert werden. Wiederkehrende Checklisten unterstützen täglich, wöchentlich und monatlich. Nach Abschluss wird die konfigurierte Kadenz bis zur ersten Fälligkeit in der Zukunft fortgeschrieben; lange Rückstände bleiben dadurch nicht künstlich weiter überfällig.

### Reports

`/reports/` liefert nur leichte Stationsorganisation: offene/überfällige Mängel, überfällige Checks, Asset-Einsatzklarquote, ausgegebene Pools und unquittierte aktive Übergaben. Die Auswertung ist nicht für individuelle Leistungsbewertung vorgesehen.

## Scopes

Bestehende Scopes bleiben bewusst kompatibel:

`read:me`, `read:handovers`, `write:handovers`, `read:calendar`, `write:calendar`, `read:coffee`, `write:coffee`, `read:checklists`, `write:checklists`.

Wachalltag-Ressourcen nutzen aktuell die passenden Handovers-/Checklists-Scopes plus Rollen- und Stationsprüfung. Ein Scope ersetzt niemals die fachliche Rollenprüfung.

## Rate-Limits

Angemeldete Anfragen werden pro Person gezählt, nicht pro IP (alle Handys im
Wachen-WLAN teilen sich hinter NAT eine Adresse). Nur Anmeldung und
Token-Ausgabe zählen zusätzlich nach Client-IP. Eine `429`-Antwort enthält
`Retry-After` in Sekunden.

## Retry-Regeln für Clients

Clients dürfen GETs sowie nachweislich idempotente Operationen erneut senden. Nicht-idempotente Mutationen wie Token-Erzeugung, Mangelanlage, Foto-Upload, Asset-/Inventar-Stammdaten oder Checklistenabschluss dürfen bei verlorener Antwort **nicht automatisch wiederholt** werden. Checkout/Checkin, identische Statussetzung und Quittierung besitzen serverseitige Idempotenz-/Zustandsregeln.

## Offline-Lesen

Maßgeblich ist [`CLIENT-OFFLINE-CONTRACT.md`](CLIENT-OFFLINE-CONTRACT.md): Der offizielle Client darf nur die dort freigegebenen Antworten (eigene Mitgliedschaft, Aufgaben, Checklisten, Übergabeliste ohne Inhalt) verschlüsselt, an Server+Token gebunden und höchstens 24 Stunden zwischenspeichern; für Admin, Kassenwart und Auditor gar nicht. Cache-Fallback ist nur bei echten Netzwerkfehlern zulässig. `401`/`403` dürfen niemals durch alte Offline-Daten verdeckt werden.

## Betrieb

- TLS vor dem App-Port
- Authorization-Header nicht loggen
- Korrelations-ID für Support/Fehleranalyse verwenden
- Reverse Proxy für Mängelfoto-Uploads auf mindestens 3 MiB Request-Body konfigurieren
- Push-Endpunkte folgen der serverseitigen HTTPS-/Port-/Host-Allowlist
- `/healthz/` bleibt außerhalb der Produkt-API
- Backup/Restore vor Pilot-/Produktivbetrieb testen

Siehe auch [`CLIENT.md`](CLIENT.md), [`ARCHITECTURE.md`](ARCHITECTURE.md), [`ASVS-L2.md`](ASVS-L2.md) und `core/api/openapi_v1.yaml`.


## Benachrichtigungen (ab 0.24.0)

| Methode | Pfad | Zweck |
| --- | --- | --- |
| `GET` | `/api/v1/benachrichtigungen/` | persönlicher Posteingang: `unread_count`, `results[]` mit `id`, `kind`, `key`, `title`, `body`, `url`, `created_at`, `read` |
| `POST` | `/api/v1/benachrichtigungen/<id>/gelesen/` | als gelesen markieren (nur eigene) |
| `GET` | `/api/v1/fahrzeuge/sperren/` | laufende Desinfektionssperren der Fahrzeuge, die die Person besetzt: `vehicle_id`, `call_sign`, `locked_until` (ISO 8601), `key`, `title`, `body` – die App plant daraus eine lokale Erinnerung |
| `POST`/`DELETE` | `/api/v1/push/geraete/` | APNs-/FCM-Token an- bzw. abmelden (`platform`, `token`, optional `app_version`) |

Alle Endpunkte brauchen den Scope `read:me`. Fahrzeuge werden nie automatisch
freigegeben; der Hinweis fordert die Besatzung zur Prüfung und Freigabe auf.
Native Push-Zustellung: [`PUSH-RELAY.md`](PUSH-RELAY.md).
