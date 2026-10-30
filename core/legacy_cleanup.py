"""Einmalige Bereinigung der Altdaten (0.27, Betreiberentscheid vom 30.10.2026).

Die einzige Ausnahme von append-only. Sie läuft nur über
``manage.py cleanup_legacy_data --apply --user NAME`` und nur mit den Rechten
des Datenbank-Eigentümers (die App-Rolle darf Audit-Einträge weder ändern noch
löschen). Ohne ``--apply`` wird nur gezählt (Trockenlauf).

1. Audit ``fleet.status_changed`` (Objekt Fahrzeug): Die früheren
   Einsatzphasen „2“, „3“ und „4“ in ``from``/``to`` werden zu „1“
   (Einsatzbereit). Sind ``from`` und ``to`` danach gleich, hielt der Eintrag
   nur einen Wechsel der Einsatzphase fest; er wird gelöscht. Die Codes „1“
   und „6“ bleiben als Speicherwerte stehen; die Audit-Ansicht zeigt sie als
   „Einsatzbereit“ und „Außer Dienst“ (``core.audit_labels``).
2. Lesebestätigungen von Dienstanweisungen: IP-Adresse und Browser werden
   geleert.
3. Bemerkungen von Desinfektionsprotokollen, die vor dem Einspielen von
   Migration 0067 begonnen wurden, werden geleert: Das Feld hieß bis dahin
   „Bemerkungen / Transportgrund“.

Je Wache entsteht ein Audit-Eintrag ``system.legacy_cleanup`` mit den Zahlen
je Schritt, der ausführenden Person und der Zeit. Ein zweiter Lauf ändert
nichts und schreibt keinen weiteren Eintrag. Backups behalten den alten Stand
bis zu ihrem Ablauf.
"""
from __future__ import annotations

from dataclasses import dataclass

from django.db import connection, transaction
from django.db.migrations.recorder import MigrationRecorder
from django.db.models import Q

VEHICLE_STATUS_ACTION = "fleet.status_changed"
CLEANUP_ACTION = "system.legacy_cleanup"
CUTOFF_MIGRATION = ("core", "0067_fleet_neutral_status")
# Frühere Einsatzphasen → „1“ (Einsatzbereit). Die Speichercodes „1“ und „6“
# bleiben nach Betreiberentscheid unverändert; wer sie später ebenfalls
# umschreiben will, ergänzt sie nur hier.
STATUS_REWRITE = {"2": "1", "3": "1", "4": "1"}
DELETE_CHUNK = 500


@dataclass
class Counts:
    vehicle_status_events: int = 0   # neutralisiert, bleiben erhalten
    mission_phase_events: int = 0    # nur Wechsel der Einsatzphase, werden gelöscht
    sop_receipts: int = 0
    disinfection_notes: int = 0

    @property
    def total(self) -> int:
        return self.vehicle_status_events + self.mission_phase_events + self.sop_receipts + self.disinfection_notes

    def changes(self) -> dict:
        return {
            "legacy_vehicle_status": {"from": self.vehicle_status_events, "to": 0},
            "legacy_mission_phases": {"from": self.mission_phase_events, "to": 0},
            "legacy_sop_receipts": {"from": self.sop_receipts, "to": 0},
            "legacy_disinfection_notes": {"from": self.disinfection_notes, "to": 0},
        }


def neutral_vehicle_metadata(metadata):
    """``(neue Metadaten, löschen)`` – oder ``(None, False)`` ohne Einsatzphase.

    Geändert werden nur die obersten Werte ``from`` und ``to``.
    """
    if not isinstance(metadata, dict):
        return None, False
    new = dict(metadata)
    changed = False
    for key in ("from", "to"):
        value = new.get(key)
        if isinstance(value, str) and value in STATUS_REWRITE:
            new[key] = STATUS_REWRITE[value]
            changed = True
    if not changed:
        return None, False
    return new, new.get("from") == new.get("to")


def stations_in_scope(actor=None, station_slug: str = ""):
    """``(Wachen der Bereinigung, übersprungene Wachen)``.

    Ohne Person (Trockenlauf) alle Wachen; ein Superuser bereinigt alle Wachen,
    ein Master-Admin nur die Wachen, in denen er aktiv Admin ist. Demo-Wachen
    je Besuch werden ohnehin gelöscht und bleiben außen vor.
    """
    from .models import Membership, Station

    stations = Station.objects.filter(demo_sandbox__isnull=True).order_by("pk")
    if station_slug:
        stations = stations.filter(slug=station_slug)
    stations = list(stations)
    if actor is None or actor.is_superuser:
        return stations, []
    admin_of = set(Membership.objects.filter(
        user=actor, role=Membership.Role.ADMIN, is_active=True,
    ).values_list("station_id", flat=True))
    return [s for s in stations if s.pk in admin_of], [s for s in stations if s.pk not in admin_of]


def cutoff():
    """Zeitpunkt, an dem Migration 0067 eingespielt wurde (oder ``None``)."""
    app, name = CUTOFF_MIGRATION
    return MigrationRecorder.Migration.objects.filter(app=app, name=name).values_list("applied", flat=True).first()


def _vehicle_events(station_ids):
    from .models import AuditEvent

    return AuditEvent.objects.filter(
        station_id__in=station_ids, action=VEHICLE_STATUS_ACTION, object_type="Vehicle",
    )


def _receipts(station_ids):
    from .orga_models import SOPReceipt

    return SOPReceipt.objects.filter(station_id__in=station_ids).filter(
        Q(ip_address__isnull=False) | ~Q(user_agent=""),
    )


def _old_notes(station_ids, before):
    from .fleet_models import DisinfectionProtocol

    if before is None:
        return DisinfectionProtocol.objects.none()
    return DisinfectionProtocol.objects.filter(station_id__in=station_ids, started_at__lt=before).exclude(notes="")


def survey(stations) -> dict:
    """Zahlen je Wache, ohne etwas zu ändern: ``{station_id: Counts}``."""
    station_ids = [station.pk for station in stations]
    result = {station_id: Counts() for station_id in station_ids}
    for event in _vehicle_events(station_ids).only("pk", "station_id", "metadata").iterator():
        new, delete = neutral_vehicle_metadata(event.metadata)
        if new is None:
            continue
        if delete:
            result[event.station_id].mission_phase_events += 1
        else:
            result[event.station_id].vehicle_status_events += 1
    for station_id in _receipts(station_ids).values_list("station_id", flat=True):
        result[station_id].sop_receipts += 1
    for station_id in _old_notes(station_ids, cutoff()).values_list("station_id", flat=True):
        result[station_id].disinfection_notes += 1
    return result


def _required_privileges():
    from .fleet_models import DisinfectionProtocol
    from .models import AuditEvent
    from .orga_models import SOPReceipt

    return (
        (AuditEvent._meta.db_table, "UPDATE"),
        (AuditEvent._meta.db_table, "DELETE"),
        (SOPReceipt._meta.db_table, "UPDATE"),
        (DisinfectionProtocol._meta.db_table, "UPDATE"),
    )


def missing_privileges() -> list[str]:
    """Fehlende Tabellenrechte des Datenbank-Benutzers (nur PostgreSQL prüft Rechte)."""
    if connection.vendor != "postgresql":
        return []
    missing = []
    with connection.cursor() as cursor:
        for table, privilege in _required_privileges():
            cursor.execute("SELECT has_table_privilege(current_user, %s, %s)", [table, privilege])
            if not cursor.fetchone()[0]:
                missing.append(f"{privilege} {table}")
    return missing


@transaction.atomic
def apply(actor, stations) -> dict:
    """Bereinigt die angegebenen Wachen in einer Transaktion; gibt die Zahlen zurück."""
    from .models import AuditEvent
    from .services import audit

    station_ids = [station.pk for station in stations]
    found = survey(stations)

    # Bewusst an der Modell-Sperre vorbei (AuditEvent.save/delete): Das ist die
    # eine, vom Betreiber entschiedene Ausnahme von append-only.
    doomed = []
    for event in _vehicle_events(station_ids).only("pk", "metadata").iterator():
        new, delete = neutral_vehicle_metadata(event.metadata)
        if new is None:
            continue
        if delete:
            doomed.append(event.pk)
        else:
            AuditEvent.objects.filter(pk=event.pk).update(metadata=new)
    for start in range(0, len(doomed), DELETE_CHUNK):
        AuditEvent.objects.filter(pk__in=doomed[start:start + DELETE_CHUNK]).delete()

    _receipts(station_ids).update(ip_address=None, user_agent="")
    _old_notes(station_ids, cutoff()).update(notes="")

    # Ein Protokoll je Wache; ein zweiter Lauf ohne Änderung schreibt keins.
    done = set(AuditEvent.objects.filter(
        station_id__in=station_ids, action=CLEANUP_ACTION,
    ).values_list("station_id", flat=True))
    for station in stations:
        counts = found[station.pk]
        if counts.total == 0 and station.pk in done:
            continue
        audit(actor, station, CLEANUP_ACTION, station, {"changes": counts.changes(), "scope": "0.27"})
    return found
