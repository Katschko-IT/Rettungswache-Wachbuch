"""Management Command: Versendet Fristen-Erinnerungen bei 30, 7 und 0 Tagen und Montags-Wochenübersicht."""
from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.deadline_reminders import (
    DEFAULT_THRESHOLDS,
    collect_deadline_items,
    send_deadline_reminders,
    send_weekly_digest,
)
from core.models import Station


class Command(BaseCommand):
    help = "Versendet Fristen-Erinnerungen bei 30, 7 und 0 Tagen sowie optional die Montags-Wochenübersicht."

    def add_arguments(self, parser):
        parser.add_argument(
            "--station",
            help="Nur für eine bestimmte Wache ausführen (Slug oder ID).",
        )
        parser.add_argument(
            "--thresholds",
            default="30,7,0",
            help="Kommagetrennte Schwellenwerte in Tagen vor Ablauf (Standard: 30,7,0).",
        )
        parser.add_argument(
            "--weekly-digest",
            action="store_true",
            help="Wochenübersicht der anstehenden Fristen an die Wachleitung versenden.",
        )
        parser.add_argument(
            "--today",
            help="Stichtag (JJJJ-MM-TT) statt heute; für Tests und Nachläufe.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Nur anzeigen, welche Fristen fällig sind, ohne Benachrichtigungen anzulegen.",
        )

    def handle(self, *args, **options):
        station = None
        if options["station"]:
            val = options["station"]
            try:
                station = Station.objects.get(pk=int(val)) if val.isdigit() else Station.objects.get(slug=val)
            except Station.DoesNotExist:
                raise CommandError(f"Wache '{val}' nicht gefunden.")

        try:
            thresholds = [int(t.strip()) for t in options["thresholds"].split(",") if t.strip()]
        except ValueError:
            raise CommandError("Ungültiges Format für --thresholds. Beispiel: --thresholds=30,7,0")

        today = timezone.localdate()
        if options["today"]:
            try:
                today = date.fromisoformat(options["today"])
            except ValueError:
                raise CommandError("Ungültiges Datum für --today. Beispiel: --today=2026-11-03")

        if options["dry_run"]:
            items = collect_deadline_items(station=station, today=today, thresholds=thresholds)
            self.stdout.write(f"Dry-Run: {len(items)} fällige Frist(en) gefunden:")
            for item in items:
                self.stdout.write(
                    f" - [{item.category.upper()}] {item.title} (Fällig am {item.due_date}, "
                    f"in {item.days_remaining} Tagen, Empfänger: {len(item.recipients)})"
                )
            return

        sent_deadlines = send_deadline_reminders(station=station, today=today, thresholds=thresholds)
        self.stdout.write(
            self.style.SUCCESS(f"Fristen-Erinnerungen: {sent_deadlines} Benachrichtigung(en) erstellt.")
        )

        if options["weekly_digest"]:
            sent_digest = send_weekly_digest(station=station, today=today)
            self.stdout.write(
                self.style.SUCCESS(f"Wochenübersicht: {sent_digest} Benachrichtigung(en) erstellt.")
            )
