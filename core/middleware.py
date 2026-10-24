"""Middleware-Schicht fuer das Wachbuch.

Sammelt nur technische, nicht personenbezogene Daten (Pfad, Methode,
Korrelations-ID). Request-Bodies, Formularfelder und Auth-Header werden
nicht geloggt.
"""

from __future__ import annotations

import logging
import re

from django.conf import settings
from django.http import HttpRequest, HttpResponse

from .errors import (
    REQUEST_ATTR_CORRELATION_ID,
    RESPONSE_CORRELATION_HEADER,
    correlation_id_for_request,
    log_exception,
    redact_request_path,
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


CAMERA_SCANNER_VIEWS = frozenset({"mpg_dashboard", "fleet_dashboard", "warehouse_dashboard"})


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
        # Kamera nur auf den Seiten mit optionalem Code-Scanner, und nur für
        # die eigene Origin; überall sonst bleibt sie gesperrt.
        match = getattr(request, "resolver_match", None)
        camera = "(self)" if match and match.url_name in CAMERA_SCANNER_VIEWS else "()"
        response.headers["Permissions-Policy"] = (
            f"camera={camera}, microphone=(), geolocation=(), payment=(), usb=(), "
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
            redact_request_path(request.path),
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
        return client_ip_from_request(request)


def client_ip_from_request(request):
    """Client-IP für Rate-Limits und Sperren.

    Hinter genau einem vertrauenswürdigen Reverse-Proxy (``TRUSTED_PROXY``)
    zählt der Eintrag, den dieser Proxy an ``X-Forwarded-For`` angehängt hat –
    also der rechte. Weiter links stehende Einträge kann der Client selbst
    setzen und sind deshalb wertlos.
    """
    trusted = bool(getattr(settings, "TRUSTED_PROXY", False))
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = ""
    if trusted and forwarded:
        ip = forwarded.split(",")[-1].strip()
    if not ip:
        ip = (request.META.get("REMOTE_ADDR") or "unknown").strip()
    if not ip or len(ip) > 64:
        ip = "unknown"
    return ip


def axes_client_ip(request, *args, **kwargs):
    """Callable für ``AXES_CLIENT_IP_CALLABLE`` mit derselben Proxy-Logik."""
    return client_ip_from_request(request)


class MfaEnforcementMiddleware:
    """Setzt ``MFA_REQUIRED`` für angemeldete Web-Sitzungen durch.

    Ohne bestätigten zweiten Faktor bleiben nur Einrichtung, Abmeldung und
    technische Pfade erreichbar. Die Token-API prüft MFA an ihren eigenen
    Ausgabestellen (``obtain_token``, ``pairing_exchange``).
    """

    ALLOWED_PREFIXES = (
        "/konto/mfa/",
        "/anmelden/",
        "/aktivieren/",
        "/setup/",
        "/abmelden/",
        "/api/",
        "/healthz/",
        "/offline/",
        "/datenschutz/",
        "/manifest.webmanifest",
        "/service-worker.js",
        "/favicon.ico",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._must_set_up_mfa(request):
            from django.shortcuts import redirect

            if request.method in ("GET", "HEAD"):
                return redirect("mfa_setup")
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied
        return self.get_response(request)

    def _must_set_up_mfa(self, request):
        from .mfa import mfa_enabled, mfa_required, user_has_confirmed_mfa

        user = getattr(request, "user", None)
        if not (mfa_enabled() and mfa_required() and user is not None and user.is_authenticated):
            return False
        path = request.path_info
        # QR-Bestätigung meldet eine andere Sitzung an und braucht daher selbst
        # einen vollständig angemeldeten Account.
        if "/bestaetigen/" not in path and (
            path.startswith(settings.STATIC_URL) or path.startswith(self.ALLOWED_PREFIXES)
        ):
            return False
        from .terminal import is_service_user

        if is_service_user(user):
            return False
        return not user_has_confirmed_mfa(user)


__all__ = [
    "client_ip_from_request",
    "axes_client_ip",
    "MfaEnforcementMiddleware",
    "SecurityHeadersMiddleware",
    "CorrelationIdMiddleware",
    "ClientIPMiddleware",
    "csp_connect_src",
]
