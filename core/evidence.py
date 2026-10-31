"""Nachweise: Verzeichnis, Schutz vor dem Löschen und „Außer Betrieb nehmen“.

Ein Nachweis (Prüfung, Funktionskontrolle, Einweisung, Übernahme,
Desinfektion, Quittierung, Buchung, Audit …) hängt nur per ``PROTECT`` an
seinem Objekt. Ein Objekt mit Nachweisen wird deshalb nicht gelöscht, sondern

- außer Betrieb genommen (Fahrzeug, Medizingerät; wieder in Betrieb nehmen
  ist möglich),
- aus dem Gebrauch genommen (Desinfektionsmittel, Django-Admin; Stufe des
  Desinfektionsplans über „In Verwendung“) oder
- außer Kraft gesetzt (Dienstanweisung).

Die Nachweise bleiben sichtbar. Außer Betrieb genommene Objekte nehmen keine
neuen Nachweise an (``vehicle_must_be_active``, ``device_must_be_in_service``).

Neue Modelle mit Nachweischarakter gehören in ``EVIDENCE_MODELS``; Modelle mit
nachweisähnlichem Namen, die keine Nachweise sind, in ``NOT_EVIDENCE`` (mit
Grund). ``core/test_evidence_protection.py`` prüft beides und löscht jedes
Objekt, auf das ein Nachweis zeigt (Negativtest).

Einzige Löschwege für Nachweise bleiben die Demo-Bereinigung
(``purge_demo_sandboxes``, ``load_demo_data --reset``) und Aufbewahrungsfristen,
beide mit Eigentümerrechten der Datenbank (docs/OPERATIONS.md).
"""
from __future__ import annotations

from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect
from django.utils import timezone, translation
from django.utils.translation import gettext, gettext_lazy as _

from .fleet_models import Vehicle
from .models import Membership
from .mpg_models import MedicalDevice
from .services import audit

# Tabellen mit Nachweischarakter ("app_label.Model"). Jeder Fremdschlüssel
# dieser Modelle ist PROTECT; append-only-Modelle (Schutz in save()/delete())
# stehen hier ebenfalls.
EVIDENCE_MODELS = (
    "core.AuditEvent",
    "core.HandoverEntry",
    "core.HandoverRevision",
    "core.HandoverAck",
    "core.HandoverAttachment",
    "core.NewsAttachment",
    "core.PinboardAttachment",
    "core.ChecklistCompletion",
    "core.CoffeeEntry",
    "core.CoffeeCashMovement",
    "core.Defect",
    "core.DefectEvent",
    "core.DefectAttachment",
    "core.AssetEvent",
    "core.InventoryEvent",
    "core.StockMovement",
    "core.WikiRevision",
    "core.VehicleHandover",
    "core.DisinfectionProtocol",
    "core.MaintenanceLog",
    "core.DeviceRoutineCheck",
    "core.DeviceTrainingRecord",
    "core.SOPRevision",
    "core.SOPReceipt",
)

# Nachweisähnliche Namen ohne Nachweischarakter, jeweils mit Grund.
NOT_EVIDENCE = {
    "core.CalendarEvent": "Termin der Wache, kein Nachweis",
    "core.DisinfectionLevel": (
        "Stufe des Desinfektionsplans, kein Nachweis; Protokolle hängen per PROTECT daran, "
        "deshalb „In Verwendung“ abwählen statt löschen"
    ),
    "core.ErrorEvent": "technisches Fehlerereignis, löscht purge_error_events nach Frist",
    "core.NewsAcknowledgement": "Lesestatus einer Neuigkeit, kein Nachweis (Lesepflicht folgt mit 0.28)",
    "core.QrTotpUse": "Schutz gegen die Wiederverwendung eines Anmeldecodes",
    "core.StationTaskCompletion": "„Wieder öffnen“ löscht bewusst (Audit station_task.reopened)",
}

# Namensendungen, die auf einen Nachweis hindeuten. Ein Modell mit dieser
# Endung muss in einer der beiden Listen stehen.
EVIDENCE_NAME_SUFFIXES = (
    "Event", "Revision", "Receipt", "Log", "Check", "Record", "Attachment", "Movement",
    "Completion", "Ack", "Acknowledgement", "Cancellation", "Protocol", "Handover", "Entry", "Use",
)

# Wer außer Betrieb nimmt und wieder in Betrieb nimmt. Übergangsweise
# Schichtleitung und Admin, bis das Funktionsmodell (0.28) die
# MPG-Beauftragten und den Fuhrpark kennt.
RETIRE_ROLES = frozenset({Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN})

VEHICLE_RETIRED_MESSAGE = _("Dieses Fahrzeug ist außer Betrieb genommen. Es nimmt keine neuen Einträge an.")
DEVICE_RETIRED_MESSAGE = _(
    "Dieses Gerät ist außer Betrieb genommen. Kontrollen, Prüfungen, Einweisungen und Mängel "
    "können nicht mehr erfasst werden."
)


def is_vehicle_retired(vehicle) -> bool:
    return not vehicle.is_active


def is_device_retired(device) -> bool:
    return device.current_status == MedicalDevice.Status.DECOMMISSIONED


def reject_if_retired(model, is_retired, detail_url_name: str, message):
    """Schreibende Ansicht für außer Betrieb genommene Objekte sperren.

    Steht unter ``membership_required``/``require_POST``: Das Objekt wird nur in
    der Wache der Person gesucht. Fehlt es, antwortet die Ansicht selbst (404).
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, slug, *args, **kwargs):
            obj = model.objects.filter(station=request.membership.station, slug=slug).first()
            if obj is not None and is_retired(obj):
                messages.error(request, str(message))
                return redirect(detail_url_name, slug=slug)
            return view_func(request, slug, *args, **kwargs)

        return wrapped

    return decorator


vehicle_must_be_active = reject_if_retired(
    Vehicle, is_vehicle_retired, "fleet_vehicle_detail", VEHICLE_RETIRED_MESSAGE,
)
device_must_be_in_service = reject_if_retired(
    MedicalDevice, is_device_retired, "mpg_device_detail", DEVICE_RETIRED_MESSAGE,
)


def retire_vehicle(vehicle, *, actor) -> bool:
    """Fahrzeug außer Betrieb nehmen. ``False``, wenn es das schon war.

    Übernahmen und Desinfektionen bleiben unverändert. Der Eintrag in „Geräte &
    Fahrzeuge“ (StationAsset) wird bewusst nicht angepasst.
    """
    from .crew_notifications import mark_vehicle_notifications_read

    with transaction.atomic():
        vehicle = Vehicle.objects.select_for_update().get(pk=vehicle.pk)
        if not vehicle.is_active:
            return False
        vehicle.is_active = False
        vehicle.save(update_fields=["is_active", "updated_at"])
        # Offene Hinweise „Fahrzeug kann freigegeben werden“ sind erledigt.
        mark_vehicle_notifications_read(vehicle)
        audit(actor, vehicle.station, "fleet.vehicle_retired", vehicle, {
            "fields": ["is_active"], "from": True, "to": False,
        })
    return True


def reactivate_vehicle(vehicle, *, actor) -> bool:
    """Fahrzeug wieder in Betrieb nehmen; es steht danach auf „Außer Dienst“.

    Einsatzbereit meldet es erst die Besatzung (fail-safe).
    """
    with transaction.atomic():
        vehicle = Vehicle.objects.select_for_update().get(pk=vehicle.pk)
        if vehicle.is_active:
            return False
        previous = vehicle.tactical_status
        vehicle.is_active = True
        vehicle.tactical_status = Vehicle.TacticalStatus.OUT_OF_SERVICE
        vehicle.status_note = ""
        vehicle.save(update_fields=["is_active", "tactical_status", "status_note", "updated_at"])
        audit(actor, vehicle.station, "fleet.vehicle_reactivated", vehicle, {
            "fields": ["is_active", "tactical_status"],
            "changes": {
                "is_active": {"from": False, "to": True},
                "tactical_status": {"from": previous, "to": Vehicle.TacticalStatus.OUT_OF_SERVICE},
            },
        })
    return True


def retire_device(device, *, actor) -> bool:
    """Medizingerät dauerhaft außer Betrieb nehmen. ``False``, wenn es das schon war.

    Prüfungen, Funktionskontrollen, Einweisungen und Mängel bleiben erhalten;
    das Datum steht in „Außerbetriebnahme“ (Bestandsverzeichnis).
    """
    with transaction.atomic():
        device = MedicalDevice.objects.select_for_update().get(pk=device.pk)
        if is_device_retired(device):
            return False
        previous = device.current_status
        device.current_status = MedicalDevice.Status.DECOMMISSIONED
        device.decommissioned_at = timezone.localdate()
        device.status_note = ""
        # current_status in update_fields: Der Status wird nach „Geräte &
        # Fahrzeuge“ gespiegelt (core/device_status.py).
        device.save(update_fields=["current_status", "decommissioned_at", "status_note", "updated_at"])
        audit(actor, device.station, "mpg.device_retired", device, {
            "fields": ["current_status"], "from": previous, "to": MedicalDevice.Status.DECOMMISSIONED,
        })
    return True


def reactivate_device(device, *, actor) -> bool:
    """Medizingerät wieder in Betrieb nehmen; es bleibt gesperrt bis zur Freigabe.

    Die Freigabe (Schichtleitung oder Admin) wird wie jede Freigabe als
    Funktionskontrolle dokumentiert (fail-safe).
    """
    with transaction.atomic():
        device = MedicalDevice.objects.select_for_update().get(pk=device.pk)
        if not is_device_retired(device):
            return False
        device.current_status = MedicalDevice.Status.OOB
        device.decommissioned_at = None
        # Gespeichert in der Wachensprache, nicht in der Sprache der Person.
        with translation.override(settings.LANGUAGE_CODE):
            device.status_note = gettext("Wieder in Betrieb genommen. Vor dem Einsatz bitte prüfen und freigeben.")[:300]
        device.save(update_fields=["current_status", "decommissioned_at", "status_note", "updated_at"])
        audit(actor, device.station, "mpg.device_reactivated", device, {
            "fields": ["current_status"], "from": MedicalDevice.Status.DECOMMISSIONED, "to": MedicalDevice.Status.OOB,
        })
    return True
