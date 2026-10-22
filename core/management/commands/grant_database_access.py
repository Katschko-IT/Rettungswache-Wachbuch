import os
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Vergibt minimale Laufzeitrechte nach den Migrationen."

    def handle(self, *args, **options):
        app_role = checked_role("APP_DB_USER")
        feed_role = checked_role("FEED_DB_USER")
        backup_role = checked_role("BACKUP_DB_USER")
        push_role = checked_role("PUSH_DB_USER", default="rwsth_push")
        owner = checked_role("POSTGRES_USER", default="rwsth_owner")
        database = checked_role("POSTGRES_DB", default="rwsth")
        statements = [
            f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC",
            f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC",
            f"GRANT CONNECT ON DATABASE {database} TO {app_role}, {feed_role}, {backup_role}, {push_role}",
            f"GRANT USAGE ON SCHEMA public TO {app_role}, {feed_role}, {backup_role}, {push_role}",
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {app_role}",
            f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {app_role}",
            f"REVOKE UPDATE, DELETE ON core_coffeeentry, core_auditevent, core_handoverrevision, "
            f"core_checklistcompletion FROM {app_role}",
            f"GRANT SELECT, UPDATE (last_success_at, last_error_at, last_error) ON core_feedsource TO {feed_role}",
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON core_feeditem TO {feed_role}",
            f"GRANT USAGE, SELECT ON SEQUENCE core_feeditem_id_seq TO {feed_role}",
            f"GRANT SELECT, UPDATE ON core_pushoutbox TO {push_role}",
            f"GRANT SELECT, DELETE ON core_pushsubscription TO {push_role}",
            f"GRANT SELECT, DELETE ON core_mobilepushdevice TO {push_role}",
            f"GRANT SELECT ON core_station TO {push_role}",
            f"GRANT INSERT ON core_auditevent TO {push_role}",
            f"GRANT USAGE, SELECT ON SEQUENCE core_auditevent_id_seq TO {push_role}",
            f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {backup_role}",
            f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {backup_role}",
            f"GRANT pg_read_all_data TO {backup_role}",
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {owner} IN SCHEMA public "
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {app_role}",
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {owner} IN SCHEMA public "
            f"GRANT USAGE, SELECT ON SEQUENCES TO {app_role}",
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {owner} IN SCHEMA public "
            f"GRANT SELECT ON TABLES TO {backup_role}",
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {owner} IN SCHEMA public "
            f"GRANT USAGE, SELECT ON SEQUENCES TO {backup_role}",
        ]
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        self.stdout.write(self.style.SUCCESS("Datenbank-Laufzeitrechte sind gesetzt."))


def checked_role(name, default=None):
    value = os.getenv(name, default or "")
    if not re.fullmatch(r"[a-z][a-z0-9_]*", value):
        raise CommandError(f"{name} ist kein erlaubter SQL-Bezeichner.")
    return value
