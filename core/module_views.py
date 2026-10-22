"""Module dashboards for dedicated Hauptreiter (MPG, Lager, Fuhrpark, Organisation)."""
from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET

from .access import CONTENT_ROLES, membership_required, station_module_required
from .models import CalendarEvent, Membership, Station
from .wachalltag_models import Defect, InventoryItem, StationAsset
from .wiki_models import WikiArticle


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("mpg_enabled")
@require_GET
def mpg_dashboard(request):
    """Cockpit für Medizinproduktebuch, STK/MTK-Prüffristen und Gerätestamm."""
    station = request.membership.station
    devices = StationAsset.objects.filter(
        station=station, kind=StationAsset.Kind.DEVICE
    ).order_by("status", "label")

    device_defects = Defect.objects.filter(
        station=station,
        category=Defect.Category.DEVICE,
        status__in=[Defect.Status.OPEN, Defect.Status.IN_PROGRESS, Defect.Status.WAITING],
    ).order_by("-priority", "created_at")

    kpis = {
        "total": devices.count(),
        "ready": devices.filter(status=StationAsset.Status.READY).count(),
        "limited": devices.filter(status=StationAsset.Status.LIMITED).count(),
        "oob": devices.filter(status=StationAsset.Status.OOB).count(),
        "workshop": devices.filter(status=StationAsset.Status.WORKSHOP).count(),
        "open_defects": device_defects.count(),
    }

    return render(
        request,
        "core/mpg_dashboard.html",
        {
            "devices": devices,
            "device_defects": device_defects[:5],
            "kpis": kpis,
            "can_manage": request.membership.role in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN},
        },
    )


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("warehouse_enabled")
@require_GET
def warehouse_dashboard(request):
    """Cockpit für Lager, Materialwirtschaft, Chargen und Verfallsdaten."""
    station = request.membership.station
    items = InventoryItem.objects.filter(station=station).order_by("kind", "label")

    checked_out = items.filter(holder__isnull=False)
    available = items.filter(holder__isnull=True)

    kpis = {
        "total": items.count(),
        "available": available.count(),
        "checked_out": checked_out.count(),
    }

    return render(
        request,
        "core/warehouse_dashboard.html",
        {
            "items": items,
            "checked_out": checked_out,
            "kpis": kpis,
            "can_manage": request.membership.role in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN},
        },
    )


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("fleet_enabled")
@require_GET
def fleet_dashboard(request):
    """Flotten-Cockpit für Fahrzeuge, Status, Prüffristen und Hygiene."""
    station = request.membership.station
    vehicles = StationAsset.objects.filter(
        station=station, kind=StationAsset.Kind.VEHICLE
    ).order_by("status", "label")

    vehicle_defects = Defect.objects.filter(
        station=station,
        category=Defect.Category.VEHICLE,
        status__in=[Defect.Status.OPEN, Defect.Status.IN_PROGRESS, Defect.Status.WAITING],
    ).order_by("-priority", "created_at")

    kpis = {
        "total": vehicles.count(),
        "ready": vehicles.filter(status=StationAsset.Status.READY).count(),
        "limited": vehicles.filter(status=StationAsset.Status.LIMITED).count(),
        "workshop": vehicles.filter(status=StationAsset.Status.WORKSHOP).count(),
        "oob": vehicles.filter(status=StationAsset.Status.OOB).count(),
        "open_defects": vehicle_defects.count(),
    }

    return render(
        request,
        "core/fleet_dashboard.html",
        {
            "vehicles": vehicles,
            "vehicle_defects": vehicle_defects[:5],
            "kpis": kpis,
            "can_manage": request.membership.role in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN},
        },
    )


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("orga_enabled")
@require_GET
def orga_dashboard(request):
    """Zentrale für Organisation, SOP-Dienstanweisungen, Wiki und Termine."""
    station = request.membership.station
    articles = WikiArticle.objects.filter(station=station, is_archived=False).order_by("-updated_at")

    now = timezone.now()
    events = CalendarEvent.objects.filter(
        station=station, ends_at__gte=now
    ).order_by("starts_at")[:6]

    return render(
        request,
        "core/orga_dashboard.html",
        {
            "articles": articles[:8],
            "total_articles": articles.count(),
            "events": events,
            "can_manage": request.membership.role in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN},
        },
    )
