"""Wachenterminal: Sperrbildschirm, Wachen-Code, Alltagsmodus und Verwaltung."""
from __future__ import annotations

import io
from datetime import timedelta
from urllib.parse import urlencode, urlparse

import qrcode
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import rate_limit
from .access import get_membership, membership_required
from .display import display_payload
from .lockscreen import background_for
from .models import HandoverEntry, Membership
from .services import audit
from .setup_wizard import setup_pending
from .task_board import day_board, month_tasks, week_board
from .terminal import (
    SESSION_LAST_SEEN,
    SESSION_TERMINAL,
    code_problem,
    create_pairing,
    create_terminal_device,
    end_terminal_session,
    generate_code,
    hash_secret,
    idle_seconds,
    is_open_mode,
    is_service_user,
    local_cert_fingerprint,
    set_station_code,
    set_terminal_cookie,
    terminal_enabled,
    terminal_for_request,
    terminal_locked,
    verify_code,
    wifi_qr_payload,
)
from .terminal_models import StationTerminal, StationTerminalCode

ADMIN_ROLES = {Membership.Role.ADMIN}


def _require_enabled():
    if not terminal_enabled():
        raise Http404


def _terminal_or_403(request):
    _require_enabled()
    terminal = terminal_for_request(request)
    if terminal is None:
        if setup_pending():
            # Erster Start des Kiosks: Die Wache gibt es noch nicht, also führt
            # der Bildschirm direkt in die Ersteinrichtung.
            return None, redirect("setup_wizard")
        return None, render(request, "core/terminal_unregistered.html", status=403)
    return terminal, None


def server_origin(request) -> str:
    configured = (getattr(settings, "SITE_URL", "") or "").strip().rstrip("/")
    parsed = urlparse(configured)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return configured
    return request.build_absolute_uri("/").rstrip("/")


def connect_link(request, *, pair: str = "") -> str:
    """App-Link für den Verbindungs-QR: Server, optional Zertifikat und Kopplungscode."""
    params = {"url": server_origin(request)}
    fingerprint = local_cert_fingerprint()
    if fingerprint:
        params["pin"] = f"sha256/{fingerprint}"
    if pair:
        params["pair"] = pair
    return "wachbuch://connect?" + urlencode(params)


def _qr_png(payload: str) -> HttpResponse:
    image = qrcode.make(payload, box_size=8, border=2)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    response = HttpResponse(buffer.getvalue(), content_type="image/png")
    response["Cache-Control"] = "no-store"
    return response


# ---- Gerät registrieren und verwalten --------------------------------------


@require_GET
def terminal_start(request, token: str):
    """Setzt das Gerätegeheimnis als Cookie; der Link gilt bis zum Widerruf."""
    _require_enabled()
    ip = request.META.get("REMOTE_ADDR", "")
    if not rate_limit.consume("terminal_start", ip, limit=10, window_seconds=60):
        return HttpResponse("Zu viele Versuche.", status=429, content_type="text/plain")
    terminal = StationTerminal.objects.select_related("station").filter(token_hash=hash_secret(token)).first()
    if terminal is None or not terminal.is_active:
        return HttpResponse(
            "Dieser Terminal-Link ist ungültig oder wurde widerrufen.",
            status=403,
            content_type="text/plain; charset=utf-8",
        )
    if request.user.is_authenticated:
        logout(request)
    StationTerminal.objects.filter(pk=terminal.pk).update(last_used_at=timezone.now())
    response = redirect("terminal_home")
    set_terminal_cookie(response, request, token)
    response["Referrer-Policy"] = "no-referrer"
    return response


@membership_required(ADMIN_ROLES)
@require_http_methods(["GET", "POST"])
def terminal_admin(request):
    _require_enabled()
    station = request.membership.station
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create":
            terminal, raw = create_terminal_device(
                station, label=request.POST.get("label") or "", created_by=request.user
            )
            audit(request.user, station, "terminal.created", terminal, {"fields": ["label"]})
            request.session["terminal_new_url"] = request.build_absolute_uri(reverse("terminal_start", args=[raw]))
        elif action == "create-here":
            # Dieser Browser (z. B. der Touch-Bildschirm des Pi) wird selbst zum
            # Terminal. Wie beim Start-Link endet die persönliche Anmeldung.
            terminal, raw = create_terminal_device(
                station, label=request.POST.get("label") or "", created_by=request.user
            )
            audit(request.user, station, "terminal.created", terminal, {"fields": ["label"], "via": "this-device"})
            logout(request)
            response = redirect("terminal_home")
            set_terminal_cookie(response, request, raw)
            return response
        elif action in {"revoke", "unlock"}:
            terminal = get_object_or_404(StationTerminal, pk=request.POST.get("terminal_id"), station=station)
            if action == "revoke" and terminal.revoked_at is None:
                terminal.revoked_at = timezone.now()
                terminal.save(update_fields=["revoked_at"])
                audit(request.user, station, "terminal.revoked", terminal, {})
                messages.success(request, "Terminal widerrufen.")
            elif action == "unlock":
                StationTerminal.objects.filter(pk=terminal.pk).update(failed_attempts=0, locked_until=None)
                audit(request.user, station, "terminal.unlocked", terminal, {})
                messages.success(request, "Sperre aufgehoben.")
        elif action == "set-code":
            code = request.POST.get("code", "")
            if code != request.POST.get("code_repeat", ""):
                messages.error(request, "Die beiden Eingaben stimmen nicht überein.")
            elif problem := code_problem(code):
                messages.error(request, problem)
            else:
                set_station_code(station, code, set_by=request.user)
                audit(request.user, station, "terminal.code_changed", station, {})
                messages.success(request, "Wachen-Code gespeichert.")
        elif action == "generate-code":
            code = generate_code()
            set_station_code(station, code, set_by=request.user)
            audit(request.user, station, "terminal.code_changed", station, {"generated": True})
            request.session["terminal_new_code"] = code
        elif action == "pair-member":
            member = get_object_or_404(
                Membership.objects.select_related("user"),
                pk=request.POST.get("membership_id"),
                station=station,
                is_active=True,
                user__is_active=True,
            )
            if is_service_user(member.user):
                raise Http404
            from .mfa import mfa_required, user_has_confirmed_mfa

            # Fremdkopplung darf keinen zweiten Faktor umgehen: Wer MFA nutzt
            # oder nutzen muss, koppelt sein Handy aus der eigenen Sitzung.
            if member.user_id != request.user.pk and (mfa_required() or user_has_confirmed_mfa(member.user)):
                messages.error(
                    request,
                    "Diese Person nutzt die Zwei-Faktor-Anmeldung und koppelt ihr Handy "
                    "selbst unter „Handy koppeln“.",
                )
                return redirect("terminal_admin")
            request.session["terminal_pair_link"] = connect_link(request, pair=create_pairing(member))
            request.session["terminal_pair_name"] = member.user.get_full_name() or member.user.username
            audit(request.user, station, "terminal.pairing_created", member, {"by_admin": True})
        return redirect("terminal_admin")
    code_record = StationTerminalCode.objects.filter(station=station).select_related("set_by").first()
    service_user_id = code_record.service_user_id if code_record else None
    members = (
        Membership.objects.filter(station=station, is_active=True, user__is_active=True)
        .exclude(user_id=service_user_id)
        .select_related("user")
        .order_by("user__last_name", "user__first_name", "user__username")
    )
    pair_name = request.session.pop("terminal_pair_name", "")
    return render(
        request,
        "core/terminal_admin.html",
        {
            "terminals": StationTerminal.objects.filter(station=station).select_related("created_by"),
            "now": timezone.now(),
            "new_url": request.session.pop("terminal_new_url", ""),
            "new_code": request.session.pop("terminal_new_code", ""),
            "code_record": code_record,
            "pair_name": pair_name,
            "members": members,
            "idle_seconds": idle_seconds(),
            "cert_fingerprint": local_cert_fingerprint(),
            "this_device": terminal_for_request(request),
        },
    )


# ---- Sperrbildschirm -------------------------------------------------------


@require_http_methods(["GET", "POST"])
@never_cache
def terminal_home(request):
    """Sperrbildschirm: Wachen-Display, Antippen öffnet den Ziffernblock."""
    terminal, error = _terminal_or_403(request)
    if error:
        return error
    if request.user.is_authenticated and is_open_mode(request):
        return redirect("terminal_menu")
    error_text = ""
    status = 200
    if request.method == "POST":
        code_set = StationTerminalCode.objects.filter(station=terminal.station).select_related("service_user").first()
        if terminal_locked(terminal):
            error_text = "Zu viele Fehlversuche. Gesperrt bis {}.".format(
                timezone.localtime(terminal.locked_until).strftime("%H:%M")
            )
        elif code_set is None:
            error_text = "Noch kein Wachen-Code festgelegt. Ein Admin legt ihn unter Team → Wachenterminal fest."
        elif verify_code(terminal, request.POST.get("code", "")):
            if request.user.is_authenticated:
                logout(request)
            login(request, code_set.service_user, backend="django.contrib.auth.backends.ModelBackend")
            request.session[SESSION_TERMINAL] = terminal.pk
            request.session[SESSION_LAST_SEEN] = timezone.now().timestamp()
            request.session.set_expiry(idle_seconds() + 60)
            StationTerminal.objects.filter(pk=terminal.pk).update(last_used_at=timezone.now())
            audit(code_set.service_user, terminal.station, "terminal.unlocked_by_code", terminal, {})
            return redirect("terminal_menu")
        else:
            audit(None, terminal.station, "terminal.code_failed", terminal, {"failures": terminal.failed_attempts})
            if terminal_locked(terminal):
                error_text = "Zu viele Fehlversuche. Gesperrt bis {}.".format(
                    timezone.localtime(terminal.locked_until).strftime("%H:%M")
                )
            else:
                error_text = "Falscher Code."
        status = 400
    return render(
        request,
        "core/terminal_home.html",
        {
            "terminal": terminal,
            "data": _lock_screen_data(terminal.station),
            "background": background_for(timezone.localdate()),
            "error_text": error_text,
            "wifi_ssid": settings.TERMINAL_WIFI_SSID if wifi_qr_payload() else "",
        },
        status=status,
    )


def _lock_screen_data(station) -> dict:
    """Daten für Sperrbildschirm und /terminal/daten/ (nur Zählwerte und Titel)."""
    payload = display_payload(station)
    for vehicle in payload.get("fleet_vehicles", []):
        # „Status 1: Einsatzbereit auf Wache“ → „Status 1“ für die Statuszeile.
        vehicle["status_short"] = vehicle.get("status_label", "").split(":")[0]
    payload["open_handovers"] = (
        HandoverEntry.objects.filter(station=station).exclude(status=HandoverEntry.Status.DONE).count()
    )
    return payload


@require_GET
@never_cache
def terminal_data(request):
    terminal, error = _terminal_or_403(request)
    if error:
        return JsonResponse({"detail": "kein Zugang"}, status=403)
    return JsonResponse(_lock_screen_data(terminal.station))


@require_GET
@never_cache
def terminal_connect_qr(request):
    """Öffentlicher Verbindungs-QR (nur Serveradresse und Zertifikat, kein Zugang)."""
    terminal, error = _terminal_or_403(request)
    if error:
        return error
    return _qr_png(connect_link(request))


@require_GET
@never_cache
def terminal_wifi_qr(request):
    """WLAN-QR der Wache; nur auf registrierten Terminals (enthält das WLAN-Passwort)."""
    terminal, error = _terminal_or_403(request)
    if error:
        return error
    payload = wifi_qr_payload()
    if not payload:
        raise Http404
    return _qr_png(payload)


@require_POST
def terminal_logout(request):
    _require_enabled()
    return end_terminal_session(request)


# ---- Alltagsmodus ----------------------------------------------------------


@require_GET
@never_cache
def terminal_menu(request):
    """Startseite nach dem Entsperren: alles für den Tagesablauf auf einen Blick."""
    _require_enabled()
    terminal = terminal_for_request(request)
    if terminal is None or not request.user.is_authenticated:
        return redirect("terminal_home" if terminal else "login")
    membership = get_membership(request.user)
    if membership is None or membership.station_id != terminal.station_id:
        return end_terminal_session(request)
    station = membership.station
    payload = display_payload(station)
    today = timezone.localdate()
    context = {
        "terminal": terminal,
        "station": station,
        "today": today,
        "weather": payload["weather"],
        "events": payload["events"],
        "waste": _upcoming_waste(station, today),
        "handovers": _open_handovers(station),
        "urgent_handovers": payload["urgent_handovers"],
    }
    if station.tasks_enabled:
        board = day_board(station, today)
        week = week_board(station, today)
        context.update({
            "day_board": board,
            "week_columns": week["columns"],
            "week_label": week["week_label"],
            "month_items": month_tasks(station, today),
        })
    return render(request, "core/terminal_menu.html", context)


def _open_handovers(station, limit: int = 6):
    """Offene Übergaben: dringend zuerst, sonst die neuesten."""
    rank = {HandoverEntry.Priority.URGENT: 0, HandoverEntry.Priority.IMPORTANT: 1}
    items = list(
        HandoverEntry.objects.filter(station=station)
        .exclude(status=HandoverEntry.Status.DONE)
        .order_by("-created_at")[:40]
    )
    items.sort(key=lambda item: rank.get(item.priority, 2))
    return items[:limit]


def _upcoming_waste(station, today, days: int = 7):
    if not station.waste_calendar_enabled:
        return None
    from datetime import datetime

    from .models import WasteCollection

    tz = timezone.get_current_timezone()
    start = datetime.combine(today, datetime.min.time(), tzinfo=tz)
    return list(
        WasteCollection.objects.filter(
            station=station, starts_at__gte=start, starts_at__lt=start + timedelta(days=days)
        ).order_by("starts_at")[:6]
    )


# ---- Handy koppeln (persönliches Konto, nicht am Terminal) ----------------


@require_http_methods(["GET", "POST"])
@never_cache
def terminal_pair(request):
    """Handy koppeln: einmaliger QR mit Kopplungscode (120 s gültig)."""
    _require_enabled()
    if not request.user.is_authenticated:
        return redirect(f"{reverse('login')}?next={reverse('terminal_pair')}")
    membership = get_membership(request.user)
    if membership is None or is_service_user(request.user):
        return redirect("access")
    if request.method == "POST":
        raw = create_pairing(membership)
        request.session["terminal_pair_link"] = connect_link(request, pair=raw)
        audit(request.user, membership.station, "terminal.pairing_created", membership, {})
        return redirect("terminal_pair")
    return render(request, "core/terminal_pair.html", {"has_code": bool(request.session.get("terminal_pair_link"))})


@require_GET
@never_cache
def terminal_pair_qr(request):
    _require_enabled()
    if not request.user.is_authenticated or is_open_mode(request):
        raise Http404
    link = request.session.pop("terminal_pair_link", "")
    if not link:
        raise Http404
    return _qr_png(link)
