import re

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import Station

CORRELATION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
ROUTE_NAME_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")


class ErrorEvent(models.Model):
    """
    Bereinigtes technisches Fehlerereignis für serverseitige 5xx-Fehler.

    Datenschutz- und Sicherheitsvorgaben:
    - Keine Exception-Texte oder Tracebacks.
    - Keine Roh-URLs oder Query-Strings.
    - Keine Request-Bodies, Header, Cookies oder Token.
    - Keine Artikel- oder Mitgliedsinhalte.
    - Aufbewahrung ist eine technische Policy, keine Rechtsfrist.
    """

    class Category(models.TextChoices):
        DATABASE = "database", _("Datenbank")
        TEMPLATE = "template", _("Vorlage")
        PERMISSION = "permission", _("Berechtigung")
        VALIDATION = "validation", _("Validierung")
        HTTP = "http", _("HTTP")
        SERVER = "server", _("Server")

    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    correlation_id = models.CharField(max_length=128, db_index=True)
    route_name = models.CharField(max_length=120)
    category = models.CharField(
        max_length=20, choices=Category.choices, default=Category.SERVER
    )
    http_status = models.PositiveSmallIntegerField()
    app_version = models.CharField(max_length=20)
    station = models.ForeignKey(
        Station,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="error_events",
    )

    class Meta:
        ordering = ["-occurred_at", "-id"]
        indexes = [
            models.Index(
                fields=["station", "-occurred_at"],
                name="error_event_station_occ_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(http_status__gte=500, http_status__lte=599),
                name="error_event_status_is_5xx",
            ),
        ]
        verbose_name = "Fehlerereignis"
        verbose_name_plural = "Fehlerereignisse"

    def clean(self):
        super().clean()
        errors = {}
        if self.http_status is None or not (500 <= self.http_status <= 599):
            errors["http_status"] = _("HTTP-Status muss zwischen 500 und 599 liegen.")
        if not self.correlation_id or not CORRELATION_ID_RE.match(self.correlation_id):
            errors["correlation_id"] = _(
                "Correlation-ID muss dem Muster ^[A-Za-z0-9_-]{1,128}$ entsprechen."
            )
        if not self.route_name or not ROUTE_NAME_RE.match(self.route_name):
            errors["route_name"] = _(
                "Routenname muss dem Muster ^[A-Za-z0-9_.:-]{1,120}$ entsprechen."
            )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.occurred_at:%Y-%m-%d %H:%M} {self.route_name} {self.http_status}"
