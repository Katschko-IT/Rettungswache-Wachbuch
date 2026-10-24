"""Registriert ein Wachenterminal und gibt den Start-Pfad einmalig aus.

Für die Einrichtung eines Kiosk-Geräts (deploy/pi/register-terminal.sh). Der
Pfad enthält das Gerätegeheimnis; er wird nur ausgegeben, nicht gespeichert.
"""
from __future__ import annotations

import secrets

from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

from core.models import Membership, Station
from core.services import audit
from core.terminal import hash_secret
from core.terminal_models import StationTerminal


class Command(BaseCommand):
    help = "Wachenterminal registrieren und Start-Pfad ausgeben."

    def add_arguments(self, parser):
        parser.add_argument("--station", default="", help="Slug der Wache (bei nur einer Wache optional)")
        parser.add_argument("--label", default="Wachenterminal")

    def handle(self, *args, **options):
        stations = Station.objects.filter(is_active=True)
        if options["station"]:
            stations = stations.filter(slug=options["station"])
        if stations.count() != 1:
            raise CommandError("Bitte genau eine aktive Wache mit --station angeben.")
        station = stations.get()
        admin = (
            Membership.objects.filter(station=station, role=Membership.Role.ADMIN, is_active=True, user__is_active=True)
            .select_related("user")
            .order_by("created_at")
            .first()
        )
        if admin is None:
            raise CommandError("Die Wache hat noch keinen aktiven Admin. Zuerst die Ersteinrichtung abschließen.")
        raw = secrets.token_urlsafe(32)
        terminal = StationTerminal.objects.create(
            station=station,
            label=options["label"][:80],
            token_hash=hash_secret(raw),
            created_by=admin.user,
        )
        audit(admin.user, station, "terminal.created", terminal, {"fields": ["label"], "via": "manage.py"})
        self.stdout.write(reverse("terminal_start", args=[raw]))
