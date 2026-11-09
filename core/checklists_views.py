"""Ansichten für Checklisten (0.28): Lauf mit Ergebnis je Punkt, Zwischenstand, Verlauf und Export.

Prüfen und Speichern übernimmt ``core/checklists_service.py`` (gemeinsam mit
der App). Jede Abfrage bleibt an ``request.membership.station`` gebunden.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, time, timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext
from django.views.decorators.http import require_GET, require_POST

from .access import CONTENT_ROLES, membership_required, station_module_required
from .checklists_service import (
    backfill_errors,
    checklist_items,
    effective_at_expression,
    finalize_run,
    has_result_per_item,
    latest_runs,
    number_text,
    parse_backfill_time,
    per_item_quota,
    prefill_from_post,
    prefill_from_results,
    raw_results_from_post,
    result_rows,
    save_draft,
    summarize,
    validate_results,
)
from .csv_safety import starts_like_formula
from .models import Checklist, ChecklistCompletion, ChecklistDraft, Membership
from .services import audit
from .terminal import is_open_mode, is_service_user
from .wachalltag_models import Defect

LEAD_ROLES = frozenset({Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN})
LAST_RUN_SESSION_KEY = "checklist_last_run"
EXPORT_DEFAULT_DAYS = 30
# Grenzen des Export-Zeitraums: davor gibt es keine Läufe, danach keine (Läufe
# liegen nie in der Zukunft); ein Jahr Spielraum für „bis Jahresende“. Auch
# Datumswerte am Rand des Kalenders (0001-01-01, 9999-12-31) führen so zu
# einer Meldung statt zu einem Fehler 500.
EXPORT_EARLIEST = date(2000, 1, 1)
EXPORT_LATEST_DAYS_AHEAD = 366

TERMINAL_EVIDENCE_MESSAGE = gettext_lazy(
    "Checklisten mit Nachweischarakter sind am Wachenterminal gesperrt. "
    "Bitte persönlich anmelden."
)


def _terminal_mode(request) -> bool:
    """Gemeinsames Wachenterminal: Alltagsmodus oder das Dienstkonto selbst."""
    return is_open_mode(request) or is_service_user(request.user)


def _is_lead(membership) -> bool:
    return membership.role in LEAD_ROLES


def _rows(items, prefill):
    empty = {"status": "", "value": "", "reason": ""}
    return [{"item": item, **prefill.get(str(item.pk), empty)} for item in items]


def _last_run_panel(request, station):
    """Ergebnis des eben abgeschlossenen Laufs dieser Person: Links zu angelegten oder verknüpften Mängeln."""
    run_id = request.session.pop(LAST_RUN_SESSION_KEY, None)
    if not isinstance(run_id, int):
        return None
    run = (
        ChecklistCompletion.objects.filter(pk=run_id, station=station, completed_by=request.user)
        .select_related("checklist")
        .first()
    )
    if run is None:
        return None
    rows = [row for row in result_rows(run.item_results) if row["defect_id"]]
    defects = Defect.objects.filter(station=station).in_bulk([row["defect_id"] for row in rows])
    entries = [
        {"row": row, "defect": defects[row["defect_id"]]}
        for row in rows
        if row["defect_id"] in defects
    ]
    if not entries:
        return None
    return {"run": run, "entries": entries}


def _render_overview(request, *, rejected=None, status=200):
    station = request.membership.station
    terminal = _terminal_mode(request)
    checklists_qs = list(
        Checklist.objects.filter(station=station, is_active=True).prefetch_related("items")
    )
    latest = latest_runs(checklists_qs)
    drafts = {
        draft.checklist_id: draft
        for draft in ChecklistDraft.objects.filter(station=station, checklist__in=checklists_qs).select_related(
            "updated_by"
        )
    }
    for checklist in checklists_qs:
        items = list(checklist.items.all())
        checklist.latest_completion = latest.get(checklist.pk)
        checklist.active_draft = drafts.get(checklist.pk)
        checklist.form_errors = []
        checklist.form_backfill = False
        checklist.form_occurred_at = ""
        if rejected is not None and rejected["checklist_id"] == checklist.pk:
            prefill = rejected["prefill"]
            checklist.form_errors = rejected["errors"]
            checklist.form_note = rejected["note"]
            checklist.form_backfill = rejected["backfill"]
            checklist.form_occurred_at = rejected["occurred_at"]
        elif checklist.active_draft is not None:
            prefill = prefill_from_results(checklist.active_draft.item_results)
            checklist.form_note = checklist.active_draft.note
        else:
            prefill = {}
            checklist.form_note = ""
        checklist.item_rows = _rows(items, prefill)
        checklist.has_quick_action = any(not item.has_measurement for item in items)
        checklist.locked_here = checklist.requires_personal_login and terminal

    is_lead = _is_lead(request.membership)
    now = timezone.localtime()
    return render(
        request,
        "core/checklists.html",
        {
            "checklists": checklists_qs,
            "terminal_open_mode": terminal,
            "last_run": _last_run_panel(request, station),
            "quota": per_item_quota(station) if is_lead else None,
            "show_quota": is_lead,
            "backfill_min": (now - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M"),
            "backfill_max": now.strftime("%Y-%m-%dT%H:%M"),
        },
        status=status,
    )


@membership_required(CONTENT_ROLES)
@station_module_required("checklists_enabled")
def checklists(request):
    """Übersicht der aktiven Checklisten mit letztem Lauf, Zwischenstand und Formular."""
    return _render_overview(request)


@membership_required(CONTENT_ROLES)
@station_module_required("checklists_enabled")
@require_POST
def checklist_complete(request, pk):
    """Checkliste abschließen oder Zwischenstand speichern."""
    station = request.membership.station
    checklist = get_object_or_404(Checklist, pk=pk, station=station, is_active=True)
    terminal = _terminal_mode(request)

    # Läufe mit Nachweischarakter dürfen am gemeinsamen Terminal nicht abgeschlossen werden
    if checklist.requires_personal_login and terminal:
        messages.error(request, TERMINAL_EVIDENCE_MESSAGE)
        return HttpResponseForbidden(str(TERMINAL_EVIDENCE_MESSAGE))

    is_draft = request.POST.get("action") == "draft"
    is_backfill = not is_draft and request.POST.get("is_paper_backfill") in ("on", "1", "true")
    if is_backfill and terminal:
        message = _("Nachträge vom Papierbogen sind am Wachenterminal nicht möglich. Bitte persönlich anmelden.")
        messages.error(request, message)
        return HttpResponseForbidden(message)

    items = checklist_items(checklist)
    note = (request.POST.get("note") or "")[:300]
    item_results, errors = validate_results(items, raw_results_from_post(items, request.POST), final=not is_draft)
    occurred_at = None
    if is_backfill:
        occurred_at, readable = parse_backfill_time(request.POST.get("occurred_at"))
        errors += backfill_errors(occurred_at) if readable else [_("Bitte einen gültigen Ereigniszeitpunkt angeben.")]
    if errors:
        # Nichts geht verloren: dieselbe Seite mit den eingegebenen Werten.
        messages.error(request, _("Die Checkliste wurde nicht gespeichert. Bitte die markierten Angaben prüfen."))
        return _render_overview(
            request,
            rejected={
                "checklist_id": checklist.pk,
                "prefill": prefill_from_post(items, request.POST),
                "errors": errors,
                "note": note,
                "backfill": is_backfill,
                "occurred_at": str(request.POST.get("occurred_at") or "")[:16],
            },
            status=400,
        )

    if is_draft:
        save_draft(
            station=station, checklist=checklist, user=request.user, item_results=item_results, note=note, via="web",
        )
        messages.success(request, _("Zwischenstand der Checkliste wurde gespeichert."))
        return redirect("checklists")

    result = finalize_run(
        station=station, checklist=checklist, user=request.user, item_results=item_results, note=note,
        is_paper_backfill=is_backfill, occurred_at=occurred_at, via="web",
    )
    if result.created_defects:
        messages.warning(request, ngettext(
            "Checkliste abgeschlossen. %(count)d Mangel wurde angelegt.",
            "Checkliste abgeschlossen. %(count)d Mängel wurden angelegt.",
            len(result.created_defects),
        ) % {"count": len(result.created_defects)})
    else:
        messages.success(request, _("Checkliste wurde als erledigt vermerkt."))
    if result.linked_defects:
        messages.info(request, ngettext(
            "%(count)d Prüfpunkt ist bereits als offener Mangel erfasst; es wurde kein weiterer Mangel angelegt.",
            "%(count)d Prüfpunkte sind bereits als offene Mängel erfasst; es wurden keine weiteren Mängel angelegt.",
            len(result.linked_defects),
        ) % {"count": len(result.linked_defects)})
    if result.defects:
        request.session[LAST_RUN_SESSION_KEY] = result.completion.pk
    return redirect("checklists")


# ---- Verlauf, Lauf und Export -------------------------------------------------


def _runs(station, checklist):
    return (
        ChecklistCompletion.objects.filter(station=station, checklist=checklist)
        .select_related("completed_by")
        .annotate(effective=effective_at_expression())
        .order_by("-effective", "-pk")
    )


@membership_required(CONTENT_ROLES)
@station_module_required("checklists_enabled")
@require_GET
def checklist_history(request, pk):
    """Endgültige Läufe einer Checkliste, neueste zuerst (Ereigniszeit bei Nachträgen)."""
    station = request.membership.station
    checklist = get_object_or_404(Checklist, pk=pk, station=station)
    page = Paginator(_runs(station, checklist), 30).get_page(request.GET.get("seite"))
    for run in page.object_list:
        run.summary = summarize(run.item_results)
        run.complete = has_result_per_item(run.item_results)
    today = timezone.localdate()
    return render(request, "core/checklist_history.html", {
        "checklist": checklist,
        "page_obj": page,
        "can_export": _is_lead(request.membership),
        "export_from": (today - timedelta(days=EXPORT_DEFAULT_DAYS)).isoformat(),
        "export_to": today.isoformat(),
        "export_min": EXPORT_EARLIEST.isoformat(),
        "export_max": (today + timedelta(days=EXPORT_LATEST_DAYS_AHEAD)).isoformat(),
    })


@membership_required(CONTENT_ROLES)
@station_module_required("checklists_enabled")
@require_GET
def checklist_run_detail(request, pk):
    """Ein Lauf mit Ergebnis, Messwert und Begründung je Prüfpunkt sowie Links zu den Mängeln."""
    station = request.membership.station
    run = get_object_or_404(
        ChecklistCompletion.objects.select_related("checklist", "completed_by"), pk=pk, station=station,
    )
    rows = result_rows(run.item_results, {item.pk: item for item in run.checklist.items.all()})
    defect_ids = {row["defect_id"] for row in rows if row["defect_id"]}
    defects = Defect.objects.filter(station=station).in_bulk(list(defect_ids))
    for row in rows:
        row["defect"] = defects.get(row["defect_id"])
    return render(request, "core/checklist_run_detail.html", {
        "run": run,
        "checklist": run.checklist,
        "rows": rows,
        "summary": summarize(run.item_results),
        "complete": has_result_per_item(run.item_results),
    })


def _csv_cell(value) -> str:
    text = "" if value is None else str(value)
    # Tabellenprogramme führen Zellen mit = + - @ (oder Tab/CR am Anfang) als Formel aus.
    return "'" + text if starts_like_formula(text) else text


def _decimal_cell(value) -> str:
    return number_text(value).replace(".", ",") if value not in (None, "") else ""


def _person_text(user) -> str:
    return user.get_full_name() or user.username


def _parse_day(raw) -> date | None:
    try:
        return date.fromisoformat(str(raw or "").strip())
    except ValueError:
        return None


@membership_required(CONTENT_ROLES)
@station_module_required("checklists_enabled")
@require_GET
def checklist_runs_export(request, pk):
    """Läufe einer Checkliste als CSV für einen Zeitraum (z. B. Temperaturprotokoll)."""
    station = request.membership.station
    checklist = get_object_or_404(Checklist, pk=pk, station=station)
    if not _is_lead(request.membership):
        messages.error(request, _("Den Export der Checklisten-Läufe erstellen Schichtleitung und Master-Admin."))
        return redirect("checklist_history", pk=checklist.pk)
    today = timezone.localdate()
    start = _parse_day(request.GET.get("von")) if request.GET.get("von") else today - timedelta(days=EXPORT_DEFAULT_DAYS)
    end = _parse_day(request.GET.get("bis")) if request.GET.get("bis") else today
    latest = today + timedelta(days=EXPORT_LATEST_DAYS_AHEAD)
    if start is None or end is None or start > end or start < EXPORT_EARLIEST or end > latest:
        messages.error(request, _("Bitte einen gültigen Zeitraum angeben (von bis bis, als Datum)."))
        return redirect("checklist_history", pk=checklist.pk)

    zone = timezone.get_current_timezone()
    since = timezone.make_aware(datetime.combine(start, time.min), zone)
    until = timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min), zone)
    runs = list(
        _runs(station, checklist).filter(effective__gte=since, effective__lt=until).order_by("effective", "pk")
    )
    items_by_id = {item.pk: item for item in checklist.items.all()}

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="checkliste_{checklist.pk}_{start.isoformat()}_{end.isoformat()}.csv"'
    )
    response.write("﻿")
    writer = csv.writer(response, delimiter=";")
    writer.writerow([
        _("Checkliste"), _("Lauf"), _("Zeitpunkt"), _("Erfasst am"), _("Nachtrag vom Papierbogen"), _("Person"),
        _("Prüfpunkt"), _("Pflichtpunkt"), _("Ergebnis"), _("Messwert"), _("Einheit"), _("Untergrenze"),
        _("Obergrenze"), _("Begründung"), _("Mangel"), _("Notiz"),
    ])
    for run in runs:
        head = [
            _csv_cell(checklist.title),
            run.pk,
            timezone.localtime(run.effective_at).strftime("%Y-%m-%d %H:%M"),
            timezone.localtime(run.created_at).strftime("%Y-%m-%d %H:%M"),
            _("ja") if run.is_paper_backfill else _("nein"),
            _csv_cell(_person_text(run.completed_by)),
        ]
        rows = result_rows(run.item_results, items_by_id) or [None]
        for row in rows:
            if row is None:
                writer.writerow(head + ["", "", "", "", "", "", "", "", "", _csv_cell(run.note)])
                continue
            writer.writerow(head + [
                _csv_cell(row["text"]),
                "" if row["required"] is None else (_("ja") if row["required"] else _("nein")),
                row["status_label"],
                _decimal_cell(row["value"]),
                _csv_cell(row["unit"]),
                _decimal_cell(row["min"]),
                _decimal_cell(row["max"]),
                _csv_cell(row["reason"]),
                row["defect_id"] or "",
                _csv_cell(run.note),
            ])
    audit(request.user, station, "checklist.exported", checklist, {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "runs": len(runs),
    })
    return response
