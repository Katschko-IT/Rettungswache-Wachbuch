"""Ansichten für den Bereich Neuigkeiten."""
from __future__ import annotations

from collections import defaultdict

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Prefetch
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods
from urllib.parse import quote

from .access import CONTENT_ROLES, membership_required
from .api.wachalltag import (
    MAX_ATTACHMENT_BYTES,
    MAX_ATTACHMENTS_PER_HANDOVER,
)
from .attachments import read_upload
from .models import NewsAcknowledgement, NewsAttachment, NewsPost
from .news import (
    acknowledge,
    acknowledgement_status,
    active_posts,
    archived_posts,
    news_audience_ids,
    status_from,
)
from .services import audit

EDITOR_ROLES = {"shift_lead", "admin"}


@membership_required(CONTENT_ROLES)
@require_GET
def news_index(request):
    station = request.membership.station
    # Leserschaft und Quittungen einmal für alle Neuigkeiten laden; Anhänge
    # nur als Kennung (die Liste zeigt bloß „mit Anhang“, nicht den Inhalt).
    audience = news_audience_ids(station)
    active = list(active_posts(station).select_related("created_by").prefetch_related(
        Prefetch("attachments", queryset=NewsAttachment.objects.only("id", "post_id")),
    ))
    archived = list(archived_posts(station).select_related("created_by")[:20])
    acknowledged = defaultdict(set)
    for post_id, user_id in NewsAcknowledgement.objects.filter(
        post__in=[post.pk for post in active + archived],
    ).values_list("post_id", "user_id"):
        acknowledged[post_id].add(user_id)
    posts = []
    for post in active:
        status = status_from(audience, acknowledged[post.pk])
        posts.append({
            "post": post,
            "status": status,
            "has_read": request.user.id not in status["missing"],
        })
    archive = [{"post": post, "status": status_from(audience, acknowledged[post.pk])} for post in archived]
    return render(request, "core/news_index.html", {
        "posts": posts,
        "archive": archive,
        "can_edit": request.membership.role in EDITOR_ROLES,
    })


@membership_required(CONTENT_ROLES)
@require_http_methods(["GET", "POST"])
def news_detail(request, pk):
    station = request.membership.station
    post = get_object_or_404(NewsPost, pk=pk, station=station)
    if request.method == "POST":
        if request.POST.get("action") == "acknowledge":
            from .terminal import is_service_user

            if is_service_user(request.user):
                raise PermissionDenied
            status = acknowledge(post, request.user)
            if status["complete"]:
                messages.success(request, _("Danke – alle haben gelesen. Die Neuigkeit ist im Archiv."))
            else:
                messages.success(request, _("Als gelesen quittiert."))
            return redirect("news_detail", pk=pk)
        if request.POST.get("action") == "upload" and request.membership.role in EDITOR_ROLES:
            if post.attachments.count() >= MAX_ATTACHMENTS_PER_HANDOVER:
                messages.error(request, _("Mehr Anhänge sind nicht möglich."))
            else:
                # Prüft Typ, Größe und Inhalt; Bilder ohne Metadaten (EXIF, GPS).
                upload, upload_error = read_upload(request.FILES.get("attachment"))
                if upload_error:
                    messages.error(request, upload_error)
                else:
                    with transaction.atomic():
                        NewsAttachment.objects.create(
                            post=post,
                            station=station,
                            filename=upload.name,
                            content_type=upload.content_type,
                            data=upload.data,
                            size=upload.size,
                            uploaded_by=request.user,
                        )
                    messages.success(request, _("Anhang wurde hinzugefügt."))
                    return redirect("news_detail", pk=pk)
    status = acknowledgement_status(post)
    return render(request, "core/news_detail.html", {
        "post": post,
        "status": status,
        "has_read": request.user.id not in status["missing"],
        "attachments": post.attachments.select_related("uploaded_by").defer("data"),
        "max_attachments": MAX_ATTACHMENTS_PER_HANDOVER,
        "can_edit": request.membership.role in EDITOR_ROLES,
        "max_upload_mb": MAX_ATTACHMENT_BYTES // (1024 * 1024),
    })


@membership_required(CONTENT_ROLES)
@require_http_methods(["GET", "POST"])
def news_create(request):
    if request.membership.role not in EDITOR_ROLES:
        return redirect("news_index")
    station = request.membership.station
    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        body = (request.POST.get("body") or "").strip()
        upload, upload_error = None, None
        if request.FILES.get("attachment") is not None:
            # Vor dem Veröffentlichen prüfen: Ein abgelehnter Anhang verschwindet
            # nicht still, Titel und Text bleiben im Formular stehen.
            upload, upload_error = read_upload(request.FILES.get("attachment"))
        if not title or not body:
            messages.error(request, _("Bitte Titel und Text ausfüllen."))
        elif upload_error:
            messages.error(request, upload_error)
        else:
            with transaction.atomic():
                post = NewsPost.objects.create(
                    station=station,
                    title=title[:160],
                    body=body[:4000],
                    created_by=request.user,
                )
                audit(request.user, station, "news.created", post, {"fields": ["title"]})
                if upload is not None:
                    NewsAttachment.objects.create(
                        post=post,
                        station=station,
                        filename=upload.name,
                        content_type=upload.content_type,
                        data=upload.data,
                        size=upload.size,
                        uploaded_by=request.user,
                    )
            messages.success(request, _("Neuigkeit wurde veröffentlicht."))
            return redirect("news_detail", pk=post.pk)
    return render(request, "core/news_form.html", {"max_upload_mb": MAX_ATTACHMENT_BYTES // (1024 * 1024)})


@membership_required(CONTENT_ROLES)
@require_GET
def news_attachment(request, pk):
    item = get_object_or_404(
        NewsAttachment, pk=pk, station=request.membership.station
    )
    response = HttpResponse(bytes(item.data), content_type=item.content_type)
    response["Content-Length"] = str(item.size)
    response["Content-Disposition"] = f"inline; filename*=UTF-8''{quote(item.filename)}"
    response["Cache-Control"] = "private, no-store"
    return response
