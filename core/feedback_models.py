"""Rückmeldungen über die öffentliche Feedback-Seite (docs/FEEDBACK.md)."""
from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class Feedback(models.Model):
    """Wunsch, Anregung, Lob, Fehler oder Frage – freiwillig und ohne IP-Adresse.

    Gehört bewusst zu keiner Wache: Die Seite ist öffentlich (auch für
    Besucher der Demo), gelesen wird sie vom Betreiber der Installation.
    """

    class Kind(models.TextChoices):
        WISH = "wish", _("Wunsch")
        IDEA = "idea", _("Anregung")
        PRAISE = "praise", _("Lob")
        BUG = "bug", _("Fehler")
        QUESTION = "question", _("Frage")

    class Role(models.TextChoices):
        CREW = "crew", _("Einsatzkraft auf der Wache")
        LEAD = "lead", _("Wachleitung oder Praxisanleitung")
        IT = "it", _("IT oder Datenschutz")
        OTHER = "other", _("Etwas anderes")

    class Status(models.TextChoices):
        NEW = "new", _("Neu")
        READ = "read", _("Gelesen")
        DONE = "done", _("Erledigt")

    created_at = models.DateTimeField(auto_now_add=True)
    kind = models.CharField(_("Art"), max_length=12, choices=Kind.choices, default=Kind.IDEA)
    message = models.TextField(_("Nachricht"), max_length=3000)
    role = models.CharField(_("Ich bin"), max_length=12, choices=Role.choices, blank=True, default="")
    rating = models.PositiveSmallIntegerField(_("Bewertung"), null=True, blank=True)
    name = models.CharField(_("Name"), max_length=120, blank=True, default="")
    email = models.EmailField(_("E-Mail für eine Antwort"), blank=True, default="")
    from_demo = models.BooleanField(default=False)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.NEW)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Rückmeldung"
        verbose_name_plural = "Rückmeldungen"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(rating__isnull=True) | models.Q(rating__gte=1, rating__lte=5),
                name="feedback_rating_1_to_5",
            ),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} vom {self.created_at:%d.%m.%Y}"
