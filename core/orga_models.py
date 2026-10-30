"""Organisations-, QM- und Desk-Modelle für den Rettungsdienst.

Beinhaltet:
- Revisionssichere SOPs & Dienstanweisungen (ÄLRD / QM gem. DIN EN ISO 9001)
  mit SHA-256 Content-Hashing und manipulationssicherem Mitarbeiter-Quittungsbuch (SOPReceipt).
- Stations-Telefonbuch & Notfall-Schnellwahl (StationContact) für Leitstelle,
  Kliniken (ZNA / CPU / Stroke), Notfallseelsorge und Giftnotruf.
"""
from __future__ import annotations

import hashlib
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .models import Station


def _require_same_station(parent, station_id: int | None, label: str) -> None:
    if parent is not None and station_id and getattr(parent, "station_id", None) != station_id:
        raise ValidationError(f"{label} und Wache müssen übereinstimmen.")


class SOPDocument(models.Model):
    """SOP (Standard Operating Procedure), Dienstanweisung oder Verfahrensanweisung."""

    class Category(models.TextChoices):
        MED_HEILKUNDE = "med", "Medizin & Heilkunde (§ 2a NotSanG / 2c)"
        TAKTIK_EINSATZ = "taktik", "Taktik & Einsatzorganisation"
        HYGIENE = "hygiene", "Hygiene & Infektionsschutz"
        FUHRPARK = "fuhrpark", "Fuhrpark, UVV & Gerätewesen"
        ALLGEMEIN = "allgemein", "Allgemeine Dienstanweisung"

    class Status(models.TextChoices):
        DRAFT = "draft", "Entwurf (In Prüfung)"
        ACTIVE = "active", "In Kraft (Gültig)"
        ARCHIVED = "archived", "Außer Kraft (Archiviert)"

    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="sops")
    slug = models.SlugField(max_length=80, help_text="Slug für Adresszeile z. B. sop-anaphylaxie")
    doc_number = models.CharField(
        max_length=40,
        verbose_name="Dokumentennummer",
        help_text="z. B. SOP-MED-01 oder DA-HYG-04",
    )
    title = models.CharField(max_length=200, verbose_name="Titel der Dienstanweisung")
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.MED_HEILKUNDE)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    current_version = models.CharField(max_length=20, default="1.0", verbose_name="Aktuelle Version")
    valid_from = models.DateField(default=timezone.localdate, verbose_name="Gültig ab")
    review_due_date = models.DateField(null=True, blank=True, verbose_name="Nächste Überprüfung (QM)")
    requires_acknowledgment = models.BooleanField(
        default=True,
        verbose_name="Pflichtquittierung für Personal",
        help_text="Erscheint als Pflichtlektüre im Mitarbeiter-Desk bis zur Kenntnisnahme",
    )

    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="created_sops")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "doc_number"]
        constraints = [
            models.UniqueConstraint(fields=["station", "slug"], name="unique_station_sop_slug"),
            models.UniqueConstraint(fields=["station", "doc_number"], name="unique_station_sop_docnumber"),
        ]
        indexes = [
            models.Index(fields=["station", "status"], name="sop_station_status_idx"),
            models.Index(fields=["station", "category"], name="sop_station_category_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.doc_number}: {self.title} (v{self.current_version})"

    @property
    def latest_revision(self) -> SOPRevision | None:
        # Listen laden die Revisionen vorab (list_with_ack_state); dann ohne Abfrage.
        if "revisions" in getattr(self, "_prefetched_objects_cache", {}):
            return max(self.revisions.all(), key=lambda rev: (rev.created_at, rev.pk), default=None)
        return self.revisions.order_by("-created_at", "-pk").first()

    def user_has_acknowledged(self, user: User) -> bool:
        """Prüft, ob der Benutzer die aktuelle Revision quittiert hat."""
        latest = self.latest_revision
        if not latest:
            return True
        # Vorab geladen sind nur die Quittungen genau eines Benutzers.
        if getattr(self, "my_receipts_user_id", None) == user.pk:
            return any(receipt.revision_id == latest.pk for receipt in self.my_receipts)
        return self.receipts.filter(user=user, revision=latest).exists()

    @staticmethod
    def list_with_ack_state(queryset, user: User) -> list[SOPDocument]:
        """SOPs samt Revisionen und eigenen Quittungen: drei Abfragen statt drei je SOP."""
        sops = list(queryset.prefetch_related(
            "revisions",
            models.Prefetch("receipts", queryset=SOPReceipt.objects.filter(user=user), to_attr="my_receipts"),
        ))
        for sop in sops:
            sop.my_receipts_user_id = user.pk
        return sops


class SOPRevision(models.Model):
    """Revisionssichere Version einer SOP mit SHA-256 Prüfsumme."""

    sop = models.ForeignKey(SOPDocument, on_delete=models.PROTECT, related_name="revisions")
    version_label = models.CharField(max_length=20, default="1.0", verbose_name="Versionsnummer")
    content_markdown = models.TextField(verbose_name="Volltext / Anweisungsinhalt")
    content_hash = models.CharField(
        max_length=64,
        verbose_name="SHA-256 Prüfsumme",
        help_text="Unveränderbare kryptographische Prüfsumme des Inhalts für QM-Audits",
    )
    change_summary = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Änderungsbegründung / Changelog",
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approved_sop_revisions",
        verbose_name="Freigegeben durch (ÄLRD / Wachleitung)",
    )
    effective_date = models.DateField(default=timezone.localdate, verbose_name="Inkrafttreten")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["sop", "version_label"], name="unique_sop_version"),
        ]

    def __str__(self) -> str:
        return f"{self.sop.doc_number} v{self.version_label} ({timezone.localtime(self.created_at).strftime('%d.%m.%Y')})"

    def save(self, *args, **kwargs):
        # Eine freigegebene Version bleibt unverändert; Änderungen ergeben eine
        # neue Version (AGENTS.md § 4).
        if self.pk:
            raise ValidationError("Versionen von Dienstanweisungen dürfen nicht verändert werden.")
        # SHA-256 Hash berechnen falls noch nicht vorhanden
        if not self.content_hash:
            raw = (self.content_markdown or "").strip().encode("utf-8")
            self.content_hash = hashlib.sha256(raw).hexdigest()
        super().save(*args, **kwargs)

        # Übergeordnete SOP auf diese Version aktualisieren
        if self.sop.current_version != self.version_label:
            self.sop.current_version = self.version_label
            self.sop.save(update_fields=["current_version", "updated_at"])

    def delete(self, *args, **kwargs):
        raise ValidationError("Versionen von Dienstanweisungen dürfen nicht gelöscht werden.")


class SOPReceipt(models.Model):
    """Revisionssicherer Nachweis über die Kenntnisnahme einer Dienstanweisung (Append-Only)."""

    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="sop_receipts")
    sop = models.ForeignKey(SOPDocument, on_delete=models.PROTECT, related_name="receipts")
    revision = models.ForeignKey(SOPRevision, on_delete=models.PROTECT, related_name="receipts")
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="sop_receipts")
    acknowledged_at = models.DateTimeField(default=timezone.now, verbose_name="Quittiert am")
    # Seit 0.26.1 werden IP-Adresse und Browser nicht mehr erfasst (leer/None).
    # Die Felder bleiben nur für Altbestände und werden weder angezeigt noch
    # exportiert. Die einmalige Bereinigung der Altbestände (0.27) leert sie per
    # QuerySet.update; deshalb hat SOPReceipt noch keinen Zeilenschutz in
    # save()/delete() und kein REVOKE (Folgeschritt nach der Bereinigung).
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP-Adresse")
    user_agent = models.CharField(max_length=255, blank=True, default="", verbose_name="Browser / Gerät")

    class Meta:
        ordering = ["-acknowledged_at"]
        constraints = [
            models.UniqueConstraint(fields=["sop", "revision", "user"], name="unique_sop_revision_receipt"),
        ]
        indexes = [
            models.Index(fields=["station", "-acknowledged_at"], name="sop_receipt_station_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user.username} quittierte {self.sop.doc_number} v{self.revision.version_label}"


class StationContact(models.Model):
    """Zentrales Wachen-Telefonbuch & Notfall-Schnellwahl."""

    class Category(models.TextChoices):
        DISPATCH = "dispatch", "Leitstelle & Disposition"
        HOSPITAL = "hospital", "Kliniken (ZNA / CPU / Stroke)"
        EMERGENCY_SERVICES = "emergency", "Notarztdienst / LNA / OrgL"
        POISON = "poison", "Giftnotruf & Toxikologie"
        PSYCH = "psych", "Krisenintervention & Seelsorge (KIT/NFS)"
        MANAGEMENT = "management", "Wachleitung & Desinfektor"
        SUPPLIER = "supplier", "Medizintechnik & Kfz-Werkstatt"
        OTHER = "other", "Sonstige Kontakte"

    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="contacts")
    name = models.CharField(max_length=120, verbose_name="Einrichtung / Name")
    contact_person = models.CharField(max_length=120, blank=True, default="", verbose_name="Ansprechpartner / Funktion")
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    phone_primary = models.CharField(max_length=60, verbose_name="Hauptrufnummer")
    phone_secondary = models.CharField(max_length=60, blank=True, default="", verbose_name="Notfalltelefon / Direktwahl")
    notes = models.CharField(max_length=255, blank=True, default="", verbose_name="Zuständigkeit / Erreichbarkeit")
    is_speed_dial = models.BooleanField(default=False, verbose_name="In Schnellwahlleiste anzeigen")
    order_rank = models.PositiveSmallIntegerField(default=10, verbose_name="Sortierung")

    class Meta:
        ordering = ["-is_speed_dial", "order_rank", "name"]
        indexes = [
            models.Index(fields=["station", "category"], name="contact_station_category_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.phone_primary})"
