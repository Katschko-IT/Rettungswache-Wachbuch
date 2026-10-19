#!/bin/sh
set -eu

exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --threads 4 --timeout 60 --access-logfile - --error-logfile - \
  --logger-class core.gunicorn_logging.RedactingGunicornLogger
