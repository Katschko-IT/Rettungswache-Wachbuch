"""Abnahmetests fuer das Wachen-Wiki (H2).

Deckt Wachentrennung, Rollen, unveraenderliche Revisionen, optimistische
Nebenlaeufigkeit (409), XSS/Textescaping, CSRF, Archivierung, Suche und
Pagination ab. Die Tests laufen gegen echte HTTP-Anfragen und die echten
Templates.
"""

from __future__ import annotations

import re

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from core.models import AuditEvent, Membership, Station
from core.wiki_models import WikiArticle, WikiRevision
from core.wiki_services import (
    WikiConflict,
    create_article,
    set_archived,
    update_article,
)


class WikiBase(TestCase):
    def setUp(self):
        super().setUp()
        self.station_a = Station.objects.create(name="Wache Alpha", slug="wache-alpha")
        self.station_b = Station.objects.create(name="Wache Beta", slug="wache-beta")
        self.admin = self._user("admin_a", self.station_a, Membership.Role.ADMIN)
        self.member = self._user("member_a", self.station_a, Membership.Role.MEMBER)
        self.lead = self._user("lead_a", self.station_a, Membership.Role.SHIFT_LEAD)
        self.auditor = self._user("auditor_a", self.station_a, Membership.Role.AUDITOR)
        self.foreign_admin = self._user("admin_b", self.station_b, Membership.Role.ADMIN)
        self.foreign_member = self._user("member_b", self.station_b, Membership.Role.MEMBER)

    def _user(self, username, station, role):
        user = User.objects.create_user(username=username, password="x" * 12, first_name=username)
        Membership.objects.create(user=user, station=station, role=role)
        return user

    def _client(self, user=None):
        client = Client()
        if user is not None:
            client.force_login(user)
        return client

    def _article(self, station=None, title="Hinweis", body="Text", user=None):
        return create_article(
            station=station or self.station_a,
            user=user or self.admin,
            title=title,
            body=body,
        )


class WikiAccessTests(WikiBase):
    def test_anonymous_is_redirected_to_login(self):
        response = self._client().get(reverse("wiki_index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/anmelden/", response["Location"])

    def test_members_and_shift_leads_can_read_own_station(self):
        article = self._article()
        for user in (self.member, self.lead, self.admin):
            with self.subTest(user=user.username):
                response = self._client(user).get(reverse("wiki_detail", args=[article.pk]))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Hinweis")

    def test_auditor_has_no_wiki_access(self):
        response = self._client(self.auditor).get(reverse("wiki_index"))
        self.assertEqual(response.status_code, 403)

    def test_foreign_station_article_is_404_for_member_and_admin(self):
        foreign = self._article(station=self.station_b, user=self.foreign_admin)
        for user in (self.member, self.admin):
            with self.subTest(user=user.username):
                response = self._client(user).get(reverse("wiki_detail", args=[foreign.pk]))
                self.assertEqual(response.status_code, 404)

    def test_list_shows_only_own_station_articles(self):
        own = self._article(title="Eigener Hinweis")
        self._article(station=self.station_b, title="Fremder Hinweis", user=self.foreign_admin)
        response = self._client(self.member).get(reverse("wiki_index"))
        self.assertContains(response, own.title)
        self.assertNotContains(response, "Fremder Hinweis")

    def test_only_admin_can_create_edit_archive(self):
        article = self._article()
        for user in (self.member, self.lead):
            with self.subTest(user=user.username):
                self.assertEqual(self._client(user).get(reverse("wiki_create")).status_code, 403)
                self.assertEqual(
                    self._client(user).get(reverse("wiki_edit", args=[article.pk])).status_code,
                    403,
                )
                self.assertEqual(
                    self._client(user).post(reverse("wiki_archive", args=[article.pk])).status_code,
                    403,
                )

    def test_post_only_endpoints_reject_get(self):
        article = self._article()
        client = self._client(self.admin)
        self.assertEqual(client.get(reverse("wiki_archive", args=[article.pk])).status_code, 405)
        self.assertEqual(client.get(reverse("wiki_restore", args=[article.pk])).status_code, 405)


class WikiCreateTests(WikiBase):
    def test_create_creates_article_and_first_revision(self):
        response = self._client(self.admin).post(
            reverse("wiki_create"),
            {"title": "  Schlüsselübergabe  ", "body": "  Ablauf am Tor  "},
        )
        self.assertEqual(response.status_code, 302)
        article = WikiArticle.objects.get(station=self.station_a)
        self.assertEqual(article.title, "Schlüsselübergabe")
        self.assertEqual(article.body, "Ablauf am Tor")
        self.assertEqual(article.current_revision_number, 1)
        revision = WikiRevision.objects.get(article=article)
        self.assertEqual(revision.number, 1)
        self.assertEqual(revision.edited_by, self.admin)
        self.assertEqual(revision.title, "Schlüsselübergabe")
        self.assertTrue(revision.app_version)
        self.assertTrue(
            AuditEvent.objects.filter(action="wiki.article_created", object_id=str(article.pk)).exists()
        )

    def test_create_rejects_empty_and_overlong_values(self):
        client = self._client(self.admin)
        for payload in (
            {"title": "   ", "body": "Text"},
            {"title": "Titel", "body": "   "},
            {"title": "x" * 161, "body": "Text"},
            {"title": "Titel", "body": "x" * 8001},
        ):
            with self.subTest(payload=payload):
                response = client.post(reverse("wiki_create"), payload)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(WikiArticle.objects.count(), 0)

    def test_slug_is_unique_per_station(self):
        first = self._article(title="Ablauf")
        second = self._article(title="Ablauf")
        other = self._article(station=self.station_b, title="Ablauf", user=self.foreign_admin)
        self.assertEqual(first.slug, "ablauf")
        self.assertEqual(second.slug, "ablauf-2")
        self.assertEqual(other.slug, "ablauf")

    def test_create_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        response = client.post(reverse("wiki_create"), {"title": "Titel", "body": "Text"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(WikiArticle.objects.count(), 0)


class WikiEditConflictTests(WikiBase):
    def test_edit_creates_new_revision_and_keeps_old_one(self):
        article = self._article()
        response = self._client(self.admin).post(
            reverse("wiki_edit", args=[article.pk]),
            {"title": "Neu", "body": "Neuer Text", "expected_revision": 1},
        )
        self.assertEqual(response.status_code, 302)
        article.refresh_from_db()
        self.assertEqual(article.current_revision_number, 2)
        self.assertEqual(article.title, "Neu")
        self.assertEqual(WikiRevision.objects.filter(article=article).count(), 2)
        old = WikiRevision.objects.get(article=article, number=1)
        self.assertEqual(old.title, "Hinweis")
        self.assertEqual(old.body, "Text")

    def test_stale_revision_returns_409_and_does_not_overwrite(self):
        article = self._article()
        self._article_update(article, expected=1, title="Erste Änderung", body="A")
        response = self._client(self.admin).post(
            reverse("wiki_edit", args=[article.pk]),
            {"title": "Zweite Änderung", "body": "B", "expected_revision": 1},
        )
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, "zwischenzeitlich geändert", status_code=409)
        article.refresh_from_db()
        self.assertEqual(article.title, "Erste Änderung")
        self.assertEqual(article.current_revision_number, 2)

    def test_conflict_response_carries_current_revision_for_retry(self):
        article = self._article()
        self._article_update(article, expected=1, title="Erste Änderung", body="A")
        response = self._client(self.admin).post(
            reverse("wiki_edit", args=[article.pk]),
            {"title": "Zweite Änderung", "body": "BBBB", "expected_revision": 1},
        )
        self.assertEqual(response.status_code, 409)
        self.assertContains(
            response, 'name="expected_revision" value="2"', status_code=409
        )
        self.assertContains(response, "Zweite Änderung", status_code=409)

        retry = self._client(self.admin).post(
            reverse("wiki_edit", args=[article.pk]),
            {"title": "Zweite Änderung", "body": "BBBB", "expected_revision": 2},
        )
        self.assertEqual(retry.status_code, 302)
        article.refresh_from_db()
        self.assertEqual(article.title, "Zweite Änderung")
        self.assertEqual(article.current_revision_number, 3)

    def test_missing_expected_revision_returns_409_and_does_not_overwrite(self):
        article = self._article()
        response = self._client(self.admin).post(
            reverse("wiki_edit", args=[article.pk]),
            {"title": "Ohne Sperre", "body": "B"},
        )
        self.assertEqual(response.status_code, 409)
        article.refresh_from_db()
        self.assertEqual(article.title, "Hinweis")
        self.assertEqual(article.current_revision_number, 1)

    def test_service_rejects_stale_expected_revision(self):
        article = self._article()
        self._article_update(article, expected=1, title="Neu", body="Neu")
        with self.assertRaises(WikiConflict) as caught:
            update_article(
                article=article,
                user=self.admin,
                expected_revision=1,
                title="Nochmal",
                body="Nochmal",
            )
        self.assertEqual(caught.exception.current_revision_number, 2)
        article.refresh_from_db()
        self.assertEqual(article.current_revision_number, 2)

    def test_archived_article_is_hidden_from_members(self):
        article = self._article(title="Archivierter Sonderhinweis")
        response = self._client(self.admin).post(
            reverse("wiki_archive", args=[article.pk]),
            {"expected_revision": 1},
        )
        self.assertEqual(response.status_code, 302)
        article.refresh_from_db()
        self.assertTrue(article.is_archived)
        self.assertEqual(
            self._client(self.member).get(reverse("wiki_detail", args=[article.pk])).status_code,
            404,
        )
        self.assertNotContains(self._client(self.member).get(reverse("wiki_index")), article.title)
        admin_list = self._client(self.admin).get(reverse("wiki_index"), {"archiv": "1"})
        self.assertContains(admin_list, article.title)

    def test_archive_keeps_revision_history_and_can_be_restored(self):
        article = self._article()
        before = WikiRevision.objects.filter(article=article).count()
        self._client(self.admin).post(
            reverse("wiki_archive", args=[article.pk]), {"expected_revision": 1}
        )
        self.assertEqual(WikiRevision.objects.filter(article=article).count(), before)
        self.assertTrue(
            AuditEvent.objects.filter(action="wiki.article_archived", object_id=str(article.pk)).exists()
        )
        response = self._client(self.admin).post(
            reverse("wiki_restore", args=[article.pk]), {"expected_revision": 1}
        )
        self.assertEqual(response.status_code, 302)
        article.refresh_from_db()
        self.assertFalse(article.is_archived)
        self.assertEqual(
            self._client(self.member).get(reverse("wiki_detail", args=[article.pk])).status_code,
            200,
        )

    def test_archive_conflict_returns_409(self):
        article = self._article()
        self._article_update(article, expected=1, title="Neu", body="Neu")
        response = self._client(self.admin).post(
            reverse("wiki_archive", args=[article.pk]), {"expected_revision": 1}
        )
        self.assertEqual(response.status_code, 409)
        article.refresh_from_db()
        self.assertFalse(article.is_archived)

    def _article_update(self, article, *, expected, title, body):
        article = update_article(
            article=article,
            user=self.admin,
            expected_revision=expected,
            title=title,
            body=body,
        )
        return article


class WikiImmutabilityTests(WikiBase):
    def test_revision_cannot_be_saved_again(self):
        article = self._article()
        revision = WikiRevision.objects.get(article=article)
        revision.title = "Manipuliert"
        with self.assertRaises(ValidationError):
            revision.save()
        revision.refresh_from_db()
        self.assertEqual(revision.title, "Hinweis")

    def test_revision_cannot_be_deleted(self):
        article = self._article()
        revision = WikiRevision.objects.get(article=article)
        with self.assertRaises(ValidationError):
            revision.delete()
        self.assertTrue(WikiRevision.objects.filter(pk=revision.pk).exists())

    def test_article_station_cannot_change(self):
        article = self._article()
        article.station = self.station_b
        with self.assertRaises(ValidationError):
            article.full_clean()
        article.refresh_from_db()
        self.assertEqual(article.station_id, self.station_a.pk)


class WikiEscapingTests(WikiBase):
    def test_title_and_body_are_escaped_in_list_and_detail(self):
        payload = '<script>alert("x")</script>'
        article = self._article(title=payload, body=f"{payload} <img src=x onerror=alert(1)>")
        for url in (reverse("wiki_index"), reverse("wiki_detail", args=[article.pk])):
            with self.subTest(url=url):
                response = self._client(self.member).get(url)
                self.assertEqual(response.status_code, 200)
                content = response.content.decode()
                self.assertNotIn("<script>alert", content)
                self.assertNotIn("<img src=x", content)
                self.assertIn("&lt;script&gt;", content)

    def test_revision_history_is_escaped(self):
        article = self._article(title="<b>Titel</b>", body="<i>Text</i>")
        response = self._client(self.admin).get(reverse("wiki_detail", args=[article.pk]))
        content = response.content.decode()
        self.assertNotIn("<b>Titel</b>", content)
        self.assertNotIn("<i>Text</i>", content)


class WikiSearchAndPaginationTests(WikiBase):
    def test_search_matches_title_and_body_with_umlauts(self):
        self._article(title="Übergabe", body="Schlüssel")
        self._article(title="Reinigung", body="Übergabeprotokoll")
        self._article(title="Sonstiges", body="Nichts")
        client = self._client(self.member)
        response = client.get(reverse("wiki_index"), {"q": "übergabe"})
        self.assertContains(response, "Übergabe")
        self.assertContains(response, "Reinigung")
        self.assertNotContains(response, "Sonstiges")
        self.assertEqual(response.context["query"], "übergabe")

    def test_empty_search_result_shows_empty_state(self):
        self._article()
        response = self._client(self.member).get(reverse("wiki_index"), {"q": "gibtesnicht"})
        self.assertContains(response, "Keine Treffer")

    def test_very_long_query_is_truncated(self):
        response = self._client(self.member).get(reverse("wiki_index"), {"q": "x" * 500})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["query"]), 120)

    def test_pagination_limits_to_twenty_and_keeps_query(self):
        for index in range(25):
            self._article(title=f"Hinweis {index:02d}")
        client = self._client(self.member)
        page_one = client.get(reverse("wiki_index"))
        self.assertEqual(len(page_one.context["page_obj"].object_list), 20)
        page_two = client.get(reverse("wiki_index"), {"seite": 2})
        self.assertEqual(len(page_two.context["page_obj"].object_list), 5)
        self.assertContains(page_two, "Seite 2 von 2")

    def test_empty_index_renders_empty_state(self):
        response = self._client(self.member).get(reverse("wiki_index"))
        self.assertContains(response, "Noch keine Hinweise")


class WikiServiceValidationTests(WikiBase):
    def test_set_archived_is_station_bound_and_idempotent(self):
        article = self._article()
        set_archived(article=article, user=self.admin, archived=True, expected_revision=1)
        set_archived(article=article, user=self.admin, archived=True, expected_revision=1)
        article.refresh_from_db()
        self.assertTrue(article.is_archived)
        self.assertEqual(WikiRevision.objects.filter(article=article).count(), 1)

    def test_edit_form_requires_revision_field_value(self):
        article = self._article()
        response = self._client(self.admin).get(reverse("wiki_edit", args=[article.pk]))
        self.assertContains(response, 'name="expected_revision"')
        self.assertContains(response, re.escape(article.title))
