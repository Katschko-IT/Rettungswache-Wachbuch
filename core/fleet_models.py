"""Fuhrpark-, Fahrzeug- und Hygienemanagement-Modelle für den Rettungsdienst.

Erfüllt StVZO (§ 29 HU jährlich für RTW/KTW), DGUV Vorschrift 70 (UVV),
DIN EN 1789 (Tragentisch-Wartung) und den RKI/VAH-Rahmenhygieneplan mit
revisionssicherem Desinfektionsprotokoll und automatischem Einwirkzeit-Sperrtimer.
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


class Vehicle(models.Model):
    """Einsatzfahrzeug im Fuhrpark (RTW, KTW, NEF, etc.)."""

    class VehicleType(models.TextChoices):
        RTW = "rtw", "Rettungswagen (RTW)"
        KTW = "ktw", "Krankentransportwagen (KTW)"
        NEF = "nef", "Notarzteinsatzfahrzeug (NEF)"
        KDOW = "kdow", "Kommandowagen (KdoW)"
        BKTW = "bktw", "Behindertentransportwagen (BKTW)"
        GW_SAN = "gw_san", "Gerätewagen Sanität (GW-San)"
        RESERVE = "reserve", "Reserve-Fahrzeug"
        OTHER = "other", "Sonstiges Fahrzeug"

    class TacticalStatus(models.TextChoices):
        STATUS_1 = "1", "Status 1: Einsatzbereit auf Wache"
        STATUS_2 = "2", "Status 2: Einsatzbereit auf Funk"
        STATUS_3 = "3", "Status 3: Einsatz übernommen / Anfahrt"
        STATUS_4 = "4", "Status 4: Am Einsatzort eingetroffen"
        STATUS_6 = "6", "Status 6: Außer Dienst / Nicht einsatzklar"
        DISINFECTION = "disinfection", "Desinfektion (Gesperrt)"
        WORKSHOP = "workshop", "Werkstatt / Reparatur"

    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="vehicles")
    slug = models.SlugField(max_length=64, help_text="Slug für QR-Code-URL z. B. rtw-01-83-01")
    call_sign = models.CharField(max_length=120, verbose_name="Funkrufname (OPTA)", help_text="z. B. Rotkreuz 01/83-01")
    license_plate = models.CharField(max_length=40, verbose_name="Amtliches Kennzeichen")
    vehicle_type = models.CharField(max_length=20, choices=VehicleType.choices, default=VehicleType.RTW)

    # Fahrzeugtechnik & Aufbau
    chassis_manufacturer = models.CharField(max_length=120, blank=True, default="Mercedes-Benz Sprinter", verbose_name="Fahrgestell")
    body_manufacturer = models.CharField(max_length=120, blank=True, default="Fahrtec Systeme", verbose_name="Kofferaufbau")
    year_of_manufacture = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Baujahr")

    # Taktischer Status & Füllstände
    tactical_status = models.CharField(max_length=20, choices=TacticalStatus.choices, default=TacticalStatus.STATUS_1)
    status_note = models.CharField(max_length=255, blank=True, default="", verbose_name="Status-Bemerkung")
    current_mileage = models.PositiveIntegerField(default=10000, verbose_name="Kilometerstand (km)")
    fuel_level_percent = models.PositiveSmallIntegerField(default=100, verbose_name="Kraftstoff (%)")
    adblue_level_percent = models.PositiveSmallIntegerField(default=100, verbose_name="AdBlue (%)")
    o2_pressure_bar = models.PositiveSmallIntegerField(default=200, verbose_name="Sauerstoffdruck (bar)")

    # Gesetzliche Prüffristen gem. StVZO / DGUV
    next_hu_date = models.DateField(null=True, blank=True, verbose_name="Nächste Hauptuntersuchung (§ 29 StVZO)")
    next_sp_date = models.DateField(null=True, blank=True, verbose_name="Nächste Sicherheitsprüfung (SP)")
    next_uvv_date = models.DateField(null=True, blank=True, verbose_name="Nächste UVV-Prüfung (DGUV V70)")
    next_stretcher_service_date = models.DateField(null=True, blank=True, verbose_name="Tragentisch-Wartung (10g / DIN EN 1789)")

    # Hygiene & Desinfektions-Sperrtimer
    last_disinfection = models.DateTimeField(null=True, blank=True, verbose_name="Letzte Desinfektion")
    disinfection_locked_until = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Desinfektions-Sperre aktiv bis",
        help_text="Fahrzeug darf vor Ablauf dieser Einwirkzeit nicht einsatzbereit gemeldet werden",
    )

    is_active = models.BooleanField(default=True, verbose_name="Im aktiven Wachdienst")
    notes = models.TextField(blank=True, default="", verbose_name="Fahrzeugakte / Besonderheiten")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["call_sign"]
        constraints = [
            models.UniqueConstraint(fields=["station", "slug"], name="unique_station_vehicle_slug"),
            models.UniqueConstraint(fields=["station", "license_plate"], name="unique_station_license_plate"),
        ]
        indexes = [
            models.Index(fields=["station", "tactical_status"], name="vehicle_station_status_idx"),
            models.Index(fields=["station", "next_hu_date"], name="vehicle_station_hu_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.call_sign} ({self.license_plate})"

    @property
    def is_disinfection_locked(self) -> bool:
        if not self.disinfection_locked_until:
            return False
        return timezone.now() < self.disinfection_locked_until

    @property
    def disinfection_remaining_seconds(self) -> int:
        if not self.is_disinfection_locked:
            return 0
        diff = (self.disinfection_locked_until - timezone.now()).total_seconds()
        return max(0, int(diff))

    @property
    def urgency(self) -> dict:
        """4-Stufen Ampel für Fristen (HU, UVV, Tragentisch)."""
        today = timezone.localdate()
        date_candidates = []
        if self.next_hu_date:
            date_candidates.append(("HU (§29)", self.next_hu_date))
        if self.next_uvv_date:
            date_candidates.append(("UVV (DGUV 70)", self.next_uvv_date))
        if self.next_stretcher_service_date:
            date_candidates.append(("Tragentisch (10g)", self.next_stretcher_service_date))
        if self.next_sp_date:
            date_candidates.append(("SP", self.next_sp_date))

        if not date_candidates:
            return {"level": "ok", "days": 999, "color": "emerald", "label": "Keine Fristen fällig", "due_date": None}

        date_candidates.sort(key=lambda x: x[1])
        label_type, earliest_date = date_candidates[0]
        days = (earliest_date - today).days

        if days < 0:
            return {
                "level": "overdue",
                "days": days,
                "color": "rose",
                "label": f"{label_type} überfällig seit {abs(days)}d",
                "due_date": earliest_date,
            }
        if days <= 30:
            return {
                "level": "critical",
                "days": days,
                "color": "amber",
                "label": f"{label_type} fällig in {days}d",
                "due_date": earliest_date,
            }
        if days <= 60:
            return {
                "level": "warning",
                "days": days,
                "color": "yellow",
                "label": f"{label_type} fällig in {days}d",
                "due_date": earliest_date,
            }
        return {
            "level": "ok",
            "days": days,
            "color": "emerald",
            "label": f"{label_type} in {days}d",
            "due_date": earliest_date,
        }


class DisinfectantMaster(models.Model):
    """VAH- / RKI-gelistetes Desinfektionsmittel."""

    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="disinfectants")
    name = models.CharField(max_length=120, verbose_name="Handelsname")
    manufacturer = models.CharField(max_length=120, blank=True, default="", verbose_name="Hersteller")
    spectrum = models.CharField(max_length=120, default="Bakterizid, Levurozid, begrenzt viruzid", verbose_name="Wirkspektrum")
    default_exposure_minutes = models.PositiveSmallIntegerField(default=15, verbose_name="Standard-Einwirkzeit (Minuten)")
    is_vah_listed = models.BooleanField(default=True, verbose_name="VAH-gelistet")

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["station", "name"], name="unique_station_disinfectant"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.default_exposure_minutes} Min)"


class DisinfectionProtocol(models.Model):
    """Revisionssicherer Nachweis über Wisch-, Schluss- und Grunddesinfektionen."""

    class Kind(models.TextChoices):
        ROUTINE = "routine", "Routine-Wischdesinfektion (Nach Transport)"
        FINAL_MRSA = "mrsa", "Gezielte Schlussdesinfektion: MRSA / VRE / 3MRGN"
        FINAL_NORO = "noro", "Gezielte Schlussdesinfektion: Norovirus / Rotavirus"
        FINAL_C_DIFF = "c_diff", "Gezielte Schlussdesinfektion: Clostridioides difficile (sporentötend)"
        BASE_MONTHLY = "base", "Monatliche Grunddesinfektion & Aufbereitung"

    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="disinfection_protocols")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="disinfections")
    performed_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="disinfections")
    disinfectant = models.ForeignKey(DisinfectantMaster, on_delete=models.PROTECT, related_name="protocols")
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.ROUTINE)
    started_at = models.DateTimeField(default=timezone.now, verbose_name="Beginn Desinfektion")
    exposure_minutes = models.PositiveSmallIntegerField(default=15, verbose_name="Einwirkzeit (Minuten)")
    lock_timer_applied = models.BooleanField(default=True, verbose_name="Einwirkzeit-Sperre angewendet")
    notes = models.CharField(max_length=255, blank=True, default="", verbose_name="Bemerkungen / Transportgrund")

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["station", "-started_at"], name="disinf_station_time_idx"),
        ]

    def save(self, *args, **kwargs):
        _require_same_station(self.vehicle, self.station_id, "Desinfektionsprotokoll (Fahrzeug)")
        super().save(*args, **kwargs)

        # Fahrzeug aktualisieren
        self.vehicle.last_disinfection = self.started_at
        if self.lock_timer_applied and self.exposure_minutes > 0:
            lock_until = self.started_at + timedelta(minutes=self.exposure_minutes)
            self.vehicle.disinfection_locked_until = lock_until
            self.vehicle.tactical_status = Vehicle.TacticalStatus.DISINFECTION
            self.vehicle.status_note = f"Desinfektion läuft ({self.get_kind_display()}): Gesperrt bis {lock_until.strftime('%H:%M')} Uhr"
        self.vehicle.save(update_fields=["last_disinfection", "disinfection_locked_until", "tactical_status", "status_note", "updated_at"])


class VehicleHandover(models.Model):
    """Revisionssicheres Schichtübernahmeprotokoll (3-Minuten Express-Check)."""

    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="vehicle_handovers")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="handovers")
    crew_member = models.ForeignKey(User, on_delete=models.PROTECT, related_name="vehicle_handovers")
    performed_at = models.DateTimeField(auto_now_add=True)

    mileage = models.PositiveIntegerField(verbose_name="Kilometerstand")
    fuel_percent = models.PositiveSmallIntegerField(default=100, verbose_name="Tankfüllstand (%)")
    adblue_percent = models.PositiveSmallIntegerField(default=100, verbose_name="AdBlue (%)")
    o2_pressure_bar = models.PositiveSmallIntegerField(default=200, verbose_name="Sauerstoffdruck (bar)")

    btm_seal_intact = models.BooleanField(default=True, verbose_name="BTM-Plombe unversehrt")
    medical_devices_checked = models.BooleanField(default=True, verbose_name="Medizingeräte-Selbsttests OK")
    vehicle_clean = models.BooleanField(default=True, verbose_name="Patientenraum & Fahrerkabine sauber")
    notes = models.CharField(max_length=255, blank=True, default="", verbose_name="Feststellungen / Bemerkung")

    class Meta:
        ordering = ["-performed_at"]
        indexes = [
            models.Index(fields=["station", "-performed_at"], name="handover_station_time_idx"),
        ]

    def save(self, *args, **kwargs):
        _require_same_station(self.vehicle, self.station_id, "Schichtübernahme (Fahrzeug)")
        super().save(*args, **kwargs)

        # Aktuelle Füllstände und km-Stand am Fahrzeug aktualisieren
        self.vehicle.current_mileage = self.mileage
        self.vehicle.fuel_level_percent = self.fuel_percent
        self.vehicle.adblue_level_percent = self.adblue_percent
        self.vehicle.o2_pressure_bar = self.o2_pressure_bar
        self.vehicle.save(update_fields=["current_mileage", "fuel_level_percent", "adblue_level_percent", "o2_pressure_bar", "updated_at"])
