# ASVS 5.0 Level 2 – Abdeckungsmatrix (Wachbuch)

Stand: 31. Juli 2026. Interne technische Selbsteinschätzung, kein Zertifikat und
keine Ersatzprüfung durch unabhängige Stelle.

Referenz: [OWASP ASVS 5.0](https://owasp.org/www-project-application-security-verification-standard/).

Legende: **OK** umgesetzt / **Teil** teilweise / **Offen** geplant / **n/a** nicht anwendbar.

## V1 Architektur und Design

| Kontrolle | Status | Hinweis |
| --- | --- | --- |
| Vertrauensgrenzen dokumentiert | OK | `docs/ARCHITECTURE.md` |
| Keine Patienten-/Einsatzdaten | OK | Produktgrenze, Privacy-by-Design |
| Threat-Model formal | Teil | Audit + RESEARCH, kein vollstaendiges STRIDE |

## V2 Authentifizierung

| Kontrolle | Status | Hinweis |
| --- | --- | --- |
| Persoenliche Konten | OK | kein Gemeinschaftskonto |
| Passwort-Login + Lockout | OK | django-axes |
| MFA (TOTP) | OK | optional / erzwingbar |
| Passkeys (WebAuthn) | OK | wenn `WEBAUTHN_RP_ID`/`ORIGIN` gesetzt |
| Passwort-Recovery-Flow | Offen | bewusst nicht oeffentlich; Admin-Reset |
| Credential Stuffing Monitoring | Teil | Axes-Zaehler, kein zentrales SIEM |

## V3 Session Management

| Kontrolle | Status | Hinweis |
| --- | --- | --- |
| Sichere Session-Cookies | OK | HttpOnly, Secure (Prod), SameSite=Lax |
| CSRF | OK | Token + HttpOnly CSRF-Cookie; SPA-Token im Meta-Tag |
| Session-Timeout | OK | 12h |
| Logout invalidiert Session | OK | Django Logout |

## V4 Access Control

| Kontrolle | Status | Hinweis |
| --- | --- | --- |
| Rollenmodell stationsbezogen | OK | Membership + Decorator |
| Objektbindung an Station | OK | Query-Filter in Views |
| Auditor ohne Fachinhalt | OK | 403 auf Content-Rollen |
| Kalender-Abo-Token widerrufbar | OK | `CalendarFeedToken` |

## V5 Validation / V7 Error Handling

| Kontrolle | Status | Hinweis |
| --- | --- | --- |
| Server-seitige Validierung | OK | Forms/Model.clean |
| Keine Stacktraces an Clients | OK | Prod DEBUG=false |
| Einheitliche Fehlerseiten | Teil | Django-Defaults |

## V8 Data Protection

| Kontrolle | Status | Hinweis |
| --- | --- | --- |
| TLS am Proxy | OK | dokumentiert |
| HSTS | OK | Django-Setting (Proxy) |
| Append-only Audit/Kasse | OK | ORM + DB-Rechte |
| Retention | Teil | Feeds ja; Audit nur nach Freigabe |
| Geheimnisse in Env | OK | `.env`, keine Secrets im Image |

## V9 Communication

| Kontrolle | Status | Hinweis |
| --- | --- | --- |
| CSP | OK | streng; `connect-src` nur `'self'` und Push-Allowlist |
| Permissions-Policy | OK | WebAuthn self; Sensoren denied |
| Clickjacking | OK | frame-ancestors/XFO |

## V10 Malicious Code / V12 Files

| Kontrolle | Status | Hinweis |
| --- | --- | --- |
| Keine allgemeinen User-Uploads | OK | nur Profilavatar (JPEG in DB, max. 2 MB Roh, 192px) |
| Chat/Post E2EE | OK | AES-256-GCM + ECDH P-256 (BSI TR-02102); siehe CRYPTO-BSI.md |
| Passwort-Hash | OK | Argon2id bevorzugt |
| TOTP at rest | OK | AES-256-GCM (HKDF aus SECRET_KEY) |
| Feed-SSRF-Haertung | OK | Allowlist, keine Redirects |

## V13 API / PWA

| Kontrolle | Status | Hinweis |
| --- | --- | --- |
| JSON-Endpunkte CSRF-geschuetzt | OK | Passkey/Push Session-POST |
| Token-API ohne CSRF | OK | `/api/v1/` Bearer/Token, csrf_exempt |
| App-Tokens hashed + widerrufbar | OK | SHA-256, Klartext einmal, `/konto/api/` |
| Service Worker ohne Write-Queue | OK | Read-only Cache |
| Web-Push opt-in | OK | nur bei VAPID + Nutzeraktion |
| OpenAPI fuer Mobile | Teil | `/api/v1/openapi.yaml` Foundation |

## V14 Configuration

| Kontrolle | Status | Hinweis |
| --- | --- | --- |
| Least-privilege DB-Rollen | OK | grant_database_access |
| Healthcheck ohne Secrets | OK | `/healthz/` |
| Dependency-Scanning in CI | Teil | Image-Scan in Workflows/Doku |

## Offene L2-Luecken vor öffentlichem DNS

1. Unabhängige ASVS-L2-Pruefung und Lasttest
2. Zentrales Monitoring/Alerting und Incident-Runbook-Probe
3. Passwort-Reset-Prozess organisatorisch festziehen
4. Audit-Export / Offline-Archiv
5. Optional: VAPID-Private-Key bleibt in Env (nicht in DB); TOTP at rest seit 0.13 AES-GCM

Siehe auch [`GO-LIVE-CHECKLIST.md`](GO-LIVE-CHECKLIST.md) und [`SECURITY-PRIVACY.md`](SECURITY-PRIVACY.md).
