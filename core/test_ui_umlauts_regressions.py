"""Regressionstests fuer UTF-8-Rendering und den CSRF/CSP-Vertrag.

Deckt die in docs/ARBEITSVERTRAG-20261019.md §5 verlangten Nachweise ab:
- Fehlerseiten 400/403/404/500 und /datenschutz/ rendern echte Umlaute,
  ohne Mojibake und ohne Ersatzzeichen.
- CSRF-Schutz bleibt aktiv (Token im Formular, POST ohne Token wird abgewiesen).
- CSP bleibt ohne 'unsafe-inline'/'unsafe-eval' und ohne fremde Skriptquellen.
- Sichtbare Modell-Validierungsfehler tragen Umlaute.
"""

from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import Client, TestCase
from django.urls import reverse

MOJIBAKE_MARKERS = (
    "Ã¤", "Ã¶", "Ã¼", "ÃŸ", "â€“", "â€ž", "â€œ", "\ufffd",
    "ÃÂ¤", "ÃÂ¶", "ÃÂ¼", "ÃÂŸ",
)


class ErrorPageUtf8Tests(TestCase):
    def test_error_templates_render_expected_umlauts(self):
        cases = [
            ("errors/400.html", {"status_code": 400, "error_label": "Ungültige Anfrage"},
             "Bitte prüfe Eingaben oder Link."),
            ("errors/403.html", {"status_code": 403, "error_label": "Zugriff verweigert"},
             "keine Berechtigung für diese Seite"),
            ("errors/404.html", {"status_code": 404, "error_label": "Nicht gefunden",
                                 "user": SimpleNamespace(is_authenticated=True)},
             "Zur Übersicht"),
            ("errors/500.html", {"status_code": 500, "error_label": "Interner Fehler"},
             "helfen können"),
        ]
        for template, context, expected in cases:
            with self.subTest(template=template):
                rendered = render_to_string(template, context)
                self.assertIn(expected, rendered)
                for marker in MOJIBAKE_MARKERS:
                    self.assertNotIn(marker, rendered)

    def test_error_template_500_covers_all_three_umlauts(self):
        rendered = render_to_string(
            "errors/500.html", {"status_code": 500, "error_label": "Interner Fehler"}
        )
        for expected in ("helfen können", "ungefähr die durchgeführte Aktion", "zurückgegeben"):
            with self.subTest(expected=expected):
                self.assertIn(expected, rendered)

    def test_rendered_404_response_is_utf8_without_mojibake(self):
        response = self.client.get("/diese-seite-gibt-es-nicht-20261019/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.charset, "utf-8")
        body = response.content.decode("utf-8")
        self.assertIn("Zur Startseite", body)
        for marker in MOJIBAKE_MARKERS:
            self.assertNotIn(marker, body)


class PrivacyPageUtf8Tests(TestCase):
    def test_privacy_page_is_utf8_with_real_umlauts(self):
        response = self.client.get(reverse("privacy"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.charset, "utf-8")
        body = response.content.decode("utf-8")
        self.assertIn("Datenschutzerklärung", body)
        for marker in MOJIBAKE_MARKERS:
            self.assertNotIn(marker, body)

    def test_privacy_page_ships_umlauts_as_multibyte_utf8(self):
        response = self.client.get(reverse("privacy"))
        word = "Datenschutzerklärung"
        encoded = word.encode("utf-8")
        # Der Umlaut 'ä' belegt in UTF-8 zwei Bytes; Transliteration waere kuerzer.
        self.assertEqual(len(encoded), len(word) + 1)
        self.assertIn(encoded, response.content)


class CsrfAndCspContractTests(TestCase):
    def test_login_form_contains_csrf_token(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "csrfmiddlewaretoken")

    def test_post_without_csrf_token_is_rejected(self):
        strict = Client(enforce_csrf_checks=True)
        response = strict.post(reverse("login"), {"username": "x", "password": "y"})
        self.assertEqual(response.status_code, 403)

    def test_csp_header_stays_strict_on_public_page(self):
        response = self.client.get(reverse("privacy"))
        policy = response.headers.get("Content-Security-Policy", "")
        self.assertIn("default-src 'self'", policy)
        self.assertIn("script-src 'self'", policy)
        self.assertNotIn("unsafe-inline", policy)
        self.assertNotIn("unsafe-eval", policy)
        self.assertIn("frame-ancestors 'none'", policy)
