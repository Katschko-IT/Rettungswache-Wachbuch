"""Öffentliche Feedback-Seite: Wünsche, Anregungen, Lob, Fehler und Fragen.

Eingeschaltet mit ``FEEDBACK_ENABLED`` (in der öffentlichen Demo
automatisch). Gespeichert wird nur, was jemand freiwillig einträgt – keine
IP-Adresse. Gelesen wird im Posteingang unter Einstellungen von
Master-Admins echter Wachen (nicht von Demo-Wachen). Nach
``FEEDBACK_RETENTION_DAYS`` löscht ``apply_retention`` die Einträge.
"""
from __future__ import annotations

import hashlib
from datetime import timedelta

from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_http_methods, require_POST

from . import demo_stats
from .access import membership_required
from .feedback_models import Feedback
from .middleware import rate_limit_ip
from .models import Membership
from .services import audit


def feedback_enabled() -> bool:
    return bool(getattr(settings, "FEEDBACK_ENABLED", False))


class FeedbackForm(forms.ModelForm):
    RATING_CHOICES = [("", gettext_lazy("Keine Angabe"))] + [(str(n), str(n)) for n in range(1, 6)]

    rating = forms.TypedChoiceField(
        label=gettext_lazy("Wie gut gefällt dir Wachwerk? (1 = gar nicht, 5 = sehr)"),
        choices=RATING_CHOICES, coerce=int, empty_value=None, required=False,
        widget=forms.RadioSelect,
    )
    consent = forms.BooleanField(
        label=gettext_lazy("Ich bin einverstanden, dass meine Angaben gespeichert werden, um die Rückmeldung zu bearbeiten."),
        required=True,
    )
    # Unsichtbares Feld gegen Spam-Programme; Menschen lassen es leer.
    website = forms.CharField(required=False, label=gettext_lazy("Bitte leer lassen"))

    class Meta:
        model = Feedback
        fields = ["kind", "message", "role", "rating", "name", "email"]
        widgets = {
            "kind": forms.RadioSelect,
            "message": forms.Textarea(attrs={"rows": 6, "maxlength": 3000}),
        }
        help_texts = {
            "message": gettext_lazy("Bitte keine Patienten-, Einsatz- oder sonstigen vertraulichen Daten."),
            "name": gettext_lazy("Freiwillig."),
            "email": gettext_lazy("Freiwillig – nur nötig, wenn du eine Antwort möchtest."),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].required = False
        self.fields["role"].choices = [("", _("Keine Angabe"))] + list(Feedback.Role.choices)
        self.fields["website"].widget.attrs.update({"tabindex": "-1", "autocomplete": "off"})


def _within_rate_limit(request) -> bool:
    raw = f"{settings.RATELIMIT_KEY_SALT}:feedback:{rate_limit_ip(request)}"
    key = "feedback:" + hashlib.sha256(raw.encode()).hexdigest()[:32]
    cache.add(key, 0, timeout=3600)
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=3600)
        count = 1
    return count <= settings.FEEDBACK_PER_IP_HOUR


@require_http_methods(["GET", "POST"])
def feedback_page(request):
    if not feedback_enabled():
        raise Http404
    thanks_url = f"{reverse('feedback')}?danke=1"
    form = FeedbackForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if form.cleaned_data.get("website"):
            # Spam: so tun, als sei alles gut, aber nichts speichern.
            return redirect(thanks_url)
        if not _within_rate_limit(request):
            form.add_error(None, _("Von diesem Anschluss kamen gerade viele Rückmeldungen. Bitte später erneut versuchen."))
        else:
            feedback = form.save(commit=False)
            feedback.from_demo = getattr(request, "demo_sandbox", None) is not None
            feedback.save()
            demo_stats.record_feedback()
            return redirect(thanks_url)
    return render(request, "core/feedback.html", {"form": form, "sent": request.GET.get("danke") == "1"})


def _inbox_guard(request):
    if not feedback_enabled() or getattr(request, "demo_sandbox", None) is not None:
        raise Http404


@membership_required({Membership.Role.ADMIN})
@require_http_methods(["GET"])
def feedback_inbox(request):
    _inbox_guard(request)
    status = request.GET.get("status", "open")
    entries = Feedback.objects.all()
    if status == "open":
        entries = entries.exclude(status=Feedback.Status.DONE)
    elif status in Feedback.Status.values:
        entries = entries.filter(status=status)
    page = Paginator(entries, 50).get_page(request.GET.get("seite"))
    counts = {
        "open": Feedback.objects.exclude(status=Feedback.Status.DONE).count(),
        "all": Feedback.objects.count(),
    }
    return render(request, "core/feedback_inbox.html", {
        "page": page, "status": status, "counts": counts,
        "statuses": Feedback.Status.choices,
        "retention_days": settings.FEEDBACK_RETENTION_DAYS,
    })


@membership_required({Membership.Role.ADMIN})
@require_POST
def feedback_status(request, pk):
    _inbox_guard(request)
    feedback = get_object_or_404(Feedback, pk=pk)
    status = request.POST.get("status", "")
    if status in Feedback.Status.values:
        feedback.status = status
        feedback.save(update_fields=["status"])
        audit(request.user, request.membership.station, "feedback.status", feedback, {"status": status})
    return redirect(request.POST.get("next") or reverse("feedback_inbox"))


@membership_required({Membership.Role.ADMIN})
@require_POST
def feedback_delete(request, pk):
    _inbox_guard(request)
    feedback = get_object_or_404(Feedback, pk=pk)
    audit(request.user, request.membership.station, "feedback.deleted", feedback, {"kind": feedback.kind})
    feedback.delete()
    messages.success(request, _("Rückmeldung gelöscht."))
    return redirect(reverse("feedback_inbox"))


def apply_feedback_retention(now=None, days=None) -> int:
    """Rückmeldungen nach ``FEEDBACK_RETENTION_DAYS`` löschen (0 = nie)."""
    days = int(settings.FEEDBACK_RETENTION_DAYS if days is None else days or 0)
    if days <= 0:
        return 0
    cutoff = (now or timezone.now()) - timedelta(days=days)
    deleted, _counts = Feedback.objects.filter(created_at__lt=cutoff).delete()
    return deleted
