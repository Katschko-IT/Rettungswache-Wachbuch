from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import UNUSABLE_PASSWORD_PREFIX, make_password
from django.core.management.base import BaseCommand

from core.demo import DEMO_ACCOUNTS


class Command(BaseCommand):
    help = (
        "Sperrt die gemeinsamen Demo-Konten aus load_demo_data (demo-admin, demo-schicht, …): "
        "kein Login, kein Passwort. Daten und Mitgliedschaften bleiben erhalten. "
        "Läuft in der öffentlichen Demo (DEMO_SANDBOX=true) bei jedem Start (scripts/migrate.sh)."
    )

    def handle(self, *args, **options):
        # Nur die festen Namen: Konten der Demo-Wachen heißen demo-<token>-<rolle>.
        usernames = [account["username"] for account in DEMO_ACCOUNTS]
        open_accounts = get_user_model().objects.filter(username__in=usernames).exclude(
            is_active=False, password__startswith=UNUSABLE_PASSWORD_PREFIX
        )
        # Neuer Passwort-Hash beendet auch bestehende Sitzungen dieser Konten.
        count = open_accounts.update(is_active=False, password=make_password(None))
        if count:
            self.stdout.write(self.style.WARNING(
                f"{count} gemeinsame Demo-Konten gesperrt (öffentliches Passwort, öffentliche Demo)."
            ))
