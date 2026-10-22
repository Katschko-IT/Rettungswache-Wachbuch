"""Zugangstoken für den Wachen-Display-Modus (Wandmonitor / Fernseher).

Ein Display-Link erlaubt ausschließlich eine lesende, aggregierte Übersicht.
Er authentifiziert keinen Benutzer und öffnet keine anderen Bereiche.

Sicherheitsmuster wie bei Einladungen und QR-Anmeldung im Projekt: Das
Klartext-Token wird nur einmal bei der Erstellung angezeigt, in der Datenbank
liegt ausschließlich der SHA-256-Hash.
"""
from __future__ import annotations

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from .models import Station

DEFAULT_DISPLAY_CONFIG = {
    "version": 1,
    "theme": "dark",
    "background_rotation_minutes": 5,
    "modules": [
        {
            "id": "clock",
            "module": "clock",
            "position": "top_left",
            "enabled": True,
            "header": "",
            "config": {"show_date": True, "show_station": True},
        },
        {
            "id": "weather",
            "module": "weather",
            "position": "top_right",
            "enabled": True,
            "header": "",
            "config": {},
        },
        {
            "id": "events",
            "module": "events",
            "position": "middle_left",
            "enabled": True,
            "header": "Heute",
            "config": {"limit": 6},
        },
        {
            "id": "waste",
            "module": "waste",
            "position": "middle_left",
            "enabled": True,
            "header": "",
            "config": {"limit": 3},
        },
        {
            "id": "tasks",
            "module": "tasks",
            "position": "middle_center",
            "enabled": True,
            "header": "Tagesaufgaben",
            "config": {"show_progress": True},
        },
        {
            "id": "traffic",
            "module": "traffic",
            "position": "middle_right",
            "enabled": True,
            "header": "Verkehrslage",
            "config": {},
        },
        {
            "id": "birthdays",
            "module": "birthdays",
            "position": "middle_right",
            "enabled": True,
            "header": "Geburtstage",
            "config": {},
        },
        {
            "id": "urgent_handovers",
            "module": "urgent_handovers",
            "position": "bottom_bar",
            "enabled": True,
            "header": "",
            "config": {},
        },
    ],
}


def default_layout_config() -> dict:
    return dict(DEFAULT_DISPLAY_CONFIG)


class DisplayToken(models.Model):
    """Widerrufbarer Lesezugang für genau einen Bildschirm einer Wache."""

    station = models.ForeignKey(
        Station, on_delete=models.CASCADE, related_name="display_tokens"
    )
    label = models.CharField(max_length=80, verbose_name="Bezeichnung")
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    layout_config = models.JSONField(
        default=default_layout_config,
        blank=True,
        verbose_name="Bildschirm-Konfiguration",
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Display-Zugang"
        verbose_name_plural = "Display-Zugänge"

    def __str__(self) -> str:
        return f"{self.label} ({self.station_id})"

    @property
    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None and self.expires_at <= timezone.now():
            return False
        return True
