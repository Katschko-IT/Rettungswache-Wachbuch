"""Medizinproduktebuch- und MPG-Modelle gem. MPDG, MPBetreibV und DIN EN 62353.

Verwaltung von aktiven Medizinprodukten (Anlage 1 & 2),
sicherheitstechnischen Kontrollen (STK), messtechnischen Kontrollen (MTK),
elektrischer Prüfung (DGUV V3), täglichen Funktionskontrollen und Einweisungsnachweisen
(Gerätepass gem. § 11 MPBetreibV).
"""
from __future__ import annotations

from datetime import date, timedelta
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import Station
from .paper_backfill import PaperBackfillRecord, backfill_constraint


def _require_same_station(parent, station_id: int | None, label: str) -> None:
    if parent is not None and station_id and getattr(parent, "station_id", None) != station_id:
        raise ValidationError(f"{label} und Wache müssen übereinstimmen.")


class MedicalDevice(models.Model):
    """Medizinprodukt im Bestandsverzeichnis (§ 14 MPBetreibV) / Medizinproduktebuch (§ 13 MPBetreibV)."""

    class RiskClass(models.TextChoices):
        CLASS_I = "I", "Klasse I"
        IIA = "IIa", "Klasse IIa"
        IIB = "IIb", "Klasse IIb"
        III = "III", "Klasse III"

    class Category(models.TextChoices):
        DEFIBRILLATOR = "defi", "Defibrillator / Monitor"
        VENTILATOR = "vent", "Beatmungsgerät"
        SUCTION = "suction", "Absaugpumpe"
        PERFUSOR = "perfusor", "Spritzenpumpe / Infusion"
        DIAGNOSTIC = "diag", "Diagnostik (EKG, SpO2, NIBP)"
        CPR = "cpr", "Reanimationshilfe"
        OTHER = "other", "Sonstiges aktives Medizinprodukt"

    class Status(models.TextChoices):
        READY = "ready", "Einsatzklar"
        LIMITED = "limited", "Eingeschränkt"
        MAINTENANCE = "maintenance", "In Wartung / STK"
        OOB = "oob", "Gesperrt"
        # Dauerhaft außer Betrieb genommen (core/evidence.py); Nachweise bleiben.
        DECOMMISSIONED = "decommissioned", "Außer Betrieb genommen"

    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="medical_devices")
    slug = models.SlugField(max_length=64, help_text="Eindeutiger Bezeichner für QR-Code-URL (/mpg/d/<slug>/)")
    name = models.CharField(max_length=160, verbose_name="Gerätebezeichnung")
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER, verbose_name="Gerätekategorie")
    risk_class = models.CharField(max_length=10, choices=RiskClass.choices, default=RiskClass.IIB, verbose_name="Risikoklasse")

    # MPBetreibV Stammdaten
    manufacturer = models.CharField(max_length=120, blank=True, default="", verbose_name="Hersteller")
    model_type = models.CharField(max_length=120, blank=True, default="", verbose_name="Typ / Modell")
    serial_number = models.CharField(max_length=120, blank=True, default="", verbose_name="Seriennummer")
    inventory_number = models.CharField(max_length=60, blank=True, default="", verbose_name="Inventarnummer / Barcode")
    udi_di = models.CharField(max_length=80, blank=True, default="", verbose_name="UDI-DI (GTIN)")
    ce_notified_body = models.CharField(max_length=10, blank=True, default="", verbose_name="CE-Kennnummer (z. B. 0123)")
    year_of_manufacture = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Baujahr")
    acquired_at = models.DateField(null=True, blank=True, verbose_name="Anschaffungsdatum")
    decommissioned_at = models.DateField(null=True, blank=True, verbose_name="Außerbetriebnahme")
    # Nur beim CSV-Stammdatenimport gesetzt (core/masterdata_import.py); frühere
    # Prüfungen liegen auf Papier, es entstehen keine rückdatierten Einträge.
    legacy_imported_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        verbose_name=_("Aus Altbestand übernommen am"),
        help_text=_("Beim CSV-Import gesetzt. Frühere Prüfungen und Einweisungen liegen auf Papier."),
    )

    # Standort & Status
    location = models.CharField(
        max_length=120,
        default="Wache",
        verbose_name="Standort / Fahrzeug",
        help_text="z. B. RTW 01/83-01 oder Gerätelager",
    )
    current_status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.READY,
        verbose_name="Betriebsstatus",
    )
    status_note = models.CharField(max_length=300, blank=True, default="", verbose_name="Status-Bemerkung")

    # Prüfvorschriften & Intervalle (Monate)
    requires_training = models.BooleanField(
        default=True,
        verbose_name="Einweisungspflichtig gem. § 11 MPBetreibV",
        help_text="Erfordert vor der Anwendung/Prüfung eine dokumentierte Geräteeinweisung.",
    )
    is_anlage_1 = models.BooleanField(default=True, verbose_name="Anlage 1 MPBetreibV (STK-Pflicht)")
    is_anlage_2 = models.BooleanField(default=False, verbose_name="Anlage 2 MPBetreibV (MTK-Pflicht)")
    stk_interval_months = models.PositiveSmallIntegerField(default=24, verbose_name="STK-Intervall (Monate)")
    mtk_interval_months = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="MTK-Intervall (Monate)")
    dguv_interval_months = models.PositiveSmallIntegerField(default=12, verbose_name="DGUV V3 Intervall (Monate)")

    # Fälligkeitsdaten
    next_stk_date = models.DateField(null=True, blank=True, verbose_name="Nächste STK")
    next_mtk_date = models.DateField(null=True, blank=True, verbose_name="Nächste MTK")
    next_dguv_date = models.DateField(null=True, blank=True, verbose_name="Nächste DGUV V3")
    last_routine_check = models.DateTimeField(null=True, blank=True, verbose_name="Letzter Funktionscheck")

    # Handbuch & Kurzanleitung
    manual_url = models.URLField(blank=True, default="", verbose_name="Online-Bedienungsanleitung")
    notes = models.TextField(blank=True, default="", verbose_name="Hinweise / Medizinproduktebuch-Notizen")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "name"]
        constraints = [
            models.UniqueConstraint(fields=["station", "slug"], name="unique_station_medical_device_slug"),
        ]
        indexes = [
            models.Index(fields=["station", "current_status"], name="med_dev_station_status_idx"),
            models.Index(fields=["station", "next_stk_date"], name="med_dev_station_stk_idx"),
        ]

    def __str__(self) -> str:
        loc = f" [{self.location}]" if self.location else ""
        return f"{self.name}{loc}"

    @property
    def next_stk(self):
        return self.next_stk_date

    @property
    def next_mtk(self):
        return self.next_mtk_date

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        update_fields = kwargs.get("update_fields")
        if update_fields is None or "current_status" in update_fields:
            from .device_status import mirror_to_asset

            mirror_to_asset(self)

    @property
    def urgency(self) -> dict:
        """Dynamische 4-Stufen Ampel (overdue, critical, warning, ok)."""
        today = timezone.localdate()
        date_candidates = []
        if self.is_anlage_1 and self.next_stk_date:
            date_candidates.append(("STK", self.next_stk_date))
        if self.is_anlage_2 and self.next_mtk_date:
            date_candidates.append(("MTK", self.next_mtk_date))
        if self.next_dguv_date:
            date_candidates.append(("DGUV V3", self.next_dguv_date))

        if not date_candidates:
            return {
                "level": "ok",
                "days": 999,
                "color": "emerald",
                "label": "Keine Frist fällig",
                "type": None,
                "due_date": None,
            }

        date_candidates.sort(key=lambda x: x[1])
        test_type, earliest_date = date_candidates[0]
        days = (earliest_date - today).days

        if days < 0:
            return {
                "level": "overdue",
                "days": days,
                "color": "rose",
                "label": f"{test_type} überfällig seit {abs(days)}d",
                "type": test_type,
                "due_date": earliest_date,
            }
        if days <= 30:
            return {
                "level": "critical",
                "days": days,
                "color": "amber",
                "label": f"{test_type} fällig in {days}d",
                "type": test_type,
                "due_date": earliest_date,
            }
        if days <= 60:
            return {
                "level": "warning",
                "days": days,
                "color": "yellow",
                "label": f"{test_type} fällig in {days}d",
                "type": test_type,
                "due_date": earliest_date,
            }
        return {
            "level": "ok",
            "days": days,
            "color": "emerald",
            "label": f"{test_type} in {days}d",
            "type": test_type,
            "due_date": earliest_date,
        }

    @property
    def is_due_soon(self) -> bool:
        return self.urgency["level"] in ("overdue", "critical", "warning")


class MaintenanceLog(models.Model):
    """Dokumentation von STK (§ 12), MTK (§ 15), DGUV V3 und Reparaturen im Medizinproduktebuch (§ 13 MPBetreibV)."""

    class Kind(models.TextChoices):
        STK = "stk", "Sicherheitstechnische Kontrolle (STK)"
        MTK = "mtk", "Messtechnische Kontrolle (MTK)"
        DGUV = "dguv", "DGUV Vorschrift 3 (Elektrische Prüfung)"
        REPAIR = "repair", "Instandsetzung / Reparatur"
        INSPECTION = "inspection", "Herstellerwartung"

    device = models.ForeignKey(MedicalDevice, on_delete=models.PROTECT, related_name="maintenance_logs")
    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="mpg_maintenance_logs")
    kind = models.CharField(max_length=20, choices=Kind.choices, verbose_name="Prüfungsart")
    performed_at = models.DateField(default=timezone.localdate, verbose_name="Prüfungsdatum")
    performed_by = models.CharField(max_length=140, verbose_name="Prüfer / Medizintechnik-Fachbetrieb")
    passed = models.BooleanField(default=True, verbose_name="Bestanden (Keine Sicherheitsmängel)")
    next_due_date = models.DateField(null=True, blank=True, verbose_name="Nächste Fälligkeit")
    findings = models.TextField(blank=True, default="", verbose_name="Prüfbefund / Festgestellte Mängel")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="created_maintenance_logs")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-performed_at", "-created_at"]
        indexes = [
            models.Index(fields=["station", "-performed_at"], name="maint_station_perf_idx"),
        ]

    def save(self, *args, **kwargs):
        # Medizinproduktebuch: Ein Prüfeintrag wird nie geändert; eine Korrektur
        # ist ein neuer Eintrag (AGENTS.md § 4).
        if self.pk:
            raise ValidationError("Prüf- und Wartungseinträge dürfen nicht verändert werden.")
        _require_same_station(self.device, self.station_id, "Wartungseintrag")
        super().save(*args, **kwargs)

        # Automatische Aktualisierung der Fristen am Gerät
        if self.passed and self.next_due_date:
            updated = False
            if self.kind == self.Kind.STK:
                self.device.next_stk_date = self.next_due_date
                updated = True
            elif self.kind == self.Kind.MTK:
                self.device.next_mtk_date = self.next_due_date
                updated = True
            elif self.kind == self.Kind.DGUV:
                self.device.next_dguv_date = self.next_due_date
                updated = True

            if self.device.current_status == MedicalDevice.Status.MAINTENANCE:
                self.device.current_status = MedicalDevice.Status.READY
                updated = True

            if updated:
                self.device.save(update_fields=["next_stk_date", "next_mtk_date", "next_dguv_date", "current_status", "updated_at"])

    def delete(self, *args, **kwargs):
        raise ValidationError("Prüf- und Wartungseinträge dürfen nicht gelöscht werden.")


class DeviceTrainingRecord(models.Model):
    """Dokumentation von Einweisungen nach § 11 MPBetreibV (Basis des digitalen Gerätepasses)."""

    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="device_trainings")
    device = models.ForeignKey(MedicalDevice, on_delete=models.PROTECT, related_name="trainings")
    trainee = models.ForeignKey(User, on_delete=models.PROTECT, related_name="device_trainings")
    instructor = models.CharField(max_length=140, verbose_name="Einweiser / Gerätebeauftragter (§ 11 MPBetreibV)")
    trained_at = models.DateField(default=timezone.localdate, verbose_name="Schulungsdatum")
    valid_until = models.DateField(
        null=True,
        blank=True,
        verbose_name="Gültig bis",
        help_text="Optionales Ablaufdatum der Einweisung (leer = unbegrenzt gültig)",
    )
    notes = models.CharField(max_length=300, blank=True, default="", verbose_name="Bemerkung")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-trained_at", "-created_at"]
        indexes = [
            models.Index(fields=["station", "trainee"], name="dev_train_station_user_idx"),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Einweisungsnachweise dürfen nicht verändert werden.")
        _require_same_station(self.device, self.station_id, "Einweisungsnachweis")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Einweisungsnachweise dürfen nicht gelöscht werden.")

    @property
    def is_valid(self) -> bool:
        if self.valid_until is None:
            return True
        return self.valid_until >= timezone.localdate()


class DeviceRoutineCheck(PaperBackfillRecord, models.Model):
    """Tägliche oder schichtweise Funktionskontrolle gem. Herstellervorgaben und Betreiberplan.

    ``checked_at`` ist die Erfassung (auch für das 5-Minuten-Storno). Bei einem
    Nachtrag vom Papierbogen steht die Zeit laut Bogen in ``occurred_at``
    (``core/paper_backfill.py``).
    """

    BACKFILL_ENTRY_FIELD = "checked_at"

    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="device_routine_checks")
    device = models.ForeignKey(MedicalDevice, on_delete=models.PROTECT, related_name="routine_checks")
    performed_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="device_routine_checks")
    checked_at = models.DateTimeField(auto_now_add=True)
    passed = models.BooleanField(default=True, verbose_name="Funktionskontrolle bestanden")
    battery_ok = models.BooleanField(default=True, verbose_name="Akkus / Energieversorgung einsatzklar")
    visual_ok = models.BooleanField(default=True, verbose_name="Sichtprüfung / Zubehör vollständig")
    function_ok = models.BooleanField(default=True, verbose_name="Selbsttest / Funktionsprüfung OK")
    notes = models.CharField(max_length=300, blank=True, default="", verbose_name="Feststellungen / Notiz")
    is_cancellation = models.BooleanField(
        default=False,
        verbose_name="Storno-Eintrag",
        help_text="Kennzeichnet diesen Eintrag als Storno einer vorangegangenen Funktionskontrolle.",
    )
    cancels_check = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="cancellation_records",
        verbose_name="Stornierte Funktionskontrolle",
    )
    is_paper_backfill = models.BooleanField("Nachtrag vom Papierbogen", default=False)
    occurred_at = models.DateTimeField("Ereigniszeitpunkt (Papierbogen)", null=True, blank=True)

    class Meta:
        ordering = ["-checked_at"]
        indexes = [
            models.Index(fields=["station", "-checked_at"], name="dev_check_station_time_idx"),
        ]
        constraints = [backfill_constraint("deviceroutinecheck")]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Funktionskontrollen dürfen nicht verändert werden.")
        _require_same_station(self.device, self.station_id, "Funktionskontrolle")
        # Ob diese Kontrolle das Gerät gesperrt hat (für die Meldung in der Ansicht).
        self.device_locked = False
        if not self.is_cancellation:
            # Bestanden ist eine Kontrolle nur, wenn jeder Prüfpunkt bestätigt ist.
            self.passed = bool(self.battery_ok and self.visual_ok and self.function_ok)
        super().save(*args, **kwargs)

        if not self.is_cancellation:
            update_fields = ["updated_at"]
            # „Letzter Funktionscheck“ nach Ereigniszeit: Ein älterer Nachtrag
            # schiebt ihn nicht zurück.
            last = self.device.last_routine_check
            if not self.is_paper_backfill or last is None or self.event_at > last:
                self.device.last_routine_check = self.event_at
                update_fields.append("last_routine_check")
            if not self.passed and self.device.current_status != MedicalDevice.Status.DECOMMISSIONED:
                # Sperre mit Mangel; aufgehoben wird sie nur über die Freigabe
                # (core/device_status.py). Eine bestandene Kontrolle hebt nichts auf.
                from .wachalltag_models import Defect

                failed = [
                    label
                    for ok, label in (
                        (self.battery_ok, "Energieversorgung"),
                        (self.visual_ok, "Sichtprüfung/Zubehör"),
                        (self.function_ok, "Selbsttest/Funktion"),
                    )
                    if not ok
                ]
                # Ein Nachtrag sperrt nur, wenn er nach der Zeit laut Bogen die
                # neueste gültige Kontrolle ist. Liegt eine neuere vor, gilt
                # deren Ergebnis; der Mangel hält das „Nein“ vom Bogen trotzdem
                # fest (Priorität „Wichtig“ statt „Dringend“).
                superseded = self.is_paper_backfill and self._newer_valid_check_exists()
                backfill_lines = ""
                if self.is_paper_backfill:
                    from django.conf import settings
                    from django.utils import translation
                    from django.utils.translation import gettext

                    # Gespeichert in der Wachensprache (wie andere Mangeltexte).
                    with translation.override(settings.LANGUAGE_CODE):
                        backfill_lines = f"{self.paper_backfill_label}\n"
                        if superseded:
                            backfill_lines += gettext(
                                "Eine neuere Funktionskontrolle liegt vor; das Gerät wurde deshalb nicht gesperrt."
                            ) + "\n"
                Defect.objects.create(
                    station_id=self.station_id,
                    medical_device=self.device,
                    title=f"Funktionskontrolle nicht bestanden: {self.device.name}"[:160],
                    description=(
                        f"{backfill_lines}Nicht in Ordnung: {', '.join(failed)}\n"
                        f"Standort: {self.device.location}\n\n{self.notes}"
                    ).strip(),
                    asset_ref=f"{self.device.name} ({self.device.inventory_number or self.device.serial_number})"[:160],
                    priority=Defect.Priority.IMPORTANT if superseded else Defect.Priority.URGENT,
                    status=Defect.Status.OPEN,
                    category=Defect.Category.DEVICE,
                    created_by=self.performed_by,
                )
                if not superseded:
                    self.device.current_status = MedicalDevice.Status.OOB
                    self.device.status_note = f"Funktionskontrolle nicht bestanden: {', '.join(failed)}"[:300]
                    update_fields += ["current_status", "status_note"]
                    self.device_locked = True
            self.device.save(update_fields=update_fields)
        else:
            # Storno-Eintrag: Letzte gültige Kontrolle ermitteln
            cancelled_ids = DeviceRoutineCheck.objects.filter(
                device=self.device, is_cancellation=True
            ).values_list("cancels_check_id", flat=True)
            from .paper_backfill import newest_event_first

            last_valid = newest_event_first(
                DeviceRoutineCheck.objects.filter(device=self.device, is_cancellation=False)
                .exclude(id__in=cancelled_ids)
                .exclude(id=self.cancels_check_id),
                "checked_at",
            ).first()
            self.device.last_routine_check = last_valid.event_at if last_valid else None
            self.device.save(update_fields=["last_routine_check", "updated_at"])

    def _newer_valid_check_exists(self) -> bool:
        """Gibt es eine nicht stornierte Kontrolle, die nach Ereigniszeit neuer ist?"""
        from .paper_backfill import event_time

        cancelled_ids = DeviceRoutineCheck.objects.filter(
            device_id=self.device_id, is_cancellation=True
        ).values_list("cancels_check_id", flat=True)
        return (
            DeviceRoutineCheck.objects.filter(device_id=self.device_id, is_cancellation=False)
            .exclude(pk=self.pk)
            .exclude(id__in=cancelled_ids)
            .annotate(event_time=event_time("checked_at"))
            .filter(event_time__gt=self.event_at)
            .exists()
        )

    def delete(self, *args, **kwargs):
        raise ValidationError("Funktionskontrollen dürfen nicht gelöscht werden.")

    @property
    def is_cancelled(self) -> bool:
        return self.cancellation_records.exists()

    @property
    def is_within_storno_window(self) -> bool:
        age = timezone.now() - self.checked_at
        return timedelta(0) <= age <= timedelta(minutes=5)

    def can_storno(self, user) -> bool:
        if self.is_cancellation or self.is_cancelled:
            return False
        if self.performed_by_id != getattr(user, "id", None):
            return False
        return self.is_within_storno_window
