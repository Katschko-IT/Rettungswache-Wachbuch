"""Eigene Einstellungen der Fristen-Erinnerungen (Mein Konto → Erinnerungen).

Jede Person stellt selbst ein, welche Bereiche sie erinnert (nur Bereiche, die
zu ihrer Rolle oder Funktion passen, ``core.deadline_reminders.CATEGORIES``),
und ob die Erinnerungen zusätzlich per E-Mail kommen. Persönliche Erinnerungen
(Lesefrist einer Dienstanweisung, eigene Mängel) gelten immer. Nicht für das
Dienstkonto des Wachenterminals.
"""
from __future__ import annotations

from django import forms
from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _, gettext_lazy
from django.views.decorators.http import require_http_methods

from .access import CONTENT_ROLES, membership_required
from .deadline_reminders import eligible_categories, is_subscribed, reminder_email_enabled
from .models import Membership
from .services import audit


class ReminderSettingsForm(forms.Form):
    reminder_email = forms.BooleanField(
        required=False,
        label=gettext_lazy("Erinnerungen zusätzlich per E-Mail"),
        help_text=gettext_lazy("An die E-Mail-Adresse deines Kontos, eine E-Mail je Lauf mit allen neuen Erinnerungen."),
    )

    def __init__(self, *args, membership: Membership, email_available: bool, **kwargs):
        super().__init__(*args, **kwargs)
        self.membership = membership
        self.categories = eligible_categories(membership)
        for category in self.categories:
            self.fields[category.field] = forms.BooleanField(
                required=False,
                label=category.label,
                help_text=category.help_text,
                initial=is_subscribed(membership, category),
            )
        self.fields["reminder_email"].initial = membership.reminder_email
        if not email_available:
            del self.fields["reminder_email"]

    def category_fields(self):
        return [self[category.field] for category in self.categories]

    def save(self) -> list[str]:
        membership = self.membership
        changed = []
        for category in self.categories:
            # Angehakt = Standard (folgt Rolle und Funktion), sonst bewusst aus.
            value = None if self.cleaned_data.get(category.field) else False
            if getattr(membership, category.field) != value:
                setattr(membership, category.field, value)
                changed.append(category.field)
        if "reminder_email" in self.fields:
            value = bool(self.cleaned_data.get("reminder_email"))
            if membership.reminder_email != value:
                membership.reminder_email = value
                changed.append("reminder_email")
        if changed:
            membership.save(update_fields=changed)
        return changed


@membership_required(CONTENT_ROLES)
@require_http_methods(["GET", "POST"])
def reminder_settings(request):
    from .terminal import is_service_user

    membership = request.membership
    if is_service_user(request.user):
        raise Http404
    email_configured = reminder_email_enabled()
    email_available = email_configured and bool(request.user.email)
    form = ReminderSettingsForm(
        request.POST if request.method == "POST" else None, membership=membership, email_available=email_available,
    )
    if request.method == "POST" and form.is_valid():
        changed = form.save()
        if changed:
            audit(request.user, membership.station, "membership.reminders_updated", membership, {"fields": changed})
        messages.success(request, _("Einstellungen der Erinnerungen gespeichert."))
        return redirect("reminder_settings")
    return render(request, "core/reminder_settings.html", {
        "form": form,
        "email_configured": email_configured,
        "email_available": email_available,
        "has_categories": bool(form.categories),
    })
