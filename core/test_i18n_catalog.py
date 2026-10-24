"""Tests fuer das Katalogwerkzeug (scripts/i18n_catalog.py).

Der eigene PO-Parser/MO-Compiler ist Ersatz fuer GNU gettext im
Auslieferungscontainer. Diese Tests belegen die kritischen Eigenschaften:
Pluralformen, Kontext, Escapes/UTF-8, mehrzeilige Strings, fuzzy-Behandlung,
Platzhaltervalidierung und die Lesbarkeit durch den stdlib-GNU-Parser.
Wenn ``msgfmt`` vorhanden ist, wird die Ausgabe zusaetzlich gegen GNU
gettext verglichen (sonst sauberer Skip).
"""

from __future__ import annotations

import gettext
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from scripts.i18n_catalog import (
    blocktranslate_msgid,
    expected_mo_catalog,
    extract_python,
    mo_catalog,
    parse_po,
    validate,
    write_mo,
)

FIXTURE = """# Kopf
msgid ""
msgstr ""
"Project-Id-Version: Test\\n"
"Language: en\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Plural-Forms: nplurals=2; plural=(n != 1);\\n"

#: core/a.py:1
msgid "Eintrag"
msgid_plural "Einträge"
msgstr[0] "Entry"
msgstr[1] "Entries"

#: core/a.py:2
msgctxt "menu"
msgid "Öffnen"
msgstr "Open"

#: core/a.py:3
msgid "Er sagte: \\"Hallo\\"\\nund ging.\\tEnde"
msgstr "He said: \\"Hello\\"\\nand left.\\tEnd"

#: core/a.py:4
msgid "Übergabe – Größe"
msgstr "Handover – size"

"""

FUZZY_FIXTURE = """msgid ""
msgstr "Language: en\\nContent-Type: text/plain; charset=UTF-8\\nPlural-Forms: nplurals=2; plural=(n != 1);\\n"

msgid "Erster"
msgstr "First"

#, fuzzy
msgid "Zweiter"
msgstr "Second"
"""


class CatalogParserTests(SimpleTestCase):
    def _write(self, directory: str, content: str) -> Path:
        path = Path(directory) / "django.po"
        path.write_text(content, encoding="utf-8")
        return path

    def test_plural_context_escapes_utf8_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            po = self._write(tmp, FIXTURE)
            entries = parse_po(po)
            by_id = {entry["msgid"]: entry for entry in entries}

            self.assertEqual(by_id["Eintrag"]["plural"], "Einträge")
            self.assertEqual(by_id["Eintrag"]["msgstr_plural"], {0: "Entry", 1: "Entries"})
            self.assertEqual(by_id["Öffnen"]["msgctxt"], "menu")
            self.assertEqual(
                by_id['Er sagte: "Hallo"\nund ging.\tEnde']["msgstr"],
                'He said: "Hello"\nand left.\tEnd',
            )
            self.assertEqual(by_id["Übergabe – Größe"]["msgstr"], "Handover – size")

            mo = Path(tmp) / "django.mo"
            write_mo(entries, mo)
            catalog = mo_catalog(mo)
            self.assertEqual(catalog[("Eintrag", 0)], "Entry")
            self.assertEqual(catalog[("Eintrag", 1)], "Entries")
            self.assertEqual(catalog["menu\x04Öffnen"], "Open")
            self.assertIn("Project-Id-Version: Test", catalog[""])
            self.assertEqual(catalog["Übergabe – Größe"], "Handover – size")
            self.assertEqual(catalog, expected_mo_catalog(entries))

    def test_compiled_plural_entry_works_with_stdlib_ngettext(self):
        """GNU-.mo-Semantik: Plural-Schluessel enthaelt '\\x00'+msgid_plural."""
        with tempfile.TemporaryDirectory() as tmp:
            po = self._write(tmp, FIXTURE)
            entries = parse_po(po)
            mo = Path(tmp) / "django.mo"
            write_mo(entries, mo)

            with mo.open("rb") as handle:
                translations = gettext.GNUTranslations(handle)
            # Variablen statt Literale: der Katalog-Extraktor darf Testfixturen
            # nicht als uebersetzbare Produkttexte einsammeln.
            singular, plural = "Eintrag", "Einträge"
            self.assertEqual(translations.ngettext(singular, plural, 1), "Entry")
            self.assertEqual(translations.ngettext(singular, plural, 3), "Entries")

    def test_fuzzy_comment_belongs_to_following_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            po = self._write(tmp, FUZZY_FIXTURE)
            entries = {entry["msgid"]: entry for entry in parse_po(po)}
            self.assertFalse(entries["Erster"]["fuzzy"])
            self.assertTrue(entries["Zweiter"]["fuzzy"])

            mo = Path(tmp) / "django.mo"
            write_mo(parse_po(po), mo)
            catalog = mo_catalog(mo)
            self.assertIn("Erster", catalog)
            self.assertNotIn("Zweiter", catalog)

    def test_fuzzy_and_plural_gaps_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            po = self._write(tmp, FUZZY_FIXTURE)
            problems = validate(parse_po(po), po, language="en")
            self.assertTrue(any("fuzzy" in problem for problem in problems), problems)

            gap = FIXTURE.replace('msgstr[1] "Entries"', "")
            po_gap = self._write(tmp, gap)
            problems = validate(parse_po(po_gap), po_gap, language="en")
            self.assertTrue(any("Pluralform fehlt" in problem for problem in problems), problems)

    def test_placeholder_validation_catches_missing_and_changed_formats(self):
        with tempfile.TemporaryDirectory() as tmp:
            po = self._write(tmp, FIXTURE)
            self.assertEqual(validate(parse_po(po), po, language="en"), [])

            broken = FIXTURE.replace('msgstr "Handover – size"', 'msgstr "Handover – size for {count}"')
            po_broken = self._write(tmp, broken)
            problems = validate(parse_po(po_broken), po_broken, language="en")
            self.assertTrue(any("Platzhalter weichen ab" in problem for problem in problems), problems)

            dropped = FIXTURE.replace(
                'msgstr[1] "Entries"', 'msgstr[1] "Entries for %(name)s"'
            )
            po_dropped = self._write(tmp, dropped)
            problems = validate(parse_po(po_dropped), po_dropped, language="en")
            self.assertTrue(any("Plural [1]" in problem for problem in problems), problems)

    def test_blocktranslate_msgid_matches_django_runtime_form(self):
        self.assertEqual(
            blocktranslate_msgid("{{ app_name }} auf dem Gerät"),
            "%(app_name)s auf dem Gerät",
        )
        self.assertEqual(
            blocktranslate_msgid("TOTP seit {{ date|date:\"d.m.Y\" }} bestätigt."),
            "TOTP seit %(date)s bestätigt.",
        )
        # Django verdoppelt literale Prozentzeichen im msgid.
        self.assertEqual(blocktranslate_msgid("100 % sicher"), "100 %% sicher")
        # Whitespace/Zeilenumbrueche bleiben wie im Template erhalten.
        self.assertEqual(
            blocktranslate_msgid("Zeile eins\n  Zeile zwei {{ x }}"),
            "Zeile eins\n  Zeile zwei %(x)s",
        )

    def test_msgfmt_parity_when_gnu_gettext_available(self):
        msgfmt = shutil.which("msgfmt")
        if not msgfmt:
            self.skipTest("msgfmt (GNU gettext) nicht installiert")
        with tempfile.TemporaryDirectory() as tmp:
            po = self._write(tmp, FIXTURE)
            gnu_mo = Path(tmp) / "gnu.mo"
            subprocess.run(
                [msgfmt, "--check", "-o", str(gnu_mo), str(po)],
                check=True,
                capture_output=True,
            )
            ours = Path(tmp) / "ours.mo"
            write_mo(parse_po(po), ours)
            self.assertEqual(mo_catalog(ours), mo_catalog(gnu_mo))


class RepositoryCatalogTests(SimpleTestCase):
    """Die eingecheckten Kataloge muessen vollstaendig und aktuell sein."""

    def test_catalogs_validate_and_checked_in_mo_is_current(self):
        for language in ("de", "en"):
            po = settings.BASE_DIR / "locale" / language / "LC_MESSAGES" / "django.po"
            mo = po.with_suffix(".mo")
            entries = parse_po(po)
            self.assertEqual(validate(entries, po, language=language), [], language)
            self.assertTrue(mo.is_file(), f"{mo} fehlt")
            self.assertEqual(mo_catalog(mo), expected_mo_catalog(entries), language)

    def test_english_catalog_has_no_empty_or_identity_translations(self):
        po = settings.BASE_DIR / "locale" / "en" / "LC_MESSAGES" / "django.po"
        # Begriffe, die im Englischen identisch sind (bewusst, kein Versehen).
        # Jeder Eintrag braucht einen Grund; echte Uebersetzungsluecken gehoeren
        # nicht hierher, sondern in den Katalog.
        identical_ok = {
            # Produkt-, Plattform- und Eigennamen
            "Wiki": "etablierter Fachbegriff, im Englischen identisch",
            "openapi.yaml": "Dateiname",
            "/anmelden/qr/": "Route, laut Projektregel unveraenderlich",
            # Protokoll-, Header- und Sicherheitsbegriffe
            "Audit": "Fachbegriff, im Englischen identisch",
            "MFA": "Akronym",
            "E2EE": "Akronym",
            "ID": "Akronym",
            "BIC:": "Bank-Feldkuerzel mit Doppelpunkt",
            "IBAN:": "Bank-Feldkuerzel mit Doppelpunkt",
            "HttpOnly:": "Cookie-Attribut",
            "SameSite:": "Cookie-Attribut",
            "SameSite=": "Cookie-Attribut, Wertzuweisung",
            "Secure:": "Cookie-Attribut",
            "Scopes:": "OAuth-Feld",
            "Authorization: Token …": "HTTP-Headerzeile",
            # Lehnwoerter, die im Deutschen und Englischen gleich lauten
            "Administration": "Lehnwort, identisch",
            "Information": "Lehnwort, identisch",
            "Link": "Lehnwort, identisch",
            "Name:": "Feldbeschriftung, identisch",
            "(Name:": "Fragment einer Feldbeschriftung",
            "Offline": "Lehnwort, identisch",
            "Person": "Lehnwort, identisch",
            "Schema:": "Fachbegriff (Datenbank), identisch",
            "Status": "Lehnwort, identisch",
            "Team": "Lehnwort, identisch",
            "Version": "Lehnwort, identisch",
            # Aus der Hilfe-/Systemseite (Lane A): im Englischen bewusst identisch.
            "Installation": "Lehnwort, identisch",
            "Build %(commit)s": "Versionszeile, Produktwort",
            "HTTP": "Protokollkuerzel",
            "Server": "Fachbegriff, identisch",
            "Slug": "Fachbegriff, identisch",
            "Text": "Feldbezeichnung, identisch",
            "Version %(version)s": "Versionszeile, Produktwort",
            "Revision %(rev_num)s": "Versionszeile, Produktwort",
            "Max.": "Abkuerzung, identisch",
            "Min.": "Abkuerzung, identisch",
            "Passkey": "Fachbegriff, identisch",
            "Passkeys": "Fachbegriff, identisch",
            "Passphrase": "Fachbegriff, identisch",
            # Fachmodule (MPG/Lager): Normen, Kennungen und Lehnwoerter
            "PZN": "Pharmazentralnummer, Kennung",
            "Optional": "Lehnwort, identisch",
            "Details": "Lehnwort, identisch",
            "OK": "Lehnwort, identisch",
            "Check": "Lehnwort, identisch",
            "Normal": "Lehnwort, identisch",
            "AdBlue": "Markenname",
            "AdBlue (%)": "Markenname mit Einheit",
            "UDI-DI (GTIN):": "Normkennung",
            # Platzhalterzeile ohne uebersetzbaren Text
            "%(category)s &middot; Version %(version)s": "nur Platzhalter und Produktwort",
        }
        identical = set()
        for entry in parse_po(po):
            if not entry["msgid"]:
                continue
            self.assertTrue(entry["msgstr"].strip(), f"leer: {entry['msgid']}")
            if entry["msgstr"] == entry["msgid"]:
                identical.add(entry["msgid"])
        self.assertEqual(identical, set(identical_ok), f"unbegruendet identisch: {sorted(identical - set(identical_ok))}")


class ExtractionTests(SimpleTestCase):
    """Import-Aliase muessen erkannt werden, sonst fehlen UI-Strings im Katalog."""

    def test_gettext_alias_is_extracted(self):
        source = (
            "from django.utils.translation import gettext_lazy as _lazy\n"
            "LABEL = _lazy(\"Fahrzeuge/Geräte\")\n"
            "OTHER = some_function(\"nicht extrahieren\")\n"
        )
        entries = extract_python(Path("core/beispiel.py"), source)
        self.assertEqual([entry[1] for entry in entries], ["Fahrzeuge/Geräte"])


class BlocktranslateRenderingTests(TestCase):
    """Blocktranslate-Strings muessen im echten Rendering uebersetzt werden."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="ohne-mitgliedschaft@example.org", password="test-password-12345"
        )

    def test_access_page_renders_english_blocktranslate(self):
        client = Client()
        client.force_login(self.user)
        client.cookies["wachbuch_language"] = "en"
        response = client.get(reverse("access"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("Signed in as <strong>", content)
        self.assertIn("must assign the account to a rescue station", content)
        self.assertNotIn("Angemeldet als", content)

    def test_access_page_renders_german_blocktranslate(self):
        client = Client()
        client.force_login(self.user)
        client.cookies["wachbuch_language"] = "de"
        response = client.get(reverse("access"))
        content = response.content.decode("utf-8")
        self.assertIn("Angemeldet als <strong>", content)
        self.assertNotIn("Signed in as", content)

    def test_placeholder_values_are_interpolated(self):
        client = Client()
        client.force_login(self.user)
        client.cookies["wachbuch_language"] = "en"
        content = client.get(reverse("access")).content.decode("utf-8")
        self.assertIn(self.user.username, content)
