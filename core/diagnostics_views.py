from django.conf import settings
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from core.access import membership_required
from core.diagnostics import CORRELATION_ID_RE
from core.diagnostics_export import (
    build_support_report,
    retained_error_events,
    support_filename,
)
from core.models import Membership

ERROR_VIEW_ROLES = {Membership.Role.ADMIN}
ERROR_PAGE_SIZE = 25


@membership_required(ERROR_VIEW_ROLES)
@require_GET
@never_cache
def error_events(request):
    station = request.membership.station
    queryset = retained_error_events(station=station)

    raw_correlation = request.GET.get("korrelation", "").strip()
    correlation = ""
    if raw_correlation and CORRELATION_ID_RE.fullmatch(raw_correlation):
        correlation = raw_correlation
        queryset = queryset.filter(correlation_id=correlation)

    paginator = Paginator(queryset, ERROR_PAGE_SIZE)
    page_number = request.GET.get("seite")
    page_obj = paginator.get_page(page_number)

    retention_days = int(getattr(settings, "ERROR_EVENT_RETENTION_DAYS", 30))

    context = {
        "page_obj": page_obj,
        "correlation": correlation,
        "retention_days": retention_days,
    }
    return render(request, "core/diagnostics_events.html", context)


@membership_required(ERROR_VIEW_ROLES)
@require_GET
@never_cache
def support_export(request):
    station = request.membership.station
    content = build_support_report(station=station)
    filename = support_filename()

    response = HttpResponse(content, content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "no-store, private"
    response["Pragma"] = "no-cache"
    response["X-Content-Type-Options"] = "nosniff"
    return response
