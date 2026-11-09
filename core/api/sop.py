"""Dienstanweisungen mit Lesepflicht in der App.

- ``GET  /api/v1/dienstanweisungen/``                  eigene Lesepflichten (``?offen=1``: nur offene)
- ``POST /api/v1/dienstanweisungen/<id>/quittieren/``   aktuelle Version als gelesen bestätigen

Gelistet werden nur Dienstanweisungen „In Kraft“ mit Pflichtbestätigung und
Textstand, deren Zielgruppe (Rolle und Funktion) die Person umfasst. Die
Antwort nennt nur den eigenen Stand, nie andere Personen oder die Quote.
Bestätigen folgt denselben Regeln wie im Web (``acknowledgement_refusal``):
nur mit dem eigenen Konto einer Inhaltsrolle, nie als Wachenterminal; auch
außerhalb der Zielgruppe freiwillig möglich, zählt dann aber nicht zur Quote.
Gespeichert werden Person, Version und Zeitpunkt, keine IP-Adresse und kein
Browser. Beide Endpunkte brauchen den Scope ``read:me`` (persönliche Aktion
wie ``/benachrichtigungen/<id>/gelesen/``).
"""
from __future__ import annotations

from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from ..errors import ERROR_CODE_CONFLICT, ERROR_CODE_FORBIDDEN, ERROR_CODE_NOT_FOUND, ERROR_CODE_VALIDATION
from . import views as base
from .wachalltag import _body


def _sop_json(sop, user, receipt, today, is_target: bool):
    revision = sop.latest_revision
    acknowledged_at = receipt.acknowledged_at.isoformat() if receipt else None
    return {
        "id": sop.pk,
        "doc_number": sop.doc_number,
        "title": sop.title,
        "revision": {"id": revision.pk, "version": revision.version_label} if revision else None,
        "ack_due_date": sop.ack_due_date.isoformat() if sop.ack_due_date else None,
        "overdue": bool(sop.ack_due_date and sop.ack_due_date < today and receipt is None),
        "acknowledged": receipt is not None,
        "acknowledged_at": acknowledged_at,
        "in_target_group": is_target,
        "url": reverse("sop_detail", args=[sop.slug]),
    }


def _revision_id(value) -> int | None:
    """Kennung der gelesenen Version: nur eine ganze Zahl oder Ziffern als Text.

    ``1e999`` und ``Infinity`` liefert ``json.loads`` als ``float('inf')``;
    Gleitkommazahlen und Wahrheitswerte gelten deshalb nie als Kennung.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.isascii() and text.isdigit() and len(text) <= 18:
            return int(text)
    return None


def _refuse(request):
    if not base._scope_allowed(request.api_token, "read:me"):
        return base._json_error(request, "Scope read:me fehlt.", status=403)
    from ..orga_models import in_reading_audience

    if not in_reading_audience(request.membership):
        return base._json_error(request, "Lesebestätigungen gibt es nur mit dem eigenen Konto.", status=403,
                                code=ERROR_CODE_FORBIDDEN)
    return None


@csrf_exempt
@require_GET
@base.api_token_required
def sop_list(request):
    refused = _refuse(request)
    if refused:
        return refused
    from ..orga_models import SOPDocument, SOPReceipt

    station = request.membership.station
    if not station.orga_enabled:
        return base.JsonResponse({"ok": True, "count": 0, "results": []})
    only_open = str(request.GET.get("offen") or "").lower() in {"1", "true", "ja"}
    today = timezone.localdate()
    sops = [
        sop for sop in SOPDocument.objects.filter(
            station=station, status=SOPDocument.Status.ACTIVE, requires_acknowledgment=True,
        ).prefetch_related("revisions").order_by("ack_due_date", "doc_number")
        if sop.latest_revision is not None and sop.matches_target(request.membership)
    ]
    receipts = {
        (receipt.sop_id, receipt.revision_id): receipt
        for receipt in SOPReceipt.objects.filter(user=request.user, sop__in=sops)
    }
    results = []
    for sop in sops:
        receipt = receipts.get((sop.pk, sop.latest_revision.pk))
        if only_open and receipt is not None:
            continue
        results.append(_sop_json(sop, request.user, receipt, today, True))
    return base.JsonResponse({"ok": True, "count": len(results), "results": results})


@csrf_exempt
@require_POST
@base.api_token_required
def sop_ack(request, pk):
    refused = _refuse(request)
    if refused:
        return refused
    from ..orga_models import SOPDocument, acknowledgement_refusal, record_acknowledgement

    station = request.membership.station
    sop = SOPDocument.objects.filter(pk=pk, station=station).first() if station.orga_enabled else None
    if sop is None:
        return base._json_error(request, "Dienstanweisung nicht gefunden.", status=404, code=ERROR_CODE_NOT_FOUND)
    refusal = acknowledgement_refusal(sop, request.membership)
    if refusal:
        code, text = refusal
        if code == "forbidden":
            return base._json_error(request, text, status=403, code=ERROR_CODE_FORBIDDEN)
        return base._json_error(request, text, status=409, code=ERROR_CODE_CONFLICT)
    body = _body(request) or {}
    expected = body.get("revision") if isinstance(body, dict) else None
    latest = sop.latest_revision
    if expected not in (None, ""):
        expected = _revision_id(expected)
        if expected is None:
            return base._json_error(request, "revision muss eine Zahl sein.", status=400, code=ERROR_CODE_VALIDATION)
        if expected != latest.pk:
            # Inzwischen gibt es eine neue Version: erst lesen, dann bestätigen.
            return base._json_error(request, "Es gibt eine neuere Version dieser Dienstanweisung.", status=409,
                                    code=ERROR_CODE_CONFLICT)
    receipt, created = record_acknowledgement(sop, request.user)
    data = _sop_json(sop, request.user, receipt, timezone.localdate(), sop.is_target_member(request.membership))
    return base.JsonResponse({"ok": True, "created": created, **data}, status=201 if created else 200)
