"""Formulare für Organisation, SOPs & Dienstanweisungen und Stations-Telefonbuch."""
from __future__ import annotations

from django import forms
from django.utils.text import slugify

from .orga_models import SOPDocument, SOPRevision, StationContact


class SOPDocumentForm(forms.ModelForm):
    initial_content = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 10, "placeholder": "# Indikation / Anwendungsbereich\n\n## 1. Handlungsalgorithmus\n\n## 2. Medikamentendosierung\n\n## 3. Dokumentation & Übergabe"}),
        label="Inhalt / Volltext der Dienstanweisung (Markdown)",
        required=False,
    )
    initial_version = forms.CharField(
        max_length=20,
        initial="1.0",
        label="Start-Versionsnummer",
        required=False,
    )

    class Meta:
        model = SOPDocument
        fields = [
            "doc_number",
            "title",
            "category",
            "status",
            "valid_from",
            "review_due_date",
            "requires_acknowledgment",
        ]
        widgets = {
            "valid_from": forms.DateInput(attrs={"type": "date"}),
            "review_due_date": forms.DateInput(attrs={"type": "date"}),
            "doc_number": forms.TextInput(attrs={"placeholder": "z. B. SOP-MED-01"}),
            "title": forms.TextInput(attrs={"placeholder": "z. B. Invasive Notfallnarkose & RSI"}),
        }

    def __init__(self, *args, station=None, **kwargs):
        self.station = station
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["initial_content"].widget = forms.HiddenInput()
            self.fields["initial_version"].widget = forms.HiddenInput()

    def clean(self):
        cleaned_data = super().clean()
        doc_number = cleaned_data.get("doc_number")
        title = cleaned_data.get("title")
        if doc_number and title and not self.instance.pk:
            base_slug = slugify(f"{doc_number}-{title}")[:70] or "sop"
            slug = base_slug
            counter = 1
            station = self.station or (self.instance.station if hasattr(self.instance, "station") else None)
            if station:
                while SOPDocument.objects.filter(station=station, slug=slug).exists():
                    slug = f"{base_slug}-{counter}"
                    counter += 1
            self.instance.slug = slug
        return cleaned_data


class SOPRevisionForm(forms.ModelForm):
    class Meta:
        model = SOPRevision
        fields = [
            "version_label",
            "content_markdown",
            "change_summary",
            "effective_date",
        ]
        widgets = {
            "effective_date": forms.DateInput(attrs={"type": "date"}),
            "version_label": forms.TextInput(attrs={"placeholder": "z. B. 1.1 oder 2.0"}),
            "change_summary": forms.TextInput(attrs={"placeholder": "z. B. Dosisanpassung Rocuronium gem. S3-Leitlinie"}),
            "content_markdown": forms.Textarea(attrs={"rows": 12}),
        }


class StationContactForm(forms.ModelForm):
    class Meta:
        model = StationContact
        fields = [
            "category",
            "name",
            "contact_person",
            "phone_primary",
            "phone_secondary",
            "notes",
            "is_speed_dial",
            "order_rank",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "z. B. Leitstelle München ILS"}),
            "contact_person": forms.TextInput(attrs={"placeholder": "z. B. Dienstgruppenleiter Dispo"}),
            "phone_primary": forms.TextInput(attrs={"placeholder": "z. B. 089 19222"}),
            "phone_secondary": forms.TextInput(attrs={"placeholder": "z. B. 089 19222-10 (Direktdurchwahl)"}),
            "notes": forms.TextInput(attrs={"placeholder": "z. B. 24/7 besetzt, Voranmeldung Schockraum"}),
        }
