from django.core.management.base import BaseCommand

from core.services import apply_retention


class Command(BaseCommand):
    help = "Wendet konfigurierte Aufbewahrungsfristen an (Feeds, optional Audit, Push-Outbox)."

    def handle(self, *args, **options):
        result = apply_retention()
        self.stdout.write(
            self.style.SUCCESS(
                f"Retention: {result['feed_items']} Feed-Eintraege, "
                f"{result['audit_events']} Audit-Ereignisse, "
                f"{result['push_outbox']} Push-Outbox-Eintraege, "
                f"{result['feedback']} Rueckmeldungen entfernt."
            )
        )
