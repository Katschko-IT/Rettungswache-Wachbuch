"""Wachenterminal: Ruhebildschirm, PIN-Anmeldung, Kachelmenü und Verwaltung."""
from __future__ import annotations

import io
import secrets
from urllib.parse import urlencode, urlparse

import qrcode
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.hashers import check_password
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import rate_limit
from .access import get_membership, membership_required
from .display import display_payload
from .models import Membership
from .services import audit
from .terminal import (
    COOKIE_NAME,
    SESSION_LAST_SEEN,
    SESSION_TERMINAL,
    TERMINAL_FAILURES_PER_10_MIN,
    create_pairing,
    end_terminal_session,
    generate_pin,
    hash_secret,
    idle_seconds,
    is_pin_session,
    local_cert_fingerprint,
    pin_locked,
    pin_problem,
    set_pin,
    terminal_enabled,
    terminal_for_request,
    verify_pin,
)
from .terminal_models import StationTerminal, TerminalPin

ADMIN_ROLES = {Membership.Role.ADMIN}
PIN_MANAGER_ROLES = {Membership.Role.ADMIN, Membership.Role.SHIFT_LEAD}


def _require_enabled():
    if not terminal_enabled():
        raise Http404


def _terminal_or_403(request):
    _require_enabled()
    terminal = terminal_for_request(request)
    if terminal is None:
        return None, HttpResponse(
            "Dieses Gerät ist nicht als Wachenterminal registriert.",
            status=403,
            content_type="text/plain; charset=utf-8",
        )
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


# ---- Gerät registrieren ----------------------------------------------------


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
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=60 * 60 * 24 * 365 * 5,
        path="/",
        httponly=True,
        samesite="Strict",
        secure=request.is_secure(),
    )
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
            raw = secrets.token_urlsafe(32)
            terminal = StationTerminal.objects.create(
                station=station,
                label=(request.POST.get("label") or "Wachenterminal").strip()[:80],
                token_hash=hash_secret(raw),
                created_by=request.user,
            )
            audit(request.user, station, "terminal.created", terminal, {"label": terminal.label})
            request.session["terminal_new_url"] = request.build_absolute_uri(reverse("terminal_start", args=[raw]))
        elif action == "revoke":
            terminal = get_object_or_404(StationTerminal, pk=request.POST.get("terminal_id"), station=station)
            if terminal.revoked_at is None:
                terminal.revoked_at = timezone.now()
                terminal.save(update_fields=["revoked_at"])
                audit(request.user, station, "terminal.revoked", terminal, {})
            messages.success(request, "Terminal widerrufen.")
        return redirect("terminal_admin")
    members = (
        Membership.objects.filter(station=station, is_active=True, user__is_active=True)
        .select_related("user", "terminal_pin")
        .order_by("user__last_name", "user__first_name", "user__username")
    )
    return render(
        request,
        "core/terminal_admin.html",
        {
            "terminals": StationTerminal.objects.filter(station=station).select_related("created_by"),
            "new_url": request.session.pop("terminal_new_url", ""),
            "new_pin": request.session.pop("terminal_new_pin", None),
            "members": members,
            "idle_seconds": idle_seconds(),
            "cert_fingerprint": local_cert_fingerprint(),
        },
    )


@membership_required(PIN_MANAGER_ROLES)
@require_POST
def terminal_pin_issue(request, membership_id: int):
    """Vergibt eine zufällige Start-PIN (einmalig angezeigt) oder entfernt sie."""
    _require_enabled()
    station = request.membership.station
    member = get_object_or_404(Membership, pk=membership_id, station=station, is_active=True)
    if request.membership.role != Membership.Role.ADMIN and member.role == Membership.Role.ADMIN:
        messages.error(request, "Die PIN von Admins vergeben nur Admins.")
        return redirect("terminal_admin" if request.membership.role == Membership.Role.ADMIN else "team")
    if request.POST.get("action") == "remove":
        TerminalPin.objects.filter(membership=member).delete()
        audit(request.user, station, "terminal.pin_removed", member, {})
        messages.success(request, "Terminal-PIN entfernt.")
    else:
        pin = generate_pin()
        set_pin(member, pin, set_by=request.user, must_change=True)
        audit(request.user, station, "terminal.pin_issued", member, {})
        name = member.user.get_full_name() or member.user.username
        request.session["terminal_new_pin"] = {"name": name, "pin": pin}
    target = request.POST.get("next") or ""
    if target == "team":
        return redirect("team")
    return redirect("terminal_admin")


# ---- Ruhebildschirm und Anmeldung -----------------------------------------


@require_GET
@never_cache
def terminal_home(request):
    terminal, error = _terminal_or_403(request)
    if error:
        return error
    if request.user.is_authenticated and is_pin_session(request):
        return redirect("terminal_menu")
    return render(
        request,
        "core/terminal_home.html",
        {"terminal": terminal, "display_station": terminal.station},
    )


@require_GET
@never_cache
def terminal_data(request):
    terminal, error = _terminal_or_403(request)
    if error:
        return JsonResponse({"detail": "kein Zugang"}, status=403)
    from .display_models import DEFAULT_DISPLAY_CONFIG

    payload = display_payload(terminal.station)
    payload["layout_config"] = DEFAULT_DISPLAY_CONFIG
    return JsonResponse(payload)


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
def terminal_people(request):
    terminal, error = _terminal_or_403(request)
    if error:
        return error
    members = (
        Membership.objects.filter(
            station=terminal.station,
            is_active=True,
            user__is_active=True,
            terminal_pin__isnull=False,
        )
        .select_related("user")
        .order_by("user__first_name", "user__last_name", "user__username")
    )
    return render(request, "core/terminal_people.html", {"terminal": terminal, "members": members})


@require_http_methods(["GET", "POST"])
@never_cache
def terminal_pin_login(request, membership_id: int):
    terminal, error = _terminal_or_403(request)
    if error:
        return error
    member = get_object_or_404(
        Membership.objects.select_related("user", "terminal_pin"),
        pk=membership_id,
        station=terminal.station,
        is_active=True,
        user__is_active=True,
        terminal_pin__isnull=False,
    )
    record = member.terminal_pin
    error_text = ""
    if request.method == "POST":
        allowed = rate_limit.consume(
            "terminal_pin", f"terminal:{terminal.pk}", limit=TERMINAL_FAILURES_PER_10_MIN, window_seconds=600
        )
        if not allowed:
            error_text = "Zu viele Versuche an diesem Terminal. Bitte einige Minuten warten."
        elif pin_locked(record):
            error_text = "PIN vorübergehend gesperrt. Bitte später erneut versuchen oder die Wachleitung fragen."
        elif verify_pin(record, request.POST.get("pin", "")):
            if request.user.is_authenticated:
                logout(request)
            login(request, member.user, backend="django.contrib.auth.backends.ModelBackend")
            request.session[SESSION_TERMINAL] = terminal.pk
            request.session[SESSION_LAST_SEEN] = timezone.now().timestamp()
            request.session.set_expiry(idle_seconds() + 60)
            StationTerminal.objects.filter(pk=terminal.pk).update(last_used_at=timezone.now())
            audit(member.user, terminal.station, "terminal.login", terminal, {})
            if record.must_change:
                return redirect("terminal_pin_change")
            return redirect("terminal_menu")
        else:
            audit(member.user, terminal.station, "terminal.login_failed", terminal, {})
            error_text = (
                "PIN falsch. Nach mehreren Fehlversuchen wird die PIN gesperrt."
                if not pin_locked(record)
                else "PIN falsch. Die PIN ist jetzt vorübergehend gesperrt."
            )
    return render(
        request,
        "core/terminal_pin.html",
        {"terminal": terminal, "member": member, "error_text": error_text, "pin_length": 6},
        status=400 if error_text else 200,
    )


@require_POST
def terminal_logout(request):
    _require_enabled()
    return end_terminal_session(request)


# ---- Nach der Anmeldung ----------------------------------------------------


def _pin_session_membership(request):
    terminal = terminal_for_request(request)
    if terminal is None or not request.user.is_authenticated:
        return None, None
    membership = get_membership(request.user)
    if membership is None or membership.station_id != terminal.station_id:
        return terminal, None
    return terminal, membership


@require_GET
@never_cache
def terminal_menu(request):
    _require_enabled()
    terminal, membership = _pin_session_membership(request)
    if terminal is None:
        return redirect("login")
    if membership is None:
        return end_terminal_session(request)
    return render(
        request,
        "core/terminal_menu.html",
        {"terminal": terminal, "station": membership.station},
    )


@require_http_methods(["GET", "POST"])
@never_cache
def terminal_pin_change(request):
    """Eigene PIN festlegen – am Terminal oder im normalen Konto."""
    _require_enabled()
    if not request.user.is_authenticated:
        return redirect(f"{reverse('login')}?next={reverse('terminal_pin_change')}")
    membership = get_membership(request.user)
    if membership is None:
        return redirect("access")
    record = TerminalPin.objects.filter(membership=membership).first()
    needs_current = record is not None and not record.must_change and not is_pin_session(request)
    error_text = ""
    if request.method == "POST":
        new_pin = request.POST.get("new_pin", "")
        if needs_current and not check_password(request.POST.get("current_pin", ""), record.pin_hash):
            error_text = "Die bisherige PIN stimmt nicht."
        elif new_pin != request.POST.get("new_pin_repeat", ""):
            error_text = "Die beiden PIN-Eingaben stimmen nicht überein."
        elif problem := pin_problem(new_pin):
            error_text = problem
        else:
            set_pin(membership, new_pin, set_by=request.user, must_change=False)
            audit(request.user, membership.station, "terminal.pin_changed", membership, {})
            messages.success(request, "Deine Terminal-PIN ist gespeichert.")
            return redirect("terminal_menu" if is_pin_session(request) else "account_home")
    return render(
        request,
        "core/terminal_pin_change.html",
        {
            "error_text": error_text,
            "needs_current": needs_current,
            "forced": bool(record and record.must_change),
            "pin_session": is_pin_session(request),
        },
        status=400 if error_text else 200,
    )


@require_http_methods(["GET", "POST"])
@never_cache
def terminal_pair(request):
    """Handy koppeln: einmaliger QR mit Kopplungscode (120 s gültig)."""
    _require_enabled()
    if not request.user.is_authenticated:
        return redirect(f"{reverse('login')}?next={reverse('terminal_pair')}")
    membership = get_membership(request.user)
    if membership is None:
        return redirect("access")
    if request.method == "POST":
        raw = create_pairing(membership)
        request.session["terminal_pair_link"] = connect_link(request, pair=raw)
        audit(request.user, membership.station, "terminal.pairing_created", membership, {})
        return redirect("terminal_pair")
    link = request.session.get("terminal_pair_link", "")
    return render(
        request,
        "core/terminal_pair.html",
        {"has_code": bool(link), "pin_session": is_pin_session(request)},
    )


@require_GET
@never_cache
def terminal_pair_qr(request):
    _require_enabled()
    if not request.user.is_authenticated:
        raise Http404
    link = request.session.pop("terminal_pair_link", "")
    if not link:
        raise Http404
    return _qr_png(link)
