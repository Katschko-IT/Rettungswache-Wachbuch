"""Wachenterminal: ein fest registrierter Touch-Bildschirm auf der Wache.

Der Bildschirm zeigt gesperrt das Wachen-Display. Mit dem gemeinsamen
vierstelligen Wachen-Code öffnet er den Alltagsmodus. Der Code gilt nur auf
registrierten Terminals (Gerätegeheimnis als HttpOnly-Cookie). Einträge im
Alltagsmodus stehen unter dem Dienstkonto „Wachenterminal“ der Wache.
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
    # Fehlversuche mit dem Wachen-Code an diesem Gerät (aufeinanderfolgend).
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["station", "label"]

    def __str__(self) -> str:
        return f"{self.label} ({self.station})"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None and self.station.is_active


class StationTerminalCode(models.Model):
    """Gemeinsamer vierstelliger Code einer Wache und ihr Terminal-Dienstkonto."""

    station = models.OneToOneField(Station, on_delete=models.CASCADE, related_name="terminal_code")
    code_hash = models.CharField(max_length=128)
    service_user = models.OneToOneField(User, on_delete=models.PROTECT, related_name="terminal_station_code")
    set_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="set_terminal_codes"
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Wachen-Code {self.station}"


class TerminalPairing(models.Model):
    """Einmalcode, mit dem ein Handy ein persönliches App-Token erhält."""

    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="terminal_pairings")
    code_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["expires_at"], name="terminal_pairing_exp_idx")]
