# QR-Login: korrigierter Sicherheitsvertrag, Zustandsmaschine und G2-Grenzen

Status: **verbindliche Vorimplementierungs-Spezifikation** für G2 (2026-10-19).
Ersetzt die technisch fehlerhaften Teile von `docs/QR-LOGIN-PLAN.md`; der Plan bleibt
als Historie erhalten. Keine produktive Aktivierung, kein Commit, kein Deployment.

## 0. Korrekturen am bisherigen Plan (belegt am Code)

1. **Login-Backend.** `login(..., backend="axes.backends.AxesStandaloneBackend")` ist
   falsch. `AxesStandaloneBackend` hat keinen `get_user` und authentifiziert niemanden;
   es ist nur ein Lockout-Monitor (django-axes 8.3.1). Der verbindliche Backend-Pfad ist
   `django.contrib.auth.backends.ModelBackend`, der auch in
   `AUTHENTICATION_BACKENDS` hinter Axes steht. Die vorhandenen Stellen in
   `core/views.py::mfa_verify` und `core/account_views.py::passkey_*_verify`, die den
   Axes-Pfad an `login()` übergeben, werden in G2 auf ModelBackend korrigiert und mit
   einem Session-Persistenztest abgesichert.
2. **MFA/Freshness.** Es gibt heute kein `auth_time`. G2 führt ausschließlich
   Session-Schlüssel ein (`auth_time`, `auth_user_id`, `auth_method`), gestempelt über
   das `user_logged_in`-Signal. Bestehende Sessions ohne Stempel sind **nicht frisch**
   und dürfen nicht bestätigen (fail-closed); sie müssen sich neu anmelden.
3. **MFA-Ort.** Ein QR-Login ersetzt keine MFA. Die Bestätigung auf dem Mitarbeitergerät
   verlangt eine echte, serverseitig geprüfte frische Authentisierung:
   - MFA-Nutzer: Passwort+MFA-Login höchstens 300 s alt **oder** aktueller TOTP-Code
     **oder** frischer Passkey-Assert (≤300 s) auf der Bestätigungsseite.
   - Nutzer ohne MFA: Passwort-Session höchstens 600 s alt; sonst erneute Anmeldung.
   - Der Browser erhält nach Exchange keine neue MFA-Pflicht, weil die Faktorprüfung
     genau auf dem bestätigenden Gerät stattfand. `MFA_REQUIRED` ohne eingerichteten
     Faktor führt weiterhin zu `mfa_setup`.
4. **TOTP-Replay.** `verify_totp(valid_window=1)` akzeptiert einen Code mehrfach.
   Für QR-Bestätigungen wird der konkrete Zeitschritt zusätzlich einmalig in
   `QrTotpUse` (unique je Nutzer und Zeitschritt) verbraucht; ein zweiter Approval-
   Versuch mit demselben Code schlägt fehl. Kein globaler MFA-Umbau.
5. **Wachenbindung.** Die Wache wird bereits bei `start` serverseitig festgelegt
   (Default-Wache oder explizit übergebener, aktiver Slug) und im Datensatz gespeichert.
   Bestätigen darf nur eine aktive Mitgliedschaft **genau dieser** Wache. Damit ist
   "falsche Wache" ein echter Negativtest und keine Annahme.
6. **Logout/Widerruf.** Ein eigener Logout-View widerruft offene QR-Freigaben des
   Nutzers vor dem Session-Ende; Rollen-/Mitgliedschaftsänderungen widerrufen sie
   ebenfalls. Zusätzlich prüft der Exchange User, Mitgliedschaft, Rolle und Wache
   erneut. Ein Logout auf dem Telefon kann eine bereits **konsumierte** Browser-Session
   nicht rückwirkend beenden; das ist eine dokumentierte Grenze, keine Behauptung.
7. **Öffentliche UUID.** `login_id` ist öffentlich und kein Geheimnis. Das Secret lebt
   nur im URL-Fragment und wird vom Server nie geloggt; der Bestätigungs-POST darf es
   bewusst im Body führen. Der manuelle Ersatzcode ist ein zweites, kurzlebiges
   Possession-Merkmal, kein Passwort.

## 1. Ziel und Nicht-Ziele

Ziel: Ein bereits angemeldetes Mitarbeitergerät bestätigt eine Anmeldung an einem
zweiten Browser. Kurzlebig, einmalig, gebunden an wartende Browser-Session, Wache und
bestätigendes Konto; ausdrückliche Zustimmung; fail-closed ohne TLS.

Nicht-Ziele: dauerhafter Bearer-QR, Passwort/TOTP-Seed/Session-ID im QR, MFA-Bypass,
Cloud-Vermittlung, Offline-Client-Cache (G4), Kamera-/Hardware-Abnahme, Produktivbetrieb.

## 2. Kanäle und Geheimnisse

| Wert | Entropie | Ablage | Übertragung |
|---|---|---|---|
| `login_id` (UUID4) | 122 bit, öffentlich | DB PK | Pfad/URL, unkritisch |
| `qr_secret` | 256 bit (`secrets.token_urlsafe(32)`) | nur `sha256` in DB | URL-Fragment; im Bestätigungs-/Status-/Exchange-POST als Header/Body |
| `manual_code` | 50 bit (10 Zeichen Crockford-Base32) | nur `sha256("manual:"+code)` | Anzeige auf Warteseite; Eingabe auf Bestätigungsseite |
| `browser_nonce` | 256 bit | Session + `sha256` in DB | nie extern |
| `browser_session_hash` | – | `sha256(session_key + "|" + nonce)` | nie extern |
| `check_word` | – | aus `HMAC(SECRET_KEY, id:secret_hash)` | Anzeige auf beiden Geräten, kein Secret |

Regeln: Secret nie in Query, Pfad, Redirect, Referer, Log, Audit oder Fehlermeldung.
Vergleiche mit `hmac.compare_digest`. QR-Bild lokal per `qrcode` als PNG/Data-URI,
keine CDN-/Cloud-SDK-Abhängigkeit.

## 3. Zustandsmaschine

```
CREATED --scan/confirm-open--> SCANNED --approve(+fresh auth+possession)--> APPROVED
   |                              |                                            |
   |                              +--deny------------------------------> DENIED
   +--expire(120 s)---------------+--expire---------------------------> EXPIRED
   +--logout/role/membership------+--revoke---------------------------> REVOKED
                                                                 APPROVED --exchange--> CONSUMED
```

- Übergänge atomar per `UPDATE ... WHERE state IN (...)` (Compare-and-Set), kein
  Read-Modify-Write ohne Bedingung. Genau eine Approval und genau ein Exchange gewinnen.
- `DENIED`, `EXPIRED`, `REVOKED`, `CONSUMED` sind terminal.
- Ablauf ausschließlich serverseitig `timezone.now()`; TTL 120 s ab `created_at`.
- Status nach außen nur `pending|approved|denied|expired|revoked|consumed`; keine
  internen Fehlertexte, keine User-IDs, keine Secrets.

## 4. Datenmodell (Migration 0030)

`QrLoginRequest`:
- `id` UUID PK (public login_id)
- `secret_hash` char(64)
- `manual_code_hash` char(64)
- `browser_session_hash` char(64)
- `browser_nonce_hash` char(64)
- `station` FK Station, PROTECT
- `origin` char(255) (kanonische https-Origin)
- `state` char(16), Choices, Default `created`
- `created_at` auto_now_add, `expires_at`, `approved_at` (null), `consumed_at` (null)
- `approved_by` FK User, null, SET_NULL
- `approved_session_hash` char(64), blank (Bindung Approval-Gerät)
- `attempts` PositiveSmallInteger default 0
- `check_word` char(32)
- Indexes: (`state`, `expires_at`), (`expires_at`)

`QrTotpUse`:
- `user` FK User CASCADE
- `time_step` BigInteger
- `created_at`
- UniqueConstraint (`user`, `time_step`) – einmalige TOTP-Bestätigung je Zeitschritt.

Kein Klartext-Secret, kein Passwort, kein TOTP-Seed, kein dauerhaftes Token.

## 5. HTTP-Vertrag

Alle QR-Antworten: `Cache-Control: no-store`, `Pragma: no-cache`,
`Referrer-Policy: no-referrer`, `X-Robots-Tag: noindex`. Alle mutierenden Aufrufe:
POST + CSRF. Feature-Gate: `QR_LOGIN_ENABLED` default `False`; ohne sichere
https-Origin (`SITE_URL` https oder request.is_secure) und ohne
`QR_LOGIN_ALLOW_INSECURE_TEST_ORIGIN=True` → 404/503, kein unsicherer Fallback.

| Methode | Pfad | Auth | Zweck |
|---|---|---|---|
| GET | `/anmelden/qr/` | anonym | Warteseite, startet per JS |
| POST | `/anmelden/qr/start/` | anonym + Session + CSRF | Request + QR-URL + manual_code einmalig |
| GET | `/anmelden/qr/<uuid>/` | anonym | Warteseite (Fragment bleibt clientseitig) |
| POST | `/anmelden/qr/<uuid>/status/` | Session-Bindung + `X-QR-Secret` | Polling, max. 1/s clientseitig |
| GET | `/anmelden/qr/<uuid>/bestaetigen/` | login + aktive Mitgliedschaft | Bestätigungsseite |
| POST | `/anmelden/qr/<uuid>/bestaetigen/` | + CSRF + Frische + Possession (`qr_secret` **oder** `manual_code`) | Approval |
| POST | `/anmelden/qr/<uuid>/ablehnen/` | + CSRF | Ablehnung |
| POST | `/anmelden/qr/<uuid>/bestaetigen/passkey/optionen/` | login + Mitgliedschaft | Passkey-Reauth-Optionen |
| POST | `/anmelden/qr/<uuid>/bestaetigen/passkey/pruefen/` | login + Mitgliedschaft | Passkey-Reauth-Assert |
| POST | `/anmelden/qr/<uuid>/exchange/` | Session-Bindung + `X-QR-Secret` + CSRF | einmaliger Login |

`start`-Antwort (JSON): `{ok, login_id, qr_url, check_word, manual_code, expires_in}`.
`status`-Antwort: `{ok, state}`. `exchange`-Antwort: `{ok, redirect}`.
Fehler: feste Codes (`qr_disabled`, `qr_expired`, `qr_invalid`, `qr_forbidden`,
`qr_rate_limited`, `qr_conflict`) mit passendem HTTP-Status (403/404/409/410/429/503),
nie Secret oder fremde Daten im Body.

## 6. Rate-Limits

Über `core.rate_limit.consume` (DB, multi-worker-fähig), getrennte Buckets:
`qr_start` (10/300 s je IP), `qr_status` (120/120 s je Session+Login),
`qr_approve` (10/60 s je Nutzer+Login), `qr_exchange` (10/60 s je Session+Login).
Grenzen als `settings.QR_LOGIN_RATE_LIMITS` überschreibbar (Tests), Produktionswerte
nicht lockern. 429 ohne Retry-Leak.

## 7. Session- und Login-Policy

- `start`: Session-Key sicherstellen (`session.save()`), Nonce je `login_id` in
  `session["qr_browser_nonces"]`; DB speichert nur Hashes.
- `exchange`: Session-Bindung + Secret erneut prüfen, dann CAS `APPROVED→CONSUMED`.
  Danach User/Mitgliedschaft/Rolle/Wache erneut laden; bei Ungültigkeit 403 und
  `REVOKED`, kein Login.
- `login(request, user, backend="django.contrib.auth.backends.ModelBackend")`;
  `login()` rotiert den Session-Key (Session-Fixation). `auth_time`, `auth_user_id`,
  `auth_method="qr"` stempeln; `qr_browser_nonces`-Eintrag und Pending-Keys löschen.
- `MFA_REQUIRED` + kein bestätigter Faktor → Redirect `mfa_setup` (wie bestehende Policy).
- Kein neues Backend, keine neue Session-Policy, keine gemeinsam genutzten Konten.

## 8. Audit und Cleanup

Audit-Aktionen: `qr_login.created`, `qr_login.approved`, `qr_login.denied`,
`qr_login.consumed`, `qr_login.revoked`, `qr_login.expired`. Metadata nur
`login_id`-Präfix (8 Zeichen), `state`, `origin_host`, `station_id`, `role`;
**kein** Secret, Code, Session-Key oder vollständiger Origin mit Pfad.

Management-Command `qr_login_cleanup`: löscht terminale Einträge älter 24 h und
`QrTotpUse` älter 24 h; dry-run-fähig, keine Cron-Anlage in G2.

## 9. UI (positiv nutzbar, nicht nur API)

- Login-Seite: sichtbarer Link/Button „Mit QR-Code anmelden" nur wenn Gate offen.
- Warteseite `/anmelden/qr/`: lokal gerendertes QR-Bild, Ablaufanzeige, Prüfwort,
  manueller 10-Zeichen-Code, Statusmeldungen per Live-Region, „Erneut versuchen".
- Bestätigungsseite: Wachename, Zielkonto, Origin-Host, Prüfwort, Restzeit,
  „Anmeldung bestätigen"/„Ablehnen"; TOTP-Feld nur wenn nötig; Passkey-Button nur
  wenn verfügbar; verständliche Fehler bei Kamera-/Berechtigungsproblemen.
- Optionales Kamera-Scannen ist progressive Enhancement; der manuelle Code ist
  Pflichtersatz. Keine Behauptung, eine echte Kamera sei getestet.
- Alle Assets lokal (`core/static/core/...`), CSP-konform, keine Inline-Skripte,
  `textContent` statt `innerHTML` für dynamische Werte.

## 10. Abnahmematrix G2 (mindestens)

Positiv: Start→Scan→Approve (TOTP frisch; Passkey frisch; Nicht-MFA frisch)→Exchange→
eingeloggt mit richtiger Wache/Rolle; Ablehnung; manueller Code; Status ohne Secret;
Session-Key vor/nach Exchange unterschiedlich.

Negativ (je eigener Test): Replay von Secret und login_id nach CONSUMED (409/410);
fremde Browser-Session (403); falsche Wache/Fremdmitgliedschaft/inaktive Mitgliedschaft
(403/404); fehlende/veraltete Frische (403); TOTP-Replay (403); fehlendes/falsches CSRF
(403); Rate-Limit (429); abgelaufen bei 119 s/121 s mit kontrollierter Uhr; Rollen-/
Mitgliedschaftsentzug zwischen Approval und Exchange (403, REVOKED); Logout widerruft
offene Freigabe; Secret fehlt in Response, Logs, Audit, Redirect, Referer; QR-Status
liefert keine User-/Secret-Daten; parallele Approvals/Exchanges: genau einer gewinnt;
Scanner≠Bestätiger (fremder Nutzer kann keine fremde Session übernehmen).

## 11. Datei-Allowlist G2

Neu: `core/qr_login.py`, `core/qr_login_views.py`, `core/auth_session.py`,
`core/migrations/0030_qrloginrequest_qrtotpuse.py`,
`core/management/commands/qr_login_cleanup.py`, `core/test_qr_login.py`,
`templates/registration/qr_wait.html`, `templates/registration/qr_confirm.html`,
`core/static/core/qr_login.js`, `core/static/core/qr_login.css`,
`docs/QR-LOGIN-SECURITY-CONTRACT.md`.

Geändert: `core/models.py` (nur neue Modelle), `config/urls.py` (QR-Routen,
Logout-View), `core/auth_views.py` (Link-Flag), `core/views.py` (Backend-Korrektur,
Logout-Hook nur falls nötig), `core/account_views.py` (Backend-Korrektur),
`core/apps.py` (Signal-Registrierung), `config/settings.py`
(`QR_LOGIN_ENABLED`, `QR_LOGIN_RATE_LIMITS`, TTL), `templates/registration/login.html`,
`templates/registration/mfa_verify.html` (nur falls Backend-Fix sichtbar),
`core/static/core/app.js` (QR-Button-Verdrahtung nur falls nötig).

Nicht ändern: bestehende Migrationen 0028/0029, Produktionsschutz, MFA-Policy,
WebAuthn-Verifikation, `docs/ROADMAP-OFFENE-BAUSTELLEN.md` (Parent), Evidence-Bäume.

## 12. Harte Grenzen

- Keine Commits/Pushes/Deployments durch den Implementierer.
- Keine echten personenbezogenen Daten, keine WAN-Abschaltung.
- Physische iPhone-/Kamera-/TLS-Abnahme bleibt offen und wird nicht simuliert.
- Ein grüner Testlauf ist keine Produktionsfreigabe.

## 13. Nachschärfung nach Review 2026-10-19 (Q1–Q4)

Diese Regeln präzisieren Abschnitte 0.2, 0.3, 0.7, 1 und 7 verbindlich; sie
lockern keine bestehende Anforderung.

1. **QR ist kein Primärnachweis (Q1).** Eine Session mit `auth_method="qr"`
   gilt niemals als frische Authentisierung für eine QR-Bestätigung – weder
   für MFA-Nutzer (300 s) noch für Nutzer ohne MFA (600 s). Nach einem
   Exchange darf dieselbe Session daher keine weitere QR-Anmeldung
   bestätigen; erforderlich sind TOTP oder ein an genau diese `login_id`
   gebundener Passkey-Assert. Eine Rotation des Session-Tokens verlängert
   keine Primärcredential-Frische. Zusätzlich darf die Session, die einen
   `QrLoginRequest` gestartet hat (`verify_browser_session`), ihn nicht selbst
   bestätigen (403 `qr_forbidden`); Bestätiger und wartender Browser sind
   getrennte Sessions.
2. **TLS fail-closed (Q2).** `SITE_URL` mit `https://` belegt keinen sicheren
   Transport. `get_canonical_origin` liefert nur bei `request.is_secure()`
   oder – ausschließlich bei explizit `TRUSTED_PROXY=True` – bei
   `X-Forwarded-Proto: https` (erster Wert) einen Origin. Andernfalls bleibt
   das Gate geschlossen (`None`, 503/404), außer
   `QR_LOGIN_ALLOW_INSECURE_TEST_ORIGIN=True` ist bewusst gesetzt.
3. **TOTP-Verbrauch nur bei gültigem Übergang (Q3).** Der TOTP-Zeitschritt wird
   erst nach bestandener Zustands-/Ablaufprüfung und gemeinsam mit dem
   Approval-CAS in einer Transaktion verbraucht. Abgelaufene (410) oder
   terminale (409) Anforderungen sowie verlorene CAS-Rennen erzeugen keine
   `QrTotpUse`-Zeile; ein bereits verbrauchter Zeitschritt rollt das Approval
   zurück. Kein Migrationsschritt.
4. **Passkey-Reauth transaktionsgebunden (Q4).** Challenge und
   Reauth-Zeitstempel sind an genau eine gültige, offene `login_id` derselben
   aktiven Wache gebunden. Die Challenge wird vor jeder Assertion-Prüfung aus
   der Session entfernt (einmalig, auch bei Fehlversuch). Options und Verify
   sind über `qr_passkey` rate-limitiert; unbekannte `login_id` → 404,
   abgelaufen → 410, terminal → 409, fremde Wache → 403.
