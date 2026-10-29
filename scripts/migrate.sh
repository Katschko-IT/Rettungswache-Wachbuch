#!/bin/sh
set -eu

python manage.py migrate --noinput
python manage.py bootstrap_project
python manage.py grant_database_access

# Öffentliche Demo (DEMO_SANDBOX=true): Musterdaten entstehen je Besuch in
# einer eigenen Demo-Wache. Gemeinsame Demo-Konten mit öffentlichem Passwort
# aus einer früheren lokalen Demo (load_demo_data) werden gesperrt.
# Sonst optional Musterdaten für lokale Demos (DEMO_MODE=true in .env).
case "${DEMO_SANDBOX:-false}" in
  1|true|TRUE|True|yes|YES|on|ON)
    python manage.py disable_shared_demo_accounts
    ;;
  *)
    case "${DEMO_MODE:-false}" in
      1|true|TRUE|True|yes|YES|on|ON) python manage.py load_demo_data ;;
    esac
    ;;
esac
