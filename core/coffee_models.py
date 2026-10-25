"""Kaffeekasse: Monatsbeitrag, Teilnehmende und die Kasse selbst.

Vorbild ist die Kasse vieler Wachen: eine Metalldose für Bargeld und eine
Mappe, in der pro Monat „bezahlt“ abgehakt wird. Die Mappe ist das persönliche
Konto (``CoffeeEntry``), die Dose und ein optionales Konto sind die Töpfe
(``CoffeeCashMovement`` plus Einzahlungen). Einsicht in fremde Stände hat nur
der Kassenwart; alle sehen, wohin das Geld der Kasse geht.
"""
from __future__ import annotations

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .models import Station


class CoffeeFund(models.Model):
    """Einstellungen der Kaffeekasse einer Wache."""

    station = models.OneToOneField(Station, on_delete=models.CASCADE, primary_key=True, related_name="coffee_fund")
    monthly_fee_cents = models.PositiveIntegerField(
        _("Monatsbeitrag in Cent"), default=0,
        help_text=_("0 = kein Monatsbeitrag, die Kasse führt dann nur Einzahlungen und Buchungen."),
    )
    reminder_day = models.PositiveSmallIntegerField(
        _("Erinnerung ab Tag"), default=10,
        help_text=_("Ab diesem Tag des Monats erinnert Wachwerk an einen offenen Beitrag. 0 = keine Erinnerung."),
    )
    account_holder = models.CharField(
        _("Kontoinhaber für Überweisungen"), max_length=70, blank=True, default="",
        help_text=_("Name für den Überweisungs-QR (GiroCode). Am besten ein eigenes Konto der Kasse."),
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        verbose_name = _("Kaffeekasse")
        verbose_name_plural = _("Kaffeekassen")

    def __str__(self) -> str:
        return str(self.station)

    @property
    def monthly_fee_euros(self) -> float:
        return self.monthly_fee_cents / 100


class CoffeeParticipant(models.Model):
    """Wer zahlt den Monatsbeitrag – und ab bzw. bis zu welchem Monat."""

    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="coffee_participants")
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="coffee_participations")
    since = models.DateField(_("Beitrag ab Monat"))
    until = models.DateField(_("Beitrag bis Monat"), null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["station", "user"], name="unique_coffee_participant"),
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.station}"

    def pays_in(self, month) -> bool:
        return self.since <= month and (self.until is None or month <= self.until)


class CoffeeCashMovement(models.Model):
    """Geld, das nicht von einer Person eingezahlt wird: Einkäufe, Kassensturz, Bank.

    Nur anhängen wie das Kassenbuch; Fehler werden durch eine Gegenbuchung
    korrigiert. ``amount_cents`` verändert den Topf ``pot``; eine Einzahlung
    der Dose aufs Konto (``deposit``) bucht die Dose ab und das Konto zu.
    """

    class Pot(models.TextChoices):
        CASH = "cash", _("Kasse (Bargeld)")
        BANK = "bank", _("Konto")

    class Kind(models.TextChoices):
        PURCHASE = "purchase", _("Einkauf")
        DEPOSIT = "deposit", _("Bargeld aufs Konto eingezahlt")
        COUNT = "count", _("Kassensturz")
        OTHER = "other", _("Sonstige Ein- oder Auszahlung")

    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="coffee_movements")
    pot = models.CharField(max_length=4, choices=Pot.choices, default=Pot.CASH)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    amount_cents = models.IntegerField()
    reason = models.CharField(max_length=200)
    # Kassensturz: gezählter und erwarteter Bestand (Differenz = amount_cents).
    counted_cents = models.IntegerField(null=True, blank=True)
    expected_cents = models.IntegerField(null=True, blank=True)
    witness = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="recorded_coffee_movements")
    correction_of = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="corrections"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # Ein Kassensturz ohne Differenz wird trotzdem festgehalten.
            models.CheckConstraint(condition=~Q(amount_cents=0) | Q(kind="count"), name="coffee_movement_nonzero"),
            models.UniqueConstraint(
                fields=["correction_of"],
                condition=Q(correction_of__isnull=False),
                name="unique_coffee_movement_correction",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.amount_cents / 100:.2f} €"

    @property
    def amount_euros(self) -> float:
        return self.amount_cents / 100

    @property
    def counted_euros(self) -> float:
        return (self.counted_cents or 0) / 100

    @property
    def expected_euros(self) -> float:
        return (self.expected_cents or 0) / 100

    def clean(self):
        if self.kind == self.Kind.DEPOSIT and (self.pot != self.Pot.CASH or self.amount_cents >= 0):
            raise ValidationError("Eine Einzahlung aufs Konto bucht Bargeld aus der Kasse ab.")
        if self.kind == self.Kind.COUNT and self.pot != self.Pot.CASH:
            raise ValidationError("Gezählt wird das Bargeld in der Kasse.")
        if self.correction_of:
            original = self.correction_of
            if original.station_id != self.station_id or original.correction_of_id:
                raise ValidationError("Diese Bewegung kann so nicht korrigiert werden.")
            if (self.pot, self.kind, self.amount_cents) != (original.pot, original.kind, -original.amount_cents):
                raise ValidationError("Eine Korrektur muss den exakten Gegenbetrag im selben Topf buchen.")

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Kassenbewegungen dürfen nicht verändert werden.")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Kassenbewegungen dürfen nicht gelöscht werden.")
