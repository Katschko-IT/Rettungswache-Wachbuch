"""Papier-Rückfallebene: Druckansichten für den Ausfall des Wachbuchs.

Nur lesen, nur die eigene Wache, nur Rollen mit fachlichem Zugriff. Auditoren
und das Dienstkonto „Wachenterminal“ haben keinen Zugang; die Pfade liegen
außerhalb von ``core.terminal.OPEN_MODE_PATHS``. Gedruckt wird mit dem
Browser (``@media print`` in ``core/static/core/paper.css``), keine PDF-Bibliothek.
"""
from __future__ import annotations

from datetime import timedelta
from functools import wraps

from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from . import paper
from .access import CONTENT_ROLES, membership_required, station_module_required


def paper_view(view_func):
    """Gemeinsame Regeln aller Druckansichten."""

    @require_GET
    @never_cache
    @membership_required(CONTENT_ROLES)
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        from .terminal import is_service_user

        # Doppelt gesichert: Die Middleware sperrt /papier/ im Alltagsmodus schon.
        if is_service_user(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapped


def _render(request, template, title, context):
    context.setdefault("generated_at", timezone.localtime())
    context["paper_title"] = title
    return render(request, template, context)


@paper_view
def paper_hub(request):
    station = request.membership.station
    context = {
        "vehicle_count": paper.active_vehicles(station).count() if station.fleet_enabled else 0,
        "device_count": paper.active_devices(station).count() if station.mpg_enabled else 0,
        "checklist_count": paper.active_checklists(station).count() if station.checklists_enabled else 0,
        "has_deadline_sources": any((
            station.fleet_enabled, station.mpg_enabled, station.orga_enabled, station.warehouse_enabled,
        )),
    }
    return _render(request, "core/paper_hub.html", _("Papier-Rückfall"), context)


@paper_view
def paper_deadlines(request):
    station = request.membership.station
    today = timezone.localdate()
    current = paper.week_start(today)
    monday = paper.selected_week(request.GET.get("woche"), today)
    context = paper.week_deadlines(station, monday)
    context.update({
        "current_week_param": paper.iso_week_param(current),
        "next_week_param": paper.iso_week_param(current + timedelta(days=7)),
        "is_current_week": monday == current,
    })
    return _render(request, "core/paper_deadlines.html", _("Fristen der Woche"), context)


@paper_view
@station_module_required("orga_enabled")
def paper_phonebook(request):
    return _render(request, "core/paper_phonebook.html", _("Telefonbuch"), {
        "book": paper.phonebook(request.membership.station),
        "blank_rows": range(paper.PHONEBOOK_BLANK_ROWS),
    })


@paper_view
@station_module_required("checklists_enabled")
def paper_checklists(request):
    return _render(request, "core/paper_checklists.html", _("Checklisten"), {
        "checklists": list(paper.active_checklists(request.membership.station)),
    })


@paper_view
@station_module_required("fleet_enabled")
def paper_vehicle_handover(request):
    from .fleet_forms import FILL_LEVEL_CHOICES
    from .fleet_models import VehicleHandover

    return _render(request, "core/paper_vehicle_handover.html", _("Fahrzeugübernahme"), {
        "vehicles": list(paper.active_vehicles(request.membership.station)),
        "checkpoints": [str(label) for label in VehicleHandover.CHECKPOINTS.values()],
        "fill_levels": ", ".join(str(label) for _value, label in FILL_LEVEL_CHOICES),
        "rows": range(paper.HANDOVER_ROWS),
    })


@paper_view
@station_module_required("fleet_enabled")
def paper_disinfection(request):
    station = request.membership.station
    return _render(request, "core/paper_disinfection.html", _("Desinfektion"), {
        "vehicles": list(paper.active_vehicles(station)),
        "disinfectants": list(paper.active_disinfectants(station)),
        "rows": range(paper.DISINFECTION_ROWS),
    })


@paper_view
@station_module_required("mpg_enabled")
def paper_device_checks(request):
    from .mpg_forms import DeviceRoutineCheckForm
    from .mpg_models import MedicalDevice

    fields = DeviceRoutineCheckForm.base_fields
    checkpoints = [str(fields[name].label) for name in DeviceRoutineCheckForm.CHECK_POINTS]
    return _render(request, "core/paper_device_checks.html", _("Funktionskontrolle Medizingeräte"), {
        "groups": paper.device_groups(request.membership.station),
        "checkpoints": checkpoints,
        "checkpoint_count": len(checkpoints),
        "locked_statuses": {MedicalDevice.Status.OOB, MedicalDevice.Status.MAINTENANCE},
    })
