"""Formulare für Fuhrpark, Fahrzeugverwaltung und RKI-Desinfektionsbuch."""
from __future__ import annotations

from django import forms
from django.utils.text import slugify

from .fleet_models import DisinfectantMaster, DisinfectionProtocol, Vehicle, VehicleHandover


class VehicleForm(forms.ModelForm):
    class Meta:
        model = Vehicle
        fields = [
            "call_sign",
            "license_plate",
            "vehicle_type",
            "chassis_manufacturer",
            "body_manufacturer",
            "year_of_manufacture",
            "current_mileage",
            "fuel_level_percent",
            "adblue_level_percent",
            "o2_pressure_bar",
            "tactical_status",
            "status_note",
            "next_hu_date",
            "next_sp_date",
            "next_uvv_date",
            "next_stretcher_service_date",
            "notes",
        ]
        widgets = {
            "next_hu_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "next_sp_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "next_uvv_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "next_stretcher_service_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "call_sign": forms.TextInput(attrs={"placeholder": "z. B. Rotkreuz 01/83-01"}),
            "license_plate": forms.TextInput(attrs={"placeholder": "z. B. M-RK 8301"}),
        }

    def __init__(self, *args, station=None, **kwargs):
        self.station = station
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        call_sign = cleaned_data.get("call_sign")
        if call_sign and not self.instance.pk:
            base_slug = slugify(call_sign)[:50] or "vehicle"
            slug = base_slug
            counter = 1
            station = self.station or (self.instance.station if hasattr(self.instance, "station") else None)
            if station:
                while Vehicle.objects.filter(station=station, slug=slug).exists():
                    slug = f"{base_slug}-{counter}"
                    counter += 1
            self.instance.slug = slug
        return cleaned_data


class DisinfectionProtocolForm(forms.ModelForm):
    class Meta:
        model = DisinfectionProtocol
        fields = [
            "disinfectant",
            "kind",
            "exposure_minutes",
            "lock_timer_applied",
            "notes",
        ]
        widgets = {
            "exposure_minutes": forms.NumberInput(attrs={"min": 1, "max": 120}),
            "notes": forms.TextInput(attrs={"placeholder": "z. B. Schlussdesinfektion nach Infektionstransport"}),
        }

    def __init__(self, *args, station=None, **kwargs):
        super().__init__(*args, **kwargs)
        if station:
            choices = DisinfectantMaster.objects.filter(station=station).order_by("name")
            self.fields["disinfectant"].queryset = choices
            # Gibt es nur ein Mittel, ist es vorausgewählt (ein Tipp weniger).
            if not self.is_bound and choices.count() == 1:
                only = choices.first()
                self.initial.setdefault("disinfectant", only.pk)
                self.initial.setdefault("exposure_minutes", only.default_exposure_minutes)


class VehicleHandoverForm(forms.ModelForm):
    class Meta:
        model = VehicleHandover
        fields = [
            "mileage",
            "fuel_percent",
            "adblue_percent",
            "o2_pressure_bar",
            "btm_seal_intact",
            "medical_devices_checked",
            "vehicle_clean",
            "notes",
        ]
        widgets = {
            "notes": forms.TextInput(attrs={"placeholder": "Besonderheiten, z. B. Steinschlag Windschutzscheibe"}),
        }
