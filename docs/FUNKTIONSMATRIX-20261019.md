# Funktionsmatrix — Wachbuch, Stand 2026-10-19

> **Abgelöst** am 30.10.2026 durch [ROADMAP.md](ROADMAP.md). Diese Datei bleibt als Verlauf erhalten.

Methode und Grenze dieser Matrix:

- Basis ist `scripts/inventory_capabilities.py` (statische Routen-/Template-Referenzanalyse) mit
  `evidence/capability-inventory.json` und `evidence/inventory-run.log`.
- **Die Inventur ist kein Funktionstest.** Sie zählt `reverse()`-Referenzen in Testdateien.
  Sie übersieht Tests, die literal auf URLs zugreifen (z. B. `client.get("/api/v1/defects/")`).
- Deshalb wurde jede Zeile zusätzlich gegen die tatsächlich laufenden Testmodule und gegen
  Literalpfade geprüft. Ergebnis: 130 Routen, 97 mit `reverse()`-Referenz; mehrere API-Routen
  gelten statisch als "ohne Test", sind aber literal getestet.
- Funktionale Grundlage: `manage.py test` mit **314 Tests, OK (skipped=1)**,
  Log `evidence/worker-full-tests.log`.

Spalten: **Routen** = Anzahl; **stat. Ref** = `reverse()`-Referenzen in Tests;
**funktionaler Nachweis** = Testmodul, das die Funktion tatsächlich ausführt;
**Pilot-Rest** = nur manuell/real möglich, nicht durch die Suite belegbar;
**fehlend** = kein Testnachweis gefunden (weder `reverse()` noch Literalpfad).

| Modul | Routen | stat. Ref | funktionaler Nachweis | Pilot-Rest | fehlend |
|---|---|---|---|---|---|
| Übergaben (Web) | 8 | 7 | `core/tests.py` (Handover, Revisionen, Append-only) | — | `api_v1_uebergabe_detail` indirekt |
| Übergaben (API) | 5 | 3 | `core/test_wachalltag_api.py` (Ack-Workflow, literal) | — | — |
| Kalender | 7 | 7 | `core/tests.py` (Termine, ICS-Feed) | ICS-Abruf gegen echten Fremdhost | — |
| Kaffeekasse | 4 | 4 | `core/tests.py` (Ledger append-only, Beträge) | — | — |
| Aufgaben | 6 | 5 | `core/tests.py` (Toggle, Tagesbezug) | — | `task_edit` (kein Treffer) |
| Checklisten | 7 | 5 | `core/test_wachalltag_api.py` (Recurring, Fast-Forward) | — | `checklist_complete` (kein Treffer) |
| Mängel (Web) | 4 | 3 | `core/tests.py` + `test_wachalltag_api.py` | Foto-Upload auf realem Gerät | `defect_attachment_web` nur indirekt |
| Mängel (API) | 4 | 0 statisch | `core/test_wachalltag_api.py` (literal: Workflow, Foto, Quota) | — | — (statischer Fehlalarm) |
| Assets (API) | 2 | 0 statisch | `core/test_wachalltag_api.py` (literal) | — | — (statischer Fehlalarm) |
| Inventar (API) | 3 | 0 statisch | `core/test_wachalltag_api.py` (literal: Checkout/Checkin) | — | — (statischer Fehlalarm) |
| Anhänge (API) | 1 | 0 statisch | `core/test_wachalltag_api.py` (Foto-Roundtrip) | — | — (statischer Fehlalarm) |
| Reports (API) | 1 | 0 statisch | `core/test_wachalltag_api.py::test_reports_aggregate_real_station_state` | — | — (statischer Fehlalarm) |
| Pinnwand | 6 | 6 | `core/test_pinboard.py` (15 Tests) | — | — |
| Chat/E2EE | 13 | 11 | `core/test_chat_api.py` (19), `test_chat_groups_api.py` (9), `test_image_privacy.py` (5) | Schlüssel auf Zweitgerät | `chat_hide` (kein Treffer), `station_member_keys` (kein Treffer) |
| Konto/MFA/Passkeys | 11 | 5 | `core/tests.py` (MFA-Basics, 4 Treffer `mfa_setup`) | Passkey-Registrierung/-Login auf echtem Authenticator | mehrere Passkey-Routen nur indirekt |
| Anmeldung/Token | 8 | 4 | `core/tests.py`, `core/test_rate_limit.py` (13) | — | Passkey-Verify-Routen indirekt |
| Team/Rollen/Audit | 7 | 7 | `core/tests.py` (Rollen, Stationsgrenzen, Audit) | — | — |
| Push/PWA | 5 | 5 | `core/tests.py` (Payload, Outbox), `test_wachalltag_design.py` | echter WebPush-Endpunkt, Installation | — |
| Auswertung/Status/Update | 4 | 3 | `core/test_update_api.py` (9) | — | `api_v1_update` indirekt |
| Datenschutz/Vorführung/Demo | 4 | 4 | `core/test_privacy_compliance.py` (7), `test_privacy_navigation.py` (10) | Betreiber-/DSGVO-Freigabe | — |
| Fehlerseiten 400/403/404/500/429 | — | — | `core/test_security_regressions.py` (27), neu `test_ui_umlauts_regressions.py` (8) | — | — |
| Statische Projektseite `site/` | — | — | `site/tests/check_site.py` (10) | GitHub-Pages-Aktivierung (bewusst nicht erfolgt) | — |
| Django-Admin | 1 | 0 | absichtlich nicht getestet (nur Staff) | — | bewusst offen |

## Belegte Lücken (kein Testnachweis)

Vier Routen haben weder `reverse()`- noch Literalpfad-Treffer in `core/tests.py` oder
`core/test_*.py`:

1. `chat_hide` — `chat/<int:pk>/ausblenden/`
2. `task_edit` — `aufgaben/<int:pk>/bearbeiten/`
3. `checklist_complete` — `checklisten/<int:pk>/erledigt/`
4. `station_member_keys` — `chat/schluessel.json`

Diese Lücken sind **nicht** durch die 314 grünen Tests abgedeckt. Sie sind unverändert und
wurden in dieser Etappe nicht angefasst.

## Was diese Etappe geändert hat

- Nur sichtbare deutsche UI-Texte (10 Dateien) plus eine neue Testdatei.
- Keine Route, kein Feld, keine Kennung, keine Migration.
- `site/` ist statisch und unveröffentlicht.

## Offene echte Abnahmen (nicht durch Tests ersetzbar)

- GitHub Pages: Konfiguration dokumentiert, **nicht aktiviert**, kein Push.
- Passkeys/WebAuthn: realer Authenticator, Recovery-Fall.
- WebPush: echter Endpunkt, Browser-Berechtigung, Zustellung.
- ICS-Feed: realer Allowlist-Host, Fehlerfall Netz/Timeout.
- Datenschutz: Betreiberprüfung und Freigabe der öffentlichen Aussagen.

---

## Nachtrag 2026-10-19b — Setup, Aktivierung, Offline

### Neue Routen (statische Referenz)

| Route | Name | Zugriff | Funktionaler Nachweis |
|---|---|---|---|
| `/setup/` | `setup_wizard` | anonym, nur mit `SETUP_BOOTSTRAP_TOKEN`; nach Abschluss 404 | `SetupWizardTests` (6) |
| `/setup/wetter/` | `setup_weather_preview` | Setup-Session + CSRF | `WeatherConsentTests` (4) |
| `/aktivieren/<token>/` | `activate_account` | Token-Inhaber, einmalig | `ActivationTests` (11) |
| `/team/einladungen/` | `team_invites` | Admin der Wache | `AscivationTests`, `test_non_admin_...` |
| `/team/einladungen/neu/` | `team_invite_create` | Admin der Wache | `test_admin_can_create_invite_...` |
| `/team/einladungen/<pk>/widerrufen/` | `team_invite_revoke` | Admin, stationsgebunden | `test_invite_revoke_is_station_scoped` |

### Widersprüche aus der Vor-Etappe — Bedeutung

Die Gegenprüfung der Vor-Etappe führte vier Hypothesen H1–H4. **H1 und H4 wurden
WIDERLEGT.** Das bedeutet dort ausdrücklich: es wurden **keine geänderten
technischen Kennungen** und **keine Rest-Transliterationen** gefunden — also
**keine neuen Bugs**. „WIDERLEGT“ ist in diesem Kontext ein negatives Ergebnis
für die Hypothese, nicht ein positiver Befund. Die Formulierungen in
`docs/NEXT-STAGES.md` §2 sind entsprechend zu lesen und wurden nicht als
Fehlerliste übernommen.

Drei konkrete Widersprüche, die nicht ungeprüft übernommen wurden:

1. **„CSRF fehlt im Aktivierungs-GET“** (Mistral-Planreview): falsch — das
   Template enthält `{% csrf_token %}`; der GET liefert nur das Formular.
2. **„`select_for_update` verhindert die Race nicht, also Ressourcen vor dem
   Commit“** (Mistral-Diffreview): falsch — das bedingte UPDATE ist das Gate und
   liegt **vor** der Ressourcenerzeugung; ein Verlierer erzeugt nichts.
3. **„AGY hat keine Befunde gemeldet, also ist der Diff ungeprüft“**: falsch —
   AGY-Planreview war vollständig (`KEINE_BEFUNDE`), das AGY-Diffreview lief
   zweimal ohne verwertbare Ausgabe (Timeout, Gemini-Filter). Das ist eine
   **Abdeckungslücke**, kein Befund und keine Freigabe.

### Offline

`docs/OFFLINE-BETRIEB.md`: WAN-Ausfall mit erreichbarem LAN-Server ist durch
`WanOutageTests` belegt. Vollständig getrenntes Gerät/Serverausfall bleibt offen
(kein Client-Cache, keine Outbox, keine Synchronisation).
