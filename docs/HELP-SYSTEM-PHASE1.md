# Hilfe & System — Phase 1 (H1/H3) Umsetzungs- und Abnahmeprotokoll

Isolierte Lane: `/opt/data/workspace/wachbuch-help-system-lane`
Basis: Releasebaum `wachbuch-release-20261019`, HEAD `98bc6d4`, 54 modifizierte +
56 unversionierte Produktdateien als Baseline übernommen (kein `.git`, keine
Evidence-, DB-, Venv- oder Cache-Dateien). Baseline-Hashmanifest:
`/opt/data/state/wachbuch-help-system/phase1/baseline-manifest.json` (577 Dateien).

## Neue Dateien

| Datei | Zweck |
|---|---|
| `core/help.py` | Manifest-Loader, Validierung, lokale Suche (Autorschaft: Mistral Large 4, siehe Providernachweis; Orchestrator-Fixes dokumentiert) |
| `core/help_data/articles.json` | kuratiertes Manifest, 7 Artikel × de/en, Revision `2026-10-19.1` |
| `core/help_views.py` | Hilfe-, Artikel- und Systemansicht |
| `templates/core/help_index.html` | Übersicht + Suche |
| `templates/core/help_article.html` | Artikeldarstellung mit Quelle/Stand |
| `templates/core/system_status.html` | Admin-Diagnose |
| `core/test_help_system.py` | 31 Abnahmetests |
| `docs/HELP-SYSTEM-BLUEPRINT.md` | H0-Architekturvertrag, Bedrohungsmodell, Roadmap |

## Geänderte Dateien

| Datei | Änderung |
|---|---|
| `core/urls.py` | Import `help_views`, drei GET-Routen (`/hilfe/`, `/hilfe/<slug>/`, `/system/`) |
| `templates/base.html` | ein Nav-Link „Hilfe“ (alle Mitglieder), Footer-Link „Hilfe“ |
| `locale/de/LC_MESSAGES/django.po|.mo` | neue msgids, bestehende 169 Übersetzungen erhalten |
| `locale/en/LC_MESSAGES/django.po|.mo` | neue msgids + 38 englische Übersetzungen ergänzt |
| `core/test_i18n_catalog.py` | bestehende Identitäts-Allowlist um vier im Englischen bewusst identische Begriffe erweitert (Administration, Version, Installation, Build-Placeholder) |

Keine Änderung an API-Prefixen, Enum-Werten, Session-, Login- oder MFA-Pfaden,
keine Migration.

## Providernachweis (real, nicht behauptet)

- GLM 5.3 über Mistral (`zai-glm-5-3`), Tool-Probe `record_probe`:
  429 `backend_out_of_capacity`, Code `3801` — zweimal (Erstprobe des Parents,
  erneute Probe nach Backoff in dieser Lane). Kein GLM-Codeartefakt.
  Belege: `phase1/glm53-probe-attempt1.json`.
- Mistral Large 4 (`mistral-large-latest`): HTTP 200, `finish_reason=tool_calls`,
  gültiges Tool-JSON `{"status":"ok","model":"mistral-large-latest"}`
  (`phase1/mistral-large-latest-probe.json`).
- Autorschaft `core/help.py`: Mistral Large 4, ein API-Aufruf, Antwort
  `finish_reason=stop`, 6064 Zeichen (`phase1/mistral-authored-help.py`).
  Der Orchestrator hat vier deterministische Korrekturen angewendet und im
  Diff dokumentiert: `import re` vor die erste Verwendung gezogen,
  `data.get(...)` statt `data[...]`, unbenutzte Walrus-Zuweisung entfernt,
  leere Abschnittstexte abgelehnt sowie `reload()`/Cache-Override testbar
  gemacht. Diese Fixes sind **nicht** Mistral-Autorschaft.

## Tests

- Gezielt: `core.test_help_system` → 31 Tests, OK.
- Rollen: anonym 302, Mitglied 200, ohne Mitgliedschaft 302, System Admin 200 /
  Mitglied + Schichtleitung 403, POST 405.
- Inhalt: 7×de/en, Umlaute, Englisch exakt, keine internen Dokumente.
- Suche: `Übergabe`/`übergabe`/`ÜBERGABE`, Limit-Klemme, ``, Emoji,
  5000-Zeichen-Query, `<script>` escaped, `javascript:` nicht verlinkt.
- System: ungültige Build-Kennung → „nicht hinterlegt“, gültige `98bc6d4`
  sichtbar, Env-Sentinel und `SECRET_KEY` nicht im Body, keine Netzaufrufe.

## Vollsuite und Browser

- `manage.py test --settings=config.test_settings`: **569 Tests, OK, 2 Skips**.
- Playwright (venv `/opt/data/tools/wachwerk-browser-venv`, Chromium,
  390×844, echter Login): Hilfeübersicht mit 7 Artikeln, Suche „Übergabe“
  inklusive Umlaut-URL, Artikel „Übergaben“ mit Quelle/Stand, Systemseite als
  Admin; Resource-Timing zeigt **keine externen Hosts**. Belege:
  `phase1/browser-check.json`, `phase1/browser-help-390.png`.
- Einschränkung: Testeinstellungen deaktivieren Whitenoise und laufen mit
  `DEBUG=false`, daher ohne CSS. Die visuelle Abnahme bleibt Parent/H5.
- Kein Serverprozess verblieben (runserver nach Prüfung beendet).

## Integration durch Parent

1. Sprachkorrektur-Stand ist inzwischen abgeschlossen (556 Korrekturen, 170
   Katalogeinträge). Diese Lane basiert **vor** diesen Textkorrekturen.
2. Übernahme: neue Dateien unverändert; bei `core/urls.py`,
   `templates/base.html` und `locale/*` konfliktgeprüft mergen.
3. Katalog nicht vollständig überschreiben: `scripts/i18n_catalog.py extract`
   im Zielbaum laufen lassen und nur die neuen msgids ergänzen, damit die
   Sprachkorrektur nicht zurückgedreht wird.
4. Danach Vollsuite im Zielbaum (Soll: 538 + 31 = 569 Tests, 2 Skips) und
   Image-Build mit `core/help_data/articles.json`.
