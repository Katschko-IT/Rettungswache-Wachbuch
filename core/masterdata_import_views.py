"""Ansichten für den CSV-Stammdatenimport (nur Master-Admins).

Die Datei wird beim Prüfen nur im Arbeitsspeicher gelesen (höchstens 1 MiB,
größere Dateien werden abgewiesen) und nie gespeichert, auch nicht in der
Sitzung. Die Vorschau trägt den Inhalt als Base64 im Formular zurück, zusammen
mit der SHA-256-Prüfsumme und einem signierten Token (Wache, Person, Art,
Prüfsumme; eine Stunde gültig). Beim Bestätigen wird alles erneut geprüft.
Antworten auf POST sind ``no-store``. Normaler CSRF-Schutz gilt unverändert.
"""
from __future__ import annotations

import base64
import binascii
import hashlib

from django import forms
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils.cache import add_never_cache_headers
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_GET, require_http_methods

from .access import membership_required
from .masterdata_import import (
    MAX_FILE_BYTES,
    MAX_PAYLOAD_CHARS,
    available_kinds,
    get_kind,
    make_token,
    next_kind,
    run_import,
    template_csv,
    token_plan,
)
from .models import Membership
from .warehouse_models import StorageLocation

ADMIN_ONLY = {Membership.Role.ADMIN}


class ImportUploadForm(forms.Form):
    file = forms.FileField(label=gettext_lazy("CSV-Datei"))


class ImportCommitForm(forms.Form):
    payload = forms.CharField(max_length=MAX_PAYLOAD_CHARS, strip=False)
    digest = forms.RegexField(regex=r"^[0-9a-f]{64}$", max_length=64)
    token = forms.CharField(max_length=500)


def _kind_or_404(request, slug: str):
    kind = get_kind(slug, request.membership.station)
    if kind is None:
        raise Http404
    return kind


def _limits() -> dict:
    return {"max_mb": MAX_FILE_BYTES // 1_048_576}


@membership_required(allowed_roles=ADMIN_ONLY)
@require_GET
def masterdata_import(request):
    station = request.membership.station
    kinds = [
        {"kind": kind, "existing": kind.handler_cls.existing_count(station)}
        for kind in available_kinds(station)
    ]
    return render(request, "core/masterdata_import.html", {"kinds": kinds, **_limits()})


@membership_required(allowed_roles=ADMIN_ONLY)
@require_GET
def masterdata_import_template(request, kind: str):
    import_kind = _kind_or_404(request, kind)
    response = HttpResponse(template_csv(import_kind), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="wachwerk-vorlage-{import_kind.slug}.csv"'
    return response


def _kind_page(request, kind, *, form=None, file_error="", status=200):
    response = render(request, "core/masterdata_import_kind.html", {
        "import_kind": kind,
        "columns": [
            {"column": column, "allowed": column.allowed_values()} for column in kind.columns
        ],
        "form": form or ImportUploadForm(),
        "file_error": file_error,
        **_limits(),
    }, status=status)
    return response


def _preview(request, kind, report, raw: bytes):
    station = request.membership.station
    can_commit = not report.has_errors and report.counts["created"] > 0
    context = {
        "import_kind": kind,
        "report": report,
        "counts": report.counts,
        "form": ImportUploadForm(),
        "can_commit": can_commit,
        **_limits(),
    }
    if can_commit:
        context["payload"] = base64.b64encode(raw).decode("ascii")
        context["token"] = make_token(station, request.user, kind.slug, report.digest, report.plan_digest)
    return render(request, "core/masterdata_import_preview.html", context)


def _check(request, kind):
    form = ImportUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        return _kind_page(request, kind, form=form, status=400)
    upload = form.cleaned_data["file"]
    if upload.size > MAX_FILE_BYTES:
        upload.close()
        return _kind_page(request, kind, status=400, file_error=_(
            "Die Datei ist größer als %(max)s MB. Bitte auf mehrere Dateien aufteilen."
        ) % {"max": MAX_FILE_BYTES // 1_048_576})
    raw = upload.read(MAX_FILE_BYTES + 1)
    upload.close()
    report = run_import(kind, station=request.membership.station, actor=request.user, raw=raw, commit=False)
    return _preview(request, kind, report, raw)


def _commit(request, kind):
    station = request.membership.station
    form = ImportCommitForm(request.POST)
    raw = plan = None
    if form.is_valid():
        try:
            raw = base64.b64decode(form.cleaned_data["payload"], validate=True)
        except (binascii.Error, ValueError):
            raw = None
    digest = form.cleaned_data.get("digest") if form.is_valid() else None
    if raw is not None and len(raw) <= MAX_FILE_BYTES and hashlib.sha256(raw).hexdigest() == digest:
        plan = token_plan(form.cleaned_data["token"], station, request.user, kind.slug, digest)
    if plan is None:
        return _kind_page(request, kind, status=400, file_error=_(
            "Die Vorschau ist abgelaufen oder die Datei wurde verändert. Bitte erneut prüfen."
        ))
    report = run_import(kind, station=station, actor=request.user, raw=raw, commit=True, expected_plan=plan)
    if not report.committed:
        return _preview(request, kind, report, raw)
    following = next_kind(kind, station)
    # „Zum Lager“ auf einer Wache ohne Lagerorte legte drei Beispiel-Lagerorte an
    # (warehouse_dashboard), die sich nicht löschen lassen. Dann zuerst Lagerorte.
    locations_missing = (
        kind.next_url_name == "warehouse_dashboard"
        and not StorageLocation.objects.filter(station=station).exists()
    )
    return render(request, "core/masterdata_import_done.html", {
        "import_kind": kind,
        "report": report,
        "counts": report.counts,
        "next_kind": following,
        "locations_missing": locations_missing,
        "locations_kind": get_kind("lagerorte", station) if locations_missing else None,
    })


@membership_required(allowed_roles=ADMIN_ONLY)
@sensitive_post_parameters("payload")
@require_http_methods(["GET", "POST"])
def masterdata_import_run(request, kind: str):
    import_kind = _kind_or_404(request, kind)
    if request.method == "GET":
        return _kind_page(request, import_kind)
    if request.POST.get("step") == "commit":
        response = _commit(request, import_kind)
    else:
        response = _check(request, import_kind)
    add_never_cache_headers(response)
    return response
