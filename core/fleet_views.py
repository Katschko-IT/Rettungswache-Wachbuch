"""Views für den Fuhrpark, Fahrzeug-Cockpit und RKI-Desinfektionsbuch."""
from __future__ import annotations

import csv
from io import BytesIO
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .access import CONTENT_ROLES, membership_required, station_module_required
from .fleet_forms import DisinfectionProtocolForm, VehicleForm, VehicleHandoverForm
from .fleet_models import DisinfectantMaster, DisinfectionProtocol, Vehicle, VehicleHandover
from .models import Membership, Station
from .wachalltag_models import Defect


def ensure_default_disinfectant(station):
    """Ein neutraler Eintrag, damit Protokolle sofort möglich sind.

    Bewusst ohne Produktnamen: Mittel, Konzentration und Einwirkzeit legt die
    Wache fest (Django-Admin „Desinfektionsmittel“); die Einwirkzeit ist im
    Protokoll anpassbar.
    """
    if not DisinfectantMaster.objects.filter(station=station).exists():
        DisinfectantMaster.objects.create(
            station=station,
            name="Flächendesinfektion (Wache festlegen)",
            manufacturer="",
            spectrum="laut Herstellerangabe",
            default_exposure_minutes=15,
            is_vah_listed=True,
        )


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("fleet_enabled")
@require_GET
def fleet_dashboard(request):
    """Flotten-Cockpit-Matrix mit Status-Übersicht, Füllständen und Fristenampel."""
    station = request.membership.station

    ensure_default_disinfectant(station)

    # Fahrzeuge aus dem älteren Geräte-Modul übernehmen. Nur vorhandene Angaben
    # werden übertragen; ein Kennzeichen wird nicht erfunden.
    from django.utils.text import slugify

    from .wachalltag_models import StationAsset
    for legacy in StationAsset.objects.filter(station=station, kind=StationAsset.Kind.VEHICLE):
        slug = slugify(legacy.asset_id)[:64] or f"fahrzeug-{legacy.pk}"
        if not Vehicle.objects.filter(station=station, slug=slug).exists():
            Vehicle.objects.create(
                station=station,
                slug=slug,
                call_sign=legacy.label,
                license_plate="",
                tactical_status=Vehicle.TacticalStatus.STATUS_1 if legacy.status == StationAsset.Status.READY else Vehicle.TacticalStatus.STATUS_6,
            )

    vehicles_qs = Vehicle.objects.filter(station=station, is_active=True)
    # Automatische Freigabe abgelaufener Desinfektions-Sperren
    for v in vehicles_qs:
        v.check_and_release_disinfection()

    query = request.GET.get("q", "").strip()
    if query:
        vehicles_qs = vehicles_qs.filter(
            Q(call_sign__icontains=query)
            | Q(slug__iexact=query)
            | Q(license_plate__icontains=query)
            | Q(chassis_manufacturer__icontains=query)
            | Q(body_manufacturer__icontains=query)
        )

    vehicle_type = request.GET.get("type", "").strip()
    if vehicle_type:
        vehicles_qs = vehicles_qs.filter(vehicle_type=vehicle_type)

    vehicles_list = list(vehicles_qs)
    filter_mode = request.GET.get("filter", "all").strip()

    status_1_count = 0
    status_2_count = 0
    in_mission_count = 0
    disinfection_count = 0
    workshop_count = 0
    urgent_inspections_count = 0

    for v in vehicles_list:
        st = v.tactical_status
        if st == Vehicle.TacticalStatus.STATUS_1:
            status_1_count += 1
        elif st == Vehicle.TacticalStatus.STATUS_2:
            status_2_count += 1
        elif st in (Vehicle.TacticalStatus.STATUS_3, Vehicle.TacticalStatus.STATUS_4):
            in_mission_count += 1
        elif st == Vehicle.TacticalStatus.DISINFECTION or v.is_disinfection_locked:
            disinfection_count += 1
        elif st in (Vehicle.TacticalStatus.WORKSHOP, Vehicle.TacticalStatus.STATUS_6):
            workshop_count += 1

        if v.urgency["level"] in ("overdue", "critical"):
            urgent_inspections_count += 1

    # Filter anwenden
    if filter_mode == "ready":
        vehicles_list = [v for v in vehicles_list if v.tactical_status in (Vehicle.TacticalStatus.STATUS_1, Vehicle.TacticalStatus.STATUS_2)]
    elif filter_mode == "disinfection":
        vehicles_list = [v for v in vehicles_list if v.tactical_status == Vehicle.TacticalStatus.DISINFECTION or v.is_disinfection_locked]
    elif filter_mode == "workshop":
        vehicles_list = [v for v in vehicles_list if v.tactical_status in (Vehicle.TacticalStatus.WORKSHOP, Vehicle.TacticalStatus.STATUS_6)]
    elif filter_mode == "urgent_inspections":
        vehicles_list = [v for v in vehicles_list if v.urgency["level"] in ("overdue", "critical")]

    open_defects = Defect.objects.filter(
        station=station,
        category=Defect.Category.VEHICLE,
        status__in=[Defect.Status.OPEN, Defect.Status.IN_PROGRESS, Defect.Status.WAITING],
    ).order_by("-priority", "created_at")[:5]

    recent_disinfections = DisinfectionProtocol.objects.filter(station=station).select_related(
        "vehicle", "performed_by", "disinfectant"
    )[:5]

    can_manage = request.membership.role in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN}

    kpis = {
        "total": len(vehicles_list),
        "status_1": status_1_count,
        "status_2": status_2_count,
        "disinfection": disinfection_count,
        "workshop": workshop_count,
        "urgent_inspections": urgent_inspections_count,
    }

    return render(
        request,
        "core/fleet_dashboard.html",
        {
            "vehicles": vehicles_list,
            "filter_mode": filter_mode,
            "query": query,
            "vehicle_type": vehicle_type,
            "types": Vehicle.VehicleType.choices,
            "kpis": kpis,
            "open_defects": open_defects,
            "recent_disinfections": recent_disinfections,
            "can_manage": can_manage,
        },
    )


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("fleet_enabled")
@require_http_methods(["GET", "POST"])
def vehicle_create(request):
    """Neues Einsatzfahrzeug anlegen."""
    station = request.membership.station
    can_manage = request.membership.role in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN}
    if not can_manage:
        messages.error(request, "Nur Wachleiter und Administratoren dürfen Fahrzeuge anlegen.")
        return redirect("fleet_dashboard")

    if request.method == "POST":
        form = VehicleForm(request.POST, station=station)
        if form.is_valid():
            vehicle = form.save(commit=False)
            vehicle.station = station
            vehicle.save()
            messages.success(request, f"Fahrzeug '{vehicle.call_sign}' erfolgreich registriert.")
            return redirect("fleet_vehicle_detail", slug=vehicle.slug)
    else:
        form = VehicleForm(station=station)

    return render(
        request,
        "core/fleet_vehicle_form.html",
        {"form": form, "title": "Neues Fahrzeug anlegen", "action_label": "Fahrzeug speichern"},
    )


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("fleet_enabled")
@require_http_methods(["GET", "POST"])
def vehicle_edit(request, slug: str):
    """Fahrzeugdaten bearbeiten."""
    station = request.membership.station
    vehicle = get_object_or_404(Vehicle, station=station, slug=slug)
    vehicle.check_and_release_disinfection()
    can_manage = request.membership.role in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN}
    if not can_manage:
        messages.error(request, "Keine Berechtigung zum Bearbeiten von Fahrzeugdaten.")
        return redirect("fleet_vehicle_detail", slug=vehicle.slug)

    if request.method == "POST":
        form = VehicleForm(request.POST, instance=vehicle, station=station)
        if form.is_valid():
            form.save()
            messages.success(request, f"Änderungen an '{vehicle.call_sign}' gespeichert.")
            return redirect("fleet_vehicle_detail", slug=vehicle.slug)
    else:
        form = VehicleForm(instance=vehicle, station=station)

    return render(
        request,
        "core/fleet_vehicle_form.html",
        {"form": form, "vehicle": vehicle, "title": f"Fahrzeug bearbeiten: {vehicle.call_sign}", "action_label": "Aktualisieren"},
    )


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("fleet_enabled")
@require_GET
def vehicle_detail(request, slug: str):
    """Mobiles Fahrzeug-Cockpit (Schichtübernahme, Desinfektion, Fristen)."""
    station = request.membership.station
    vehicle = get_object_or_404(Vehicle, station=station, slug=slug)
    vehicle.check_and_release_disinfection()

    handovers = vehicle.handovers.select_related("crew_member").order_by("-performed_at")[:10]
    disinfections = vehicle.disinfections.select_related("performed_by", "disinfectant").order_by("-started_at")[:10]
    defects = Defect.objects.filter(
        station=station,
        category=Defect.Category.VEHICLE,
        asset_ref__icontains=vehicle.license_plate,
    ).order_by("-created_at")[:5]

    can_manage = request.membership.role in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN}

    handover_form = VehicleHandoverForm(auto_id="handover_%s", initial={
        "mileage": vehicle.current_mileage,
        "fuel_percent": vehicle.fuel_level_percent,
        "adblue_percent": vehicle.adblue_level_percent,
        "o2_pressure_bar": vehicle.o2_pressure_bar,
    })
    ensure_default_disinfectant(station)
    disinfection_form = DisinfectionProtocolForm(station=station, auto_id="disinfection_%s")

    vehicle_qr_url = request.build_absolute_uri(reverse("fleet_vehicle_qr", args=[vehicle.slug]))

    return render(
        request,
        "core/fleet_vehicle_detail.html",
        {
            "vehicle": vehicle,
            "handovers": handovers,
            "disinfections": disinfections,
            "defects": defects,
            "can_manage": can_manage,
            "handover_form": handover_form,
            "disinfection_form": disinfection_form,
            "vehicle_qr_url": vehicle_qr_url,
        },
    )


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("fleet_enabled")
@require_POST
def vehicle_status_change(request, slug: str):
    """BOS-Taktischen Status ändern (mit Desinfektions-Sperrschutz!)."""
    station = request.membership.station
    vehicle = get_object_or_404(Vehicle, station=station, slug=slug)
    vehicle.check_and_release_disinfection()

    new_status = request.POST.get("status", "").strip()
    if new_status not in Vehicle.TacticalStatus.values:
        messages.error(request, "Ungültiger Statuscode.")
        return redirect("fleet_vehicle_detail", slug=vehicle.slug)

    # Desinfektions-Sperre prüfen: Rückmeldung auf Status 1 oder 2 während Einwirkzeit verboten!
    if vehicle.is_disinfection_locked and new_status in (Vehicle.TacticalStatus.STATUS_1, Vehicle.TacticalStatus.STATUS_2):
        mins = max(1, int(vehicle.disinfection_remaining_seconds / 60))
        messages.error(
            request,
            f"SPERRPFLICHT: Fahrzeug befindet sich noch in der Desinfektions-Einwirkzeit! Freigabe erst in {mins} Minute(n) möglich.",
        )
        return redirect("fleet_vehicle_detail", slug=vehicle.slug)

    vehicle.tactical_status = new_status
    if new_status in (Vehicle.TacticalStatus.STATUS_1, Vehicle.TacticalStatus.STATUS_2):
        vehicle.status_note = ""
    vehicle.save(update_fields=["tactical_status", "status_note", "updated_at"])

    messages.success(request, f"Status für {vehicle.call_sign} auf '{vehicle.get_tactical_status_display()}' gesetzt.")
    return redirect("fleet_vehicle_detail", slug=vehicle.slug)


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("fleet_enabled")
@require_POST
def vehicle_disinfection_create(request, slug: str):
    """Desinfektionsprotokoll erfassen und Sperrtimer starten."""
    station = request.membership.station
    vehicle = get_object_or_404(Vehicle, station=station, slug=slug)
    vehicle.check_and_release_disinfection()

    form = DisinfectionProtocolForm(request.POST, station=station)
    if form.is_valid():
        protocol = form.save(commit=False)
        protocol.station = station
        protocol.vehicle = vehicle
        protocol.performed_by = request.user
        protocol.save()

        messages.warning(
            request,
            f"Desinfektion erfasst: Fahrzeug {vehicle.call_sign} ist für {protocol.exposure_minutes} Minuten gesperrt (Einwirkzeit bis {timezone.localtime(vehicle.disinfection_locked_until).strftime('%H:%M')} Uhr).",
        )
    else:
        messages.error(request, "Fehlerhafte Angaben beim Desinfektionsprotokoll.")

    return redirect("fleet_vehicle_detail", slug=vehicle.slug)


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("fleet_enabled")
@require_POST
def vehicle_handover_create(request, slug: str):
    """3-Minuten Express-Schichtübernahme erfassen."""
    station = request.membership.station
    vehicle = get_object_or_404(Vehicle, station=station, slug=slug)
    vehicle.check_and_release_disinfection()

    form = VehicleHandoverForm(request.POST)
    if form.is_valid():
        handover = form.save(commit=False)
        handover.station = station
        handover.vehicle = vehicle
        handover.crew_member = request.user
        handover.save()

        # Automatische Warnung bei kritischem Sauerstoff- oder Kraftstoffstand
        warnings = []
        if handover.o2_pressure_bar < 100:
            warnings.append(f"Sauerstoffvorrat niedrig ({handover.o2_pressure_bar} bar)!")
        if handover.fuel_percent < 30:
            warnings.append(f"Kraftstoffstand niedrig ({handover.fuel_percent} %)!")

        if warnings:
            messages.warning(request, "Schichtübernahme gespeichert mit Warnhinweis: " + " ".join(warnings))
        else:
            messages.success(request, f"Schichtübernahme für {vehicle.call_sign} erfolgreich bestätigt (Einsatzklar).")
    else:
        messages.error(request, "Ungültige Angaben bei der Schichtübernahme.")

    return redirect("fleet_vehicle_detail", slug=vehicle.slug)


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("fleet_enabled")
@require_POST
def vehicle_defect_report(request, slug: str):
    """Fahrzeugmangel melden und Fahrzeug auf Werkstatt setzen."""
    station = request.membership.station
    vehicle = get_object_or_404(Vehicle, station=station, slug=slug)
    vehicle.check_and_release_disinfection()

    title = request.POST.get("title", f"Mangel an {vehicle.call_sign}").strip()
    description = request.POST.get("description", "").strip()
    priority = request.POST.get("priority", Defect.Priority.IMPORTANT)

    defect = Defect.objects.create(
        station=station,
        title=title[:160],
        description=f"Fahrzeug: {vehicle.call_sign} ({vehicle.license_plate})\nkm-Stand: {vehicle.current_mileage}\n\n{description}".strip(),
        asset_ref=f"{vehicle.call_sign} ({vehicle.license_plate})",
        priority=priority,
        status=Defect.Status.OPEN,
        category=Defect.Category.VEHICLE,
        created_by=request.user,
    )

    if priority == Defect.Priority.URGENT:
        vehicle.tactical_status = Vehicle.TacticalStatus.WORKSHOP
        vehicle.status_note = f"Dringender Werkstattmangel #{defect.id}: {title}"
        vehicle.save(update_fields=["tactical_status", "status_note", "updated_at"])
        messages.warning(request, f"Dringender Mangel erfasst! Fahrzeug wurde sofort auf 'Werkstatt' gesetzt.")
    else:
        messages.success(request, f"Mangel #{defect.id} erfasst.")

    return redirect("fleet_vehicle_detail", slug=vehicle.slug)


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("fleet_enabled")
@require_GET
def vehicle_qr(request, slug: str):
    """Wetterfester QR-Code für Fahrzeugtür / Sonnenblende als PNG."""
    import qrcode

    station = request.membership.station
    vehicle = get_object_or_404(Vehicle, station=station, slug=slug)
    vehicle.check_and_release_disinfection()

    target_url = request.build_absolute_uri(reverse("fleet_vehicle_detail", args=[vehicle.slug]))
    image = qrcode.make(target_url)

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    response = HttpResponse(buffer.getvalue(), content_type="image/png")
    response["Cache-Control"] = "public, max-age=86400"
    return response


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("fleet_enabled")
@require_GET
def export_fleet_csv(request):
    """Export der Flotte mit Fristen und Füllständen als CSV."""
    station = request.membership.station
    vehicles = Vehicle.objects.filter(station=station).order_by("call_sign")

    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = f'attachment; filename="Fuhrpark_{station.slug}_{timezone.localdate().isoformat()}.csv"'

    writer = csv.writer(response, delimiter=";")
    writer.writerow([
        "Funkrufname (OPTA)",
        "Kennzeichen",
        "Typ",
        "Fahrgestell",
        "Kofferaufbau",
        "Status",
        "Kilometerstand",
        "Tank (%)",
        "AdBlue (%)",
        "O2 Druck (bar)",
        "Nächste HU (§ 29)",
        "Nächste UVV (DGUV 70)",
        "Tragentisch 10g",
        "Letzte Desinfektion",
    ])

    for v in vehicles:
        writer.writerow([
            v.call_sign,
            v.license_plate,
            v.get_vehicle_type_display(),
            v.chassis_manufacturer,
            v.body_manufacturer,
            v.get_tactical_status_display(),
            v.current_mileage,
            v.fuel_level_percent,
            v.adblue_level_percent,
            v.o2_pressure_bar,
            v.next_hu_date.isoformat() if v.next_hu_date else "",
            v.next_uvv_date.isoformat() if v.next_uvv_date else "",
            v.next_stretcher_service_date.isoformat() if v.next_stretcher_service_date else "",
            timezone.localtime(v.last_disinfection).strftime("%d.%m.%Y %H:%M") if v.last_disinfection else "",
        ])

    return response
