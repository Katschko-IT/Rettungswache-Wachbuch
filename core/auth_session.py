"""Session auth stamping and freshness helpers."""

from __future__ import annotations

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.utils import timezone

SESSION_KEY_AUTH_TIME = "auth_time"
SESSION_KEY_AUTH_USER_ID = "auth_user_id"
SESSION_KEY_AUTH_METHOD = "auth_method"


@receiver(user_logged_in)
def stamp_auth_session(sender, request, user, **kwargs):
    """Stamp session with auth_time, auth_user_id, and auth_method on login."""
    if request and hasattr(request, "session"):
        request.session[SESSION_KEY_AUTH_TIME] = int(timezone.now().timestamp())
        request.session[SESSION_KEY_AUTH_USER_ID] = user.pk
        if not request.session.get(SESSION_KEY_AUTH_METHOD):
            request.session[SESSION_KEY_AUTH_METHOD] = "password"


def get_auth_method(request) -> str | None:
    """Return the stamped auth method only if it belongs to request.user."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return None
    if request.session.get(SESSION_KEY_AUTH_USER_ID) != request.user.pk:
        return None
    method = request.session.get(SESSION_KEY_AUTH_METHOD)
    if isinstance(method, str) and method:
        return method
    return None


def get_auth_time(request) -> int | None:
    """Return auth_time integer timestamp if present and belongs to request.user."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return None
    session_user_id = request.session.get(SESSION_KEY_AUTH_USER_ID)
    if session_user_id != request.user.pk:
        return None
    auth_time = request.session.get(SESSION_KEY_AUTH_TIME)
    if isinstance(auth_time, (int, float)):
        return int(auth_time)
    return None


def get_auth_age(request) -> int | None:
    """Return age of authentication in seconds, or None if unstamped / mismatched."""
    auth_time = get_auth_time(request)
    if auth_time is None:
        return None
    now_ts = int(timezone.now().timestamp())
    age = now_ts - auth_time
    return max(0, age)


def is_auth_fresh(request, max_age_seconds: int) -> bool:
    """True if authentication is stamped, belongs to request.user, and age <= max_age_seconds."""
    age = get_auth_age(request)
    if age is None:
        return False
    return age <= max_age_seconds
