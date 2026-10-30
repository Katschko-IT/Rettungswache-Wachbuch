"""Formulare für das Medizinproduktebuch (MPG / MPBetreibV)."""
from __future__ import annotations

import re
from django import forms
from django.contrib.auth.models import User
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from .models import Membership
from .mpg_models import DeviceRoutineCheck, DeviceTrainingRecord, MaintenanceLog, MedicalDevice


class MedicalDeviceForm(forms.ModelForm):
    class Meta:
        model = MedicalDevice
        fields = [
            "name",
            "category",
            "risk_class",
            "manufacturer",
            "model_type",
            "serial_number",
            "inventory_number",
            "udi_di",
            "ce_notified_body",
            "year_of_manufacture",
            "acquired_at",
            "location",
            "current_status",
            "status_note",
            "is_anlage_1",
            "is_anlage_2",
            "stk_interval_months",
            "mtk_interval_months",
            "dguv_interval_months",
            "next_stk_date",
            "next_mtk_date",
            "next_dguv_date",
            "manual_url",
            "notes",
        ]
        widgets = {
            "acquired_at": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "next_stk_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "next_mtk_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "next_dguv_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "status_note": forms.TextInput(attrs={"placeholder": "z. B. Akku schwach, STK fällig"}),
            "location": forms.TextInput(attrs={"placeholder": "z. B. RTW 01/83-01 oder Notfallrucksack"}),
        }

    def __init__(self, *args, station=None, **kwargs):
        self.station = station
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.current_status == MedicalDevice.Status.OOB:
            # Gesperrte Geräte werden nur über „Gerät freigeben“ wieder einsatzklar.
            field = self.fields["current_status"]
            field.choices = [
                choice for choice in field.choices
                if choice[0] in {MedicalDevice.Status.OOB, MedicalDevice.Status.DECOMMISSIONED}
            ]
            field.help_text = "Gesperrt. Freigabe über „Gerät freigeben“ auf der Geräteseite."

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get("name")
        if name and not self.instance.pk:
            base_slug = slugify(name)[:50] or "device"
            slug = base_slug
            counter = 1
            station = self.station or (self.instance.station if hasattr(self.instance, "station") else None)
            if station:
                while MedicalDevice.objects.filter(station=station, slug=slug).exists():
                    slug = f"{base_slug}-{counter}"
                    counter += 1
            self.instance.slug = slug
        return cleaned_data


class MaintenanceLogForm(forms.ModelForm):
    # Ergebnis der Prüfung (STK/MTK/DGUV) aktiv wählen; „Bestanden“ ist nicht
    # vorbelegt. Nur ein bestandenes Ergebnis verschiebt die Frist am Gerät.
    passed = forms.TypedChoiceField(
        label=_("Ergebnis"),
        choices=(("yes", _("Bestanden")), ("no", _("Nicht bestanden"))),
        coerce=lambda value: value == "yes",
        widget=forms.RadioSelect,
        required=True,
        error_messages={"required": _("Bitte das Ergebnis wählen.")},
    )

    class Meta:
        model = MaintenanceLog
        fields = [
            "kind",
            "performed_at",
            "performed_by",
            "passed",
            "next_due_date",
            "findings",
        ]
        widgets = {
            "performed_at": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "next_due_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "findings": forms.Textarea(attrs={"rows": 3, "placeholder": "Befund, Prüfwerte, ausgetauschte Teile..."}),
            "performed_by": forms.TextInput(attrs={"placeholder": "Firma / Medizintechniker Name"}),
        }


YES = "yes"
NO = "no"
YES_NO_CHOICES = ((YES, _("Ja")), (NO, _("Nein")))


def _yes_no_field(label):
    """Pflichtfrage Ja/Nein ohne Vorauswahl.

    Ein Prüfnachweis entsteht nur, wenn die prüfende Person jeden Punkt
    selbst beantwortet. Ein fehlender Wert ist ein Fehler, weder „Ja“ noch
    „Nein“.
    """
    return forms.TypedChoiceField(
        label=label,
        choices=YES_NO_CHOICES,
        coerce=lambda value: value == YES,
        widget=forms.RadioSelect,
        required=True,
        error_messages={"required": _("Bitte Ja oder Nein wählen.")},
    )


class DeviceRoutineCheckForm(forms.ModelForm):
    battery_ok = _yes_no_field(_("Energieversorgung / Akkus geladen"))
    visual_ok = _yes_no_field(_("Sichtprüfung & Vollständigkeit (Kabel, Sensoren)"))
    function_ok = _yes_no_field(_("Selbsttest / Gerätestart fehlerfrei"))
    # Ausdruck oder QR-Text eines Geräte-Selbsttests. Wird nur als Notiz
    # gespeichert; das Ergebnis bestätigt die prüfende Person selbst.
    selftest_protocol = forms.CharField(
        required=False,
        max_length=500,
        label="Selbsttest-Protokoll (optional)",
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    CHECK_POINTS = ("battery_ok", "visual_ok", "function_ok")

    class Meta:
        model = DeviceRoutineCheck
        fields = [
            "battery_ok",
            "visual_ok",
            "function_ok",
            "notes",
        ]
        widgets = {
            "notes": forms.TextInput(attrs={"placeholder": "Bemerkung (optional bei Mängeln oder Auffälligkeiten)"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Das Modell setzt die Prüfpunkte auf True; im Formular darf davon
        # nichts als Vorauswahl ankommen.
        for name in self.CHECK_POINTS:
            self.initial.pop(name, None)
            self.fields[name].initial = None

    @property
    def check_points(self):
        return [self[name] for name in self.CHECK_POINTS]


class DeviceTrainingRecordForm(forms.ModelForm):
    class Meta:
        model = DeviceTrainingRecord
        fields = [
            "trainee",
            "instructor",
            "trained_at",
            "notes",
        ]
        widgets = {
            "trained_at": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "instructor": forms.TextInput(attrs={"placeholder": "Name des Gerätebeauftragten / Herstellers"}),
            "notes": forms.TextInput(attrs={"placeholder": "z. B. Erstschulung oder Re-Zertifizierung"}),
        }

    def __init__(self, *args, station=None, **kwargs):
        super().__init__(*args, **kwargs)
        if station:
            station_user_ids = Membership.objects.filter(
                station=station, is_active=True
            ).values_list("user_id", flat=True)
            self.fields["trainee"].queryset = User.objects.filter(
                id__in=station_user_ids
            ).order_by("last_name", "first_name")


class GroupTrainingForm(forms.Form):
    trainees = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label="Eingewiesene Mitarbeiter",
    )
    instructor = forms.CharField(
        max_length=140,
        label="Gerätebeauftragter / Einweiser (§ 11 MPBetreibV)",
        widget=forms.TextInput(attrs={"placeholder": "z. B. Max Mustermann (MPG-Beauftragter)"}),
    )
    trained_at = forms.DateField(
        label="Schulungsdatum",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    notes = forms.CharField(
        max_length=300,
        required=False,
        label="Schulungsinhalt / Notiz",
        widget=forms.TextInput(attrs={"placeholder": "z. B. Gruppeneinweisung Beatmung MEDUMAT"}),
    )

    def __init__(self, *args, station=None, **kwargs):
        super().__init__(*args, **kwargs)
        if station:
            station_user_ids = Membership.objects.filter(
                station=station, is_active=True
            ).values_list("user_id", flat=True)
            self.fields["trainees"].queryset = User.objects.filter(
                id__in=station_user_ids
            ).order_by("last_name", "first_name")
