#!/bin/sh
# Legt beim ersten Start der Datenbank die Laufzeitrollen an
# (docker-entrypoint-initdb.d, läuft nur bei leerem Datenverzeichnis).
# Fehlende Rollen auf älteren Volumes ergänzt grant_database_access.
# Ohne Passwort entsteht eine NOLOGIN-Rolle (Dienst kann sich nicht anmelden).
set -eu

psql -v ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --set=app_user="$APP_DB_USER" \
    --set=app_password="$APP_DB_PASSWORD" \
    --set=feed_user="$FEED_DB_USER" \
    --set=feed_password="$FEED_DB_PASSWORD" \
    --set=backup_user="$BACKUP_DB_USER" \
    --set=backup_password="$BACKUP_DB_PASSWORD" \
    --set=push_user="${PUSH_DB_USER:-rwsth_push}" \
    --set=push_password="${PUSH_DB_PASSWORD:-}" <<'SQL'
SELECT CASE WHEN r.password = ''
            THEN format('CREATE ROLE %I NOLOGIN', r.name)
            ELSE format('CREATE ROLE %I LOGIN PASSWORD %L', r.name, r.password)
       END
FROM (VALUES (:'app_user', :'app_password'),
             (:'feed_user', :'feed_password'),
             (:'backup_user', :'backup_password'),
             (:'push_user', :'push_password')) AS r(name, password)
WHERE NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = r.name) \gexec
SQL
