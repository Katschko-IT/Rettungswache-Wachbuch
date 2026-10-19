# i18n Etappe 1 – Checkpoint (de/en)

Stand: 2026-10-19. Arbeitsbaum `/opt/data/workspace/wachbuch-release-20261019`
(Basis-Commit `98bc6d4`), Integration aus der Lane
`/opt/data/workspace/wachbuch-i18n-agy-20261019`. Kein Commit, kein Push, kein
Deploy, keine Veröffentlichung.

## Was in dieser Etappe übersetzt ist

Sichtbare feste Texte der Anmelde-, Setup-, Aktivierungs- und Fehlerpfade
sowie die Formulare `TotpConfirmForm`, `RegistrationForm`, `SetupWizardForm`,
`ActivationPasswordForm`:

- `templates/base.html` (Navigation, Sprachumschalter, Fußzeile)
- `templates/registration/login.html`, `mfa_verify.html`, `mfa_setup.html`, `mfa_manage.html`
- `templates/core/setup_wizard.html`, `setup_token.html`, `activate_account.html`,
  `access.html`, `form_errors.html`
- `templates/errors/{400,403,404,429,500}.html`
- `core/errors.py` (Fehlercode-Labels), `core/forms.py` (vier Formulare),
  `core/setup_views.py`, MFA-Meldungen in `core/views.py`,
  `core/waste_sync.py` (nur Umlautkorrektur)

Sprachwahl: Deutsch ist Standard (`LANGUAGE_CODE = "de"`). Ein Sprachcookie
(`wachbuch_language`, HttpOnly, SameSite=Lax, `Secure` entsprechend
`SECURE_COOKIES`, ein Jahr) oder die Profilsprache `UserProfile.language`
(Migration `0031`) schaltet auf Englisch. Der Wechsel läuft über
`POST /sprache/` (CSRF-geschuetzt, kein Sprachprefix in URLs, keine
Session-Schreibzugriffe bei anonymen Wechseln).

## Was ausdrücklich **nicht** übersetzt ist

Diese Etappe macht die genannten Pfade zweisprachig, **nicht die Anwendung**:

- Dashboard, Übergaben, Kaffeekasse, Pinnwand, Chat, Aufgaben, Admin-Oberfläche,
  JavaScript-Texte und die Dokumentation bleiben deutschsprachig.
- Die Website (`site/`) ist nicht Teil dieser Etappe.
- Eine eingeloggte Seite kann daher teilweise deutsch bleiben. Das ist der
  vereinbarte Etappenzuschnitt, keine vollständige englische Oberfläche.

## Kataloge

- 169 Quellstrings (deutsche `msgid`), dieser Wert ist die Summe der markierten
  Strings aus Python, Templates und JavaScript.
- `locale/de/LC_MESSAGES/django.po`: Identitätskatalog (deutsche Quelle).
- `locale/en/LC_MESSAGES/django.po`: vollständig übersetzt, keine leeren
  `msgstr`, keine `fuzzy`-Eintraege, Platzhalter identisch.
- `locale/*/LC_MESSAGES/django.mo` sind eingecheckt. Der Container braucht damit
  **kein** GNU gettext zur Laufzeit.
- Wichtig: `{% blocktranslate %}`-Msgids enthalten `%(name)s`, nicht `{{ name }}`.
  Django ersetzt Variablen zur Laufzeit; der Katalog muss diese Form treffen.
  Ein Katalog mit `{{ name }}` wäre still unübersetzt (Mischsprache).

## Katalogwerkzeug `scripts/i18n_catalog.py`

`xgettext`/`msgfmt` stehen im Auslieferungsimage nicht zur Verfügung. Das Skript
ersetzt `makemessages`/`compilemessages` mit der Standardbibliothek:

- `extract` – sammelt `gettext`/`ngettext`/`pgettext`/`npgettext`,
  `{% translate %}`, `{% blocktranslate %}` (inkl. `{% plural %}`) und
  `gettext()` in JavaScript; behält vorhandene Übersetzungen.
- `compile` – prüft Platzhalter, Pluralformen, fehlende Übersetzungen, `fuzzy`
  und schreibt GNU-kompatible `.mo`-Dateien.
- `check` – prüft zusätzlich, ob die eingecheckten `.mo`-Dateien zum `.po`
  passen (verhindert veraltete Kataloge im Image). Läuft in der CI.

GNU-Kompatibilität ist belegt durch: Lesen über `gettext.GNUTranslations`,
Byte-Vergleich der Kataloginhalte mit einer von `polib` 1.2.0 erzeugten `.mo`
(identisch) sowie einen Test, der bei vorhandenem `msgfmt` die Ausgabe gegen
GNU gettext vergleicht (`core/test_i18n_catalog.py`, wird ohne `msgfmt`
übersprungen).

## Liefersicherheit

- `Dockerfile` kopiert `locale/` in Build- und Runtime-Stage. Vorher fehlte das:
  Im Image wären alle Übersetzungen still auf Deutsch zurückgefallen.
- CI: `python scripts/i18n_catalog.py check` und ein Image-Smoke-Test, der
  `/app/locale/en/LC_MESSAGES/django.mo` öffnet und `Anmelden -> Sign in`
  nachweist.

## Terminologiepruefung (Mistral Large)

169 Einträge, zwei Anfragen an `mistral-large-latest` (HTTP 200,
`finish_reason=stop`, Modell in der Antwort bestätigt). 14 Hinweise, davon
4 übernommen und 10 mit Begründung verworfen (u. a. "rescue station" bleibt
für "Rettungswache" stehen, weil das Glossar nur "Wache = station" festlegt;
zwei Hinweise waren in sich widersprüchlich). Details:
`/opt/data/state/wachbuch-i18n-phase1/abschluss/mistral-review/`.

## Verifikation

- Lane: `manage.py check`, `makemigrations --check`, 113 gezielte Tests,
  538 Tests gesamt (OK, 2 übersprungen; Basis-Release 504), Ruff E4/E7/E9,
  13 Site-Tests, `git diff --check`, Katalogcheck.
- Release: gleiche Suite nach Integration (siehe Commit-freier Status unten).
- Browser (Chromium, lokaler Server, synthetische Daten, CSRF und MFA aktiv):
  39/39 Prüfungen – echter Login, Sprachwechsel, Formularfehler in beiden
  Sprachen, Cookie-Attribute, offener Redirect blockiert, 403 ohne CSRF,
  Rollen unverändert, `/uebergaben/`-Links ohne Sprachprefix, 404 de/en,
  QR-Start weiterhin funktionsfähig.

## Offene Punkte (nächster Schnitt)

1. Fachseiten und Dashboard-Übersetzungen (Übergaben, Kasse, Pinnwand, Chat,
   Aufgaben), Admin-Oberfläche, JavaScript-Texte.
2. Website `site/` und Dokumentation auf Englisch.
3. Nachweise/Sprachwahl im Profil-UI sichtbar machen (bisher nur über
   Sprachumschalter und Migration).
4. Redaktioneller LanguageTool-Lauf über die deutschen Quellstrings.
