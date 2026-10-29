# Deutsche Textqualität – Quellenmaßstab, Korrekturen und Restbefunde

Stand: 2026-10-19. Geltungsbereich: deutsche Quelltexte des Arbeitsbaums
`/opt/data/workspace/wachbuch-release-20261019` (Basis-Commit `98bc6d4`).
Kein Commit, kein Push, kein Deploy, keine Veröffentlichung.

Dieses Dokument ist **kein Vollständigkeitsnachweis**. Es belegt, welche
Textstellen geprüft, welche Korrekturen angewandt und welche Restbefunde
bewusst offen gelassen wurden.

## 1. Prüfmittel und Korpus

- Prüfwerkzeug: eigene LanguageTool-Instanz, LanguageTool **6.8**
  (Build 2026-09-18), auf dem Hetzner-VPS über SSH-Stdin an die Loopback-API.
  Kein Cloud-Fallback, keine Weitergabe an Dritte.
- Korpus: 2.683 Quellsegmente, davon 2.232 eindeutig, 245.427 Zeichen, 22 Batches.
  Erfasst werden deutsche `.po`-Quellen, Python-Meldungen und Markdown-Prosa;
  Codeblöcke, englische Kataloge und Nutzerdaten sind ausgeschlossen.
- Wichtig: **2.561 Hinweise sind keine 2.561 Fehler.** LanguageTool meldet
  Kandidaten; ein Teil sind Extraktionsartefakte, technische Bezeichner,
  Zitate oder Stilhinweise.
- Der Hinweis-Offset im Report bezieht sich auf das gereinigte Textfragment,
  nicht auf die Originaldatei. Zeilennummern im JSON sind deshalb Näherungen
  und vor einer Änderung immer am Quelltext zu prüfen.

Reproduktion:

```bash
/opt/data/workspace/agy-eval-wachbuch/.venv/bin/python \
  /opt/data/scripts/languagetool_check.py \
  --root /opt/data/workspace/wachbuch-release-20261019 \
  --include-md --out /opt/data/state/wachbuch-languagetool/post-corrections-final.json
```

## 2. Angewandte Korrekturen

| Gruppe | Umfang | Beleg |
| --- | --- | --- |
| Markdown-Fließtext, Umlaut-Transliteration | 526 Ersetzungen in 425 Zeilen, 18 Dateien | LanguageTool-Tokenmap, reine `ae/oe/ue/ss`-Substitution |
| Python-Meldungen (Modelle) | 27 Ersetzungen in `core/wachalltag_models.py`, `core/models.py` | fokussierter LT-Lauf: 25 Segmente, 0 Befunde |
| Kongruenz/Artikel sichtbarer UI | 3 Stellen (Aktivierungshinweis, zwei Doku-Sätze) | LT + unabhängige Mistral-Large-Prüfung |
| Kataloge | 170 Einträge de/en, `.mo` neu kompiliert | `scripts/i18n_catalog.py check` |

Maschinelle Prüfung der Fließtext-Änderungen: 425 geänderte Zeilen, 1.056
geänderte Segmente, **0 nicht-transliterierende Änderungen** (jedes geänderte
Segment ist ausschließlich `ae→ä`, `oe→ö`, `ue→ü`, `ss→ß`). Codeblöcke,
Inline-Code, URLs, Pfade/Slugs, Tabellenzeilen und Blockquote-Zeilen wurden
nicht verändert; dadurch bleiben Befehle, Versionen und Quellzitate unangetastet.

Nicht geändert und ausdrücklich geschützt:

- URL-Slugs und Pfade (`/uebersicht/`, `/vorfuehrung/`),
- CSS-Klassen und Dateinamen (`is-vorfuehrung`),
- technische Bezeichner (`Korrelations-ID`, `SameSite`, `HttpOnly`, `WebPush`,
  `Ciphertext`, `Outbox`, `ECDH`),
- Produkt- und Gattungsnamen (`Wachwerk`, `Wachbuch`),
- Quellzitate in Blockquotes sowie Code- und Kommandozeilen.

## 3. Rollenformulierung „Master-Admin“

Die Stelle `templates/core/activate_account.html` / `locale/*/django.po` lautete
„Bitte wende dich an **die** Master-Admin deiner Wache“. Die Rolle heißt im
gesamten Produkt „**der** Master-Admin“ (Glossar, übrige UI-Texte, README).
Korrigiert wurde deshalb minimal auf „an **den** Master-Admin deiner Wache“.

Die ebenfalls geprüfte neutrale Variante „an die Administration deiner Wache“
wurde verworfen: Sie führt einen Akteur ein, den die Oberfläche sonst nicht
kennt, und wäre in einer Support-Anweisung mehrdeutig. Die Entscheidung ist
unabhängig gegengeprüft (Mistral Large, `finish_reason=stop`, Urteil
„maskuliner Artikel gemäß Glossar“).

## 4. Einordnung der Hinweise (definitive Gruppen)

| Gruppe | Bedeutung | Behandlung |
| --- | --- | --- |
| `accepted` / `source_true_error` | im Quelltext bestätigt und korrigiert | 556 Textstellen (526 + 27 + 3) |
| `protected_code_or_quote` | Vorkommen in Code, Slug, Zitat, Tabelle | unverändert, siehe Abschnitt 2 |
| `technical_term` | Fachbegriff, kein Tippfehler | 150 Kandidaten, unverändert |
| `extraction_artifact` | Fragment-/Platzhalterartefakt der Extraktion | 325 Kandidaten, kein Produktfehler |
| `deferred_runtime_verification` | nur im laufenden System belegbar | 1.495 Kandidaten, nicht handgeprüft |

Beispiele für Extraktionsartefakte, die **nicht** als Fehler gewertet wurden:
`Wert Wert` und `Wert .` entstehen, weil Variablenplatzhalter beim Extrahieren
entfernt werden; mehrzeilige Sätze erzeugen Wiederholungs- und Groß-/Klein-
schreibungsbefunde („Bitte … Bitte …“) über Segmentgrenzen hinweg. Diese
Befunde dürfen keine UI-Umschreibung auslösen.

## 5. Restbefunde (bewusst offen)

- **Textchoicen-Labels** in `core/wachalltag_models.py` (`Gerät`, `Schlüssel`,
  `Gebäude`, `Eingeschränkt`, `Außer Betrieb`, `Rückgabe`, `Täglich`,
  `Wöchentlich`) tragen seit Migration `0064_wachalltag_umlaut_labels` echte
  Umlaute. Die Migration ändert nur Metadaten (`sqlmigrate`: no-op), die
  gespeicherten Werte bleiben gleich.
- **Fachmodule, JavaScript-Texte, Admin-Oberfläche und Website (`site/`)** sind
  nicht Teil dieses Laufs; dort stehen weitere Umlaut- und Stilbefunde an.
- **1.495 manuelle Prüffälle** wurden nicht einzeln handgeprüft. Die Zahl ist
  eine Obergrenze offener Kandidaten, keine Fehlerzahl.
- Der LanguageTool-Nachlauf bewertet statischen Quelltext, keine gerenderte
  Oberfläche und kein Browser-Verhalten.

## 6. Nachweise

- `manage.py check`: keine Befunde.
- `makemigrations --check --dry-run`: keine Änderungen.
- Testsuite: 538 Tests, OK, 2 übersprungen (Umgebung: `MFA_ENABLED=true`,
  `DJANGO_DEBUG=false`, eigene SQLite-Datei, `config.test_settings`).
- `ruff check --select E4,E7,E9`: keine Befunde.
- `site/tests/check_site.py`: 13 Tests OK.
- `scripts/i18n_catalog.py check`: Kataloge vollständig, `.mo` aktuell.
- Gerenderte Prüfung des geänderten msgid: deutsch „an den Master-Admin“,
  englisch „Please contact your station's master admin …“.
- `git diff --check`: keine Whitespace-Fehler.

## 7. Nachlauf LanguageTool (nach Codefreeze)

| Kennzahl | vorher | nachher |
| --- | --- | --- |
| Hinweise gesamt | 2.561 | 2.018 |
| Umlaut-Transliterationskandidaten | 568 | 20 |
| Segmente | 2.683 | 2.683 |
| Zeichen | 245.427 | 244.874 |

Die verbleibenden Hinweise enthalten Wiederholungs-, Komma- und
Groß-/Kleinschreibungsmeldungen aus der Segmentierung sowie technische
Bezeichner. Nicht alle übrigen Hinweise sind manuell klassifiziert; sie sind
Kandidaten und dürfen weder als bestätigte Fehler noch pauschal als Fehlalarme
gezählt werden.

### 7.1 Nachträglich behobene Doku-Reststellen (14 Zeilen)

Die nachstehende Tabelle dokumentiert den früheren Restbefund: Das erste
Ersetzungswerkzeug ließ Schrägstrich-Komposita und Tabellenzellen bewusst aus,
um Slugs, Pfade und Tabellenwerte nicht pauschal umzuschreiben. Diese konkreten
14 Zeilen wurden anschließend separat durch Gemini 3.8 High geprüft und vom
Parent übernommen. Maschinell nachgewiesen: ausschließlich deutsche
Transliterationskorrekturen, identischer Inline-Code und keine URL-Änderung.
Der zuvor ausgewiesene LanguageTool-Nachlauf ist ein historischer Stand vor
 diesen letzten Korrekturen, keine Aussage über einen neuen Nullbefund.

| Datei | Zeile | Wort | Kontext |
| --- | --- | --- | --- |
| CHANGELOG.md | 128 | `Empfaenger` | `Absender/Empfaenger` |
| CHANGELOG.md | 167 | `Feed-DB-Passwoerter` | `App-/Feed-DB-Passwoerter` |
| COMPLIANCE.md | 98 | `Abhaengigkeiten` | `Abhaengigkeiten/Image-Digest` |
| DESIGN-SYSTEM.md | 128 | `Weiss` | `Schwarz/Weiss` |
| PRODUKT-FAHRPLAN.md | 26 | `Geraete` | `Geraete/Statusboard` |
| PRODUKT-FAHRPLAN.md | 43 | `Aushaenge` | `(Aushaenge/Notizen)` |
| PRODUKT-FAHRPLAN.md | 59 | `oeffentlich` | `(oeffentlich/privat/...)` |
| PRODUKT-FAHRPLAN.md | 94 | `Prueffristen` | `Prueffristen/Intervalle` |
| PRODUKT-FAHRPLAN.md | 95 | `Geraetekarte` | `Geraetekarte/Pruefhistorie` |
| PRODUKT-FAHRPLAN.md | 101 | `Lehrgaenge` | `Tauglichkeiten/Lehrgaenge` |
| PRODUKT-FAHRPLAN.md | 108 | `Loeschwasser` | `Hydranten/Loeschwasser` |
| PRODUKT-FAHRPLAN.md | 113 | `Design-Paritaet` | `Navigation/Design-Paritaet` |
| ROADMAP.md | 58 | `ausser` | `eingeschränkte/ausser` |
| AUDIT-2026-07.md | 64 | `Pruefung` | Tabellenzelle |

Die tabellierten Fundstellen sind damit abgearbeitet. Die vollständige deutsche
Sprachabnahme ist dadurch nicht abgeschlossen: andere Kandidaten und bislang
nicht übersetzte Fachmodule bleiben separat zu prüfen.
