#!/usr/bin/env python3
"""
Testsuite zur Überprüfung der statischen Projektwebseite unter site/.
Reiner Standardbibliothek-Test (docs/ARBEITSVERTRAG-20261019.md §3).

Geprüft werden Struktur, lokale Assets, Barrierefreiheits-Grundlagen, ehrliche
Produktaussagen und die Abwesenheit von Demo-/Werbe-Jargon.

Bewusste Anpassung 2026-10-19: Die frühere Pflichtaussage „nicht veröffentlicht“
beschrieb den Zwischenstand, nicht das Produkt. An ihre Stelle treten prüfbare
Aussagen zum Reifegrad („keine Produktionsfreigabe“, offene externe Abnahmen,
nicht implementierter Client-Offlinebetrieb). Die Sicherheits- und Produktgrenzen
bleiben vollständig prüfpflichtig.
"""

import html.parser
import pathlib
import re
import sys
import unittest

SITE_DIR = pathlib.Path(__file__).resolve().parent.parent
INDEX_HTML = SITE_DIR / "index.html"
STYLES_CSS = SITE_DIR / "styles.css"
README_MD = SITE_DIR / "README.md"
NOJEKYLL = SITE_DIR / ".nojekyll"
SHOTS_DIR = SITE_DIR / "assets" / "screenshots"
FONTS_DIR = SITE_DIR / "assets" / "fonts"


class HTMLStructureParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.ids = set()
        self.h1_count = 0
        self.links = []
        self.sources = []
        self.stylesheets = []
        self.scripts = []
        self.images = []
        self.figures = 0
        self.has_html_lang_de = False
        self.has_viewport = False
        self.has_main_landmark = False

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        self.tags.append(tag)

        if tag == "html" and attr_dict.get("lang") == "de":
            self.has_html_lang_de = True

        if tag == "meta" and attr_dict.get("name") == "viewport":
            self.has_viewport = True

        if tag == "main":
            self.has_main_landmark = True

        if "id" in attr_dict:
            self.ids.add(attr_dict["id"])

        if tag == "h1":
            self.h1_count += 1

        if tag == "figure":
            self.figures += 1

        if tag == "a" and "href" in attr_dict:
            self.links.append((attr_dict["href"], attr_dict.get("class", "")))

        if tag == "link" and attr_dict.get("rel") == "stylesheet":
            if "href" in attr_dict:
                self.stylesheets.append(attr_dict["href"])

        if tag in ("img", "source", "script") and "src" in attr_dict:
            self.sources.append(attr_dict["src"])

        if tag == "img":
            self.images.append(attr_dict)

        if tag == "script":
            self.scripts.append(attr_dict)


class TestSiteIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for path in (INDEX_HTML, STYLES_CSS, README_MD, NOJEKYLL):
            if not path.is_file():
                raise AssertionError(f"Erforderliche Datei fehlt: {path}")

        cls.index_content = INDEX_HTML.read_text(encoding="utf-8")
        cls.styles_content = STYLES_CSS.read_text(encoding="utf-8")
        cls.readme_content = README_MD.read_text(encoding="utf-8")
        cls.nojekyll_content = NOJEKYLL.read_text(encoding="utf-8")

        cls.parser = HTMLStructureParser()
        cls.parser.feed(cls.index_content)

    def test_utf8_decoding_and_no_mojibake(self):
        """Alle Dateien müssen sauberes UTF-8 ohne BOM oder Mojibake enthalten."""
        for path, content in [
            (INDEX_HTML, self.index_content),
            (STYLES_CSS, self.styles_content),
            (README_MD, self.readme_content),
            (NOJEKYLL, self.nojekyll_content),
        ]:
            raw = path.read_bytes()
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), f"BOM in {path.name} unzulässig")
            self.assertNotIn("\ufffd", content, f"Ersetzungszeichen in {path.name} gefunden")
            for bad in ("Ã¤", "Ã¶", "Ã¼", "Ã„", "Ã–", "Ãœ", "ÃŸ", "â€“", "â€ž", "â€œ"):
                self.assertNotIn(bad, content, f"Mojibake '{bad}' in {path.name} gefunden")

    def test_single_h1(self):
        """Die Seite muss genau eine <h1>-Überschrift haben."""
        self.assertEqual(
            self.parser.h1_count,
            1,
            f"Erwartet genau 1 <h1>, gefunden: {self.parser.h1_count}",
        )

    def test_mandatory_landmarks(self):
        """Pflicht-Landmarks header, nav, main, footer müssen vorhanden sein."""
        for landmark in ("header", "nav", "main", "footer"):
            self.assertIn(
                landmark,
                self.parser.tags,
                f"Pflicht-Landmark <{landmark}> fehlt in site/index.html",
            )
        self.assertTrue(self.parser.has_html_lang_de, '<html lang="de"> fehlt oder ist inkorrekt')
        self.assertTrue(self.parser.has_viewport, "Viewport-Meta fehlt (Responsivität)")

    def test_skip_link_exists_and_target_resolves(self):
        """Skip-Link muss vorhanden sein und auf ein existierendes ID-Ziel verweisen."""
        skip_links = [
            href for href, cls in self.parser.links if "skip-link" in cls or href.startswith("#main")
        ]
        self.assertTrue(len(skip_links) >= 1, "Kein Skip-Link gefunden")

        target_id = skip_links[0].lstrip("#")
        self.assertIn(
            target_id,
            self.parser.ids,
            f"Ziel des Skip-Links '#{target_id}' existiert nicht als id in site/index.html",
        )

    def test_internal_hrefs_and_srcs_resolve_locally(self):
        """Alle internen Links und Verweise müssen lokal auflösen."""
        for sheet in self.parser.stylesheets:
            self.assertFalse(
                sheet.startswith("http://") or sheet.startswith("https://"),
                f"Externes Stylesheet unzulässig: {sheet}",
            )
            local_path = (SITE_DIR / sheet).resolve()
            self.assertTrue(local_path.is_file(), f"Stylesheet existiert nicht lokal: {sheet}")

        for src in self.parser.sources:
            self.assertFalse(
                src.startswith("http://") or src.startswith("https://"),
                f"Externe Ressource unzulässig: {src}",
            )
            local_path = (SITE_DIR / src).resolve()
            self.assertTrue(local_path.is_file(), f"Ressource existiert nicht lokal: {src}")

        for href, _ in self.parser.links:
            if href.startswith("#"):
                target_id = href.lstrip("#")
                self.assertIn(
                    target_id,
                    self.parser.ids,
                    f"Anker-Link '{href}' verweist auf nicht existierende ID '{target_id}'",
                )

    def test_no_http_assets(self):
        """Keine http://-Assets im HTML oder CSS (weder href noch src noch url())."""
        http_pattern = re.compile(r"http://", re.IGNORECASE)
        self.assertIsNone(
            http_pattern.search(self.index_content),
            "Unverschlüsselte http://-Links oder -Assets in site/index.html unzulässig",
        )
        self.assertIsNone(
            http_pattern.search(self.styles_content),
            "Unverschlüsselte http://-Verweise in site/styles.css unzulässig",
        )

    def test_no_placeholders_or_demo_jargon(self):
        """Keine Platzhalter und keine Demo-/Vorführ-Sprache in der öffentlichen Seite."""
        placeholder_pattern = re.compile(r"\b(todo|lorem|example\.com)\b", re.IGNORECASE)
        for name, content in [
            ("index.html", self.index_content),
            ("styles.css", self.styles_content),
            ("README.md", self.readme_content),
        ]:
            match = placeholder_pattern.search(content)
            self.assertIsNone(
                match,
                f"Platzhalter '{match.group(0) if match else ''}' in {name} gefunden",
            )

        demo_pattern = re.compile(r"\b(demo|demo-modus|musterstadt|vorführung)\b", re.IGNORECASE)
        for name, content in [("index.html", self.index_content), ("styles.css", self.styles_content)]:
            match = demo_pattern.search(content)
            self.assertIsNone(
                match,
                f"Demo-/Vorführ-Jargon '{match.group(0) if match else ''}' in {name} gefunden",
            )

    def test_mandatory_statements_present(self):
        """Pflichtaussagen zu Produktgrenzen und Reifegrad müssen enthalten sein."""
        lower_html = self.index_content.lower()

        # Produktabgrenzung
        self.assertIn("kein einsatzleit", lower_html, "Abgrenzung zu Einsatzleitsystemen fehlt")
        self.assertIn(
            "patientendokumentationssystem",
            lower_html,
            "Abgrenzung zu Patientendokumentation fehlt",
        )
        self.assertIn("dienstplanung", lower_html, "Abgrenzung zur Dienstplanung fehlt")

        # Ehrlicher Reifegrad
        self.assertIn("vorproduktion", lower_html, "Reifegrad 'Vorproduktion' fehlt")
        self.assertIn("keine produktionsfreigabe", lower_html, "Hinweis auf fehlende Produktionsfreigabe fehlt")
        self.assertIn("externe abnahmen", lower_html, "Offene externe Abnahmen werden nicht benannt")
        self.assertIn(
            "nicht umgesetzt",
            lower_html,
            "Nicht implementierte Funktion (Client-Offline) wird nicht als solche benannt",
        )
        self.assertIn("outbox", lower_html, "Grenze des Client-Offlinebetriebs (Outbox) fehlt")

        # Betriebsmodell & Technologie
        for term in ("docker", "postgresql", "django", "agpl"):
            self.assertIn(term, lower_html, f"Technische Pflichtangabe '{term}' fehlt")

    def test_forbidden_statements_absent(self):
        """Verbotene Werbe-, Garantie- oder Zertifizierungsaussagen dürfen nicht vorkommen."""
        lower_html = self.index_content.lower()

        for forbidden in (
            "garantiert",
            "garantie",
            "garantieren",
            "zertifiziert",
            "zertifikat",
            "zertifizierung",
            "100 % sicher",
            "100% sicher",
            "dsgvo-konform",
            "produktionsreif",
        ):
            self.assertIsNone(
                re.search(re.escape(forbidden), lower_html),
                f"Verbotene Aussage '{forbidden}' in site/index.html gefunden",
            )

        positive_patient_claims = re.search(
            r"(verwalt|speicher|erfass|unterstütz|feature|bietet|beinhaltet)[^\.\n]*patientendaten",
            lower_html,
        )
        self.assertIsNone(
            positive_patient_claims,
            f"Patientendaten als Feature formuliert: {positive_patient_claims.group(0) if positive_patient_claims else ''}",
        )

    def test_no_javascript_and_no_external_cdns(self):
        """Kein JavaScript, keine Skripte und keine externen CDNs/Webfonts."""
        self.assertEqual(len(self.parser.scripts), 0, "JavaScript/Script-Tags sind in site/ unzulässig")
        self.assertNotIn("<script", self.index_content.lower(), "Unzulässiges <script>-Tag gefunden")
        self.assertNotIn("@import", self.styles_content.lower(), "Externes @import in styles.css unzulässig")
        self.assertNotIn("fonts.googleapis.com", self.index_content, "Google Fonts CDN unzulässig")
        self.assertNotIn("cdnjs.cloudflare.com", self.index_content, "Cloudflare CDN unzulässig")
        self.assertNotIn("http://", self.styles_content.lower(), "Unsicheres http:// in Styles")

    def test_screenshots_are_local_real_app_shots(self):
        """Screenshots müssen lokal vorliegen, dimensioniert und mit Alternativtext versehen sein."""
        self.assertTrue(SHOTS_DIR.is_dir(), "Screenshot-Verzeichnis fehlt")
        shots = sorted(SHOTS_DIR.glob("*.webp"))
        self.assertGreaterEqual(len(shots), 8, f"Zu wenige Screenshots: {len(shots)}")
        self.assertGreaterEqual(len(self.parser.images), 8, "Zu wenige <img>-Elemente in der Galerie")
        self.assertGreaterEqual(self.parser.figures, 9, "Galerie braucht <figure>-Elemente mit Captions")

        for img in self.parser.images:
            self.assertTrue(img.get("src", "").startswith("assets/screenshots/"), f"Bild nicht lokal: {img}")
            self.assertTrue(img.get("alt", "").strip(), f"Alternativtext fehlt für {img.get('src')}")
            self.assertGreaterEqual(len(img.get("alt", "")), 40, f"Alternativtext zu knapp: {img.get('src')}")
            self.assertTrue(img.get("width", "").isdigit(), f"width fehlt: {img.get('src')}")
            self.assertTrue(img.get("height", "").isdigit(), f"height fehlt: {img.get('src')}")
            self.assertLessEqual(int(img["width"]), 1280, "Screenshot breiter als 1280 CSS-Pixel")

        lower_html = self.index_content.lower()
        self.assertIn("synthetischen daten", lower_html, "Kennzeichnung der synthetischen Daten fehlt")

    def test_local_fonts_and_license(self):
        """Schriften müssen lokal eingebunden sein und eine Lizenz mitliefern."""
        for weight in ("Regular", "Semibold", "Bold"):
            font = FONTS_DIR / f"SourceSans3-{weight}.woff2"
            self.assertTrue(font.is_file(), f"Lokale Schrift fehlt: {font.name}")
            self.assertIn(f"assets/fonts/SourceSans3-{weight}.woff2", self.styles_content)

        self.assertTrue((FONTS_DIR / "LICENSE-SourceSans3.txt").is_file(), "Schriftlizenz fehlt")
        self.assertNotIn("fonts.googleapis", self.styles_content)

    def test_responsive_and_motion_requirements(self):
        """Responsive Grundlagen, Touch-Ziele und reduzierte Bewegung müssen im CSS stehen."""
        css = self.styles_content
        self.assertIn("@media (max-width: 46rem)", css, "Mobiler Breakpoint fehlt")
        self.assertIn("(prefers-reduced-motion: reduce)", css, "Reduzierte Bewegung fehlt")
        self.assertIn("(prefers-contrast: more)", css, "Kontrastmodus fehlt")
        self.assertIn("--touch: 48px", css, "Touch-Ziel 48px fehlt")
        self.assertIn(":focus-visible", css, "Tastaturfokus fehlt")


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestSiteIntegrity)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
