"""
Bereinigte Erfassung serverseitiger technischer Fehlerereignisse (5xx).

Architektur und Vertrauensgrenzen:
- Klare Trennung von fachlichem Audit (AuditEvent) und technischer Diagnose (ErrorEvent).
- Fehlerereignisse dienen ausschließlich der internen Betriebsstabilität auf Wachenebene.
- Es werden niemals Fehlermeldungen, Tracebacks, Roh-URLs, Query-Strings, Request-Bodies,
  Cookies, Header oder Authentifizierungs-Token gespeichert.
- Keine Abhängigkeit von Docker-, SSH- oder sonstigen Infrastruktur-Rohlogs im laufenden Betrieb.
- Erfassung erfolgt best-effort und darf den primären HTTP-Ablauf nicht blockieren oder verzögern.
"""

import logging
import sys
import uuid

from django.core.exceptions import (
    PermissionDenied,
    SuspiciousOperation,
    ValidationError,
)
from django.core.signals import got_request_exception
from django.db import DatabaseError
from django.template import TemplateDoesNotExist, TemplateSyntaxError

from core.diagnostics_models import CORRELATION_ID_RE, ROUTE_NAME_RE, ErrorEvent
from core.version import APP_VERSION

logger = logging.getLogger(__name__)

UNMATCHED_ROUTE = "unmatched"


def category_for_exception(exc: BaseException | None) -> str:
    """
    Klassifiziert eine Ausnahme ausschließlich anhand ihrer Klasse bzw. ihres Typs.

    Liest niemals str(exc), exc.args oder Attribute der Exception aus, um
    Datenabflüsse vollständig auszuschließen.
    """
    if exc is None:
        return ErrorEvent.Category.SERVER
    if isinstance(exc, DatabaseError):
        return ErrorEvent.Category.DATABASE
    if isinstance(exc, (TemplateDoesNotExist, TemplateSyntaxError)):
        return ErrorEvent.Category.TEMPLATE
    if isinstance(exc, PermissionDenied):
        return ErrorEvent.Category.PERMISSION
    if isinstance(exc, ValidationError):
        return ErrorEvent.Category.VALIDATION
    if isinstance(exc, SuspiciousOperation):
        return ErrorEvent.Category.HTTP
    return ErrorEvent.Category.SERVER


def correlation_id_for_event(request) -> str:
    """
    Ermittelt die Correlation-ID für das Fehlerereignis.

    Übernimmt request.correlation_id nur bei exakter Übereinstimmung mit dem
    erlaubten Muster. Verändert oder kürzt fehlerhafte IDs niemals, sondern
    verwirft sie und generiert eine neue hexadezimale UUIDv4.
    """
    raw_id = getattr(request, "correlation_id", "")
    if isinstance(raw_id, str) and CORRELATION_ID_RE.match(raw_id):
        return raw_id
    return uuid.uuid4().hex


def route_name_for_request(request) -> str:
    """
    Ermittelt den stabilen Django-Routennamen (view_name).

    Verwendet niemals request.path, relative URLs oder variable Pfadparameter.
    """
    resolver_match = getattr(request, "resolver_match", None)
    if resolver_match is None:
        return UNMATCHED_ROUTE
    view_name = getattr(resolver_match, "view_name", None)
    if not view_name or not isinstance(view_name, str):
        return UNMATCHED_ROUTE
    if ROUTE_NAME_RE.match(view_name):
        return view_name
    return "unknown"


def record_server_error(
    request,
    *,
    status: int = 500,
    exc: BaseException | None = None,
) -> ErrorEvent | None:
    """
    Erfasst ein bereinigtes Fehlerereignis für HTTP-Statuscodes zwischen 500 und 599.

    Führt keine zusätzlichen DB-Queries für Berechtigungen oder Stationen durch.
    Ruft nicht full_clean() auf. Fängt alle internen Ausnahmen ab und garantiert,
    dass die Anfrageverarbeitung niemals fehlschlägt.
    """
    if not (500 <= status <= 599):
        return None

    try:
        correlation_id = correlation_id_for_event(request)
        route_name = route_name_for_request(request)
        category = category_for_exception(exc)

        station = None
        membership = getattr(request, "membership", None)
        if membership is not None:
            station = getattr(membership, "station", None)

        event = ErrorEvent.objects.create(
            correlation_id=correlation_id,
            route_name=route_name,
            category=category,
            http_status=status,
            app_version=APP_VERSION,
            station=station,
        )
        if request is not None:
            setattr(request, "_error_event_recorded", True)
        return event
    except Exception:
        logger.warning("error_event_not_recorded")
        return None


def _on_request_exception(sender, request=None, **kwargs):
    """
    Modulweiter Signal-Handler für got_request_exception.

    Ermittelt die Ausnahme synchron über sys.exc_info()[1], da Django diese
    nicht als Signal-Argument übergibt, und erfasst das Fehlerereignis.
    """
    try:
        exc = sys.exc_info()[1]
        record_server_error(request, status=500, exc=exc)
    except Exception:
        logger.warning("error_event_not_recorded")


class ErrorEventMiddleware:
    """
    Middleware zur bereinigten Erfassung serverseitiger 5xx-Fehler.

    Verbindet got_request_exception und fängt zusätzlich direkte 5xx-Responses ab.
    Blockiert die Antwort nicht über die Fehlerbehandlung hinaus und rendert niemals Templates.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        got_request_exception.connect(
            _on_request_exception,
            dispatch_uid="wachbuch_record_error_event",
            weak=False,
        )

    def __call__(self, request):
        response = self.get_response(request)
        status_code = getattr(response, "status_code", 200)
        if status_code >= 500 and not getattr(request, "_error_event_recorded", False):
            record_server_error(request, status=status_code)
        return response
