"""Formulare für Lager- und Materialwirtschaft (FEFO, Chargen, Bestände)."""
from __future__ import annotations

from django import forms
from django.utils.text import slugify

from .warehouse_models import ItemBatch, MedicalItem, StockItem, StockMovement, StorageLocation


class MedicalItemForm(forms.ModelForm):
    class Meta:
        model = MedicalItem
        fields = [
            "name",
            "category",
            "unit",
            "pzn",
            "gtin",
            "min_stock",
            "target_stock",
            "requires_cooling",
            "room_temp_max_days",
            "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Dosierung, Indikation, Fachinformation..."}),
            "pzn": forms.TextInput(attrs={"placeholder": "z. B. 01234567"}),
            "gtin": forms.TextInput(attrs={"placeholder": "z. B. 04012345678901"}),
        }

    def __init__(self, *args, station=None, **kwargs):
        self.station = station
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get("name")
        if name and not self.instance.pk:
            base_slug = slugify(name)[:50] or "item"
            slug = base_slug
            counter = 1
            station = self.station or (self.instance.station if hasattr(self.instance, "station") else None)
            if station:
                while MedicalItem.objects.filter(station=station, slug=slug).exists():
                    slug = f"{base_slug}-{counter}"
                    counter += 1
            self.instance.slug = slug
        return cleaned_data


class ItemBatchForm(forms.ModelForm):
    initial_location = forms.ModelChoiceField(
        queryset=StorageLocation.objects.none(),
        label="Einbuchen an Lagerort",
        required=True,
    )
    initial_quantity = forms.IntegerField(
        min_value=1,
        initial=10,
        label="Anfangsbestand (Menge)",
        required=True,
    )

    class Meta:
        model = ItemBatch
        fields = [
            "batch_number",
            "manufacturer_exp_date",
            "out_of_fridge_date",
        ]
        widgets = {
            "manufacturer_exp_date": forms.DateInput(attrs={"type": "date"}),
            "out_of_fridge_date": forms.DateInput(attrs={"type": "date"}),
            "batch_number": forms.TextInput(attrs={"placeholder": "z. B. LOT-98745A"}),
        }

    def __init__(self, *args, station=None, **kwargs):
        super().__init__(*args, **kwargs)
        if station:
            self.fields["initial_location"].queryset = StorageLocation.objects.filter(
                station=station
            ).order_by("name")


class StorageLocationForm(forms.ModelForm):
    class Meta:
        model = StorageLocation
        fields = ["name", "kind", "is_cold_storage", "parent", "description"]
        widgets = {
            "description": forms.TextInput(attrs={"placeholder": "z. B. Fach 3B rechts im RTW-Schrank"}),
        }

    def __init__(self, *args, station=None, **kwargs):
        self.station = station
        super().__init__(*args, **kwargs)
        if station:
            self.fields["parent"].queryset = StorageLocation.objects.filter(
                station=station
            ).order_by("name")

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get("name")
        if name and not self.instance.pk:
            base_slug = slugify(name)[:50] or "loc"
            slug = base_slug
            counter = 1
            station = self.station or (self.instance.station if hasattr(self.instance, "station") else None)
            if station:
                while StorageLocation.objects.filter(station=station, slug=slug).exists():
                    slug = f"{base_slug}-{counter}"
                    counter += 1
            self.instance.slug = slug
        return cleaned_data


class StockTransferForm(forms.Form):
    source_location = forms.ModelChoiceField(
        queryset=StorageLocation.objects.none(),
        label="Von Lagerort",
        required=True,
    )
    target_location = forms.ModelChoiceField(
        queryset=StorageLocation.objects.none(),
        label="Nach Lagerort (z. B. RTW)",
        required=True,
    )
    quantity = forms.IntegerField(min_value=1, initial=1, label="Menge", required=True)
    mark_out_of_fridge = forms.BooleanField(
        required=False,
        initial=True,
        label="Kühlkette unterbrochen (Out-of-Fridge aktivieren)",
    )
    note = forms.CharField(max_length=200, required=False, label="Grund / Notiz")

    def __init__(self, *args, station=None, **kwargs):
        super().__init__(*args, **kwargs)
        if station:
            self.fields["source_location"].queryset = StorageLocation.objects.filter(
                station=station
            ).order_by("name")
            self.fields["target_location"].queryset = StorageLocation.objects.filter(
                station=station
            ).order_by("name")


class BatchRecallForm(forms.Form):
    batch_number = forms.CharField(
        max_length=60,
        label="Betroffene Chargennummer (Lot)",
        widget=forms.TextInput(attrs={"placeholder": "z. B. LOT-98745A"}),
    )
    reason = forms.CharField(
        max_length=255,
        label="Rückrufgrund (BfArM-Meldung / Hersteller)",
        widget=forms.TextInput(attrs={"placeholder": "z. B. BfArM-Recall vom 22.10. wegen Partikelfunden"}),
    )
