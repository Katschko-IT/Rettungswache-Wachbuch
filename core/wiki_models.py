from __future__ import annotations

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import Station


class WikiArticle(models.Model):
    """
    Wiki-Artikel für wachenbezogene Hinweise und organisatorische Abläufe.

    WICHTIG:
    - Reines internes Organisationswerkzeug. Keine Patientendaten, Notfalleinsatz-
      oder Diagnosedaten erfassen.
    - Jeder Artikel ist fest an genau eine Rettungswache gebunden. Ein Wechsel der
      Wache ist nach dem Anlegen strikt unzulässig.
    - Ein physisches Löschen über die Benutzeroberfläche ist nicht vorgesehen;
      Artikel werden stattdessen über das Flag 'is_archived' archiviert.
    """

    station = models.ForeignKey(
        Station,
        on_delete=models.CASCADE,
        related_name="wiki_articles",
        verbose_name=_("Wache"),
    )
    slug = models.SlugField(
        max_length=80,
        verbose_name=_("Slug"),
    )
    title = models.CharField(
        max_length=160,
        verbose_name=_("Titel"),
    )
    body = models.TextField(
        max_length=8000,
        verbose_name=_("Text"),
    )
    is_archived = models.BooleanField(
        default=False,
        verbose_name=_("Archiviert"),
    )
    current_revision_number = models.PositiveIntegerField(
        default=1,
        verbose_name=_("Aktuelle Revisionsnummer"),
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="created_wiki_articles",
        verbose_name=_("Erstellt von"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Erstellt am"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Aktualisiert am"),
    )

    class Meta:
        ordering = ["title"]
        constraints = [
            models.UniqueConstraint(
                fields=["station", "slug"],
                name="unique_wiki_slug_per_station",
            ),
        ]
        indexes = [
            models.Index(
                fields=["station", "is_archived", "title"],
                name="wiki_article_station_idx",
            ),
        ]
        verbose_name = _("Wiki-Artikel")
        verbose_name_plural = _("Wiki-Artikel")

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("wiki_detail", args=[self.pk])

    def clean(self) -> None:
        super().clean()
        if self.title is not None:
            self.title = self.title.strip()
        if not self.title:
            raise ValidationError({"title": _("Der Titel darf nicht leer sein.")})
        if len(self.title) > 160:
            raise ValidationError({"title": _("Der Titel darf maximal 160 Zeichen lang sein.")})

        if self.body is not None:
            self.body = self.body.strip()
        if not self.body:
            raise ValidationError({"body": _("Der Text darf nicht leer sein.")})
        if len(self.body) > 8000:
            raise ValidationError({"body": _("Der Text darf maximal 8000 Zeichen lang sein.")})

        if self.pk:
            original = WikiArticle.objects.filter(pk=self.pk).values("station_id").first()
            if original and original["station_id"] != self.station_id:
                raise ValidationError(
                    {"station": _("Ein Wiki-Artikel darf die zugeordnete Wache nicht wechseln.")}
                )


class WikiRevision(models.Model):
    """
    Unveränderliche historische Revision eines Wiki-Artikels.

    Dokumentiert fortlaufend nummerierte Inhaltsstände inklusive Bearbeiter,
    Zeitpunkt und Softwareversion (APP_VERSION). Revisionen sind nach dem Anlegen
    append-only und dürfen weder modifiziert noch gelöscht werden.
    """

    article = models.ForeignKey(
        WikiArticle,
        on_delete=models.PROTECT,
        related_name="revisions",
        verbose_name=_("Artikel"),
    )
    number = models.PositiveIntegerField(
        verbose_name=_("Revisionsnummer"),
    )
    title = models.CharField(
        max_length=160,
        verbose_name=_("Titel"),
    )
    body = models.TextField(
        max_length=8000,
        verbose_name=_("Text"),
    )
    edited_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="wiki_revisions",
        verbose_name=_("Bearbeitet von"),
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        verbose_name=_("Erstellt am"),
    )
    app_version = models.CharField(
        max_length=20,
        verbose_name=_("Softwareversion"),
    )

    class Meta:
        ordering = ["-number"]
        constraints = [
            models.UniqueConstraint(
                fields=["article", "number"],
                name="unique_wiki_revision_number",
            ),
        ]
        indexes = [
            models.Index(
                fields=["article", "-number"],
                name="wiki_revision_art_num_idx",
            ),
        ]
        verbose_name = _("Wiki-Revision")
        verbose_name_plural = _("Wiki-Revisionen")

    def __str__(self) -> str:
        return f"{self.article_id} r{self.number}"

    def save(self, *args, **kwargs) -> None:
        if self.pk:
            raise ValidationError(_("Wiki-Revisionen dürfen nicht verändert werden."))
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(_("Wiki-Revisionen dürfen nicht gelöscht werden."))
