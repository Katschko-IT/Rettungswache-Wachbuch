from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import OperationalError
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from core.access import CONTENT_ROLES, membership_required
from core.models import Membership
from core.wiki_forms import WikiArticleForm
from core.wiki_models import WikiArticle, WikiRevision
from core.wiki_services import (
    WikiConflict,
    WikiWriteConflict,
    _is_db_locked_error,
    create_article,
    set_archived,
    update_article,
)

WIKI_ROLES = CONTENT_ROLES
WIKI_ADMIN = {Membership.Role.ADMIN}


@membership_required(WIKI_ROLES)
@require_GET
def wiki_index(request):
    station = request.membership.station
    can_manage = request.membership.role in WIKI_ADMIN

    raw_query = request.GET.get("q", "")
    query = raw_query.strip()[:120]

    show_archived = can_manage and request.GET.get("archiv") == "1"

    qs = WikiArticle.objects.filter(station=station)
    if not show_archived:
        qs = qs.filter(is_archived=False)

    qs = qs.order_by("-updated_at", "-id")

    if query and query.isascii():
        # Der Datenbankfilter ist schnell, faltet aber auf SQLite nur ASCII.
        qs = qs.filter(Q(title__icontains=query) | Q(body__icontains=query))
    elif query:
        # Umlaute und andere Nicht-ASCII-Zeichen werden portabel in Python
        # verglichen; die Menge ist auf die Artikel dieser Wache begrenzt.
        needle = query.casefold()
        qs = [
            article
            for article in qs
            if needle in article.title.casefold() or needle in article.body.casefold()
        ]

    archived_count = (
        WikiArticle.objects.filter(station=station, is_archived=True).count()
        if can_manage
        else 0
    )

    paginator = Paginator(qs, 20)
    page_number = request.GET.get("seite", 1)
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "core/wiki_index.html",
        {
            "page_obj": page_obj,
            "query": query,
            "show_archived": show_archived,
            "can_manage": can_manage,
            "archived_count": archived_count,
        },
    )


@membership_required(WIKI_ROLES)
@require_GET
@never_cache
def wiki_detail(request, pk):
    station = request.membership.station
    can_manage = request.membership.role in WIKI_ADMIN

    article = get_object_or_404(WikiArticle, pk=pk, station=station)
    if article.is_archived and not can_manage:
        raise Http404

    revisions = (
        WikiRevision.objects.filter(article=article)
        .select_related("edited_by")
        .order_by("-number")[:50]
    )

    return render(
        request,
        "core/wiki_detail.html",
        {
            "article": article,
            "revisions": revisions,
            "can_manage": can_manage,
            "conflict": False,
            "current_revision": article.current_revision_number,
        },
    )


@membership_required(WIKI_ADMIN)
@require_http_methods(["GET", "POST"])
@never_cache
def wiki_create(request):
    station = request.membership.station

    if request.method == "POST":
        form = WikiArticleForm(request.POST)
        if form.is_valid():
            try:
                article = create_article(
                    station=station,
                    user=request.user,
                    title=form.cleaned_data["title"],
                    body=form.cleaned_data["body"],
                )
                messages.success(request, _("Hinweis erfolgreich angelegt."))
                return redirect("wiki_detail", pk=article.pk)
            except ValidationError as exc:
                form.add_error(None, exc)
            except WikiWriteConflict:
                form.add_error(
                    None,
                    _("Der Hinweis konnte aufgrund eines gleichzeitigen Schreibkonflikts nicht angelegt werden. Bitte versuchen Sie es erneut."),
                )
                return render(
                    request,
                    "core/wiki_form.html",
                    {
                        "form": form,
                        "page_title": _("Neuen Hinweis anlegen"),
                        "can_manage": True,
                        "conflict": False,
                        "article": None,
                    },
                    status=409,
                )
            except OperationalError as exc:
                if not _is_db_locked_error(exc):
                    raise
                form.add_error(
                    None,
                    _("Die Datenbank ist derzeit ausgelastet. Bitte versuchen Sie es erneut."),
                )
                return render(
                    request,
                    "core/wiki_form.html",
                    {
                        "form": form,
                        "page_title": _("Neuen Hinweis anlegen"),
                        "can_manage": True,
                        "conflict": False,
                        "article": None,
                    },
                    status=409,
                )
    else:
        form = WikiArticleForm()

    return render(
        request,
        "core/wiki_form.html",
        {
            "form": form,
            "page_title": _("Neuen Hinweis anlegen"),
            "can_manage": True,
            "conflict": False,
            "article": None,
        },
    )


@membership_required(WIKI_ADMIN)
@require_http_methods(["GET", "POST"])
@never_cache
def wiki_edit(request, pk):
    station = request.membership.station
    article = get_object_or_404(WikiArticle, pk=pk, station=station)

    conflict = False
    current_revision = article.current_revision_number

    if request.method == "POST":
        form = WikiArticleForm(request.POST)
        if form.is_valid():
            expected = form.cleaned_data.get("expected_revision")
            if expected is None:
                # Ohne Revisionsnummer ist kein optimistischer Vergleich moeglich.
                # Nicht auf die aktuelle Revision zurueckfallen, sonst wuerde ein
                # paralleler Schreibvorgang still ueberschrieben (Lost Update).
                conflict_form = WikiArticleForm(
                    initial={
                        "title": form.cleaned_data["title"],
                        "body": form.cleaned_data["body"],
                        "expected_revision": current_revision,
                    }
                )
                return render(
                    request,
                    "core/wiki_form.html",
                    {
                        "form": conflict_form,
                        "article": article,
                        "page_title": _("Hinweis bearbeiten"),
                        "conflict": True,
                        "current_revision": current_revision,
                        "can_manage": True,
                    },
                    status=409,
                )
            try:
                article = update_article(
                    article=article,
                    user=request.user,
                    expected_revision=expected,
                    title=form.cleaned_data["title"],
                    body=form.cleaned_data["body"],
                )
                messages.success(request, _("Hinweis erfolgreich aktualisiert."))
                return redirect("wiki_detail", pk=article.pk)
            except WikiConflict as exc:
                # Die eigene Eingabe bleibt sichtbar, das Hidden-Feld traegt aber
                # bereits die aktuelle Revision, damit ein erneutes Speichern
                # nicht wieder gegen denselben Konflikt laeuft.
                conflict_form = WikiArticleForm(
                    initial={
                        "title": form.cleaned_data["title"],
                        "body": form.cleaned_data["body"],
                        "expected_revision": exc.current_revision_number,
                    }
                )
                return render(
                    request,
                    "core/wiki_form.html",
                    {
                        "form": conflict_form,
                        "article": article,
                        "page_title": _("Hinweis bearbeiten"),
                        "conflict": True,
                        "current_revision": exc.current_revision_number,
                        "can_manage": True,
                    },
                    status=409,
                )
            except ValidationError as exc:
                form.add_error(None, exc)
    else:
        form = WikiArticleForm(
            initial={
                "title": article.title,
                "body": article.body,
                "expected_revision": article.current_revision_number,
            }
        )

    return render(
        request,
        "core/wiki_form.html",
        {
            "form": form,
            "article": article,
            "page_title": _("Hinweis bearbeiten"),
            "conflict": conflict,
            "current_revision": current_revision,
            "can_manage": True,
        },
    )


@membership_required(WIKI_ADMIN)
@require_POST
@never_cache
def wiki_archive(request, pk):
    station = request.membership.station
    article = get_object_or_404(WikiArticle, pk=pk, station=station)

    raw_revision = request.POST.get("expected_revision")
    expected_revision = None
    if raw_revision is not None:
        raw_str = str(raw_revision).strip()
        try:
            parsed = int(raw_str)
            if parsed >= 1:
                expected_revision = parsed
        except (ValueError, TypeError):
            expected_revision = None

    if expected_revision is None:
        revisions = (
            WikiRevision.objects.filter(article=article)
            .select_related("edited_by")
            .order_by("-number")[:50]
        )
        return render(
            request,
            "core/wiki_detail.html",
            {
                "article": article,
                "revisions": revisions,
                "can_manage": True,
                "conflict": True,
                "current_revision": article.current_revision_number,
            },
            status=409,
        )

    try:
        set_archived(
            article=article,
            user=request.user,
            archived=True,
            expected_revision=expected_revision,
        )
        messages.success(request, _("Hinweis wurde archiviert."))
        return redirect("wiki_detail", pk=article.pk)
    except WikiConflict as exc:
        revisions = (
            WikiRevision.objects.filter(article=article)
            .select_related("edited_by")
            .order_by("-number")[:50]
        )
        return render(
            request,
            "core/wiki_detail.html",
            {
                "article": article,
                "revisions": revisions,
                "can_manage": True,
                "conflict": True,
                "current_revision": exc.current_revision_number,
            },
            status=409,
        )


@membership_required(WIKI_ADMIN)
@require_POST
@never_cache
def wiki_restore(request, pk):
    station = request.membership.station
    article = get_object_or_404(WikiArticle, pk=pk, station=station)

    raw_revision = request.POST.get("expected_revision")
    expected_revision = None
    if raw_revision is not None:
        raw_str = str(raw_revision).strip()
        try:
            parsed = int(raw_str)
            if parsed >= 1:
                expected_revision = parsed
        except (ValueError, TypeError):
            expected_revision = None

    if expected_revision is None:
        revisions = (
            WikiRevision.objects.filter(article=article)
            .select_related("edited_by")
            .order_by("-number")[:50]
        )
        return render(
            request,
            "core/wiki_detail.html",
            {
                "article": article,
                "revisions": revisions,
                "can_manage": True,
                "conflict": True,
                "current_revision": article.current_revision_number,
            },
            status=409,
        )

    try:
        set_archived(
            article=article,
            user=request.user,
            archived=False,
            expected_revision=expected_revision,
        )
        messages.success(request, _("Hinweis wurde wiederhergestellt."))
        return redirect("wiki_detail", pk=article.pk)
    except WikiConflict as exc:
        revisions = (
            WikiRevision.objects.filter(article=article)
            .select_related("edited_by")
            .order_by("-number")[:50]
        )
        return render(
            request,
            "core/wiki_detail.html",
            {
                "article": article,
                "revisions": revisions,
                "can_manage": True,
                "conflict": True,
                "current_revision": exc.current_revision_number,
            },
            status=409,
        )
