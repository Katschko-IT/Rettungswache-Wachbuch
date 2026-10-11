"""Middleware-Schicht fuer das Wachbuch.

Sammelt nur technische, nicht personenbezogene Daten (Pfad, Methode,
Korrelations-ID). Request-Bodies, Formularfelder und Auth-Header werden
nicht geloggt.
"""

from __future__ import annotations

import logging
import re

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.urls import Resolver404, resolve

from .errors import (
    REQUEST_ATTR_CORRELATION_ID,
    RESPONSE_CORRELATION_HEADER,
    correlation_id_for_request,
    log_exception,
)


# Hostname or leading-dot suffix, e.g. fcm.googleapis.com / .push.apple.com.
_CSP_HOST_RE = re.compile(
    r"^\.?[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$"
)


def csp_connect_src(allowed_hosts=None):
    """Build ``connect-src`` from the Push HTTPS allowlist.

    The previous ``https:`` scheme source allowed the browser to talk to any
    HTTPS origin. Push subscriptions only need the configured push hosts.
    """
    hosts = (
        allowed_hosts
        if allowed_hosts is not None
        else getattr(settings, "PUSH_ALLOWED_ENDPOINT_HOSTS", set())
    )
    extra = set()
    for raw in hosts or ():
        entry = (raw or "").strip().lower()
        if not entry or not _CSP_HOST_RE.fullmatch(entry):
            continue
        if entry.startswith("."):
            extra.add(f"https://{entry[1:]}")
            extra.add(f"https://*{entry}")
        else:
            extra.add(f"https://{entry}")
    return " ".join(["'self'", *sorted(extra)])


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Scheme-relative redirects such as //example.org are interpreted as
        # external destinations by browsers. The Wachbuch has no intentional
        # cross-origin redirects, so fail closed to the local root.
        location = response.headers.get("Location")
        if location and location.startswith("//"):
            response.headers["Location"] = "/"

        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            f"script-src 'self'; font-src 'self'; connect-src {csp_connect_src()}; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=(), "
            "publickey-credentials-get=(self), publickey-credentials-create=(self)"
        )
        return response


class CorrelationIdMiddleware:
    """Stellt pro Request eine Korrelations-ID bereit.

    * Uebernimmt eine gueltige ``X-Correlation-ID`` aus dem Request (Pattern
      ``[A-Za-z0-9_-]{1,128}``), erzeugt sonst eine frische UUID4.
    * Legt die ID auf ``request.correlation_id`` ab.
    * Setzt sie als ``X-Correlation-ID`` in jede Antwort.
    * Schreibt sie als ``correlation_id`` Log-``extra`` fuer strukturierte Logs.
    """

    HEADER = RESPONSE_CORRELATION_HEADER

    def __init__(self, get_response):
        self.get_response = get_response
        self._logger = logging.getLogger("wachbuch.requests")

    def __call__(self, request: HttpRequest) -> HttpResponse:
        correlation_id = correlation_id_for_request(request)
        setattr(request, REQUEST_ATTR_CORRELATION_ID, correlation_id)
        self._logger.info(
            "request_started method=%s path=%s correlation_id=%s",
            request.method or "",
            request.path or "",
            correlation_id,
            extra={"correlation_id": correlation_id},
        )
        try:
            response = self.get_response(request)
        except Exception:
            log_exception(request, message="request_failed")
            raise
        response[self.HEADER] = correlation_id
        return response


class ClientIPMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.client_ip = self._extract(request)
        return self.get_response(request)

    def _extract(self, request):
        trusted = bool(getattr(settings, "TRUSTED_PROXY", False))
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if trusted and forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = (request.META.get("REMOTE_ADDR") or "unknown").strip()
        if not ip or len(ip) > 64:
            ip = "unknown"
        return ip


# Routes that a visitor of the public demo must never reach. The set targets
# real, existing URL names (see ``config/urls.py`` and ``core/urls.py``) rather
# than hardcoded paths, so the block stays correct if routes move.
PUBLIC_DEMO_BLOCKED_URL_NAMES = frozenset({
    # No self-service registration / account creation.
    "register",
    "team_user_create",
    "team_create",
    "membership_update",
    "registration_reject",
    # No station-wide configuration changes (could re-enable feeds/push/modules).
    "station_settings",
    # No security-mechanism changes on the shared demo accounts.
    "mfa_setup",
    "mfa_disable",
    "passkey_register_options",
    "passkey_register_verify",
    "passkey_delete",
    # No credential / egress artefacts.
    "api_tokens_manage",
    "push_settings",
    "calendar_feed_manage",
    "api_v1_token",
    "api_v1_anmeldung",
    # No passwordless demo entry: the public demo is behind the login form only.
    "demo_login",
})


class PublicDemoGuardMiddleware:
    """Server-side guard for the public, internet-facing demo instance.

    Active only while ``settings.DEMO_PUBLIC_MODE`` is true. It resolves the
    incoming request to its URL name and raises ``Http404`` for forbidden
    operations, so no production-style control (Django admin, registration,
    user/membership management, station settings, MFA/passkey enrolment, API
    tokens, push subscriptions, calendar feed links) is reachable by a demo
    visitor. Read/write routes of the operational modules (handovers, calendar,
    tasks, defects, assets, checklists, coffee fund) stay reachable, but the
    passwordless ``demo_login`` entry does not.

    Placed last in ``MIDDLEWARE`` so the resulting 404 still flows back through
    the outer security-header middleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if getattr(settings, "DEMO_PUBLIC_MODE", False):
            try:
                match = resolve(request.path_info)
            except Resolver404:
                match = None
            if match is not None and (
                match.namespace == "admin"
                or match.url_name in PUBLIC_DEMO_BLOCKED_URL_NAMES
            ):
                raise Http404
        return self.get_response(request)


__all__ = [
    "SecurityHeadersMiddleware",
    "CorrelationIdMiddleware",
    "ClientIPMiddleware",
    "PublicDemoGuardMiddleware",
    "PUBLIC_DEMO_BLOCKED_URL_NAMES",
    "csp_connect_src",
]
