"""Views fuer den Sprachwechsel."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect
from django.utils import translation
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from core.i18n import normalize_language, set_language_cookie
from core.models import UserProfile


@require_POST
def set_language(request: HttpRequest) -> HttpResponse:
    """Sprachwechsel via POST ohne Session-Aenderungen."""
    raw_language = request.POST.get("language")
    language = normalize_language(raw_language)
    if not language:
        return HttpResponseBadRequest("Ungültige Sprache.", content_type="text/plain; charset=utf-8")

    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "/"
    if not url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = "/"

    if request.user.is_authenticated:
        profile = UserProfile.for_user(request.user)
        if profile.language != language:
            profile.language = language
            profile.save(update_fields=["language", "updated_at"])

    translation.activate(language)
    response = redirect(next_url)
    set_language_cookie(response, language)
    return response
