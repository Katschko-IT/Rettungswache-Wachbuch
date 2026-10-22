"""Views für das Lager- & Materialwirtschaftsmodul (FEFO & Verfallsradar).

Erfüllt AMG, MPDG und Best-in-Class Notfall-Logistik (Kühlketten-Dynamik 'Out-of-Fridge',
BfArM-Rückrufsperre und 1-Scan GS1-DataMatrix Support).
"""
from __future__ import annotations

import csv
from datetime import date, timedelta
from django.contrib import messages
from django.db import transaction
from django.db.models import F, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .access import CONTENT_ROLES, membership_required, station_module_required
from .models import Membership, Station, StationTask
from .warehouse_forms import (
    BatchRecallForm,
    ItemBatchForm,
    MedicalItemForm,
    StockTransferForm,
    StorageLocationForm,
)
from .warehouse_models import ItemBatch, MedicalItem, StockItem, StockMovement, StorageLocation


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("warehouse_enabled")
@require_GET
def warehouse_dashboard(request):
    """FEFO-Verfallsradar, Chargenübersicht und Nachbestell-Radar."""
    station = request.membership.station

    # Falls noch keine Standard-Lagerorte existieren, Standardorte anlegen
    if not StorageLocation.objects.filter(station=station).exists():
        StorageLocation.objects.create(
            station=station, slug="hauptlager", name="Zentrallager / Apotheke", kind=StorageLocation.Kind.CENTRAL
        )
        StorageLocation.objects.create(
            station=station, slug="kuehlschrank", name="Medikamentenkühlschrank", kind=StorageLocation.Kind.FRIDGE, is_cold_storage=True
        )
        StorageLocation.objects.create(
            station=station, slug="rtw-01", name="RTW 01/83-01 Schrank", kind=StorageLocation.Kind.VEHICLE
        )

    # Legacy InventoryItem nahtlos synchronisieren
    from .wachalltag_models import InventoryItem
    for legacy in InventoryItem.objects.filter(station=station):
        if not MedicalItem.objects.filter(station=station, slug=legacy.item_id).exists():
            MedicalItem.objects.create(
                station=station,
                slug=legacy.item_id,
                name=legacy.label,
                category=MedicalItem.Category.AIRWAY if "atmung" in legacy.label.lower() else MedicalItem.Category.OTHER,
            )

    items_qs = MedicalItem.objects.filter(station=station).prefetch_related("batches", "stock_items")

    query = request.GET.get("q", "").strip()
    if query:
        items_qs = items_qs.filter(
            Q(name__icontains=query)
            | Q(pzn__icontains=query)
            | Q(gtin__icontains=query)
            | Q(batches__batch_number__icontains=query)
        ).distinct()

    category = request.GET.get("category", "").strip()
    if category:
        items_qs = items_qs.filter(category=category)

    filter_mode = request.GET.get("filter", "all").strip()

    # Alle Chargen für die Wache analysieren
    all_batches = ItemBatch.objects.filter(station=station).select_related("item").prefetch_related("stock_items__location")

    today = timezone.localdate()
    recalled_count = 0
    overdue_count = 0
    critical_count = 0
    warning_count = 0
    ok_count = 0

    for b in all_batches:
        urg = b.urgency
        lvl = urg["level"]
        if lvl == "recalled":
            recalled_count += 1
        elif lvl == "overdue":
            overdue_count += 1
        elif lvl == "critical":
            critical_count += 1
        elif lvl == "warning":
            warning_count += 1
        else:
            ok_count += 1

    items_list = list(items_qs)
    low_stock_items = [it for it in items_list if it.is_under_min_stock]

    # Filter anwenden
    if filter_mode == "urgent":
        urgent_item_ids = {b.item_id for b in all_batches if b.urgency["level"] in ("overdue", "critical")}
        items_list = [it for it in items_list if it.id in urgent_item_ids]
    elif filter_mode == "warning":
        warning_item_ids = {b.item_id for b in all_batches if b.urgency["level"] == "warning"}
        items_list = [it for it in items_list if it.id in warning_item_ids]
    elif filter_mode == "recalled":
        recalled_item_ids = {b.item_id for b in all_batches if b.is_recalled}
        items_list = [it for it in items_list if it.id in recalled_item_ids]
    elif filter_mode == "low_stock":
        items_list = low_stock_items

    # FEFO-Highlighting für jeden Artikel (nächstes Verfallsdatum)
    for it in items_list:
        batches = [b for b in it.batches.all() if not b.is_recalled]
        if batches:
            batches.sort(key=lambda b: b.effective_date)
            it.earliest_batch = batches[0]
        else:
            it.earliest_batch = None

    recent_movements = StockMovement.objects.filter(station=station).select_related(
        "item", "batch", "source_location", "target_location", "actor"
    )[:8]

    can_manage = request.membership.role in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN}

    return render(
        request,
        "core/warehouse_dashboard.html",
        {
            "items": items_list,
            "filter_mode": filter_mode,
            "query": query,
            "category": category,
            "categories": MedicalItem.Category.choices,
            "total_items_count": len(items_list),
            "recalled_count": recalled_count,
            "overdue_count": overdue_count,
            "critical_count": critical_count,
            "warning_count": warning_count,
            "ok_count": ok_count,
            "low_stock_count": len(low_stock_items),
            "recent_movements": recent_movements,
            "can_manage": can_manage,
        },
    )


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("warehouse_enabled")
@require_http_methods(["GET", "POST"])
def item_create(request):
    """Neuen Artikel im Lager anlegen."""
    station = request.membership.station
    can_manage = request.membership.role in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN}
    if not can_manage:
        messages.error(request, "Nur Wachleiter und Administratoren dürfen Artikel im Lager anlegen.")
        return redirect("warehouse_dashboard")

    if request.method == "POST":
        form = MedicalItemForm(request.POST, station=station)
        if form.is_valid():
            item = form.save(commit=False)
            item.station = station
            item.save()
            messages.success(request, f"Artikel '{item.name}' erfolgreich registriert.")
            return redirect("warehouse_item_detail", slug=item.slug)
    else:
        form = MedicalItemForm(station=station)

    return render(
        request,
        "core/warehouse_item_form.html",
        {"form": form, "title": "Neuen Artikel anlegen", "action_label": "Artikel speichern"},
    )


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("warehouse_enabled")
@require_http_methods(["GET", "POST"])
def item_edit(request, slug: str):
    """Artikelstammdaten bearbeiten."""
    station = request.membership.station
    item = get_object_or_404(MedicalItem, station=station, slug=slug)
    can_manage = request.membership.role in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN}
    if not can_manage:
        messages.error(request, "Keine Berechtigung zum Bearbeiten.")
        return redirect("warehouse_item_detail", slug=item.slug)

    if request.method == "POST":
        form = MedicalItemForm(request.POST, instance=item, station=station)
        if form.is_valid():
            form.save()
            messages.success(request, f"Änderungen an '{item.name}' gespeichert.")
            return redirect("warehouse_item_detail", slug=item.slug)
    else:
        form = MedicalItemForm(instance=item, station=station)

    return render(
        request,
        "core/warehouse_item_form.html",
        {"form": form, "item": item, "title": f"Artikel bearbeiten: {item.name}", "action_label": "Aktualisieren"},
    )


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("warehouse_enabled")
@require_GET
def item_detail(request, slug: str):
    """Detailansicht eines Artikels mit FEFO-Chargenliste und Lagerort-Beständen."""
    station = request.membership.station
    item = get_object_or_404(MedicalItem, station=station, slug=slug)

    batches = item.batches.prefetch_related("stock_items__location").order_by("calculated_exp_date")
    stock_items = item.stock_items.select_related("batch", "location").order_by("location__name")
    movements = item.movements.select_related("batch", "source_location", "target_location", "actor")[:15]

    can_manage = request.membership.role in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN}
    batch_form = ItemBatchForm(station=station)
    transfer_form = StockTransferForm(station=station)

    return render(
        request,
        "core/warehouse_item_detail.html",
        {
            "item": item,
            "batches": batches,
            "stock_items": stock_items,
            "movements": movements,
            "can_manage": can_manage,
            "batch_form": batch_form,
            "transfer_form": transfer_form,
        },
    )


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("warehouse_enabled")
@require_POST
@transaction.atomic
def batch_create(request, slug: str):
    """Neue Charge einbuchen (Wareneingang)."""
    station = request.membership.station
    item = get_object_or_404(MedicalItem, station=station, slug=slug)

    form = ItemBatchForm(request.POST, station=station)
    if form.is_valid():
        batch = form.save(commit=False)
        batch.station = station
        batch.item = item
        batch.save()

        location = form.cleaned_data["initial_location"]
        quantity = form.cleaned_data["initial_quantity"]

        # Bestand anlegen
        stock, created = StockItem.objects.get_or_create(
            station=station,
            item=item,
            batch=batch,
            location=location,
            defaults={"quantity": quantity},
        )
        if not created:
            stock.quantity += quantity
            stock.save(update_fields=["quantity", "updated_at"])

        # Buchungsjournal
        StockMovement.objects.create(
            station=station,
            item=item,
            batch=batch,
            source_location=None,
            target_location=location,
            quantity=quantity,
            kind=StockMovement.Kind.INBOUND,
            actor=request.user,
            note="Wareneingang Charge",
        )

        messages.success(request, f"Charge {batch.batch_number} ({quantity} {item.get_unit_display()}) erfolgreich eingebucht.")
    else:
        messages.error(request, "Fehlerhafte Angaben beim Anlegen der Charge.")

    return redirect("warehouse_item_detail", slug=item.slug)


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("warehouse_enabled")
@require_POST
@transaction.atomic
def stock_transfer(request, batch_id: int):
    """Umlagerung einer Charge zwischen Lagerorten (z. B. Lager → RTW)."""
    station = request.membership.station
    batch = get_object_or_404(ItemBatch, station=station, id=batch_id)
    item = batch.item

    form = StockTransferForm(request.POST, station=station)
    if form.is_valid():
        source_loc = form.cleaned_data["source_location"]
        target_loc = form.cleaned_data["target_location"]
        qty = form.cleaned_data["quantity"]
        mark_oof = form.cleaned_data["mark_out_of_fridge"]
        note = form.cleaned_data.get("note", "")

        if source_loc == target_loc:
            messages.error(request, "Quell- und Ziellagerort dürfen nicht identisch sein.")
            return redirect("warehouse_item_detail", slug=item.slug)

        source_stock = StockItem.objects.filter(station=station, batch=batch, location=source_loc).first()
        if not source_stock or source_stock.quantity < qty:
            available = source_stock.quantity if source_stock else 0
            messages.error(request, f"Nicht genug Bestand am Quellort (Verfügbar: {available}).")
            return redirect("warehouse_item_detail", slug=item.slug)

        # Quellbestand abbuchen
        source_stock.quantity -= qty
        if source_stock.quantity == 0:
            source_stock.delete()
        else:
            source_stock.save(update_fields=["quantity", "updated_at"])

        # Zielbestand aufbuchen
        target_stock, _ = StockItem.objects.get_or_create(
            station=station,
            item=item,
            batch=batch,
            location=target_loc,
            defaults={"quantity": 0},
        )
        target_stock.quantity += qty
        target_stock.save(update_fields=["quantity", "updated_at"])

        # Kühlkette prüfen (Out-of-Fridge aktivieren falls Ziellager ungekühlt)
        if mark_oof and item.requires_cooling and not target_loc.is_cold_storage:
            if not batch.out_of_fridge_date:
                batch.out_of_fridge_date = timezone.localdate()
                batch.save()
                messages.warning(
                    request,
                    f"Out-of-Fridge aktiviert: Charge {batch.batch_number} läuft ungekühlt nach {item.room_temp_max_days} Tagen ab ({batch.effective_date.strftime('%d.%m.%Y')}).",
                )

        # Buchungsjournal
        StockMovement.objects.create(
            station=station,
            item=item,
            batch=batch,
            source_location=source_loc,
            target_location=target_loc,
            quantity=qty,
            kind=StockMovement.Kind.TRANSFER,
            actor=request.user,
            note=note or f"Umlagerung {source_loc.name} → {target_loc.name}",
        )

        messages.success(request, f"{qty} {item.get_unit_display()} erfolgreich auf {target_loc.name} umgebucht.")
    else:
        messages.error(request, "Ungültige Angaben bei der Umlagerung.")

    return redirect("warehouse_item_detail", slug=item.slug)


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("warehouse_enabled")
@require_POST
@transaction.atomic
def stock_consume(request, batch_id: int):
    """Verbrauch am Patienten / Verfallsausscheidung verbuchen."""
    station = request.membership.station
    batch = get_object_or_404(ItemBatch, station=station, id=batch_id)
    item = batch.item

    loc_id = request.POST.get("location_id")
    qty = int(request.POST.get("quantity", 1))
    reason = request.POST.get("reason", "Einsatzverbrauch")
    is_discard = request.POST.get("is_discard") == "1"

    loc = get_object_or_404(StorageLocation, station=station, id=loc_id)
    stock = StockItem.objects.filter(station=station, batch=batch, location=loc).first()

    if not stock or stock.quantity < qty:
        messages.error(request, "Kein ausreichender Bestand vorhanden.")
        return redirect("warehouse_item_detail", slug=item.slug)

    stock.quantity -= qty
    if stock.quantity == 0:
        stock.delete()
    else:
        stock.save(update_fields=["quantity", "updated_at"])

    kind = StockMovement.Kind.DISCARD_EXPIRED if is_discard else StockMovement.Kind.OUTBOUND
    StockMovement.objects.create(
        station=station,
        item=item,
        batch=batch,
        source_location=loc,
        target_location=None,
        quantity=qty,
        kind=kind,
        actor=request.user,
        note=reason,
    )

    action_label = "ausgemustert" if is_discard else "als verbraucht verbucht"
    messages.success(request, f"{qty} {item.get_unit_display()} {action_label}.")
    return redirect("warehouse_item_detail", slug=item.slug)


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("warehouse_enabled")
@require_http_methods(["GET", "POST"])
@transaction.atomic
def batch_recall(request):
    """BfArM-Rückrufsperre: Blitz-Filter und sofortige Quarantäne über alle Fahrzeuge."""
    station = request.membership.station

    if request.method == "POST":
        form = BatchRecallForm(request.POST)
        if form.is_valid():
            lot = form.cleaned_data["batch_number"].strip()
            reason = form.cleaned_data["reason"].strip()

            matching_batches = ItemBatch.objects.filter(station=station, batch_number__iexact=lot)
            if not matching_batches.exists():
                messages.error(request, f"Keine Charge mit der Lot-Nummer '{lot}' auf der Wache gefunden.")
            else:
                updated_count = 0
                for b in matching_batches:
                    b.is_recalled = True
                    b.recall_reason = reason
                    b.save(update_fields=["is_recalled", "recall_reason"])
                    updated_count += 1

                    # Log quarantine
                    StockMovement.objects.create(
                        station=station,
                        item=b.item,
                        batch=b,
                        source_location=None,
                        target_location=None,
                        quantity=sum(si.quantity for si in b.stock_items.all()),
                        kind=StockMovement.Kind.RECALL_QUARANTINE,
                        actor=request.user,
                        note=f"RÜCKRUF-SPERRE: {reason}",
                    )

                messages.warning(
                    request,
                    f"RÜCKRUF AKTIV! {updated_count} Charge(n) mit Lot '{lot}' wurden sofort für alle Fahrzeuge und Einsätze gesperrt.",
                )
                return redirect("warehouse_dashboard")
    else:
        form = BatchRecallForm()

    # Aktuell gesperrte Chargen auflisten
    recalled_batches = ItemBatch.objects.filter(station=station, is_recalled=True).select_related("item").prefetch_related("stock_items__location")

    return render(
        request,
        "core/warehouse_recall.html",
        {"form": form, "recalled_batches": recalled_batches},
    )


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("warehouse_enabled")
@require_GET
def export_fefo_csv(request):
    """Export aller Bestände sortiert nach FEFO (Verfallsdatum) als CSV."""
    station = request.membership.station
    stock_items = StockItem.objects.filter(station=station).select_related(
        "item", "batch", "location"
    ).order_by("batch__calculated_exp_date", "item__name")

    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = f'attachment; filename="FEFO_Lagerbestand_{station.slug}_{timezone.localdate().isoformat()}.csv"'

    writer = csv.writer(response, delimiter=";")
    writer.writerow([
        "Artikel",
        "Kategorie",
        "PZN",
        "GTIN",
        "Charge (Lot)",
        "Hersteller-MHD",
        "Out-of-Fridge Datum",
        "Effektives MHD (FEFO)",
        "Lagerort",
        "Bestand",
        "Einheit",
        "Status / Rückruf",
    ])

    for si in stock_items:
        writer.writerow([
            si.item.name,
            si.item.get_category_display(),
            si.item.pzn,
            si.item.gtin,
            si.batch.batch_number,
            si.batch.manufacturer_exp_date.isoformat(),
            si.batch.out_of_fridge_date.isoformat() if si.batch.out_of_fridge_date else "",
            si.batch.effective_date.isoformat(),
            si.location.name,
            si.quantity,
            si.item.get_unit_display(),
            "GESPERRT: " + si.batch.recall_reason if si.batch.is_recalled else si.batch.urgency["label"],
        ])

    return response


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("warehouse_enabled")
@require_http_methods(["GET", "POST"])
def warehouse_reorder_proposal(request):
    """Automatischer Bestellschein & Nachbestell-Trigger bei Mindestbestand."""
    station = request.membership.station
    items = MedicalItem.objects.filter(station=station).prefetch_related("stock_items__batch")

    low_stock_proposals = []
    for item in items:
        if item.is_under_min_stock:
            curr = item.total_stock
            suggested = max(item.target_stock - curr, 1)
            low_stock_proposals.append({
                "item": item,
                "current_stock": curr,
                "min_stock": item.min_stock,
                "target_stock": item.target_stock,
                "suggested_qty": suggested,
                "unit": item.get_unit_display(),
            })

    action = request.POST.get("action") or request.GET.get("action")

    if action == "export_csv" or request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
        response["Content-Disposition"] = f'attachment; filename="Apotheken_Bestellung_{station.slug}_{timezone.localdate().isoformat()}.csv"'
        writer = csv.writer(response, delimiter=";")
        writer.writerow(["PZN", "Artikelbezeichnung", "Kategorie", "Bestellmenge", "Einheit", "Ist-Bestand", "Mindestbestand", "Sollbestand"])
        for p in low_stock_proposals:
            writer.writerow([
                p["item"].pzn,
                p["item"].name,
                p["item"].get_category_display(),
                p["suggested_qty"],
                p["unit"],
                p["current_stock"],
                p["min_stock"],
                p["target_stock"],
            ])
        return response

    if request.method == "POST" and (action == "create_task" or request.POST.get("create_task") == "1"):
        if not low_stock_proposals:
            messages.info(request, "Alle Artikel haben ausreichenden Bestand. Keine Nachbestellung nötig.")
            return redirect("warehouse_reorder_proposal")

        task_title = f"📦 Apotheken-Bestellung auslösen: {len(low_stock_proposals)} Artikel unter Mindestbestand"
        if not StationTask.objects.filter(station=station, title=task_title).exists():
            StationTask.objects.create(
                station=station,
                title=task_title,
                band=StationTask.Band.EXTRA,
                repeat=StationTask.Repeat.ONCE,
            )
            messages.success(request, f"Tagesaufgabe im Wachbuch angelegt: '{task_title}'.")
        else:
            messages.info(request, "Die Nachbestell-Aufgabe existiert bereits im Wachbuch.")
        return redirect("warehouse_reorder_proposal")

    return render(
        request,
        "core/warehouse_reorder.html",
        {
            "proposals": low_stock_proposals,
            "total_low_count": len(low_stock_proposals),
            "can_manage": request.membership.role in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN},
        },
    )


@membership_required(allowed_roles=CONTENT_ROLES)
@station_module_required("warehouse_enabled")
@require_POST
def warehouse_express_transfer(request):
    """1-Scan Schnellaufrüstung: Bucht Material direkt vom Zentrallager auf Zielfahrzeug."""
    station = request.membership.station
    target_slug = request.POST.get("target_location_slug", "").strip()
    batch_id = request.POST.get("batch_id")
    barcode = request.POST.get("barcode", "").strip()
    qty_str = request.POST.get("quantity", "1").strip()

    try:
        quantity = max(1, int(qty_str))
    except ValueError:
        quantity = 1

    target_loc = get_object_or_404(StorageLocation, station=station, slug=target_slug)

    batch = None
    if batch_id:
        batch = get_object_or_404(ItemBatch, id=batch_id, station=station)
    elif barcode:
        batch = ItemBatch.objects.filter(station=station, batch_number__iexact=barcode, is_recalled=False).first()
        if not batch:
            item = MedicalItem.objects.filter(
                Q(station=station) & (Q(pzn__iexact=barcode) | Q(gtin__iexact=barcode))
            ).first()
            if item:
                batch = item.batches.filter(is_recalled=False).order_by("calculated_exp_date").first()

    if not batch:
        messages.error(request, f"Keine passende Charge für Barcode '{barcode}' gefunden.")
        return redirect("warehouse_dashboard")

    if batch.is_recalled:
        messages.error(request, f"Charge {batch.batch_number} ist gesperrt und darf nicht gebucht werden!")
        return redirect("warehouse_dashboard")

    central_loc = StorageLocation.objects.filter(
        station=station, kind__in=[StorageLocation.Kind.CENTRAL, StorageLocation.Kind.FRIDGE]
    ).first()

    with transaction.atomic():
        if central_loc:
            src_stock = StockItem.objects.filter(location=central_loc, batch=batch).first()
            if src_stock and src_stock.quantity >= quantity:
                src_stock.quantity -= quantity
                src_stock.save(update_fields=["quantity"])

        target_stock, _ = StockItem.objects.get_or_create(
            station=station,
            item=batch.item,
            batch=batch,
            location=target_loc,
            defaults={"quantity": 0},
        )
        target_stock.quantity += quantity
        target_stock.save(update_fields=["quantity"])

        if batch.item.requires_cooling and not target_loc.is_cold_storage and not batch.out_of_fridge_date:
            batch.out_of_fridge_date = timezone.localdate()
            if batch.item.room_temp_max_days:
                calc_exp = batch.out_of_fridge_date + timedelta(days=batch.item.room_temp_max_days)
                if not batch.calculated_exp_date or calc_exp < batch.calculated_exp_date:
                    batch.calculated_exp_date = calc_exp
            batch.save(update_fields=["out_of_fridge_date", "calculated_exp_date"])

        StockMovement.objects.create(
            station=station,
            item=batch.item,
            batch=batch,
            source_location=central_loc,
            target_location=target_loc,
            quantity=quantity,
            kind=StockMovement.Kind.TRANSFER,
            actor=request.user,
            note=f"1-Scan Express-Umlagerung nach {target_loc.name}",
        )

    messages.success(
        request,
        f"✅ {quantity}x {batch.item.name} (Lot {batch.batch_number}) erfolgreich nach '{target_loc.name}' aufgerüstet.",
    )
    return redirect("warehouse_dashboard")
