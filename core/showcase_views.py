"""Schaufenster der öffentlichen Demo: Sperrbildschirm-Vorschau und die Seite
„Für IT & Datenschutz“.

Die Vorschau zeigt den echten Sperrbildschirm des Wachenterminals mit den
Daten der eigenen Demo-Wache. Sie meldet niemanden an, legt kein Terminal und
kein Dienstkonto an und nimmt keine Eingaben entgegen – das Dienstkonto
„Wachenterminal“ bleibt unberührt (AGENTS.md, Abschnitt 4).
"""
from __future__ import annotations

from types import SimpleNamespace

from django.http import Http404
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .access import CONTENT_ROLES, get_membership
from .lockscreen import background_for


@require_GET
@never_cache
def lock_screen_preview(request):
    """Nur in einer Demo-Wache; ohne Demo antwortet die Adresse mit 404."""
    sandbox = getattr(request, "demo_sandbox", None)
    membership = get_membership(request.user) if sandbox is not None else None
    if (
        membership is None
        or membership.station_id != sandbox.station_id
        or membership.role not in CONTENT_ROLES
    ):
        raise Http404
    from .terminal_views import _lock_screen_data

    station = membership.station
    return render(request, "core/terminal_home.html", {
        "terminal": SimpleNamespace(station=station),
        "data": _lock_screen_data(station),
        "background": background_for(timezone.localdate()),
        "error_text": "",
        "wifi_ssid": "",
        "preview": True,
    })


@require_GET
def it_privacy(request):
    """Öffentliche Kurzinfo für IT und Datenschutz (ohne Daten einer Wache)."""
    return render(request, "core/it_privacy.html")
