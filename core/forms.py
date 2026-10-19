from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlparse

from django import forms
from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import BirthdayPreference, CalendarEvent, EmployeeActivation, HandoverEntry, Membership, PinboardNote, Station, StationTask


class DateTimeLocalInput(forms.DateTimeInput):
    input_type = "datetime-local"


class HandoverForm(forms.ModelForm):
    class Meta:
        model = HandoverEntry
        fields = ["category", "priority", "title", "details"]
        widgets = {"details": forms.Textarea(attrs={"rows": 6})}


class HandoverEditForm(forms.ModelForm):
    class Meta:
        model = HandoverEntry
        fields = ["category", "priority", "title", "details"]
        widgets = {"details": forms.Textarea(attrs={"rows": 6})}
        labels = {
            "category": "Kategorie",
            "priority": "Priorität",
            "title": "Titel",
            "details": "Details",
        }


class HandoverStatusForm(forms.ModelForm):
    class Meta:
        model = HandoverEntry
        fields = ["status"]


class TotpConfirmForm(forms.Form):
    token = forms.CharField(
        max_length=8,
        label=_("Einmalcode"),
        widget=forms.TextInput(attrs={
            "inputmode": "numeric",
            "autocomplete": "one-time-code",
            "pattern": "[0-9]*",
        }),
    )


class CalendarEventForm(forms.ModelForm):
    class Meta:
        model = CalendarEvent
        fields = ["title", "description", "starts_at", "ends_at"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "starts_at": DateTimeLocalInput(format="%Y-%m-%dT%H:%M"),
            "ends_at": DateTimeLocalInput(format="%Y-%m-%dT%H:%M"),
        }


class BirthdayForm(forms.ModelForm):
    consent = forms.BooleanField(
        required=False,
        label=_("Ich möchte meinen Geburtstag freiwillig im Team anzeigen."),
    )

    class Meta:
        model = BirthdayPreference
        fields = ["day", "month"]
        labels = {"day": "Tag", "month": "Monat"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["day"].widget.attrs.update({"min": 1, "max": 31})
        self.fields["month"].widget.attrs.update({"min": 1, "max": 12})
        self.fields["consent"].initial = self.instance.is_visible

    def clean(self):
        cleaned = super().clean()
        day = cleaned.get("day")
        month = cleaned.get("month")
        if cleaned.get("consent") and (not day or not month):
            raise forms.ValidationError(_("Bitte Tag und Monat angeben oder die Anzeige deaktivieren."))
        if day and month:
            try:
                date(2000, month, day)
            except ValueError as exc:
                raise forms.ValidationError(_("Tag und Monat ergeben kein gültiges Datum.")) from exc
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        was_visible = instance.is_visible
        instance.is_visible = self.cleaned_data["consent"]
        if instance.is_visible and not was_visible:
            instance.consented_at = timezone.now()
            instance.withdrawn_at = None
        if not instance.is_visible:
            if was_visible:
                instance.withdrawn_at = timezone.now()
            instance.day = None
            instance.month = None
            instance.consented_at = None
        if commit:
            instance.save()
        return instance


class CoffeeEntryForm(forms.Form):
    member = forms.ModelChoiceField(queryset=User.objects.none(), label=_("Teammitglied"))
    direction = forms.ChoiceField(
        choices=(("credit", "Einzahlung/Gutschrift"), ("debit", "Entnahme/Verbrauch")),
        label=_("Buchungsart"),
    )
    amount_eur = forms.DecimalField(
        min_value=Decimal("0.01"), max_digits=8, decimal_places=2, label=_("Betrag in EUR")
    )
    reason = forms.CharField(max_length=200, label=_("Grund"))

    def __init__(self, *args, station, **kwargs):
        super().__init__(*args, **kwargs)
        member_ids = Membership.objects.filter(station=station, is_active=True).values("user_id")
        self.fields["member"].queryset = User.objects.filter(id__in=member_ids).order_by(
            "first_name", "username"
        )

    def amount_cents(self):
        cents = int((self.cleaned_data["amount_eur"] * 100).quantize(Decimal("1"), ROUND_HALF_UP))
        return cents if self.cleaned_data["direction"] == "credit" else -cents


class CoffeeCorrectionForm(forms.Form):
    reason = forms.CharField(max_length=200, label=_("Korrekturgrund"))


class MembershipAssignmentForm(forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.none(), label=_("Benutzerkonto"))
    role = forms.ChoiceField(choices=Membership.Role.choices, label=_("Rolle"))

    def __init__(self, *args, station=None, **kwargs):
        super().__init__(*args, **kwargs)
        if station is None:
            self.fields["user"].queryset = User.objects.none()
            return
        from .access import users_awaiting_station_access

        self.fields["user"].queryset = users_awaiting_station_access(station)


class MasterAdminCreateUserForm(forms.Form):
    username = forms.CharField(max_length=150, label=_("Benutzername (z. B. E-Mail)"))
    first_name = forms.CharField(max_length=150, label=_("Vorname"), required=False)
    last_name = forms.CharField(max_length=150, label=_("Nachname"), required=False)
    password1 = forms.CharField(
        label=_("Startpasswort"),
        widget=forms.PasswordInput,
        help_text=_("Der Nutzer sollte das Passwort danach unter Mein Konto ändern."),
    )
    password2 = forms.CharField(label=_("Startpasswort wiederholen"), widget=forms.PasswordInput)
    role = forms.ChoiceField(choices=Membership.Role.choices, label=_("Rolle"), initial=Membership.Role.MEMBER)

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError(_("Dieser Benutzername ist bereits vergeben."))
        return username

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError(_("Die Passwörter stimmen nicht überein."))
        if password1:
            from django.contrib.auth.password_validation import validate_password

            validate_password(password1)
        return cleaned


class MembershipEditForm(forms.Form):
    role = forms.ChoiceField(choices=Membership.Role.choices, label=_("Rolle"))
    is_active = forms.BooleanField(required=False, label=_("Zugang aktiv"))

    def __init__(self, *args, membership, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].initial = membership.role
        self.fields["is_active"].initial = membership.is_active


class StationSettingsForm(forms.ModelForm):
    class Meta:
        model = Station
        fields = [
            "name",
            "organization_profile",
            "calendar_enabled",
            "birthdays_enabled",
            "coffee_enabled",
            "feeds_enabled",
            "tasks_enabled",
            "chat_enabled",
            "pinboard_enabled",
            "holidays_enabled",
            "checklists_enabled",
            "waste_calendar_enabled",
            "waste_calendar_url",
            "paypal_me_url",
            "wero_link",
            "iban",
            "bic",
            "payment_note",
        ]
        labels = {
            "name": "Name der Organisationseinheit",
            "organization_profile": "Profil dieser Einrichtung",
            "paypal_me_url": "PayPal.me-Link",
            "wero_link": "Wero-Link",
            "iban": "IBAN",
            "bic": "BIC",
            "payment_note": "Zahlungshinweis",
        }
        help_texts = {
            "paypal_me_url": "Vollständige https://paypal.me/…-URL.",
            "wero_link": "Vollständige https://…-URL zum Wero-Profil.",
            "iban": "Deutsche IBAN (DE + 20 Ziffern), nur für die Anzeige.",
            "bic": "Optional, 8 oder 11 Zeichen.",
            "payment_note": "Freitext, z. B. Verwendungszweck oder Ansprechpartner.",
            "waste_calendar_url": "Vollständige https://…-URL zu einer ICS-Datei. Der Host muss in FEED_ALLOWED_HOSTS stehen.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["organization_profile"].required = False
        self.fields["organization_profile"].widget.attrs["required"] = "required"

    def clean_organization_profile(self):
        return self.cleaned_data.get("organization_profile") or self.instance.organization_profile

    def clean_waste_calendar_url(self):
        value = (self.cleaned_data.get("waste_calendar_url") or "").strip()
        if not value:
            return value
        if not value.startswith("https://"):
            raise forms.ValidationError(_("Müllkalender-URLs müssen mit https:// beginnen."))
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        if not host:
            raise forms.ValidationError(_("Müllkalender-URLs brauchen einen Hostnamen."))
        if parsed.username or parsed.password:
            raise forms.ValidationError(_("Müllkalender-URLs dürfen keine Zugangsdaten enthalten."))
        try:
            port = parsed.port
        except ValueError:
            raise forms.ValidationError(_("Die Portangabe der Müllkalender-URL ist ungültig."))
        if port not in {None, 443}:
            raise forms.ValidationError(_("Müllkalender-URLs dürfen nur HTTPS-Port 443 verwenden."))
        if host not in settings.FEED_ALLOWED_HOSTS:
            raise forms.ValidationError(
                "Der Host muss zuerst in FEED_ALLOWED_HOSTS freigegeben werden."
            )
        return value

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("waste_calendar_enabled") and not cleaned.get("waste_calendar_url"):
            self.add_error(
                "waste_calendar_url",
                "Für den Müllkalender-Fallback wird eine HTTPS-ICS-URL benötigt.",
            )
        return cleaned

    def clean_paypal_me_url(self):
        value = (self.cleaned_data.get("paypal_me_url") or "").strip()
        if value and not value.startswith("https://"):
            raise forms.ValidationError(_("PayPal.me-Links müssen mit https:// beginnen."))
        return value

    def clean_wero_link(self):
        value = (self.cleaned_data.get("wero_link") or "").strip()
        if value and not value.startswith("https://"):
            raise forms.ValidationError(_("Wero-Links müssen mit https:// beginnen."))
        return value

    def clean_iban(self):
        value = (self.cleaned_data.get("iban") or "").replace(" ", "").upper()
        if value and not (value.startswith("DE") and len(value) == 22 and value[2:].isdigit()):
            raise forms.ValidationError(_("Bitte eine gültige deutsche IBAN (DE + 20 Ziffern) angeben."))
        return value

    def clean_bic(self):
        value = (self.cleaned_data.get("bic") or "").replace(" ", "").upper()
        if value and (not value.isalnum() or len(value) not in (8, 11)):
            raise forms.ValidationError(_("BIC muss 8 oder 11 alphanumerische Zeichen haben."))
        return value


class RegistrationForm(forms.Form):
    username = forms.CharField(max_length=150, label=_("Benutzername (z. B. E-Mail)"))
    first_name = forms.CharField(max_length=150, label=_("Vorname"), required=False)
    preferred_station = forms.ModelChoiceField(
        queryset=Station.objects.none(),
        required=True,
        label=_("Gewünschte Wache"),
        empty_label=_("Bitte Wache wählen"),
        error_messages={"required": _("Bitte eine Wache auswählen.")},
    )
    note = forms.CharField(
        max_length=300,
        required=False,
        label=_("Hinweis an die Verwaltung"),
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    password1 = forms.CharField(label=_("Passwort"), widget=forms.PasswordInput)
    password2 = forms.CharField(label=_("Passwort wiederholen"), widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["preferred_station"].queryset = Station.objects.filter(
            is_active=True
        ).order_by("name")

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError(_("Dieser Benutzername ist bereits vergeben."))
        return username

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError(_("Die Passwörter stimmen nicht überein."))
        if password1:
            from django.contrib.auth.password_validation import validate_password

            validate_password(password1)
        return cleaned


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
        labels = {
            "first_name": "Vorname",
            "last_name": "Nachname",
            "email": "E-Mail",
        }


class AvatarForm(forms.Form):
    avatar = forms.ImageField(
        required=False,
        label=_("Profilbild"),
        help_text=_("JPEG, PNG oder WebP, max. 2 MB. Wird auf 192×192 verkleinert."),
    )
    clear_avatar = forms.BooleanField(required=False, label=_("Profilbild entfernen"))

    def clean(self):
        cleaned = super().clean()
        avatar = cleaned.get("avatar")
        clear = cleaned.get("clear_avatar")
        if not avatar and not clear:
            raise forms.ValidationError(_("Bitte ein Bild wählen oder Entfernen markieren."))
        if avatar and clear:
            raise forms.ValidationError(_("Bild hochladen und entfernen geht nicht gleichzeitig."))
        if avatar:
            from .avatars import process_avatar_upload

            try:
                data, content_type = process_avatar_upload(avatar)
            except ValidationError as exc:
                raise forms.ValidationError(exc.messages) from exc
            cleaned["avatar_bytes"] = data
            cleaned["avatar_content_type"] = content_type
        return cleaned


class ChatMessageForm(forms.Form):
    body = forms.CharField(
        max_length=500,
        label=_("Kurze Nachricht"),
        widget=forms.Textarea(attrs={
            "rows": 2,
            "maxlength": 500,
            "placeholder": "Kurze Nachricht an die Kollegen …",
        }),
    )


class PinboardNoteForm(forms.ModelForm):
    class Meta:
        model = PinboardNote
        fields = ["title", "body", "category"]
        labels = {
            "title": "Titel",
            "body": "Text",
            "category": "Art",
        }
        widgets = {
            "body": forms.Textarea(attrs={
                "rows": 5,
                "maxlength": 2000,
                "placeholder": "Kurzer Aushang für die Wache …",
            }),
        }


class StationTaskForm(forms.ModelForm):
    class Meta:
        model = StationTask
        fields = ["title", "band", "weekday", "notes", "sort_order", "is_active"]
        labels = {
            "title": "Aufgabe",
            "band": "Farbe / Bereich",
            "weekday": "Wochentag",
            "notes": "Hinweis",
            "sort_order": "Reihenfolge",
            "is_active": "Aktiv",
        }
        help_texts = {
            "band": "Grün = täglich, Gelb = Wochentag, Blau = zusätzlich.",
            "weekday": "Nur bei gelben Wochentagsaufgaben setzen.",
        }

    def clean(self):
        cleaned = super().clean()
        band = cleaned.get("band")
        weekday = cleaned.get("weekday")
        if band == StationTask.Band.WEEKDAY and weekday is None:
            self.add_error("weekday", "Bitte einen Wochentag wählen.")
        if band != StationTask.Band.WEEKDAY:
            cleaned["weekday"] = None
        return cleaned


def _translated_profile_choices():
    """Organisationsprofil-Auswahl mit uebersetzten Labels (Modell bleibt unveraendert)."""
    labels = {
        Station.Profile.RESCUE: _("Rettungsdienst"),
        Station.Profile.FIRE: _("Feuerwehr"),
        Station.Profile.POLICE: _("Polizei"),
        Station.Profile.GENERAL: _("Allgemein"),
    }
    return [(value, labels[value]) for value in Station.Profile.values]


class SetupWizardForm(forms.Form):
    """First-installation data. The bootstrap token is only used on step 1."""

    bootstrap_token = forms.CharField(
        required=False,
        label=_("Bootstrap-Token"),
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "off"}),
        help_text=_("Wird vom Betreiber außerhalb der Anwendung gesetzt (SETUP_BOOTSTRAP_TOKEN)."),
    )
    station_name = forms.CharField(label=_("Name der Wache"), max_length=120)
    organization_profile = forms.ChoiceField(
        label=_("Organisationsprofil"), choices=_translated_profile_choices(), initial=Station.Profile.RESCUE
    )
    employee_count = forms.IntegerField(label=_("Mitarbeiterzahl"), min_value=1, max_value=9999, required=False)
    street = forms.CharField(label=_("Straße und Hausnummer"), max_length=120, required=False)
    postal_code = forms.CharField(label=_("Postleitzahl"), max_length=10, required=False)
    city = forms.CharField(label=_("Ort"), max_length=80, required=False)
    timezone_name = forms.ChoiceField(
        label=_("Zeitzone"),
        choices=[("Europe/Berlin", "Europe/Berlin"), ("Europe/Vienna", "Europe/Vienna"), ("Europe/Zurich", "Europe/Zurich")],
        initial="Europe/Berlin",
    )
    weather_enabled = forms.BooleanField(label=_("5-Tage-Wetter am Wachenstandort anzeigen"), required=False)
    admin_username = forms.CharField(label=_("Benutzername des Master-Admins"), max_length=150)
    admin_first_name = forms.CharField(label=_("Vorname"), max_length=150, required=False)
    admin_last_name = forms.CharField(label=_("Nachname"), max_length=150, required=False)
    admin_email = forms.EmailField(label=_("E-Mail (optional)"), required=False)
    password1 = forms.CharField(label=_("Passwort"), widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    password2 = forms.CharField(label=_("Passwort wiederholen"), widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    def __init__(self, *args, preview_only: bool = False, **kwargs):
        # The optional weather check is submitted from the station section
        # before the master-admin block is filled in. In that partial POST the
        # admin/password fields are legitimately empty and must not be reported
        # as missing required fields.
        self.preview_only = preview_only
        super().__init__(*args, **kwargs)
        if preview_only:
            for name in ("admin_username", "password1", "password2"):
                self.fields[name].required = False

    def clean_admin_username(self):
        username = (self.cleaned_data.get("admin_username") or "").strip()
        if getattr(self, "preview_only", False):
            return username
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError(_("Dieser Benutzername ist bereits vergeben."))
        return username

    def clean_station_name(self):
        name = (self.cleaned_data.get("station_name") or "").strip()
        if len(name) < 2:
            raise ValidationError(_("Bitte einen aussagekräftigen Wachennamen angeben."))
        return name

    def clean(self):
        cleaned = super().clean()
        if getattr(self, "preview_only", False):
            # Partial weather POST: only the station section is validated.
            if cleaned.get("postal_code") and not (cleaned["postal_code"].isdigit() and len(cleaned["postal_code"]) in (4, 5)):
                self.add_error("postal_code", _("Bitte eine vier- oder fünfstellige Postleitzahl angeben."))
            return cleaned
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", _("Die Passwörter stimmen nicht überein."))
        if password1:
            from django.contrib.auth.password_validation import validate_password

            candidate_user = User(
                username=cleaned.get("admin_username", ""),
                first_name=cleaned.get("admin_first_name", ""),
                last_name=cleaned.get("admin_last_name", ""),
                email=cleaned.get("admin_email", ""),
            )
            try:
                validate_password(password1, user=candidate_user)
            except ValidationError as exc:
                self.add_error("password1", exc)
        if cleaned.get("postal_code") and not (cleaned["postal_code"].isdigit() and len(cleaned["postal_code"]) in (4, 5)):
            self.add_error("postal_code", _("Bitte eine vier- oder fünfstellige Postleitzahl angeben."))
        return cleaned


class ActivationPasswordForm(forms.Form):
    password1 = forms.CharField(
        label=_("Neues Passwort"), widget=forms.PasswordInput(attrs={"autocomplete": "new-password"})
    )
    password2 = forms.CharField(
        label=_("Passwort wiederholen"), widget=forms.PasswordInput(attrs={"autocomplete": "new-password"})
    )

    def __init__(self, *args, user=None, **kwargs):
        # The similarity validator can only work with the real account.
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", _("Die Passwörter stimmen nicht überein."))
        if password1:
            from django.contrib.auth.password_validation import validate_password

            try:
                validate_password(password1, user=self.user)
            except ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned


class EmployeeInviteForm(forms.Form):
    username = forms.CharField(label=_("Benutzername"), max_length=150)
    first_name = forms.CharField(label=_("Vorname"), max_length=150, required=False)
    last_name = forms.CharField(label=_("Nachname"), max_length=150, required=False)
    role = forms.ChoiceField(
        label=_("Rolle"),
        choices=[
            (Membership.Role.MEMBER, Membership.Role.MEMBER.label),
            (Membership.Role.SHIFT_LEAD, Membership.Role.SHIFT_LEAD.label),
            (Membership.Role.CASHIER, Membership.Role.CASHIER.label),
        ],
        initial=Membership.Role.MEMBER,
    )

    def __init__(self, *args, station=None, **kwargs):
        self.station = station
        super().__init__(*args, **kwargs)

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        existing = User.objects.filter(username__iexact=username).first()
        if existing is None:
            return username
        from .setup_wizard import reusable_pending_invite

        if not reusable_pending_invite(existing, station=self.station):
            raise ValidationError(_("Dieser Benutzername ist bereits vergeben."))
        if EmployeeActivation.objects.filter(
            user=existing,
            used_at__isnull=True,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).exists():
            raise ValidationError(
                "Für dieses Konto ist bereits ein offener Aktivierungslink vorhanden. "
                "Bitte zuerst widerrufen."
            )
        return username
