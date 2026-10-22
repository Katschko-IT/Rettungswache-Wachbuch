"""Account security endpoints: Passkeys, Web-Push, calendar feed tokens."""

from __future__ import annotations

import io
import json
import secrets

import qrcode
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from webauthn.helpers import bytes_to_base64url

from .access import CONTENT_ROLES, get_membership, membership_required, station_module_required
from .api.views import generate_api_token
from .mfa import mfa_enabled, mfa_required, user_has_confirmed_mfa, user_has_totp
from .models import (
    ApiToken,
    CalendarEvent,
    CalendarFeedToken,
    Membership,
    PushSubscription,
    WebAuthnCredential,
)
from .push import push_endpoint_allowed, vapid_public_key, web_push_enabled
from .services import audit
from .webauthn_auth import (
    authentication_options,
    registration_options_for,
    user_has_passkey,
    verify_and_store_registration,
    verify_authentication,
    webauthn_enabled,
)


MFA_MAX_FAILURES = 8


def _json_body(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return None


def _mfa_failure(request):
    failures = int(request.session.get("mfa_failures", 0)) + 1
    request.session["mfa_failures"] = failures
    if failures >= MFA_MAX_FAILURES:
        request.session.pop("mfa_pending_user_id", None)
        request.session.pop("mfa_next", None)
        request.session.pop("mfa_failures", None)
        request.session.pop("webauthn_auth_challenge", None)
        return True
    return False


def _ics_escape(value):
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _ics_datetime(value):
    return timezone.localtime(value).strftime("%Y%m%dT%H%M%S")


def build_station_calendar_ics(station, events):
    from .holidays import station_agenda

    stamp = timezone.now().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Wachbuch//DE",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_ics_escape(station.name)}",
    ]
    agenda = station_agenda(station, events, past_days=30, future_days=400)
    for item in agenda:
        if item.kind == "holiday" and item.all_day:
            day = timezone.localtime(item.starts_at).strftime("%Y%m%d")
            next_day = timezone.localtime(item.ends_at).strftime("%Y%m%d")
            lines.extend([
                "BEGIN:VEVENT",
                f"UID:wachbuch-holiday-{day}@rettungswache-wachbuch",
                f"DTSTAMP:{stamp}",
                f"DTSTART;VALUE=DATE:{day}",
                f"DTEND;VALUE=DATE:{next_day}",
                f"SUMMARY:{_ics_escape(item.title)}",
                f"DESCRIPTION:{_ics_escape(item.description)}",
                "TRANSP:TRANSPARENT",
                "END:VEVENT",
            ])
            continue
        uid_prefix = "wachbuch-waste" if item.kind == "waste" else "wachbuch-event"
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid_prefix}-{item.source_pk}@rettungswache-wachbuch",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{_ics_datetime(item.starts_at)}",
            f"DTEND:{_ics_datetime(item.ends_at)}",
            f"SUMMARY:{_ics_escape(item.title)}",
            f"DESCRIPTION:{_ics_escape(item.description)}",
            "END:VEVENT",
        ])
    lines.extend(["END:VCALENDAR", ""])
    return "\r\n".join(lines)


@require_GET
def passkey_login_options(request):
    if not webauthn_enabled():
        raise Http404
    options, options_json = authentication_options(user=None)
    request.session["webauthn_login_challenge"] = bytes_to_base64url(options.challenge)
    return HttpResponse(options_json, content_type="application/json")


@require_POST
def passkey_login_verify(request):
    if not webauthn_enabled():
        raise Http404
    challenge = request.session.get("webauthn_login_challenge")
    body = _json_body(request)
    if not challenge or not body or "credential" not in body:
        return JsonResponse({"ok": False, "error": "Ungültige Anfrage."}, status=400)
    try:
        user = verify_authentication(json.dumps(body["credential"]), challenge)
    except Exception:
        return JsonResponse({"ok": False, "error": "Passkey konnte nicht geprüft werden."}, status=400)
    request.session.pop("webauthn_login_challenge", None)
    request.session["auth_method"] = "passkey"
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    redirect_to = reverse("landing")
    if mfa_enabled() and mfa_required() and not user_has_confirmed_mfa(user):
        redirect_to = reverse("mfa_setup")
    return JsonResponse({"ok": True, "redirect": redirect_to})


@require_GET
def passkey_mfa_options(request):
    if not webauthn_enabled() or not mfa_enabled():
        raise Http404
    pending_id = request.session.get("mfa_pending_user_id")
    if not pending_id:
        return JsonResponse({"ok": False, "error": "Keine ausstehende Anmeldung."}, status=400)
    user = get_object_or_404(User, pk=pending_id, is_active=True)
    if not user_has_passkey(user):
        return JsonResponse({"ok": False, "error": "Kein Passkey hinterlegt."}, status=400)
    options, options_json = authentication_options(user=user)
    request.session["webauthn_auth_challenge"] = bytes_to_base64url(options.challenge)
    return HttpResponse(options_json, content_type="application/json")


@require_POST
def passkey_mfa_verify(request):
    if not webauthn_enabled() or not mfa_enabled():
        raise Http404
    pending_id = request.session.get("mfa_pending_user_id")
    challenge = request.session.get("webauthn_auth_challenge")
    body = _json_body(request)
    if not pending_id or not challenge or not body or "credential" not in body:
        return JsonResponse({"ok": False, "error": "Ungültige Anfrage."}, status=400)
    user = get_object_or_404(User, pk=pending_id, is_active=True)
    try:
        verified = verify_authentication(
            json.dumps(body["credential"]), challenge, expected_user=user
        )
    except Exception:
        locked = _mfa_failure(request)
        error = "Zu viele Fehlversuche." if locked else "Passkey ungültig."
        return JsonResponse({"ok": False, "error": error}, status=400)
    request.session["auth_method"] = "passkey"
    login(request, verified, backend="django.contrib.auth.backends.ModelBackend")
    next_url = request.session.pop("mfa_next", None) or reverse("landing")
    request.session.pop("mfa_pending_user_id", None)
    request.session.pop("mfa_failures", None)
    request.session.pop("webauthn_auth_challenge", None)
    return JsonResponse({"ok": True, "redirect": next_url})


@require_GET
def passkey_register_options(request):
    if not webauthn_enabled() or not request.user.is_authenticated:
        raise Http404
    options, options_json = registration_options_for(request.user)
    request.session["webauthn_register_challenge"] = bytes_to_base64url(options.challenge)
    return HttpResponse(options_json, content_type="application/json")


@require_POST
def passkey_register_verify(request):
    if not webauthn_enabled() or not request.user.is_authenticated:
        raise Http404
    challenge = request.session.get("webauthn_register_challenge")
    body = _json_body(request)
    if not challenge or not body or "credential" not in body:
        return JsonResponse({"ok": False, "error": "Ungültige Anfrage."}, status=400)
    try:
        credential, _created = verify_and_store_registration(
            request.user,
            json.dumps(body["credential"]),
            challenge,
            device_name=body.get("device_name", "")[:120],
        )
    except Exception:
        return JsonResponse({"ok": False, "error": "Registrierung fehlgeschlagen."}, status=400)
    request.session.pop("webauthn_register_challenge", None)
    membership = get_membership(request.user)
    station = membership.station if membership else None
    audit(request.user, station, "webauthn.registered", credential, {
        "fields": ["credential_id"],
    })
    return JsonResponse({"ok": True})


@require_POST
def passkey_delete(request, pk):
    if not webauthn_enabled() or not request.user.is_authenticated:
        raise Http404
    credential = get_object_or_404(WebAuthnCredential, pk=pk, user=request.user)
    if mfa_required() and not user_has_totp(request.user):
        remaining = WebAuthnCredential.objects.filter(user=request.user).exclude(pk=pk).count()
        if remaining == 0:
            messages.error(request, _("Mindestens ein zweiter Faktor muss erhalten bleiben."))
            return redirect("mfa_setup")
    credential.delete()
    messages.success(request, _("Passkey wurde entfernt."))
    return redirect("mfa_setup")


@membership_required(CONTENT_ROLES)
@require_http_methods(["GET", "POST"])
def push_settings(request):
    if not web_push_enabled():
        raise Http404
    station = request.membership.station
    if request.method == "POST":
        body = _json_body(request)
        if body is None and request.POST.get("action") == "unsubscribe":
            PushSubscription.objects.filter(user=request.user, station=station).delete()
            messages.success(request, _("Push-Benachrichtigungen deaktiviert."))
            return redirect("push_settings")
        if not body or body.get("action") == "unsubscribe":
            PushSubscription.objects.filter(user=request.user, station=station).delete()
            return JsonResponse({"ok": True})
        endpoint = body.get("endpoint", "")
        keys = body.get("keys") or {}
        if not endpoint or not keys.get("p256dh") or not keys.get("auth"):
            return JsonResponse({"ok": False, "error": "Unvollständige Subscription."}, status=400)
        if not push_endpoint_allowed(str(endpoint)):
            return JsonResponse(
                {"ok": False, "error": "Push-Endpunkt ist nicht in der HTTPS-Allowlist."},
                status=400,
            )
        PushSubscription.objects.update_or_create(
            endpoint=endpoint[:500],
            defaults={
                "user": request.user,
                "station": station,
                "p256dh": keys["p256dh"][:200],
                "auth": keys["auth"][:100],
                "user_agent": request.META.get("HTTP_USER_AGENT", "")[:300],
            },
        )
        return JsonResponse({"ok": True})
    active = PushSubscription.objects.filter(user=request.user, station=station).exists()
    return render(request, "core/push_settings.html", {
        "push_config": {
            "vapidPublicKey": vapid_public_key(),
            "subscribeUrl": reverse("push_settings"),
        },
        "push_active": active,
    })


@membership_required(CONTENT_ROLES)
@station_module_required("calendar_enabled")
@require_GET
def calendar_feed_ics(request):
    station = request.membership.station
    events = CalendarEvent.objects.filter(station=station).order_by("starts_at")
    body = build_station_calendar_ics(station, events)
    response = HttpResponse(body, content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = 'inline; filename="wachbuch-kalender.ics"'
    return response


@require_GET
def calendar_feed_token_ics(request, token):
    feed = get_object_or_404(
        CalendarFeedToken.objects.select_related("station"),
        token=token,
        is_active=True,
        station__calendar_enabled=True,
        station__is_active=True,
    )
    feed.last_used_at = timezone.now()
    feed.save(update_fields=["last_used_at"])
    events = CalendarEvent.objects.filter(station=feed.station).order_by("starts_at")
    body = build_station_calendar_ics(feed.station, events)
    response = HttpResponse(body, content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = 'inline; filename="wachbuch-kalender.ics"'
    return response


@membership_required({Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN})
@station_module_required("calendar_enabled")
@require_http_methods(["GET", "POST"])
def calendar_feed_manage(request):
    station = request.membership.station
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create":
            CalendarFeedToken.objects.create(
                station=station,
                token=secrets.token_urlsafe(32),
                label=(request.POST.get("label") or "Kalender-Abo")[:120],
                created_by=request.user,
            )
            messages.success(request, _("Abo-Link wurde erzeugt."))
        elif action == "revoke":
            CalendarFeedToken.objects.filter(
                station=station, pk=request.POST.get("token_id")
            ).update(is_active=False)
            messages.success(request, _("Abo-Link wurde widerrufen."))
        return redirect("calendar_feed_manage")
    tokens = CalendarFeedToken.objects.filter(station=station).select_related("created_by")
    return render(request, "core/calendar_feed.html", {"tokens": tokens})


@require_http_methods(["GET", "POST"])
def api_tokens_manage(request):
    """Create/revoke app tokens for native clients (Paperless/Nextcloud style)."""
    if not request.user.is_authenticated:
        return redirect(f"{reverse('login')}?next={reverse('api_tokens_manage')}")
    membership = get_membership(request.user)
    if membership is None:
        messages.error(request, _("API-Tokens brauchen einen aktiven Wachenzugang."))
        return redirect("account_home")
    plaintext = None
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create":
            from .api.views import DEFAULT_MOBILE_SCOPES, default_token_expiry

            raw, token_hash, prefix = generate_api_token()
            token = ApiToken.objects.create(
                user=request.user,
                label=(request.POST.get("label") or "Mobile App")[:120],
                token_prefix=prefix,
                token_hash=token_hash,
                scopes=list(DEFAULT_MOBILE_SCOPES),
                expires_at=default_token_expiry(),
            )
            audit(request.user, membership.station, "api.token_created", token, {
                "fields": ["label", "scopes", "expires_at"],
                "via": "account",
            })
            plaintext = raw
            messages.success(request, _("App-Token erzeugt. Bitte jetzt kopieren – es wird nur einmal angezeigt."))
        elif action == "revoke":
            updated = ApiToken.objects.filter(
                user=request.user,
                pk=request.POST.get("token_id"),
                is_active=True,
            ).update(is_active=False)
            if updated:
                audit(request.user, membership.station, "api.token_revoked", request.user, {
                    "fields": ["is_active"],
                })
                messages.success(request, _("App-Token wurde widerrufen."))
        if plaintext is None:
            return redirect("api_tokens_manage")
    tokens = ApiToken.objects.filter(user=request.user).order_by("-created_at")
    setup_url = request.build_absolute_uri("/").rstrip("/")
    return render(request, "core/api_tokens.html", {
        "tokens": tokens,
        "plaintext_token": plaintext,
        "api_root": "/api/v1/",
        "mobile_setup_url": setup_url,
    })


@require_GET
def mobile_setup_qr(request):
    """PNG QR with the public server origin for the mobile client camera scan."""
    if not request.user.is_authenticated:
        return redirect(f"{reverse('login')}?next={reverse('mobile_setup_qr')}")
    from .terminal import local_cert_fingerprint
    from .terminal_views import connect_link

    if local_cert_fingerprint():
        # Lokales Zertifikat (z. B. Raspberry Pi): Fingerabdruck mitgeben.
        setup_url = connect_link(request)
    else:
        setup_url = request.build_absolute_uri("/").rstrip("/")
    image = qrcode.make(setup_url, box_size=6, border=2)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return HttpResponse(buffer.getvalue(), content_type="image/png")
