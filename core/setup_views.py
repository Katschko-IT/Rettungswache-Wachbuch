"""Views for the one-time installation and employee activation.

Offline contract: nothing in this module performs an external network call
except the explicitly triggered weather preview (``core.weather``), which is
optional and failure-tolerant.
"""

from __future__ import annotations

import base64
import hashlib
import io
import time

import qrcode
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import weather
from .access import membership_required
from .forms import ActivationPasswordForm, EmployeeInviteForm, SetupWizardForm
from .models import EmployeeActivation, Membership, Station
from .rate_limit import consume as rate_limit_consume
from .services import audit
from .terminal import is_local_request
from .setup_wizard import (
    ActivationInvalid,
    SetupAlreadyCompleted,
    SetupConflict,
    SetupDisabled,
    SetupTokenInvalid,
    activation_url,
    active_activations,
    bootstrap_fingerprint,
    complete_setup,
    consume_activation,
    create_employee_invite,
    find_activation,
    revoke_activation,
    setup_available,
    setup_completed,
    verify_bootstrap_hash,
    verify_bootstrap_token,
)

SETUP_SESSION_KEY = "setup_bootstrap_hash"
SETUP_DONE_KEY = "setup_done"
SETUP_SESSION_AT = "setup_bootstrap_at"
SETUP_SESSION_TTL = 600
WEATHER_SESSION_KEY = "setup_weather_preview"
DRAFT_SESSION_KEY = "setup_draft"
BOOTSTRAP_LIMIT = 5
BOOTSTRAP_WINDOW = 900
ACTIVATION_LOOKUP_LIMIT = 60
ACTIVATION_LOOKUP_WINDOW = 60


def _client_key(request) -> str:
    return getattr(request, "client_ip", None) or request.META.get("REMOTE_ADDR", "unknown")


def _allowed_timezone_names() -> set[str]:
    field = SetupWizardForm.base_fields["timezone_name"]
    return {str(value) for value, _label in field.choices}


def _requested_timezone(request) -> str:
    """Return a whitelisted, real IANA zone; never a free-form cache key."""
    name = (request.POST.get("timezone_name") or "").strip()
    if not name:
        name = "Europe/Berlin"
    if name not in _allowed_timezone_names():
        raise weather.WeatherUnavailable(
            _("Bitte eine der angebotenen Zeitzonen wählen.")
        )
    return name


def _clear_setup_session(request) -> None:
    for key in (SETUP_SESSION_KEY, SETUP_SESSION_AT, WEATHER_SESSION_KEY, DRAFT_SESSION_KEY):
        request.session.pop(key, None)


def _session_proof_valid(request) -> bool:
    stored = request.session.get(SETUP_SESSION_KEY)
    started = request.session.get(SETUP_SESSION_AT)
    if not stored or not started:
        return False
    try:
        within_ttl = (time.time() - float(started)) < SETUP_SESSION_TTL
        token_current = verify_bootstrap_hash(str(stored))
    except (SetupDisabled, TypeError, ValueError):
        within_ttl = False
        token_current = False
    if not (within_ttl and token_current):
        # Rotation or removal of the bootstrap token invalidates every session
        # proof issued for the previous token, and with it the weather preview
        # and draft derived from that access.
        _clear_setup_session(request)
        return False
    return True


def _address_fingerprint(data: dict) -> str:
    """Stable, non-reversible binding of a weather preview to its address."""

    def norm(value) -> str:
        return " ".join(str(value or "").split()).casefold()

    joined = "|".join(
        norm(data.get(key))
        for key in ("street", "postal_code", "city", "timezone_name")
    )
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _require_setup_available():
    if not setup_available():
        raise Http404
    if setup_completed():
        raise Http404


def _station_slug(name: str) -> str:
    base = slugify(name)[:40] or "wache"
    candidate = base
    index = 2
    while Station.objects.filter(slug=candidate).exists():
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def _render_wizard(request, form, *, weather_preview=None, weather_error="", status=200):
    return render(
        request,
        "core/setup_wizard.html",
        {"form": form, "weather_preview": weather_preview, "weather_error": weather_error},
        status=status,
    )


@require_http_methods(["GET", "POST"])
def setup_wizard(request):
    _require_setup_available()

    if request.method == "POST" and "bootstrap_token" in request.POST and not _session_proof_valid(request):
        if not rate_limit_consume(
            "setup_bootstrap", _client_key(request), limit=BOOTSTRAP_LIMIT, window_seconds=BOOTSTRAP_WINDOW
        ):
            return render(request, "core/setup_token.html", {"rate_limited": True}, status=429)
        token = request.POST.get("bootstrap_token", "").strip()
        if not verify_bootstrap_token(token):
            return render(request, "core/setup_token.html", {"invalid": True}, status=403)
        request.session.cycle_key()
        request.session[SETUP_SESSION_KEY] = bootstrap_fingerprint(token)
        request.session[SETUP_SESSION_AT] = time.time()
        request.session.pop(WEATHER_SESSION_KEY, None)
        return redirect("setup_wizard")

    if not _session_proof_valid(request):
        return render(request, "core/setup_token.html", {})

    if request.method == "POST":
        form = SetupWizardForm(request.POST)
        if form.is_valid():
            data = dict(form.cleaned_data)
            data["slug"] = _station_slug(data["station_name"])
            preview = request.session.get(WEATHER_SESSION_KEY) or {}
            if data.get("weather_enabled") and preview.get("latitude") is not None:
                if preview.get("address_fingerprint") != _address_fingerprint(data):
                    # The preview belongs to a different address: never store
                    # foreign or previous coordinates under the new station.
                    request.session.pop(WEATHER_SESSION_KEY, None)
                    form.add_error(
                        "weather_enabled",
                        _("Die Anschrift wurde nach der Wettervorschau geändert. "
                          "Bitte die Wettervorschau für die aktuelle Anschrift erneut laden."),
                    )
                    return _render_wizard(
                        request,
                        form,
                        weather_preview=None,
                        weather_error=_("Wettervorschau passt nicht zur eingegebenen Anschrift."),
                    )
                data["latitude"] = preview["latitude"]
                data["longitude"] = preview["longitude"]
            elif data.get("weather_enabled"):
                # Without coordinates the station would be permanently broken:
                # ask for an explicit decision instead of failing silently later.
                form.add_error(
                    "weather_enabled",
                    _("Bitte zuerst die Wettervorschau laden oder die Wetteranzeige abwählen."),
                )
                return _render_wizard(
                    request,
                    form,
                    weather_preview=None,
                    weather_error=_("Wetter ist aktiviert, aber es liegen keine Koordinaten vor."),
                )
            try:
                station, user = complete_setup(
                    data=data, bootstrap_hash=request.session[SETUP_SESSION_KEY]
                )
            except SetupConflict as exc:
                form.add_error(None, str(exc))
                return _render_wizard(request, form, weather_error="", status=409)
            except SetupAlreadyCompleted:
                request.session.pop(SETUP_SESSION_KEY, None)
                request.session.pop(SETUP_SESSION_AT, None)
                return render(request, "core/setup_token.html", {"already_completed": True}, status=409)
            except SetupTokenInvalid:
                request.session.pop(SETUP_SESSION_KEY, None)
                return redirect("setup_wizard")
            except SetupDisabled:
                raise Http404
            _clear_setup_session(request)
            return _finish_setup(request, station, user, form.cleaned_data)
    else:
        initial = dict(request.session.get(DRAFT_SESSION_KEY) or {})
        # Am Touch-Bildschirm des Servers ist „dieses Gerät“ das Terminal.
        initial.setdefault("register_terminal", is_local_request(request))
        # Über eine echte Domain aufgerufen: vermutlich öffentlich erreichbar.
        public = _looks_public(request)
        initial.setdefault("public_site", public)
        initial.setdefault("mfa_required", public)
        initial.setdefault("server_location", "germany" if public else "station")
        form = SetupWizardForm(initial=initial)

    return _render_wizard(
        request,
        form,
        weather_preview=request.session.get(WEATHER_SESSION_KEY),
    )


def _looks_public(request) -> bool:
    """Aufruf über einen Domainnamen statt über IP, localhost oder einen LAN-Namen."""
    import ipaddress

    try:
        host = request.get_host().rsplit(":", 1)[0].strip("[]").lower()
    except Exception:  # DisallowedHost: nichts vermuten
        return False
    if is_local_request(request) or host.endswith((".lan", ".local", ".home", ".internal")) or "." not in host:
        return False
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return True
    return False


def _finish_setup(request, station, user, cleaned):
    """Optionaler Terminal-Schritt, dann Abschlussseite mit den nächsten Schritten."""
    from .terminal import create_terminal_device, set_station_code, set_terminal_cookie, terminal_enabled

    code_set = register = False
    raw_terminal = ""
    if terminal_enabled():
        if cleaned.get("terminal_code"):
            set_station_code(station, cleaned["terminal_code"], set_by=user)
            audit(user, station, "terminal.code_changed", station, {"via": "setup"})
            code_set = True
        if cleaned.get("register_terminal"):
            terminal, raw_terminal = create_terminal_device(station, label="Wachenterminal", created_by=user)
            audit(user, station, "terminal.created", terminal, {"fields": ["label"], "via": "setup"})
            register = True
    request.session[SETUP_DONE_KEY] = {
        "station": station.name,
        "admin": user.get_username(),
        "terminal_enabled": terminal_enabled(),
        "terminal_registered": register,
        "code_set": code_set,
        "weather": bool(station.weather_enabled),
        "public_site": bool(cleaned.get("public_site")),
        "mfa_required": bool(cleaned.get("mfa_required")),
    }
    response = redirect("setup_done")
    if raw_terminal:
        set_terminal_cookie(response, request, raw_terminal)
    return response


@require_GET
def setup_done(request):
    """Einmalige Zusammenfassung nach dem Abschluss; ohne frische Einrichtung 404."""
    summary = request.session.get(SETUP_DONE_KEY)
    if not summary or request.user.is_authenticated:
        raise Http404
    response = render(request, "core/setup_done.html", {"summary": summary})
    response["Cache-Control"] = "no-store, max-age=0"
    return response


@require_POST
def setup_weather_preview(request):
    _require_setup_available()
    if not _session_proof_valid(request):
        return redirect("setup_wizard")

    address_parts = [
        request.POST.get("street", "").strip(),
        f"{request.POST.get('postal_code', '').strip()} {request.POST.get('city', '').strip()}".strip(),
    ]
    address = ", ".join(part for part in address_parts if part)
    consent = request.POST.get("geo_consent") == "1"
    weather_enabled = request.POST.get("weather_enabled") in {"on", "1", "true", "True"}
    if not weather_enabled:
        request.session.pop(WEATHER_SESSION_KEY, None)
        return _render_wizard(
            request,
            SetupWizardForm(request.POST, preview_only=True),
            weather_error=_(
                "Die Wettervorschau ist nur sinnvoll, wenn die Wetteranzeige aktiviert ist. "
                "Bitte zuerst „5-Tage-Wetter … anzeigen“ auswählen."
            ),
        )
    if not consent:
        request.session.pop(WEATHER_SESSION_KEY, None)
        return _render_wizard(
            request,
            SetupWizardForm(request.POST, preview_only=True),
            weather_error=_(
                "Ohne ausdrückliche Einwilligung wird die Anschrift nicht an den Wetterdienst übermittelt. "
                "Die Wachendaten werden ausschließlich lokal gespeichert."
            ),
        )
    try:
        timezone_name = _requested_timezone(request)
        location = weather.geocode(address)
        forecast = weather.fetch_forecast(
            location["latitude"],
            location["longitude"],
            timezone_name=timezone_name,
        )
    except weather.WeatherUnavailable as exc:
        request.session.pop(WEATHER_SESSION_KEY, None)
        return _render_wizard(
            request,
            SetupWizardForm(request.POST, preview_only=True),
            weather_error=(
                _("Wetter konnte nicht geladen werden (%(error)s). Die Installation ist davon nicht betroffen "
                  "und kann ohne Wetter fortgesetzt werden.")
                % {"error": str(exc)}
            ),
        )
    request.session[DRAFT_SESSION_KEY] = {
        key: request.POST.get(key, "")
        for key in (
            "station_name",
            "organization_profile",
            "employee_count",
            "street",
            "postal_code",
            "city",
            "timezone_name",
            "weather_enabled",
            "traffic_enabled",
            "traffic_roads",
            "traffic_radius_km",
            "traffic_warning_areas",
            "admin_username",
            "admin_first_name",
            "admin_last_name",
            "admin_email",
            "public_site",
            "operator_name",
            "operator_represented_by",
            "operator_street",
            "operator_postal_code",
            "operator_city",
            "operator_email",
            "operator_phone",
            "dpo_name",
            "dpo_email",
            "server_location",
            "hosting_provider",
            "supervisory_authority",
            "mfa_required",
        )
    }
    request.session[WEATHER_SESSION_KEY] = {
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "label": location["label"],
        "days": forecast.days,
        "fetched_at": forecast.fetched_at_iso,
        "stale": forecast.stale,
        "age_minutes": forecast.age_minutes,
        "address_fingerprint": _address_fingerprint(
            {
                "street": request.POST.get("street", ""),
                "postal_code": request.POST.get("postal_code", ""),
                "city": request.POST.get("city", ""),
                "timezone_name": timezone_name,
            }
        ),
    }
    return redirect("setup_wizard")


def _activation_conflict(activation) -> str | None:
    """Return why a link must not be offered, or None when it is redeemable."""
    if activation is None or not activation.is_open:
        return "invalid"
    if not activation.station.is_active:
        return "station"
    if Membership.objects.filter(user=activation.user, is_active=True).exclude(
        station=activation.station
    ).exists():
        return "foreign"
    return None


@require_http_methods(["GET", "POST"])
def activate_account(request, token):
    if not rate_limit_consume(
        "activation_lookup",
        _client_key(request),
        limit=ACTIVATION_LOOKUP_LIMIT,
        window_seconds=ACTIVATION_LOOKUP_WINDOW,
    ):
        response = render(request, "core/activate_account.html", {"rate_limited": True}, status=429)
        response["Cache-Control"] = "no-store, max-age=0"
        response["Referrer-Policy"] = "no-referrer"
        return response
    activation = find_activation(token)
    conflict = _activation_conflict(activation)
    invalid = conflict is not None
    form = (
        ActivationPasswordForm(request.POST or None, user=activation.user)
        if not invalid
        else None
    )

    if not invalid and request.method == "POST" and form.is_valid():
        try:
            consume_activation(token, password=form.cleaned_data["password1"])
        except ActivationInvalid:
            invalid = True
            form = None
            # A membership at another station is terminal for this link. Close
            # only this activation so it cannot stay open forever; the foreign
            # membership itself is never touched.
            if _activation_conflict(activation) == "foreign":
                revoke_activation(activation)
            response = render(request, "core/activate_account.html", {"invalid": True}, status=410)
        else:
            messages.success(request, _("Konto aktiviert. Bitte jetzt mit dem neuen Passwort anmelden."))
            return redirect("login")
    elif invalid:
        if conflict == "foreign":
            revoke_activation(activation)
        response = render(request, "core/activate_account.html", {"invalid": True}, status=410)
    else:
        response = render(request, "core/activate_account.html", {"form": form, "activation": activation})

    response["Cache-Control"] = "no-store, max-age=0"
    # same-origin statt no-referrer: Bei no-referrer senden Browser für das
    # eigene Formular „Origin: null“, und die CSRF-Prüfung lehnt ab. Fremde
    # Seiten erhalten weiterhin keinen Referer mit dem Einmal-Token.
    response["Referrer-Policy"] = "same-origin"
    return response


@membership_required({Membership.Role.ADMIN})
@require_http_methods(["GET", "POST"])
def team_invites(request):
    station = request.membership.station
    return render(
        request,
        "core/team_invites.html",
        {"activations": active_activations(station)},
    )


@membership_required({Membership.Role.ADMIN})
@require_http_methods(["GET", "POST"])
def team_invite_create(request):
    station = request.membership.station
    form = EmployeeInviteForm(request.POST or None, station=station)
    if request.method == "POST" and form.is_valid():
        try:
            user, activation, raw = create_employee_invite(
                station=station, created_by=request.user, data=form.cleaned_data
            )
        except SetupConflict as exc:
            # A concurrent request created the username between validation and
            # insert; the transaction has rolled back completely. Report a
            # normal form error instead of a 500.
            form.add_error("username", str(exc))
            response = render(request, "core/team_invite_form.html", {"form": form}, status=409)
            response["Cache-Control"] = "no-store, max-age=0"
            return response
        url = activation_url(request, raw)
        image = qrcode.make(url, box_size=6, border=2)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        data_uri = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
        response = render(
            request,
            "core/team_invite.html",
            {
                "created_user": user,
                "activation": activation,
                "activation_link": url,
                "qr_data_uri": data_uri,
                "role": form.cleaned_data["role"],
            },
        )
        response["Cache-Control"] = "no-store, max-age=0"
        # Die Seite enthält Formulare (z. B. Abmelden); siehe activate_account.
        response["Referrer-Policy"] = "same-origin"
        return response
    return render(request, "core/team_invite_form.html", {"form": form})


@membership_required({Membership.Role.ADMIN})
@require_POST
def team_invite_revoke(request, pk):
    station = request.membership.station
    activation = EmployeeActivation.objects.filter(pk=pk, station=station).first()
    if activation is None:
        raise Http404
    if revoke_activation(activation, actor=request.user):
        messages.success(request, _("Aktivierungslink wurde widerrufen."))
    else:
        messages.info(request, _("Aktivierungslink war bereits verbraucht oder widerrufen."))
    return redirect("team_invites")
