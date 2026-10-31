"""Formulare für Fuhrpark, Fahrzeugverwaltung und RKI-Desinfektionsbuch."""
from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError
from django.utils.formats import number_format
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from .disinfection_plan import active_disinfectants, active_levels
from .fleet_models import DisinfectantMaster, DisinfectionLevel, DisinfectionProtocol, Vehicle, VehicleHandover


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
        if self.instance.pk:
            # Den Status eines vorhandenen Fahrzeugs ändert nur das Cockpit:
            # dort gelten Desinfektionssperre und Audit. Das Bearbeiten-Formular
            # könnte beides sonst umgehen.
            del self.fields["tactical_status"]
            return
        # Einsatzbereit, Eingeschränkt, Werkstatt, Außer Dienst. Einsatzphasen
        # gibt es nicht, „Desinfektion“ setzt nur das Protokoll.
        self.fields["tactical_status"].choices = [
            (value, label) for value, label in Vehicle.TacticalStatus.choices
            if value in Vehicle.SELECTABLE_STATUSES
        ]

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
    """Desinfektion erfassen: Stufe aus dem Plan der Wache, ohne Vorauswahl.

    Bis der Desinfektionsplan bestätigt ist, bleiben Mittel, Einwirkzeit und
    Sperre wie bisher im Formular.
    """

    class Meta:
        model = DisinfectionProtocol
        fields = [
            "level",
            "disinfectant",
            "exposure_minutes",
            "lock_timer_applied",
            "notes",
        ]
        widgets = {
            "exposure_minutes": forms.NumberInput(attrs={"min": 1, "max": 120}),
            # Kein Beispiel mit Transport- oder Infektionsbezug (Produktgrenze).
            "notes": forms.TextInput(attrs={"placeholder": _("z. B. Trage und Griffe zusätzlich gewischt")}),
        }

    def __init__(self, *args, station=None, **kwargs):
        super().__init__(*args, **kwargs)
        level = self.fields["level"]
        level.required = True
        level.empty_label = _("Bitte Stufe wählen")
        level.error_messages["required"] = _("Bitte eine Stufe wählen.")
        if station is None:
            # Ohne Wache keine Auswahl (jede Abfrage ist an eine Wache gebunden).
            level.queryset = DisinfectionLevel.objects.none()
            self.fields["disinfectant"].queryset = DisinfectantMaster.objects.none()
            return
        level.queryset = active_levels(station)
        # Nur Mittel in Gebrauch; alte Protokolle behalten ihr Mittel (PROTECT).
        choices = active_disinfectants(station)
        self.fields["disinfectant"].queryset = choices
        # Gibt es nur ein Mittel, ist es vorausgewählt (ein Tipp weniger). Die
        # Stufe bleibt immer ohne Vorauswahl.
        if not self.is_bound and choices.count() == 1:
            only = choices.first()
            self.initial.setdefault("disinfectant", only.pk)
            self.initial.setdefault("exposure_minutes", only.default_exposure_minutes)


YES_NO_CHOICES = [("yes", _("Ja")), ("no", _("Nein"))]
# Größter plausibler Sprung zwischen zwei Übernahmen.
MAX_MILEAGE_STEP_KM = 2000
# Schnellwahl statt vorbelegter Prozentzahl; gespeichert wird der Prozentwert.
FILL_LEVEL_CHOICES = [(10, _("Reserve")), (25, "¼"), (50, "½"), (75, "¾"), (100, _("Voll"))]


class YesNoField(forms.TypedChoiceField):
    """Pflichtfrage Ja/Nein ohne Vorauswahl (kein vorab gesetztes Häkchen)."""

    widget = forms.RadioSelect

    def __init__(self, **kwargs):
        kwargs.setdefault("error_messages", {"required": _("Bitte Ja oder Nein wählen.")})
        super().__init__(
            choices=YES_NO_CHOICES, coerce=lambda value: value == "yes", empty_value=None, required=True, **kwargs,
        )


class FillLevelField(forms.TypedChoiceField):
    widget = forms.RadioSelect

    def __init__(self, **kwargs):
        kwargs.setdefault("error_messages", {"required": _("Bitte den Füllstand wählen.")})
        super().__init__(choices=FILL_LEVEL_CHOICES, coerce=int, empty_value=None, required=True, **kwargs)


class VehicleHandoverForm(forms.ModelForm):
    """Fahrzeugübernahme: Jede Angabe wird aktiv gemacht, nichts ist vorbelegt."""

    mileage = forms.IntegerField(
        label=_("km-Stand"),
        min_value=0,
        widget=forms.NumberInput(attrs={"inputmode": "numeric", "autocomplete": "off"}),
        error_messages={"required": _("Bitte den km-Stand eintragen.")},
    )
    o2_pressure_bar = forms.IntegerField(
        label=_("O₂ Druck (bar)"),
        min_value=0,
        max_value=300,
        widget=forms.NumberInput(attrs={"inputmode": "numeric", "autocomplete": "off"}),
        error_messages={"required": _("Bitte den Sauerstoffdruck eintragen.")},
    )
    fuel_percent = FillLevelField(label=_("Kraftstoff"))
    adblue_percent = FillLevelField(label=_("AdBlue"))
    btm_seal_intact = YesNoField(label=VehicleHandover.CHECKPOINTS["btm_seal_intact"])
    medical_devices_checked = YesNoField(label=VehicleHandover.CHECKPOINTS["medical_devices_checked"])
    vehicle_clean = YesNoField(label=VehicleHandover.CHECKPOINTS["vehicle_clean"])

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

    def __init__(self, *args, vehicle=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.vehicle = vehicle
        # Ein neues Modellobjekt bringt seine Standardwerte (100 %, 200 bar,
        # „Ja“) als Startwerte mit. Die Übernahme darf nichts vorbelegen.
        for name in self.fields:
            if name != "notes":
                self.initial.pop(name, None)
                self.fields[name].initial = None
        # Verlässlich ist der km-Stand erst nach einer gespeicherten Übernahme.
        # Neue oder aus dem Gerätemodul übernommene Fahrzeuge tragen sonst nur
        # den Platzhalter des Modells (10.000 km) und blockierten die erste
        # Übernahme.
        self.last_mileage = None
        if vehicle is not None and vehicle.pk and vehicle.handovers.exists():
            self.last_mileage = vehicle.current_mileage
            self.fields["mileage"].help_text = _("zuletzt %(km)s km") % {
                "km": number_format(vehicle.current_mileage, force_grouping=True),
            }
            self.fields["mileage"].widget.attrs["min"] = vehicle.current_mileage
            self.fields["o2_pressure_bar"].help_text = _("zuletzt %(bar)s bar") % {"bar": vehicle.o2_pressure_bar}
        elif vehicle is not None:
            self.fields["mileage"].help_text = _("Erste Übernahme: bitte den km-Stand vom Tacho eintragen.")

    def clean_mileage(self):
        mileage = self.cleaned_data["mileage"]
        last = self.last_mileage
        if last is not None and mileage < last:
            raise ValidationError(
                _("Der km-Stand darf nicht unter dem letzten Stand (%(km)s km) liegen."),
                code="mileage_below_last",
                params={"km": number_format(last, force_grouping=True)},
            )
        # Tippfehler-Schutz (eine Ziffer zu viel). Ohne bekannten Stand (keine
        # Übernahme oder 0 km) gibt es keine Obergrenze.
        if last and mileage > last + MAX_MILEAGE_STEP_KM:
            raise ValidationError(
                _(
                    "Mehr als %(step)s km seit dem letzten Stand (%(km)s km) – bitte den km-Stand prüfen. "
                    "Stimmt er, trägt die Wachleitung ihn in den Fahrzeugdaten ein."
                ),
                code="mileage_implausible",
                params={
                    "step": number_format(MAX_MILEAGE_STEP_KM, force_grouping=True),
                    "km": number_format(last, force_grouping=True),
                },
            )
        return mileage

    # Gruppen für die Vorlage (Zahlenfelder, Füllstände, Ja/Nein-Prüfpunkte).
    @property
    def number_fields(self):
        return [self["mileage"], self["o2_pressure_bar"]]

    @property
    def level_fields(self):
        return [self["fuel_percent"], self["adblue_percent"]]

    @property
    def checkpoint_fields(self):
        return [self[name] for name in VehicleHandover.CHECKPOINTS]
