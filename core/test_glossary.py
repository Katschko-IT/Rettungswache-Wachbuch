"""Glossar als verbindliche Regel (Roadmap 0.27, Baustein 9 „Glossar zuerst“).

``docs/DESIGN-SYSTEM.md`` legt im Abschnitt „Glossar“ zwischen
``<!-- glossar:begin -->`` und ``<!-- glossar:end -->`` die Begriffe der
Oberfläche fest. Jedes Wort in Backticks in der Spalte „Nicht verwenden“ ist
für neue übersetzbare Texte gesperrt. Bestehende Vorkommen sind je Begriff als
Ausgangsstand eingefroren (Ratsche) und verschwinden mit der Umbenennung in
UX-PLAN B4 (0.28). Weniger Vorkommen als im Ausgangsstand sind immer erlaubt:
Andere Pakete dürfen alte Wörter entfernen, ohne diesen Test anzufassen.

Geprüft werden die markierten Texte, die ``scripts.i18n_catalog.collect()``
in Python, Templates und JavaScript findet (msgid und Pluralform). Inhalte,
die eine Wache selbst anlegt, und englische Übersetzungen prüft der Test
nicht; die Spalte „Englisch“ ist verbindliche Dokumentation.

Die Tabelle „Modulnamen“ (``<!-- modulnamen:begin -->``) ist das Ziel für B4.
Hier wird nur geprüft, dass sie zur Seite „Mehr“ und zur Leiste passt.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from core.navigation import CATALOG
from scripts.i18n_catalog import collect

ROOT = Path(settings.BASE_DIR)
DESIGN_SYSTEM = ROOT / "docs" / "DESIGN-SYSTEM.md"
MORE_TEMPLATE = ROOT / "templates" / "core" / "more.html"
AGENTS = ROOT / "AGENTS.md"

GLOSSARY_MARKERS = ("<!-- glossar:begin -->", "<!-- glossar:end -->")
GLOSSARY_HEADER = ["Begriff", "Englisch", "Nicht verwenden", "Bedeutung"]
MODULE_MARKERS = ("<!-- modulnamen:begin -->", "<!-- modulnamen:end -->")
MODULE_HEADER = ["Bereich", "Kachel, h1 und Titel", "Leiste", "Heute abweichend"]
EMPTY_CELLS = {"", "–", "-"}

# Begriffe, auf die sich andere Pakete und Tests verlassen.
CORE_TERMS = (
    "Wache",
    "Übergabe",
    "Gelesen – quittieren",
    "Lesebestätigung",
    "Mangel",
    "Erledigt",
    "Dienstanweisung",
    "Fahrzeugzustand",
    "Einsatzbereit",
    "Eingeschränkt",
    "Desinfektion",
    "Werkstatt",
    "Außer Dienst",
    "Außer Betrieb nehmen",
    "Gesperrt",
    "Medizingerät",
    "Funktionskontrolle",
    "Wachenterminal",
    "Sperrbildschirm",
)

# Ausgangsstand 0.27 (gezählt an 7e38617): Anzahl der übersetzbaren Texte je
# gesperrtem Begriff. Abbau mit UX-PLAN B4 (0.28). Erhöhen nur mit Begründung
# für ein altes Vorkommen; neue Texte nutzen den Begriff der ersten Spalte.
BASELINE = {
    "Cockpit": 4,  # Fahrzeug- und Geräteseite, Kachel „Cockpit & Schichtübernahme“
    "Desk": 1,  # „Organisation & Desk“
    "Asset": 1,  # „Assets einsatzklar“ (Auswertung)
    "Poolbestand": 1,  # Kachel „Geräte & Poolbestand“
    "Logbuch": 1,  # Kachel „Audit-Logbuch“
    "SOP": 8,  # Orga-Modul und Seiten der Dienstanweisungen
    "Display-Token": 1,  # Kachel „Display-Tokens“
    "Push-Mitteilung": 1,  # Kachel „Push-Mitteilungen“
    "Fahrzeugstatus": 10,  # Audit-Labels, Fuhrpark, Display, Startseite, Datenschutz
    "Lesequittierung": 1,  # Einleitung des Orga-Moduls
}

GUARD_HINT = (
    "Bitte den Begriff aus der ersten Spalte des Glossars verwenden "
    "(docs/DESIGN-SYSTEM.md, Abschnitt „Glossar“). Nur für ein altes Vorkommen "
    "darf BASELINE in core/test_glossary.py mit Begründung erhöht werden."
)


def _document() -> str:
    return DESIGN_SYSTEM.read_text(encoding="utf-8")


def table_lines(markers, text: str | None = None) -> list[str]:
    """Nicht leere Zeilen zwischen den beiden Markern."""
    text = _document() if text is None else text
    begin, end = markers
    start = text.index(begin) + len(begin)
    stop = text.index(end, start)
    return [line.strip() for line in text[start:stop].splitlines() if line.strip()]


def split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_separator(cells: list[str]) -> bool:
    return all(cell and set(cell) <= set("-:") for cell in cells)


def table_rows(markers, text: str | None = None) -> list[list[str]]:
    """Datenzeilen der Tabelle, ohne Kopf- und Trennzeile."""
    rows = [split_row(line) for line in table_lines(markers, text)]
    return [cells for cells in rows[1:] if not is_separator(cells)]


def glossary_rows(text: str | None = None) -> list[list[str]]:
    return table_rows(GLOSSARY_MARKERS, text)


def avoided_terms(rows: list[list[str]]) -> list[str]:
    """Wörter in Backticks aus der Spalte „Nicht verwenden“, ohne Dubletten."""
    terms: list[str] = []
    for cells in rows:
        for term in re.findall(r"`([^`]+)`", cells[2]):
            if term not in terms:
                terms.append(term)
    return terms


def matcher(term: str) -> re.Pattern:
    """Findet den Begriff als eigenes Wort, mit Endung und in Bindestrich-Wörtern."""
    return re.compile(r"(?<!\w)" + re.escape(term) + r"(?:es|en|s|e|n)?(?!\w)")


def term_hits(found: dict, term: str) -> list[tuple[tuple, list[str]]]:
    pattern = matcher(term)
    hits = []
    for key, locations in found.items():
        _context, msgid, plural = key
        if any(text and pattern.search(text) for text in (msgid, plural)):
            hits.append((key, locations))
    return sorted(hits, key=lambda item: (item[0][1], item[0][2] or "", item[0][0] or ""))


def guard_report(found: dict, terms: list[str], baseline: dict[str, int]) -> list[str]:
    """Meldet jeden gesperrten Begriff, der öfter vorkommt als erlaubt."""
    problems = []
    for term in terms:
        hits = term_hits(found, term)
        allowed = baseline.get(term, 0)
        if len(hits) <= allowed:
            continue
        lines = [f"„{term}“: {len(hits)} Texte, erlaubt sind {allowed}."]
        for (_context, msgid, plural), locations in hits:
            text = msgid if plural is None else f"{msgid} / {plural}"
            lines.append(f"  - {text!r} ({', '.join(locations)})")
        problems.append("\n".join(lines))
    return problems


class GlossaryDocumentTests(SimpleTestCase):
    def test_glossary_section_is_marked_and_well_formed(self):
        text = _document()
        begin, end = GLOSSARY_MARKERS
        self.assertEqual(text.count(begin), 1)
        self.assertEqual(text.count(end), 1)
        self.assertLess(text.index("## Glossar"), text.index(begin))
        self.assertLess(text.index(begin), text.index(end))

        lines = table_lines(GLOSSARY_MARKERS)
        self.assertEqual(split_row(lines[0]), GLOSSARY_HEADER)
        self.assertTrue(is_separator(split_row(lines[1])), lines[1])
        terms = []
        for line in lines:
            with self.subTest(line=line):
                self.assertTrue(line.startswith("|") and line.endswith("|"), line)
                self.assertEqual(len(split_row(line)), 4, line)
        for cells in glossary_rows():
            with self.subTest(term=cells[0]):
                self.assertNotIn(cells[0], EMPTY_CELLS)
                self.assertNotIn(cells[1], EMPTY_CELLS)
                self.assertNotIn(cells[3], EMPTY_CELLS)
            terms.append(cells[0])
        self.assertGreaterEqual(len(terms), len(CORE_TERMS))
        duplicates = sorted({term for term in terms if terms.count(term) > 1})
        self.assertEqual(duplicates, [], "Begriff doppelt im Glossar")

    def test_core_terms_are_defined(self):
        terms = {cells[0] for cells in glossary_rows()}
        missing = [term for term in CORE_TERMS if term not in terms]
        self.assertEqual(missing, [])

    def test_unavailability_terms_stay_apart(self):
        # Festlegung für 0.27: „Gesperrt“ ist vorübergehend und nur für
        # Medizingeräte, „Außer Dienst“ nur ein Fahrzeugzustand, „Außer Betrieb
        # nehmen“ dauerhaft. Ein Fahrzeug in der Desinfektion ist nicht „Gesperrt“.
        meaning = {cells[0]: cells[3].lower() for cells in glossary_rows()}
        self.assertIn("vorübergehend", meaning["Gesperrt"])
        self.assertIn("nur für medizingeräte", meaning["Gesperrt"])
        self.assertNotIn("einwirkzeit", meaning["Gesperrt"])
        self.assertIn("nicht „gesperrt“", meaning["Desinfektion"])
        self.assertIn("nur für fahrzeuge", meaning["Außer Dienst"])
        self.assertIn("dauerhaft", meaning["Außer Betrieb nehmen"])
        self.assertIn("nie für eine vorübergehende sperre", meaning["Außer Betrieb nehmen"])

    def test_glossary_terms_do_not_trip_the_guard(self):
        rows = glossary_rows()
        patterns = {term: matcher(term) for term in avoided_terms(rows)}
        self.assertTrue(patterns, "Keine gesperrten Begriffe gefunden")
        for cells in rows:
            for term, pattern in patterns.items():
                with self.subTest(begriff=cells[0], gesperrt=term):
                    self.assertIsNone(pattern.search(cells[0]))

    def test_baseline_only_names_guarded_terms(self):
        # Wer einen Begriff aus der Sperrliste nimmt, muss auch den
        # Ausgangsstand streichen; sonst wäre der Eintrag wirkungslos.
        terms = set(avoided_terms(glossary_rows()))
        self.assertEqual(sorted(set(BASELINE) - terms), [])

    def test_agents_md_names_the_guarded_terms(self):
        # Pakete, die parallel entstehen, lesen zuerst AGENTS.md. Die
        # Sperrliste steht deshalb auch dort (§ 6) und muss zum Glossar passen.
        paragraphs = AGENTS.read_text(encoding="utf-8").split("\n\n")
        rule = [text for text in paragraphs if "`core/test_glossary.py`" in text]
        self.assertEqual(len(rule), 1, "Glossar-Regel in AGENTS.md § 6 fehlt")
        self.assertIn("`docs/DESIGN-SYSTEM.md`", rule[0])
        named = [term for term in re.findall(r"`([^`]+)`", rule[0]) if "/" not in term]
        self.assertEqual(sorted(named), sorted(avoided_terms(glossary_rows())))

    def test_module_names_match_more_page_and_nav(self):
        text = _document()
        for marker in MODULE_MARKERS:
            self.assertEqual(text.count(marker), 1, marker)
        lines = table_lines(MODULE_MARKERS)
        self.assertEqual(split_row(lines[0]), MODULE_HEADER)
        self.assertTrue(is_separator(split_row(lines[1])), lines[1])

        more = MORE_TEMPLATE.read_text(encoding="utf-8")
        patterns = [matcher(term) for term in avoided_terms(glossary_rows())]
        keys = []
        for cells in table_rows(MODULE_MARKERS):
            with self.subTest(row=cells):
                self.assertEqual(len(cells), 4)
                match = re.fullmatch(r"`([a-z_]+)`", cells[0])
                self.assertIsNotNone(match, "Bereich als `data-more`-Schlüssel angeben")
                key = match.group(1)
                keys.append(key)
                self.assertIn(f'data-more="{key}"', more)
                self.assertNotIn(cells[1], EMPTY_CELLS)
                if key in CATALOG:
                    self.assertNotIn(cells[2], EMPTY_CELLS, "Modul steht in der Leiste")
                else:
                    self.assertIn(cells[2], EMPTY_CELLS, "Modul ist nicht in der Leiste wählbar")
                for name in (cells[1], cells[2]):
                    for pattern in patterns:
                        self.assertIsNone(pattern.search(name), name)
        self.assertEqual(len(keys), len(set(keys)), "Bereich doppelt")


class GlossaryGuardTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.found = collect()
        cls.terms = avoided_terms(glossary_rows())

    def test_no_new_avoided_terms_in_ui_strings(self):
        problems = guard_report(self.found, self.terms, BASELINE)
        if problems:
            self.fail("\n\n".join(problems) + "\n\n" + GUARD_HINT)

    def test_matcher_catches_variants_and_spares_other_words(self):
        flagged = (
            ("Cockpit", "Neues Cockpit"),
            ("Cockpit", "Fahrzeug-Cockpit öffnen"),
            ("Cockpit", "Alle Cockpits"),
            ("Logbuch", "des Logbuches"),
            ("SOP", "Heilkunde-SOPs"),
            ("SOP", "SOP-Nummer"),
            ("Display-Token", "Display-Tokens"),
            ("Push-Mitteilung", "Push-Mitteilungen"),
            ("Lesequittierung", "Lesequittierungen"),
            ("Fahrzeugstatus", "Fahrzeugstatus geändert"),
        )
        spared = (
            ("Desk", "Desktop"),
            ("Desk", "Desinfektion"),
            ("Asset", "Assistent"),
            ("Fahrzeugstatus", "Fahrzeugzustand"),
            ("SOP", "Dienstanweisung"),
            ("Logbuch", "Fahrtenbuch"),
        )
        for term, text in flagged:
            with self.subTest(term=term, text=text):
                self.assertIsNotNone(matcher(term).search(text))
        for term, text in spared:
            with self.subTest(term=term, text=text):
                self.assertIsNone(matcher(term).search(text))

    def test_guard_reports_new_text_with_location(self):
        found = {
            (None, "Fahrzeug-Cockpit öffnen", None): ["templates/core/neu.html:3"],
            (None, "Ein Gerät", "%(count)s Assets"): ["core/neu.py:7"],
            (None, "Fahrzeugzustand", None): ["core/neu.py:9"],
        }
        problems = guard_report(found, ["Cockpit", "Asset", "Fahrzeugstatus"], {})
        self.assertEqual(len(problems), 2)
        self.assertIn("„Cockpit“: 1 Texte, erlaubt sind 0.", problems[0])
        self.assertIn("templates/core/neu.html:3", problems[0])
        # Auch die Pluralform zählt.
        self.assertIn("core/neu.py:7", problems[1])
        self.assertNotIn("Fahrzeugzustand", "\n".join(problems))

    def test_guard_allows_fewer_occurrences_than_baseline(self):
        # Kein Test auf veraltete Ausgangsstände: Entfernen alter Wörter
        # bricht nie den Build.
        self.assertEqual(guard_report({}, list(BASELINE), BASELINE), [])
        found = {(None, "Neue SOP anlegen", None): ["templates/core/orga_dashboard.html:15"]}
        self.assertEqual(guard_report(found, ["SOP"], {"SOP": 1}), [])
        self.assertEqual(len(guard_report(found, ["SOP"], {"SOP": 0})), 1)
