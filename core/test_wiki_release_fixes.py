"""Regressionstests fuer die Wiki-Reviewbefunde F1 (Slug-Race) und F2 (Revision).

F1: Parallele Anlage desselben Titels darf weder HTTP 500 noch einen
    Teilzustand (Artikel ohne Revision/Audit) erzeugen. Die echte
    PostgreSQL-Stationssperre ist auf SQLite ein No-op; deshalb pruefen diese
    Tests zusaetzlich den gebundenen Savepoint-Retry und die kontrollierte
    Fehlerantwort.
F2: Archivieren/Wiederherstellen ohne gueltige ``expected_revision`` muss
    fail-closed mit 409 enden und darf das Archiv-Flag nicht veraendern.

Die Tests sind bewusst ohne Import der neuen internen Exceptions geschrieben,
damit derselbe Testlauf auch gegen den ungefix ten Ausgangsstand rot werden
kann (Import-Fehler waeren kein Verhaltensnachweis).
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth.models import User
from django.db import IntegrityError, OperationalError
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

SLUG_CONSTRAINT = 'duplicate key value violates unique constraint "unique_wiki_slug_per_station"'
WIKI_AUDIT_ACTIONS = (
    "wiki.article_created",
    "wiki.article_archived",
    "wiki.article_restored",
)


class ReleaseFixBase(TestCase):
    def setUp(self):
        super().setUp()
        self.station = Station.objects.create(name="Wache Fix", slug="wache-fix")
        self.other_station = Station.objects.create(name="Wache Fremd", slug="wache-fremd")
        self.admin = self._user("fix_admin", self.station, Membership.Role.ADMIN)
        self.foreign_admin = self._user(
            "fix_foreign_admin", self.other_station, Membership.Role.ADMIN
        )

    def _user(self, username, station, role):
        user = User.objects.create_user(username=username, password="x" * 12)
        Membership.objects.create(user=user, station=station, role=role)
        return user

    def _client(self, user=None, *, raise_request_exception=True):
        client = Client(raise_request_exception=raise_request_exception)
        if user is not None:
            client.force_login(user)
        return client

    def _article(self, title="Hinweis", body="Text"):
        return create_article(
            station=self.station, user=self.admin, title=title, body=body
        )

    def _counts(self):
        return (
            WikiArticle.objects.count(),
            WikiRevision.objects.count(),
            AuditEvent.objects.filter(action__in=WIKI_AUDIT_ACTIONS).count(),
        )


class SlugRaceServiceTests(ReleaseFixBase):
    def test_slug_collision_on_insert_retries_with_next_candidate(self):
        original_save = WikiArticle.save
        calls = {"save": 0}

        def flaky_save(instance, *args, **kwargs):
            calls["save"] += 1
            if calls["save"] == 1:
                raise IntegrityError(SLUG_CONSTRAINT)
            return original_save(instance, *args, **kwargs)

        with mock.patch.object(WikiArticle, "save", flaky_save):
            article = create_article(
                station=self.station, user=self.admin, title="Race", body="Inhalt"
            )

        self.assertEqual(calls["save"], 2)
        self.assertEqual(article.slug, "race-2")
        self.assertEqual(WikiArticle.objects.count(), 1)
        self.assertEqual(WikiRevision.objects.filter(article=article).count(), 1)
        self.assertEqual(
            WikiRevision.objects.get(article=article).number, 1
        )
        self.assertEqual(
            AuditEvent.objects.filter(
                action="wiki.article_created", object_id=str(article.pk)
            ).count(),
            1,
        )

    def test_exhausted_slug_retries_raise_controlled_error_without_writes(self):
        with mock.patch.object(
            WikiArticle, "save", side_effect=IntegrityError(SLUG_CONSTRAINT)
        ):
            with self.assertRaises(Exception) as ctx:
                create_article(
                    station=self.station, user=self.admin, title="Race", body="X"
                )

        self.assertNotIsInstance(ctx.exception, IntegrityError)
        self.assertEqual(self._counts(), (0, 0, 0))

    def test_non_slug_integrity_error_is_not_swallowed(self):
        with mock.patch.object(
            WikiArticle, "save", side_effect=IntegrityError("NOT NULL constraint failed")
        ):
            with self.assertRaises(IntegrityError):
                create_article(
                    station=self.station, user=self.admin, title="Race", body="X"
                )

        self.assertEqual(self._counts(), (0, 0, 0))

    def test_slug_not_null_error_is_not_mistaken_for_a_unique_collision(self):
        # Enthaelt "slug" und "constraint", ist aber keine Eindeutigkeitsverletzung.
        with mock.patch.object(
            WikiArticle,
            "save",
            side_effect=IntegrityError(
                "NOT NULL constraint failed: core_wikiarticle.slug"
            ),
        ):
            with self.assertRaises(IntegrityError):
                create_article(
                    station=self.station, user=self.admin, title="Race", body="X"
                )

        self.assertEqual(self._counts(), (0, 0, 0))

    def test_busy_database_is_retried_then_succeeds(self):
        original_save = WikiArticle.save
        calls = {"save": 0}

        def busy_once(instance, *args, **kwargs):
            calls["save"] += 1
            if calls["save"] == 1:
                raise OperationalError("database is locked")
            return original_save(instance, *args, **kwargs)

        with mock.patch.object(WikiArticle, "save", busy_once):
            article = create_article(
                station=self.station, user=self.admin, title="Busy", body="X"
            )

        self.assertEqual(calls["save"], 2)
        self.assertEqual(article.slug, "busy")
        self.assertEqual(self._counts(), (1, 1, 1))

    def test_persistent_busy_database_raises_controlled_error_without_writes(self):
        with mock.patch.object(
            WikiArticle, "save", side_effect=OperationalError("database is locked")
        ):
            with self.assertRaises(Exception) as ctx:
                create_article(
                    station=self.station, user=self.admin, title="Busy", body="X"
                )

        self.assertNotIsInstance(ctx.exception, OperationalError)
        self.assertEqual(self._counts(), (0, 0, 0))

    def test_revision_failure_rolls_back_article_and_audit(self):
        with mock.patch.object(
            WikiRevision, "save", side_effect=RuntimeError("revision write failed")
        ):
            with self.assertRaises(RuntimeError):
                create_article(
                    station=self.station, user=self.admin, title="Atomar", body="X"
                )

        self.assertEqual(self._counts(), (0, 0, 0))


class SlugRaceViewTests(ReleaseFixBase):
    def test_create_view_slug_race_returns_409_and_writes_nothing(self):
        client = self._client(self.admin, raise_request_exception=False)
        with mock.patch.object(
            WikiArticle, "save", side_effect=IntegrityError(SLUG_CONSTRAINT)
        ):
            response = client.post(
                reverse("wiki_create"), {"title": "Race", "body": "Inhalt"}
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(self._counts(), (0, 0, 0))

    def test_create_view_busy_database_returns_409_and_writes_nothing(self):
        client = self._client(self.admin, raise_request_exception=False)
        with mock.patch.object(
            WikiArticle, "save", side_effect=OperationalError("database is locked")
        ):
            response = client.post(
                reverse("wiki_create"), {"title": "Busy", "body": "Inhalt"}
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(self._counts(), (0, 0, 0))

    def test_create_view_unexpected_db_error_is_not_masked_as_success(self):
        client = self._client(self.admin, raise_request_exception=False)
        with mock.patch.object(
            WikiArticle,
            "save",
            side_effect=IntegrityError("FOREIGN KEY constraint failed"),
        ):
            response = client.post(
                reverse("wiki_create"), {"title": "Anders", "body": "Inhalt"}
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(self._counts(), (0, 0, 0))


class ArchiveRevisionServiceTests(ReleaseFixBase):
    def test_set_archived_without_expected_revision_fails_closed(self):
        article = self._article()
        with self.assertRaises(WikiConflict):
            set_archived(article=article, user=self.admin, archived=True)

        article.refresh_from_db()
        self.assertFalse(article.is_archived)
        self.assertEqual(self._counts(), (1, 1, 1))

    def test_set_archived_rejects_empty_nonnumeric_zero_negative_and_bool(self):
        for value in (None, "", "   ", "abc", "1.5", 0, -1, 1.0, True):
            with self.subTest(value=repr(value)):
                article = self._article(title=f"Hinweis {repr(value)}")
                with self.assertRaises(WikiConflict):
                    set_archived(
                        article=article,
                        user=self.admin,
                        archived=True,
                        expected_revision=value,
                    )
                article.refresh_from_db()
                self.assertFalse(article.is_archived)
                self.assertEqual(
                    AuditEvent.objects.filter(
                        action="wiki.article_archived", object_id=str(article.pk)
                    ).count(),
                    0,
                )

    def test_set_archived_stale_revision_still_conflicts_without_write(self):
        article = self._article()
        update_article(
            article=article,
            user=self.admin,
            expected_revision=1,
            title="Hinweis neu",
            body="Neuer Text",
        )
        with self.assertRaises(WikiConflict):
            set_archived(
                article=article, user=self.admin, archived=True, expected_revision=1
            )
        article.refresh_from_db()
        self.assertFalse(article.is_archived)


class ArchiveRevisionViewTests(ReleaseFixBase):
    def test_archive_missing_expected_revision_returns_409_without_write(self):
        article = self._article()
        response = self._client(self.admin).post(reverse("wiki_archive", args=[article.pk]))

        self.assertEqual(response.status_code, 409)
        article.refresh_from_db()
        self.assertFalse(article.is_archived)
        self.assertEqual(
            AuditEvent.objects.filter(
                action="wiki.article_archived", object_id=str(article.pk)
            ).count(),
            0,
        )

    def test_archive_invalid_expected_revision_values_return_409(self):
        for value in ("", "   ", "abc", "1.5", "0", "-1"):
            with self.subTest(value=repr(value)):
                article = self._article(title=f"Archiv {repr(value)}")
                response = self._client(self.admin).post(
                    reverse("wiki_archive", args=[article.pk]),
                    {"expected_revision": value},
                )
                self.assertEqual(response.status_code, 409)
                article.refresh_from_db()
                self.assertFalse(article.is_archived)

    def test_restore_without_expected_revision_returns_409_without_write(self):
        article = self._article()
        set_archived(
            article=article, user=self.admin, archived=True, expected_revision=1
        )
        response = self._client(self.admin).post(reverse("wiki_restore", args=[article.pk]))

        self.assertEqual(response.status_code, 409)
        article.refresh_from_db()
        self.assertTrue(article.is_archived)

    def test_restore_invalid_expected_revision_values_return_409(self):
        article = self._article()
        set_archived(
            article=article, user=self.admin, archived=True, expected_revision=1
        )
        for value in ("", "abc", "0", "-3"):
            with self.subTest(value=repr(value)):
                response = self._client(self.admin).post(
                    reverse("wiki_restore", args=[article.pk]),
                    {"expected_revision": value},
                )
                self.assertEqual(response.status_code, 409)
                article.refresh_from_db()
                self.assertTrue(article.is_archived)

    def test_valid_expected_revision_still_archives_and_restores(self):
        article = self._article()
        response = self._client(self.admin).post(
            reverse("wiki_archive", args=[article.pk]), {"expected_revision": "1"}
        )
        self.assertEqual(response.status_code, 302)
        article.refresh_from_db()
        self.assertTrue(article.is_archived)

        response = self._client(self.admin).post(
            reverse("wiki_restore", args=[article.pk]), {"expected_revision": "1"}
        )
        self.assertEqual(response.status_code, 302)
        article.refresh_from_db()
        self.assertFalse(article.is_archived)
