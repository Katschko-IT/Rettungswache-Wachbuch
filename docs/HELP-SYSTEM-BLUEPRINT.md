# Hilfe, Wiki, Systemdiagnose und Versionierung — Architekturvertrag (H0)

Status: Entwurf für den ersten Vertikalschnitt (H1/H3). Keine Veröffentlichung.
Grundlage: `docs/../wachbuch-help-system-plan.md` (Bauplan) und der tatsächlich
gelesene Code dieses Releasebaums (`core/version.py`, `core/access.py`,
`core/models.py`, `config/settings.py`, `core/i18n.py`, `core/urls.py`,
`templates/base.html`).

## 1. Geltungsbereich dieses Slices

Enthalten:

- **H1** lokale, mitgelieferte Produkthilfe (de/en) mit lokaler Suche.
- **H3** Versionsanzeige und geschützte Systemseite mit minimaler Diagnose.

Nicht enthalten (bewusst später, siehe Roadmap):

- **H2** Wachen-Wiki mit Revisionen und optimistischer Nebenläufigkeit.
- **H4** Fehlerereignis-Collector und Supportexport.
- Jegliche Änderung an API-Prefixen, Enum-Werten, Session-/MFA-Verträgen.

## 2. Rollen- und Zugriffsvertrag

Bestehende Mechanismen werden wiederverwendet, kein zweiter Auth-Stack:

| Fläche | Decorator | Wirkung |
|---|---|---|
| `/hilfe/`, `/hilfe/<slug>/` | `membership_required()` | angemeldet **und** aktive Mitgliedschaft in einer aktiven Wache; sonst 302 auf Login bzw. `/zugang/` |
| `/system/` | `membership_required({Membership.Role.ADMIN})` | serverseitig fail-closed; Mitglieder/Schichtleitung/Auditor erhalten 403 |

Produkthilfe ist **stationlos**: alle Wachen sehen denselben Produkttext. Sie
enthält keine wacheneigenen Inhalte, keine Patientendaten, keine internen
Dokumente (AGENTS, Audit-/Review-Logs, Evidence). Die Wachen-Wiki-Inhalte aus H2
werden diese Fläche erst später ergänzen und dann stationsgebunden gefiltert.

## 3. Datenfluss H1

1. Redaktionelles Manifest `core/help_data/articles.json` (im Image enthalten,
   weil `core/` per Dockerfile kopiert wird).
2. `core/help.py` validiert beim ersten Zugriff: ASCII-Slug
   `^[a-z0-9][a-z0-9-]{0,59}$`, Sprache `de|en`, nichtleere Titel/Summary,
   nichtleere Abschnitte, keine doppelten `(slug, language)`. Fehler führen zu
   `HelpContentError`, nie zu Pfad- oder Inhaltsausgabe.
3. Anzeige über Django-Templates mit Autoescape; keine eigene Markdown-Engine,
   kein `|safe`, keine HTML-Fragmente aus dem Manifest.
4. Suche: reine In-Memory-Suche über `casefold()`, Limit 1..50, Query auf 120
   Zeichen begrenzt, keine Regulär-Ausdrücke aus Nutzereingaben, kein Netz.

Ein vom Benutzer gewählter Dateipfad ist an keiner Stelle möglich; der Pfad wird
ausschließlich aus `__file__` abgeleitet.

## 4. Datenfluss H3

- Version: `settings.APP_VERSION`, gespeist aus `core/version.py` (0.16.0) bzw.
  `APP_VERSION`-Umgebungsvariable des Builds.
- Build-Kennung: `APP_BUILD_COMMIT`, nur bei `^[0-9a-fA-F]{7,40}$`; sonst
  „nicht hinterlegt“.
- Datenbank: `SELECT 1` read-only, Fehlerklasse wird zu „nicht erreichbar“.
- Migrationen: `MigrationRecorder` (angewendet) gegen `MigrationExecutor.loader`
  Blattknoten (offen). Nur Zähler/Namesliste, keine freie SQL-Eingabe.
- Cache: Backend-Klassenname aus `settings.CACHES["default"]`, Warnung wenn
  nicht dauerhaft (LocMem).
- Releasehinweis: statisch aus `APP_VERSION`; **kein** Updater, kein Download,
  keine Installationssteuerung.

Verboten und durch Tests abgesichert: Git-/Shell-/Docker-Aufrufe pro Request,
Envdump, Hostpfade, Secrets, externe HTTP-Aufrufe, Rohlogs.

## 5. Bedrohungsmodell (Auszug)

| Risiko | Gegenmaßnahme |
|---|---|
| Pfad-Traversal über Artikelpfad | Manifest-Allowlist, Pfad aus `__file__`, Slug-Regex, `<slug:>`-Converter, 404-Test |
| XSS über Suche/Artikel | Autoescape, keine Nutzereingabe in `|safe`/Markdown, Escaping-Test mit `<script>` |
| Rechteausweitung | vorhandene `membership_required`-Semantik, Systemseite Admin-only, 403-Tests je Rolle |
| Datenabfluss über Diagnose | feste Feldliste, keine Exception-Texte, Sentineltest für Env |
| Netzabhängigkeit / Offline | Suche und Artikel rein lokal, Netzwerk-Mocks im Test |
| Falsche Versionsaussage | Build-Kennung nur bei gültigem Hex, sonst ehrlich „nicht hinterlegt“ |

## 6. Roadmap und Abnahmekriterien

**Phase 1 (dieser Slice, H1+H3)**

- A1 Anonym → 302 Login; Mitglied → 200; ohne Mitgliedschaft → 302 `/zugang/`.
- A2 Systemseite: Admin 200, Mitglied/Schichtleitung 403, anonym 302.
- A3 7 Artikel × de/en, Manifestrevision sichtbar, Umlaute korrekt.
- A4 Suche: casefold, Umlaute, Limit, leere/exotische Eingaben, XSS escaped.
- A5 404 für unbekannten Slug und Traversal; nur GET (POST 405).
- A6 Keine externen Netzaufrufe, kein Env-/Pfad-Leak, kein Secret im Body.
- A7 Katalog `extract/compile/check` grün, `makemigrations --check`, `check`,
  Ruff E4/E7/E9, gezielte und vollständige Suite.

**Phase 2 (H2)** Wiki-Modell, Revisionen, 409-Konflikt, Archivierung,
Stationsgrenze, XSS-/Historien-Tests.

**Phase 3 (H4)** bereinigte 5xx-Ereignisse, Collector-Rekursionsschutz,
Supportexport mit Allowlist, `no-store`, Dateinamen-/Contenttype-Tests.

**Phase 4 (H5)** Integration in den Releasebaum nach Sprachkorrektur,
Image-Build mit Hilfeartefakt, Browser-/Tastatur-/390-px-Abnahme, unabhängiges
Modellreview, Parent-Nachabnahme.

## 7. Offene Grenzen

- Kein Browser-/Touch-Nachweis in diesem Subagentenlauf (Parent-Abnahme).
- Keine Aussage über Produktionsimage, solange der Slice nicht integriert ist.
- H2/H4 absichtlich nicht begonnen.
