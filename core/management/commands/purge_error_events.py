"""
Management-Befehl zur technischen Bereinigung veralteter Fehlerereignisse.
"""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.diagnostics_models import ErrorEvent


class Command(BaseCommand):
    help = (
        "Löscht veraltete bereinigte Fehlerereignisse gemäß technischer "
        "Aufbewahrungsrichtlinie (keine gesetzliche Aufbewahrungsfrist). "
        "Standard-Haltedauer aus settings.ERROR_EVENT_RETENTION_DAYS (Fallback: 30 Tage)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="Aufbewahrungsdauer in Tagen (Standard: settings.ERROR_EVENT_RETENTION_DAYS oder 30).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simuliert den Löschvorgang und gibt nur die Anzahl der betroffenen Ereignisse aus.",
        )

    def handle(self, *args, **options):
        days = options.get("days")
        if days is None:
            days = getattr(settings, "ERROR_EVENT_RETENTION_DAYS", 30)

        if not isinstance(days, int) or days <= 0:
            raise CommandError("Der Parameter --days muss eine positive Ganzzahl sein.")

        cutoff = timezone.now() - timedelta(days=days)
        queryset = ErrorEvent.objects.filter(occurred_at__lt=cutoff)
        dry_run = options.get("dry_run", False)

        if dry_run:
            count = queryset.count()
            self.stdout.write(
                self.style.WARNING(
                    f"DRY-RUN: {count} Fehlerereignis(se) vor dem "
                    f"{cutoff:%Y-%m-%d %H:%M:%S} UTC (älter als {days} Tage) würden gelöscht."
                )
            )
            return

        deleted_count, _ = queryset.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"{deleted_count} Fehlerereignis(se) vor dem "
                f"{cutoff:%Y-%m-%d %H:%M:%S} UTC (älter als {days} Tage) gelöscht."
            )
        )
