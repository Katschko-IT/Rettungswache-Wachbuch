# SETUP-WIZARD-PLAN — Schreibvertrag und Abnahme (2026-10-19)

Status: **Entwurf vor Implementierung, vom Implementierer eigenständig fortgeschrieben.**
Kein Commit, kein Push, kein Deployment. Arbeitsbaum ausschließlich
`/opt/data/workspace/wachbuch-umlaute-pages-20261019`.

## 1. Ziel und Produktgrenze

Sicherer Erstinstallations-Wizard für genau eine Wache:

1. Wachendaten: Name, Organisationsprofil, Mitarbeiterzahl (Größe), Anschrift.
2. Optional: 5-Tage-Wetter am Wachenstandort über Open-Meteo, nur nach ausdrücklicher
   Einwilligung zur Übermittlung der Anschrift (Geocoding).
3. Genau ein Bootstrap-Administratorkonto, danach persönliche Mitarbeiterkonten mit
   Einmal-Aktivierungslink und QR (kein dauerhafter QR-Zugangsschlüssel).

Keine Patienten-, Einsatz-, Alarmierungs-, Diagnose- oder Leistungsdaten. Keine
erfundenen Behörden-, Rechts- oder Produktionsdaten.

## 2. Bootstrap-Autorisierung (kein first-user-wins)

- Autorisierung ausschließlich über serverseitig konfiguriertes Geheimnis
  `SETUP_BOOTSTRAP_TOKEN` (Umgebungsvariable, niemals in Repo/Log/HTML).
- Ist die Variable leer oder fehlt sie, ist `/setup/` **fail-closed nicht vorhanden**
  (HTTP 404) — unabhängig von Datenbankzustand.
- Vergleich über `hashlib.sha256` + `secrets.compare_digest` (keine Timing-Offenbarung,
  kein Klartextvergleich).
- Fehlversuche: rate-limited (`core.rate_limit.consume`, Bucket `setup_bootstrap`,
  Limit 5 / 15 min pro Client-IP). Zusätzlich Zeitfenster in der Session (10 min)
  nach erfolgreicher Tokenprüfung.
- Kein anonymer „erster registrierter Benutzer wird Admin“-Pfad. `REGISTRATION_ENABLED`
  bleibt davon unberührt und schaltet **keinen** Admin frei.

## 3. Einmaliger, atomarer Abschluss

- Singleton `InstallationSetup` (pk=1, CheckConstraint) hält `completed_at`,
  `station`, `completed_by`, `bootstrap_fingerprint` (SHA-256-Hex des benutzten Tokens,
  nie der Rohwert).
- Abschluss in **einer** Transaktion:
  1. bedingtes Claim-Update
     `InstallationSetup.objects.filter(pk=1, completed_at__isnull=True).update(...)`
     → `rowcount == 0` bedeutet „bereits abgeschlossen“ → HTTP 409, keine Ressourcen.
  2. Station + Admin-Benutzer + Membership + Audit erst nach erfolgreichem Claim.
  3. Jede spätere Ausnahme rollt Claim und Ressourcen gemeinsam zurück.
- Parallelität ehrlich getrennt:
  - **SQLite:** `SELECT … FOR UPDATE` ist ein No-op; die Einmaligkeit stützt sich auf
    das bedingte UPDATE plus Transaktion (Write-Lock). Ein echter Nebenläufigkeitstest
    läuft nur mit PostgreSQL; unter SQLite wird das als Skip ausgewiesen, nicht als
    grüner Lock-Nachweis.
  - **PostgreSQL:** zusätzlich `select_for_update()` auf der Singleton-Zeile.
- Nach Abschluss liefert `/setup/` dauerhaft 404/410 — auch mit gültigem Token.

## 4. Wachendaten und Wetter

Neue `Station`-Felder (additiv, bestehende Datenverträge unverändert):
`employee_count`, `street`, `postal_code`, `city`, `latitude`, `longitude`,
`timezone_name`, `weather_enabled`.

- Wetter ist **optional** und niemals Setup-Blocker. Jeder Fehler (Timeout, HTTP,
  ungültige Antwort) führt zu einem sichtbaren Hinweis und einem leeren Wetterblock.
  Wird die Wetteranzeige aktiviert, aber keine Vorschau geladen, verlangt der
  Abschluss eine ausdrückliche Entscheidung (Vorschau laden oder Wetter abwählen);
  die Installation bleibt ohne Wetter jederzeit abschließbar.
- Kein privater/benutzerdefinierter Geo-Endpunkt. Feste Allowlist:
  `https://geocoding-api.open-meteo.com/v1/search` und
  `https://api.open-meteo.com/v1/forecast`, nur HTTPS, kein Redirect-Follow,
  Timeout 3 s, Response-Größenlimit. Die Allowlist prüft Hostname und Schema;
  eine Auflösung/Prüfung der aufgelösten IP-Adressen (DNS-Rebinding-Schutz auf
  IP-Ebene) ist ausdrücklich **nicht** Teil der Zusage.
- Ohne `weather_enabled` **und** ohne separate Bestätigung `geo_consent` wird keine
  Anschrift an einen externen Dienst gesendet. Erst nach Bestätigung wird geocodiert;
  die Koordinaten werden gespeichert, die Anschrift nicht erneut extern übermittelt.
- Genau **5 lokale Kalendertage**, `timezone=<station.timezone_name>`
  (nur die im Formular angebotenen, via `zoneinfo` validen Zonen),
  `forecast_days=5`; Cache 60 min pro Koordinate. Wetterfehler werden nicht gecacht.
  Zusätzlich existiert eine getrennte, auf 12 h begrenzte Stale-Kopie mit
  Original-Abrufzeit; sie wird nur bei Abruffehler und nur mit `stale=True`,
  Abrufzeit und Alter angezeigt. Liegt der erste Tag nicht mehr in der lokalen
  Gegenwart, wird sie verworfen statt als „nächste fünf Tage“ ausgegeben.
- Live-Prüfung ausschließlich mit **synthetischen Beispielkoordinaten**
  (52.2787/8.0479) und als synthetisch gekennzeichnet.

## 5. Mitarbeiterkonten und Aktivierung

- Admin legt Konto ohne Passwort an (`is_active=False`, unusable password) und
  erzeugt `EmployeeActivation`:
  - RohToken `secrets.token_urlsafe(32)`, nur einmal in Antwort/QR sichtbar;
  - DB speichert **nur** `token_hash` (SHA-256) und `token_prefix` (8 Zeichen);
  - `expires_at` = +7 Tage, widerrufbar (`revoked_at`), einmalig (`used_at`).
- Aktivierung: `/aktivieren/<token>/`
  - GET: Hinweis + Formular „Passwort selbst setzen“ (Django-Passwortvalidatoren),
    `Cache-Control: no-store`, `Referrer-Policy: no-referrer`.
  - POST: CSRF-Pflicht. Einmal-Verbrauch über bedingtes UPDATE
    (`used_at__isnull=True`, `revoked_at__isnull=True`, `expires_at__gt=now`);
    `rowcount == 0` → 410. Danach Passwort setzen, `is_active=True`, Audit **ohne**
    Token, Session nicht anmelden → Weiterleitung auf `/anmelden/`.
  - Abgelaufen/widerrufen/verbraucht/fremde Wache: 410, keine Preisgabe von Details.
- Kein Klartextpasswort und kein Token in Audit, Logs, Fehlermeldungen oder
  dauerhaft in der Datenbank. QR enthält **nur** den einmaligen Aktivierungslink,
  keine dauerhaften Zugangsdaten.
- MFA bleibt unangetastet: Aktivierung meldet nicht an; der normale Login inkl.
  MFA-/Passkey-Pflicht greift danach unverändert.

## 6. Wiederholbarer QR-Login — Entscheidung

**Nicht implementiert, ausdrücklich Restpunkt.** Begründung: ein wiederholbarer
QR-Login benötigt ein kurzlebiges Einmal-Challenge-Objekt plus bereits
authentifizierte Gerätebestätigung; ein dauerhaft gültiger QR-Schlüssel wäre ein
Umgehungsweg an MFA/Passwort vorbei. Spezifikation für eine spätere Etappe:

1. Bereits angemeldetes Gerät A erzeugt `QrLoginChallenge` (128-bit Zufall,
   `challenge_hash` serverseitig, TTL ≤ 60 s, single-use, an `user` + `station`
   gebunden).
2. Gerät B (scanner) POSTet die Challenge **nur zusammen mit einem bereits
   authentifizierten, MFA-bestätigten** Session-Kontext; ohne diesen Kontext 403.
3. Verbrauch atomar per bedingtem UPDATE; jede Challenge ist einmalig.
4. Kein QR-Inhalt, der allein als Zugangsschlüssel dient; keine Speicherung von
   Roh-Challenge oder Session-Token; Audit ohne Challenge-Wert.
5. Testpflichten: Replay, TTL-Ablauf, fremde Wache, fehlende MFA, paralleler
   Doppelverbrauch.

Bis dahin existiert **kein** Endpunkt für wiederholbaren QR-Login; der bestehende
`mobile_setup_qr` zeigt nur die Server-Origin und enthält keine Zugangsdaten.

## 7. Datei-Allowlist dieses Slices

Neu:
- `core/setup_wizard.py` (Bootstrap-/Aktivierungs-Services)
- `core/setup_views.py` (Setup-, Aktivierungs- und Einladungs-Views)
- `docs/OFFLINE-BETRIEB.md` (LAN-/WAN-Ausfall, Prüfgates, offene Grenzen)
- `core/weather.py` (Open-Meteo-Client, Allowlist, Cache, 5 Tage)
- `core/test_setup_wizard.py`
- `templates/core/setup_wizard.html`, `setup_confirm.html`, `activate_account.html`,
  `team_invite.html`, `team_invites.html`
- `docs/SETUP-WIZARD-PLAN.md` (diese Datei)

Geändert:
- `core/models.py` (Station-Felder, `InstallationSetup`, `EmployeeActivation`)
- `core/forms.py` (Setup-/Aktivierungs-/Invite-Formulare)
- `core/views.py` (Setup- und Invite-Views)
- `core/urls.py`, `config/urls.py`
- `core/migrations/00XX_*.py` (eine neue Migration)
- `templates/core/more.html` (nur Admin-Link auf Einladungen, falls passend)
- `docs/NEXT-STAGES.md`, `docs/FUNKTIONSMATRIX-20261019.md`, `site/README.md`

Nicht geändert: bestehende Auth-/MFA-/Passkey-Logik, `mobile_setup_qr`, Rollen- und
Station-Grenzen, Produktionskonfiguration, fremde Arbeitsbäume.

## 7a. Offline-/WAN-Ausfall (harte Anforderung, ergänzt 2026-10-19)

- Wizard, Passwortlogin, MFA, Rollenprüfung, Aktivierung und QR-Erzeugung
  benötigen **keine** Internetverbindung; Assets sind lokal.
- Wetter/Geocoding sind strikt optional, werden nie beim Abschluss aufgerufen,
  haben 3 s Timeout, Circuit Breaker und einen Cache mit Abrufzeit/Alter.
  Bei fehlgeschlagener Aktualisierung werden nur echte alte Werte als
  „veraltet“ gezeigt, niemals Dummy-Livewerte.
- Adresse wird lokal gespeichert; kein erzwungener Geocoder.
- Getestet mit verweigerten DNS-/HTTP-Aufrufen (`socket.getaddrinfo`,
  `urllib.request.urlopen` → `OSError`) bei erreichbarem lokalem Testclient.
- **Nicht** bewiesen: vollständig getrenntes Handy oder Serverausfall
  (Client-Offlinecache/Outbox/Sync-Konflikte). Siehe `docs/OFFLINE-BETRIEB.md`.
- Kein Tailscale-/Internetzwang; lokale HTTPS-/Origin-Konfiguration ist
  dokumentierte Voraussetzung, Authschutz wird nicht abgeschaltet.

## 8. Abnahmekriterien (negative Tests zuerst)

| ID | Kriterium | Nachweis |
|---|---|---|
| S1 | Setup ohne konfiguriertes Token → 404 | HTTP-Test |
| S2 | Falsches Token → 403 + Rate-Limit | HTTP-Test, `RateLimit`-Zähler |
| S3 | Doppelabschluss → 409, keine zweite Station/Membership | Service-/HTTP-Test |
| S4 | Setup nach Abschluss → 404/410, auch mit Token | HTTP-Test |
| S5 | Admin-Konto genau einmal, Rolle `admin`, gleiche Station | DB-Assertion |
| S6 | Aktivierung: Token nur als Hash, Rohwert nicht in DB/Audit/Log | DB-/Log-Assertion |
| S7 | Replay/abgelaufen/widerrufen/fremde Wache → 410 | HTTP-Tests |
| S8 | POST ohne CSRF → 403 | HTTP-Test |
| S9 | Passwort wird vom Mitarbeiter gesetzt; Login danach möglich; MFA nicht umgangen | HTTP-Test |
| S10 | Wetterfehler blockiert Setup nicht | gemockter Client |
| S11 | Ohne `geo_consent` kein externer Aufruf (Double nie aufgerufen) | Negativ-Assertion |
| S12 | 5 lokale Tage, Cache, HTTPS-Allowlist, keine private IP | Unit-Tests |
| S13 | Kein wiederholbarer QR-Login-Endpunkt vorhanden | URL-Resolver-Test |
| S14 | `makemigrations --check` ohne Änderungen, volle Suite grün | Kommando-Log |
| S15 | Setup/Login/Aktivierung bei verweigertem DNS+HTTP | `WanOutageTests` |
| S16 | Wetter beim Abschluss nie aufgerufen; Fehler blockiert nicht | Mock-Assertion |
| S17 | Aktivierungstoken im App-Log redigiert | `assertLogs` |

## 9. Sichere Defaults bei offenen Fragen

- Kein Nutzer-Dialog verfügbar: Token-basierte Bootstrap-Autorisierung statt
  first-user-wins; Wetter standardmäßig **aus**; Aktivierungslink 7 Tage;
  keine automatische Anmeldung nach Aktivierung; QR-Login bleibt Restpunkt.
- Diese Entscheidungen schwächen keine bestehende Schutzgrenze ab.

## 10. Rollen

- Plan-Gegenprüfung: AGY (read-only) + Mistral (`api.mistral.ai/v1`), echte Läufe.
- Implementierung: ein Implementierer (Hermes-Worker) in genau diesem Baum.
- Unabhängiges Diffreview nach Implementierung: AGY + Mistral gegen den echten Diff.
- Finaler Argon-Review: **nicht** vom Worker; Parent friert den Stand ein.


## 11. Ergebnisse der Plan-Gegenprüfung (echte Läufe)

- **Mistral** (`mistral-large-latest`, HTTP 200, `finish_reason=stop`):
  5 Hinweise. Übernommen: kein `token_prefix` in der DB (nur Hash), CSRF-Token
  im Aktivierungsformular, MFA-Test nach Aktivierung, SSRF-Antwortvalidierung,
  expliziter Doppel-Claim-Test. Nicht als Fehler übernommen: „CSRF fehlt im
  GET-Formular“ (Token wird im Template gesetzt) und „CSRF fehlt in
  `setup_weather_preview`“ (globale `CsrfViewMiddleware`; per Test belegt).
- **AGY** (`gemini-3.8-flash-medium`, read-only): Planlauf vollständig,
  Ergebnis `KEINE_BEFUNDE`. Diffreview-Läufe: erster Lauf Timeout ohne Ausgabe,
  zweiter Lauf durch Gemini-Filter blockiert. Beides wird **nicht** als Befund
  gewertet; die Diffreview-Abdeckung stützt sich auf Mistral plus Tests.

## 12. Ergebnisse des echten Diffreviews

Mistral-Diffreview (`evidence/diff-review-mistral-wizard.json`, HTTP 200,
`model_reported=mistral-large-latest`, `finish_reason=stop`) meldete 5 Punkte:

| Befund | Bewertung |
|---|---|
| Race in `complete_setup` | **abgelehnt**: das bedingte UPDATE ist das alleinige Gate; Verlierer erzeugt keine Ressourcen. PostgreSQL serialisiert zusätzlich über `select_for_update`, SQLite über den Write-Lock. |
| CSRF in `setup_weather_preview` fehlt | **abgelehnt**: Middleware erzwingt CSRF; neuer Test S8b belegt 403 ohne Token. |
| Session-Fixation/TTL | **teilweise übernommen**: `cycle_key()` nach Tokenprüfung; selektives Entfernen der Setup-Keys; TTL 600 s bleibt. |
| Längenprüfung bei `compare_digest` | **abgelehnt**: beide Seiten sind SHA-256-Hex (konstante Länge); leere Eingabe → `False`. |
| Rate-Limit auf Admin-Einladungen | **abgelehnt**: admin-only, CSRF-geschützt, auditiert; kein Schutzgewinn gegen das Bedrohungsmodell. |
