"""Ansichten für Checklisten (0.28)."""
from __future__ import annotations

from django.contrib import messages
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .access import CONTENT_ROLES, membership_required, station_module_required
from .checklists_forms import validate_checklist_submission
from .models import Checklist, ChecklistCompletion
from .services import audit
from .terminal import is_open_mode
from .wachalltag_models import Defect, DefectEvent


def _prefill_value(value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _prefill(results: dict) -> dict:
    """Vorbelegung je Prüfpunkt (nur Text), aus einem Zwischenstand oder einer abgelehnten Eingabe."""
    return {
        key: {
            "status": str(entry.get("status") or ""),
            "value": _prefill_value(entry.get("value")),
            "reason": str(entry.get("reason") or ""),
        }
        for key, entry in (results or {}).items()
        if isinstance(entry, dict)
    }


@membership_required(CONTENT_ROLES)
@station_module_required("checklists_enabled")
def checklists(request):
    """Übersicht der aktiven Checklisten mit letztem Abschluss und Zwischenstand."""
    return _render_checklists(request)


def _render_checklists(request, posted=None):
    """Seite der Checklisten; ``posted`` belegt die abgelehnte Eingabe wieder vor.

    Ohne abgelehnte Eingabe wird der letzte Zwischenstand eingesetzt, damit „Zwischenstand
    speichern“ die Antworten beim nächsten Öffnen tatsächlich wiederherstellt.
    """
    station = request.membership.station
    checklists_qs = list(
        Checklist.objects.filter(station=station, is_active=True).prefetch_related("items")
    )
    latest = {}
    for completion in (
        ChecklistCompletion.objects.filter(station=station, is_draft=False)
        .select_related("completed_by", "checklist")
        .order_by("checklist_id", "-created_at")
    ):
        latest.setdefault(completion.checklist_id, completion)

    drafts = {}
    for draft in (
        ChecklistCompletion.objects.filter(station=station, is_draft=True)
        .select_related("completed_by", "checklist")
        .order_by("checklist_id", "-created_at")
    ):
        drafts.setdefault(draft.checklist_id, draft)

    for cl in checklists_qs:
        cl.latest_completion = latest.get(cl.id)
        draft = drafts.get(cl.id)
        # Ein Zwischenstand gilt nur, solange kein neuerer Abschluss existiert.
        if draft and cl.latest_completion and draft.created_at <= cl.latest_completion.created_at:
            draft = None
        cl.active_draft = draft
        if posted and posted["checklist_id"] == cl.id:
            results, note = posted["results"], posted["note"]
        elif draft:
            results, note = _prefill(draft.item_results), draft.note
        else:
            results, note = {}, None
        cl.prefill_note = note
        for item in cl.items.all():
            item.prefill = results.get(str(item.id), {})

    return render(
        request,
        "core/checklists.html",
        {
            "checklists": checklists_qs,
            "terminal_open_mode": is_open_mode(request),
        },
    )


@membership_required(CONTENT_ROLES)
@station_module_required("checklists_enabled")
@require_POST
def checklist_complete(request, pk):
    """Checkliste abschließen oder Zwischenstand speichern."""
    station = request.membership.station
    checklist = get_object_or_404(Checklist, pk=pk, station=station, is_active=True)

    # Läufe mit Nachweischarakter dürfen am gemeinsamen Terminal nicht abgeschlossen werden
    if checklist.requires_personal_login and is_open_mode(request):
        messages.error(
            request,
            _(
                "Checklisten mit Nachweischarakter sind am Wachenterminal gesperrt. "
                "Bitte persönlich anmelden."
            ),
        )
        return HttpResponseForbidden(
            _(
                "Checklisten mit Nachweischarakter sind am Wachenterminal gesperrt. "
                "Bitte persönlich anmelden."
            )
        )

    action = request.POST.get("action", "")
    is_draft = action == "draft" or request.POST.get("is_draft") in ("true", "1", "draft", True)

    items = list(checklist.items.all())
    has_item_submission = any(
        f"result_{item.id}" in request.POST
        or f"value_{item.id}" in request.POST
        or f"reason_{item.id}" in request.POST
        for item in items
    ) or ("item_results" in request.POST and isinstance(request.POST.get("item_results"), dict))

    if has_item_submission:
        item_results, errors = validate_checklist_submission(
            checklist, request.POST, is_draft=is_draft
        )
        if errors and not is_draft:
            for err in errors:
                messages.error(request, err)
            # Nicht umleiten: Sonst wären alle bereits gegebenen Antworten weg.
            return _render_checklists(
                request,
                posted={
                    "checklist_id": checklist.id,
                    "note": (request.POST.get("note") or "")[:300],
                    "results": {
                        str(item.id): {
                            "status": request.POST.get(f"result_{item.id}", ""),
                            "value": request.POST.get(f"value_{item.id}", ""),
                            "reason": request.POST.get(f"reason_{item.id}", ""),
                        }
                        for item in items
                    },
                },
            )
    else:
        item_results = {}

    with transaction.atomic():
        # Append-only: Zwischenstand und Abschluss sind jeweils ein neuer Datensatz.
        completion = ChecklistCompletion(
            station=station,
            checklist=checklist,
            completed_by=request.user,
            note=(request.POST.get("note") or "")[:300],
            is_draft=is_draft,
            item_results=item_results,
        )

        # Bei endgültigem Abschluss Mängel für „nicht in Ordnung“-Punkte automatisch anlegen
        if not is_draft and has_item_submission:
            for item in items:
                res = item_results.get(str(item.id))
                if res and res.get("status") == "not_ok":
                    reason = res.get("reason") or ""
                    val = res.get("value")
                    desc_parts = [
                        f"Prüfpunkt: {item.text}",
                        f"Checkliste: {checklist.title}",
                        f"Feststellung: {reason or 'nicht in Ordnung'}",
                    ]
                    if val is not None:
                        unit = f" {item.measurement_unit}" if item.measurement_unit else ""
                        bounds = (
                            f"[{item.min_value if item.min_value is not None else '—'}.."
                            f"{item.max_value if item.max_value is not None else '—'}]"
                        )
                        desc_parts.append(f"Messwert: {val}{unit} (Grenzen: {bounds})")
                    desc_parts.append(
                        f"Erfasst im Prüflauf von {request.user.first_name or request.user.username}."
                    )

                    defect = Defect.objects.create(
                        station=station,
                        title=f"Mangel aus Checkliste „{checklist.title}“: {item.text}"[:160],
                        description="\n".join(desc_parts),
                        asset_ref=f"Checkliste: {checklist.title}"[:160],
                        priority=Defect.Priority.IMPORTANT,
                        status=Defect.Status.OPEN,
                        category=Defect.Category.TASK,
                        created_by=request.user,
                    )
                    DefectEvent.objects.create(
                        defect=defect,
                        station=station,
                        actor=request.user,
                        kind=DefectEvent.Kind.CREATED,
                        note=defect.title,
                    )
                    audit(
                        request.user,
                        station,
                        "defect.created",
                        defect,
                        {
                            "via": "checklist",
                            "checklist_id": checklist.id,
                            "item_id": item.id,
                        },
                    )
                    res["defect_id"] = defect.id

        completion.item_results = item_results
        completion.save()

        if is_draft:
            audit(
                request.user,
                station,
                "checklist.draft_saved",
                completion,
                {
                    "fields": ["checklist", "note", "item_results"],
                },
            )
            messages.success(request, _("Zwischenstand der Checkliste wurde gespeichert."))
        else:
            defects_created = [
                res["defect_id"] for res in item_results.values() if res.get("defect_id")
            ]
            audit(
                request.user,
                station,
                "checklist.completed",
                completion,
                {
                    "fields": ["checklist", "note", "item_results"],
                    "defects_created": defects_created,
                },
            )
            from .api.wachalltag import advance_checklist_schedule

            advance_checklist_schedule(checklist.pk)
            if defects_created:
                messages.warning(
                    request,
                    _("Checkliste abgeschlossen. %(count)d Mangel automatisch angelegt.")
                    % {"count": len(defects_created)},
                )
            else:
                messages.success(request, _("Checkliste wurde als erledigt vermerkt."))

    return redirect("checklists")
