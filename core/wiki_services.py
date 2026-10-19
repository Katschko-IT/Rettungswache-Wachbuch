from __future__ import annotations

import time

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import QuerySet
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from core.models import Station
from core.services import audit
from core.version import APP_VERSION
from core.wiki_models import WikiArticle, WikiRevision


class WikiConflict(Exception):
    """Die erwartete Ausgangsrevision ist nicht mehr aktuell."""

    def __init__(self, current_revision_number: int):
        self.current_revision_number = current_revision_number
        super().__init__(f"Revision {current_revision_number} ist aktuell.")


class WikiWriteConflict(Exception):
    """Konflikt beim Erstellen eines Wiki-Artikels (Slug-Race oder Datenbank ausgelastet)."""


class WikiSlugConflict(WikiWriteConflict):
    """Spezifischer Konflikt durch wiederholte Slug-Kollisionen."""


def _is_slug_unique_violation(exc: IntegrityError) -> bool:
    """
    Prüft, ob ein IntegrityError eine Slug-Kollision (unique_wiki_slug_per_station) darstellt.
    """
    cause = getattr(exc, "__cause__", None)
    if cause is not None:
        diag = getattr(cause, "diag", None)
        if diag is not None and getattr(diag, "constraint_name", None) == "unique_wiki_slug_per_station":
            return True

    msg = str(exc).lower()
    if "unique_wiki_slug_per_station" in msg:
        return True
    if "slug" in msg and ("unique" in msg or "duplicate" in msg):
        return True

    if cause is not None:
        cause_msg = str(cause).lower()
        if "unique_wiki_slug_per_station" in cause_msg:
            return True
        if "slug" in cause_msg and ("unique" in cause_msg or "duplicate" in cause_msg):
            return True

    return False


def _is_db_locked_error(exc: OperationalError) -> bool:
    """
    Prüft, ob ein OperationalError ein Busy- oder Lock-Fehler der Datenbank ist.
    """
    msg = str(exc).lower()
    busy_patterns = ("database is locked", "database table is locked", "locked", "busy")
    if any(pat in msg for pat in busy_patterns):
        return True
    cause = getattr(exc, "__cause__", None)
    if cause is not None:
        cause_msg = str(cause).lower()
        if any(pat in cause_msg for pat in busy_patterns):
            return True
    return False


def clean_title(raw: str) -> str:
    """
    Bereinigt und validiert den Titel eines Wiki-Artikels.

    Entfernt Whitespace an den Rändern. Weist leere Titel sowie Titel
    mit mehr als 160 Zeichen mit einem ValidationError ab.
    """
    if raw is None or not isinstance(raw, str):
        cleaned = ""
    else:
        cleaned = raw.strip()

    if not cleaned:
        raise ValidationError(_("Der Titel darf nicht leer sein."))
    if len(cleaned) > 160:
        raise ValidationError(_("Der Titel darf maximal 160 Zeichen lang sein."))
    return cleaned


def clean_body(raw: str) -> str:
    """
    Bereinigt und validiert den Inhalt eines Wiki-Artikels.

    Entfernt Whitespace an den Rändern, erhält jedoch interne Zeilenumbrüche.
    Weist leere Texte sowie Texte mit mehr als 8000 Zeichen mit einem
    ValidationError ab.
    """
    if raw is None or not isinstance(raw, str):
        cleaned = ""
    else:
        cleaned = raw.strip()

    if not cleaned:
        raise ValidationError(_("Der Text darf nicht leer sein."))
    if len(cleaned) > 8000:
        raise ValidationError(_("Der Text darf maximal 8000 Zeichen lang sein."))
    return cleaned


def unique_slug(
    station: Station,
    title: str,
    *,
    exclude_pk: int | None = None,
) -> str:
    """
    Erzeugt einen innerhalb einer Rettungswache eindeutigen Slug für einen Wiki-Artikel.

    Kollisionen werden fortlaufend durch Anhängen von -2, -3 etc. aufgelöst.
    Die Maximallänge beträgt 80 Zeichen.
    """
    base_slug = slugify(title)[:60].strip("-")
    if not base_slug:
        base_slug = "hinweis"

    candidate = base_slug
    counter = 1

    qs = WikiArticle.objects.filter(station=station)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)

    while qs.filter(slug=candidate).exists():
        counter += 1
        suffix = f"-{counter}"
        max_base_len = 80 - len(suffix)
        candidate = f"{base_slug[:max_base_len]}{suffix}"

    return candidate


@transaction.atomic
def create_article(
    *,
    station: Station,
    user: User | None,
    title: str,
    body: str,
) -> WikiArticle:
    """
    Erstellt einen neuen Wiki-Artikel inklusive initialer Revision 1 atomar.

    Erzeugt einen Audit-Eintrag für die Erstellung.
    """
    cleaned_title = clean_title(title)
    cleaned_body = clean_body(body)

    Station.objects.select_for_update().get(pk=station.pk)
    initial_slug = unique_slug(station, cleaned_title)

    base_slug = slugify(cleaned_title)[:60].strip("-")
    if not base_slug:
        base_slug = "hinweis"

    article: WikiArticle | None = None
    tried_slugs: set[str] = set()
    max_attempts = 8
    candidate_slug = initial_slug
    # Ein Datenbank-Lock ist kein Slug-Konflikt: derselbe Kandidat wird erneut
    # versucht, statt dem Artikel unnoetig ein Suffix zu geben.
    retry_same_slug = False

    for attempt in range(1, max_attempts + 1):
        if attempt > 1 and not retry_same_slug:
            candidate_slug = unique_slug(station, cleaned_title)
            if candidate_slug in tried_slugs:
                counter = attempt
                while True:
                    suffix = f"-{counter}"
                    candidate_slug = f"{base_slug[:80 - len(suffix)]}{suffix}"
                    if candidate_slug not in tried_slugs:
                        break
                    counter += 1

        tried_slugs.add(candidate_slug)

        try:
            with transaction.atomic():
                candidate_article = WikiArticle(
                    station=station,
                    slug=candidate_slug,
                    title=cleaned_title,
                    body=cleaned_body,
                    is_archived=False,
                    current_revision_number=1,
                    created_by=user,
                )
                candidate_article.full_clean(validate_constraints=False)
                candidate_article.save()
                article = candidate_article
                break
        except IntegrityError as exc:
            if not _is_slug_unique_violation(exc):
                raise
            retry_same_slug = False
            if attempt == max_attempts:
                raise WikiSlugConflict(
                    "Artikel konnte wegen Slug-Konflikten nicht angelegt werden."
                ) from exc
        except OperationalError as exc:
            if not _is_db_locked_error(exc):
                raise
            retry_same_slug = True
            if attempt == max_attempts:
                raise WikiWriteConflict(
                    "Datenbank ist ausgelastet. Bitte versuchen Sie es erneut."
                ) from exc
            time.sleep(0.05)

    if article is None:
        raise WikiWriteConflict("Artikel konnte nicht angelegt werden.")

    revision = WikiRevision(
        article=article,
        number=1,
        title=cleaned_title,
        body=cleaned_body,
        edited_by=user,
        app_version=APP_VERSION,
    )
    revision.full_clean()
    revision.save()

    audit(user, station, "wiki.article_created", article, {"revision": 1})
    return article


@transaction.atomic
def update_article(
    *,
    article: WikiArticle,
    user: User | None,
    expected_revision: int,
    title: str,
    body: str,
) -> WikiArticle:
    """
    Aktualisiert einen Wiki-Artikel atomar unter Berücksichtigung optimistischer Sperren.

    Prüft, ob die aktuelle Revision mit der erwarteten Ausgangsrevision übereinstimmt.
    Bei Abweichung wird ein WikiConflict ausgelöst. Bei Erfolg wird eine neue
    Revision angelegt, der Artikel aktualisiert und ein Audit-Eintrag geschrieben.
    """
    cleaned_title = clean_title(title)
    cleaned_body = clean_body(body)

    locked = WikiArticle.objects.select_for_update().get(pk=article.pk)
    if locked.current_revision_number != expected_revision:
        raise WikiConflict(locked.current_revision_number)

    next_number = locked.current_revision_number + 1

    revision = WikiRevision(
        article=locked,
        number=next_number,
        title=cleaned_title,
        body=cleaned_body,
        edited_by=user,
        app_version=APP_VERSION,
    )
    revision.full_clean()
    revision.save()

    locked.title = cleaned_title
    locked.body = cleaned_body
    locked.current_revision_number = next_number
    locked.full_clean()
    locked.save(update_fields=["title", "body", "current_revision_number", "updated_at"])

    article.refresh_from_db()
    audit(user, locked.station, "wiki.article_updated", locked, {"revision": next_number})
    return article


@transaction.atomic
def set_archived(
    *,
    article: WikiArticle,
    user: User | None,
    archived: bool,
    expected_revision: int | None = None,
) -> WikiArticle:
    """
    Archiviert oder reaktiviert einen Wiki-Artikel atomar.

    Erzeugt keine neue Inhaltsrevision, hinterlässt jedoch einen Audit-Eintrag.
    Wird expected_revision übergeben, wird diese optimistisch geprüft.
    """
    locked = WikiArticle.objects.select_for_update().get(pk=article.pk)
    if (
        isinstance(expected_revision, bool)
        or not isinstance(expected_revision, int)
        or expected_revision < 1
        or locked.current_revision_number != expected_revision
    ):
        raise WikiConflict(locked.current_revision_number)

    locked.is_archived = bool(archived)
    locked.save(update_fields=["is_archived", "updated_at"])

    article.refresh_from_db()

    action = "wiki.article_archived" if archived else "wiki.article_restored"
    audit(
        user,
        locked.station,
        action,
        locked,
        {"revision": locked.current_revision_number},
    )
    return article


def revision_history(
    article: WikiArticle,
    *,
    limit: int | None = None,
) -> QuerySet[WikiRevision]:
    """
    Liefert den Revisionsverlauf eines Wiki-Artikels in absteigender Reihenfolge.
    """
    qs = WikiRevision.objects.filter(article=article).select_related("edited_by").order_by("-number")
    if limit is not None and limit > 0:
        return qs[:limit]
    return qs
