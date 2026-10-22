"""Wachenterminal: ein fest registrierter Touch-Bildschirm auf der Wache.

Auf dem Terminal meldet sich jede Person mit ihrem eigenen Konto und einer
persönlichen PIN an. Die PIN gilt nur zusammen mit einem registrierten Terminal
(Gerätegeheimnis als HttpOnly-Cookie) und nie im Internet oder in der App.
"""
from __future__ import annotations

from django.contrib.auth.models import User
from django.db import models

from .models import Membership, Station


class StationTerminal(models.Model):
    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="terminals")
    label = models.CharField(max_length=80, default="Wachenterminal")
    token_hash = models.CharField(max_length=64, unique=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="created_terminals")
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["station", "label"]

    def __str__(self) -> str:
        return f"{self.label} ({self.station})"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None and self.station.is_active


class TerminalPin(models.Model):
    membership = models.OneToOneField(Membership, on_delete=models.CASCADE, related_name="terminal_pin")
    pin_hash = models.CharField(max_length=128)
    # Von Wachleitung vergebene PIN: beim ersten Anmelden selbst ändern.
    must_change = models.BooleanField(default=True)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    set_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="set_terminal_pins"
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Terminal-PIN für {self.membership}"


class TerminalPairing(models.Model):
    """Einmalcode, mit dem ein Handy am Terminal ein App-Token erhält."""

    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="terminal_pairings")
    code_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["expires_at"], name="terminal_pairing_exp_idx")]
