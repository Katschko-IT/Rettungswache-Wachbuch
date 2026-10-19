"""Pilot HTTPS configuration for local testing and staged validation.

Derives from config.settings, enforces secure cookies and proxy headers behind a
local TLS-terminating reverse proxy, while keeping HSTS disabled (0) so test
environments do not lock browsers into HTTPS permanently.
"""

from __future__ import annotations

import os

from .settings import *  # noqa: F401, F403

DEBUG = False

# Strict fail-closed parsing without wildcard fallback.
# Wildcards ('*') are strictly excluded to avoid insecure open pilot deployments.
_raw_allowed = os.getenv("ALLOWED_HOSTS", "").strip()
ALLOWED_HOSTS = [
    host.strip()
    for host in _raw_allowed.split(",")
    if host.strip() and host.strip() != "*" and not host.strip().startswith("*.")
]

_raw_csrf = os.getenv("CSRF_TRUSTED_ORIGINS", "").strip()
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in _raw_csrf.split(",")
    if origin.strip() and origin.strip() != "*" and not origin.strip().startswith("*.")
]

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# Konsistent zu den explizit gesetzten Cookie-Flags: der Pilot läuft nur hinter
# dem lokalen TLS-Proxy. Ohne diese Zeile meldet `check --deploy` W103, obwohl
# SESSION_COOKIE_SECURE/CSRF_COOKIE_SECURE bereits True sind.
SECURE_COOKIES = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
# Der Pilot laeuft ausschliesslich hinter dem lokalen TLS-Proxy. Direkte
# HTTP-Zugriffe auf den App-Port werden umgeleitet statt ungesichert bedient.
SECURE_SSL_REDIRECT = True
X_FRAME_OPTIONS = "DENY"
SILENCED_SYSTEM_CHECKS = list(SILENCED_SYSTEM_CHECKS) + ["security.W004"]
