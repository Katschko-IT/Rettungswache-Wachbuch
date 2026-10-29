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

Ergänzung 2026-10-29: Erlaubt ist genau ein Knopf zur öffentlichen Live-Version
(demo.rwsth.de) mit kurzem Hinweis im Kopfbereich; sonst bleibt Demo-Sprache
verboten. Das Logo im Kopf zählt nicht als Screenshot.
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
SHOTS_DIR = SITE_DIR / "assets" / "design" / "screens"
FONTS_DIR = SITE_DIR / "assets" / "design" / "fonts"
EN_DIR = SITE_DIR / "en"
EN_HTML = EN_DIR / "index.html"
BRAND_LOGO_CLASS = "pub-brand-logo"
# Einzige erlaubte Erwähnung der öffentlichen Demo: Knopf und Hinweis im Kopf.
DEMO_URL = "https://demo.rwsth.de/"
LIVE_CTA_RE = re.compile(r'<a class="pub-button primary pub-live" href="([^"]*)">.*?</a>', re.DOTALL)
LIVE_NOTE_RE = re.compile(r'<p class="pub-live-note">.*?</p>', re.DOTALL)


def screenshots(images):
    """Alle <img> außer dem Logo im Kopf: die App-Aufnahmen."""
    return [img for img in images if BRAND_LOGO_CLASS not in img.get("class", "").split()]


def without_live_demo(content):
    """Seiteninhalt ohne den erlaubten Demo-Knopf und -Hinweis."""
    return LIVE_NOTE_RE.sub("", LIVE_CTA_RE.sub("", content))


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
        self.lang = None
        self.has_html_lang_de = False
        self.has_viewport = False
        self.has_main_landmark = False

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        self.tags.append(tag)

        if tag == "html":
            self.lang = attr_dict.get("lang")
            if attr_dict.get("lang") == "de":
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
        for name, content in [
            ("index.html", without_live_demo(self.index_content)),
            ("styles.css", self.styles_content),
        ]:
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

        for img in screenshots(self.parser.images):
            self.assertTrue(img.get("src", "").startswith("assets/design/screens/"), f"Bild nicht lokal: {img}")
            self.assertTrue(img.get("alt", "").strip(), f"Alternativtext fehlt für {img.get('src')}")
            self.assertGreaterEqual(len(img.get("alt", "")), 40, f"Alternativtext zu knapp: {img.get('src')}")
            self.assertTrue(img.get("width", "").isdigit(), f"width fehlt: {img.get('src')}")
            self.assertTrue(img.get("height", "").isdigit(), f"height fehlt: {img.get('src')}")
            self.assertLessEqual(int(img["width"]), 1440, "Screenshot breiter als 1440 CSS-Pixel")

        lower_html = self.index_content.lower()
        self.assertIn("synthetischen daten", lower_html, "Kennzeichnung der synthetischen Daten fehlt")

    def test_brand_logo_is_local(self):
        """Das Logo im Kopf liegt lokal unter assets/design/, mit Name und Maßen."""
        logos = [img for img in self.parser.images if img not in screenshots(self.parser.images)]
        self.assertEqual(len(logos), 1, "Genau ein Logo im Kopf erwartet")
        logo = logos[0]
        self.assertEqual(logo.get("src"), "assets/design/brand-wachwerk.png")
        self.assertTrue((SITE_DIR / logo["src"]).is_file(), "Logo-Datei fehlt")
        self.assertEqual(logo.get("alt"), "Wachwerk")
        self.assertTrue(logo.get("width", "").isdigit() and logo.get("height", "").isdigit())

    def test_live_demo_link(self):
        """Genau ein deutlicher Knopf zur öffentlichen Demo, mit Zugangsdaten daneben."""
        self.assertEqual(LIVE_CTA_RE.findall(self.index_content), [DEMO_URL])
        hero = self.index_content.split('<section id="top"', 1)[1].split("</section>", 1)[0]
        self.assertIn(DEMO_URL, hero, "Demo-Knopf gehört in den Kopfbereich")
        notes = LIVE_NOTE_RE.findall(self.index_content)
        self.assertEqual(len(notes), 1, "Hinweis zur Demo fehlt")
        self.assertIn("<strong>Demo</strong> / <strong>Demo</strong>", notes[0])
        self.assertIn("gelöscht", notes[0], "Hinweis, dass die Demo-Wache gelöscht wird, fehlt")

    def test_local_fonts_and_license(self):
        """Schriften müssen lokal eingebunden sein und eine Lizenz mitliefern."""
        fonts_css = (SITE_DIR / "assets" / "design" / "fonts.css").read_text(encoding="utf-8")
        self.assertIn("assets/design/fonts.css", self.index_content, "Schrift-Stylesheet nicht eingebunden")
        for weight in ("400", "600", "700"):
            font = FONTS_DIR / f"atkinson-hyperlegible-next-latin-{weight}-normal.woff2"
            self.assertTrue(font.is_file(), f"Lokale Schrift fehlt: {font.name}")
            self.assertIn(f"fonts/{font.name}", fonts_css)

        self.assertTrue((FONTS_DIR / "LICENSE-AtkinsonHyperlegibleNext.txt").is_file(), "Schriftlizenz fehlt")
        self.assertNotIn("fonts.googleapis", fonts_css)
        self.assertNotIn("fonts.googleapis", self.styles_content)

    def test_responsive_and_motion_requirements(self):
        """Responsive Grundlagen, Touch-Ziele und reduzierte Bewegung müssen im CSS stehen."""
        css = self.styles_content
        self.assertIn("@media (max-width: 46rem)", css, "Mobiler Breakpoint fehlt")
        self.assertIn("(prefers-reduced-motion: reduce)", css, "Reduzierte Bewegung fehlt")
        self.assertIn("(prefers-contrast: more)", css, "Kontrastmodus fehlt")
        self.assertIn("--touch: 48px", css, "Touch-Ziel 48px fehlt")
        self.assertIn(":focus-visible", css, "Tastaturfokus fehlt")


class TestEnglishSite(unittest.TestCase):
    """EN-Fassung unter site/en/: Metadaten, lokale Assets, Links und Sprachgates."""

    @classmethod
    def setUpClass(cls):
        if not EN_HTML.is_file():
            raise AssertionError(f"Englische Seite fehlt: {EN_HTML}")
        cls.en_content = EN_HTML.read_text(encoding="utf-8")
        cls.de_content = INDEX_HTML.read_text(encoding="utf-8")
        cls.styles_content = STYLES_CSS.read_text(encoding="utf-8")
        cls.en = HTMLStructureParser()
        cls.en.feed(cls.en_content)
        cls.de = HTMLStructureParser()
        cls.de.feed(cls.de_content)

    def _meta(self, content):
        found = {}
        for tag in re.findall(r"<meta\b[^>]*>", content, re.IGNORECASE):
            name = re.search(r'(?:name|property)="([^"]+)"', tag)
            value = re.search(r'content="([^"]*)"', tag)
            if name and value:
                found[name.group(1)] = value.group(1)
        return found

    def _title(self, content):
        match = re.search(r"<title>(.*?)</title>", content, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else ""

    def test_en_utf8_decoding_and_no_mojibake(self):
        """EN-Seite muss sauberes UTF-8 ohne BOM, Ersatzzeichen oder Mojibake sein."""
        raw = EN_HTML.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), "BOM in site/en/index.html unzulässig")
        self.assertNotIn("\ufffd", self.en_content, "Ersetzungszeichen in site/en/index.html")
        for bad in ("Ã¤", "Ã¶", "Ã¼", "Ã„", "Ã–", "Ãœ", "ÃŸ", "â€“", "â€ž", "â€œ"):
            self.assertNotIn(bad, self.en_content, f"Mojibake '{bad}' in site/en/index.html")

    def test_en_document_structure(self):
        """EN-Seite braucht lang=en, Viewport, genau eine h1 und alle Landmarks."""
        self.assertEqual(self.en.lang, "en", '<html lang="en"> fehlt in site/en/index.html')
        self.assertTrue(self.en.has_viewport, "Viewport-Meta fehlt in der EN-Seite")
        self.assertEqual(self.en.h1_count, 1, f"Erwartet genau 1 <h1>, gefunden: {self.en.h1_count}")
        for landmark in ("header", "nav", "main", "footer"):
            self.assertIn(landmark, self.en.tags, f"Pflicht-Landmark <{landmark}> fehlt in der EN-Seite")
        self.assertTrue(self.en.has_main_landmark, "<main> fehlt in der EN-Seite")

        skip_links = [
            href for href, cls in self.en.links if "skip-link" in cls or href.startswith("#main")
        ]
        self.assertTrue(skip_links, "Kein Skip-Link in der EN-Seite")
        self.assertIn(
            skip_links[0].lstrip("#"),
            self.en.ids,
            f"Ziel des EN-Skip-Links '{skip_links[0]}' existiert nicht",
        )

    def test_en_metadata_is_translated(self):
        """Titel, Description und Open-Graph-Texte müssen englisch und gepflegt sein."""
        meta = self._meta(self.en_content)
        de_meta = self._meta(self.de_content)
        title = self._title(self.en_content)

        self.assertIn("station logbook", title.lower(), f"EN-Titel nicht übersetzt: {title}")
        self.assertNotEqual(title, self._title(self.de_content), "EN-Titel identisch mit DE-Titel")
        self.assertIn("description", meta, "Meta-Description fehlt in der EN-Seite")
        self.assertIn("og:title", meta, "og:title fehlt in der EN-Seite")
        self.assertIn("og:description", meta, "og:description fehlt in der EN-Seite")

        german = re.compile(r"[äöüßÄÖÜ]|\b(und|oder|nicht|für|über|Wachbuch|Rettungswachen)\b")
        for key in ("description", "og:title", "og:description"):
            self.assertGreaterEqual(len(meta[key]), 40, f"{key} zu knapp in der EN-Seite")
            self.assertIsNone(german.search(meta[key]), f"{key} enthält noch deutschen Text: {meta[key]}")
            if key in de_meta:
                self.assertNotEqual(meta[key], de_meta[key], f"{key} unverändert aus der DE-Seite übernommen")
        self.assertIn("station logbook", meta["og:title"].lower(), "og:title nicht übersetzt")

    def test_en_local_assets_and_no_duplication(self):
        """EN-Seite nutzt ../assets und ../styles.css; im en/ Ordner liegen keine Kopien."""
        self.assertEqual(
            self.en.stylesheets,
            ["../assets/design/fonts.css", "../assets/design/tokens.css", "../assets/design/public.css", "../styles.css"],
            f"EN-Seite muss die gemeinsamen Stylesheets nutzen, gefunden: {self.en.stylesheets}",
        )
        self.assertTrue((SITE_DIR / "styles.css").is_file(), "Zentrales Stylesheet fehlt")
        self.assertFalse((EN_DIR / "styles.css").exists(), "styles.css darf im en/ Ordner nicht dupliziert werden")
        self.assertFalse((EN_DIR / "assets").exists(), "Assets dürfen im en/ Ordner nicht dupliziert werden")

        for src in self.en.sources:
            self.assertFalse(src.startswith(("http://", "https://")), f"Externe Ressource in EN-Seite: {src}")
            self.assertTrue(src.startswith("../assets/"), f"EN-Ressource nutzt nicht ../assets: {src}")
            self.assertTrue((EN_DIR / src).resolve().is_file(), f"EN-Ressource fehlt: {src}")

        for img in screenshots(self.en.images):
            self.assertTrue(img.get("src", "").startswith("../assets/design/screens/"), f"Bild nicht lokal: {img}")
            self.assertTrue(img.get("alt", "").strip(), f"Alternativtext fehlt für {img.get('src')}")
            self.assertGreaterEqual(len(img.get("alt", "")), 40, f"Alternativtext zu knapp: {img.get('src')}")
            self.assertTrue(img.get("width", "").isdigit(), f"width fehlt: {img.get('src')}")
            self.assertTrue(img.get("height", "").isdigit(), f"height fehlt: {img.get('src')}")

        self.assertGreaterEqual(len(self.en.images), 10, "EN-Seite muss alle App-Screenshots zeigen")
        self.assertGreaterEqual(len(list(SHOTS_DIR.glob("*.webp"))), 10, "Screenshot-Bestand unvollständig")

    def test_en_no_javascript_or_external_cdn(self):
        """Auch die EN-Seite bleibt skript- und CDN-frei."""
        self.assertEqual(len(self.en.scripts), 0, "Script-Tags in der EN-Seite unzulässig")
        self.assertNotIn("<script", self.en_content.lower(), "Unzulässiges <script>-Tag in der EN-Seite")
        self.assertNotIn("http://", self.en_content.lower(), "Unsicheres http:// in der EN-Seite")
        for marker in ("fonts.googleapis.com", "cdnjs.cloudflare.com", "@import"):
            self.assertNotIn(marker, self.en_content.lower(), f"Externer Verweis '{marker}' in der EN-Seite")
        self.assertNotIn("fonts.googleapis", self.styles_content)

    def test_en_internal_links_resolve(self):
        """Alle internen EN-Links und Anker müssen auflösen, Repository-Links bleiben absolut."""
        for href, _ in self.en.links:
            if href.startswith("#"):
                self.assertIn(
                    href.lstrip("#"),
                    self.en.ids,
                    f"EN-Anker '{href}' verweist auf keine existierende ID",
                )
                continue
            if href.startswith(("https://", "http://", "mailto:")):
                continue
            target = (EN_DIR / href).resolve()
            self.assertTrue(target.exists(), f"Interner EN-Link zeigt ins Leere: {href}")
            if href.endswith("/") or target.is_dir():
                self.assertTrue((target / "index.html").is_file(), f"Verzeichnislink ohne index.html: {href}")

        for href, _ in self.de.links:
            if href.startswith("#"):
                continue
            if href.startswith(("https://", "http://", "mailto:")):
                continue
            self.assertTrue((SITE_DIR / href).exists(), f"Interner DE-Link zeigt ins Leere: {href}")

    def test_language_switch_gates(self):
        """DE/EN-Umschaltung muss reziprok, eindeutig und mit hreflang belegt sein."""
        de_switch = re.search(r'<div class="lang-switch".*?</div>', self.de_content, re.DOTALL)
        en_switch = re.search(r'<div class="lang-switch".*?</div>', self.en_content, re.DOTALL)
        self.assertIsNotNone(de_switch, "Sprachumschaltung fehlt in site/index.html")
        self.assertIsNotNone(en_switch, "Sprachumschaltung fehlt in site/en/index.html")
        self.assertEqual(self.de_content.count('class="lang-switch"'), 1, "DE-Seite braucht genau eine Sprachumschaltung")
        self.assertEqual(self.en_content.count('class="lang-switch"'), 1, "EN-Seite braucht genau eine Sprachumschaltung")

        de_block, en_block = de_switch.group(0), en_switch.group(0)
        self.assertRegex(de_block, r'href="en/"[^>]*hreflang="en"', "DE → EN Link fehlt oder ohne hreflang")
        self.assertRegex(en_block, r'href="\.\./"[^>]*hreflang="de"', "EN → DE Link fehlt oder ohne hreflang")
        self.assertIn('aria-label="Switch to English"', de_block, "DE-Sprachlink ohne klaren englischen Namen")
        self.assertIn("Zur deutschen Fassung wechseln", en_block, "EN-Sprachlink ohne klaren deutschen Namen")
        self.assertIn('<span aria-current="true">DE</span>', de_block, "DE-Seite markiert DE nicht als aktuell")
        self.assertIn('<span aria-current="true">EN</span>', en_block, "EN-Seite markiert EN nicht als aktuell")

        self.assertTrue((SITE_DIR / "en" / "index.html").is_file(), "Ziel des DE → EN Links fehlt")
        self.assertTrue((SITE_DIR / "index.html").is_file(), "Ziel des EN → DE Links fehlt")

        for content, name in ((self.de_content, "DE"), (self.en_content, "EN")):
            self.assertIn(f'hreflang="de"', content, f"{name}-Seite ohne hreflang=de")
            self.assertIn(f'hreflang="en"', content, f"{name}-Seite ohne hreflang=en")
            self.assertIn("https://katschko-it.github.io/Rettungswache-Wachbuch/en/", content)
            self.assertIn("https://katschko-it.github.io/Rettungswache-Wachbuch/", content)

    def test_en_claim_gates(self):
        """EN-Fassung trägt dieselben Fakten- und Abgrenzungsaussagen wie die DE-Fassung."""
        lower = self.en_content.lower()
        for required in (
            "no production approval",
            "pre-production",
            "not implemented",
            "outbox",
            "external acceptance",
            "synthetic",
            "german-language interface",
            "patient documentation system",
            "duty scheduling",
            "incident command",
            "open",
            "agpl",
            "postgresql",
            "django",
            "docker",
        ):
            self.assertIn(required, lower, f"Pflichtaussage '{required}' fehlt in der EN-Seite")

        for forbidden in (
            "guaranteed",
            "guarantee",
            "certified",
            "certification",
            "gdpr-compliant",
            "production-ready",
            "production ready",
            "100% secure",
            "audited",
        ):
            self.assertIsNone(
                re.search(re.escape(forbidden), lower),
                f"Verbotene Werbeaussage '{forbidden}' in der EN-Seite",
            )

        self.assertIsNone(
            re.search(r"\b(todo|lorem|example\.com|demo)\b", without_live_demo(self.en_content).lower()),
            "Platzhalter oder Demo-Jargon in der EN-Seite",
        )
        self.assertEqual(LIVE_CTA_RE.findall(self.en_content), [DEMO_URL], "Demo-Knopf fehlt in der EN-Seite")
        notes = LIVE_NOTE_RE.findall(self.en_content)
        self.assertEqual(len(notes), 1, "Hinweis zur Demo fehlt in der EN-Seite")
        self.assertIn("<strong>Demo</strong> / <strong>Demo</strong>", notes[0])

    def test_en_mirrors_de_structure(self):
        """EN-Seite muss dieselben Abschnitte, Sprungziele und Screenshots abbilden."""
        self.assertEqual(self.en.ids, self.de.ids, "IDs/Anker unterscheiden sich zwischen DE und EN")
        self.assertEqual(self.en.figures, self.de.figures, "Unterschiedliche Anzahl <figure> zwischen DE und EN")
        self.assertEqual(len(self.en.images), len(self.de.images), "Unterschiedliche Bildanzahl zwischen DE und EN")
        self.assertEqual(
            [img.get("src", "").replace("../", "") for img in self.en.images],
            [img.get("src", "") for img in self.de.images],
            "EN-Seite nutzt andere Screenshots als die DE-Seite",
        )
        self.assertEqual(
            [href for href, _ in self.en.links if href.startswith("#")],
            [href for href, _ in self.de.links if href.startswith("#")],
            "Sprungziele unterscheiden sich zwischen DE und EN",
        )
        self.assertEqual(self.en_content.count("<details>"), self.de_content.count("<details>"), "FAQ-Anzahl weicht ab")
        self.assertEqual(
            self.en_content.count("<tr>"),
            self.de_content.count("<tr>"),
            "Tabellenzeilen weichen zwischen DE und EN ab",
        )


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestSiteIntegrity)
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestEnglishSite))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
