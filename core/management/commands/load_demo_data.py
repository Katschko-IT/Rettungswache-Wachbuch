from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.demo import demo_accounts_for_display, demo_mode_enabled, demo_password, load_demo_data


class Command(BaseCommand):
    help = (
        "Befüllt die Standardwache mit fiktiven Musterdaten zum Testen und Vorführen "
        "(Konten demo-*, Übergaben, Kalender, Kasse, Checklisten)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Vorhandene Demo-Daten entfernen und neu anlegen.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Auch ohne DEMO_MODE=true ausführen (nur lokale/Test-Umgebungen).",
        )

    def handle(self, *args, **options):
        if getattr(settings, "DEMO_SANDBOX", False):
            raise CommandError(
                "Öffentliche Demo (DEMO_SANDBOX=true): Musterdaten entstehen je Besuch in einer eigenen "
                "Demo-Wache. load_demo_data würde gemeinsame Konten mit öffentlichem Passwort in der "
                "Wache der Installation anlegen."
            )
        if not demo_mode_enabled() and not options["force"]:
            raise CommandError(
                "Demo-Modus ist aus. Setze DEMO_MODE=true oder nutze --force für lokale Tests."
            )
        if options["force"] and not settings.DEBUG and not demo_mode_enabled():
            raise CommandError(
                "--force ohne DEMO_MODE ist nur mit DJANGO_DEBUG=true erlaubt."
            )

        result = load_demo_data(reset=options["reset"], force=options["force"] or options["reset"])
        if result.skipped:
            self.stdout.write(self.style.WARNING(
                f"Musterdaten bereits vorhanden für {result.station.name}. "
                "Konten/Passwörter wurden aktualisiert. Neu befüllen mit --reset."
            ))
        else:
            action = "zurückgesetzt und neu befüllt" if result.reset else "befüllt"
            self.stdout.write(self.style.SUCCESS(
                f"Demo-Wache {result.station.name} {action}: "
                f"{result.created_users} Konten neu, {result.created_handovers} Demo-Übergaben."
            ))

        self.stdout.write("")
        self.stdout.write(f"Gemeinsames Demo-Passwort: {demo_password()}")
        for account in demo_accounts_for_display():
            self.stdout.write(f"  {account['username']:16}  {account['label']}")
        self.stdout.write("")
        self.stdout.write("Nur für Test/Demo – nicht produktiv verwenden.")
