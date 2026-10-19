"""Konsistente Fehlerbehandlung fuer HTML- und JSON-Antworten.

Definiert kanonische JSON-Fehlerstruktur, zentrale Fehler-Codes und Helper
fuer API-Views und HTML-Handler-Views (400/403/404/429/500).
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Mapping, Optional

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.utils.translation import gettext_lazy as _

CORRELATION_HEADER = "HTTP_X_CORRELATION_ID"
RESPONSE_CORRELATION_HEADER = "X-Correlation-ID"

CORRELATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{1,128}$")

# One-time activation tokens must never reach any log sink. The trailing slash
# is optional: a request without it is redirected later, but may still be
# logged by error handling or by a different middleware order.
_ACTIVATION_PATH = re.compile(
    r"(/aktivieren/)(?!\[redacted\])[^/\s?#\"'<>,\;)\]}]+([,;)\]}]?)"
)


def redact_request_path(path: str) -> str:
    """Remove one-time activation tokens from a request path.

    Trailing punctuation is preserved so surrounding log text stays readable.
    """
    return _ACTIVATION_PATH.sub(
        lambda match: f"{match.group(1)}[redacted]{match.group(2)}", path or ""
    )


REQUEST_ATTR_CORRELATION_ID = "correlation_id"

logger = logging.getLogger("wachbuch.errors")

ERROR_CODE_VALIDATION = "validation_error"
ERROR_CODE_AUTH_REQUIRED = "auth_required"
ERROR_CODE_FORBIDDEN = "forbidden"
ERROR_CODE_NOT_FOUND = "not_found"
ERROR_CODE_RATE_LIMIT = "rate_limit"
ERROR_CODE_SERVER_ERROR = "server_error"
ERROR_CODE_MFA_REQUIRED = "mfa_required"
ERROR_CODE_MFA_SETUP_REQUIRED = "mfa_setup_required"

ERROR_CODES: dict[str, dict[str, Any]] = {
    ERROR_CODE_VALIDATION: {"status": 400, "label": _("Ungültige Anfrage.")},
    ERROR_CODE_AUTH_REQUIRED: {"status": 401, "label": _("Anmeldung erforderlich.")},
    ERROR_CODE_FORBIDDEN: {"status": 403, "label": _("Zugriff verweigert.")},
    ERROR_CODE_NOT_FOUND: {"status": 404, "label": _("Nicht gefunden.")},
    ERROR_CODE_RATE_LIMIT: {"status": 429, "label": _("Zu viele Anfragen.")},
    ERROR_CODE_SERVER_ERROR: {"status": 500, "label": _("Serverfehler.")},
    ERROR_CODE_MFA_REQUIRED: {"status": 403, "label": _("Zwei-Faktor-Anmeldung erforderlich.")},
    ERROR_CODE_MFA_SETUP_REQUIRED: {"status": 403, "label": _("Zwei-Faktor-Anmeldung muss zuerst eingerichtet werden.")},
}


def is_api_request(request):
    if request is None:
        return False
    path = getattr(request, "path", "") or ""
    if path.startswith("/api/"):
        return True
    accept = (request.META.get("HTTP_ACCEPT") or "").lower()
    return "application/json" in accept and "text/html" not in accept


def correlation_id_for_request(request):
    if request is not None:
        existing = getattr(request, REQUEST_ATTR_CORRELATION_ID, None)
        if isinstance(existing, str) and existing:
            return existing
        raw = request.META.get(CORRELATION_HEADER) or ""
        if raw and CORRELATION_ID_PATTERN.fullmatch(raw):
            setattr(request, REQUEST_ATTR_CORRELATION_ID, raw)
            return raw
    return uuid.uuid4().hex


def status_for_code(code: str) -> int:
    entry = ERROR_CODES.get(code)
    return int(entry["status"]) if entry else 500


def label_for_code(code: str) -> str:
    entry = ERROR_CODES.get(code)
    return str(entry["label"]) if entry else str(ERROR_CODES[ERROR_CODE_SERVER_ERROR]["label"])


def build_error_payload(
    code: str,
    *,
    message: Optional[str] = None,
    correlation_id: Optional[str] = None,
    extra: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "error": {
            "code": code if code in ERROR_CODES else ERROR_CODE_SERVER_ERROR,
            "message": (message or label_for_code(code)),
            "correlation_id": correlation_id or "",
        },
    }
    if extra:
        for key, value in extra.items():
            if key == "error":
                continue
            payload[key] = value
    return payload


def json_error(
    request,
    code: str,
    *,
    message: Optional[str] = None,
    status: Optional[int] = None,
    extra: Optional[Mapping[str, Any]] = None,
    log: bool = False,
) -> JsonResponse:
    correlation_id = correlation_id_for_request(request)
    http_status = int(status) if status is not None else status_for_code(code)
    payload = build_error_payload(
        code,
        message=message,
        correlation_id=correlation_id,
        extra=extra,
    )
    if log:
        path = (getattr(request, "path", "") if request is not None else "") or ""
        method = (getattr(request, "method", "") if request is not None else "") or ""
        logger.warning(
            "api_error code=%s status=%s method=%s path=%s correlation_id=%s",
            payload["error"]["code"],
            http_status,
            method,
            path,
            correlation_id,
            extra={"correlation_id": correlation_id},
        )
    response = JsonResponse(payload, status=http_status)
    response[RESPONSE_CORRELATION_HEADER] = correlation_id
    return response


def log_exception(request, *, exc=None, message: str = "unhandled_exception") -> str:
    correlation_id = correlation_id_for_request(request)
    path = redact_request_path(
        (getattr(request, "path", "") if request is not None else "") or ""
    )
    method = (getattr(request, "method", "") if request is not None else "") or ""
    logger.error(
        "unhandled_exception message=%s method=%s path=%s correlation_id=%s",
        message,
        method,
        path,
        correlation_id,
        exc_info=exc is not None,
        extra={"correlation_id": correlation_id},
    )
    return correlation_id


__all__ = [
    "CORRELATION_HEADER",
    "RESPONSE_CORRELATION_HEADER",
    "REQUEST_ATTR_CORRELATION_ID",
    "CORRELATION_ID_PATTERN",
    "ERROR_CODE_VALIDATION",
    "ERROR_CODE_AUTH_REQUIRED",
    "ERROR_CODE_FORBIDDEN",
    "ERROR_CODE_NOT_FOUND",
    "ERROR_CODE_RATE_LIMIT",
    "ERROR_CODE_SERVER_ERROR",
    "ERROR_CODE_MFA_REQUIRED",
    "ERROR_CODE_MFA_SETUP_REQUIRED",
    "ERROR_CODES",
    "is_api_request",
    "correlation_id_for_request",
    "status_for_code",
    "label_for_code",
    "build_error_payload",
    "json_error",
    "log_exception",
    "redact_request_path",
]


if settings.configured:
    _ = ERROR_CODES
