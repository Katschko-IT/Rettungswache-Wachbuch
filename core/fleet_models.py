"""Fuhrpark-, Fahrzeug- und Hygienemanagement-Modelle für den Rettungsdienst.

Erfüllt StVZO (§ 29 HU jährlich für RTW/KTW), DGUV Vorschrift 70 (UVV),
DIN EN 1789 (Tragentisch-Wartung) und den RKI/VAH-Rahmenhygieneplan mit
revisionssicherem Desinfektionsprotokoll und automatischem Einwirkzeit-Sperrtimer.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext, gettext_lazy as _

from .models import Membership, Station


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
        """Fahrzeugzustand – fünf Zustände, ohne Einsatzphasen oder FMS-Status.

        Gespeichert werden seit 0.27 neutrale Werte (Migration 0069). Die
        früheren Codes („1“ … „6“) stehen nur noch in alten Audit-Einträgen;
        die Audit-Ansicht benennt sie neutral (``core.audit_labels``).
        """

        READY = "ready", _("Einsatzbereit")
        LIMITED = "limited", _("Eingeschränkt")
        DISINFECTION = "disinfection", _("Desinfektion")
        WORKSHOP = "workshop", _("Werkstatt")
        OUT_OF_SERVICE = "out_of_service", _("Außer Dienst")

    # Von Hand wählbar. „Desinfektion“ setzt nur das Desinfektionsprotokoll.
    SELECTABLE_STATUSES = (
        TacticalStatus.READY, TacticalStatus.LIMITED, TacticalStatus.WORKSHOP, TacticalStatus.OUT_OF_SERVICE,
    )
    # Fahrbereit (auch mit Einschränkung): während der Einwirkzeit nicht wählbar.
    AVAILABLE_STATUSES = (TacticalStatus.READY, TacticalStatus.LIMITED)
    # Zählt als „Einsatzbereit“ (Kennzahl und Filter); „Eingeschränkt“ zählt eigens.
    READY_STATUSES = (TacticalStatus.READY,)

    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="vehicles")
    slug = models.SlugField(max_length=64, help_text="Slug für QR-Code-URL z. B. rtw-01-83-01")
    call_sign = models.CharField(max_length=120, verbose_name="Funkrufname (OPTA)", help_text="z. B. Rotkreuz 01/83-01")
    license_plate = models.CharField(max_length=40, verbose_name="Amtliches Kennzeichen")
    vehicle_type = models.CharField(max_length=20, choices=VehicleType.choices, default=VehicleType.RTW)

    # Fahrzeugtechnik & Aufbau
    chassis_manufacturer = models.CharField(max_length=120, blank=True, default="Mercedes-Benz Sprinter", verbose_name="Fahrgestell")
    body_manufacturer = models.CharField(max_length=120, blank=True, default="Fahrtec Systeme", verbose_name="Kofferaufbau")
    year_of_manufacture = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Baujahr")

    # Fahrzeugzustand & Füllstände (Feldname aus historischen Gründen)
    tactical_status = models.CharField(
        max_length=20, choices=TacticalStatus.choices, default=TacticalStatus.READY,
        verbose_name=_("Fahrzeugzustand"),
    )
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
    def status_short(self) -> str:
        """Kurzform für Sperrbildschirm und Chips (die fünf Zustände sind kurz)."""
        return str(self.get_tactical_status_display())

    @property
    def is_disinfection_locked(self) -> bool:
        if not self.disinfection_locked_until:
            return False
        return timezone.now() < self.disinfection_locked_until

    @property
    def awaiting_crew_release(self) -> bool:
        """Einwirkzeit abgelaufen, Fahrzeug steht noch auf „Desinfektion“.

        Bewusst keine automatische Freigabe: Die Besatzung prüft das Fahrzeug
        und setzt den Status selbst; sie wird dazu benachrichtigt
        (``core.crew_notifications``).
        """
        return (
            self.tactical_status == self.TacticalStatus.DISINFECTION
            and self.disinfection_locked_until is not None
            and timezone.now() >= self.disinfection_locked_until
        )

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


# Erregernamen gehören nicht in Stufen-Namen (Produktgrenze, AGENTS.md § 1).
# Bewusst eine kleine Sperrliste mit Wortgrenzen, keine vollständige Prüfung:
# Kurze oder mehrdeutige Kürzel (VRE, Rota, HIV, TBC, SARS) nur als ganzes
# Wort, eindeutige Wortstämme (Noro…, Clostridi…) auch in Zusammensetzungen.
PATHOGEN_PATTERN = re.compile(
    r"\b(?:"
    r"\d?mrsa\w*|vre|\d?mrgn\w*|esbl\w*|"
    r"noro\w*|rota|rota(?:virus|viren)\w*|"
    r"c\.?\s?diff\w*|clostridi\w*|difficile\w*|"
    r"corona\w*|covid\w*|sars(?:-cov\S*)?|"
    r"influenza\w*|grippe\w*|tuberkulose\w*|tbc|masern\w*|hepatitis\w*|hiv|"
    r"meningokokk\w*|ebola\w*|skabies\w*|krätze\w*"
    r")(?!\w)",
    re.IGNORECASE,
)
PATHOGEN_MESSAGE = _("Bitte die Stufe nach Umfang oder Wirkbereich benennen, nicht nach Erregern.")

# Stufen nach Umfang bzw. Wirkbereich (Betreiberentscheid 0.27). Migration 0069
# legt dieselben Namen für bestehende Wachen an und ordnet die früheren Arten
# verlustfrei zu (je Art eine Stufe). Die Wache kann sie umbenennen.
DEFAULT_LEVEL_NAMES = (
    _("Routine-Wischdesinfektion"),
    _("Schlussdesinfektion (begrenzt viruzid/bakterizid)"),
    _("Schlussdesinfektion (viruzid)"),
    _("Schlussdesinfektion (sporizid)"),
    _("Grunddesinfektion"),
)

# Bis zum Funktionsmodell (0.28) stehen Schichtleitung und Admin für „Hygiene“.
DISINFECTION_DETAIL_ROLES = frozenset({Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN})


def contains_pathogen_term(text) -> bool:
    return bool(text) and PATHOGEN_PATTERN.search(str(text)) is not None


def neutral_disinfection_note(lock_until) -> str:
    """Statusbemerkung während der Einwirkzeit, ohne Art oder Erreger.

    Gespeichert in der Wachensprache, nicht in der Sprache der Person, die
    gerade das Protokoll erfasst.
    """
    with translation.override(settings.LANGUAGE_CODE):
        return gettext("Desinfektion bis %(time)s Uhr") % {"time": timezone.localtime(lock_until).strftime("%H:%M")}


class DisinfectantMaster(models.Model):
    """VAH- / RKI-gelistetes Desinfektionsmittel."""

    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="disinfectants")
    name = models.CharField(max_length=120, verbose_name="Handelsname")
    manufacturer = models.CharField(max_length=120, blank=True, default="", verbose_name="Hersteller")
    spectrum = models.CharField(max_length=120, default="Bakterizid, Levurozid, begrenzt viruzid", verbose_name="Wirkspektrum")
    default_exposure_minutes = models.PositiveSmallIntegerField(default=15, verbose_name="Standard-Einwirkzeit (Minuten)")
    is_vah_listed = models.BooleanField(default=True, verbose_name="VAH-gelistet")
    # Nicht löschen, sondern aus dem Gebrauch nehmen: Protokolle verweisen per
    # PROTECT auf das Mittel (core/evidence.py).
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("In Gebrauch"),
        help_text=_(
            "Mittel, die nicht mehr in Gebrauch sind, stehen im Desinfektionsprotokoll nicht mehr zur Wahl. "
            "Bestehende Nachweise bleiben erhalten."
        ),
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["station", "name"], name="unique_station_disinfectant"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.default_exposure_minutes} Min)"


class DisinfectionLevel(models.Model):
    """Stufe aus dem Desinfektionsplan der Wache: Stufe → Mittel → Freigaberegel.

    Namen benennen Umfang oder Wirkbereich, nie einen Erreger. Freigaberegel und
    Bestätigung wirken erst mit dem bestätigten Desinfektionsplan; bis dahin
    gilt das bisherige Verhalten (Mittel, Einwirkzeit und Sperre wählt das
    Protokollformular). Bezeichnungen pflegt jede Wache selbst.
    """

    class ReleaseRule(models.TextChoices):
        AFTER_DRYING = "dry", _("Nach Antrocknen")
        AFTER_EXPOSURE = "exposure", _("Nach Einwirkzeit")

    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="disinfection_levels")
    name = models.CharField(max_length=80, verbose_name=_("Stufe"))
    disinfectant = models.ForeignKey(
        DisinfectantMaster, on_delete=models.PROTECT, null=True, blank=True, related_name="levels",
        verbose_name=_("Desinfektionsmittel"),
    )
    release_rule = models.CharField(
        max_length=12, choices=ReleaseRule.choices, default=ReleaseRule.AFTER_EXPOSURE, verbose_name=_("Freigabe"),
    )
    exposure_minutes = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name=_("Einwirkzeit (Minuten)"))
    is_active = models.BooleanField(default=True, verbose_name=_("In Verwendung"))
    rule_confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Bestätigt am"))
    rule_confirmed_by = models.ForeignKey(
        User, on_delete=models.PROTECT, null=True, blank=True, related_name="+", verbose_name=_("Bestätigt von"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["station", "name"], name="unique_station_disinfection_level"),
            models.CheckConstraint(
                condition=models.Q(exposure_minutes__isnull=True) | models.Q(exposure_minutes__gte=1),
                name="disinf_level_minutes_positive",
            ),
            # Eine bestätigte Regel ist vollständig: Mittel und, bei „Nach
            # Einwirkzeit“, die Minuten.
            models.CheckConstraint(
                condition=models.Q(rule_confirmed_at__isnull=True) | (
                    models.Q(disinfectant__isnull=False)
                    & (models.Q(release_rule="dry") | models.Q(exposure_minutes__isnull=False))
                ),
                name="disinf_level_confirmed_complete",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_confirmed(self) -> bool:
        return self.rule_confirmed_at is not None

    @property
    def is_complete(self) -> bool:
        if not self.disinfectant_id:
            return False
        return self.release_rule == self.ReleaseRule.AFTER_DRYING or bool(self.exposure_minutes)

    @property
    def applied_minutes(self) -> int:
        if self.exposure_minutes:
            return self.exposure_minutes
        return self.disinfectant.default_exposure_minutes if self.disinfectant_id else 0

    def clean(self):
        super().clean()
        errors = {}
        if contains_pathogen_term(self.name):
            errors["name"] = PATHOGEN_MESSAGE
        if self.disinfectant_id and self.station_id and self.disinfectant.station_id != self.station_id:
            errors["disinfectant"] = _("Das Desinfektionsmittel gehört zu einer anderen Wache.")
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Auch außerhalb von Formularen (Shell, Import): kein Erregername.
        if contains_pathogen_term(self.name):
            raise ValidationError({"name": PATHOGEN_MESSAGE})
        _require_same_station(self.disinfectant, self.station_id, "Desinfektionsstufe (Mittel)")
        super().save(*args, **kwargs)


class DisinfectionProtocol(models.Model):
    """Revisionssicherer Nachweis einer Fahrzeugdesinfektion nach Stufe des Plans.

    Stufe, Einwirkzeit und Bemerkung sehen nur die durchführende Person,
    Schichtleitung und Admin (``details_visible_to``); alle anderen sehen
    „Desinfektion“ mit Datum, Mittel und Person.
    """

    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="disinfection_protocols")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="disinfections")
    performed_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="disinfections")
    disinfectant = models.ForeignKey(DisinfectantMaster, on_delete=models.PROTECT, related_name="protocols")
    # Leer nur bei programmatisch angelegten Protokollen: Das Formular verlangt
    # eine Stufe, Migration 0069 hat allen Altprotokollen eine zugeordnet.
    level = models.ForeignKey(
        DisinfectionLevel, on_delete=models.PROTECT, null=True, blank=True, related_name="protocols",
        verbose_name=_("Stufe"),
    )
    started_at = models.DateTimeField(default=timezone.now, verbose_name="Beginn Desinfektion")
    exposure_minutes = models.PositiveSmallIntegerField(default=15, verbose_name="Einwirkzeit (Minuten)")
    lock_timer_applied = models.BooleanField(default=True, verbose_name="Einwirkzeit-Sperre angewendet")
    notes = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Bemerkung (keine Patienten- oder Einsatzangaben)"),
        help_text=_(
            "Nur Angaben zur Desinfektion. Keine Namen, Diagnosen, Transportziele oder Einsatzdaten eintragen."
        ),
    )

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["station", "-started_at"], name="disinf_station_time_idx"),
        ]

    def details_visible_to(self, membership) -> bool:
        """Stufe, Einwirkzeit und Bemerkung: nur durchführende Person, Schichtleitung, Admin."""
        if membership is None or membership.station_id != self.station_id:
            return False
        return membership.user_id == self.performed_by_id or membership.role in DISINFECTION_DETAIL_ROLES

    def save(self, *args, **kwargs):
        _require_same_station(self.vehicle, self.station_id, "Desinfektionsprotokoll (Fahrzeug)")
        _require_same_station(self.disinfectant, self.station_id, "Desinfektionsprotokoll (Mittel)")
        _require_same_station(self.level, self.station_id, "Desinfektionsprotokoll (Stufe)")
        super().save(*args, **kwargs)

        # Fahrzeug aktualisieren
        self.vehicle.last_disinfection = self.started_at
        if self.lock_timer_applied and self.exposure_minutes > 0:
            lock_until = self.started_at + timedelta(minutes=self.exposure_minutes)
            self.vehicle.disinfection_locked_until = lock_until
            self.vehicle.tactical_status = Vehicle.TacticalStatus.DISINFECTION
            # Neutral: Die Stufe steht nur im Protokoll, nie im Fahrzeugzustand,
            # auf Display, Sperrbildschirm oder in der App.
            self.vehicle.status_note = neutral_disinfection_note(lock_until)
        self.vehicle.save(update_fields=["last_disinfection", "disinfection_locked_until", "tactical_status", "status_note", "updated_at"])


class VehicleHandover(models.Model):
    """Revisionssicheres Schichtübernahmeprotokoll (3-Minuten Express-Check)."""

    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="vehicle_handovers")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="handovers")
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

    # Ja/Nein-Prüfpunkte der Übernahme (Formular: Pflichtangabe ohne Vorauswahl).
    CHECKPOINTS = {
        "btm_seal_intact": _("BTM-Plombe unversehrt & geprüft"),
        "medical_devices_checked": _("Selbsttests der Medizingeräte in Ordnung"),
        "vehicle_clean": _("Patientenraum & Fahrerkabine einsatzklar/sauber"),
    }
    # Vorschlag für den Mangel, wenn ein Prüfpunkt mit „Nein“ beantwortet wurde.
    CHECKPOINT_DEFECTS = {
        "btm_seal_intact": _("BTM-Plombe nicht unversehrt"),
        "medical_devices_checked": _("Selbsttest eines Medizingeräts nicht in Ordnung"),
        "vehicle_clean": _("Patientenraum oder Fahrerkabine nicht einsatzklar"),
    }

    class Meta:
        ordering = ["-performed_at"]
        indexes = [
            models.Index(fields=["station", "-performed_at"], name="handover_station_time_idx"),
        ]

    @property
    def failed_checkpoints(self) -> list[str]:
        """Prüfpunkte, die bei der Übernahme mit „Nein“ beantwortet wurden."""
        return [name for name in self.CHECKPOINTS if getattr(self, name) is False]

    @property
    def failed_checkpoint_labels(self) -> list[str]:
        return [str(self.CHECKPOINTS[name]) for name in self.failed_checkpoints]

    def save(self, *args, **kwargs):
        _require_same_station(self.vehicle, self.station_id, "Schichtübernahme (Fahrzeug)")
        super().save(*args, **kwargs)

        # Aktuelle Füllstände und km-Stand am Fahrzeug aktualisieren
        self.vehicle.current_mileage = self.mileage
        self.vehicle.fuel_level_percent = self.fuel_percent
        self.vehicle.adblue_level_percent = self.adblue_percent
        self.vehicle.o2_pressure_bar = self.o2_pressure_bar
        self.vehicle.save(update_fields=["current_mileage", "fuel_level_percent", "adblue_level_percent", "o2_pressure_bar", "updated_at"])
