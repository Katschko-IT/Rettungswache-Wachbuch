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
from django.utils.translation import gettext, gettext_lazy

from .models import Membership, Station


def _require_same_station(parent, station_id: int | None, label: str) -> None:
    if parent is not None and station_id and getattr(parent, "station_id", None) != station_id:
        raise ValidationError(f"{label} und Wache müssen übereinstimmen.")


def reading_audience(station):
    """Aktive Mitgliedschaften, die eine Dienstanweisung lesen und bestätigen können.

    Nur Inhaltsrollen mit aktivem Konto; ohne Auditor und ohne das Dienstkonto
    „Wachenterminal“ (AGENTS.md § 4: keine Lesebestätigungen am Terminal).
    Zielgruppe, Quote, offene Personen und Erinnerungen bauen darauf auf.
    """
    from .access import CONTENT_ROLES
    from .terminal_models import StationTerminalCode

    service_ids = StationTerminalCode.objects.values_list("service_user_id", flat=True)
    return (
        Membership.objects.filter(
            station=station,
            is_active=True,
            user__is_active=True,
            role__in=CONTENT_ROLES,
        )
        .exclude(user_id__in=service_ids)
    )


def in_reading_audience(membership) -> bool:
    """Gehört die Mitgliedschaft grundsätzlich zur Leserschaft (siehe ``reading_audience``)?"""
    from .access import CONTENT_ROLES
    from .terminal import is_service_user

    if membership is None or not membership.is_active or membership.role not in CONTENT_ROLES:
        return False
    user = membership.user
    return bool(user.is_active) and not is_service_user(user)


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
    ack_due_date = models.DateField("Lesefrist bis", null=True, blank=True)
    target_role = models.CharField(
        "Zielgruppe (Rolle)",
        max_length=20,
        blank=True,
        default="",
        help_text="Leer = alle aktiven Mitglieder der Wache",
    )
    # Kurzname aus Membership.FUNCTIONS; zusammen mit target_role gilt beides.
    target_function = models.CharField(
        "Zielgruppe (Funktion)",
        max_length=20,
        blank=True,
        default="",
        help_text="Leer = ohne Einschränkung nach Funktion",
    )
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

    @property
    def target_role_label(self) -> str:
        if not self.target_role:
            return str(gettext_lazy("Alle aktiven Mitglieder"))
        return str(dict(Membership.Role.choices).get(self.target_role, self.target_role))

    @property
    def target_function_label(self) -> str:
        labels = {code: label for code, _field, label in Membership.FUNCTIONS}
        return str(labels.get(self.target_function, "")) if self.target_function else ""

    @property
    def target_group_label(self) -> str:
        """Zielgruppe in Worten: Rolle und, falls gesetzt, Funktion."""
        function = self.target_function_label
        if not function:
            return self.target_role_label
        if not self.target_role:
            return gettext("Funktion %(function)s") % {"function": function}
        return gettext("%(role)s mit Funktion %(function)s") % {
            "role": self.target_role_label,
            "function": function,
        }

    def _function_field(self) -> str | None:
        for code, field, _label in Membership.FUNCTIONS:
            if code == self.target_function:
                return field
        return None

    def matches_target(self, membership) -> bool:
        """Passen Rolle und Funktion der Mitgliedschaft zur Zielgruppe (ohne Leserschaftsprüfung)?"""
        if membership is None:
            return False
        if self.target_role and membership.role != self.target_role:
            return False
        field = self._function_field()
        if self.target_function and (field is None or not getattr(membership, field, False)):
            return False
        return True

    def is_target_member(self, membership) -> bool:
        """Muss diese Person die Dienstanweisung bestätigen?"""
        return in_reading_audience(membership) and self.matches_target(membership)

    def target_memberships(self):
        memberships = reading_audience(self.station)
        if self.target_role:
            memberships = memberships.filter(role=self.target_role)
        if self.target_function:
            field = self._function_field()
            if field is None:
                return memberships.none()
            memberships = memberships.filter(**{field: True})
        return memberships

    def target_user_ids(self) -> set[int]:
        return set(self.target_memberships().values_list("user_id", flat=True))

    def ack_progress(self) -> dict[str, int]:
        """Berechnet die aggregierte Lesequote für die Wachleitung.

        Gibt die Quote als Aggregat zurück, ohne einzelne Personen aufzuführen
        (Schutz der Beschäftigtendaten gem. Mitbestimmung). Es zählen nur
        Personen der Zielgruppe; freiwillige Bestätigungen anderer nicht.
        """
        target_user_ids = self.target_user_ids()
        target_count = len(target_user_ids)

        latest = self.latest_revision
        if not latest or target_count == 0:
            return {
                "acknowledged_count": 0,
                "target_count": target_count,
                "percent": 0,
            }

        acked_user_ids = set(
            self.receipts.filter(revision=latest, user_id__in=target_user_ids).values_list("user_id", flat=True)
        )
        acknowledged_count = len(acked_user_ids)
        percent = round((acknowledged_count / target_count) * 100) if target_count > 0 else 0

        return {
            "acknowledged_count": acknowledged_count,
            "target_count": target_count,
            "percent": percent,
        }

    def unacknowledged_users(self):
        """Personen der Zielgruppe, die die aktuelle Revision noch nicht bestätigt haben."""
        target_user_ids = self.target_user_ids()
        latest = self.latest_revision
        if not latest or not target_user_ids:
            return User.objects.none()

        acked_user_ids = set(
            self.receipts.filter(revision=latest, user_id__in=target_user_ids).values_list("user_id", flat=True)
        )
        open_ids = target_user_ids - acked_user_ids
        return User.objects.filter(id__in=open_ids).order_by("pk")


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
    # Altbestände leert der einmalige Befehl ``cleanup_legacy_data`` (0.27) per
    # QuerySet.update; die Felder werden weder angezeigt noch exportiert.
    # Deshalb hat SOPReceipt noch keinen Zeilenschutz in save()/delete() und
    # kein REVOKE (Folgeschritt nach der Bereinigung). Die Spalten entfallen
    # später, wenn alle Installationen bereinigt sind.
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

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Lesebestätigungen dürfen nicht verändert werden.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Lesebestätigungen dürfen nicht gelöscht werden.")


def acknowledgement_refusal(sop: SOPDocument, membership) -> tuple[str, str] | None:
    """Warum die Person die aktuelle Version nicht bestätigen kann: (Code, Text), sonst ``None``.

    Dieselben Regeln für Web und App: nur mit dem eigenen Konto einer
    Inhaltsrolle (nie das Wachenterminal), nur „In Kraft“ und nur mit einem
    freigegebenen Textstand.
    """
    from .access import CONTENT_ROLES
    from .terminal import is_service_user

    if membership is None or membership.role not in CONTENT_ROLES or is_service_user(membership.user):
        return "forbidden", gettext("Lesebestätigungen gibt es nur mit dem eigenen Konto.")
    if sop.status == SOPDocument.Status.ARCHIVED:
        return "not_in_force", gettext("Diese Dienstanweisung ist außer Kraft und kann nicht mehr quittiert werden.")
    if sop.status != SOPDocument.Status.ACTIVE:
        return "not_in_force", gettext("Diese Dienstanweisung ist noch ein Entwurf und kann noch nicht bestätigt werden.")
    if sop.latest_revision is None:
        return "no_revision", gettext("Diese Dienstanweisung hat noch keinen freigegebenen Textstand.")
    return None


def record_acknowledgement(sop: SOPDocument, user: User) -> tuple[SOPReceipt, bool]:
    """Lesebestätigung der aktuellen Version (append-only, idempotent).

    Datensparsam (ab 0.26.1): Person, Version und Zeitpunkt. IP-Adresse und
    Browser werden nicht gespeichert.
    """
    return SOPReceipt.objects.get_or_create(
        station=sop.station,
        sop=sop,
        revision=sop.latest_revision,
        user=user,
        defaults={"ip_address": None, "user_agent": "", "acknowledged_at": timezone.now()},
    )


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


StandardOperatingProcedure = SOPDocument
SopReceipt = SOPReceipt
