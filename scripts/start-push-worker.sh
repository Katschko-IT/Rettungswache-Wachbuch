#!/bin/sh
# Push-Postausgang (Dienst push-worker). push_worker erneuert nach jedem
# erfolgreichen Durchlauf die Lebenszeichen-Datei in /tmp; der Compose-
# Healthcheck prüft ihr Alter. Erreicht der Worker die Datenbank nicht, bleibt
# sie alt und der Dienst wird "unhealthy". exec, damit SIGTERM ankommt.
set -eu

exec python manage.py push_worker --watch \
    --interval "${PUSH_WORKER_INTERVAL:-15}" \
    --batch-size "${PUSH_WORKER_BATCH:-25}" \
    --heartbeat-file "${PUSH_HEARTBEAT_FILE:-/tmp/push_worker.alive}"
