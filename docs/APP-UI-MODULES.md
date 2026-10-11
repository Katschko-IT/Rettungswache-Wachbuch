# App-UI-Module – Oberflächenvertrag der angemeldeten Fachseiten

Stand: 11. Oktober 2026
Geltungsbereich: `templates/core/*.html` (angemeldete App-Oberfläche)
Nicht in diesem Dokument: öffentliche Seiten (`landing.html`, `access.html`,
`privacy.html`, `vorfuehrung.html`, `offline.html`) sowie die zentrale Shell
(`templates/base.html`). Diese liegen bei den jeweiligen Modul-Workern.

## Ziel

Alle angemeldeten Fachseiten und Unterseiten folgen einer einheitlichen,
mobil wie Desktop gut lesbaren Struktur, die zur neuen Bootstrap-basierten
Product-Landing passt. Der Umbau ist **markup-only**: Datenmodell, Auth,
Rollen, Feature-Gates und JavaScript bleiben unverändert.

## Schichtenmodell

1. **Shell** (`templates/base.html`, anderer Worker): `body.ww-app`,
   lokales BootstrapCSS, `.app-ui.css` und die Einbindung der Blöcke.
   Die Fachseiten reichen ihren Inhalt ausschließlich über `{% block content %}`
   (und `{% block title %}`) ein.
2. **Designschicht** (`core/static/core/app-ui.css`, anderer Worker):
   gestaltet die gemeinsamen `ww-`-Klassen und die bestehenden funktionalen
   Komponenten (`.list-row`, `.status-label`, `.form-card`, `.button`, …).
3. **Fachmodule** (dieser Worker): semantisches HTML, die gemeinsamen
   `ww-`-Klassen und additive Bootstrap-Utilities.

## Gemeinsame, optionale Klassen

Diese Klassen werden **zusätzlich** zu den bestehenden funktionalen Klassen
gesetzt. Fehlt eine Klasse (z. B. weil `app-ui.css` nicht geladen ist), bleibt
die Seite durch die vorhandenen Funktionsklassen und semantisches HTML
weiterhin benutzbar – fehlende CSS darf nie zu einer Kaputtdarstellung führen.

| Klasse | Verwendung: wird gesetzt auf … |
|---|---|
| `ww-app` | `body` in der Shell (andere Worker) |
| `ww-page-intro` | `<header>` der Seitenintro (zusammen mit `.page-heading`) |
| `ww-form-panel` | `<form>`, das Eingaben erfasst (zusammen mit `.form-card`) |
| `ww-surface` | neutrale Inhaltsfläche/`<section>` (zusammen mit `.section-block`) |
| `ww-module-index` | Modul-/Linkverzeichnis (`more.html`, Konto-Links) |
| `ww-section-caption` | kleine Kontextzeile/Kicker über einem Abschnitt |

Zusätzlich werden ausschließlich **additive** Bootstrap-Utilities genutzt,
die ohne Bootstrap inert sind und mit Bootstrap nur verfeinern (z. B.
`visually-hidden` bleibt die bestehende projektweite Hilfsklasse).

## Verbindliche Markup-Regeln

- Genau **eine `h1` pro Vollseite**; Teil-/Fragmenttemplates enthalten keine `h1`.
- **Höchstens eine primäre Aktion** pro Ansicht. Mehrere `.button primary` sind
  nur zulässig, wenn jede für sich ein eigener aktiver Vorgang ist
  (z. B. `account.html`: Profilbild/Profil/Passwort, `checklists.html`: je
  Checkliste, Tagesaufgaben: je Aufgabe).
- Keine „Einheitskarte mit allem drin": Module, Filter, Listen, Formulare und
  Hilfe liegen in getrennten, semantisch benannten Bereichen.
- Keine `|safe`-Ausgabe, keine Inline-Styles, keine `<script>`-Blöcke und
  keine Inline-Event-Handler. JSON gelangt ausschließlich über `json_script`.
- Listen/Details/Formulare/Filter/Statustabellen/Aktionsgruppen/Leerzustände/
  Hilfe/Header sind semantisch ausgezeichnet (u. a. `aria-current` für aktive
  Filter/Tabs, `caption`/`scope` für Tabellen, `role="alert"` für Formfehler).

## Bewahrte funktionale Verträge (unverändert)

- Alle Formular-`action`-URLs, Feld-`name`/`id`, `{% csrf_token %}`-Blöcke.
- Alle Rollen-/Feature-Bedingungen (`{% if current_membership.role == 'admin' %}`,
  `checklists_enabled`, `coffee_enabled`, …).
- Alle Kontextvariablen und alle `json_script`-Namen
  (`chat-feed-json`, `private-members-json`, `mail-envelope-json`,
  `push-config`, …) inklusive der `data-*`-Hooks für das E2EE-JS.
- Append-only-Semantik: Kaffeekasse (Korrektur nur als Gegenbuchung),
  Audit (nur lesende Tabelle), Checklisten-Abschlüsse, Übergaberevisionen.
- Sensible Status: Krypto-/Messenger-/Privatpoststatus (E2EE-Hinweise,
  Vertrauensmodell-Satz, Schlüssel-Status) bleiben vollständig erhalten.

## Modulverzeichnis (Seiteninventar)

Legende: **P** = primäre Handlung/en der Ansicht.

### Übersicht & Navigation
- `dashboard.html` – **P**: Übergabe anlegen. Überblick über dringende/aktive
  Übergaben und nächste Termine.
- `more.html` – **P**: –. Professionelles Modulverzeichnis, in Gruppen
  (Betrieb, Nachrichten, Konto/Gerät, Verwaltung) mit `ww-module-index`.

### Übergaben
- `handover_list.html` – **P**: Übergabe anlegen. Filter Aktiv/Dringend/Archiv.
- `handover_detail.html` – **P**: Status aktualisieren. Details + Revisionen.
- `handover_form.html` – **P**: Übergabe anlegen. Schutz-Hinweis zu Freitexten.
- `handover_edit.html` – **P**: Korrektur speichern (erzeugt neue Revision).
- `pagination.html` – **Fragment**, unverändert (keine eigene Layoutrolle).

### Kalender
- `calendar.html` – **P**: Termin anlegen. Agenda; ICS-Export sekundär.
- `calendar_feed.html` – **P**: Abo-Link erzeugen. Tokenverwaltung.
- `calendar_form.html` – **P**: Termin anlegen.

### Tagesaufgaben
- `tasks_today.html` – **P**: je Aufgabe „Erledigt". Wandtafel-Bänder.
- `tasks_week.html` – **P**: je Aufgabe (Wochenbogen).
- `tasks_manage.html` – **P**: Aufgabe anlegen. Vorlagenliste.
- `task_form.html` – **P**: Speichern.
- `task_row.html` – **Fragment**, unverändert (POST `task_toggle`, versteckte Felder).

### Mängel, Geräte, Auswertung
- `defects.html` – **P**: Mangel anlegen. Statusfilter.
- `defect_detail.html` – **P**: Status speichern. Fotos + Verlauf.
- `defect_form.html` – **P**: Mangel speichern.
- `assets_inventory.html` – **P**: Speichern (je Status) / Anlegen. Anlegen in `<details>`.
- `wachalltag_reports.html` – **P**: –. Stationszustand, klar als Betriebsübersicht.

### Gemeinschaft & Organisation
- `coffee.html` – **P**: Buchung erfassen. Kassenbuch append-only.
- `coffee_form.html` / `coffee_correction.html` – **P**: Buchung / Gegenbuchung.
- `checklists.html` – **P**: Als erledigt vermerken (je Checkliste).
- `checklist_schedules.html` – **P**: Speichern (je Intervall).
- `pinboard.html` – **P**: Aushang anlegen. Aktionsgruppe je Aushang.
- `pinboard_form.html` – **P**: Speichern.
- `birthdays.html` – **P**: Meine Einstellung. Nur MM-TT.
- `birthday_settings.html` – **P**: Einstellung speichern.
- `feeds.html` – **P**: –. Inhaltstyp-Filter Meldungen/Verkehr.

### Nachrichten, Post, Krypto
- `chat.html` – **P**: Verschlüsselt senden. Tabs Wache/Privat/Post.
- `private_chat_home.html` – **P**: Chat öffnen.
- `private_chat_thread.html` – **P**: Verschlüsselt senden.
- `secure_mail_inbox.html` – **P**: Verschlüsselt senden.
- `secure_mail_detail.html` – **P**: – (Nur-Lese-Ansicht).
- `crypto_setup.html` – **P**: Schlüssel einrichten / entsperren.

### Konto, Team, Verwaltung
- `account.html` – **P**: je Formular (Profilbild/Profil/Passwort). Konto-Links als Modulindex.
- `api_tokens.html` – **P**: Token erzeugen. Widerruf je Token.
- `push_settings.html` – **P**: Aktivieren/Deaktivieren.
- `team.html` – **P**: Benutzer anlegen. Offene Registrierungen + Mitglieder.
- `team_form.html` / `team_user_create.html` / `membership_form.html` – Formulare.
- `station_settings.html` – **P**: Speichern.
- `audit_log.html` – **P**: –. Append-only-Tabelle, keine Freitexte.
- `form_errors.html` – **Fragment**, unverändert (`role="alert"`-Zusammenfassung).

## Übergabe-Revisionen

- Dieser Stand ist markup-only und ohne Datenbank lauffähig
  (`config.test_settings`).
- Offen für die Shell-/CSS-Worker: `ww-app`-Body, `app-ui.css`,
  Bootstrap-Einbindung. Die Fachseiten liefern dafür konsistente Haken.
- Kein Commit/Push/Merge/Deploy durch diesen Worker.
