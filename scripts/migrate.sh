#!/bin/sh
set -eu

python manage.py migrate --noinput
python manage.py bootstrap_project
python manage.py grant_database_access

# Optional Musterdaten für lokale Demos oder die öffentliche Demo
# (DEMO_MODE=true oder DEMO_PUBLIC_MODE=true in .env).
demo_seed=0
case "${DEMO_MODE:-false}" in
  1|true|TRUE|yes|YES|on|ON) demo_seed=1 ;;
esac
case "${DEMO_PUBLIC_MODE:-false}" in
  1|true|TRUE|yes|YES|on|ON) demo_seed=1 ;;
esac
if [ "$demo_seed" = "1" ]; then
  python manage.py load_demo_data
fi
