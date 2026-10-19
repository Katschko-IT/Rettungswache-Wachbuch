"""Abnahmetests fuer Produkthilfe und Systemseite (H1/H3).

Deckt ab: anonyme Umleitung, Rollenmatrix, Stationsunabhaengigkeit der
Produkthilfe, de/en-Rendering mit echten Umlauten, lokale Suche (casefold,
Limit, leere/exotische Eingaben, XSS-reflect), 404/Traversal, reine GET-Semantik,
keine externen Netzaufrufe und keine Offenlegung von Umgebungsgeheimnissen.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from core import help as help_module
from core.models import Membership, Station

LANG_COOKIE = settings.LANGUAGE_COOKIE_NAME


class HelpSystemBase(TestCase):
    def setUp(self):
        super().setUp()
        self.station_a = Station.objects.create(name="Wache Alpha", slug="wache-alpha")
        self.station_b = Station.objects.create(name="Wache Beta", slug="wache-beta")

        self.admin = self._user("admin_a", self.station_a, Membership.Role.ADMIN)
        self.member = self._user("member_a", self.station_a, Membership.Role.MEMBER)
        self.lead = self._user("lead_a", self.station_a, Membership.Role.SHIFT_LEAD)
        self.foreign = self._user("member_b", self.station_b, Membership.Role.MEMBER)
        self.nobody = User.objects.create_user(username="nobody", password="x" * 12)

    def _user(self, username, station, role):
        user = User.objects.create_user(username=username, password="x" * 12)
        Membership.objects.create(user=user, station=station, role=role)
        return user

    def _client(self, user=None, language="de"):
        client = Client()
        if user is not None:
            client.force_login(user)
        client.cookies[LANG_COOKIE] = language
        return client


class HelpAccessTests(HelpSystemBase):
    def test_anonymous_redirects_to_login(self):
        response = self._client().get(reverse("help_index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/anmelden/", response["Location"])

    def test_member_of_any_station_gets_same_product_help(self):
        a = self._client(self.member).get(reverse("help_index"))
        b = self._client(self.foreign).get(reverse("help_index"))
        self.assertEqual(a.status_code, 200)
        self.assertEqual(b.status_code, 200)
        def main_region(response):
            body = response.content.decode()
            return body.split('<main id="inhalt"', 1)[1].split("</main>", 1)[0]

        self.assertEqual(main_region(a), main_region(b))
        self.assertNotIn("Wache Alpha", main_region(a))

    def test_authenticated_without_membership_redirects_to_access(self):
        response = self._client(self.nobody).get(reverse("help_index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("access"), response["Location"])

    def test_article_requires_membership(self):
        response = self._client().get(reverse("help_article", args=["erste-schritte"]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/anmelden/", response["Location"])

    def test_post_is_rejected(self):
        response = self._client(self.member).post(reverse("help_index"), {"q": "x"})
        self.assertEqual(response.status_code, 405)

    def test_session_remains_authenticated(self):
        client = self._client(self.member)
        client.get(reverse("help_index"))
        self.assertEqual(client.get(reverse("dashboard")).status_code, 200)


class HelpContentTests(HelpSystemBase):
    def test_manifest_is_complete_and_bilingual(self):
        revision = help_module.manifest_revision()
        self.assertEqual(revision, "2026-10-19.1")
        de = help_module.get_articles("de")
        en = help_module.get_articles("en")
        self.assertEqual(len(de), 7)
        self.assertEqual([a.slug for a in de], [a.slug for a in en])
        for article in de + en:
            self.assertTrue(article.title.strip())
            self.assertTrue(article.sections)

    def test_unknown_language_and_slug_are_empty(self):
        self.assertEqual(help_module.get_articles("fr"), [])
        self.assertIsNone(help_module.get_article("does-not-exist", "de"))
        self.assertIsNone(help_module.get_article("erste-schritte", "fr"))

    def test_article_renders_german_and_english(self):
        de = self._client(self.member).get(reverse("help_article", args=["uebergaben"]))
        en = self._client(self.member, language="en").get(reverse("help_article", args=["uebergaben"]))
        self.assertEqual(de.status_code, 200)
        self.assertEqual(en.status_code, 200)
        self.assertIn("Übergaben", de.content.decode())
        self.assertIn("Dienstübergaben", de.content.decode())
        self.assertIn("Handovers", en.content.decode())
        self.assertNotIn("Dienstübergaben", en.content.decode())
        self.assertIn("Quelle: Produkthandbuch Wachbuch 0.16.0", de.content.decode())
        self.assertIn("Artikelstand 1", de.content.decode())
        self.assertIn("Manifest 2026-10-19.1", de.content.decode())

    def test_english_ui_labels_and_version_page(self):
        body = self._client(self.admin, language="en").get(reverse("system_status")).content.decode()
        self.assertIn("Version and system status", body)
        self.assertIn("Pending migrations", body)
        self.assertIn("Build identifier", body)
        self.assertIn("not provided", body)
        help_en = self._client(self.member, language="en").get(reverse("help_index")).content.decode()
        self.assertIn("Search help", help_en)
        self.assertIn("Topics", help_en)

    def test_index_language_switch_keeps_articles_consistent(self):
        de = self._client(self.member).get(reverse("help_index")).content.decode()
        en = self._client(self.member, language="en").get(reverse("help_index")).content.decode()
        self.assertIn("Erste Schritte", de)
        self.assertIn("Getting started", en)

    def test_unknown_slug_and_traversal_return_404(self):
        client = self._client(self.member)
        self.assertEqual(client.get("/hilfe/gibt-es-nicht/").status_code, 404)
        self.assertEqual(client.get("/hilfe/..%2Fetc%2Fpasswd/").status_code, 404)
        self.assertEqual(client.get("/hilfe/UPPER-CASE/").status_code, 404)

    def test_content_contains_no_internal_docs(self):
        client = self._client(self.member)
        for slug in [a.slug for a in help_module.get_articles("de")]:
            body = client.get(reverse("help_article", args=[slug])).content.decode()
            for forbidden in ("AGENTS.md", "AuditEvent", "Traceback", "SECRET_KEY"):
                self.assertNotIn(forbidden, body)


class HelpSearchTests(HelpSystemBase):
    def test_search_casefold_and_umlauts(self):
        for query in ("Übergabe", "übergabe", "ÜBERGABE"):
            slugs = [a.slug for a in help_module.search(query, "de")]
            self.assertIn("uebergaben", slugs, query)
        english = [a.slug for a in help_module.search("handover", "en")]
        self.assertEqual(english[0], "uebergaben")
        self.assertIn("uebergaben", english)

    def test_empty_and_whitespace_query_returns_nothing(self):
        self.assertEqual(help_module.search("", "de"), [])
        self.assertEqual(help_module.search("   ", "de"), [])

    def test_limit_is_clamped_and_title_ranks_first(self):
        everything = help_module.search("e", "de", limit=999)
        self.assertLessEqual(len(everything), 50)
        self.assertEqual(help_module.search("e", "de", limit=0), everything[:1])

    def test_null_and_exotic_unicode_do_not_crash(self):
        for query in ("\x00", "🙂" * 5, "Übergabe\x00", "a" * 5000):
            self.assertIsInstance(help_module.search(query, "de"), list)

    def test_search_reflects_escaped_query(self):
        payload = "<script>alert(1)</script>"
        response = self._client(self.member).get(reverse("help_index"), {"q": payload})
        body = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("<script>alert(1)</script>", body)
        self.assertIn("&lt;script&gt;", body)

    def test_search_with_url_payload_is_not_linked(self):
        payload = "javascript:alert(1)"
        body = self._client(self.member).get(reverse("help_index"), {"q": payload}).content.decode()
        self.assertNotIn('href="javascript:', body)

    def test_search_matches_only_requested_language(self):
        slugs = [a.language for a in help_module.search("handover", "de")]
        self.assertNotIn("en", slugs)


class SystemStatusTests(HelpSystemBase):
    def test_member_and_lead_are_forbidden(self):
        for user in (self.member, self.lead):
            response = self._client(user).get(reverse("system_status"))
            self.assertEqual(response.status_code, 403, user.username)

    def test_anonymous_is_redirected(self):
        response = self._client().get(reverse("system_status"))
        self.assertEqual(response.status_code, 302)

    def test_admin_sees_version_and_minimal_diagnostics(self):
        response = self._client(self.admin).get(reverse("system_status"))
        body = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn(settings.APP_VERSION, body)
        self.assertIn("Erreichbarkeit", body)
        self.assertIn("Offene Migrationen", body)
        self.assertIn("Zwischenspeicher", body)
        self.assertNotIn(settings.SECRET_KEY, body)
        self.assertNotIn("/opt/data", body)

    def test_invalid_build_commit_is_reported_as_missing(self):
        with mock.patch.dict(os.environ, {"APP_BUILD_COMMIT": "not-a-hex-commit"}):
            body = self._client(self.admin).get(reverse("system_status")).content.decode()
        self.assertIn("nicht hinterlegt", body)
        self.assertNotIn("not-a-hex-commit", body)

    def test_valid_build_commit_is_shown(self):
        with mock.patch.dict(os.environ, {"APP_BUILD_COMMIT": "98bc6d4"}):
            body = self._client(self.admin).get(reverse("system_status")).content.decode()
        self.assertIn("98bc6d4", body)

    def test_no_external_network_calls(self):
        client = self._client(self.admin)
        with mock.patch("socket.create_connection", side_effect=AssertionError("network")), \
             mock.patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            self.assertEqual(client.get(reverse("system_status")).status_code, 200)
            self.assertEqual(client.get(reverse("help_index")).status_code, 200)

    def test_no_environment_dump(self):
        with mock.patch.dict(os.environ, {"WACHBUCH_LEAK_SENTINEL": "LEAK-ME-123"}):
            body = self._client(self.admin).get(reverse("system_status")).content.decode()
        self.assertNotIn("LEAK-ME-123", body)
        self.assertNotIn("WACHBUCH_LEAK_SENTINEL", body)


class HelpModuleValidationTests(TestCase):
    def _write(self, data: dict) -> str:
        import tempfile

        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(data, handle)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def _valid(self, **overrides):
        article = {
            "slug": "ok-slug",
            "language": "de",
            "title": "Titel",
            "summary": "Kurz",
            "revision": "1",
            "source": "Quelle",
            "sections": [{"heading": "A", "body": "B"}],
        }
        article.update(overrides)
        return {"manifest_revision": "test.1", "articles": [article]}

    def test_valid_manifest_loads(self):
        path = self._write(self._valid())
        help_module.reload(Path(path))
        self.assertEqual(help_module.get_article("ok-slug", "de").title, "Titel")
        self.assertEqual(help_module.manifest_revision(), "test.1")
        help_module.reload()

    def test_invalid_slug_is_rejected(self):
        path = self._write(self._valid(slug="../etc/passwd"))
        with self.assertRaises(help_module.HelpContentError):
            help_module.reload(Path(path))
        help_module.reload()

    def test_unknown_language_is_rejected(self):
        path = self._write(self._valid(language="fr"))
        with self.assertRaises(help_module.HelpContentError):
            help_module.reload(Path(path))
        help_module.reload()

    def test_duplicate_slug_language_is_rejected(self):
        article = self._valid()["articles"][0]
        path = self._write({"manifest_revision": "t", "articles": [article, article]})
        with self.assertRaises(help_module.HelpContentError):
            help_module.reload(Path(path))
        help_module.reload()
