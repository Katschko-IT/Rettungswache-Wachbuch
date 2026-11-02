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


def can_confirm_disinfection(membership) -> bool:
    """Prüft, ob das Mitglied Desinfektionsstufen bestätigen oder bearbeiten darf.

    Berechtigt sind Hygienebeauftragte / Schichtleitung und Master-Admins der Wache.
    """
    if not membership or not getattr(membership, "is_active", False):
        return False
    from .models import Membership

    return (
        membership.role in {Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN}
        or bool(getattr(membership, "is_hygiene_lead", False))
    )


def apply_level_defaults(cleaned_data: dict, level: DisinfectionLevel | None) -> dict:
    """Wendet die Vorgaben einer bestätigten Desinfektionsstufe auf das Protokoll an.

    Ist die Stufe durch Hygienebeauftragte/Wachleitung bestätigt, werden Mittel,
    Freigaberegel und Einwirkzeit übernommen, falls sie im Protokollformular
    nicht abweichend/strenger angegeben wurden.
    """
    if level is None or not getattr(level, "is_rule_confirmed", False):
        return cleaned_data

    # Desinfektionsmittel übernehmen, falls nicht angegeben
    disinfectant = cleaned_data.get("disinfectant")
    is_empty_disinfectant = False
    if disinfectant is None:
        is_empty_disinfectant = True
    elif isinstance(disinfectant, str) and not disinfectant.strip():
        is_empty_disinfectant = True

    if is_empty_disinfectant and getattr(level, "disinfectant", None):
        cleaned_data["disinfectant"] = level.disinfectant

    rule = getattr(level, "release_rule", None)
    if rule:
        if not cleaned_data.get("release_rule"):
            cleaned_data["release_rule"] = rule

        is_timer = rule in {
            "timer",
            "exposure",
            getattr(DisinfectionLevel.ReleaseRule, "AFTER_EXPOSURE", "exposure"),
        }
        if is_timer:
            if not cleaned_data.get("exposure_minutes") and getattr(level, "exposure_minutes", None):
                cleaned_data["exposure_minutes"] = level.exposure_minutes
            if cleaned_data.get("lock_timer_applied") is None:
                cleaned_data["lock_timer_applied"] = True
        elif rule in {"dry", getattr(DisinfectionLevel.ReleaseRule, "AFTER_DRYING", "dry")}:
            user_rule = cleaned_data.get("release_rule")
            if user_rule in {
                "timer",
                "exposure",
                getattr(DisinfectionLevel.ReleaseRule, "AFTER_EXPOSURE", "exposure"),
            }:
                if not cleaned_data.get("exposure_minutes") and getattr(level, "exposure_minutes", None):
                    cleaned_data["exposure_minutes"] = level.exposure_minutes
                if cleaned_data.get("lock_timer_applied") is None:
                    cleaned_data["lock_timer_applied"] = True
            else:
                if cleaned_data.get("lock_timer_applied") is None:
                    cleaned_data["lock_timer_applied"] = False

    return cleaned_data

