"""Lager- und Materialwirtschaftsmodelle für den Rettungsdienst gem. AMG, MPDG & FEFO.

Unterstützt hierarchische Lagerorte (Zentrallager, RTW, Notfallkoffer),
Chargenverwaltung (Lot-Nr., PZN, GTIN), Verfallsdaten-Radar nach FEFO-Prinzip,
dynamische 'Out-of-Fridge'-Haltbarkeit für kühlpflichtige Notfallmedikamente
sowie ein revisionssicheres Buchungsjournal.
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


class StorageLocation(models.Model):
    """Hierarchischer Lagerort auf der Wache oder in einem Einsatzfahrzeug."""

    class Kind(models.TextChoices):
        CENTRAL = "central", "Hauptlager / Apotheke"
        VEHICLE = "vehicle", "Fahrzeug / RTW / KTW"
        CONTAINER = "container", "Koffer / Rucksack"
        FRIDGE = "fridge", "Medikamentenkühlschrank (2–8 °C)"
        OTHER = "other", "Sonstiger Lagerort"

    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="storage_locations")
    slug = models.SlugField(max_length=64, help_text="Eindeutiger Bezeichner z. B. rtw-01-schrank-1")
    name = models.CharField(max_length=120, verbose_name="Lagerort-Bezeichnung")
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.CENTRAL)
    is_cold_storage = models.BooleanField(default=False, verbose_name="Kühlpflichtiger Lagerort (Kühlschrank)")
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="Übergeordneter Lagerort",
    )
    description = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["kind", "name"]
        constraints = [
            models.UniqueConstraint(fields=["station", "slug"], name="unique_station_storage_location_slug"),
        ]

    def __str__(self) -> str:
        if self.parent:
            return f"{self.parent.name} → {self.name}"
        return self.name


class MedicalItem(models.Model):
    """Artikelstamm für Medikamente, Verbrauchsmaterial und Medizinprodukte."""

    class Category(models.TextChoices):
        MEDICATION = "med", "Notfallmedikamente & Ampullen"
        INFUSION = "infusion", "Infusionslösungen & Elektrolyte"
        AIRWAY = "airway", "Atemwegsmanagement & Beatmung"
        DIAGNOSTIC = "diag", "Diagnostik & Monitoring"
        BANDAGE = "bandage", "Verbandstoffe & Wundversorgung"
        HYGIENE = "hygiene", "Hygiene & Desinfektion"
        IMMOBILIZATION = "immo", "Immobilisation & Rettung"
        OTHER = "other", "Sonstiges Material"

    class Unit(models.TextChoices):
        AMPOULE = "amp", "Ampulle(n)"
        PIECE = "pcs", "Stück"
        PACK = "pack", "Packung(en)"
        BOTTLE = "btl", "Flasche(n)"
        ROLL = "roll", "Rolle(n)"
        CAN = "can", "Kanister / Dose"

    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="medical_items")
    slug = models.SlugField(max_length=64)
    name = models.CharField(max_length=160, verbose_name="Artikelbezeichnung")
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    unit = models.CharField(max_length=20, choices=Unit.choices, default=Unit.PIECE, verbose_name="Einheit")
    
    # Pharma- & Barcode-Standards
    pzn = models.CharField(max_length=20, blank=True, default="", verbose_name="PZN (Pharmazentralnummer)")
    gtin = models.CharField(max_length=30, blank=True, default="", verbose_name="GTIN / EAN")
    
    # Bestandssteuerung
    min_stock = models.PositiveIntegerField(default=5, verbose_name="Mindestbestand Wache")
    target_stock = models.PositiveIntegerField(default=10, verbose_name="Sollbestand Wache")

    # Kühlketten-Dynamik ("Out-of-Fridge"-Regel)
    requires_cooling = models.BooleanField(
        default=False,
        verbose_name="Kühlpflichtig (2–8 °C)",
        help_text="z. B. Rocuronium, Succinylcholin, Oxytocin",
    )
    room_temp_max_days = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Max. Tage bei Raumtemperatur",
        help_text="z. B. 84 Tage (= 12 Wochen) für Rocuronium ungekühlt auf dem RTW",
    )

    notes = models.TextField(blank=True, default="", verbose_name="Dosierung / Lagerhinweise")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "name"]
        constraints = [
            models.UniqueConstraint(fields=["station", "slug"], name="unique_station_medical_item_slug"),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def total_stock(self) -> int:
        return sum(si.quantity for si in self.stock_items.filter(batch__is_recalled=False))

    @property
    def is_under_min_stock(self) -> bool:
        return self.total_stock < self.min_stock


class ItemBatch(models.Model):
    """Spezifische Charge eines Artikels mit Verfallsdatum und Rückrufstatus."""

    item = models.ForeignKey(MedicalItem, on_delete=models.CASCADE, related_name="batches")
    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="item_batches")
    batch_number = models.CharField(max_length=60, verbose_name="Chargennummer (Lot)")
    
    # Ablaufdaten
    manufacturer_exp_date = models.DateField(verbose_name="Hersteller-MHD (aufgedruckt)")
    out_of_fridge_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Datum der Kühlkettenunterbrechung",
        help_text="Wann wurde die Charge auf das Fahrzeug entnommen?",
    )
    calculated_exp_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Effektives Verfallsdatum",
        help_text="Unter Berücksichtigung der Out-of-Fridge-Regel",
    )

    # BfArM Rückruf-Sperre
    is_recalled = models.BooleanField(default=False, verbose_name="Charge zurückgerufen / gesperrt")
    recall_reason = models.CharField(max_length=255, blank=True, default="", verbose_name="Rückrufgrund")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["calculated_exp_date", "manufacturer_exp_date"]
        constraints = [
            models.UniqueConstraint(fields=["item", "batch_number"], name="unique_item_batch_number"),
        ]
        indexes = [
            models.Index(fields=["station", "calculated_exp_date"], name="batch_station_exp_idx"),
            models.Index(fields=["station", "batch_number"], name="batch_station_lot_idx"),
        ]

    def save(self, *args, **kwargs):
        _require_same_station(self.item, self.station_id, "Charge")

        # Dynamische Haltbarkeit berechnen
        eff_date = self.manufacturer_exp_date
        if self.item.requires_cooling and self.item.room_temp_max_days and self.out_of_fridge_date:
            oof_limit = self.out_of_fridge_date + timedelta(days=self.item.room_temp_max_days)
            if oof_limit < eff_date:
                eff_date = oof_limit
        self.calculated_exp_date = eff_date

        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.item.name} (Lot: {self.batch_number}, MHD: {self.effective_date.isoformat()})"

    @property
    def effective_date(self) -> date:
        return self.calculated_exp_date or self.manufacturer_exp_date

    @property
    def urgency(self) -> dict:
        """FEFO-Ampel: overdue, critical (<=30d), warning (<=90d), ok (>90d), recalled."""
        if self.is_recalled:
            return {
                "level": "recalled",
                "days": -999,
                "color": "rose",
                "label": f"Gesperrt: {self.recall_reason or 'Rückruf'}",
            }

        today = timezone.localdate()
        days = (self.effective_date - today).days

        if days < 0:
            return {
                "level": "overdue",
                "days": days,
                "color": "rose",
                "label": f"Abgelaufen seit {abs(days)}d ({self.effective_date.strftime('%d.%m.%Y')})",
            }
        if days <= 30:
            return {
                "level": "critical",
                "days": days,
                "color": "amber",
                "label": f"Verfällt in {days}d ({self.effective_date.strftime('%d.%m.%Y')})",
            }
        if days <= 90:
            return {
                "level": "warning",
                "days": days,
                "color": "yellow",
                "label": f"Verfällt in {days}d ({self.effective_date.strftime('%d.%m.%Y')})",
            }
        return {
            "level": "ok",
            "days": days,
            "color": "emerald",
            "label": f"Haltbar bis {self.effective_date.strftime('%d.%m.%Y')} ({days}d)",
        }


class StockItem(models.Model):
    """Physischer Bestand einer bestimmten Charge an einem bestimmten Lagerort."""

    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="stock_items")
    item = models.ForeignKey(MedicalItem, on_delete=models.CASCADE, related_name="stock_items")
    batch = models.ForeignKey(ItemBatch, on_delete=models.CASCADE, related_name="stock_items")
    location = models.ForeignKey(StorageLocation, on_delete=models.CASCADE, related_name="stock_items")
    quantity = models.PositiveIntegerField(default=0, verbose_name="Menge")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["batch", "location"], name="unique_batch_at_location"),
        ]
        indexes = [
            models.Index(fields=["station", "location"], name="stock_station_loc_idx"),
        ]

    def save(self, *args, **kwargs):
        _require_same_station(self.item, self.station_id, "Bestandseintrag (Artikel)")
        _require_same_station(self.location, self.station_id, "Bestandseintrag (Lagerort)")
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.item.name} ({self.quantity} {self.item.get_unit_display()}) @ {self.location.name}"


class StockMovement(models.Model):
    """Append-Only Transaktionsprotokoll aller Materialbewegungen."""

    class Kind(models.TextChoices):
        INBOUND = "inbound", "Wareneingang / Beschaffung"
        OUTBOUND = "outbound", "Verbrauch"
        TRANSFER = "transfer", "Umlagerung (z. B. Lager → RTW)"
        DISCARD_EXPIRED = "discard_expired", "Ausscheidung (Verfall)"
        RECALL_QUARANTINE = "recall_quarantine", "Sperrung (BfArM-Rückruf)"
        INVENTORY_CORRECTION = "correction", "Inventur-Korrektur"

    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="stock_movements")
    item = models.ForeignKey(MedicalItem, on_delete=models.PROTECT, related_name="movements")
    batch = models.ForeignKey(ItemBatch, on_delete=models.PROTECT, related_name="movements")
    source_location = models.ForeignKey(
        StorageLocation,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="outbound_movements",
        verbose_name="Von Lagerort",
    )
    target_location = models.ForeignKey(
        StorageLocation,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="inbound_movements",
        verbose_name="Nach Lagerort",
    )
    quantity = models.PositiveIntegerField(verbose_name="Menge")
    kind = models.CharField(max_length=25, choices=Kind.choices, verbose_name="Buchungsart")
    actor = models.ForeignKey(User, on_delete=models.PROTECT, related_name="stock_movements")
    note = models.CharField(max_length=255, blank=True, default="", verbose_name="Grund / Beleg")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["station", "-created_at"], name="mvmnt_station_time_idx"),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Materialbuchungen sind revisionssicher und dürfen nicht verändert werden.")
        _require_same_station(self.item, self.station_id, "Buchungsjournal")
        super().save(*args, **kwargs)
