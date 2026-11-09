"""Bezug eines Mangels: Auswahlliste, Zuordnung und Hinweis „bereits gemeldet“.

Ein Bezug ist ein Fahrzeug aus dem Fuhrpark, ein Medizinprodukt aus dem
Medizinproduktebuch, ein Eintrag aus „Geräte & Fahrzeuge“ (``StationAsset``)
oder freier Text.

Zwei Meldungen betreffen nur dann dasselbe Objekt, wenn

- der Schlüssel gleich ist (``Defect.vehicle`` bzw. ``Defect.medical_device``)
  oder
- der gespeicherte Bezug nach Normalisierung (Groß-/Kleinschreibung,
  Leerraum) exakt einem Namen des Objekts entspricht.

Teilstrings zählen nie: „RTW 1“ ist nicht „RTW 10“ und nicht „RTW“.

Jede Abfrage hier ist an genau eine Wache gebunden; Mängel, Fahrzeuge und
Geräte anderer Wachen erscheinen weder in der Auswahl noch im Hinweis.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from django.urls import reverse
from django.utils.translation import gettext_lazy as _

VEHICLE_PREFIX = "vehicle:"
DEVICE_PREFIX = "device:"
ASSET_PREFIX = "asset:"
CUSTOM_VALUE = "__custom__"


def normalize_ref(value) -> str:
    """Vergleichsform eines Bezugs: Leerraum zusammengefasst, klein geschrieben.

    Entspricht ``normalizeRef`` in ``core/static/core/defect_form.js``.
    """
    return " ".join(str(value or "").split()).lower()


def vehicle_ref_label(vehicle) -> str:
    """Bezug eines Fahrzeugs, wie ihn auch die Fuhrpark-Meldung schreibt."""
    if vehicle.license_plate:
        return f"{vehicle.call_sign} ({vehicle.license_plate})"
    return vehicle.call_sign


def device_ref_label(device) -> str:
    """Bezug eines Medizinprodukts, wie ihn auch das Medizinproduktebuch schreibt."""
    number = device.inventory_number or device.serial_number
    if number:
        return f"{device.name} ({number})"
    return device.name


@dataclass
class RefOption:
    """Eine Zeile der Bezugsauswahl."""

    key: str
    kind: str  # "vehicle", "device" oder "asset"
    group: str
    label: str  # wird als Defect.asset_ref gespeichert
    status: str = ""
    category: str = ""
    vehicle_id: int | None = None
    device_id: int | None = None
    asset_pk: int | None = None
    aliases: set[str] = field(default_factory=set)  # normalisierte Namen
    lookup: set[str] = field(default_factory=set)  # kleingeschriebene Kennungen für ?asset=

    @property
    def display(self) -> str:
        return f"{self.label} · {self.status}" if self.status else self.label

    def matches(self, defect) -> bool:
        if self.vehicle_id is not None and defect.vehicle_id == self.vehicle_id:
            return True
        if self.device_id is not None and defect.medical_device_id == self.device_id:
            return True
        return bool(defect.asset_ref) and normalize_ref(defect.asset_ref) in self.aliases


def _unique(values):
    seen, twice = set(), set()
    for value in values:
        (twice if value in seen else seen).add(value)
    return seen - twice


def _mirrors_vehicle(asset, vehicle) -> bool:
    """Wie ``Vehicle.matching_assets``, ohne eigene Abfrage je Fahrzeug."""
    return (
        asset.label == vehicle.call_sign
        or asset.asset_id == vehicle.slug
        or asset.label.startswith(f"{vehicle.call_sign} ")
    )


def build_reference_options(station, *, include_devices=True) -> list[RefOption]:
    """Bezugsauswahl einer Wache: Fahrzeuge, Medizingeräte, weitere Einträge.

    Fahrzeuge nur aktive (nicht außer Betrieb genommene), Medizingeräte nur
    nicht außer Betrieb genommene, jeweils nur bei eingeschaltetem Modul.
    Ein Eintrag aus „Geräte & Fahrzeuge“, der ein gelistetes Fahrzeug oder
    Gerät spiegelt, erscheint nicht doppelt; seine Namen zählen für das
    Fahrzeug bzw. Gerät.
    """
    from .fleet_models import Vehicle
    from .mpg_models import MedicalDevice
    from .wachalltag_models import Defect, StationAsset

    assets = list(StationAsset.objects.filter(station=station).order_by("kind", "label"))
    mirrored: set[int] = set()
    options: list[RefOption] = []

    if getattr(station, "fleet_enabled", False):
        vehicles = list(Vehicle.objects.filter(station=station, is_active=True).order_by("call_sign"))
        unique_signs = _unique(normalize_ref(v.call_sign) for v in vehicles)
        for vehicle in vehicles:
            option = RefOption(
                key=f"{VEHICLE_PREFIX}{vehicle.pk}",
                kind="vehicle",
                group=str(_("Fahrzeuge")),
                label=vehicle_ref_label(vehicle),
                status="" if vehicle.tactical_status == Vehicle.TacticalStatus.READY
                else str(vehicle.get_tactical_status_display()),
                category=Defect.Category.VEHICLE,
                vehicle_id=vehicle.pk,
            )
            option.aliases |= {
                normalize_ref(option.label),
                normalize_ref(f"{vehicle.call_sign} ({vehicle.license_plate})"),
            }
            if normalize_ref(vehicle.call_sign) in unique_signs:
                option.aliases.add(normalize_ref(vehicle.call_sign))
            option.lookup |= {option.key, vehicle.slug.lower()}
            for asset in assets:
                if asset.kind == StationAsset.Kind.VEHICLE and _mirrors_vehicle(asset, vehicle):
                    mirrored.add(asset.pk)
                    option.aliases.add(normalize_ref(asset.label))
                    option.lookup |= {f"{ASSET_PREFIX}{asset.pk}", str(asset.pk), asset.asset_id.lower()}
            options.append(option)

    if include_devices and getattr(station, "mpg_enabled", False):
        devices = list(
            MedicalDevice.objects.filter(station=station)
            .exclude(current_status=MedicalDevice.Status.DECOMMISSIONED)
            .order_by("name", "pk")
        )
        unique_names = _unique(normalize_ref(d.name) for d in devices)
        for device in devices:
            option = RefOption(
                key=f"{DEVICE_PREFIX}{device.pk}",
                kind="device",
                group=str(_("Medizingeräte")),
                label=device_ref_label(device),
                status="" if device.current_status == MedicalDevice.Status.READY
                else str(device.get_current_status_display()),
                category=Defect.Category.DEVICE,
                device_id=device.pk,
            )
            number = device.inventory_number or device.serial_number
            option.aliases |= {normalize_ref(option.label), normalize_ref(f"{device.name} ({number})")}
            if normalize_ref(device.name) in unique_names:
                option.aliases.add(normalize_ref(device.name))
            option.lookup |= {option.key, device.slug.lower()}
            for asset in assets:
                if asset.kind == StationAsset.Kind.DEVICE and asset.asset_id == device.slug:
                    mirrored.add(asset.pk)
                    option.aliases.add(normalize_ref(asset.label))
                    option.lookup |= {f"{ASSET_PREFIX}{asset.pk}", str(asset.pk), asset.asset_id.lower()}
            options.append(option)

    groups = {
        StationAsset.Kind.VEHICLE: (str(_("Fahrzeuge")), Defect.Category.VEHICLE),
        StationAsset.Kind.DEVICE: (str(_("Geräte")), Defect.Category.DEVICE),
        StationAsset.Kind.KEY: (str(_("Schlüssel")), Defect.Category.KEY),
    }
    for asset in assets:
        if asset.pk in mirrored:
            continue
        group, category = groups.get(asset.kind, (str(_("Weitere")), Defect.Category.MATERIAL))
        option = RefOption(
            key=f"{ASSET_PREFIX}{asset.pk}",
            kind="asset",
            group=group,
            label=asset.label,
            status="" if asset.status == StationAsset.Status.READY else str(asset.get_status_display()),
            category=category,
            asset_pk=asset.pk,
        )
        option.aliases |= {normalize_ref(asset.label), normalize_ref(asset.asset_id)}
        option.lookup |= {option.key, str(asset.pk), asset.asset_id.lower()}
        options.append(option)

    # Fahrzeuge aus dem Fuhrpark und aus „Geräte & Fahrzeuge“ in einer Gruppe.
    order = {str(_("Fahrzeuge")): 0, str(_("Medizingeräte")): 1, str(_("Geräte")): 2, str(_("Schlüssel")): 3}
    options.sort(key=lambda option: order.get(option.group, 9))
    return options


def grouped_options(options):
    """[(Gruppenname, [Optionen])] in der Reihenfolge der Liste."""
    groups: list[tuple[str, list[RefOption]]] = []
    for option in options:
        if groups and groups[-1][0] == option.group:
            groups[-1][1].append(option)
        else:
            groups.append((option.group, [option]))
    return groups


def resolve_reference(options, value):
    """Option zu einem Schlüssel oder einer Kennung (``?asset=``), sonst ``None``.

    Angenommen werden der Schlüssel (``vehicle:3``), Kennungen
    (Fahrzeug- bzw. Geräte-Kurzname, ``asset_id`` und Nummer eines Eintrags
    in „Geräte & Fahrzeuge“) und der angezeigte Name, jeweils exakt.
    """
    raw = str(value or "").strip()
    if not raw:
        return None
    lowered = raw.lower()
    for option in options:
        if lowered in option.lookup:
            return option
    normalized = normalize_ref(raw)
    for option in options:
        if normalize_ref(option.label) == normalized:
            return option
    return None


def duplicates_for(option, open_defects, *, text: str = "", options=()):
    """Offene Mängel zur gewählten Option oder zum Freitext (exakt)."""
    if option is not None:
        return [defect for defect in open_defects if option.matches(defect)]
    normalized = normalize_ref(text)
    if not normalized:
        return []
    same_object = [candidate for candidate in options if normalized in candidate.aliases]
    return [
        defect for defect in open_defects
        if (defect.asset_ref and normalize_ref(defect.asset_ref) == normalized)
        or any(candidate.matches(defect) for candidate in same_object)
    ]


def defect_hint_json(defect) -> dict:
    return {
        "pk": defect.pk,
        "title": defect.title,
        "status": str(defect.get_status_display()),
        "priority": str(defect.get_priority_display()),
        "asset_ref": defect.asset_ref,
        "url": reverse("defect_detail_web", args=[defect.pk]),
    }


def duplicate_hint_data(options, open_defects) -> dict:
    """Daten für den Hinweis im Browser (json_script), nur diese Wache.

    ``by_key``: Schlüssel der Auswahl -> Mangelnummern;
    ``by_text``: normalisierter Freitext -> Mangelnummern;
    ``defects``: Nummer -> Titel, Status, Priorität, Bezug, Adresse.
    """
    by_key: dict[str, list[int]] = {}
    by_text: dict[str, list[int]] = {}
    used: dict[int, object] = {}
    for option in options:
        matching = [defect for defect in open_defects if option.matches(defect)]
        if not matching:
            continue
        by_key[option.key] = [defect.pk for defect in matching]
        for alias in option.aliases:
            bucket = by_text.setdefault(alias, [])
            bucket.extend(defect.pk for defect in matching if defect.pk not in bucket)
        used.update((defect.pk, defect) for defect in matching)
    for defect in open_defects:
        if not defect.asset_ref:
            continue
        bucket = by_text.setdefault(normalize_ref(defect.asset_ref), [])
        if defect.pk not in bucket:
            bucket.append(defect.pk)
        used[defect.pk] = defect
    return {
        "by_key": by_key,
        "by_text": by_text,
        "defects": {str(pk): defect_hint_json(defect) for pk, defect in used.items()},
        "categories": {option.key: option.category for option in options},
    }


def filter_defects_by_reference(queryset, station, value):
    """``?asset=`` der API: dieselbe exakte Zuordnung wie der Hinweis im Browser."""
    from django.db.models import Q

    from .wachalltag_models import Defect

    options = build_reference_options(station)
    option = resolve_reference(options, value)
    aliases = option.aliases if option is not None else {normalize_ref(value)}
    text_ids = [
        pk for pk, ref in Defect.objects.filter(station=station).exclude(asset_ref="").values_list("pk", "asset_ref")
        if normalize_ref(ref) in aliases
    ]
    condition = Q(pk__in=text_ids)
    if option is not None and option.vehicle_id is not None:
        condition |= Q(vehicle_id=option.vehicle_id)
    if option is not None and option.device_id is not None:
        condition |= Q(medical_device_id=option.device_id)
    return queryset.filter(station=station).filter(condition)
