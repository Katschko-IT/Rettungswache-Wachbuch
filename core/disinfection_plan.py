"""Desinfektionsplan der Wache: Stufen und Desinfektionsmittel.

Alle Abfragen sind an eine Wache gebunden. Jede Auswahl von Mitteln läuft über
``active_disinfectants``, jede Auswahl von Stufen über ``active_levels`` –
so gibt es je eine Stelle für die Filter: Mittel, die nicht mehr in Gebrauch
sind, und Stufen, die nicht mehr in Verwendung sind, stehen nicht zur Wahl
(Protokolle behalten sie per PROTECT, core/evidence.py).

Bis der Plan bestätigt ist, gilt das bisherige Verhalten: Das
Protokollformular fragt Mittel, Einwirkzeit und Sperre ab; die Freigaberegel
einer Stufe wirkt noch nicht.
"""
from __future__ import annotations

from django.conf import settings
from django.utils import translation

from .fleet_models import DEFAULT_LEVEL_NAMES, DisinfectantMaster, DisinfectionLevel


def active_disinfectants(station):
    return DisinfectantMaster.objects.filter(station=station, is_active=True).order_by("name", "pk")


def active_levels(station):
    return DisinfectionLevel.objects.filter(station=station, is_active=True).select_related("disinfectant")


def ensure_default_levels(station) -> None:
    """Die Standardstufen anlegen, falls die Wache noch keine Stufe hat.

    Namen in der Wachensprache; Mittel und Einwirkzeit vom ersten Mittel der
    Wache, Freigabe „Nach Einwirkzeit“ und unbestätigt – also das bisherige
    Verhalten. Wachwerk macht damit keine fachliche Vorgabe: Die Wache passt
    den Plan mit ihren Hygienebeauftragten an.
    """
    if DisinfectionLevel.objects.filter(station=station).exists():
        return
    agent = active_disinfectants(station).first()
    minutes = (agent.default_exposure_minutes or None) if agent else None
    with translation.override(settings.LANGUAGE_CODE):
        names = [str(name) for name in DEFAULT_LEVEL_NAMES]
    for name in names:
        DisinfectionLevel.objects.get_or_create(
            station=station,
            name=name,
            defaults={
                "disinfectant": agent,
                "release_rule": DisinfectionLevel.ReleaseRule.AFTER_EXPOSURE,
                "exposure_minutes": minutes,
            },
        )
