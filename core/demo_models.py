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


class DemoDailyStat(models.Model):
    """Anonyme Tageszähler der öffentlichen Demo (core/demo_stats.py).

    Bewusst nur Zahlen je Tag: keine IP-Adresse, kein Konto, kein Token und
    keine Verknüpfung zu einer Demo-Wache. Bleibt erhalten, wenn die Demo-
    Wachen gelöscht werden.
    """

    day = models.DateField(unique=True)
    started = models.PositiveIntegerField(default=0)
    tour_completed = models.PositiveIntegerField(default=0)
    feedback = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-day"]
        verbose_name = "Demo-Tageszahl"
        verbose_name_plural = "Demo-Tageszahlen"

    def __str__(self):
        return f"Demo-Zahlen {self.day:%d.%m.%Y}"
