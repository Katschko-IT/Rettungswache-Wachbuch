"""Persönliche Benachrichtigungen und registrierte Mobilgeräte.

``UserNotification`` ist der Posteingang einer Person: Web-Oberfläche und App
lesen ihn, Web-Push und (künftig) nativer Push sind nur zusätzliche Kanäle.
Dadurch geht keine Nachricht verloren, wenn ein Gerät gerade nicht erreichbar
ist. Inhalte bleiben organisatorisch – keine Patienten- oder Einsatzdaten.

``MobilePushDevice`` speichert Push-Tokens der iOS-/Android-App. Versendet wird
darüber erst, wenn ein Push-Relay konfiguriert ist (``PUSH_RELAY_URL``).
"""
from __future__ import annotations

from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .models import Station


class UserNotification(models.Model):
    class Kind(models.TextChoices):
        VEHICLE_READY = "vehicle_ready", "Fahrzeug kann freigegeben werden"
        COFFEE_DUE = "coffee_due", "Kaffeekasse: Beitrag offen"

    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="user_notifications")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=32, choices=Kind.choices)
    title = models.CharField(max_length=120)
    body = models.CharField(max_length=300, blank=True, default="")
    url = models.CharField(max_length=200, blank=True, default="")
    # Ein Ereignis erzeugt pro Person höchstens eine Nachricht, auch wenn
    # mehrere Prozesse gleichzeitig prüfen.
    dedupe_key = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "dedupe_key"], name="unique_user_notification_key"),
        ]
        indexes = [
            models.Index(fields=["user", "read_at"], name="notification_user_read_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.title} → {self.user}"


class MobilePushDevice(models.Model):
    class Platform(models.TextChoices):
        IOS = "ios", "iOS (APNs)"
        ANDROID = "android", "Android (FCM)"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="mobile_push_devices")
    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="mobile_push_devices")
    platform = models.CharField(max_length=16, choices=Platform.choices)
    token = models.CharField(max_length=512)
    app_version = models.CharField(max_length=40, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["platform", "token"], name="unique_mobile_push_token"),
        ]

    def __str__(self) -> str:
        return f"{self.get_platform_display()} · {self.user}"


class SignalContact(models.Model):
    """Eigene Signal-Nummer für persönliche Benachrichtigungen (freiwillig, per Code bestätigt)."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="signal_contact")
    number = models.CharField(max_length=20)
    verified_at = models.DateTimeField(null=True, blank=True)
    code_hash = models.CharField(max_length=64, blank=True, default="")
    code_expires_at = models.DateTimeField(null=True, blank=True)
    code_attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Signal · {self.user}"


class SignalOutbox(models.Model):
    """Postausgang für Signal; der notify-worker versendet und wiederholt bei Fehlern."""

    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="signal_outbox")
    # +49… (Person) oder group.… (Gruppe)
    recipient = models.CharField(max_length=200)
    message = models.TextField()
    dedupe_key = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["dedupe_key"], condition=~Q(dedupe_key=""), name="unique_signal_dedupe"),
        ]
        indexes = [models.Index(fields=["sent_at", "next_attempt_at"], name="signal_outbox_due_idx")]

    def __str__(self) -> str:
        return f"Signal → {self.recipient[:12]}…"
