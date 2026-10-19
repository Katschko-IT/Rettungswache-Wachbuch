# QR-Login: Sicherheitsvertrag, Zustandsmaschine und Integrationsplan

Status: **Planung (Phase 1 / G2-Vorbereitung)**. Keine Implementierung, keine Migration, keine UI in diesem Schritt.
Grundlage: `core/auth_views.py`, `core/views.py` (`mfa_verify`), `core/account_views.py` (Passkey-Login),
`core/mfa.py`, `core/webauthn_auth.py`, `config/settings.py`, `docs/SECURITY-PRIVACY.md`, `docs/ASVS-L2.md`.

## 1. Ziel und Nicht-Ziele

Ziel: Ein bereits angemeldetes Mitarbeitergerät (Telefon/Tablet) bestätigt eine Anmeldung an einem
zweiten Browser, ohne Passwort oder dauerhaftes Token im QR-Code. Der Vorgang ist kurzlebig,
einmalig, an Browser-Sitzung, Wache und Mitarbeiter gebunden und fail-closed.

Nicht-Ziele (ausdrücklich):

- Kein dauerhafter Bearer-QR, kein QR als Passwortersatz, kein Generalschlüssel.
- Keine Passwörter, TOTP-Seeds, Session-IDs oder API-Tokens im QR oder in der URL-Query.
- Kein MFA-Bypass: der QR ersetzt weder TOTP noch Passkey, er löst sie nicht aus.
- Kein genereller Offline-Client-Cache (das bleibt G4, separater Architektur-Slice).
- Keine Kamera-/Hardware-Abnahme in Phase 1; kein Produktiv-Deployment.

## 2. Vorhandene Bausteine (Bestandsaufnahme)

| Baustein | Ist-Zustand | Nutzung im QR-Flow |
|---|---|---|
| Passwort-Login | `PasswordLoginView`; bei bestätigter MFA nur `mfa_pending_user_id` in Session, danach `mfa_verify` | QR ersetzt diesen Schritt nicht; Session wird erst nach vollständiger Faktorprüfung erzeugt |
| TOTP | `TotpDevice`, `verify_totp(valid_window=1)`, 8 Fehlversuche | frische Re-Authentifizierung auf dem Bestätigungsgerät |
| Passkey | `WebAuthnCredential`, `authentication_options`, `verify_authentication`, RP-ID/Origin Pflicht | bevorzugte frische Re-Auth auf dem Telefon |
| Session | `cached_db`/`db`, `SESSION_COOKIE_AGE=12h`, `SameSite=Lax`, `Secure` bei `SECURE_COOKIES` | Browser- und Telefon-Session strikt trennen; `cycle_key()` vor Login |
| CSRF | Django-CSRF, `CSRF_COOKIE_HTTPONLY=True`, `SameSite=Lax` | Approval und Exchange nur per POST mit CSRF |
| Rate-Limit | `core.rate_limit.consume` (DB, fensterbasiert) | alle QR-Endpunkte begrenzen |
| Logs | `ActivationRedactingFormatter`, `RedactingGunicornLogger` | QR-Geheimnis darf nie in Query/Pfad stehen; zusätzlich redigieren |
| Origin | `SITE_URL`, `ALLOWED_HOSTS`, `SECURE_PROXY_SSL_HEADER` | QR-URL nur aus kanonischer HTTPS-Origin |

Lücke: Es gibt noch kein `auth_time`/Freshness-Attribut in der Session. Der Plan führt es ein
(nur Session-Key, keine Migration), damit „frisch authentifiziert" prüfbar ist.

## 3. Sicherheitsvertrag (verbindlich)

1. **Zwei Geheimnisse, getrennte Kanäle.** QR enthält `login_id` (öffentliche UUID) und ein
   256-Bit-`qr_secret` ausschließlich im URL-Fragment (`#…`). Fragmente werden nicht an den Server
   gesendet, nicht in Access-Logs/Referer übertragen. Server speichert nur `sha256(qr_secret)`.
2. **Kein Login durch Scan.** Der Scan allein authentifiziert niemanden. Erst die ausdrückliche
   Bestätigung auf einem bereits authentifizierten Gerät erzeugt eine Freigabe.
3. **Bindung an die wartende Browsersitzung.** Der Status-/Exchange-Aufruf benötigt dasselbe
   Session-Cookie und denselben in der Session gespeicherten `qr_browser_nonce`. Ein Angreifer mit
   kopiertem QR kann die Anmeldung nicht auf seinen Browser umleiten.
4. **Bindung an Wache und Rollen.** Bestätigen darf nur eine aktive Mitgliedschaft derselben Wache;
   die Mitgliedschaft wird bei Approval **und** Exchange erneut geprüft (Widerruf/Rollenwechsel).
5. **Ausdrückliche Zustimmung.** Die Bestätigungsseite zeigt Origin-Host, Wachename, Zielkonto und
   einen aus der Challenge abgeleiteten Prüfwort-Code. Bestätigung nur per POST + CSRF, nie per GET.
6. **Frische Re-Authentifizierung.** Hat der bestätigende Nutzer MFA, muss er auf dem Telefon
   innerhalb von 300 s einen Passkey-Assert oder TOTP-Code vorlegen. Ohne MFA genügt eine
   Passwort-Session, die höchstens 10 Minuten alt ist (`auth_time`). Kein stilles Überspringen.
7. **Einmaligkeit und Ablauf.** `login_id` ist einmalig, `qr_secret` einmal verwendbar,
   Gültigkeit 120 s, maximal eine Freigabe, maximal ein Exchange. Danach `CONSUMED`.
8. **Session-Fixation.** Vor `login()` immer `cycle_key()`; alle `qr_*`- und `mfa_*`-Pending-Keys
   werden entfernt; CSRF-Token rotiert.
9. **Fail-closed.** Feature-Flag `QR_LOGIN_ENABLED` default `False`. Ohne HTTPS-`SITE_URL`,
   gültige `WEBAUTHN_ORIGIN`/RP-ID und sichere Cookies wird der Flow nicht angeboten (404/503),
   nicht etwa ungesichert fortgesetzt. Kein Fallback auf HTTP, keine Cloud-vermittelte Challenge.
10. **Keine Geheimnisse in Logs.** Kein `qr_secret` in Query, Pfad, Fehlermeldung oder Audit-Payload.
    Audit enthält nur `login_id`-Präfix, Wache, Ergebnis, Zeit, User-ID.
11. **Kein MFA-Bypass, keine geteilten Konten.** Jede Freigabe ist an genau ein Nutzerkonto und
    ein Gerät gebunden; keine Gruppenfreigabe, kein „Admin bestätigt für alle".
12. **Rate-Limits und Widerruf.** Create/Status/Approve/Exchange sind getrennt limitiert; offene
    Requests werden bei Logout, Rollenentzug oder Wachen-Deaktivierung ungültig.

## 4. Zustandsmaschine

```
CREATED ──scan/open──> SCANNED ──approve(+fresh auth)──> APPROVED ──exchange──> CONSUMED
   │                      │                                  │
   │                      ├──deny────────────────────────────┴──> DENIED
   ├──expire(120s)────────┴──expire───────────────────────────────> EXPIRED
   └──revoke(logout/role/membership)──────────────────────────────> REVOKED
```

Regeln:

- Übergänge sind atomar per `UPDATE … WHERE state=<erwartet>` (Compare-and-Set), damit parallele
  Approvals/Exchanges nicht doppelt gewinnen.
- `APPROVED` ist nur für die gebundene Browser-Session und nur einmal exchangebar.
- `DENIED`, `EXPIRED`, `REVOKED`, `CONSUMED` sind terminal; Status liefert nur `ok/expired/denied`.
- Ein zweiter Scan ändert `CREATED → SCANNED` idempotent, aber nie `APPROVED → SCANNED`.
- Zeitvergleich ausschließlich serverseitig (`timezone.now()`), keine Client-Zeit.

## 5. Datenmodell (Plan, noch nicht migriert)

`QrLoginRequest`:

| Feld | Typ | Zweck |
|---|---|---|
| `id` | UUID PK | öffentliche `login_id`, kein Geheimnis |
| `secret_hash` | char(64) | SHA-256 des Fragment-Geheimnisses |
| `browser_session_hash` | char(64) | Bindung an wartende Session (Hash des Session-Keys) |
| `browser_nonce` | char(64) | zusätzliche Session-Bindung, nur in Session + DB-Hash |
| `station_id` | FK, nullbar | optional vorab gewählte Wache; sonst bei Approval gesetzt |
| `state` | choices | siehe Zustandsmaschine |
| `created_at`, `expires_at`, `approved_at`, `consumed_at` | datetime | Ablauf/Audit |
| `approved_by_id` | FK User, nullbar | bestätigender Mitarbeiter |
| `origin` | char(255) | kanonischer Origin zum Anzeigen/Prüfen |
| `attempts` | int | Fehlversuche/Diagnose, hart begrenzt |

Kein Klartext-Secret, kein Passwort, kein TOTP-Seed, kein dauerhaftes Token. Cleanup löscht
terminale Einträge nach 24 h (Management-Command, kein Cron in Phase 1).

## 6. Endpunkte (Plan)

| Methode | Pfad | Auth | CSRF | Zweck |
|---|---|---|---|---|
| POST | `/anmelden/qr/start/` | anonym + Session | ja | Request erzeugen, QR-Daten einmalig zurückgeben |
| GET | `/anmelden/qr/<uuid>/` | anonym | – | Warteseite, liefert nur Status, `no-store`, `no-referrer` |
| POST | `/anmelden/qr/<uuid>/status/` | Session-gebunden + Secret-Header | ja | Polling (max. 1/s, 120 s) |
| GET | `/anmelden/qr/<uuid>/bestaetigen/` | aktive Mitgliedschaft | – | Bestätigungsseite mit Prüfwort |
| POST | `/anmelden/qr/<uuid>/bestaetigen/` | aktive Mitgliedschaft + frische Re-Auth | ja | ausdrückliche Freigabe |
| POST | `/anmelden/qr/<uuid>/ablehnen/` | aktive Mitgliedschaft | ja | Ablehnung |
| POST | `/anmelden/qr/<uuid>/exchange/` | Session-gebunden + Secret | ja | einmaliger Login, `cycle_key()` |

`qr_secret` wird ausschließlich im JSON-Body/Header übertragen, nie in Query oder Pfad.
Die Warteseite enthält `Referrer-Policy: no-referrer`, `Cache-Control: no-store`.

## 7. Testmatrix (verpflichtend vor Freigabe)

Positiv:

- Start → Scan → Approval mit frischem Passkey → Exchange → eingeloggt, Rolle/Wache korrekt.
- Approval mit frischem TOTP; Ablauf genau an der Grenze (119 s/121 s) mit kontrollierter Uhr.
- Ablehnung, Ablauf, Widerruf, Logout; Status liefert nie ein Secret.
- Nicht-MFA-Nutzer mit 5 Minuten alter Session; MFA-Nutzer mit 2 Minuten alter Re-Auth.

Negativ (jeweils eigener Test):

- Replay von `qr_secret` und von `login_id` nach `CONSUMED` → 410/409, kein Login.
- Fremde Browser-Session (anderes Cookie, gleicher QR) → 403, kein Login.
- Falsche Wache / Fremdmitgliedschaft / deaktivierte Mitgliedschaft → 403/404.
- Fehlende oder veraltete MFA-Re-Auth → 403, kein Login; kein stilles Überspringen.
- Fehlendes CSRF-Token auf Approval/Exchange → 403.
- Rate-Limit-Überschreitung auf Start/Status/Approve → 429, Zähler fensterstabil.
- Session-Fixation: Session-Key vor/nach Exchange unterschiedlich, alte Session ohne Rechte.
- Token-Leak: `qr_secret` fehlt in Response-Headern, Logs, Audit, Redirect-URLs, Referer.
- Scanner ≠ Bestätiger: Gerät A scannt, Gerät B (anderer Nutzer) kann nicht bestätigen.
- Parallele Approvals/Exchanges: genau einer gewinnt (CAS), andere 409.
- Rollenentzug zwischen Approval und Exchange → Exchange verweigert.

## 8. Integration in bestehende Auth

- Nach erfolgreichem Exchange: `login(request, user, backend="axes.backends.AxesStandaloneBackend")`,
  danach dieselbe MFA-Policy wie heute: `mfa_required()` und fehlende bestätigte MFA → `mfa_setup`.
- Der QR-Flow erzeugt **keine** parallele Session-Policy und keine neue Backend-Klasse.
- `mfa_pending_*`-Keys werden nicht wiederverwendet; QR hat eigene, kurzlebige Keys.
- Bestätigungsgerät nutzt vorhandene Passkey-/TOTP-Prüfpfade; keine neue Krypto.
- Audit-Events: `qr_login.created/approved/denied/consumed/expired/revoked` ohne Secrets.

## 9. Offene Entscheidungen (vor Implementierung zu klären)

1. **MFA-Ort:** Gilt die frische Re-Auth auf dem Telefon als zweiter Faktor für den Browser-Login
   (empfohlen, da dasselbe Konto), oder muss MFA zusätzlich im Browser eingegeben werden? Letzteres
   würde den Komfortvorteil stark reduzieren. Ohne Entscheidung bleibt der Flow für MFA-Nutzer
   deaktiviert (fail-closed).
2. **Mehrfachmitgliedschaften:** QR-Login ist aktuell auf genau eine aktive Mitgliedschaft ausgelegt
   (`get_membership`). Mehrfachwachen brauchen eine explizite Auswahl vor Approval.
3. **Kamera-Fehler:** manueller Ersatz (kurzer Code) ist Pflicht; Kamera-Scanning bleibt optionale UI
   mit lokalem Asset, kein Cloud-SDK.
4. **Gültigkeitsfenster:** 120 s ist konservativ; längere Fenster erhöhen Replay-/Schulterblick-Risiko.
5. **Tablet als Bestätigungsgerät:** geteilte Geräte sind ausgeschlossen (keine gemeinsamen Konten);
   Geräte-Registrierung/Logout-Semantik bleibt G4.

## 10. Umsetzungsschnitt für Phase 2 (G2) und Gegenprüfung (M3)

1. Feature-Flag + Settings-Gate (fail-closed) und Tests, bevor UI entsteht.
2. Modell + Migration `QrLoginRequest` (nur Hashes, Indizes auf `expires_at`, `state`).
3. Service-Funktionen mit CAS-Übergängen und Audit; keine View-Logik in Templates.
4. Start-/Status-/Approve-/Exchange-Views mit CSRF, Rate-Limit, `no-store`, `no-referrer`.
5. UI: Warteseite, Bestätigungsseite mit Prüfwort, manueller Code; Kamera optional.
6. Testmatrix aus Abschnitt 7, danach M3-Gegenprüfung auf eingefrorenem Diff.
7. Erst danach Browser-/Geräteabnahme mit echter lokaler HTTPS-Umgebung (nicht durch Mocks ersetzt).

Bis zur Klärung von Punkt 9.1 und ohne TLS-/Geräteabnahme bleibt QR-Login **deaktiviert**.
