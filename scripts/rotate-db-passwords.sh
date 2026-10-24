#!/bin/sh
# Rotate PostgreSQL app/feed/backup/push role passwords for an existing stack.
# Run on the host with docker compose available. Owner credentials stay in .env
# until you intentionally rotate POSTGRES_PASSWORD via a dump/restore cycle.
set -eu

# Im Repository-Checkout: Elternordner von scripts/. Bei einer install.sh-
# Installation: WACHBUCH_DIR=/opt/wachbuch scripts/rotate-db-passwords.sh
ROOT_DIR=${WACHBUCH_DIR:-$(CDPATH='' cd -- "$(dirname "$0")/.." && pwd)}
cd "$ROOT_DIR"

if [ ! -f .env ]; then
  echo "Missing .env – copy .env.example and set secrets first." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
. ./.env
set +a

: "${POSTGRES_DB:?}"
: "${POSTGRES_USER:?}"
: "${APP_DB_USER:?}"
: "${FEED_DB_USER:?}"
: "${BACKUP_DB_USER:?}"
: "${PUSH_DB_USER:?}"

NEW_APP=$(openssl rand -hex 24)
NEW_FEED=$(openssl rand -hex 24)
NEW_BACKUP=$(openssl rand -hex 24)
NEW_PUSH=$(openssl rand -hex 24)

echo "Rotating passwords for ${APP_DB_USER}, ${FEED_DB_USER}, ${BACKUP_DB_USER} and ${PUSH_DB_USER} ..."
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --set=app_user="$APP_DB_USER" \
  --set=app_password="$NEW_APP" \
  --set=feed_user="$FEED_DB_USER" \
  --set=feed_password="$NEW_FEED" \
  --set=backup_user="$BACKUP_DB_USER" \
  --set=backup_password="$NEW_BACKUP" \
  --set=push_user="$PUSH_DB_USER" \
  --set=push_password="$NEW_PUSH" <<'SQL'
SELECT format('ALTER ROLE %I WITH PASSWORD %L', :'app_user', :'app_password') \gexec
SELECT format('ALTER ROLE %I WITH PASSWORD %L', :'feed_user', :'feed_password') \gexec
SELECT format('ALTER ROLE %I WITH PASSWORD %L', :'backup_user', :'backup_password') \gexec
SELECT format('ALTER ROLE %I WITH PASSWORD %L', :'push_user', :'push_password') \gexec
SQL

TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT
awk -v app="$NEW_APP" -v feed="$NEW_FEED" -v backup="$NEW_BACKUP" -v push="$NEW_PUSH" '
  BEGIN { updated_app=0; updated_feed=0; updated_backup=0; updated_push=0 }
  /^APP_DB_PASSWORD=/ { print "APP_DB_PASSWORD=" app; updated_app=1; next }
  /^FEED_DB_PASSWORD=/ { print "FEED_DB_PASSWORD=" feed; updated_feed=1; next }
  /^BACKUP_DB_PASSWORD=/ { print "BACKUP_DB_PASSWORD=" backup; updated_backup=1; next }
  /^PUSH_DB_PASSWORD=/ { print "PUSH_DB_PASSWORD=" push; updated_push=1; next }
  { print }
  END {
    if (!updated_app) print "APP_DB_PASSWORD=" app
    if (!updated_feed) print "FEED_DB_PASSWORD=" feed
    if (!updated_backup) print "BACKUP_DB_PASSWORD=" backup
    if (!updated_push) print "PUSH_DB_PASSWORD=" push
  }
' .env > "$TMP"
cp "$TMP" .env

echo "Updated .env. Restarting web, notify-worker, feed-worker, backup and push-worker ..."
docker compose up -d --force-recreate web notify-worker feed-worker backup push-worker
echo "Done. Verify /healthz/ and worker logs."
