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

from .models import Station


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
        OOB = "oob", "Außer Betrieb (Gesperrt)"
        DECOMMISSIONED = "decommissioned", "Ausgemustert"

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

    device = models.ForeignKey(MedicalDevice, on_delete=models.CASCADE, related_name="maintenance_logs")
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


class DeviceTrainingRecord(models.Model):
    """Dokumentation von Einweisungen nach § 11 MPBetreibV (Basis des digitalen Gerätepasses)."""

    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="device_trainings")
    device = models.ForeignKey(MedicalDevice, on_delete=models.CASCADE, related_name="trainings")
    trainee = models.ForeignKey(User, on_delete=models.CASCADE, related_name="device_trainings")
    instructor = models.CharField(max_length=140, verbose_name="Einweiser / Gerätebeauftragter (§ 11 MPBetreibV)")
    trained_at = models.DateField(default=timezone.localdate, verbose_name="Schulungsdatum")
    notes = models.CharField(max_length=300, blank=True, default="", verbose_name="Bemerkung")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-trained_at"]
        constraints = [
            models.UniqueConstraint(fields=["device", "trainee"], name="unique_device_trainee_record"),
        ]
        indexes = [
            models.Index(fields=["station", "trainee"], name="dev_train_station_user_idx"),
        ]

    def save(self, *args, **kwargs):
        _require_same_station(self.device, self.station_id, "Einweisungsnachweis")
        super().save(*args, **kwargs)


class DeviceRoutineCheck(models.Model):
    """Tägliche oder schichtweise Funktionskontrolle gem. Herstellervorgaben und Betreiberplan."""

    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="device_routine_checks")
    device = models.ForeignKey(MedicalDevice, on_delete=models.CASCADE, related_name="routine_checks")
    performed_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="device_routine_checks")
    checked_at = models.DateTimeField(auto_now_add=True)
    passed = models.BooleanField(default=True, verbose_name="Funktionskontrolle bestanden")
    battery_ok = models.BooleanField(default=True, verbose_name="Akkus / Energieversorgung einsatzklar")
    visual_ok = models.BooleanField(default=True, verbose_name="Sichtprüfung / Zubehör vollständig")
    function_ok = models.BooleanField(default=True, verbose_name="Selbsttest / Funktionsprüfung OK")
    notes = models.CharField(max_length=300, blank=True, default="", verbose_name="Feststellungen / Notiz")

    class Meta:
        ordering = ["-checked_at"]
        indexes = [
            models.Index(fields=["station", "-checked_at"], name="dev_check_station_time_idx"),
        ]

    def save(self, *args, **kwargs):
        _require_same_station(self.device, self.station_id, "Funktionskontrolle")
        # Bestanden ist eine Kontrolle nur, wenn jeder Prüfpunkt bestätigt ist.
        self.passed = bool(self.battery_ok and self.visual_ok and self.function_ok)
        super().save(*args, **kwargs)

        self.device.last_routine_check = self.checked_at
        update_fields = ["last_routine_check", "updated_at"]
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
            Defect.objects.create(
                station_id=self.station_id,
                medical_device=self.device,
                title=f"Funktionskontrolle nicht bestanden: {self.device.name}"[:160],
                description=(
                    f"Nicht in Ordnung: {', '.join(failed)}\n"
                    f"Standort: {self.device.location}\n\n{self.notes}"
                ).strip(),
                asset_ref=f"{self.device.name} ({self.device.inventory_number or self.device.serial_number})"[:160],
                priority=Defect.Priority.URGENT,
                status=Defect.Status.OPEN,
                category=Defect.Category.DEVICE,
                created_by=self.performed_by,
            )
            self.device.current_status = MedicalDevice.Status.OOB
            self.device.status_note = f"Funktionskontrolle nicht bestanden: {', '.join(failed)}"[:300]
            update_fields += ["current_status", "status_note"]
        self.device.save(update_fields=update_fields)
