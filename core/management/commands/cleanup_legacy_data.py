"""Einmalige Bereinigung der Altdaten (0.27). Ohne ``--apply`` nur Trockenlauf.

Details und Begründung: ``core/legacy_cleanup.py`` und docs/OPERATIONS.md,
Abschnitt „Einmalige Bereinigung der Altdaten (0.27)“.
"""
from __future__ import annotations

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from core import legacy_cleanup
from core.models import Membership

APPLY_COMMAND = "docker compose run --rm migrate python manage.py cleanup_legacy_data --apply --user BENUTZERNAME"


class Command(BaseCommand):
    help = (
        "Bereinigt einmalig Altdaten: frühere Einsatzphasen im Audit, IP-Adresse und Browser alter "
        "Lesebestätigungen, Desinfektionsbemerkungen aus der Zeit vor 0.26.1. Ohne --apply nur Trockenlauf."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Bereinigung ausführen (sonst nur zählen).")
        parser.add_argument("--user", default="", help="Benutzername der ausführenden Person (Pflicht mit --apply).")
        parser.add_argument("--station", default="", help="Nur diese Wache (Kürzel/Slug).")

    def handle(self, *args, **options):
        apply = options["apply"]
        actor = self._actor(options["user"].strip(), required=apply)
        stations, skipped = legacy_cleanup.stations_in_scope(actor, options["station"].strip())
        if options["station"].strip() and not stations and not skipped:
            raise CommandError("Diese Wache gibt es nicht.")

        if apply:
            missing = legacy_cleanup.missing_privileges()
            if missing:
                raise CommandError(
                    "Der Datenbank-Benutzer darf Audit-Einträge, Lesebestätigungen oder Desinfektionsprotokolle "
                    f"nicht ändern ({', '.join(missing)}). Bitte mit Eigentümerrechten ausführen: {APPLY_COMMAND}"
                )
            counts = legacy_cleanup.apply(actor, stations)
        else:
            self.stdout.write("Trockenlauf – es wird nichts geändert.")
            counts = legacy_cleanup.survey(stations)

        if legacy_cleanup.cutoff() is None:
            self.stdout.write("Hinweis: Migration 0067 ist nicht eingetragen; alte Desinfektionsbemerkungen bleiben.")
        for station in stations:
            found = counts[station.pk]
            self.stdout.write(f"{station.name} ({station.slug}):")
            self.stdout.write(f"  Audit-Einträge mit früheren Einsatzphasen, werden neutral: {found.vehicle_status_events}")
            self.stdout.write(f"  Audit-Einträge nur mit Wechsel der Einsatzphase, werden gelöscht: {found.mission_phase_events}")
            self.stdout.write(f"  Lesebestätigungen mit IP-Adresse oder Browser: {found.sop_receipts}")
            self.stdout.write(f"  Desinfektionsbemerkungen aus der Zeit vor 0.26.1: {found.disinfection_notes}")
        for station in skipped:
            self.stdout.write(f"{station.name} ({station.slug}): übersprungen – die Person ist dort nicht Master-Admin.")
        if not stations:
            self.stdout.write("Keine Wache zu bereinigen.")
            return

        if apply:
            self.stdout.write(self.style.SUCCESS(
                "Bereinigt. Protokoll im Audit jeder Wache: „Altdaten einmalig bereinigt“. "
                "Backups behalten den alten Stand bis zu ihrem Ablauf."
            ))
        else:
            self.stdout.write(f"Ausführen mit Eigentümerrechten: {APPLY_COMMAND}")

    def _actor(self, username: str, *, required: bool):
        if not username:
            if required:
                raise CommandError("Bitte mit --user die ausführende Person angeben.")
            return None
        user = User.objects.filter(username=username).first()
        if user is None or not user.is_active:
            raise CommandError("Diese Person gibt es nicht oder ihr Konto ist deaktiviert.")
        if not user.is_superuser and not Membership.objects.filter(
            user=user, role=Membership.Role.ADMIN, is_active=True,
        ).exists():
            raise CommandError("Ausführen dürfen nur Superuser oder Master-Admins einer Wache.")
        return user
