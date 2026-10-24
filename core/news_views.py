"""Ansichten für den Bereich Neuigkeiten."""
from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods
from urllib.parse import quote

from .access import CONTENT_ROLES, membership_required
from .api.wachalltag import (
    ALLOWED_ATTACHMENT_TYPES,
    MAX_ATTACHMENT_BYTES,
    attachment_is_valid,
)
from .models import NewsAttachment, NewsPost
from .news import acknowledge, acknowledgement_status, active_posts, archived_posts
from .services import audit

EDITOR_ROLES = {"shift_lead", "admin"}


@membership_required(CONTENT_ROLES)
@require_GET
def news_index(request):
    station = request.membership.station
    posts = []
    for post in active_posts(station).select_related("created_by").prefetch_related("attachments"):
        status = acknowledgement_status(post)
        posts.append({
            "post": post,
            "status": status,
            "has_read": request.user.id not in status["missing"],
        })
    archive = []
    for post in archived_posts(station).select_related("created_by")[:20]:
        status = acknowledgement_status(post)
        archive.append({"post": post, "status": status})
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
            upload = request.FILES.get("attachment")
            if upload is None:
                messages.error(request, _("Bitte eine Datei auswählen."))
            elif upload.content_type not in ALLOWED_ATTACHMENT_TYPES:
                messages.error(request, _("Erlaubt sind JPEG, PNG, WebP und PDF."))
            elif upload.size > MAX_ATTACHMENT_BYTES:
                messages.error(request, _("Datei darf maximal 5 MiB groß sein."))
            else:
                raw = upload.read()
                if not attachment_is_valid(raw, upload.content_type):
                    messages.error(request, _("Datei ist kein gültiges Bild und kein lesbares PDF."))
                else:
                    with transaction.atomic():
                        NewsAttachment.objects.create(
                            post=post,
                            station=station,
                            filename=upload.name[:180],
                            content_type=upload.content_type,
                            data=raw,
                            size=len(raw),
                            uploaded_by=request.user,
                        )
                    messages.success(request, _("Anhang wurde hinzugefügt."))
                    return redirect("news_detail", pk=pk)
    status = acknowledgement_status(post)
    return render(request, "core/news_detail.html", {
        "post": post,
        "status": status,
        "has_read": request.user.id not in status["missing"],
        "attachments": post.attachments.select_related("uploaded_by").all(),
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
        if not title or not body:
            messages.error(request, _("Bitte Titel und Text ausfüllen."))
        else:
            with transaction.atomic():
                post = NewsPost.objects.create(
                    station=station,
                    title=title[:160],
                    body=body[:4000],
                    created_by=request.user,
                )
                audit(request.user, station, "news.created", post, {"fields": ["title"]})
                upload = request.FILES.get("attachment")
                if upload and upload.content_type in ALLOWED_ATTACHMENT_TYPES and upload.size <= MAX_ATTACHMENT_BYTES:
                    raw = upload.read()
                    if attachment_is_valid(raw, upload.content_type):
                        NewsAttachment.objects.create(
                            post=post,
                            station=station,
                            filename=upload.name[:180],
                            content_type=upload.content_type,
                            data=raw,
                            size=len(raw),
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
