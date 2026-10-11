"""Gezielte Tests für die Präsentations-Landing (Wachwerk).

Prüfen die neue, eigenständige Startseite und die lokale, serverunabhängige
Produktvorschau auf Sicherheit (CSP), Barrierefreiheit und Produktgrenze.
Keine Serveraufrufe, kein Login, keine Speicherung in der Vorschau.
"""

from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse


class PresentationLandingTests(TestCase):
    def _template(self) -> str:
        return (Path(settings.BASE_DIR) / "templates" / "core" / "landing.html").read_text(
            encoding="utf-8"
        )

    def _js(self) -> str:
        return (
            Path(settings.BASE_DIR) / "core" / "static" / "core" / "presentation.js"
        ).read_text(encoding="utf-8")

    def _css(self) -> str:
        return (
            Path(settings.BASE_DIR) / "core" / "static" / "core" / "presentation.css"
        ).read_text(encoding="utf-8")

    def test_public_landing_renders_preview_and_boundary(self):
        self.client.logout()
        response = self.client.get(reverse("landing"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "<h1>Die nächste Schicht. Schon im Bild.</h1>", html=False, count=1
        )
        self.assertContains(
            response, "Vorschau mit fiktiven Beispieldaten – keine echte App-Sitzung."
        )
        # Produktgrenze bleibt sichtbar.
        self.assertContains(response, "Kein Einsatzleit-, Alarmierungs-, Diagnose- oder Patientensystem.")
        # Pflichtlinks der Landing.
        self.assertContains(response, reverse("login"))
        self.assertContains(response, reverse("vorfuehrung"))
        self.assertContains(response, reverse("privacy"))
        # Die echte Demo ist ein separater Link, kein iframe.
        self.assertNotContains(response, "<iframe")

    def test_project_and_platform_icons_are_honest_and_local(self):
        response = self.client.get(reverse("landing"))
        self.assertContains(response, 'href="https://github.com/darkspike1988/Rettungswache-Wachbuch"')
        for icon in ("github", "android", "ios"):
            self.assertContains(response, f"core/icons/{icon}.svg")
        self.assertContains(response, "noch nicht in den App-Stores veröffentlicht")
        self.assertNotContains(response, "https://play.google.com/store/apps")
        self.assertNotContains(response, "https://apps.apple.com/")

    def test_landing_has_no_register_link(self):
        self.client.logout()
        response = self.client.get(reverse("landing"))
        self.assertNotContains(response, reverse("register"))

    def test_preview_assets_are_local_and_csp_referenced(self):
        self.client.logout()
        response = self.client.get(reverse("landing"))
        self.assertContains(response, "core/presentation.css")
        self.assertContains(response, "core/presentation.js")
        # Keine externen Asset-Quellen (kein CDN).
        self.assertNotContains(response, "https://cdn")
        self.assertNotContains(response, "fonts.googleapis.com")

    def test_landing_template_is_csp_safe(self):
        source = self._template()
        self.assertNotIn("|safe", source)
        self.assertNotIn("innerHTML", source)
        self.assertNotIn(" style=", source)
        self.assertNotIn("onclick", source)
        # Skripte ausschließlich extern (kein Inline-<script> mit Inhalt).
        self.assertIn("<script src=\"{% static 'core/presentation.js' %}\" defer></script>", source)
        self.assertNotIn("<script>", source)

    def test_preview_javascript_avoids_html_sinks_and_storage(self):
        js = self._js()
        # Keine HTML-Sinks: Zuweisung oder Zugriff auf innerHTML.
        self.assertNotIn(".innerHTML", js)
        self.assertNotIn("innerHTML =", js)
        self.assertNotIn("insertAdjacentHTML", js)
        self.assertNotIn(".outerHTML", js)
        # Keine dynamische Code-Ausführung (neue Funktion aus String).
        self.assertNotIn("new Function", js)
        # Keine Speicherung, kein Tracking, keine Netzwerkaufrufe.
        self.assertNotIn("localStorage", js)
        self.assertNotIn("sessionStorage", js)
        self.assertNotIn("fetch(", js)
        self.assertNotIn("XMLHttpRequest", js)
        # DOM-Text wird ausschließlich per textContent gesetzt.
        self.assertIn("textContent", js)

    def test_preview_css_respects_accessibility_baseline(self):
        css = self._css()
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn("--pw-touch: 48px", css)
        self.assertIn("focus-visible", css)
        self.assertIn("aria-live", self._template())

    def test_preview_covers_required_scenarios(self):
        source = self._template()
        for scenario in ("overview", "handover", "tasks", "calendar"):
            self.assertIn(f'data-pw-panel="{scenario}"', source)
        # Kenntnisnahme einer Revision erledigt den Vorgang nicht.
        self.assertIn("Sie erledigt die Übergabe nicht", source)
        # Reset vorhanden.
        self.assertIn("data-pw-reset", source)
        # Getrennte Tagesaufgaben (Grün/Gelb/Blau).
        self.assertIn("Grün · täglich", source)
        self.assertIn("Gelb · Wochentagsrotation", source)
        self.assertIn("Blau · zusätzlich", source)

    def test_copy_has_one_home_for_each_core_explanation(self):
        source = self._template()
        for explanation in (
            "Vorschau mit fiktiven Beispieldaten – keine echte App-Sitzung.",
            "noch nicht in den App-Stores veröffentlicht",
            "Sie erledigt die Übergabe nicht",
            "Ohne Analytics oder Scoring",
            "Der Master-Admin legt Nutzer an",
            "Kein Einsatzleit-, Alarmierungs-, Diagnose- oder Patientensystem.",
        ):
            self.assertEqual(source.count(explanation), 1, explanation)
        for redundant_question in (
            "Wo laufen die Daten?",
            "Brauche ich für die Vorschau ein Konto?",
            "Welche Oberflächen gibt es?",
            "Drei Dinge, die die Schicht wirklich braucht.",
        ):
            self.assertNotIn(redundant_question, source)
        # The remaining navigation anchor points to its actual subject.
        self.assertEqual(source.count('id="funktionen"'), 1)
        self.assertIn('href="#funktionen">Betrieb</a>', source)

    def test_preview_respects_product_boundary(self):
        source = self._template()
        # Die Produktgrenze wird offen benannt.
        self.assertIn("Kein Einsatzleit-, Alarmierungs-, Diagnose- oder Patientensystem.", source)
        # Es gibt keine Felder oder Beispielwerte für Patienten-/Einsatzdaten.
        lowered = source.lower()
        for forbidden in ("patientenname", "einsatzdaten", "diagnose-daten", "alarmstufe", "einsatz-id"):
            self.assertNotIn(forbidden, lowered)
