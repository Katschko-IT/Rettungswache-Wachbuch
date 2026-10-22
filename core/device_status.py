"""Betriebsstatus von Medizinprodukten: Sperre, Freigabe und Spiegelung.

Regeln:

- Gesperrt (``oob``) wird ein Gerät durch einen gemeldeten Mangel oder eine
  nicht bestandene Funktionskontrolle. Beides legt einen Mangel an, der mit dem
  Gerät verknüpft ist.
- Eine bestandene Funktionskontrolle hebt keine Sperre auf.
- Freigeben darf nur Schichtleitung oder Admin, und erst wenn alle verknüpften
  Mängel erledigt sind. Die Freigabe wird als Funktionskontrolle dokumentiert.
- Das Medizinproduktebuch (``MedicalDevice``) ist führend. Ein gleichnamiges
  Gerät im Bereich „Geräte & Fahrzeuge“ (``StationAsset``) zeigt denselben
  Status; Änderungen dort werden zurückgespiegelt.
"""
from __future__ import annotations

from django.db.models import QuerySet

DEVICE_TO_ASSET = {
    "ready": "ready",
    "limited": "limited",
    "maintenance": "workshop",
    "oob": "oob",
    "decommissioned": "oob",
}
ASSET_TO_DEVICE = {
    "ready": "ready",
    "limited": "limited",
    "workshop": "maintenance",
    "oob": "oob",
}
# Statuswerte, die ein gesperrtes Gerät wieder in Betrieb nehmen.
IN_SERVICE = {"ready", "limited"}


def open_defects(device) -> QuerySet:
    from .wachalltag_models import Defect

    return Defect.objects.filter(medical_device=device).exclude(status=Defect.Status.DONE)


def release_blockers(device) -> list:
    """Offene Mängel, die eine Freigabe verhindern (leer = freigabefähig)."""
    return list(open_defects(device).order_by("created_at"))


def mirror_to_asset(device) -> None:
    from .wachalltag_models import StationAsset

    target = DEVICE_TO_ASSET.get(device.current_status)
    if target is None:
        return
    StationAsset.objects.filter(
        station_id=device.station_id,
        asset_id=device.slug,
        kind=StationAsset.Kind.DEVICE,
    ).exclude(status=target).update(status=target, note=device.status_note[:300])


def mirror_to_device(asset) -> None:
    from .mpg_models import MedicalDevice
    from .wachalltag_models import StationAsset

    if asset.kind != StationAsset.Kind.DEVICE:
        return
    target = ASSET_TO_DEVICE.get(asset.status)
    if target is None:
        return
    MedicalDevice.objects.filter(station_id=asset.station_id, slug=asset.asset_id).exclude(
        current_status__in={target, MedicalDevice.Status.DECOMMISSIONED}
    ).update(current_status=target, status_note=asset.note[:300])


def asset_release_blockers(asset) -> list:
    """Offene Gerätemängel, wenn ein Asset auf „einsatzklar“ gesetzt werden soll."""
    from .mpg_models import MedicalDevice
    from .wachalltag_models import StationAsset

    if asset.kind != StationAsset.Kind.DEVICE:
        return []
    device = MedicalDevice.objects.filter(station_id=asset.station_id, slug=asset.asset_id).first()
    if device is None or device.current_status != MedicalDevice.Status.OOB:
        return []
    return release_blockers(device)
