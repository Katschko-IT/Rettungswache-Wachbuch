"""Betreiberangaben dieser Installation: Impressum, Datenschutz-Information, 2FA-Pflicht.

Eine Installation ist genau eine Wache; ihr Betreiber (Träger, Verein oder
Person) steht im Impressum (§ 5 DDG) und ist Verantwortlicher im Sinne von
Art. 13 DSGVO. Die Angaben werden im Einrichtungsassistenten erfasst und von
Admins unter Einstellungen → Impressum & Datenschutz gepflegt.
"""
from __future__ import annotations

from django.conf import settings
from django.db import OperationalError, ProgrammingError, models
from django.utils.translation import gettext_lazy as _


class SiteProfile(models.Model):
    class ServerLocation(models.TextChoices):
        STATION = "station", _("Eigener Server in der Wache")
        GERMANY = "germany", _("Rechenzentrum in Deutschland")
        EU = "eu", _("Rechenzentrum in der EU")
        OTHER = "other", _("Anderer Standort (siehe Hosting-Angabe)")

    singleton = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)

    # Impressum (Anbieterkennzeichnung)
    operator_name = models.CharField(_("Anbieter (Name oder Organisation)"), max_length=200)
    legal_form = models.CharField(_("Rechtsform"), max_length=120, blank=True, default="")
    represented_by = models.CharField(
        _("Vertreten durch"), max_length=200, blank=True, default="",
        help_text=_("Vertretungsberechtigte Person(en), z. B. Vorstand oder Geschäftsführung."),
    )
    street = models.CharField(_("Straße und Hausnummer"), max_length=120, blank=True, default="")
    postal_code = models.CharField(_("Postleitzahl"), max_length=10, blank=True, default="")
    city = models.CharField(_("Ort"), max_length=80, blank=True, default="")
    country = models.CharField(_("Land"), max_length=80, blank=True, default="Deutschland")
    email = models.EmailField(_("E-Mail"), blank=True, default="")
    phone = models.CharField(_("Telefon"), max_length=60, blank=True, default="")
    register_entry = models.CharField(
        _("Registereintrag"), max_length=200, blank=True, default="",
        help_text=_("z. B. Amtsgericht Musterstadt, VR 1234 – leer lassen, wenn nicht vorhanden."),
    )
    vat_id = models.CharField(_("Umsatzsteuer-ID"), max_length=40, blank=True, default="")
    content_responsible = models.CharField(
        _("Inhaltlich verantwortlich"), max_length=300, blank=True, default="",
        help_text=_("Nur nötig bei redaktionellen Inhalten (§ 18 Abs. 2 MStV)."),
    )
    impressum_extra = models.TextField(_("Weitere Angaben im Impressum"), blank=True, default="")
    public_site = models.BooleanField(
        _("Öffentlich im Internet erreichbar"), default=False,
        help_text=_("Dann sind Impressum und vollständige Kontaktangaben Pflicht."),
    )

    # Datenschutz-Information (Art. 13 DSGVO)
    privacy_email = models.EmailField(
        _("Kontakt für Datenschutzfragen"), blank=True, default="",
        help_text=_("Leer = E-Mail des Anbieters."),
    )
    hosting_provider = models.CharField(
        _("Hosting-Anbieter"), max_length=300, blank=True, default="",
        help_text=_("Name und Sitz des Rechenzentrums (Auftragsverarbeiter), leer bei eigenem Server."),
    )
    server_location = models.CharField(
        _("Serverstandort"), max_length=20, choices=ServerLocation.choices, default=ServerLocation.STATION,
    )
    supervisory_authority = models.CharField(
        _("Zuständige Datenschutz-Aufsichtsbehörde"), max_length=300, blank=True, default="",
        help_text=_("z. B. Die Landesbeauftragte für den Datenschutz Niedersachsen."),
    )

    # Sicherheit
    mfa_required = models.BooleanField(
        _("Zwei-Faktor-Anmeldung für alle Konten"), default=False,
        help_text=_("Jede Person richtet bei der nächsten Anmeldung eine Authenticator-App ein "
                    "(z. B. Google Authenticator, Microsoft Authenticator, Aegis, 2FAS)."),
    )

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )

    class Meta:
        verbose_name = _("Betreiberangaben")
        verbose_name_plural = _("Betreiberangaben")

    def __str__(self) -> str:
        return self.operator_name

    @classmethod
    def current(cls) -> SiteProfile | None:
        return cls.objects.filter(pk=1).first()

    @property
    def is_configured(self) -> bool:
        return bool(self.operator_name and self.city)

    @property
    def address_lines(self) -> list[str]:
        city = " ".join(part for part in (self.postal_code, self.city) if part)
        lines = [self.street, city]
        if self.country and self.country.casefold() != "deutschland":
            lines.append(self.country)
        return [line for line in lines if line]

    @property
    def privacy_contact(self) -> str:
        return self.privacy_email or self.email


def site_mfa_required() -> bool:
    """2FA-Pflicht aus den Betreiberangaben (zusätzlich zu MFA_REQUIRED in der Umgebung)."""
    try:
        return SiteProfile.objects.filter(pk=1, mfa_required=True).exists()
    except (OperationalError, ProgrammingError):  # Tabelle fehlt noch (vor der Migration)
        return False
