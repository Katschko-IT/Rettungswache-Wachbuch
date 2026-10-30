"""Views für das MPG- & Medizingerätemodul (Medizinproduktebuch).

Erfüllt MPDG, MPBetreibV (§§ 6, 11-14) und DIN EN 62353.
"""
from __future__ import annotations

import csv
from io import BytesIO
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .access import CONTENT_ROLES, membership_required, station_module_required
from .models import Membership, Station
from .mpg_forms import (
    DeviceRoutineCheckForm,
    DeviceTrainingRecordForm,
    GroupTrainingForm,
    MaintenanceLogForm,
    MedicalDeviceForm,
)
from .device_status import ASSET_TO_DEVICE, DEVICE_TO_ASSET, mirror_to_asset, release_blockers
from .mpg_models import DeviceRoutineCheck, DeviceTrainingRecord, MaintenanceLog, MedicalDevice
from .services import audit
from .wachalltag_models import Defect


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("mpg_enabled")
@require_GET
def mpg_dashboard(request):
    """Cockpit für Medizinproduktebuch, STK/MTK-Prüffristen und Gerätestamm."""
    station = request.membership.station

    # Geräte aus „Geräte & Fahrzeuge“ übernehmen. Das Medizinproduktebuch ist
    # danach führend; der Status wird in beide Richtungen gespiegelt.
    from .wachalltag_models import StationAsset

    known = {
        device.slug: device
        for device in MedicalDevice.objects.filter(
            station=station,
            slug__in=StationAsset.objects.filter(station=station, kind=StationAsset.Kind.DEVICE).values("asset_id"),
        )
    }
    for legacy in StationAsset.objects.filter(station=station, kind=StationAsset.Kind.DEVICE):
        device = known.get(legacy.asset_id)
        if device is None:
            MedicalDevice.objects.create(
                station=station,
                slug=legacy.asset_id,
                name=legacy.label,
                location="Wache",
                current_status=ASSET_TO_DEVICE.get(legacy.status, MedicalDevice.Status.READY),
                status_note=legacy.note[:300],
            )
        elif DEVICE_TO_ASSET.get(device.current_status) != legacy.status:
            mirror_to_asset(device)

    devices_qs = MedicalDevice.objects.filter(station=station).exclude(
        current_status=MedicalDevice.Status.DECOMMISSIONED
    )

    query = request.GET.get("q", "").strip()
    if query:
        devices_qs = devices_qs.filter(
            Q(name__icontains=query)
            | Q(slug__iexact=query)
            | Q(model_type__icontains=query)
            | Q(serial_number__icontains=query)
            | Q(inventory_number__icontains=query)
            | Q(location__icontains=query)
            | Q(manufacturer__icontains=query)
        )

    category = request.GET.get("category", "").strip()
    if category:
        devices_qs = devices_qs.filter(category=category)

    # Filter nach Ampel / Dringlichkeit
    filter_mode = request.GET.get("filter", "all").strip()
    devices = list(devices_qs)

    overdue_count = 0
    critical_count = 0
    warning_count = 0
    ok_count = 0
    oob_count = 0

    for dev in devices:
        urg = dev.urgency
        lvl = urg["level"]
        if dev.current_status in (MedicalDevice.Status.OOB, MedicalDevice.Status.MAINTENANCE) or lvl == "overdue":
            overdue_count += 1
        elif lvl == "critical":
            critical_count += 1
        elif lvl == "warning":
            warning_count += 1
        else:
            ok_count += 1

        if dev.current_status == MedicalDevice.Status.OOB:
            oob_count += 1

    if filter_mode == "urgent":
        devices = [d for d in devices if d.urgency["level"] in ("overdue", "critical")]
    elif filter_mode == "warning":
        devices = [d for d in devices if d.urgency["level"] == "warning"]
    elif filter_mode == "oob":
        devices = [d for d in devices if d.current_status in (MedicalDevice.Status.OOB, MedicalDevice.Status.MAINTENANCE)]
    elif filter_mode == "ok":
        devices = [d for d in devices if d.urgency["level"] == "ok" and d.current_status == MedicalDevice.Status.READY]

    open_defects = Defect.objects.filter(
        station=station,
        category=Defect.Category.DEVICE,
        status__in=[Defect.Status.OPEN, Defect.Status.IN_PROGRESS, Defect.Status.WAITING],
    ).order_by("-priority", "created_at")

    recent_checks = DeviceRoutineCheck.objects.filter(station=station).select_related(
        "device", "performed_by"
    )[:5]
    recent_maint = MaintenanceLog.objects.filter(station=station).select_related(
        "device", "created_by"
    )[:5]

    can_manage = request.membership.role in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN}

    kpis = {
        "total": len(devices),
        "ready": ok_count,
        "limited": sum(1 for d in devices if d.current_status == MedicalDevice.Status.LIMITED),
        "oob": oob_count,
        "open_defects": open_defects.count(),
    }

    return render(
        request,
        "core/mpg_dashboard.html",
        {
            "devices": devices,
            "filter_mode": filter_mode,
            "query": query,
            "category": category,
            "categories": MedicalDevice.Category.choices,
            "total_count": len(devices),
            "overdue_count": overdue_count,
            "critical_count": critical_count,
            "warning_count": warning_count,
            "ok_count": ok_count,
            "oob_count": oob_count,
            "open_defects": open_defects[:5],
            "recent_checks": recent_checks,
            "recent_maint": recent_maint,
            "can_manage": can_manage,
            "kpis": kpis,
        },
    )


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("mpg_enabled")
@require_http_methods(["GET", "POST"])
def mpg_device_create(request):
    """Neues aktives Medizinprodukt anlegen."""
    station = request.membership.station
    can_manage = request.membership.role in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN}
    if not can_manage:
        messages.error(request, "Nur Wachleiter und Administratoren dürfen Medizinprodukte anlegen.")
        return redirect("mpg_dashboard")

    if request.method == "POST":
        form = MedicalDeviceForm(request.POST, station=station)
        if form.is_valid():
            device = form.save(commit=False)
            device.station = station
            device.save()
            messages.success(request, f"Medizinprodukt '{device.name}' erfolgreich registriert.")
            return redirect("mpg_device_detail", slug=device.slug)
    else:
        form = MedicalDeviceForm(station=station)

    return render(
        request,
        "core/mpg_device_form.html",
        {
            "form": form,
            "title": "Neues Medizinprodukt anlegen",
            "action_label": "Gerät speichern",
        },
    )


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("mpg_enabled")
@require_http_methods(["GET", "POST"])
def mpg_device_edit(request, slug: str):
    """Medizinprodukt-Stammdaten bearbeiten."""
    station = request.membership.station
    device = get_object_or_404(MedicalDevice, station=station, slug=slug)
    can_manage = request.membership.role in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN}
    if not can_manage:
        messages.error(request, "Keine Berechtigung zum Bearbeiten von Medizinprodukten.")
        return redirect("mpg_device_detail", slug=device.slug)

    if request.method == "POST":
        form = MedicalDeviceForm(request.POST, instance=device, station=station)
        if form.is_valid():
            form.save()
            messages.success(request, f"Änderungen an '{device.name}' gespeichert.")
            return redirect("mpg_device_detail", slug=device.slug)
    else:
        form = MedicalDeviceForm(instance=device, station=station)

    return render(
        request,
        "core/mpg_device_form.html",
        {
            "form": form,
            "device": device,
            "title": f"Medizinprodukt bearbeiten: {device.name}",
            "action_label": "Aktualisieren",
        },
    )


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("mpg_enabled")
@require_GET
def mpg_device_detail(request, slug: str):
    """Mobiles Geräte-Cockpit & digitales Medizinproduktebuch gem. § 13 MPBetreibV."""
    station = request.membership.station
    device = get_object_or_404(MedicalDevice, station=station, slug=slug)

    maint_logs = device.maintenance_logs.select_related("created_by").order_by("-performed_at")[:10]
    routine_checks = device.routine_checks.select_related("performed_by").order_by("-checked_at")[:10]
    trainings = device.trainings.select_related("trainee").order_by("-trained_at")

    is_user_trained = device.trainings.filter(trainee=request.user).exists()
    can_manage = request.membership.role in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN}

    maint_form = MaintenanceLogForm(auto_id="maint_%s")
    check_form = DeviceRoutineCheckForm(auto_id="check_%s")
    training_form = DeviceTrainingRecordForm(station=station, auto_id="training_%s")
    group_training_form = GroupTrainingForm(station=station, auto_id="group_%s")

    device_qr_url = request.build_absolute_uri(reverse("mpg_device_qr", args=[device.slug]))
    blocking_defects = release_blockers(device) if device.current_status == MedicalDevice.Status.OOB else []

    return render(
        request,
        "core/mpg_device_detail.html",
        {
            "device": device,
            "blocking_defects": blocking_defects,
            "maint_logs": maint_logs,
            "routine_checks": routine_checks,
            "trainings": trainings,
            "is_user_trained": is_user_trained,
            "can_manage": can_manage,
            "maint_form": maint_form,
            "check_form": check_form,
            "training_form": training_form,
            "group_training_form": group_training_form,
            "device_qr_url": device_qr_url,
        },
    )


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("mpg_enabled")
@require_POST
def mpg_routine_check(request, slug: str):
    """Funktionskontrolle erfassen.

    Jeder Prüfpunkt wird von der prüfenden Person bestätigt. Ein mitgeschickter
    Selbsttest-Ausdruck (Scan oder Text) wird nur als Notiz gespeichert und
    nicht automatisch ausgewertet.
    """
    station = request.membership.station
    device = get_object_or_404(MedicalDevice, station=station, slug=slug)
    was_locked = device.current_status == MedicalDevice.Status.OOB

    if request.POST.get("quick_pass") == "1":
        check = DeviceRoutineCheck(
            station=station,
            device=device,
            performed_by=request.user,
            battery_ok=True,
            visual_ok=True,
            function_ok=True,
            notes="Schnellkontrolle: alle Prüfpunkte bestätigt",
        )
    else:
        form = DeviceRoutineCheckForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Ungültige Eingaben bei der Funktionskontrolle.")
            return redirect("mpg_device_detail", slug=device.slug)
        check = form.save(commit=False)
        check.station = station
        check.device = device
        check.performed_by = request.user
        protocol = form.cleaned_data.get("selftest_protocol", "")
        if protocol:
            check.notes = f"{check.notes} | Selbsttest: {protocol}".strip(" |")[:300]
    check.save()
    audit(request.user, station, "mpg.routine_check", device, {"passed": check.passed})

    if not check.passed:
        messages.warning(
            request,
            f"Funktionskontrolle nicht bestanden. '{device.name}' ist gesperrt und ein Mangel wurde angelegt.",
        )
    elif was_locked:
        messages.info(
            request,
            f"Kontrolle gespeichert. '{device.name}' bleibt gesperrt, bis die Schichtleitung es nach "
            "Abschluss aller Mängel freigibt.",
        )
    else:
        messages.success(request, _("Funktionskontrolle für „%(name)s“ gespeichert.") % {"name": device.name})
    return redirect("mpg_device_detail", slug=device.slug)


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("mpg_enabled")
@require_POST
def mpg_device_release(request, slug: str):
    """Gesperrtes Gerät nach Abschluss aller Mängel wieder freigeben."""
    station = request.membership.station
    device = get_object_or_404(MedicalDevice, station=station, slug=slug)
    if request.membership.role not in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN}:
        messages.error(request, "Nur Schichtleitung oder Admin darf Geräte freigeben.")
        return redirect("mpg_device_detail", slug=device.slug)
    if device.current_status != MedicalDevice.Status.OOB:
        messages.info(request, "Das Gerät ist nicht gesperrt.")
        return redirect("mpg_device_detail", slug=device.slug)
    blockers = release_blockers(device)
    if blockers:
        numbers = ", ".join(f"#{item.pk}" for item in blockers)
        messages.error(request, f"Freigabe nicht möglich: offene Mängel {numbers}. Bitte zuerst abschließen.")
        return redirect("mpg_device_detail", slug=device.slug)
    confirmed = all(request.POST.get(name) == "on" for name in ("battery_ok", "visual_ok", "function_ok"))
    if not confirmed:
        messages.error(request, "Für die Freigabe müssen alle Prüfpunkte bestätigt sein.")
        return redirect("mpg_device_detail", slug=device.slug)
    note = (request.POST.get("notes") or "").strip()
    with transaction.atomic():
        DeviceRoutineCheck(
            station=station,
            device=device,
            performed_by=request.user,
            battery_ok=True,
            visual_ok=True,
            function_ok=True,
            notes=f"Freigabe nach Sperre: {note}".strip(": ")[:300],
        ).save()
        device.refresh_from_db()
        device.current_status = MedicalDevice.Status.READY
        device.status_note = ""
        device.save(update_fields=["current_status", "status_note", "updated_at"])
        audit(request.user, station, "mpg.device_released", device, {"note": bool(note)})
    messages.success(request, f"'{device.name}' ist wieder einsatzklar.")
    return redirect("mpg_device_detail", slug=device.slug)


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("mpg_enabled")
@require_POST
def mpg_maintenance_create(request, slug: str):
    """STK, MTK oder DGUV V3 Prüfung dokumentieren."""
    station = request.membership.station
    device = get_object_or_404(MedicalDevice, station=station, slug=slug)
    can_manage = request.membership.role in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN}
    if not can_manage:
        messages.error(request, "Nur autorisiertes Personal darf Prüfungen und Wartungen eintragen.")
        return redirect("mpg_device_detail", slug=device.slug)

    form = MaintenanceLogForm(request.POST)
    if form.is_valid():
        log = form.save(commit=False)
        log.station = station
        log.device = device
        log.created_by = request.user
        log.save()
        messages.success(request, f"{log.get_kind_display()} für '{device.name}' erfolgreich dokumentiert.")
    else:
        messages.error(request, "Bitte Eingaben im Prüfungsformular prüfen.")

    return redirect("mpg_device_detail", slug=device.slug)


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("mpg_enabled")
@require_POST
def mpg_training_create(request, slug: str):
    """Geräteeinweisung (§ 11 MPBetreibV) für Einzelpersonen oder Gruppen speichern."""
    station = request.membership.station
    device = get_object_or_404(MedicalDevice, station=station, slug=slug)
    can_manage = request.membership.role in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN}
    if not can_manage:
        messages.error(request, "Nur MPG-Beauftragte und Wachleiter dürfen Einweisungen bescheinigen.")
        return redirect("mpg_device_detail", slug=device.slug)

    is_group = "trainees" in request.POST
    if is_group:
        group_form = GroupTrainingForm(request.POST, station=station)
        if group_form.is_valid():
            trainees = group_form.cleaned_data["trainees"]
            instructor = group_form.cleaned_data["instructor"]
            trained_at = group_form.cleaned_data["trained_at"]
            notes = group_form.cleaned_data.get("notes", "")

            created_count = 0
            for trainee in trainees:
                obj, created = DeviceTrainingRecord.objects.update_or_create(
                    device=device,
                    trainee=trainee,
                    defaults={
                        "station": station,
                        "instructor": instructor,
                        "trained_at": trained_at,
                        "notes": notes,
                    },
                )
                if created:
                    created_count += 1
            messages.success(
                request,
                f"Gruppenschulung dokumentiert: {len(trainees)} Mitarbeiter für '{device.name}' eingewiesen.",
            )
        else:
            messages.error(request, "Fehlerhafte Angaben bei der Gruppenschulung.")
    else:
        form = DeviceTrainingRecordForm(request.POST, station=station)
        if form.is_valid():
            record = form.save(commit=False)
            record.station = station
            record.device = device
            # Vorherige Einweisung aktualisieren falls vorhanden
            DeviceTrainingRecord.objects.filter(device=device, trainee=record.trainee).delete()
            record.save()
            messages.success(
                request,
                f"Einweisung für {record.trainee.get_full_name() or record.trainee.username} gespeichert.",
            )
        else:
            messages.error(request, "Fehlerhafte Angaben beim Einweisungsnachweis.")

    return redirect("mpg_device_detail", slug=device.slug)


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("mpg_enabled")
@require_POST
def mpg_device_defect(request, slug: str):
    """Sofort-Eskalation: Mangel an Gerät melden und Einsatzstatus sperren."""
    station = request.membership.station
    device = get_object_or_404(MedicalDevice, station=station, slug=slug)

    title = request.POST.get("title", "").strip() or f"Defekt an {device.name}"
    description = request.POST.get("description", "").strip()
    priority = request.POST.get("priority", Defect.Priority.URGENT)

    if priority not in Defect.Priority.values:
        priority = Defect.Priority.URGENT

    # Mangel im Wachalltag anlegen; er hält das Gerät gesperrt, bis er erledigt ist.
    defect = Defect.objects.create(
        station=station,
        medical_device=device,
        title=title[:160],
        description=f"Standort: {device.location}\nSeriennummer: {device.serial_number}\n\n{description}".strip(),
        asset_ref=f"{device.name} ({device.inventory_number or device.serial_number})",
        priority=priority,
        status=Defect.Status.OPEN,
        category=Defect.Category.DEVICE,
        created_by=request.user,
    )

    # Gerät sperren
    device.current_status = MedicalDevice.Status.OOB
    device.status_note = f"Defekt gemeldet: {title}"
    device.save(update_fields=["current_status", "status_note", "updated_at"])
    audit(request.user, station, "mpg.device_locked", device, {"defect_id": defect.pk})

    messages.warning(
        request,
        f"Mangel #{defect.id} erfasst! Gerät '{device.name}' wurde sofort auf 'Außer Betrieb' gesetzt.",
    )
    return redirect("mpg_device_detail", slug=device.slug)


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("mpg_enabled")
@require_GET
def mpg_geraetepass(request):
    """Digitaler Gerätepass gem. § 11 MPBetreibV: Übersicht aller Befähigungen."""
    station = request.membership.station
    user_memberships = Membership.objects.filter(station=station, is_active=True).select_related("user")
    users = [m.user for m in user_memberships]

    devices = MedicalDevice.objects.filter(station=station).exclude(
        current_status=MedicalDevice.Status.DECOMMISSIONED
    ).order_by("category", "name")

    # Alle Trainings für die Wache laden
    all_trainings = DeviceTrainingRecord.objects.filter(station=station).select_related("device", "trainee")
    user_device_map: dict[tuple[int, int], DeviceTrainingRecord] = {}
    for t in all_trainings:
        user_device_map[(t.trainee_id, t.device_id)] = t

    # Matrix für Template aufbereiten
    matrix = []
    for u in users:
        trained_devices = []
        for d in devices:
            rec = user_device_map.get((u.id, d.id))
            trained_devices.append({
                "device": d,
                "is_trained": rec is not None,
                "record": rec,
            })
        matrix.append({
            "user": u,
            "trained_count": sum(1 for item in trained_devices if item["is_trained"]),
            "items": trained_devices,
        })

    # Persönlicher Gerätepass des eingeloggten Benutzers
    my_trainings = [t for t in all_trainings if t.trainee_id == request.user.id]

    return render(
        request,
        "core/mpg_geraetepass.html",
        {
            "devices": devices,
            "matrix": matrix,
            "my_trainings": my_trainings,
            "total_devices_count": devices.count(),
        },
    )


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("mpg_enabled")
@require_GET
def mpg_device_qr(request, slug: str):
    """Wetterfester QR-Code für den Geräteaufkleber als PNG."""
    import qrcode

    station = request.membership.station
    device = get_object_or_404(MedicalDevice, station=station, slug=slug)

    target_url = request.build_absolute_uri(reverse("mpg_device_detail", args=[device.slug]))
    image = qrcode.make(target_url)

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    response = HttpResponse(buffer.getvalue(), content_type="image/png")
    response["Cache-Control"] = "public, max-age=86400"
    return response


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("mpg_enabled")
@require_GET
def mpg_export_bestandsverzeichnis(request):
    """Export des gesetzlichen Bestandsverzeichnisses gem. § 14 MPBetreibV als CSV."""
    station = request.membership.station
    devices = MedicalDevice.objects.filter(station=station).order_by("category", "name")

    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = f'attachment; filename="MPG_Bestandsverzeichnis_{station.slug}_{timezone.localdate().isoformat()}.csv"'

    writer = csv.writer(response, delimiter=";")
    writer.writerow([
        "Inventarnummer",
        "Gerätebezeichnung",
        "Kategorie",
        "Risikoklasse",
        "Hersteller",
        "Typ / Modell",
        "Seriennummer",
        "UDI-DI (GTIN)",
        "CE-Kennnummer",
        "Baujahr",
        "Standort / Fahrzeug",
        "Status",
        "Anlage 1 (STK)",
        "STK-Intervall (M)",
        "Nächste STK",
        "Nächste MTK",
        "Nächste DGUV V3",
        "Letzte Funktionskontrolle",
    ])

    for d in devices:
        writer.writerow([
            d.inventory_number,
            d.name,
            d.get_category_display(),
            d.get_risk_class_display(),
            d.manufacturer,
            d.model_type,
            d.serial_number,
            d.udi_di,
            d.ce_notified_body,
            d.year_of_manufacture or "",
            d.location,
            d.get_current_status_display(),
            "Ja" if d.is_anlage_1 else "Nein",
            d.stk_interval_months,
            d.next_stk_date.isoformat() if d.next_stk_date else "",
            d.next_mtk_date.isoformat() if d.next_mtk_date else "",
            d.next_dguv_date.isoformat() if d.next_dguv_date else "",
            timezone.localtime(d.last_routine_check).strftime("%d.%m.%Y %H:%M") if d.last_routine_check else "",
        ])

    return response
