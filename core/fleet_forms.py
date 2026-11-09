"""Formulare für Fuhrpark, Fahrzeugverwaltung und RKI-Desinfektionsbuch."""
from __future__ import annotations

from datetime import datetime, timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.formats import number_format
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from .disinfection_plan import active_disinfectants, active_levels, apply_level_defaults
from .fleet_models import DisinfectantMaster, DisinfectionLevel, DisinfectionProtocol, Vehicle, VehicleHandover
from .paper_backfill import PaperBackfillFormMixin


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
            "has_adblue",
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
        if "adblue_level_percent" in self.fields:
            self.fields["adblue_level_percent"].required = False
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
        has_adblue = cleaned_data.get("has_adblue", True)
        adblue = cleaned_data.get("adblue_level_percent")
        if not has_adblue:
            cleaned_data["adblue_level_percent"] = 0
        elif adblue is None and "adblue_level_percent" in self.fields:
            self.add_error("adblue_level_percent", ValidationError(_("Bitte den AdBlue-Stand angeben."), code="required"))
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


class DisinfectionLevelSelect(forms.Select):
    """Auswahl der Desinfektionsstufe mit data-Attributen für den bestätigten Plan."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        if value:
            level = getattr(value, "instance", None)
            if level is None and hasattr(self, "levels_by_pk"):
                level = self.levels_by_pk.get(value) or self.levels_by_pk.get(str(value))
            if level:
                option["attrs"]["data-disinfectant"] = str(level.disinfectant_id or "")
                option["attrs"]["data-release-rule"] = str(level.release_rule or "")
                option["attrs"]["data-exposure-minutes"] = str(level.exposure_minutes or "")
                option["attrs"]["data-confirmed"] = "1" if getattr(level, "is_rule_confirmed", False) else "0"
        return option


# „Frei ab“ laut Papierbogen: höchstens so lange nach dem Beginn (fängt auch
# Tippfehler wie „Frei ab“ vor dem Beginn ab).
MAX_BACKFILL_RELEASE_MINUTES = 12 * 60


def minutes_until_release(start: datetime, release_time) -> int | None:
    """Minuten vom Beginn bis zur Uhrzeit „Frei ab“ (am selben oder am nächsten Tag).

    ``None``, wenn „Frei ab“ nicht nach dem Beginn liegt oder mehr als
    ``MAX_BACKFILL_RELEASE_MINUTES`` danach.
    """
    local_start = timezone.localtime(start)
    tz = timezone.get_current_timezone()
    release = timezone.make_aware(datetime.combine(local_start.date(), release_time), tz)
    if release <= local_start:
        release = timezone.make_aware(datetime.combine(local_start.date() + timedelta(days=1), release_time), tz)
    minutes = int((release - start).total_seconds() // 60)
    if minutes < 1 or minutes > MAX_BACKFILL_RELEASE_MINUTES:
        return None
    return minutes


class DisinfectionProtocolForm(PaperBackfillFormMixin, forms.ModelForm):
    """Desinfektion erfassen: Stufe aus dem Plan der Wache, ohne Vorauswahl.

    Bis der Desinfektionsplan bestätigt ist, bleiben Mittel, Einwirkzeit und
    Sperre wie bisher im Formular. Optional als Nachtrag vom Papierbogen mit
    dem Beginn laut Bogen (``core/paper_backfill.py``). Der Bogen nennt keine
    Stufe und keine Einwirkzeit (Entscheidung D2): Bei einem Nachtrag ist die
    Stufe freiwillig, und „Frei ab“ laut Bogen ergibt die Einwirkzeit.
    """

    released_at = forms.TimeField(
        required=False,
        label=_("Frei ab laut Papierbogen"),
        help_text=_(
            "Uhrzeit aus der Spalte „Frei ab“. Daraus ergibt sich die Einwirkzeit ab dem Beginn laut Bogen; "
            "die Angabe geht der Einwirkzeit oben vor."
        ),
        widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
    )

    class Meta:
        model = DisinfectionProtocol
        fields = [
            "level",
            "disinfectant",
            "exposure_minutes",
            "lock_timer_applied",
            "notes",
            "is_paper_backfill",
            "occurred_at",
        ]
        widgets = {
            "exposure_minutes": forms.NumberInput(attrs={"min": 1, "max": 120}),
            # Kein Beispiel mit Transport- oder Infektionsbezug (Produktgrenze).
            "notes": forms.TextInput(attrs={"placeholder": _("z. B. Trage und Griffe zusätzlich gewischt")}),
        }

    def __init__(self, *args, station=None, allow_backfill=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_paper_backfill(allow=allow_backfill)
        if allow_backfill:
            # Bei einem Nachtrag sind Stufe und Einwirkzeit freiwillig; der
            # Browser kennt das Häkchen nicht und prüft deshalb keine Pflicht.
            # Die Prüfung macht der Server, Eingaben bleiben dabei erhalten.
            self.use_required_attribute = False
        else:
            self.fields.pop("released_at", None)
        level = self.fields["level"]
        level.required = True
        level.empty_label = _("Bitte Stufe wählen")
        level.error_messages["required"] = _("Bitte eine Stufe wählen.")
        level.widget = DisinfectionLevelSelect(choices=level.choices)
        if allow_backfill and self.is_bound and self.is_backfill_requested:
            level.required = False
            self.fields["exposure_minutes"].required = False
        if station is None:
            # Ohne Wache keine Auswahl (jede Abfrage ist an eine Wache gebunden).
            level.queryset = DisinfectionLevel.objects.none()
            self.fields["disinfectant"].queryset = DisinfectantMaster.objects.none()
            return
        levels_qs = active_levels(station)
        level.queryset = levels_qs
        level.widget.levels_by_pk = {lvl.pk: lvl for lvl in levels_qs}
        level.widget.levels_by_pk.update({str(lvl.pk): lvl for lvl in levels_qs})

        # Nur Mittel in Gebrauch; alte Protokolle behalten ihr Mittel (PROTECT).
        choices = active_disinfectants(station)
        self.fields["disinfectant"].queryset = choices
        # Gibt es nur ein Mittel, ist es vorausgewählt (ein Tipp weniger). Die
        # Stufe bleibt immer ohne Vorauswahl.
        if not self.is_bound and choices.count() == 1:
            only = choices.first()
            self.initial.setdefault("disinfectant", only.pk)
            self.initial.setdefault("exposure_minutes", only.default_exposure_minutes)

        if self.is_bound:
            level_pk = self.data.get(self.add_prefix("level")) or self.data.get("level")
            if level_pk:
                selected_level = level.widget.levels_by_pk.get(level_pk) or level.widget.levels_by_pk.get(str(level_pk))
                if selected_level is None and hasattr(level.queryset, "filter"):
                    try:
                        selected_level = level.queryset.filter(pk=level_pk).first()
                    except (ValueError, TypeError):
                        pass
                if selected_level and getattr(selected_level, "is_rule_confirmed", False) and selected_level.disinfectant_id:
                    self.fields["disinfectant"].required = False
                    self.fields["exposure_minutes"].required = False

    def clean(self):
        cleaned_data = super().clean()
        level = cleaned_data.get("level")
        cleaned_data = apply_level_defaults(cleaned_data, level)
        if not cleaned_data.get("disinfectant"):
            self.add_error("disinfectant", ValidationError(_("Bitte ein Desinfektionsmittel auswählen."), code="required"))
        cleaned_data = self.clean_paper_backfill(cleaned_data)
        if self.backfill_allowed and cleaned_data.get("is_paper_backfill"):
            self._clean_backfill_release(cleaned_data)
        return cleaned_data

    def _clean_backfill_release(self, cleaned_data: dict) -> None:
        """Einwirkzeit eines Nachtrags aus „Frei ab“ laut Bogen (sonst wie eingetragen)."""
        release_time = cleaned_data.get("released_at")
        if release_time is None:
            if not cleaned_data.get("exposure_minutes") and "exposure_minutes" not in self.errors:
                self.add_error("exposure_minutes", ValidationError(
                    _("Bitte „Frei ab“ laut Bogen oder die Einwirkzeit angeben."), code="required",
                ))
            return
        start = cleaned_data.get("occurred_at")
        if start is None or "occurred_at" in self.errors:
            return  # Der Fehler steht an der Ereigniszeit.
        minutes = minutes_until_release(start, release_time)
        if minutes is None:
            self.add_error("released_at", ValidationError(
                _("„Frei ab“ muss nach dem Beginn laut Bogen liegen, höchstens 12 Stunden danach."), code="invalid",
            ))
            return
        cleaned_data["exposure_minutes"] = minutes
        cleaned_data["lock_timer_applied"] = True


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


class VehicleHandoverForm(PaperBackfillFormMixin, forms.ModelForm):
    """Fahrzeugübernahme: Jede Angabe wird aktiv gemacht, nichts ist vorbelegt.

    Optional als Nachtrag vom Papierbogen: Dann wird der km-Stand nicht mit dem
    letzten Stand verglichen; die Werte am Fahrzeug ändert der Nachtrag nur,
    wenn er die neueste Übernahme ist (``VehicleHandover.save``).
    """

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
            "is_paper_backfill",
            "occurred_at",
        ]
        widgets = {
            "notes": forms.TextInput(attrs={"placeholder": "Besonderheiten, z. B. Steinschlag Windschutzscheibe"}),
        }

    def __init__(self, *args, vehicle=None, allow_backfill=True, **kwargs):
        super().__init__(*args, **kwargs)
        if vehicle is None and getattr(self.instance, "vehicle_id", None):
            vehicle = self.instance.vehicle
        self.vehicle = vehicle
        if self.vehicle and not self.vehicle.has_adblue:
            self.fields["adblue_percent"].required = False
            self.fields["adblue_percent"].help_text = _("Entfällt (kein AdBlue-Tank)")
            self.fields["adblue_percent"].widget.attrs["disabled"] = True

        # Ein neues Modellobjekt bringt seine Standardwerte (100 %, 200 bar,
        # „Ja“) als Startwerte mit. Die Übernahme darf nichts vorbelegen.
        for name in self.fields:
            if name != "notes":
                self.initial.pop(name, None)
                self.fields[name].initial = None
        self.setup_paper_backfill(allow=allow_backfill)
        # Verlässlich ist der km-Stand erst nach einer gespeicherten Übernahme.
        # Neue oder aus dem Gerätemodul übernommene Fahrzeuge tragen sonst nur
        # den Platzhalter des Modells (10.000 km) und blockierten die erste
        # Übernahme.
        self.last_mileage = None
        if vehicle is not None and vehicle.pk and vehicle.handovers.exists():
            self.last_mileage = vehicle.current_mileage
            # Kein min-Attribut mit dem letzten Stand: Ein Nachtrag vom
            # Papierbogen darf darunter liegen; live prüft clean_mileage.
            self.fields["mileage"].help_text = _("zuletzt %(km)s km") % {
                "km": number_format(vehicle.current_mileage, force_grouping=True),
            }
            self.fields["o2_pressure_bar"].help_text = _("zuletzt %(bar)s bar") % {"bar": vehicle.o2_pressure_bar}
        elif vehicle is not None:
            self.fields["mileage"].help_text = _("Erste Übernahme: bitte den km-Stand vom Tacho eintragen.")

    def clean_adblue_percent(self):
        val = self.cleaned_data.get("adblue_percent")
        if self.vehicle and not self.vehicle.has_adblue:
            return 0 if val is None else val
        return val

    def clean(self):
        cleaned_data = super().clean()
        if self.vehicle and not self.vehicle.has_adblue:
            if not cleaned_data.get("adblue_percent"):
                cleaned_data["adblue_percent"] = 0
        return self.clean_paper_backfill(cleaned_data)

    def clean_mileage(self):
        mileage = self.cleaned_data["mileage"]
        if self.backfill_allowed and self.is_backfill_requested:
            # Nachtrag: Der Bogen ist älter als der letzte Stand am Fahrzeug.
            return mileage
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
        if self.vehicle and not self.vehicle.has_adblue:
            return [self["fuel_percent"]]
        return [self["fuel_percent"], self["adblue_percent"]]

    @property
    def checkpoint_fields(self):
        return [self[name] for name in VehicleHandover.CHECKPOINTS]


class DisinfectionLevelRuleForm(forms.ModelForm):
    """Regel einer Desinfektionsstufe: Mittel, Freigabe und Einwirkzeit festlegen & bestätigen."""

    class Meta:
        model = DisinfectionLevel
        fields = [
            "disinfectant",
            "release_rule",
            "exposure_minutes",
        ]
        widgets = {
            "exposure_minutes": forms.NumberInput(attrs={"min": 1, "max": 180, "placeholder": _("Minuten")}),
        }

    def __init__(self, *args, station=None, **kwargs):
        super().__init__(*args, **kwargs)
        if station is not None:
            self.fields["disinfectant"].queryset = active_disinfectants(station)
        self.fields["disinfectant"].required = True
        self.fields["release_rule"].required = True

    def clean(self):
        cleaned_data = super().clean()
        rule = cleaned_data.get("release_rule")
        minutes = cleaned_data.get("exposure_minutes")
        if rule == DisinfectionLevel.ReleaseRule.AFTER_EXPOSURE and not minutes:
            self.add_error(
                "exposure_minutes",
                ValidationError(
                    _("Bei Freigabe nach Einwirkzeit ist die Dauer in Minuten erforderlich."),
                    code="required",
                ),
            )
        return cleaned_data
