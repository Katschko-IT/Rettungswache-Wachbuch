"""Views and HTTP endpoints for QR-Code login."""

from __future__ import annotations

import json
from functools import wraps
from urllib.parse import urlencode, urlparse

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.contrib.auth.views import LogoutView
from django.db.models import F
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from webauthn.helpers import bytes_to_base64url

from .access import get_membership
from .auth_session import get_auth_method, get_auth_time
from .mfa import mfa_enabled, mfa_required, user_has_confirmed_mfa, user_has_passkey, user_has_totp
from .models import Membership, QrLoginRequest, Station
from .qr_login import (
    approve_qr_request,
    get_approval_freshness,
    check_qr_rate_limit,
    create_qr_login_request,
    deny_qr_request,
    exchange_qr_request,
    get_canonical_origin,
    get_external_state,
    hash_manual_code,
    is_qr_login_enabled,
    mark_scanned_if_created,
    revoke_open_requests_for_user,
    verify_browser_session,
    verify_possession,
    verify_secret,
)
from .services import audit
from .webauthn_auth import authentication_options, verify_authentication, webauthn_enabled


def qr_response_headers(response: HttpResponse) -> HttpResponse:
    """Set mandatory security headers on all QR login responses."""
    response["Cache-Control"] = "no-store"
    response["Pragma"] = "no-cache"
    if not response.has_header("Referrer-Policy"):
        response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex"
    return response


def qr_form_page_headers(response: HttpResponse) -> HttpResponse:
    """Security-Header fuer QR-HTML-Seiten mit echten Formularen.

    same-origin sendet keinen Referer an fremde Origins; das Secret steht
    ohnehin nur im URL-Fragment. Der Wechsel ist noetig, weil der Browser
    sonst Origin: null sendet und Django CSRF blockt.
    """
    qr_response_headers(response)
    response["Referrer-Policy"] = "same-origin"
    return response


def qr_endpoint(view_func):
    """Decorator ensuring security headers and feature gate check."""
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        resp = view_func(request, *args, **kwargs)
        return qr_response_headers(resp)

    return wrapped


def qr_error(code: str, status: int) -> JsonResponse:
    resp = JsonResponse({"ok": False, "error": code}, status=status)
    return qr_response_headers(resp)


def get_client_ip(request: HttpRequest) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff and getattr(settings, "TRUSTED_PROXY", False):
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "127.0.0.1")


def _json_body(request: HttpRequest) -> dict:
    try:
        return json.loads(request.body.decode("utf-8"))
    except Exception:
        return {}


def _get_request_secret(request: HttpRequest) -> str:
    secret = request.headers.get("X-QR-Secret", "").strip()
    if secret:
        return secret
    if request.POST:
        return request.POST.get("qr_secret", "").strip()
    if request.content_type == "application/json":
        body = _json_body(request)
        return str(body.get("qr_secret", "")).strip()
    return ""


@qr_endpoint
@require_GET
def qr_login_wait(request: HttpRequest, login_id: str | None = None) -> HttpResponse:
    """Warteseite fuer den initiierenden Browser."""
    if not is_qr_login_enabled(request):
        raise Http404

    context = {
        "login_id": str(login_id) if login_id else "",
        "app_name": getattr(settings, "APP_NAME", "Wachbuch"),
    }
    return render(request, "registration/qr_wait.html", context)


@qr_endpoint
@require_POST
def qr_login_start(request: HttpRequest) -> JsonResponse:
    """Startet eine neue QR-Login-Transaktion."""
    if not is_qr_login_enabled(request):
        return qr_error("qr_disabled", 503)

    ip = get_client_ip(request)
    if not check_qr_rate_limit("qr_start", f"ip:{ip}"):
        return qr_error("qr_rate_limited", 429)

    station_slug = request.POST.get("station") or request.GET.get("station")
    station = None
    if station_slug:
        station = Station.objects.filter(slug=station_slug, is_active=True).first()
        if not station:
            return qr_error("qr_invalid", 400)
    else:
        station = Station.get_default()

    try:
        qr_req, secret, manual_code, check_word, qr_url, qr_image = create_qr_login_request(
            request, station=station
        )
    except ValueError:
        return qr_error("qr_disabled", 503)

    ttl = getattr(settings, "QR_LOGIN_TTL_SECONDS", 120)
    data = {
        "ok": True,
        "login_id": str(qr_req.id),
        "qr_url": qr_url,
        "qr_image": qr_image,
        "check_word": check_word,
        "manual_code": manual_code,
        "expires_in": ttl,
    }
    return JsonResponse(data)


@qr_endpoint
@require_POST
def qr_login_status(request: HttpRequest, login_id: str) -> JsonResponse:
    """Liefert den Live-Status der QR-Transaktion fuer die wartende Browser-Session."""
    if not is_qr_login_enabled(request):
        return qr_error("qr_disabled", 503)

    qr_req = QrLoginRequest.objects.filter(pk=login_id).first()
    if not qr_req:
        return qr_error("qr_invalid", 404)

    session_key = request.session.session_key or ""
    if not check_qr_rate_limit("qr_status", f"{session_key}:{login_id}"):
        return qr_error("qr_rate_limited", 429)

    if not verify_browser_session(request, qr_req):
        return qr_error("qr_forbidden", 403)

    secret = _get_request_secret(request)
    if not secret or not verify_secret(qr_req, secret):
        return qr_error("qr_forbidden", 403)

    state = get_external_state(qr_req)
    return JsonResponse({"ok": True, "state": state})


@qr_endpoint
@require_http_methods(["GET", "POST"])
def qr_login_manual(request: HttpRequest) -> HttpResponse:
    """Manueller Ersatz fuer den Kamera-Scan: 10-stelligen Code eingeben.

    Der Code wird serverseitig gehasht nachgeschlagen, ist an die aktive Wache
    gebunden und nur fuer nicht-terminale, nicht abgelaufene Requests gueltig.
    Nach erfolgreicher Eingabe wird ein kurzlebiger Session-Grant gesetzt; die
    Bestaetigungsseite kann dann ohne erneute Code-Eingabe freigeben.
    """
    if not is_qr_login_enabled(request):
        raise Http404
    if not request.user.is_authenticated:
        login_url = reverse("login")
        return redirect(f"{login_url}?{urlencode({'next': request.get_full_path()})}")

    membership = get_membership(request.user)
    if not membership:
        return redirect("access")

    error = ""
    status = 200
    if request.method == "POST":
        if not check_qr_rate_limit("qr_manual", f"{request.user.id}:{get_client_ip(request)}"):
            error = "Zu viele Versuche. Bitte kurz warten."
            status = 429
        else:
            code = (request.POST.get("manual_code") or "").strip()
            qr_req = (
                QrLoginRequest.objects.filter(
                    manual_code_hash=hash_manual_code(code),
                    station=membership.station,
                    state__in=[QrLoginRequest.State.CREATED, QrLoginRequest.State.SCANNED],
                    expires_at__gt=timezone.now(),
                ).first()
            )
            if qr_req is None:
                error = "Code unbekannt oder abgelaufen. Bitte am wartenden Bildschirm erneuern."
                status = 400
            else:
                request.session[f"qr_manual_grant_{qr_req.pk}"] = int(timezone.now().timestamp())
                return redirect("qr_login_confirm", login_id=qr_req.pk)

    context = {
        "error": error,
        "station": membership.station,
    }
    response = render(request, "registration/qr_manual.html", context, status=status)
    return qr_form_page_headers(response)


def _manual_grant_valid(request: HttpRequest, login_id) -> bool:
    granted_at = request.session.get(f"qr_manual_grant_{login_id}")
    if not isinstance(granted_at, int):
        return False
    age = int(timezone.now().timestamp()) - granted_at
    return 0 <= age <= getattr(settings, "QR_LOGIN_TTL_SECONDS", 120)


@qr_endpoint
@require_http_methods(["GET", "POST"])
def qr_login_confirm(request: HttpRequest, login_id: str) -> HttpResponse:
    """Bestätigungsseite (GET) und Approval (POST) auf dem Mitarbeitergeraet."""
    if not is_qr_login_enabled(request):
        if request.method == "POST":
            return qr_error("qr_disabled", 503)
        raise Http404

    if not request.user.is_authenticated:
        login_url = reverse("login")
        query = urlencode({"next": request.get_full_path()})
        return redirect(f"{login_url}?{query}")

    qr_req = QrLoginRequest.objects.select_related("station").filter(pk=login_id).first()
    if not qr_req:
        if request.method == "POST":
            return qr_error("qr_invalid", 404)
        raise Http404

    now = timezone.now()
    if qr_req.expires_at <= now:
        if request.method == "POST":
            return qr_error("qr_expired", 410)
        messages.error(request, "Diese QR-Anmeldung ist abgelaufen.")
        return redirect("dashboard")

    membership = get_membership(request.user)
    if not membership or not membership.is_active or membership.station_id != qr_req.station_id:
        if request.method == "POST":
            return qr_error("qr_forbidden", 403)
        messages.error(request, "Keine aktive Berechtigung für diese Wache.")
        return redirect("access")

    if request.method == "GET":
        mark_scanned_if_created(qr_req)

        has_mfa = user_has_confirmed_mfa(request.user)
        has_totp = user_has_totp(request.user)
        has_passkey = webauthn_enabled() and user_has_passkey(request.user)

        auth_time = get_auth_time(request)
        now_ts = int(now.timestamp())
        auth_age = (now_ts - auth_time) if auth_time is not None else 999999
        is_fresh = get_auth_method(request) != "qr" and (
            (0 <= auth_age <= 300) if has_mfa else (0 <= auth_age <= 600)
        )

        context = {
            "qr_req": qr_req,
            "station": qr_req.station,
            "origin_host": urlparse(qr_req.origin).netloc or qr_req.origin,
            "check_word": qr_req.check_word,
            "has_mfa": has_mfa,
            "has_totp": has_totp,
            "has_passkey": has_passkey,
            "is_fresh": is_fresh,
            "requires_totp_or_passkey": has_mfa and not is_fresh,
            "has_manual_grant": _manual_grant_valid(request, qr_req.pk),
            "expires_in": max(0, int((qr_req.expires_at - now).total_seconds())),
        }
        return qr_form_page_headers(render(request, "registration/qr_confirm.html", context))

    # POST (Approval)
    if not check_qr_rate_limit("qr_approve", f"{request.user.id}:{login_id}"):
        return qr_error("qr_rate_limited", 429)

    if qr_req.state not in (QrLoginRequest.State.CREATED, QrLoginRequest.State.SCANNED):
        return qr_error("qr_conflict", 409)

    if verify_browser_session(request, qr_req):
        return qr_error("qr_forbidden", 403)

    secret = _get_request_secret(request)
    body = _json_body(request) if request.content_type == "application/json" else {}
    manual_code = (
        request.POST.get("manual_code")
        or body.get("manual_code")
        or ""
    ).strip()

    if not verify_possession(qr_req, secret, manual_code) and not _manual_grant_valid(
        request, qr_req.pk
    ):
        QrLoginRequest.objects.filter(pk=qr_req.pk).update(attempts=F("attempts") + 1)
        return qr_error("qr_forbidden", 403)

    totp_token = (
        request.POST.get("totp_code")
        or request.POST.get("token")
        or body.get("totp_code")
        or body.get("token")
        or ""
    ).strip()

    ok, totp_step, _ = get_approval_freshness(
        request, request.user, totp_token=totp_token, qr_request=qr_req
    )
    if not ok:
        return qr_error("qr_forbidden", 403)

    approved = approve_qr_request(
        qr_req,
        request.user,
        membership,
        session_key=request.session.session_key or "",
        totp_step=totp_step,
    )
    if not approved:
        if timezone.now() >= qr_req.expires_at:
            return qr_error("qr_expired", 410)
        return qr_error("qr_conflict", 409)

    request.session.pop("qr_passkey_reauth_time", None)
    request.session.pop("qr_passkey_reauth_user_id", None)
    request.session.pop("qr_passkey_reauth_login_id", None)

    if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.content_type == "application/json":
        return JsonResponse({"ok": True, "state": "approved"})

    messages.success(request, "Anmeldung erfolgreich bestätigt.")
    return redirect("dashboard")


@qr_endpoint
@require_POST
def qr_login_deny(request: HttpRequest, login_id: str) -> HttpResponse:
    """Ablehnung der QR-Anmeldung durch das Mitarbeitergeraet."""
    if not is_qr_login_enabled(request):
        return qr_error("qr_disabled", 503)

    if not request.user.is_authenticated:
        return qr_error("qr_forbidden", 403)

    qr_req = QrLoginRequest.objects.filter(pk=login_id).first()
    if not qr_req:
        return qr_error("qr_invalid", 404)

    membership = get_membership(request.user)
    if not membership or not membership.is_active or membership.station_id != qr_req.station_id:
        return qr_error("qr_forbidden", 403)

    if timezone.now() >= qr_req.expires_at:
        return qr_error("qr_expired", 410)

    denied = deny_qr_request(qr_req, user=request.user)
    if not denied:
        return qr_error("qr_conflict", 409)

    if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.content_type == "application/json":
        return JsonResponse({"ok": True, "state": "denied"})

    messages.info(request, "Anmeldung wurde abgelehnt.")
    return redirect("dashboard")


@qr_endpoint
@require_POST
def qr_login_passkey_options(request: HttpRequest, login_id: str) -> HttpResponse:
    """Optionen fuer die Passkey-Reauthentisierung auf der Bestaetigungsseite."""
    if not is_qr_login_enabled(request):
        return qr_error("qr_disabled", 503)

    if not request.user.is_authenticated:
        return qr_error("qr_forbidden", 403)

    if not webauthn_enabled() or not user_has_passkey(request.user):
        return qr_error("qr_forbidden", 403)

    if not check_qr_rate_limit("qr_passkey", f"{request.user.id}:{login_id}"):
        return qr_error("qr_rate_limited", 429)

    qr_req = QrLoginRequest.objects.filter(pk=login_id).first()
    if not qr_req:
        return qr_error("qr_invalid", 404)
    if timezone.now() >= qr_req.expires_at:
        return qr_error("qr_expired", 410)
    if qr_req.state not in (QrLoginRequest.State.CREATED, QrLoginRequest.State.SCANNED):
        return qr_error("qr_conflict", 409)

    membership = get_membership(request.user)
    if not membership or not getattr(membership, "is_active", True) or membership.station_id != qr_req.station_id:
        return qr_error("qr_forbidden", 403)

    options, options_json = authentication_options(user=request.user)
    request.session["qr_passkey_challenge"] = {
        "challenge": bytes_to_base64url(options.challenge),
        "login_id": str(qr_req.pk),
    }
    return HttpResponse(options_json, content_type="application/json")


@qr_endpoint
@require_POST
def qr_login_passkey_verify(request: HttpRequest, login_id: str) -> JsonResponse:
    """Prueft Passkey-Assertion fuer Reauth auf der Bestaetigungsseite."""
    if not is_qr_login_enabled(request):
        return qr_error("qr_disabled", 503)

    if not request.user.is_authenticated:
        return qr_error("qr_forbidden", 403)

    if not check_qr_rate_limit("qr_passkey", f"{request.user.id}:{login_id}"):
        return qr_error("qr_rate_limited", 429)

    challenge_data = request.session.pop("qr_passkey_challenge", None)
    if (
        not isinstance(challenge_data, dict)
        or not challenge_data.get("challenge")
        or challenge_data.get("login_id") != str(login_id)
    ):
        return qr_error("qr_invalid", 400)

    challenge_val = challenge_data["challenge"]

    body = _json_body(request)
    if not body or "credential" not in body:
        return qr_error("qr_invalid", 400)

    qr_req = QrLoginRequest.objects.filter(pk=login_id).first()
    if not qr_req:
        return qr_error("qr_invalid", 404)
    if timezone.now() >= qr_req.expires_at:
        return qr_error("qr_expired", 410)
    if qr_req.state not in (QrLoginRequest.State.CREATED, QrLoginRequest.State.SCANNED):
        return qr_error("qr_conflict", 409)

    membership = get_membership(request.user)
    if not membership or not getattr(membership, "is_active", True) or membership.station_id != qr_req.station_id:
        return qr_error("qr_forbidden", 403)

    try:
        verify_authentication(
            json.dumps(body["credential"]),
            challenge_val,
            expected_user=request.user,
        )
    except Exception:
        return qr_error("qr_forbidden", 403)

    request.session["qr_passkey_reauth_time"] = int(timezone.now().timestamp())
    request.session["qr_passkey_reauth_user_id"] = request.user.pk
    request.session["qr_passkey_reauth_login_id"] = str(qr_req.pk)
    return JsonResponse({"ok": True})


@qr_endpoint
@require_POST
def qr_login_exchange(request: HttpRequest, login_id: str) -> JsonResponse:
    """Tauscht die freigegebene QR-Anmeldung gegen eine gueltige Session ein."""
    if not is_qr_login_enabled(request):
        return qr_error("qr_disabled", 503)

    qr_req = QrLoginRequest.objects.select_related("station").filter(pk=login_id).first()
    if not qr_req:
        return qr_error("qr_invalid", 404)

    session_key = request.session.session_key or ""
    if not check_qr_rate_limit("qr_exchange", f"{session_key}:{login_id}"):
        return qr_error("qr_rate_limited", 429)

    # Replay protection: if already consumed, return 409/410
    if qr_req.state == QrLoginRequest.State.CONSUMED:
        return qr_error("qr_conflict", 409)

    if not verify_browser_session(request, qr_req):
        return qr_error("qr_forbidden", 403)

    secret = _get_request_secret(request)
    if not secret or not verify_secret(qr_req, secret):
        return qr_error("qr_forbidden", 403)

    if timezone.now() >= qr_req.expires_at:
        return qr_error("qr_expired", 410)

    if qr_req.state != QrLoginRequest.State.APPROVED:
        return qr_error("qr_conflict", 409)

    # CAS APPROVED -> CONSUMED
    consumed = exchange_qr_request(qr_req)
    if not consumed:
        return qr_error("qr_conflict", 409)

    # Re-verify approving user, station, role, and active membership
    user = User.objects.filter(pk=qr_req.approved_by_id, is_active=True).first()
    membership = (
        Membership.objects.filter(
            user=user,
            station=qr_req.station,
            is_active=True,
        ).first()
        if user
        else None
    )

    if not user or not membership:
        qr_req.state = QrLoginRequest.State.REVOKED
        qr_req.save(update_fields=["state"])
        audit(user, qr_req.station, "qr_login.revoked", qr_req, {
            "login_id_prefix": str(qr_req.id)[:8],
            "state": "revoked",
            "origin_host": urlparse(qr_req.origin).netloc or qr_req.origin,
            "station_id": qr_req.station_id,
            "role": "",
        })
        return qr_error("qr_forbidden", 403)

    # Log in user with ModelBackend
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session["auth_time"] = int(timezone.now().timestamp())
    request.session["auth_user_id"] = user.pk
    request.session["auth_method"] = "qr"

    # Remove nonces and pending mfa keys
    nonces = request.session.get("qr_browser_nonces", {})
    nonces.pop(str(qr_req.id), None)
    request.session["qr_browser_nonces"] = nonces
    request.session.pop("mfa_pending_user_id", None)
    request.session.pop("mfa_next", None)
    request.session.pop("mfa_failures", None)

    audit(user, qr_req.station, "qr_login.consumed", qr_req, {
        "login_id_prefix": str(qr_req.id)[:8],
        "state": "consumed",
        "origin_host": urlparse(qr_req.origin).netloc or qr_req.origin,
        "station_id": qr_req.station_id,
        "role": membership.role,
    })

    redirect_to = reverse("landing")
    if mfa_enabled() and mfa_required() and not user_has_confirmed_mfa(user):
        redirect_to = reverse("mfa_setup")

    return JsonResponse({"ok": True, "redirect": redirect_to})


class QrLogoutView(LogoutView):
    """Logout-View that revokes open approved QR requests before destroying session."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            revoke_open_requests_for_user(request.user)
        return super().dispatch(request, *args, **kwargs)
