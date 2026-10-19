"""Management command to clean up expired and terminal QR login requests and TOTP replay records."""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from core.models import QrLoginRequest, QrTotpUse


class Command(BaseCommand):
    help = "Löscht terminale QR-Login-Anfragen und verbrauchte TOTP-Schritte älter als 24 Stunden."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=24,
            help="Alter in Stunden für die Löschung (Standard: 24).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Nur anzeigen, was gelöscht werden würde, ohne Daten zu verändern.",
        )

    def handle(self, *args, **options):
        hours = max(1, int(options["hours"]))
        dry_run = bool(options["dry_run"])
        cutoff = timezone.now() - timedelta(hours=hours)

        terminal_states = [
            QrLoginRequest.State.DENIED,
            QrLoginRequest.State.EXPIRED,
            QrLoginRequest.State.REVOKED,
            QrLoginRequest.State.CONSUMED,
        ]

        req_qs = QrLoginRequest.objects.filter(
            Q(state__in=terminal_states, created_at__lt=cutoff)
            | Q(expires_at__lt=cutoff)
        )
        totp_qs = QrTotpUse.objects.filter(created_at__lt=cutoff)

        req_count = req_qs.count()
        totp_count = totp_qs.count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"qr_login_cleanup (dry-run): {req_count} QR-Anfragen und {totp_count} TOTP-Einträge würden gelöscht werden (älter als {hours}h)."
                )
            )
            return

        deleted_req, _ = req_qs.delete()
        deleted_totp, _ = totp_qs.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"qr_login_cleanup: {deleted_req} QR-Anfragen und {deleted_totp} TOTP-Einträge gelöscht (älter als {hours}h)."
            )
        )
