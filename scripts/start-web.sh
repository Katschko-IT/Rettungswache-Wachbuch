#!/bin/sh
# Startet Gunicorn mit config/gunicorn.py. Worker, Threads und Timeout kommen
# aus GUNICORN_WORKERS/GUNICORN_THREADS/GUNICORN_TIMEOUT (Standard 2/4/60).
set -eu

exec gunicorn --config /app/config/gunicorn.py config.wsgi:application
