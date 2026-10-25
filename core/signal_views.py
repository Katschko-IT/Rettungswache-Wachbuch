"""Signal: eigene Nummer bestätigen (alle) und Wachen-Gruppe verbinden (Admin)."""
from __future__ import annotations

import base64

from django.contrib import messages
from django.core.cache import cache
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from . import signal_messenger as signal
from .access import CONTENT_ROLES, membership_required
from .models import Membership
from .notification_models import SignalContact
from .services import audit

CODE_SENDS_PER_HOUR = 3


def _require_signal():
    if not signal.signal_enabled():
        raise Http404


@membership_required(CONTENT_ROLES)
@require_http_methods(["GET", "POST"])
def signal_account(request):
    """Eigene Signal-Nummer hinterlegen: Erinnerungen und Hinweise kommen dann auch per Signal."""
    _require_signal()
    contact = SignalContact.objects.filter(user=request.user).first()
    action = request.POST.get("action")
    if request.method == "POST" and action == "number":
        try:
            number = signal.normalize_number(request.POST.get("number", ""))
        except ValueError:
            messages.error(request, _("Bitte eine gültige Handynummer eingeben, z. B. 0171 2345678."))
            return redirect("signal_account")
        key = f"signal-code:{request.user.pk}"
        sends = cache.get(key, 0)
        if sends >= CODE_SENDS_PER_HOUR:
            messages.error(request, _("Zu viele Codes angefordert. Bitte in einer Stunde erneut versuchen."))
            return redirect("signal_account")
        try:
            signal.start_verification(request.user, number)
        except signal.SignalError:
            messages.error(request, _("Signal ist gerade nicht erreichbar. Bitte später erneut versuchen."))
            return redirect("signal_account")
        cache.set(key, sends + 1, 3600)
        messages.success(request, _("Wir haben dir per Signal einen Code geschickt."))
        return redirect("signal_account")
    if request.method == "POST" and action == "confirm" and contact:
        if signal.confirm_verification(contact, request.POST.get("code", "")):
            audit(request.user, request.membership.station, "signal.contact_verified", contact, {"fields": ["number"]})
            messages.success(request, _("Signal ist aktiv. Du bekommst deine Benachrichtigungen jetzt auch per Signal."))
        else:
            messages.error(request, _("Der Code stimmt nicht oder ist abgelaufen."))
        return redirect("signal_account")
    if request.method == "POST" and action == "remove" and contact:
        contact.delete()
        audit(request.user, request.membership.station, "signal.contact_removed", request.user, {"fields": ["number"]})
        messages.success(request, _("Deine Signal-Nummer wurde gelöscht."))
        return redirect("signal_account")
    return render(request, "core/signal_account.html", {"contact": contact})


@membership_required({Membership.Role.ADMIN})
@require_http_methods(["GET", "POST"])
def signal_admin(request):
    """Signal der Wache: Konto koppeln, Gruppe wählen, Testnachricht."""
    station = request.membership.station
    enabled = signal.signal_enabled()
    linked = enabled and signal.is_linked()
    groups, error = [], ""
    if linked:
        try:
            groups = signal.groups()
        except signal.SignalError as exc:
            error = str(exc)
    if request.method == "POST" and linked:
        action = request.POST.get("action")
        if action == "group":
            chosen = request.POST.get("group_id", "")
            if chosen and chosen not in {g["id"] for g in groups}:
                messages.error(request, _("Diese Gruppe kennt das verbundene Signal-Konto nicht."))
                return redirect("signal_admin")
            station.signal_group_id = chosen
            station.save(update_fields=["signal_group_id"])
            audit(request.user, station, "signal.group_changed", station, {"fields": ["signal_group_id"]})
            messages.success(request, _("Signal-Gruppe gespeichert.") if chosen else _("Signal-Gruppe entfernt."))
            return redirect("signal_admin")
        if action == "test" and station.signal_group_id:
            try:
                signal.send([station.signal_group_id], _("Wachwerk: Testnachricht – die Signal-Benachrichtigungen funktionieren."))
            except signal.SignalError as exc:
                messages.error(request, _("Senden fehlgeschlagen: %(error)s") % {"error": exc})
            else:
                messages.success(request, _("Testnachricht gesendet."))
            return redirect("signal_admin")
    link_qr, link_error = "", ""
    if enabled and not linked:
        try:
            link_qr = "data:image/png;base64," + base64.b64encode(signal.link_qr_png("Wachwerk")).decode("ascii")
        except signal.SignalError as exc:
            link_error = str(exc)
    suggested = ""
    if station.signal_group_url:
        suggested = next((g["id"] for g in groups if g["invite_link"] and
                          g["invite_link"].rstrip("/") == station.signal_group_url.rstrip("/")), "")
    return render(request, "core/signal_admin.html", {
        "enabled": enabled,
        "linked": linked,
        "groups": groups,
        "error": error,
        "suggested": suggested,
        "station": station,
        "link_qr": link_qr,
        "link_error": link_error,
        "people": SignalContact.objects.filter(
            verified_at__isnull=False,
            user__station_memberships__station=station, user__station_memberships__is_active=True,
        ).count(),
    })
