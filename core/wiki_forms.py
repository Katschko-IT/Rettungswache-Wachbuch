from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from core.wiki_services import clean_body, clean_title


class WikiArticleForm(forms.Form):
    """Formular zum Erstellen und Bearbeiten von Wiki-Artikeln."""

    title = forms.CharField(
        max_length=160,
        label=_("Titel"),
        help_text=_("Aussagekräftiger Titel des Eintrags (max. 160 Zeichen)."),
    )
    body = forms.CharField(
        max_length=8000,
        widget=forms.Textarea(attrs={"rows": 14}),
        label=_("Text"),
        help_text=_("Inhalt des Eintrags (reiner Text, max. 8000 Zeichen)."),
    )
    expected_revision = forms.IntegerField(
        widget=forms.HiddenInput,
        required=False,
        min_value=1,
    )

    def clean_title(self) -> str:
        title = self.cleaned_data.get("title", "")
        return clean_title(title)

    def clean_body(self) -> str:
        body = self.cleaned_data.get("body", "")
        return clean_body(body)

    def clean(self) -> dict:
        cleaned_data = super().clean()
        expected = cleaned_data.get("expected_revision")
        if expected is not None and expected < 1:
            raise ValidationError(
                {"expected_revision": _("Die Revisionsnummer muss mindestens 1 sein.")}
            )
        return cleaned_data
