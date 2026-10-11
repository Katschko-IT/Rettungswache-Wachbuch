# Öffentliche App-Oberfläche (Unterseiten, Auth- und Fehlerseiten)

Stand: 11. Oktober 2026 · Branch `work/app-design-public` (Basis `f2a33e0`)

Diese Datei dokumentiert die Überarbeitung der öffentlichen Unterseiten sowie
der Auth- und Fehlerseiten der Web-PWA, damit sie zur neuen Product-Landing
(`templates/core/landing.html`, `core/static/core/presentation.css`) passen.
Sie ergänzt [`DESIGN-SYSTEM.md`](DESIGN-SYSTEM.md) und ersetzt es nicht.

## Ausgangslage und Grenzen

- Die neue Landing (`landing.html`) ist **unverändert** und bleibt die visuelle
  Referenz: ruhig, feldlesbar, öffentlicher Dienst, hoher Kontrast, keine
  Marketing-Ästhetik, keine Deko-Kartenwand.
- Die gemeinsame Designschicht `ww-app` am `body` sowie die lokale
  Bootstrap-CSS werden **separat durch den Parent** in `templates/base.html`
  eingebunden. Diese Arbeitskopie ändert **kein** `base.html`, **kein** CSS,
  **kein** JavaScript und **kein** Python.
- In dieser Kopie werden nur die erlaubten Templates sowie diese neue
  Dokumentation geändert.

## Verfügbare Designklassen in den Templates

Verwendet werden ausschließlich dokumentierte Hooks:

- **Neue Schicht (Parent-CSS):** `ww-auth-layout`, `ww-auth-aside`,
  `ww-form-panel`, `ww-page-intro`, `ww-surface`, `ww-section-caption`.
- **Bestehend und erhalten:** `page-heading`, `context-line`, `lead`, `hint`,
  `form-card`, `button primary`, `button secondary`, `text-action`,
  `form-actions`, `notice`, `content-flow`, `narrow`, `prose`,
  `summary-list`, `inline-form`, `landing-points`, `passkey-login`,
  `mfa-secret`, `mfa-key`, `mfa-uri`, `error-shell`, `error-code`,
  `error-message`, `error-actions`, `error-meta`, `error-support`,
  `offline-panel`, `card`.
- **Bootstrap Grid/Utilities** (durch Parent-CSS): `row`, `col-*`, `g-*`,
  `visually-hidden`.

## Gemeinsame Muster

- **Genau eine `h1` pro Seite.** Kontext vor der `h1` steht in
  `p.context-line`; Nebenüberschriften sind `h2`/`h3`.
- **CTA-Hierarchie:** genau eine primäre Aktion (`button primary`); Zurück-/
  Abbruch-/Alternativaktionen sind `button secondary` oder `text-action`.
- **Auth-Seiten** (Anmeldung, Registrierung, MFA-Bestätigung, Zugang) nutzen
  `ww-auth-layout` als zweispaltiges Raster: links `ww-form-panel` mit
  `ww-page-intro`, rechts `ww-auth-aside` mit kurzen, faktenbasierten
  Hinweisen passend zum Landing-Ton.
- **Status- und Fehlerseiten** nutzen `ww-surface` als ruhige Fläche ohne
  Kartenwand.
- **Mobil:** `ww-auth-layout` und Bootstrap-Spalten stapeln einspaltig; kein
  horizontaler Scroll auf 320 px.
- **Keine Inline-Skripte, Inline-Styles, Inline-Eventhandler, `|safe` oder
  `innerHTML`.** Der einzige dynamische Zweig im Fehlerbereich bleibt die
  Korrelations-ID (autoescaped).

## Seiteninventur (jeder erlaubte Pfad)

| Pfad | Route | Status | Kernänderung |
|---|---|---|---|
| `templates/registration/login.html` | `/anmelden/` | geändert | Auth-Raster + Aside, klare CTA, Demo-Hinweis als `notice` |
| `templates/registration/register.html` | `/registrieren/` | geändert | Auth-Raster + Aside, Sekundäraktion als Button |
| `templates/registration/mfa_verify.html` | `/anmelden/mfa/` | geändert | Auth-Raster + Aside, Code-Hinweis als `hint` |
| `templates/registration/mfa_setup.html` | `/konto/mfa/` | geändert | Auth-Raster + Aside (3 Schritte) |
| `templates/registration/mfa_manage.html` | `/konto/mfa/` (verwaltet) | geändert | Auth-Raster + Aside (Sicherheit), Zurück als Button |
| `templates/core/access.html` | `/zugang/` | geändert | Auth-Raster, primärer Bereichs-Link, Aside „So geht es weiter“ |
| `templates/core/offline.html` | `/offline/` | geändert | `ww-surface`-Statusfläche, `ww-page-intro` |
| `templates/errors/400.html` | Handler 400 | geändert | `ww-surface`, Umlaute normalisiert |
| `templates/errors/403.html` | Handler 403 | geändert | `ww-surface`, CTA-Hierarchie (Anmelden primär) |
| `templates/errors/404.html` | Handler 404 | geändert | `ww-surface`, „Zur Übersicht“ für Angemeldete |
| `templates/errors/429.html` | Handler 429 | geändert | `ww-surface`, Umlaute normalisiert |
| `templates/errors/500.html` | Handler 500 | geändert | `ww-surface`, CTA-Hierarchie, Umlaute normalisiert |
| `templates/core/privacy.html` | `/datenschutz/` | geändert | Kopf `ww-page-intro`, Kontakte responsiv, CTA-Zeile |
| `templates/core/vorfuehrung.html` | `/vorfuehrung/` | **unverändert** | siehe Begründung unten |

## Bewahrte Verträge

- **Rechts-/Datenschutzinhalt vollständig erhalten.** `privacy.html` enthält
  jeden Abschnitt, jede Aussage und die Kontakt-Schleife (Name, Wache,
  Organisation, E-Mail, Telefon, Adresse, externer Kontakt) unverändert.
  Es wurden keine Aussagen erfunden, gekürzt oder sinnverändert.
- **Zugriffs-/Fehlerseiten ohne neue Rechts- oder Funktionsbehauptungen.** Bei
  403 und 500 wurden nur Orthografie/Umlaute und die CTA-Anordnung angepasst,
  nicht der Aussagegehalt.
- **Formverträge erhalten.** Alle Formulare behalten `method="post"`,
  `{% csrf_token %}`, das Fehlerinclude `core/form_errors.html`, `{{ form.as_p }}`,
  Hidden-Felder (`next`), Feldnamen und IDs.
- **Testselectoren erhalten.** `error-shell`, `error-code`, `error-title`,
  `error-meta` („Korrelations-ID“), `form-card`, `offline-panel`,
  `data-passkey-login`, `data-passkey-login-status`, `data-passkey-mfa`,
  `data-passkey-mfa-status`, `data-passkey-register`,
  `data-passkey-register-status` bleiben wörtlich vorhanden.
- **Produktgrenze/Demoschutz erhalten.** „Konten vergibt die
  Wachenverwaltung“, „zweite Faktorstufe“, „Wachbuch ist kein Patienten-,
  Einsatz- oder Alarmierungssystem“ bleiben konsistent mit README,
  Landing und Datenschutz.
- **Öffentliche Demo bleibt hinter dem Login.** Der Registrierungslink auf der
  Anmeldeseite bleibt an `registration_enabled` gebunden; der Demo-Hinweis
  bleibt an `demo_public_mode` gebunden. Kein passwortloser Einstieg, keine
  Registrierungs-/Verwaltungsroute wird in der öffentlichen Demo beworben.

## Warum `vorfuehrung.html` unverändert bleibt

Die Vorführung ist eine eigenständige Präsentationsstrecke:

- Sie ist an `core/static/core/demo.css` und an `core/static/core/app.js`
  gebunden (`[data-demo-deck]`, `[data-demo-slide]`, `[data-demo-prev/next/
  music/count/bar]`). Eine Struktur-/Klassenänderung würde Deck-Zählung
  („1 / 8“), Foliensteuerung und Styling brechen; CSS/JS-Änderungen sind
  außerhalb des Scopes.
- Sie erfüllt die Designregeln bereits: genau eine `h1` (visually-hidden),
  klare CTA-Hierarchie (primär vorwärts, sekundär zurück), Zurück-/Weiter-
  Steuerung, Demo-Schutz (`demo_public_mode` zeigt Zugangsdaten,
  `demo_login` nur wenn `demo_mode` und **nicht** `demo_public_mode`).
- Der CSP-Regressionstest verlangt, dass die Datei keine Inline-Skripte/-Styles
  enthält und `data-demo-deck` vorhanden ist — beides bleibt so erhalten.

## Prüfungen (isoliert, ohne Live-Datenbank)

```bash
PY=/opt/data/workspace/wachbuch-r1-postgres-agy-20261009/.venv-r1/bin/python
$PY manage.py check --settings=config.test_settings
$PY manage.py test --settings=config.test_settings \
  core.test_security_regressions core.test_privacy_compliance \
  core.test_demo_public_mode core.test_presentation
```

Ohne `DATABASE_URL`/`DB_HOST` nutzt `config.test_settings` die lokale SQLite-
Datei (`settings.py`), also keine Produktivdatenbank.
