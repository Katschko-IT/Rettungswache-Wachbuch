"""Sprachhelfer und I18N-Infrastruktur fuer das Wachbuch."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.utils import translation
from django.utils.cache import patch_vary_headers

SUPPORTED_LANGUAGES: tuple[str, ...] = tuple(code for code, _ in settings.LANGUAGES)


def normalize_language(value: Any) -> str | None:
    """Normalisiert einen Sprachcode und prueft gegen SUPPORTED_LANGUAGES."""
    if not value or not isinstance(value, str):
        return None
    cleaned = value.strip().replace("_", "-")
    if not cleaned:
        return None
    primary = cleaned.split("-")[0].lower()
    if primary in SUPPORTED_LANGUAGES:
        return primary
    return None


def preferred_language(user: Any) -> str | None:
    """Liest user.profile.language defensiv ohne erzwungene Queries."""
    if not user or not getattr(user, "is_authenticated", False):
        return None
    try:
        profile = getattr(user, "profile", None)
    except ObjectDoesNotExist:
        return None
    if profile is None:
        return None
    lang = getattr(profile, "language", "")
    return normalize_language(lang)


def request_language(request: Any) -> str:
    """Ermittelt die effektive Sprache des Requests: Cookie > get_language > Default."""
    cookie_name = getattr(settings, "LANGUAGE_COOKIE_NAME", "wachbuch_language")
    if request is not None:
        cookie_val = getattr(request, "COOKIES", {}).get(cookie_name)
        normalized_cookie = normalize_language(cookie_val)
        if normalized_cookie:
            return normalized_cookie
    current = normalize_language(translation.get_language())
    if current:
        return current
    fallback = normalize_language(getattr(settings, "LANGUAGE_CODE", "de"))
    return fallback or "de"


def set_language_cookie(response: Any, language: str) -> None:
    """Setzt das Sprachcookie, Content-Language und Vary: Cookie auf der Response."""
    valid_language = normalize_language(language) or getattr(settings, "LANGUAGE_CODE", "de")
    cookie_name = getattr(settings, "LANGUAGE_COOKIE_NAME", "wachbuch_language")
    max_age = getattr(settings, "LANGUAGE_COOKIE_AGE", 31_536_000)
    samesite = getattr(settings, "LANGUAGE_COOKIE_SAMESITE", "Lax")
    secure = getattr(settings, "LANGUAGE_COOKIE_SECURE", False)
    httponly = getattr(settings, "LANGUAGE_COOKIE_HTTPONLY", True)

    response.set_cookie(
        cookie_name,
        valid_language,
        max_age=max_age,
        path="/",
        secure=secure,
        httponly=httponly,
        samesite=samesite,
    )
    response["Content-Language"] = valid_language
    patch_vary_headers(response, ("Cookie",))


def apply_login_language(request: Any, user: Any, response: Any) -> Any:
    """Aktiviert Nutzersprache nach Login, wenn kein Sprachcookie vorhanden ist."""
    cookie_name = getattr(settings, "LANGUAGE_COOKIE_NAME", "wachbuch_language")
    has_cookie = bool(request and getattr(request, "COOKIES", {}).get(cookie_name))
    if not has_cookie:
        lang = preferred_language(user)
        if lang:
            translation.activate(lang)
            set_language_cookie(response, lang)
    return response
