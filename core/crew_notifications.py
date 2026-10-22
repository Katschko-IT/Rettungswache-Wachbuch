"""Benachrichtigt die Besatzung, wenn die Einwirkzeit einer Desinfektion endet.

Das Fahrzeug wird **nicht** automatisch freigegeben: Die Besatzung prüft es und
setzt den Status selbst. Diese Funktion sorgt nur dafür, dass sie rechtzeitig
davon erfährt.

Besatzung eines Fahrzeugs sind alle aktiven Mitglieder der Wache, die es in den
letzten 24 Stunden per Schichtübernahme übernommen haben, sowie die Person, die
die Desinfektion erfasst hat.

Zustellung: Jede Person erhält einen Eintrag im persönlichen Posteingang
(``UserNotification``; Web und App lesen ihn). Zusätzlich werden Outbox-Zeilen
für Web-Push (wenn aktiviert) und für native App-Geräte (wenn ein Push-Relay
konfiguriert ist) geschrieben; den Versand übernimmt der Push-Worker. Hier wird
nie eine Netzverbindung geöffnet.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger(__name__)

CREW_WINDOW = timedelta(hours=24)
# Ältere, längst abgelaufene Sperren lösen keine Nachricht mehr aus
# (z. B. nach längerem Ausfall des Workers).
NOTIFY_WINDOW = timedelta(hours=6)


def dedupe_key(vehicle) -> str:
    return f"vehicle_ready:{vehicle.pk}:{vehicle.disinfection_locked_until.isoformat()}"


def crew_for_vehicle(vehicle, now=None):
    """Aktive Mitglieder, die das Fahrzeug gerade besetzen (siehe Moduldoku)."""
    from django.contrib.auth.models import User

    from .access import CONTENT_ROLES
    from .fleet_models import DisinfectionProtocol, VehicleHandover
    from .models import Membership

    now = now or timezone.now()
    since = now - CREW_WINDOW
    user_ids = set(
        VehicleHandover.objects.filter(vehicle=vehicle, performed_at__gte=since)
        .values_list("crew_member_id", flat=True)
    )
    latest = (
        DisinfectionProtocol.objects.filter(vehicle=vehicle, started_at__gte=since)
        .order_by("-started_at")
        .values_list("performed_by_id", flat=True)
        .first()
    )
    if latest:
        user_ids.add(latest)
    active = Membership.objects.filter(
        station=vehicle.station, is_active=True, role__in=CONTENT_ROLES, user_id__in=user_ids,
    ).values_list("user_id", flat=True)
    return list(User.objects.filter(pk__in=active, is_active=True).order_by("pk"))


def _payload(vehicle, url):
    return {
        "title": f"{vehicle.call_sign}: Einwirkzeit abgelaufen",
        "body": "Desinfektion abgeschlossen. Bitte Fahrzeug prüfen und den Status selbst freigeben.",
        "url": url,
    }


def push_relay_enabled() -> bool:
    # Das Token braucht nur der Push-Worker; zum Einreihen genügt die Adresse.
    return bool(getattr(settings, "PUSH_RELAY_URL", ""))


def _enqueue_channels(notification, payload):
    from .models import PushOutbox, PushSubscription
    from .notification_models import MobilePushDevice
    rows = []
    # Der Versand (mit VAPID-Schlüssel) liegt beim Push-Worker; zum Einreihen
    # reicht der Schalter, damit dieser Prozess keinen privaten Schlüssel braucht.
    if getattr(settings, "WEB_PUSH_ENABLED", False):
        for sub in PushSubscription.objects.filter(user=notification.user, station=notification.station):
            rows.append(PushOutbox(station=notification.station, user=notification.user,
                                   subscription=sub, payload=payload))
    if push_relay_enabled():
        for device in MobilePushDevice.objects.filter(user=notification.user, station=notification.station):
            rows.append(PushOutbox(station=notification.station, user=notification.user,
                                   device=device, payload=payload))
    if rows:
        PushOutbox.objects.bulk_create(rows)
    return len(rows)


def notify_vehicle_ready(vehicle, now=None) -> int:
    """Benachrichtigt die Besatzung eines Fahrzeugs genau einmal je Sperre."""
    from .notification_models import UserNotification
    from .services import audit

    now = now or timezone.now()
    url = reverse("fleet_vehicle_detail", args=[vehicle.slug])
    payload = _payload(vehicle, url)
    key = dedupe_key(vehicle)
    created_for = []
    for user in crew_for_vehicle(vehicle, now):
        try:
            with transaction.atomic():
                notification, created = UserNotification.objects.get_or_create(
                    user=user,
                    dedupe_key=key,
                    defaults={
                        "station": vehicle.station,
                        "kind": UserNotification.Kind.VEHICLE_READY,
                        "title": payload["title"],
                        "body": payload["body"],
                        "url": url,
                    },
                )
                if created:
                    _enqueue_channels(notification, {**payload, "notification_id": notification.pk})
                    created_for.append(user.pk)
        except IntegrityError:
            # Ein paralleler Lauf war schneller; die Nachricht existiert schon.
            continue
    if created_for:
        audit(None, vehicle.station, "fleet.disinfection_crew_notified", vehicle, {
            "fields": ["disinfection_locked_until"],
            "recipients": len(created_for),
        })
    return len(created_for)


def notify_ready_vehicles(now=None) -> int:
    """Prüft alle Wachen auf abgelaufene Einwirkzeiten. Idempotent."""
    from .fleet_models import Vehicle

    now = now or timezone.now()
    due = Vehicle.objects.filter(
        is_active=True,
        station__fleet_enabled=True,
        tactical_status=Vehicle.TacticalStatus.DISINFECTION,
        disinfection_locked_until__lte=now,
        disinfection_locked_until__gte=now - NOTIFY_WINDOW,
    ).select_related("station")
    total = 0
    for vehicle in due:
        try:
            total += notify_vehicle_ready(vehicle, now)
        except Exception:  # pragma: no cover - ein Fahrzeug darf die übrigen nicht blockieren
            logger.exception("Besatzungsbenachrichtigung für Fahrzeug %s fehlgeschlagen", vehicle.pk)
    return total


def mark_vehicle_notifications_read(vehicle) -> int:
    """Nach der Freigabe sind offene Hinweise zu diesem Fahrzeug erledigt."""
    from .notification_models import UserNotification

    return UserNotification.objects.filter(
        station=vehicle.station,
        kind=UserNotification.Kind.VEHICLE_READY,
        dedupe_key__startswith=f"vehicle_ready:{vehicle.pk}:",
        read_at__isnull=True,
    ).update(read_at=timezone.now())


def upcoming_locks_for_user(user, station, now=None):
    """Laufende Sperren der Fahrzeuge, die die Person besetzt.

    Die App plant damit eine lokale Erinnerung zur Sperrzeit – auch ohne
    Server-Push und ohne Netz zum Ablaufzeitpunkt.
    """
    from .fleet_models import Vehicle

    now = now or timezone.now()
    result = []
    for vehicle in Vehicle.objects.filter(
        station=station,
        is_active=True,
        tactical_status=Vehicle.TacticalStatus.DISINFECTION,
        disinfection_locked_until__gt=now,
    ).order_by("disinfection_locked_until"):
        if any(member.pk == user.pk for member in crew_for_vehicle(vehicle, now)):
            payload = _payload(vehicle, reverse("fleet_vehicle_detail", args=[vehicle.slug]))
            result.append({
                "vehicle_id": vehicle.pk,
                "call_sign": vehicle.call_sign,
                "locked_until": vehicle.disinfection_locked_until.isoformat(),
                "key": dedupe_key(vehicle),
                "title": payload["title"],
                "body": payload["body"],
            })
    return result
