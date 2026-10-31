"""Außer Betrieb nehmen und wieder in Betrieb nehmen (Fahrzeug, Medizingerät).

Statt zu löschen: Die Nachweise bleiben, das Objekt verschwindet aus den
Übersichten und nimmt keine neuen Einträge an. Die Regeln stehen in
``core/evidence.py``; diese Ansichten rufen nur die Dienste dort auf.
"""
from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from .access import CONTENT_ROLES, membership_required, station_module_required
from .evidence import RETIRE_ROLES, reactivate_device, reactivate_vehicle, retire_device, retire_vehicle
from .fleet_models import Vehicle
from .mpg_models import MedicalDevice


def _may_retire(request) -> bool:
    return request.membership.role in RETIRE_ROLES


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("fleet_enabled")
@require_POST
def fleet_vehicle_retire(request, slug: str):
    vehicle = get_object_or_404(Vehicle, station=request.membership.station, slug=slug)
    if not _may_retire(request):
        messages.error(request, _("Fahrzeuge nehmen Schichtleitung und Admin außer Betrieb."))
    elif retire_vehicle(vehicle, actor=request.user):
        messages.success(request, _("%(vehicle)s ist außer Betrieb genommen. Übernahmen und Desinfektionen bleiben als Nachweis erhalten.") % {
            "vehicle": vehicle.call_sign,
        })
    else:
        messages.info(request, _("Dieses Fahrzeug ist bereits außer Betrieb genommen."))
    return redirect("fleet_vehicle_detail", slug=vehicle.slug)


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("fleet_enabled")
@require_POST
def fleet_vehicle_reactivate(request, slug: str):
    vehicle = get_object_or_404(Vehicle, station=request.membership.station, slug=slug)
    if not _may_retire(request):
        messages.error(request, _("Fahrzeuge nehmen Schichtleitung und Admin wieder in Betrieb."))
    elif reactivate_vehicle(vehicle, actor=request.user):
        messages.success(request, _("%(vehicle)s ist wieder in Betrieb und steht auf „Außer Dienst“, bis die Besatzung es einsatzbereit meldet.") % {
            "vehicle": vehicle.call_sign,
        })
    else:
        messages.info(request, _("Dieses Fahrzeug ist in Betrieb."))
    return redirect("fleet_vehicle_detail", slug=vehicle.slug)


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("fleet_enabled")
@require_GET
def fleet_retired_list(request):
    vehicles = Vehicle.objects.filter(station=request.membership.station, is_active=False).order_by("call_sign")
    rows = [
        {
            "name": vehicle.call_sign,
            "sub": " · ".join(part for part in (vehicle.license_plate, vehicle.get_vehicle_type_display()) if part),
            "since": None,
            "url": reverse("fleet_vehicle_detail", args=[vehicle.slug]),
        }
        for vehicle in vehicles
    ]
    return render(request, "core/retired_list.html", {
        "title": _("Außer Betrieb genommene Fahrzeuge"),
        "lead": _("Diese Fahrzeuge erscheinen nicht mehr in Übersicht, Display und Sperrbildschirm. Übernahmen und Desinfektionen bleiben als Nachweis erhalten."),
        "empty": _("Keine Fahrzeuge außer Betrieb genommen."),
        "back_url": reverse("fleet_dashboard"),
        "back_label": _("Zurück zur Fuhrpark-Übersicht"),
        "rows": rows,
    })


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("mpg_enabled")
@require_POST
def mpg_device_retire(request, slug: str):
    device = get_object_or_404(MedicalDevice, station=request.membership.station, slug=slug)
    if not _may_retire(request):
        messages.error(request, _("Medizingeräte nehmen Schichtleitung und Admin außer Betrieb."))
    elif retire_device(device, actor=request.user):
        messages.success(request, _("„%(name)s“ ist außer Betrieb genommen. Prüfungen, Kontrollen und Einweisungen bleiben als Nachweis erhalten.") % {
            "name": device.name,
        })
    else:
        messages.info(request, _("Dieses Gerät ist bereits außer Betrieb genommen."))
    return redirect("mpg_device_detail", slug=device.slug)


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("mpg_enabled")
@require_POST
def mpg_device_reactivate(request, slug: str):
    device = get_object_or_404(MedicalDevice, station=request.membership.station, slug=slug)
    if not _may_retire(request):
        messages.error(request, _("Medizingeräte nehmen Schichtleitung und Admin wieder in Betrieb."))
    elif reactivate_device(device, actor=request.user):
        messages.success(request, _("„%(name)s“ ist wieder in Betrieb und bleibt gesperrt, bis die Schichtleitung es nach einer Kontrolle freigibt.") % {
            "name": device.name,
        })
    else:
        messages.info(request, _("Dieses Gerät ist in Betrieb."))
    return redirect("mpg_device_detail", slug=device.slug)


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("mpg_enabled")
@require_GET
def mpg_retired_list(request):
    devices = MedicalDevice.objects.filter(
        station=request.membership.station, current_status=MedicalDevice.Status.DECOMMISSIONED,
    ).order_by("category", "name")
    rows = [
        {
            "name": device.name,
            "sub": " · ".join(part for part in (device.location, device.inventory_number or device.serial_number) if part),
            # Altbestände (vor 0.27 über das Bearbeiten-Formular) haben kein Datum.
            "since": device.decommissioned_at,
            "url": reverse("mpg_device_detail", args=[device.slug]),
        }
        for device in devices
    ]
    return render(request, "core/retired_list.html", {
        "title": _("Außer Betrieb genommene Medizingeräte"),
        "lead": _("Diese Geräte erscheinen nicht mehr in Übersicht, Gerätepass und Display. Prüfungen, Kontrollen und Einweisungen bleiben als Nachweis erhalten."),
        "empty": _("Keine Medizingeräte außer Betrieb genommen."),
        "back_url": reverse("mpg_dashboard"),
        "back_label": _("Zurück zur MPG-Übersicht"),
        "rows": rows,
    })
