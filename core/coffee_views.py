"""Kaffeekasse: eigene Übersicht, Mappe des Kassenwarts, Kasse und Einstellungen.

Einsicht in Stände und Buchungen anderer Personen hat nur der Kassenwart.
Admins richten die Kasse ein (Beitrag, Teilnehmende, Zahlungswege), sehen aber
nur Summen ohne Namen. Kassenbestand, Einkäufe und Kassenstürze sind für alle
sichtbar – so bleibt nachvollziehbar, wohin das Geld der Kasse geht.
"""
from __future__ import annotations

import csv
import datetime as dt

from django.contrib import messages
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST

from . import coffee as logic
from .access import CONTENT_ROLES, membership_required, station_module_required
from .coffee_models import CoffeeCashMovement, CoffeeFund, CoffeeParticipant
from .forms import (
    CoffeeCorrectionForm,
    CoffeeCountForm,
    CoffeeEntryForm,
    CoffeeFundForm,
    CoffeeMovementForm,
    CoffeeParticipantForm,
    CoffeePaymentForm,
    CoffeePaymentWaysForm,
    CoffeePurchaseForm,
)
from .models import CoffeeEntry, Membership
from .services import audit

CASHIER = {Membership.Role.CASHIER}
SETUP_ROLES = {Membership.Role.CASHIER, Membership.Role.ADMIN}
MONTHS_SHOWN = 6


def _is_cashier(request) -> bool:
    return request.membership.role == Membership.Role.CASHIER


def _page(request, queryset, per_page=25):
    from django.core.paginator import Paginator

    return Paginator(queryset, per_page).get_page(request.GET.get("seite"))


def _qr_data_uri(payload: str) -> str:
    from .views import _qr_data_uri as render_qr

    return render_qr(payload)


def _payment_methods(station) -> list:
    methods = [CoffeeEntry.Method.CASH]
    if station.iban:
        methods.append(CoffeeEntry.Method.TRANSFER)
    if station.paypal_me_url:
        methods.append(CoffeeEntry.Method.PAYPAL)
    if station.wero_link:
        methods.append(CoffeeEntry.Method.WERO)
    return methods


def _person(user) -> str:
    return user.get_full_name() or user.get_username()


@membership_required(CONTENT_ROLES)
@station_module_required("coffee_enabled")
def coffee(request):
    station = request.membership.station
    fund = logic.fund_for(station)
    logic.ensure_fees(station)
    today = logic.station_today(station)
    current = logic.month_start(today)
    status = logic.member_status(station, request.user)
    participant = CoffeeParticipant.objects.filter(station=station, user=request.user).first()
    own_entries = CoffeeEntry.objects.filter(station=station, member=request.user).select_related(
        "created_by", "correction_of"
    )
    suggested = status.open_cents or fund.monthly_fee_cents
    girocode = None
    if station.iban:
        name = fund.account_holder or station.name
        try:
            payload = logic.epc_payload(
                name=name, iban=station.iban, bic=station.bic, amount_cents=suggested,
                text=logic.transfer_text(station, request.user),
            )
            girocode = {"image": _qr_data_uri(payload), "name": name, "iban": logic.normalize_iban(station.iban),
                        "amount_euros": suggested / 100, "text": logic.transfer_text(station, request.user)}
        except ValueError:
            girocode = None
    prepaid_months = 0
    if fund.monthly_fee_cents and status.credit_cents:
        prepaid_months = status.credit_cents // fund.monthly_fee_cents
    return render(request, "core/coffee.html", {
        "station": station,
        "fund": fund,
        "status": status,
        "months": [
            m for m in status.recent(current, 12)
            if m.status != logic.NOT_CHARGED or (participant and m.period >= participant.since)
        ],
        "participant": participant,
        "prepaid_months": prepaid_months,
        "prepaid_until": logic.add_months(current, prepaid_months) if prepaid_months else None,
        "page_obj": _page(request, own_entries, 15),
        "pots": logic.pots(station),
        "movements": CoffeeCashMovement.objects.filter(station=station).select_related("created_by")[:8],
        "last_count": logic.last_count(station),
        "summary": logic.month_summary(station, current) if fund.monthly_fee_cents else None,
        "current_month": current,
        "girocode": girocode,
        "is_cashier": _is_cashier(request),
        "can_setup": request.membership.role in SETUP_ROLES,
    })


@membership_required(CONTENT_ROLES)
@station_module_required("coffee_enabled")
@require_http_methods(["GET", "POST"])
def coffee_pay(request):
    """Selbst abhaken: Bargeld in die Kasse gelegt oder überwiesen."""
    station = request.membership.station
    fund = logic.fund_for(station)
    status = logic.member_status(station, request.user)
    suggested = status.open_cents or fund.monthly_fee_cents or None
    chosen = _chosen_amount(request.GET.get("betrag"))
    if chosen:
        suggested = chosen
    form = CoffeePaymentForm(
        request.POST or None, methods=_payment_methods(station),
        initial={"amount_eur": f"{suggested / 100:.2f}" if suggested else None},
    )
    if request.method == "POST" and form.is_valid():
        method = form.cleaned_data["method"]
        note = form.cleaned_data["note"]
        reason = _("Selbst eingetragen: %(method)s") % {"method": CoffeeEntry.Method(method).label}
        if note:
            reason = f"{reason} – {note}"
        with transaction.atomic():
            entry = CoffeeEntry.objects.create(
                station=station, member=request.user, amount_cents=form.amount_cents(), reason=reason[:200],
                kind=CoffeeEntry.Kind.PAYMENT, method=method, created_by=request.user,
            )
            audit(request.user, station, "coffee.payment_reported", entry, {"fields": ["amount_cents", "method"]})
        messages.success(request, _("Danke! Deine Zahlung ist eingetragen."))
        return redirect("coffee")
    return render(request, "core/coffee_pay.html", {
        "form": form, "station": station, "fund": fund, "status": status,
        "quick_amounts": _quick_amounts(fund, status), "suggested": suggested,
    })


def _chosen_amount(raw) -> int:
    """Betrag aus den Schnellwahl-Links (?betrag=1500, in Cent)."""
    if raw and raw.isdigit() and 0 < int(raw) <= 50000:
        return int(raw)
    return 0


def _quick_amounts(fund, status) -> list:
    amounts = []
    if status.open_cents:
        amounts.append((status.open_cents, _("Alles Offene")))
    if fund.monthly_fee_cents:
        for months in (1, 3, 6, 12):
            cents = fund.monthly_fee_cents * months
            if cents != status.open_cents:
                amounts.append((cents, _("%(n)s Monat(e)") % {"n": months}))
    return [{"cents": cents, "euros": cents / 100, "label": label} for cents, label in amounts[:4]]


@membership_required(CASHIER)
@station_module_required("coffee_enabled")
def coffee_book(request):
    """Die Mappe: Monatsübersicht aller Teilnehmenden (nur Kassenwart)."""
    station = request.membership.station
    fund = logic.fund_for(station)
    logic.ensure_fees(station)
    current = logic.month_start(logic.station_today(station))
    statuses = logic.station_statuses(station)
    months = [logic.add_months(current, -offset) for offset in range(MONTHS_SHOWN - 1, -1, -1)]
    rows = []
    participants = logic.participants_query(station).select_related("user").order_by("user__first_name", "user__username")
    for participant in participants:
        status = statuses.get(participant.user_id) or logic.MemberStatus()
        cells = [status.months.get(m) or logic.MonthStatus(m, logic.NOT_CHARGED) for m in months]
        rows.append({"user": participant.user, "participant": participant, "status": status, "cells": cells})
    former_ids = logic.former_members_with_balance(station, statuses)
    others = [
        {"user": user, "status": statuses[user.pk]}
        for user in User.objects.filter(pk__in=[
            uid for uid, s in statuses.items()
            if s.balance_cents and uid not in {r["user"].pk for r in rows}
        ]).order_by("first_name", "username")
    ]
    return render(request, "core/coffee_book.html", {
        "fund": fund,
        "months": months,
        "rows": rows,
        "others": others,
        "former_ids": set(former_ids),
        "open_total_euros": (sum(r["status"].open_cents for r in rows) + sum(o["status"].open_cents for o in others)) / 100,
        "pots": logic.pots(station),
    })


@membership_required(CASHIER)
@station_module_required("coffee_enabled")
@require_POST
def coffee_cash_received(request, user_id):
    """Ein Tipp in der Mappe: ein Monatsbeitrag bar erhalten."""
    station = request.membership.station
    fund = logic.fund_for(station)
    participant = get_object_or_404(CoffeeParticipant, station=station, user_id=user_id)
    if not fund.monthly_fee_cents:
        raise Http404
    with transaction.atomic():
        entry = CoffeeEntry.objects.create(
            station=station, member=participant.user, amount_cents=fund.monthly_fee_cents,
            reason=_("Monatsbeitrag bar erhalten"), kind=CoffeeEntry.Kind.PAYMENT,
            method=CoffeeEntry.Method.CASH, created_by=request.user,
        )
        audit(request.user, station, "coffee.entry_created", entry, {"fields": ["member", "amount_cents", "method"]})
    messages.success(request, _("%(amount)s bar von %(person)s eingetragen.") % {
        "amount": logic.euro(fund.monthly_fee_cents), "person": _person(participant.user),
    })
    return redirect("coffee_book")


@membership_required(CASHIER)
@station_module_required("coffee_enabled")
@require_POST
def coffee_waive(request, user_id, period):
    """Monat befreien (Urlaub, Elternzeit, Krankheit) – gleicht genau diesen Beitrag aus."""
    station = request.membership.station
    try:
        month = dt.date.fromisoformat(period)
    except ValueError as exc:
        raise Http404 from exc
    fee = get_object_or_404(
        CoffeeEntry, station=station, member_id=user_id, kind=CoffeeEntry.Kind.FEE, period=month,
        correction_of__isnull=True,
    )
    reason = (request.POST.get("reason") or "").strip()[:150] or _("Befreit")
    try:
        with transaction.atomic():
            entry = CoffeeEntry.objects.create(
                station=station, member_id=user_id, amount_cents=-fee.amount_cents,
                reason=_("Befreiung %(month)s: %(reason)s") % {"month": logic.month_label(month), "reason": reason},
                kind=CoffeeEntry.Kind.WAIVER, period=month, created_by=request.user,
            )
            audit(request.user, station, "coffee.month_waived", entry, {"fields": ["period"]})
    except (IntegrityError, ValidationError):
        messages.error(request, _("Dieser Monat ist bereits befreit."))
        return redirect("coffee_book")
    messages.success(request, _("%(month)s ist befreit.") % {"month": logic.month_label(month)})
    return redirect("coffee_book")


@membership_required(CASHIER)
@station_module_required("coffee_enabled")
def coffee_ledger(request):
    """Alle Buchungen aller Personen (Kassenbuch, nur Kassenwart)."""
    station = request.membership.station
    entries = CoffeeEntry.objects.filter(station=station).select_related(
        "member", "created_by", "correction_of"
    ).prefetch_related("corrections")
    person = request.GET.get("person")
    if person and person.isdigit():
        entries = entries.filter(member_id=int(person))
    self_reported = request.GET.get("selbst") == "1"
    if self_reported:
        entries = [e for e in entries if e.created_by_id == e.member_id and e.kind == CoffeeEntry.Kind.PAYMENT]
    return render(request, "core/coffee_ledger.html", {
        "page_obj": _page(request, entries, 30),
        "self_reported": self_reported,
    })


@membership_required(CASHIER)
@station_module_required("coffee_enabled")
@require_http_methods(["GET", "POST"])
def coffee_create(request):
    station = request.membership.station
    form = CoffeeEntryForm(request.POST or None, station=station)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            entry = CoffeeEntry.objects.create(station=station, created_by=request.user, **form.entry_kwargs())
            audit(request.user, station, "coffee.entry_created", entry, {
                "fields": ["member", "amount_cents", "reason", "method"]
            })
        messages.success(request, _("Kassenbuchung wurde erfasst."))
        return redirect("coffee")
    return render(request, "core/coffee_form.html", {"form": form})


@membership_required(CASHIER)
@station_module_required("coffee_enabled")
@require_http_methods(["GET", "POST"])
def coffee_correct(request, pk):
    base_qs = CoffeeEntry.objects.select_related("member").filter(
        pk=pk,
        station=request.membership.station,
        correction_of__isnull=True,
    )
    original = get_object_or_404(base_qs)
    if original.corrections.exists():
        messages.error(request, _("Diese Buchung wurde bereits korrigiert."))
        return redirect("coffee")
    form = CoffeeCorrectionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                original = get_object_or_404(base_qs.select_for_update())
                if original.corrections.exists():
                    messages.error(request, _("Diese Buchung wurde bereits korrigiert."))
                    return redirect("coffee")
                correction = CoffeeEntry.objects.create(
                    station=original.station,
                    member=original.member,
                    amount_cents=-original.amount_cents,
                    reason=form.cleaned_data["reason"],
                    kind=original.kind,
                    method=original.method,
                    period=original.period,
                    created_by=request.user,
                    correction_of=original,
                )
                audit(request.user, original.station, "coffee.entry_corrected", correction, {
                    "fields": ["reason", "correction_of"]
                })
        except (IntegrityError, ValidationError):
            messages.error(request, _("Diese Buchung wurde bereits korrigiert."))
            return redirect("coffee")
        messages.success(request, _("Gegenbuchung wurde erfasst."))
        return redirect("coffee")
    return render(request, "core/coffee_correction.html", {
        "form": form,
        "original": original,
        "correction_euros": -original.amount_cents / 100,
    })


@membership_required(SETUP_ROLES)
@station_module_required("coffee_enabled")
@require_http_methods(["GET", "POST"])
def coffee_participants(request):
    station = request.membership.station
    current = logic.month_start(logic.station_today(station))
    month_choices = [(logic.add_months(current, offset), logic.month_label(logic.add_months(current, offset)))
                     for offset in (-2, -1, 0, 1, 2)]
    form = CoffeeParticipantForm(request.POST or None, station=station, months=month_choices,
                                 initial={"since": current.isoformat()})
    if request.method == "POST" and request.POST.get("action") == "add" and form.is_valid():
        participant = CoffeeParticipant.objects.create(
            station=station, user=form.cleaned_data["user"],
            since=dt.date.fromisoformat(form.cleaned_data["since"]), created_by=request.user,
        )
        audit(request.user, station, "coffee.participant_added", participant, {"fields": ["since"]})
        messages.success(request, _("%(person)s zahlt jetzt den Monatsbeitrag.") % {"person": _person(participant.user)})
        return redirect("coffee_participants")
    if request.method == "POST" and request.POST.get("action") in {"end", "resume"}:
        participant = get_object_or_404(CoffeeParticipant, station=station, pk=request.POST.get("participant"))
        if request.POST["action"] == "end":
            # Der laufende Monat wird noch berechnet; ab dem nächsten nicht mehr.
            participant.until = current
            message = _("%(person)s zahlt ab nächstem Monat keinen Beitrag mehr.")
        else:
            participant.until = None
            message = _("%(person)s zahlt wieder den Monatsbeitrag.")
        participant.save(update_fields=["until"])
        audit(request.user, station, "coffee.participant_changed", participant, {"fields": ["until"]})
        messages.success(request, message % {"person": _person(participant.user)})
        return redirect("coffee_participants")
    participants = CoffeeParticipant.objects.filter(station=station).select_related("user").order_by(
        "user__first_name", "user__username"
    )
    return render(request, "core/coffee_participants.html", {
        "form": form, "participants": participants, "current_month": current,
        "fund": logic.fund_for(station),
    })


@membership_required(SETUP_ROLES)
@station_module_required("coffee_enabled")
@require_http_methods(["GET", "POST"])
def coffee_settings(request):
    station = request.membership.station
    fund = CoffeeFund.objects.filter(station=station).first() or CoffeeFund(station=station)
    fund_form = CoffeeFundForm(request.POST or None, instance=fund, prefix="fund")
    ways_form = CoffeePaymentWaysForm(request.POST or None, instance=station, prefix="ways")
    if request.method == "POST" and fund_form.is_valid() and ways_form.is_valid():
        with transaction.atomic():
            fund = fund_form.save(commit=False)
            fund.updated_by = request.user
            fund.save()
            ways_form.save()
            audit(request.user, station, "coffee.settings_updated", fund, {
                "fields": sorted(set(fund_form.changed_data) | set(ways_form.changed_data)),
            })
        messages.success(request, _("Einstellungen der Kaffeekasse gespeichert."))
        return redirect("coffee")
    return render(request, "core/coffee_settings.html", {"fund_form": fund_form, "ways_form": ways_form})


@membership_required(CONTENT_ROLES)
@station_module_required("coffee_enabled")
def coffee_cash(request):
    """Kasse und Konto: Bestand und alle Bewegungen – für alle sichtbar."""
    station = request.membership.station
    movements = CoffeeCashMovement.objects.filter(station=station).select_related(
        "created_by", "witness", "correction_of"
    ).prefetch_related("corrections")
    return render(request, "core/coffee_cash.html", {
        "pots": logic.pots(station),
        "page_obj": _page(request, movements, 25),
        "last_count": logic.last_count(station),
        "is_cashier": _is_cashier(request),
    })


@membership_required(CONTENT_ROLES)
@station_module_required("coffee_enabled")
@require_http_methods(["GET", "POST"])
def coffee_purchase(request):
    station = request.membership.station
    form = CoffeePurchaseForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            movement = CoffeeCashMovement.objects.create(
                station=station, pot=form.cleaned_data["pot"], kind=CoffeeCashMovement.Kind.PURCHASE,
                amount_cents=-form.amount_cents(), reason=form.cleaned_data["what"], created_by=request.user,
            )
            audit(request.user, station, "coffee.purchase_recorded", movement, {"fields": ["amount_cents", "pot"]})
        messages.success(request, _("Einkauf eingetragen. Den Beleg bitte in die Kasse legen."))
        return redirect("coffee_cash")
    return render(request, "core/coffee_simple_form.html", {
        "form": form,
        "title": _("Einkauf eintragen"),
        "lead": _("Geld aus der Kasse oder vom Konto für Kaffee, Milch, Filter … Alle im Team sehen den Einkauf."),
        "submit": _("Einkauf eintragen"),
    })


@membership_required(CASHIER)
@station_module_required("coffee_enabled")
@require_http_methods(["GET", "POST"])
def coffee_movement(request):
    station = request.membership.station
    form = CoffeeMovementForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            movement = CoffeeCashMovement.objects.create(
                station=station, reason=form.cleaned_data["reason"], created_by=request.user,
                **form.movement_kwargs(),
            )
            audit(request.user, station, "coffee.movement_recorded", movement, {"fields": ["kind", "pot", "amount_cents"]})
        messages.success(request, _("Kassenbewegung eingetragen."))
        return redirect("coffee_cash")
    return render(request, "core/coffee_simple_form.html", {
        "form": form,
        "title": _("Kassenbewegung eintragen"),
        "lead": _("Bargeld aufs Konto bringen, Startbestand oder Spende eintragen."),
        "submit": _("Eintragen"),
    })


@membership_required(CASHIER)
@station_module_required("coffee_enabled")
@require_http_methods(["GET", "POST"])
def coffee_count(request):
    """Kassensturz: Bargeld zählen und mit dem Soll vergleichen."""
    station = request.membership.station
    expected = logic.pots(station).cash_cents
    form = CoffeeCountForm(request.POST or None, station=station, user=request.user)
    if request.method == "POST" and form.is_valid():
        counted = form.counted_cents()
        difference = counted - expected
        note = form.cleaned_data["note"]
        reason = _("Kassensturz") + (f": {note}" if note else "")
        with transaction.atomic():
            movement = CoffeeCashMovement.objects.create(
                station=station, pot=CoffeeCashMovement.Pot.CASH, kind=CoffeeCashMovement.Kind.COUNT,
                amount_cents=difference, counted_cents=counted, expected_cents=expected,
                witness=form.cleaned_data["witness"], reason=reason[:200], created_by=request.user,
            )
            audit(request.user, station, "coffee.cash_counted", movement, {
                "fields": ["counted_cents", "expected_cents"], "difference_cents": difference,
            })
        if difference:
            messages.warning(request, _("Kassensturz gespeichert. Differenz: %(diff)s") % {"diff": logic.euro(difference)})
        else:
            messages.success(request, _("Kassensturz gespeichert: Die Kasse stimmt."))
        return redirect("coffee_cash")
    return render(request, "core/coffee_simple_form.html", {
        "form": form,
        "title": _("Kassensturz"),
        "lead": _("Laut Buchungen sollten %(amount)s in der Kasse sein. Bitte zählen und den Betrag eintragen; eine Differenz wird als eigene Buchung festgehalten.") % {
            "amount": logic.euro(expected)},
        "submit": _("Kassensturz speichern"),
    })


@membership_required(CASHIER)
@station_module_required("coffee_enabled")
@require_http_methods(["GET", "POST"])
def coffee_movement_correct(request, pk):
    station = request.membership.station
    original = get_object_or_404(CoffeeCashMovement, pk=pk, station=station, correction_of__isnull=True)
    if original.corrections.exists() or not original.amount_cents:
        messages.error(request, _("Diese Bewegung kann nicht (mehr) korrigiert werden."))
        return redirect("coffee_cash")
    form = CoffeeCorrectionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                correction = CoffeeCashMovement.objects.create(
                    station=station, pot=original.pot, kind=original.kind, amount_cents=-original.amount_cents,
                    reason=form.cleaned_data["reason"], created_by=request.user, correction_of=original,
                )
                audit(request.user, station, "coffee.movement_corrected", correction, {"fields": ["correction_of"]})
        except (IntegrityError, ValidationError):
            messages.error(request, _("Diese Bewegung wurde bereits korrigiert."))
            return redirect("coffee_cash")
        messages.success(request, _("Gegenbuchung wurde erfasst."))
        return redirect("coffee_cash")
    return render(request, "core/coffee_simple_form.html", {
        "form": form,
        "title": _("Kassenbewegung korrigieren"),
        "lead": _("%(what)s über %(amount)s wird durch eine Gegenbuchung ausgeglichen; das Original bleibt sichtbar.") % {
            "what": original.get_kind_display(), "amount": logic.euro(original.amount_cents)},
        "submit": _("Gegenbuchung erfassen"),
    })


def _csv_cell(value) -> str:
    text = str(value)
    # Tabellenprogramme führen Zellen mit = + - @ als Formel aus.
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@membership_required(CASHIER)
@station_module_required("coffee_enabled")
def coffee_export(request):
    station = request.membership.station
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="kaffeekasse.csv"'
    response.write("﻿")
    writer = csv.writer(response, delimiter=";")
    writer.writerow([_("Datum"), _("Bereich"), _("Person"), _("Art"), _("Zahlungsweg/Topf"), _("Monat"),
                     _("Betrag EUR"), _("Grund"), _("Erfasst von")])
    for entry in CoffeeEntry.objects.filter(station=station).select_related("member", "created_by").order_by("created_at"):
        writer.writerow([
            entry.created_at.strftime("%Y-%m-%d %H:%M"), _("Person"), _csv_cell(_person(entry.member)),
            entry.get_kind_display(), entry.get_method_display() if entry.method else "",
            entry.period.strftime("%Y-%m") if entry.period else "", f"{entry.amount_cents / 100:.2f}".replace(".", ","),
            _csv_cell(entry.reason), _csv_cell(_person(entry.created_by)) if entry.created_by else _("automatisch"),
        ])
    for movement in CoffeeCashMovement.objects.filter(station=station).select_related("created_by").order_by("created_at"):
        writer.writerow([
            movement.created_at.strftime("%Y-%m-%d %H:%M"), _("Kasse"), "", movement.get_kind_display(),
            movement.get_pot_display(), "", f"{movement.amount_cents / 100:.2f}".replace(".", ","),
            _csv_cell(movement.reason), _csv_cell(_person(movement.created_by)),
        ])
    audit(request.user, station, "coffee.exported", station, {"fields": ["entries", "movements"]})
    return response

