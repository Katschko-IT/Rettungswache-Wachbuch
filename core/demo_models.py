"""Demo-Wache eines einzelnen Besuchs der öffentlichen Demo (docs/DEMO.md)."""
from __future__ import annotations

from django.db import models
from django.utils import timezone


class DemoSandbox(models.Model):
    """Eine Demo-Wache mit Musterdaten, die genau einem Demo-Besuch gehört.

    Abmelden setzt ``ended_at``; ``purge_demo_sandboxes`` löscht danach die
    Wache mit allen Konten und Einträgen.
    """

    station = models.OneToOneField("core.Station", on_delete=models.CASCADE, related_name="demo_sandbox")
    token = models.CharField(max_length=16, unique=True)
    created_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    # Ende der Musterdaten: Was danach entsteht, hat der Besuch selbst getan
    # (Grundlage für den Demo-Rundgang).
    ready_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Demo-Wache"
        verbose_name_plural = "Demo-Wachen"

    def __str__(self):
        return f"Demo {self.token}"
