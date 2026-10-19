from urllib.parse import quote

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from .access import CONTENT_ROLES, membership_required
from .wachalltag_models import DefectAttachment


@membership_required(allowed_roles=CONTENT_ROLES)
@require_GET
def defect_attachment(request, pk):
    item = get_object_or_404(
        DefectAttachment,
        pk=pk,
        station=request.membership.station,
    )
    response = HttpResponse(bytes(item.data), content_type=item.content_type)
    response["Content-Length"] = str(item.size)
    response["Content-Disposition"] = f"inline; filename*=UTF-8''{quote(item.filename)}"
    response["Cache-Control"] = "private, no-store"
    return response

@membership_required(allowed_roles=CONTENT_ROLES)
@require_GET
def handover_attachment(request, pk):
    from .models import HandoverAttachment

    item = get_object_or_404(
        HandoverAttachment,
        pk=pk,
        station=request.membership.station,
    )
    response = HttpResponse(bytes(item.data), content_type=item.content_type)
    response["Content-Length"] = str(item.size)
    response["Content-Disposition"] = f"inline; filename*=UTF-8''{quote(item.filename)}"
    response["Cache-Control"] = "private, no-store"
    return response
