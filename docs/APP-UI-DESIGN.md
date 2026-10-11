# Wachwerk – App-UI-Design (gemeinsame Unterseiten-Shell)

Stand: 11. Oktober 2026
Bezugsticket: „Die restlichen Seiten und Unterseiten sind noch im alten Design –
bitte einmal neu machen."

## 1. Zweck

Alle server-gerenderten Unterseiten (Übersicht, Übergaben, Kalender, Mehr und
deren Module, Konto, Chat, Krypto, Fehler-/Auth-Seiten) teilen **eine**
durchgestaltete App-Shell. Sie ist an die neue Bootstrap-5.3.8-Produkt-Landing
(`templates/core/landing.html` + `core/static/core/presentation.css`) angelehnt,
übernimmt deren Bildsprache und bleibt gleichzeitig bei den bestehenden,
funktionalen Klassennamen, Rollen, IDs und Sicherheitsgrenzen.

Die Umsetzung ist bewusst eine **gezielte Designschicht** – keine zweite
Palette und kein generischer Karten-Wall:

- `templates/base.html` – lädt Bootstrap lokal **vor** `app.css` und die neue
  Schicht `app-ui.css` **zuletzt**; `body` trägt `ww-app` plus eine
  Authentifizierungs-Variante.
- `core/static/core/app-ui.css` – die neue Designschicht (Token-Brücke,
  Typografie-Skala, Shell, Komponenten, Responsive, Kontrast, Motion).

## 2. Gemeinsame Tokens (Landing = App)

`app-ui.css` definiert `--ww-*`-Werte mit Fallback und bindet sie an die
bestehenden App-Variablen (`--brand`, `--text`, `--surface`, `--line`, …).
Dadurch folgen die Unterseiten automatisch den `profile-*`-Themes und dem
Highcontrast-Modus.

| Rolle | Wert | Landing-Pendant |
|---|---|---|
| Schrift | `"Source Sans 3"` (lokal, `core/static/core/fonts/`) | `--pw-*` Webfonts |
| Primärblau | `--brand` (`#0d47a1`) | `--pw-brand` |
| Tiefblau | `--brand-deep` (`#082e63`) | `--pw-brand-deep` |
| Ink (Überschriften) | `--brand-ink` / `#0f1b2e` | `--pw-ink` |
| Surface | `--surface` (`#ffffff`) | `--pw-surface` |
| Trennlinie | `--line` (`#dce4ef`) | `--pw-line` |
| Fokus | `--focus` (`#f0b429`) | `--pw-focus` |
| Radius | `14px` (`--ww-radius`) | `--pw-radius` |
| Rasterbreite | `1120px` (`--ww-container`) | `--pw-container` |
| Touch-Ziel | `48px` (`--ww-touch`) | `--pw-touch` |

## 3. Designentscheidungen

1. **Ladereihenfolge.** Bootstrap 5.3.8 (MIT, lokal vendored) liefert nur
   Reboot + Variablen und liegt **vor** `app.css`; `app-ui.css` liegt nach
   `app.css`, `accessibility.css` und `crypto_unlock.css`. Damit gewinnt die
   bewusste App-Typo über Bootstrap-Reboot, ohne bestehende Regeln zu brechen.
2. **Body-Vertrag.** `body.ww-app` immer; dazu `ww-app--auth` (angemeldet) bzw.
   `ww-app--anon` (Login, Registrierung, Fehlerseiten). `has-app-nav` und
   `profile-*` bleiben unverändert erhalten.
3. **Starke Seitentitel & Aktionshierarchie.** Klare H1-Skala, `context-line`
   als Überzeile mit feiner Marke (CSS-gezeichnet, kein Icon-Font), genau eine
   hervorgehobene Primäraktion oben rechts (`.heading-with-action`), ruhige
   Statuszeile darunter.
4. **Ruhige Navigationsleiste.** Flache, helle Leiste mit klarem
   `aria-current="page"`-Zustand; mobil als feste vierteilige Bottom-Navigation
   (Übersicht · Übergaben · Kalender · Mehr) mit 48px-Flächen.
5. **Aufgaben zuerst (task-first).** Formulare, Listen, Tabellen, Fehler,
   Empty-States, Details, Tabs, Krypto-Dialog, Chat und Kalender sind auf
   schnelles Erfassen/Lesen ausgelegt; Dekoration nur, wo sie Orientierung gibt.
6. **Flächen statt Schatten.** Rand + minimale Anhebung passend zur Landing
   („Flaechen nutzen Rand statt schwerer Schatten", siehe `DESIGN-SYSTEM.md`).
7. **Keine Icon-Fantasie.** Alle Affordanzen sind CSS-gezeichnet (Aufklapp-`+`,
   Listen-Chevron) oder bereits im HTML vorhandene SVGs der Live-Navigation.
8. **Sicherheit unverändert.** Keine externen Quellen (kein CDN, keine
   Google-Fonts), keine Inline-Styles (CSP `style-src 'self'`), keine `|safe`-
   oder `innerHTML`-Sinks. `LogoutPOST`, CSRF, Rollenbedingungen und die
   Produkt-/Demo-Grenzen bleiben wörtlich erhalten.
9. **Installationshinweis schließbar.** Das PWA-Banner startet mit `hidden` und
   hat zwei gleichwertige Schließen-Bedienelemente, beide mit
   `data-install-dismiss` (JS des Parents hört per `querySelectorAll`):
   „Später" und ein echtes X (`type="button"`, `class="button secondary
   install-close"`, `aria-label="Installationshinweis schließen"`). Mobil bleibt
   „Später" breit, das X eine quadratische 48px-Fläche. Ein globales
   `[hidden] { display: none !important; }` garantiert, dass das
   `display:flex` des Banners (aus `app.css`) den verborgenen Zustand nie
   überstimmt. Ob nach Installation/Standalone/iOS gar nicht mehr angezeigt
   wird, entscheidet die Installlogik (`app.js`, hier nicht angefasst).

## 4. Abgedeckte Komponenten

Seitentitel/Überzeile · Statuskarten (`status-summary`/`status-pill`) ·
Schnellzugriff (`quick-actions`) · Karten (`section-block`, `form-card`) ·
Listen (`item-list`/`list-row`, `more-list` mit Chevron) · Tabellen
(`table-wrap`/`responsive-table`) · Formularfelder, Fehlerlisten und
Fehlerzusammenfassung · Empty-States · Badges (`status-label`, `legend-chip`,
`nav-badge`) · Details (`details-block`, `details-help`, `details.form-card`) ·
Tabs (`filter-nav`, `chat-tabs`) · Krypto-Dialog (`dialog.crypto-unlock`) ·
Chat (`chat-thread`/`chat-bubble`) · Kalender (`agenda`, `week-board`,
`agenda-holiday`/`agenda-waste`) · Taskboard (`task-band`, `task-row`,
`week-task`, `task-legend`) · Zugangs-/Auth-Panel (`access-panel`) ·
Fehlerseiten (`error-shell`) · Konto (`avatar-panel`, `more-list`) ·
Kaffeekasse (`balance-row`, `payment-hints`, `responsive-table`) ·
Installationshinweis (`install-banner`, `install-actions`, `install-close`).

## 5. Erhaltene Semantik

- **Taskboard-Bänder** Grün/Gelb/Blau bleiben bei ihren `--band`/`--band-soft`-
  Farben (`#16a34a`, `#b45309`, `#0d47a1`); die Designschicht fasst nur
  Rhythmus, Rundung und Touch-Flächen an.
- **Hoher Kontrast** (`prefers-contrast: more`) setzt weiterhin die
  Schwarz/Weiß-Tokens aus `accessibility.css`; `app-ui.css` entfernt dort nur
  Schatten und verstärkt Ränder.
- **Organisationsprofile** (`profile-rescue/fire/police/general`) bleiben
  erhalten, weil alle Regeln über `var(--brand)` usw. laufen.

## 6. Responsive & Barrierefreiheit

- Einspaltig ab Start; das 1120px-Raster greift erst mit ausreichend Platz.
- Bis `48rem`: vierteilige Bottom-Navigation, kompakter Header, gestapelte
  Aktionsleiste.
- Bei `320px` kein horizontales Scrollen; `min-width: 0` und
  `overflow-wrap: anywhere` verhindern versteckten Overflow.
- `200%` Text: keine festen Höhen auf Textflächen, `text-wrap: balance` für
  Titel, umbrechende Aktionsleisten.
- `prefers-reduced-motion: reduce` schaltet jede Animation/Transition ab;
  Bewegung ist nur optional (`no-preference`) und ohne Layout-Sprünge.
- Tastaturfokus bleibt über den bestehenden `:focus-visible`-Ring sichtbar.

## 7. Tests

`core/test_app_ui.py` prüft auf `config.test_settings` (eigene Test-DB, keine
bestehende DB) das Base-Laden (bootstrap → app.css → app-ui.css), die
`ww-app`/`ww-app--auth`/`ww-app--anon`-Varianten, erhaltene Berechtigungen
(Rollen-Navigation, Auditor), die Schreibsicherheit (CSRF auf LogoutPOST,
Task-Toggle) und dass die Designschicht keine externen Quellen oder
Inline-Styles einführt.

## 8. Verbleibende Grenzen

- Der Service-Worker-Precache (`core/views.py::service_worker`) lädt die lokale
  Bootstrap-Datei und `app-ui.css` **vor** `app.css` bzw. als letzte Designschicht;
  die Cache-Version enthält den Zusatz `-app-ui-1`, damit installierte Apps die
  neuen Dateien erhalten.
- **Reflow bei 200 % Schriftgröße:** Der Abnahmelauf prüft auf allen 34 Seiten,
  dass das Dokument nicht seitlich scrollt (`scrollLeft` bleibt 0) und kein
  Element außerhalb eines bewussten Scroll-Containers über den Viewport
  hinausragt. Dafür wurden Tabellenkarten, Listenzeilen, Agenda-Zeilen, die
  Navigationsleiste und das Übersichts-Grid nachgezogen. `scrollWidth -
  innerWidth` ist hier **kein** gültiges Signal: bei sichtbarem `html`-Kasten
  meldet es den Overflow-Bereich auch dann, wenn die Seite gar nicht scrollen
  kann.
- **Fehlerhandler:** `core/context.py` liest `request.user` nur noch über
  `getattr(...)`. Vorher brach die 500-Seite selbst ab (`'WSGIRequest' object has
  no attribute 'user'`), wenn eine Anfrage nie die Auth-Middleware passiert hatte
  – etwa bei einer fehlenden statischen Datei – und Besucher sahen einen nackten
  Serverfehler statt der gestalteten Fehlerseite.
- Browser-, Screenreader-, Kontrast- und Reflow-Nachweise am realen Gerät
  stehen weiterhin aus (siehe `docs/GO-LIVE-CHECKLIST.md`).


## Handoff (Stand 11.10.2026)

```text
Roadmap-ID: R-022 (Nachtrag Unterseiten) – R-018 bleibt offen
Branch/PR: feature/app-design-consistency (lokal gepusht, kein PR)
Bereits geändert: 61 Templates, base.html, app-ui.css, app.js, core/views.py,
  core/context.py, core/models.py + Migration 0028, vorfuehrung.html, Tests/Docs
Ausgeführte Checks und Ergebnis: Django 351 Tests OK (1 Skip);
  makemigrations --check sauber; Browserlauf gegen das Image 34 angemeldete
  Seiten, eine h1 je Seite, keine Konsolenfehler, Trefferflaechen >= 44 px;
  200 %-Reflow korrigiert; öffentliche Demo nachgeprüft (6 Seiten, echter
  HTTPS-Login, 6 Nutzer/61 Tabellen unverändert)
Offene Risiken/Blocker: kein Screenreader-/Kontrast-/Gerätetest (R-018),
  keine unabhaengige Fremdabnahme der Fassung; iPhone-Safari-Tab erkennt
  "bereits installiert" nicht zuverlässig
Nächste kleinste Aktion: R-018-Teilpruefung Kontrast/Fokus mit NVDA bzw.
  VoiceOver auf einem realen Gerät
```
