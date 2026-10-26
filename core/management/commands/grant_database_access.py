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
        # Ältere Volumes wurden vor Einführung einzelner Rollen (z. B. rwsth_push)
        # initialisiert; init-db.sh läuft nur beim ersten Start. Fehlende Rollen
        # deshalb hier idempotent anlegen, sonst scheitern die GRANTs.
        role_passwords = (
            (app_role, "APP_DB_PASSWORD"),
            (feed_role, "FEED_DB_PASSWORD"),
            (backup_role, "BACKUP_DB_PASSWORD"),
            (push_role, "PUSH_DB_PASSWORD"),
        )
        statements = [
            ensure_role_statement(role, os.getenv(password_env, ""))
            for role, password_env in role_passwords
        ]
        statements += [
            f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC",
            f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC",
            f"GRANT CONNECT ON DATABASE {database} TO {app_role}, {feed_role}, {backup_role}, {push_role}",
            f"GRANT USAGE ON SCHEMA public TO {app_role}, {feed_role}, {backup_role}, {push_role}",
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {app_role}",
            f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {app_role}",
            f"REVOKE UPDATE, DELETE ON core_coffeeentry, core_coffeecashmovement, core_auditevent, "
            f"core_handoverrevision, core_checklistcompletion FROM {app_role}",
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


DOLLAR_TAG = "$rwsth_role$"


def sql_literal(value):
    """SQL-Stringliteral (standard_conforming_strings ist seit PG 9.1 Standard)."""
    if "\x00" in value:
        raise CommandError("Passwort enthält ein NUL-Zeichen.")
    return "'" + value.replace("'", "''") + "'"


def ensure_role_statement(role, password):
    """Legt eine fehlende Rolle an; bestehende Rollen und Passwörter bleiben unverändert.

    Ohne Passwort entsteht eine NOLOGIN-Rolle, damit die GRANTs gelingen; der
    zugehörige Dienst kann sich dann erst nach dem Setzen eines Passworts anmelden.
    """
    if DOLLAR_TAG in password:
        raise CommandError("Passwort enthält eine nicht erlaubte Zeichenfolge.")
    login = f"LOGIN PASSWORD {sql_literal(password)}" if password else "NOLOGIN"
    return (
        f"DO {DOLLAR_TAG} BEGIN "
        f"IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = {sql_literal(role)}) THEN "
        f"CREATE ROLE {role} {login}; "
        f"END IF; END {DOLLAR_TAG}"
    )


def checked_role(name, default=None):
    value = os.getenv(name, default or "")
    if not re.fullmatch(r"[a-z][a-z0-9_]*", value):
        raise CommandError(f"{name} ist kein erlaubter SQL-Bezeichner.")
    return value
