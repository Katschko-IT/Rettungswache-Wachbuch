import json
from datetime import date, timedelta
from urllib.parse import quote, urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import IntegrityError, connection, transaction
from django.db.models import Case, IntegerField, Sum, Value, When
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _lazy
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .access import CONTENT_ROLES, get_membership, membership_required, pending_registrations_for_station, station_module_required, users_awaiting_station_access
from .errors import (
    ERROR_CODE_FORBIDDEN,
    ERROR_CODE_NOT_FOUND,
    ERROR_CODE_RATE_LIMIT,
    ERROR_CODE_SERVER_ERROR,
    ERROR_CODE_VALIDATION,
    RESPONSE_CORRELATION_HEADER,
    correlation_id_for_request,
    is_api_request,
    json_error,
    label_for_code,
    log_exception,
)

from .forms import (
    BirthdayForm,
    CalendarEventForm,
    CoffeeCorrectionForm,
    CoffeeEntryForm,
    HandoverEditForm,
    HandoverForm,
    HandoverStatusForm,
    MembershipAssignmentForm,
    MembershipEditForm,
    MasterAdminCreateUserForm,
    PinboardNoteForm,
    StationSettingsForm,
    StationTaskForm,
    TotpConfirmForm,
)
from .models import (
    AuditEvent,
    BirthdayPreference,
    CalendarEvent,
    Checklist,
    ChecklistCompletion,
    CoffeeEntry,
    FeedItem,
    FeedSource,
    HandoverAttachment,
    HandoverEntry,
    Membership,
    PinboardAttachment,
    PinboardNote,
    Station,
    StationTask,
    TotpDevice,
    WebAuthnCredential,
)
from .api.wachalltag import (
    ALLOWED_ATTACHMENT_TYPES,
    MAX_ATTACHMENT_BYTES,
    MAX_ATTACHMENTS_PER_HANDOVER,
    attachment_is_valid,
)
from .attachments import read_uploads
from .wachalltag_models import ChecklistSchedule, Defect, InventoryItem, StationAsset
from .waste_sync import store_station_waste
from .mfa import (
    confirm_device,
    create_pending_device,
    mfa_enabled,
    mfa_required,
    provisioning_uri,
    totp_plaintext,
    user_has_confirmed_mfa,
    verify_totp,
)
from .services import (
    archive_pinboard_note,
    audit,
    change_handover_status,
    clear_birthday_on_exit,
    create_handover,
    create_pinboard_note,
    set_pinboard_pin,
    structure_changes,
    update_handover_content,
    update_pinboard_note,
)
from .task_board import (
    day_board,
    ensure_default_station_tasks,
    toggle_task_completion,
    week_board,
)


def healthz(request: HttpRequest) -> JsonResponse:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return JsonResponse({"status": "ok", "version": settings.APP_VERSION})


def _render_error(request: HttpRequest, *, status: int, code: str, template_name: str) -> HttpResponse:
    """Rendert eine Fehlerseite oder liefert JSON fuer API-Anfragen."""
    if is_api_request(request):
        return json_error(request, code, status=status)
    correlation_id = correlation_id_for_request(request)
    context = {
        "status_code": status,
        "error_code": code,
        "correlation_id": correlation_id,
        "error_label": label_for_code(code),
    }
    response = render(request, template_name, context, status=status)
    response[RESPONSE_CORRELATION_HEADER] = correlation_id
    return response


def bad_request(request, exception=None):
    return _render_error(
        request,
        status=400,
        code=ERROR_CODE_VALIDATION,
        template_name="errors/400.html",
    )


def permission_denied(request, exception=None):
    return _render_error(
        request,
        status=403,
        code=ERROR_CODE_FORBIDDEN,
        template_name="errors/403.html",
    )


def page_not_found(request, exception=None):
    return _render_error(
        request,
        status=404,
        code=ERROR_CODE_NOT_FOUND,
        template_name="errors/404.html",
    )


def rate_limited(request, exception=None):
    return _render_error(
        request,
        status=429,
        code=ERROR_CODE_RATE_LIMIT,
        template_name="errors/429.html",
    )


def server_error(request):
    correlation_id = log_exception(request, message="handler500")
    if is_api_request(request):
        return json_error(request, ERROR_CODE_SERVER_ERROR, status=500)
    response = render(
        request,
        "errors/500.html",
        {
            "status_code": 500,
            "error_code": ERROR_CODE_SERVER_ERROR,
            "correlation_id": correlation_id,
            "error_label": label_for_code(ERROR_CODE_SERVER_ERROR),
        },
        status=500,
    )
    response[RESPONSE_CORRELATION_HEADER] = correlation_id
    return response


def _static_url(path):
    return staticfiles_storage.url(path)


@require_GET
def web_manifest(request):
    icons = [
        {
            "src": _static_url("core/icons/icon-192.png"),
            "sizes": "192x192",
            "type": "image/png",
            "purpose": "any",
        },
        {
            "src": _static_url("core/icons/icon-512.png"),
            "sizes": "512x512",
            "type": "image/png",
            "purpose": "any",
        },
        {
            "src": _static_url("core/icons/icon-maskable-512.png"),
            "sizes": "512x512",
            "type": "image/png",
            "purpose": "maskable",
        },
    ]
    shortcut_icon = [{"src": _static_url("core/icons/icon-192.png"), "sizes": "192x192"}]
    shortcuts = [
        {"name": "Übersicht", "url": reverse("dashboard"), "icons": shortcut_icon},
        {"name": "Übergaben", "url": reverse("handover_list"), "icons": shortcut_icon},
        {"name": "Tagesaufgaben", "url": reverse("tasks_today"), "icons": shortcut_icon},
    ]
    payload = {
        "name": settings.APP_NAME,
        "short_name": settings.APP_NAME,
        "description": "Mobiles Wachbuch für die interne Organisation einer Rettungswache.",
        "lang": "de",
        "start_url": reverse("dashboard"),
        "scope": "/",
        "display": "standalone",
        "orientation": "any",
        "background_color": "#f7f9fc",
        "theme_color": "#0d47a1",
        "icons": icons,
        "shortcuts": shortcuts,
        "categories": ["productivity", "utilities"],
    }
    return JsonResponse(payload)


@require_GET
@never_cache
def service_worker(request):
    shell_assets = [
        _static_url("core/app.css"),
        _static_url("core/accessibility.css"),
        _static_url("core/demo.css"),
        _static_url("core/app.js"),
        _static_url("core/fonts/SourceSans3-Regular.woff2"),
        _static_url("core/fonts/SourceSans3-Semibold.woff2"),
        _static_url("core/fonts/SourceSans3-Bold.woff2"),
        _static_url("core/icons/icon-192.png"),
        _static_url("core/icons/icon-512.png"),
    ]
    response = render(
        request,
        "core/service_worker.js",
        {
            "sw_version": settings.APP_VERSION,
            "offline_url": reverse("offline"),
            "shell_assets": json.dumps(shell_assets),
        },
        content_type="application/javascript; charset=utf-8",
    )
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response


@require_GET
def privacy_notice(request):
    session_cookie_age = int(getattr(settings, "SESSION_COOKIE_AGE", 1209600))
    csrf_cookie_age = int(getattr(settings, "CSRF_COOKIE_AGE", 31449600))


    return render(request, "core/privacy.html", {
        "session_cookie": getattr(settings, "SESSION_COOKIE_NAME", "sessionid"),
        "session_cookie_name": getattr(settings, "SESSION_COOKIE_NAME", "sessionid"),
        "session_cookie_secure": bool(getattr(settings, "SESSION_COOKIE_SECURE", False)),
        "session_cookie_httponly": bool(getattr(settings, "SESSION_COOKIE_HTTPONLY", True)),
        "session_cookie_samesite": getattr(settings, "SESSION_COOKIE_SAMESITE", "Lax") or "nicht gesetzt (Browserstandard)",
        "session_cookie_age": session_cookie_age,
        "session_exact_hours": session_cookie_age // 3600 if session_cookie_age and session_cookie_age % 3600 == 0 else None,
        "session_expire_at_browser_close": bool(getattr(settings, "SESSION_EXPIRE_AT_BROWSER_CLOSE", False)),

        "csrf_use_sessions": bool(getattr(settings, "CSRF_USE_SESSIONS", False)),
        "csrf_cookie": getattr(settings, "CSRF_COOKIE_NAME", "csrftoken"),
        "csrf_cookie_name": getattr(settings, "CSRF_COOKIE_NAME", "csrftoken"),
        "csrf_cookie_secure": bool(getattr(settings, "CSRF_COOKIE_SECURE", False)),
        "csrf_cookie_httponly": bool(getattr(settings, "CSRF_COOKIE_HTTPONLY", False)),
        "csrf_cookie_samesite": getattr(settings, "CSRF_COOKIE_SAMESITE", "Lax") or "nicht gesetzt (Browserstandard)",
        "csrf_cookie_age": csrf_cookie_age,
        "csrf_exact_days": csrf_cookie_age // 86400 if csrf_cookie_age and csrf_cookie_age % 86400 == 0 else None,
    })


@require_GET
def offline(request):
    return render(request, "core/offline.html")


@require_POST
def demo_login(request):
    from .demo import demo_mode_enabled

    if not demo_mode_enabled():
        raise Http404
    user = User.objects.filter(username="demo-admin", is_active=True).first()
    if user is None:
        raise Http404
    from django.contrib.auth import login

    user.backend = "django.contrib.auth.backends.ModelBackend"
    login(request, user)
    return redirect("dashboard")


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


@membership_required(CONTENT_ROLES)
@station_module_required("calendar_enabled")
@require_GET
def calendar_event_ics(request, pk):
    event = get_object_or_404(
        CalendarEvent,
        pk=pk,
        station=request.membership.station,
    )
    stamp = timezone.now().strftime("%Y%m%dT%H%M%SZ")
    uid = f"wachbuch-event-{event.pk}@rettungswache-wachbuch"
    description = _ics_escape(event.description or "")
    body = "\r\n".join([
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Wachbuch//DE",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{stamp}",
        f"DTSTART:{_ics_datetime(event.starts_at)}",
        f"DTEND:{_ics_datetime(event.ends_at)}",
        f"SUMMARY:{_ics_escape(event.title)}",
        f"DESCRIPTION:{description}",
        "END:VEVENT",
        "END:VCALENDAR",
        "",
    ])
    filename = f"{slugify(event.title) or 'termin'}.ics"
    response = HttpResponse(body, content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = (
        f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"
    )
    return response


@require_GET
def landing(request):
    """Öffentliche Projektseite — Fachfunktionen erst nach Login und Mitgliedschaft."""
    if request.user.is_authenticated:
        membership = get_membership(request.user)
        if membership:
            if membership.role == Membership.Role.AUDITOR:
                return redirect("audit_log")
            return redirect("dashboard")
        return redirect("access")
    return render(request, "core/landing.html")


@require_GET
def vorfuehrung(request):
    """Öffentliche Vorführung ohne Fachdaten; bleibt auch nach Login erreichbar."""
    return render(request, "core/vorfuehrung.html")


@require_GET
def access(request):
    """Freigabehinweis für angemeldete Nutzer ohne aktive Mitgliedschaft."""
    if not request.user.is_authenticated:
        login_url = reverse("login")
        query = urlencode({"next": request.get_full_path()})
        return redirect(f"{login_url}?{query}")
    membership = get_membership(request.user)
    if membership:
        if membership.role == Membership.Role.AUDITOR:
            return redirect("audit_log")
        return redirect("dashboard")
    return render(request, "core/access.html")


DASHBOARD_PROFILES = {
    Station.Profile.RESCUE: {
        "eyebrow": _lazy("Rettungsdienst"),
        "handover_title": _lazy("Für die nächste Schicht"),
        "handover_link": _lazy("Alle Übergaben"),
        "asset_label": _lazy("Fahrzeuge/Geräte"),
        "task_label": _lazy("Wachaufgaben"),
        "cards": ("defects", "assets", "loans", "checklists", "tasks"),
    },
    Station.Profile.FIRE: {
        "eyebrow": _lazy("Feuerwehr"),
        "handover_title": _lazy("Für den nächsten Dienst"),
        "handover_link": _lazy("Alle Dienstübergaben"),
        "asset_label": _lazy("Einsatzmittel"),
        "task_label": _lazy("Wachdienst-Aufgaben"),
        "cards": ("defects", "assets", "checklists", "tasks"),
    },
    Station.Profile.POLICE: {
        "eyebrow": _lazy("Polizei"),
        "handover_title": _lazy("Für die nächste Dienstübergabe"),
        "handover_link": _lazy("Alle Dienstübergaben"),
        "asset_label": _lazy("Fahrzeuge/Geräte"),
        "task_label": _lazy("Dienststellen-Aufgaben"),
        "cards": ("defects", "assets", "loans", "checklists", "tasks"),
    },
    Station.Profile.GENERAL: {
        "eyebrow": _lazy("Organisationseinheit"),
        "handover_title": _lazy("Für die nächste Übergabe"),
        "handover_link": _lazy("Alle Übergaben"),
        "asset_label": _lazy("Geräte/Fahrzeuge"),
        "task_label": _lazy("Organisationsaufgaben"),
        "cards": ("defects", "assets", "loans", "checklists", "tasks"),
    },
}


def dashboard_profile(station):
    return DASHBOARD_PROFILES.get(station.organization_profile, DASHBOARD_PROFILES[Station.Profile.GENERAL])


@membership_required(CONTENT_ROLES)

def dashboard(request):
    station = request.membership.station
    now = timezone.now()
    active = prioritized_handovers(station)
    events = []
    if station.calendar_enabled:
        from .holidays import is_upcoming_agenda_item, station_agenda

        qs = CalendarEvent.objects.filter(
            station=station, ends_at__gte=now
        ).select_related("created_by").order_by("starts_at")
        agenda = station_agenda(station, qs, past_days=0, future_days=400)
        events = [item for item in agenda if is_upcoming_agenda_item(item, now=now)][:5]
    task_progress = None
    if station.tasks_enabled:
        ensure_default_station_tasks(station)
        task_progress = day_board(station, timezone.localdate())

    # Ein kleiner, stationsisolierter Lageblock: vorhandene Wachalltag-Daten
    # werden sichtbar gemacht, ohne neue Daten oder einen zweiten Workflow einzuführen.
    active_defects = Defect.objects.filter(station=station).exclude(status=Defect.Status.DONE)
    asset_attention = StationAsset.objects.filter(station=station).exclude(status=StationAsset.Status.READY)
    inventory_loans = InventoryItem.objects.filter(station=station, holder__isnull=False)
    due_checklists = ChecklistSchedule.objects.filter(
        station=station,
        checklist__is_active=True,
        due_next__isnull=False,
        due_next__lte=now,
    ) if station.checklists_enabled else ChecklistSchedule.objects.none()
    operations = {
        "defects_count": active_defects.count(),
        "urgent_defects_count": active_defects.filter(priority=Defect.Priority.URGENT).count(),
        "asset_attention_count": asset_attention.count(),
        "inventory_loans_count": inventory_loans.count(),
        "due_checklists_count": due_checklists.count(),
        "task_total": task_progress["total"] if task_progress else 0,
        "task_done": task_progress["done_count"] if task_progress else 0,
    }
    profile = dashboard_profile(station)
    card_definitions = {
        "defects": ("defects_web", _("Mängel"), _("offen"), operations["defects_count"]),
        "assets": ("assets_inventory_web", profile["asset_label"], _("nicht bereit"), operations["asset_attention_count"]),
        "loans": ("assets_inventory_web", _("Inventar"), _("ausgegeben"), operations["inventory_loans_count"]),
        "checklists": ("checklists", _("Checklisten"), _("fällig oder überfällig"), operations["due_checklists_count"]),
        "tasks": ("tasks_today", profile["task_label"], _("heute erledigt"), f'{operations["task_done"]}/{operations["task_total"]}'),
    }
    dashboard_cards = [
        {"url_name": card_definitions[key][0], "title": card_definitions[key][1], "subtitle": card_definitions[key][2], "value": card_definitions[key][3]}
        for key in profile["cards"]
        if (key not in {"checklists", "tasks"} or (key == "checklists" and station.checklists_enabled) or (key == "tasks" and station.tasks_enabled))
    ]
    context = {
        "dashboard_profile": profile,
        "dashboard_cards": dashboard_cards,
        "open_handovers": active[:5],
        "open_count": active.count(),
        "urgent_count": active.filter(priority=HandoverEntry.Priority.URGENT).count(),
        "events": events,
        "calendar_enabled": station.calendar_enabled,
        "checklists_enabled": station.checklists_enabled,
        "tasks_enabled": station.tasks_enabled,
        "task_progress": task_progress,
        "operations": operations,
    }
    return render(request, "core/dashboard.html", context)


def prioritized_handovers(station):
    return (
        HandoverEntry.objects.filter(station=station)
        .exclude(status=HandoverEntry.Status.DONE)
        .select_related("author")
        .annotate(
            priority_rank=Case(
                When(priority=HandoverEntry.Priority.URGENT, then=Value(0)),
                When(priority=HandoverEntry.Priority.IMPORTANT, then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            ),
            status_rank=Case(
                When(status=HandoverEntry.Status.OPEN, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            ),
        )
        .order_by("priority_rank", "status_rank", "-updated_at")
    )


def page_for(request, queryset, per_page=20):
    return Paginator(queryset, per_page).get_page(request.GET.get("seite"))


def upcoming_birthdays(station):
    today = timezone.localdate()
    preferences = list(
        BirthdayPreference.objects.filter(
            station=station,
            is_visible=True,
            day__isnull=False,
            month__isnull=False,
            user__is_active=True,
            user__station_memberships__station=station,
            user__station_memberships__is_active=True,
        )
        .select_related("user")
        .distinct()
    )

    def next_date(item):
        for year in range(today.year, today.year + 5):
            try:
                candidate = date(year, item.month, item.day)
            except ValueError:
                continue
            if candidate >= today:
                return candidate
        return date.max

    return sorted(preferences, key=next_date)


@membership_required(CONTENT_ROLES)
def handover_list(request):
    scope = request.GET.get("ansicht", "aktiv")
    if scope == "archiv":
        handovers = HandoverEntry.objects.filter(
            station=request.membership.station,
            status=HandoverEntry.Status.DONE,
        ).select_related("author").order_by("-completed_at", "-updated_at")
    else:
        scope = "dringend" if scope == "dringend" else "aktiv"
        handovers = prioritized_handovers(request.membership.station)
        if scope == "dringend":
            handovers = handovers.filter(priority=HandoverEntry.Priority.URGENT)
    return render(request, "core/handover_list.html", {
        "page_obj": page_for(request, handovers),
        "scope": scope,
    })


@membership_required(CONTENT_ROLES)
@require_http_methods(["GET", "POST"])
def handover_create(request):
    form = HandoverForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        uploads, upload_error = read_uploads(request.FILES.getlist("attachments"))
        if upload_error:
            messages.error(request, upload_error)
        else:
            handover = create_handover(form, request.membership)
            for upload, raw in uploads:
                HandoverAttachment.objects.create(
                    handover=handover,
                    station=request.membership.station,
                    filename=upload.name[:180],
                    content_type=upload.content_type,
                    data=raw,
                    size=len(raw),
                    uploaded_by=request.user,
                )
            messages.success(request, _("Übergabe wurde angelegt."))
            return redirect("handover_detail", pk=handover.pk)
    return render(request, "core/handover_form.html", {"form": form})


@membership_required(CONTENT_ROLES)
@require_http_methods(["GET", "POST"])
def handover_detail(request, pk):
    handover = get_object_or_404(
        HandoverEntry.objects.select_related("author").prefetch_related("revisions__changed_by"),
        pk=pk,
        station=request.membership.station,
    )
    if request.method == "POST" and request.POST.get("action") == "upload":
        upload = request.FILES.get("attachment")
        if upload is None:
            messages.error(request, _("Bitte eine Datei auswählen."))
        elif upload.content_type not in ALLOWED_ATTACHMENT_TYPES:
            messages.error(request, _("Erlaubt sind JPEG, PNG, WebP und PDF."))
        elif upload.size > MAX_ATTACHMENT_BYTES:
            messages.error(request, _("Datei darf maximal 5 MiB groß sein."))
        elif handover.attachments.count() >= MAX_ATTACHMENTS_PER_HANDOVER:
            messages.error(request, _("Mehr Anhänge sind nicht möglich."))
        else:
            raw = upload.read()
            if not attachment_is_valid(raw, upload.content_type):
                messages.error(request, _("Datei ist kein gültiges Bild und kein lesbares PDF."))
            else:
                with transaction.atomic():
                    attachment = HandoverAttachment.objects.create(
                        handover=handover,
                        station=request.membership.station,
                        filename=upload.name[:180],
                        content_type=upload.content_type,
                        data=raw,
                        size=len(raw),
                        uploaded_by=request.user,
                    )
                    audit(request.user, request.membership.station, "handover.attachment_added", handover, {
                        "attachment_id": attachment.pk,
                        "size": len(raw),
                    })
                messages.success(request, _("Anhang wurde hinzugefügt."))
                return redirect("handover_detail", pk=pk)
    can_change_status = request.membership.role in {
        Membership.Role.SHIFT_LEAD,
        Membership.Role.ADMIN,
    }
    return render(request, "core/handover_detail.html", {
        "handover": handover,
        "status_form": HandoverStatusForm(instance=handover),
        "can_change_status": can_change_status,
        "can_edit_content": can_change_status,
        "attachments": handover.attachments.select_related("uploaded_by").all(),
        "max_upload_mb": MAX_ATTACHMENT_BYTES // (1024 * 1024),
    })


@membership_required({Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN})
@require_http_methods(["GET", "POST"])
def handover_edit(request, pk):
    handover = get_object_or_404(HandoverEntry, pk=pk, station=request.membership.station)
    form = HandoverEditForm(request.POST or None, instance=handover)
    if request.method == "POST" and form.is_valid():
        update_handover_content(handover, form.cleaned_data, request.membership)
        messages.success(request, _("Übergabe wurde korrigiert (neue Revision)."))
        return redirect("handover_detail", pk=pk)
    return render(request, "core/handover_edit.html", {
        "form": form,
        "handover": handover,
    })


@membership_required({Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN})
@require_POST
def handover_status(request, pk):
    handover = get_object_or_404(HandoverEntry, pk=pk, station=request.membership.station)
    form = HandoverStatusForm(request.POST, instance=handover)
    if form.is_valid():
        change_handover_status(handover, form.cleaned_data["status"], request.membership)
        messages.success(request, _("Status wurde aktualisiert."))
    else:
        messages.error(request, _("Status konnte nicht aktualisiert werden."))
    return redirect("handover_detail", pk=pk)


@membership_required(CONTENT_ROLES)
@station_module_required("calendar_enabled")
def calendar_view(request):
    station = request.membership.station
    can_create = request.membership.role in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN}
    from .holidays import station_agenda

    qs = CalendarEvent.objects.filter(
        station=station,
        ends_at__gte=timezone.now() - timedelta(days=1),
    ).select_related("created_by")
    agenda = station_agenda(station, qs)
    return render(request, "core/calendar.html", {
        "page_obj": page_for(request, agenda, 20),
        "can_create": can_create,
        "holidays_enabled": station.holidays_enabled,
        "waste_enabled": station.waste_calendar_enabled,
    })


@membership_required({Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN})
@station_module_required("calendar_enabled")
@require_http_methods(["GET", "POST"])
def calendar_create(request):
    form = CalendarEventForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            event = form.save(commit=False)
            event.station = request.membership.station
            event.created_by = request.user
            event.full_clean()
            event.save()
            audit(request.user, request.membership.station, "calendar.created", event, {"fields": [
                "title", "description", "starts_at", "ends_at"
            ]})
        messages.success(request, _("Termin wurde angelegt."))
        return redirect("calendar")
    return render(request, "core/calendar_form.html", {"form": form})


@membership_required(CONTENT_ROLES)
@station_module_required("birthdays_enabled")
def birthdays(request):
    return render(request, "core/birthdays.html", {
        "birthdays": upcoming_birthdays(request.membership.station),
    })


@membership_required(CONTENT_ROLES)
@station_module_required("birthdays_enabled")
@require_http_methods(["GET", "POST"])
def birthday_settings(request):
    preference, _created = BirthdayPreference.objects.get_or_create(
        user=request.user,
        station=request.membership.station,
    )
    form = BirthdayForm(request.POST or None, instance=preference)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            saved = form.save()
            audit(request.user, request.membership.station, "birthday.preference_changed", saved, {
                "fields": ["day", "month", "is_visible"]
            })
        messages.success(request, _("Geburtstagseinstellung wurde gespeichert."))
        return redirect("birthdays")
    return render(request, "core/birthday_settings.html", {
        "form": form,
    })


@membership_required(CONTENT_ROLES)
@station_module_required("coffee_enabled")
def coffee(request):
    station = request.membership.station
    can_book = request.membership.role in {Membership.Role.CASHIER, Membership.Role.ADMIN}
    all_entries = CoffeeEntry.objects.filter(station=station).select_related(
        "member", "created_by", "correction_of"
    ).prefetch_related("corrections")
    visible_entries = all_entries if can_book else all_entries.filter(member=request.user)
    total_cents = all_entries.aggregate(total=Sum("amount_cents"))["total"] or 0
    own_cents = all_entries.filter(member=request.user).aggregate(total=Sum("amount_cents"))["total"] or 0
    return render(request, "core/coffee.html", {
        "page_obj": page_for(request, visible_entries, 25),
        "total_euros": total_cents / 100,
        "own_euros": own_cents / 100,
        "can_book": can_book,
        "station": station,
    })


@membership_required({Membership.Role.CASHIER, Membership.Role.ADMIN})
@station_module_required("coffee_enabled")
@require_http_methods(["GET", "POST"])
def coffee_create(request):
    station = request.membership.station
    form = CoffeeEntryForm(request.POST or None, station=station)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            entry = CoffeeEntry.objects.create(
                station=station,
                member=form.cleaned_data["member"],
                amount_cents=form.amount_cents(),
                reason=form.cleaned_data["reason"],
                created_by=request.user,
            )
            audit(request.user, station, "coffee.entry_created", entry, {
                "fields": ["member", "amount_cents", "reason"]
            })
        messages.success(request, _("Kassenbuchung wurde erfasst."))
        return redirect("coffee")
    return render(request, "core/coffee_form.html", {"form": form})


@membership_required({Membership.Role.CASHIER, Membership.Role.ADMIN})
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
                    created_by=request.user,
                    correction_of=original,
                )
                audit(request.user, original.station, "coffee.entry_corrected", correction, {
                    "fields": ["reason", "correction_of"]
                })
        except IntegrityError:
            messages.error(request, _("Diese Buchung wurde bereits korrigiert."))
            return redirect("coffee")
        messages.success(request, _("Gegenbuchung wurde erfasst."))
        return redirect("coffee")
    return render(request, "core/coffee_correction.html", {
        "form": form,
        "original": original,
        "correction_euros": -original.amount_cents / 100,
    })


@membership_required(CONTENT_ROLES)
@station_module_required("feeds_enabled")
def feeds(request):
    feed_type = "verkehr" if request.GET.get("typ") == "verkehr" else "meldungen"
    kind = FeedSource.Kind.CLOSURE_CSV if feed_type == "verkehr" else FeedSource.Kind.NEWS_RSS
    items = FeedItem.objects.filter(
        source__kind=kind,
        source__is_enabled=True,
    ).select_related("source")
    return render(request, "core/feeds.html", {
        "page_obj": page_for(request, items, 25),
        "feed_type": feed_type,
        "sources": FeedSource.objects.filter(is_enabled=True, kind=kind),
    })


def _parse_work_date(raw_value):
    if not raw_value:
        return timezone.localdate()
    try:
        return date.fromisoformat(raw_value)
    except ValueError:
        return timezone.localdate()


@membership_required(CONTENT_ROLES)
@station_module_required("tasks_enabled")
def tasks_today(request):
    station = request.membership.station
    ensure_default_station_tasks(station)
    work_date = _parse_work_date(request.GET.get("tag"))
    board = day_board(station, work_date)
    can_manage = request.membership.role in {
        Membership.Role.SHIFT_LEAD,
        Membership.Role.ADMIN,
    }
    return render(request, "core/tasks_today.html", {
        "board": board,
        "can_manage": can_manage,
        "prev_date": work_date - timedelta(days=1),
        "next_date": work_date + timedelta(days=1),
        "is_today": work_date == timezone.localdate(),
    })


@membership_required(CONTENT_ROLES)
@station_module_required("tasks_enabled")
def tasks_week(request):
    station = request.membership.station
    ensure_default_station_tasks(station)
    pivot = _parse_work_date(request.GET.get("woche"))
    board = week_board(station, pivot)
    can_manage = request.membership.role in {
        Membership.Role.SHIFT_LEAD,
        Membership.Role.ADMIN,
    }
    return render(request, "core/tasks_week.html", {
        "board": board,
        "can_manage": can_manage,
        "prev_week": board["monday"] - timedelta(days=7),
        "next_week": board["monday"] + timedelta(days=7),
    })


@membership_required(CONTENT_ROLES)
@station_module_required("tasks_enabled")
@require_POST
def task_toggle(request, pk):
    station = request.membership.station
    task = get_object_or_404(StationTask, pk=pk, station=station, is_active=True)
    work_date = _parse_work_date(request.POST.get("tag"))
    mark_done = request.POST.get("erledigt") == "1"
    if not task.applies_to_date(work_date):
        messages.error(request, _("Diese Aufgabe gilt nicht für den gewählten Tag."))
    else:
        toggle_task_completion(
            task=task,
            membership=request.membership,
            work_date=work_date,
            mark_done=mark_done,
        )
        if mark_done:
            messages.success(request, _("Aufgabe wurde als erledigt markiert."))
        else:
            messages.success(request, _("Aufgabe wurde wieder geöffnet."))
    next_url = request.POST.get("next") or reverse("tasks_today")
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = reverse("tasks_today")
    return redirect(next_url)


@membership_required({Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN})
@station_module_required("tasks_enabled")
def tasks_manage(request):
    station = request.membership.station
    ensure_default_station_tasks(station)
    tasks = StationTask.objects.filter(station=station)
    return render(request, "core/tasks_manage.html", {
        "page_obj": page_for(request, tasks, 40),
    })


@membership_required({Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN})
@station_module_required("tasks_enabled")
@require_http_methods(["GET", "POST"])
def task_create(request):
    form = StationTaskForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            task = form.save(commit=False)
            task.station = request.membership.station
            task.full_clean()
            task.save()
            audit(request.user, request.membership.station, "station_task.created", task, {
                "fields": ["title", "band", "weekday", "notes", "is_active"],
            })
        messages.success(request, _("Aufgabe wurde angelegt."))
        return redirect("tasks_manage")
    return render(request, "core/task_form.html", {
        "form": form,
        "page_title": "Aufgabe anlegen",
    })


@membership_required({Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN})
@station_module_required("tasks_enabled")
@require_http_methods(["GET", "POST"])
def task_edit(request, pk):
    task = get_object_or_404(StationTask, pk=pk, station=request.membership.station)
    form = StationTaskForm(request.POST or None, instance=task)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            saved = form.save(commit=False)
            saved.full_clean()
            saved.save()
            audit(request.user, request.membership.station, "station_task.updated", saved, {
                "fields": form.changed_data,
            })
        messages.success(request, _("Aufgabe wurde gespeichert."))
        return redirect("tasks_manage")
    return render(request, "core/task_form.html", {
        "form": form,
        "page_title": "Aufgabe bearbeiten",
        "task": task,
    })


@membership_required(CONTENT_ROLES)
@station_module_required("checklists_enabled")
def checklists(request):
    station = request.membership.station
    checklists_qs = list(
        Checklist.objects.filter(station=station, is_active=True).prefetch_related("items")
    )
    latest = {}
    for completion in (
        ChecklistCompletion.objects.filter(station=station)
        .select_related("completed_by", "checklist")
        .order_by("checklist_id", "-created_at")
    ):
        latest.setdefault(completion.checklist_id, completion)
    for checklist in checklists_qs:
        checklist.latest_completion = latest.get(checklist.id)
    return render(request, "core/checklists.html", {"checklists": checklists_qs})


@membership_required(CONTENT_ROLES)
@station_module_required("checklists_enabled")
@require_POST
def checklist_complete(request, pk):
    station = request.membership.station
    checklist = get_object_or_404(Checklist, pk=pk, station=station, is_active=True)
    with transaction.atomic():
        completion = ChecklistCompletion.objects.create(
            station=station,
            checklist=checklist,
            completed_by=request.user,
            note=(request.POST.get("note") or "")[:300],
        )
        audit(request.user, station, "checklist.completed", completion, {
            "fields": ["checklist", "note"],
        })
    messages.success(request, _("Checkliste wurde als erledigt vermerkt."))
    return redirect("checklists")


def more(request):
    return render(request, "core/more.html")


@membership_required({Membership.Role.ADMIN})
def team(request):
    station = request.membership.station
    members = Membership.objects.filter(station=station).select_related("user")
    pending_registrations = pending_registrations_for_station(station)
    pending_count = users_awaiting_station_access(station).count()
    return render(request, "core/team.html", {
        "page_obj": page_for(request, members, 25),
        "pending_count": pending_count,
        "pending_registrations": pending_registrations,
    })


@membership_required({Membership.Role.ADMIN})
@require_http_methods(["GET", "POST"])
def team_user_create(request):
    """Master-Admin creates a user account and grants station membership."""
    form = MasterAdminCreateUserForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        station = request.membership.station
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=form.cleaned_data["username"],
                    password=form.cleaned_data["password1"],
                    first_name=form.cleaned_data.get("first_name") or "",
                    last_name=form.cleaned_data.get("last_name") or "",
                )
                from .models import UserProfile

                UserProfile.for_user(user)
                membership = Membership.objects.create(
                    user=user,
                    station=station,
                    role=form.cleaned_data["role"],
                )
                audit(request.user, station, "membership.user_created", membership, {
                    "fields": ["user", "role", "is_active"],
                })
        except IntegrityError:
            form.add_error("username", "Dieses Konto konnte nicht angelegt werden.")
        else:
            messages.success(
                request,
                f"Benutzer {user.username} angelegt und freigegeben. "
                "Bitte Startpasswort persönlich übergeben.",
            )
            return redirect("team")
    return render(request, "core/team_user_create.html", {"form": form})


@membership_required({Membership.Role.ADMIN})
@require_http_methods(["GET", "POST"])
def team_create(request):
    form = MembershipAssignmentForm(request.POST or None, station=request.membership.station)
    if request.method == "POST" and form.is_valid():
        station = request.membership.station
        user = form.cleaned_data["user"]
        role = form.cleaned_data["role"]
        try:
            with transaction.atomic():
                membership = (
                    Membership.objects.select_for_update()
                    .filter(user=user, station=station)
                    .first()
                )
                if membership is None:
                    membership = Membership.objects.create(
                        user=user,
                        station=station,
                        role=role,
                    )
                    action = "membership.created"
                    success = "Mitgliedschaft wurde freigegeben."
                elif membership.is_active:
                    form.add_error("user", "Dieses Konto besitzt bereits eine aktive Mitgliedschaft.")
                    membership = None
                else:
                    membership.role = role
                    membership.is_active = True
                    membership.save(update_fields=["role", "is_active"])
                    action = "membership.reactivated"
                    success = "Mitgliedschaft wurde erneut freigegeben."
                if membership is not None:
                    audit(request.user, station, action, membership, {
                        "fields": ["user", "role", "is_active"]
                    })
                    from .models import RegistrationRequest

                    RegistrationRequest.objects.filter(
                        user=user,
                        status=RegistrationRequest.Status.PENDING,
                        preferred_station=station,
                    ).update(
                        status=RegistrationRequest.Status.APPROVED,
                        reviewed_at=timezone.now(),
                        reviewed_by=request.user,
                    )
        except IntegrityError:
            form.add_error("user", "Dieses Konto kann derzeit nicht freigegeben werden.")
            membership = None
        if membership is not None and not form.errors:
            messages.success(request, success)
            return redirect("team")
    return render(request, "core/team_form.html", {
        "form": form,
    })


@membership_required({Membership.Role.ADMIN})
@require_http_methods(["GET", "POST"])
def membership_update(request, pk):
    membership = get_object_or_404(Membership, pk=pk, station=request.membership.station)
    form = MembershipEditForm(request.POST or None, membership=membership)
    if request.method == "POST" and form.is_valid():
        new_role = form.cleaned_data["role"]
        new_active = form.cleaned_data["is_active"]
        removes_admin = (
            membership.role == Membership.Role.ADMIN
            and membership.is_active
            and (new_role != Membership.Role.ADMIN or not new_active)
        )
        if membership.user_id == request.user.id and removes_admin:
            form.add_error("role", "Die eigene Master-Admin-Rolle kann hier nicht entzogen werden.")
        with transaction.atomic():
            if not form.errors:
                membership = Membership.objects.select_for_update().get(pk=membership.pk)
                if removes_admin:
                    admin_ids = list(Membership.objects.select_for_update().filter(
                        station=membership.station,
                        role=Membership.Role.ADMIN,
                        is_active=True,
                    ).values_list("pk", flat=True))
                    if len(admin_ids) <= 1:
                        form.add_error("role", "Mindestens ein aktiver Admin muss erhalten bleiben.")
            if not form.errors:
                before = {
                    "role": membership.role,
                    "is_active": membership.is_active,
                }
                was_active = membership.is_active
                membership.role = form.cleaned_data["role"]
                membership.is_active = form.cleaned_data["is_active"]
                membership.save(update_fields=["role", "is_active"])
                if before["role"] != membership.role or before["is_active"] != membership.is_active:
                    from .qr_login import revoke_open_requests_for_user
                    revoke_open_requests_for_user(membership.user)
                if was_active and not membership.is_active:
                    clear_birthday_on_exit(membership.user, membership.station, request.user)
                audit(request.user, request.membership.station, "membership.updated", membership, {
                    "fields": ["role", "is_active"],
                    "changes": structure_changes(before, {
                        "role": membership.role,
                        "is_active": membership.is_active,
                    }),
                })
                messages.success(request, _("Mitgliedschaft wurde aktualisiert."))
        if not form.errors:
            return redirect("team")
    return render(request, "core/membership_form.html", {
        "form": form,
        "edited_membership": membership,
    })


@membership_required({Membership.Role.ADMIN})
@require_http_methods(["GET", "POST"])
def presentation_settings(request):
    """Bereiche in die Leiste holen bzw. unter 'Mehr' belassen und sortieren."""
    from .navigation import CATALOG, MORE_ITEMS, PINNED, nav_config, parse_order_more

    station = request.membership.station
    if request.method == "POST":
        order = [part.strip() for part in (request.POST.get("order") or "").split(",") if part.strip()]
        order = [key for key in order if key in CATALOG]
        if not order:
            order = list(CATALOG.keys())
        primary = [
            key for key in order
            if key in PINNED or request.POST.get(f"inbar_{key}")
        ]
        # Alles, was nicht oben steht, erscheint unter „Mehr“ – in derselben
        # Reihenfolge wie in der Liste.
        below = [key for key in order if key not in primary]
        station.nav_order = ",".join(primary)
        station.more_order = ",".join(parse_order_more(",".join(below)))
        station.save(update_fields=["nav_order", "more_order"])
        messages.success(request, _("Darstellung gespeichert."))
        return redirect("presentation_settings")

    config = nav_config(station)
    by_key = {option["key"]: option for option in config["options"]}
    rows = [by_key[key] for key in config["sequence"] if key in by_key]
    rows += [option for option in config["options"] if not option["selected"]]

    return render(request, "core/presentation.html", {"rows": rows})


@membership_required({Membership.Role.ADMIN})
@require_http_methods(["GET", "POST"])
def station_settings(request):
    station = request.membership.station
    if request.method == "POST":
        post_data = request.POST.copy()
        post_data.setdefault("organization_profile", station.organization_profile)
    else:
        post_data = None
    form = StationSettingsForm(post_data, request.FILES or None, instance=station)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            # Nur echte Modellfelder protokollieren; Upload-Felder wie die
            # ICS-Datei existieren nicht auf der Station.
            model_fields = set(form._meta.fields)
            changed_fields = [
                field for field in form.changed_data if field in model_fields
            ]
            # form.initial keeps values from before ModelForm._post_clean mutated instance.
            before = {field: form.initial.get(field) for field in changed_fields}
            saved = form.save()
            after = {field: getattr(saved, field) for field in changed_fields}
            audit(request.user, station, "station.settings_updated", saved, {
                "fields": changed_fields,
                "changes": structure_changes(before, after),
            })
            upload = form.cleaned_data.get("waste_calendar_file")
            imported = None
            if upload:
                if not saved.waste_calendar_enabled:
                    saved.waste_calendar_enabled = True
                    saved.save(update_fields=["waste_calendar_enabled"])
                imported = store_station_waste(saved, upload.read())
        messages.success(request, _("Einstellungen wurden gespeichert."))
        if imported is not None:
            messages.success(request, _("Müllkalender übernommen: %(count)s Termine.") % {"count": imported})
        return redirect("station_settings")
    return render(request, "core/station_settings.html", {"form": form})


@membership_required({Membership.Role.AUDITOR, Membership.Role.ADMIN})
def audit_log(request):
    events = AuditEvent.objects.filter(station=request.membership.station).select_related("actor")
    return render(request, "core/audit_log.html", {"page_obj": page_for(request, events, 30)})


@require_http_methods(["GET", "POST"])
def mfa_verify(request):
    if not mfa_enabled():
        return redirect("login")
    pending_id = request.session.get("mfa_pending_user_id")
    if not pending_id:
        return redirect("login")
    user = get_object_or_404(User, pk=pending_id, is_active=True)
    from .mfa import user_has_totp
    from .webauthn_auth import user_has_passkey, webauthn_enabled

    has_totp = user_has_totp(user)
    has_passkey = webauthn_enabled() and user_has_passkey(user)
    if not has_totp and not has_passkey:
        request.session.pop("mfa_pending_user_id", None)
        return redirect("login")
    form = TotpConfirmForm(request.POST or None) if has_totp else None
    if has_totp and request.method == "POST" and form.is_valid():
        device = TotpDevice.objects.filter(user=user, is_confirmed=True).first()
        failures = int(request.session.get("mfa_failures", 0))
        if device and verify_totp(device, form.cleaned_data["token"]):
            from django.contrib.auth import login

            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            next_url = request.session.pop("mfa_next", None) or reverse("landing")
            request.session.pop("mfa_pending_user_id", None)
            request.session.pop("mfa_failures", None)
            return redirect(next_url)
        failures += 1
        request.session["mfa_failures"] = failures
        if failures >= 8:
            request.session.pop("mfa_pending_user_id", None)
            request.session.pop("mfa_next", None)
            request.session.pop("mfa_failures", None)
            messages.error(request, _("Zu viele Fehlversuche. Bitte erneut anmelden."))
            return redirect("login")
        form.add_error("token", _("Code ungültig oder abgelaufen."))
    return render(request, "registration/mfa_verify.html", {
        "form": form,
        "has_totp": has_totp,
        "has_passkey": has_passkey,
    })


@require_http_methods(["GET", "POST"])
def mfa_setup(request):
    if not mfa_enabled():
        raise Http404
    if not request.user.is_authenticated:
        return redirect(f"{reverse('login')}?{urlencode({'next': reverse('mfa_setup')})}")
    from .webauthn_auth import user_has_passkey, webauthn_enabled

    existing = TotpDevice.objects.filter(user=request.user, is_confirmed=True).first()
    passkeys = list(WebAuthnCredential.objects.filter(user=request.user)) if webauthn_enabled() else []
    if request.method == "GET" and (existing or passkeys):
        return render(request, "registration/mfa_manage.html", {
            "device": existing,
            "passkeys": passkeys,
            "webauthn_enabled": webauthn_enabled(),
        })
    device = create_pending_device(request.user)
    form = TotpConfirmForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if confirm_device(device, form.cleaned_data["token"]):
            messages.success(request, _("Zwei-Faktor-Authentifizierung ist aktiv."))
            return redirect("mfa_setup")
        form.add_error("token", _("Code ungültig. Bitte erneut scannen und prüfen."))
        device = TotpDevice.objects.get(pk=device.pk)
    return render(request, "registration/mfa_setup.html", {
        "form": form,
        "secret": totp_plaintext(device),
        "provisioning_uri": provisioning_uri(device),
        "webauthn_enabled": webauthn_enabled(),
        "passkeys": passkeys,
    })


@require_POST
def mfa_disable(request):
    if not mfa_enabled() or not request.user.is_authenticated:
        return redirect("login")
    if mfa_required():
        messages.error(request, _("MFA ist für diese Installation vorgeschrieben."))
        return redirect("mfa_setup")
    from .mfa import disable_all_mfa

    disable_all_mfa(request.user)
    messages.success(request, _("Zwei-Faktor-Authentifizierung wurde deaktiviert."))
    return redirect("more")


# --- Pinnwand (digitale Aushaenge) -----------------------------------------

PINBOARD_MANAGE_ROLES = {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN}


@membership_required(CONTENT_ROLES)
@station_module_required("pinboard_enabled")
def pinboard(request):
    station = request.membership.station
    notes = (
        PinboardNote.objects.filter(station=station, is_archived=False)
        .select_related("author")
        .order_by("-is_pinned", "-updated_at")
    )
    can_manage = request.membership.role in PINBOARD_MANAGE_ROLES
    return render(request, "core/pinboard.html", {
        "page_obj": page_for(request, notes),
        "can_manage": can_manage,
    })


@membership_required(CONTENT_ROLES)
@station_module_required("pinboard_enabled")
@require_http_methods(["GET", "POST"])
def pinboard_create(request):
    form = PinboardNoteForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        uploads, upload_error = read_uploads(request.FILES.getlist("attachments"))
        if upload_error:
            messages.error(request, upload_error)
            return render(request, "core/pinboard_form.html", {"form": form, "page_title": "Aushang anlegen"})
        note = create_pinboard_note(
            station=request.membership.station,
            author=request.user,
            title=form.cleaned_data["title"],
            body=form.cleaned_data["body"],
            category=form.cleaned_data["category"],
        )
        for upload, raw in uploads:
            PinboardAttachment.objects.create(
                note=note,
                station=request.membership.station,
                filename=upload.name[:180],
                content_type=upload.content_type,
                data=raw,
                size=len(raw),
                uploaded_by=request.user,
            )
        messages.success(request, _("Aushang wurde angelegt."))
        return redirect("pinboard")
    return render(request, "core/pinboard_form.html", {
        "form": form,
        "page_title": "Aushang anlegen",
    })


@membership_required(CONTENT_ROLES)
@station_module_required("pinboard_enabled")
@require_http_methods(["GET", "POST"])
def pinboard_edit(request, pk):
    note = get_object_or_404(PinboardNote, pk=pk, station=request.membership.station, is_archived=False)
    if not (request.membership.role in PINBOARD_MANAGE_ROLES or note.author_id == request.user.id):
        raise PermissionDenied
    form = PinboardNoteForm(request.POST or None, instance=note)
    if request.method == "POST" and form.is_valid():
        update_pinboard_note(
            note,
            actor=request.user,
            title=form.cleaned_data["title"],
            body=form.cleaned_data["body"],
            category=form.cleaned_data["category"],
        )
        messages.success(request, _("Aushang wurde aktualisiert."))
        return redirect("pinboard")
    return render(request, "core/pinboard_form.html", {
        "form": form,
        "page_title": "Aushang bearbeiten",
    })


@membership_required(PINBOARD_MANAGE_ROLES)
@station_module_required("pinboard_enabled")
@require_POST
def pinboard_pin(request, pk):
    note = get_object_or_404(PinboardNote, pk=pk, station=request.membership.station, is_archived=False)
    set_pinboard_pin(note, actor=request.user, pinned=not note.is_pinned)
    return redirect("pinboard")


@membership_required(CONTENT_ROLES)
@station_module_required("pinboard_enabled")
@require_POST
def pinboard_archive(request, pk):
    note = get_object_or_404(PinboardNote, pk=pk, station=request.membership.station, is_archived=False)
    if not (request.membership.role in PINBOARD_MANAGE_ROLES or note.author_id == request.user.id):
        raise PermissionDenied
    archive_pinboard_note(note, actor=request.user)
    messages.success(request, _("Aushang wurde archiviert."))
    return redirect("pinboard")
