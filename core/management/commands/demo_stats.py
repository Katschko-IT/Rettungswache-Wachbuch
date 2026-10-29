"""Anonyme Demo-Kennzahlen ausgeben (core/demo_stats.py).

    docker compose exec web python manage.py demo_stats --tage 30
"""
from django.core.management.base import BaseCommand

from core.demo_stats import active_count, recent_days, totals


class Command(BaseCommand):
    help = "Zeigt gestartete Demos, abgeschlossene Rundgänge und Rückmeldungen je Tag."

    def add_arguments(self, parser):
        parser.add_argument("--tage", type=int, default=30, help="Zeitraum in Tagen (Standard: 30).")

    def handle(self, *args, **options):
        days = max(1, options["tage"])
        self.stdout.write(f"{'Tag':<12}{'Demos':>8}{'Rundgang':>10}{'Feedback':>10}")
        for row in recent_days(days):
            self.stdout.write(
                f"{row['day']:%d.%m.%Y}  {row['started']:>8}{row['tour_completed']:>10}{row['feedback']:>10}"
            )
        summary = totals(days)
        share = f" ({summary['tour_share']} %)" if summary["tour_share"] is not None else ""
        self.stdout.write(
            f"Summe {days} Tage: {summary['started']} Demos, {summary['tour_completed']} Rundgänge"
            f"{share}, {summary['feedback']} Rückmeldungen. Gerade aktiv: {active_count()}."
        )
