#!/bin/sh
# Wachwerk-Überwachung für einen Server im Internet (docs/HETZNER.md).
# Läuft als root per systemd-Timer alle 5 Minuten (harden-host.sh) und prüft:
#   - https://<WACHBUCH_HOSTNAME>/healthz/ über Caddy antwortet mit 200
#   - das TLS-Zertifikat gilt noch mindestens CERT_MIN_DAYS Tage
#   - kein Container ist "unhealthy", startet ständig neu oder fehlt
#   - das neueste Backup ist jünger als BACKUP_MAX_AGE_HOURS
#   - die Systemplatte ist zu weniger als DISK_MAX_PERCENT belegt
# Alles gut: Aufruf von PING_URL. Fehler: PING_URL/fail mit den Gründen.
# Bleibt der Ping ganz aus (Server aus, Netz weg), meldet der Dienst hinter
# PING_URL (z. B. healthchecks.io) das ebenfalls.
#
#   wachwerk-health            still, Exit 1 bei Fehlern (Journal)
#   wachwerk-health --verbose  jede Prüfung anzeigen
#   wachwerk-health --test     Fehlermeldung probeweise auslösen
set -u

WACHWERK_DIR="${WACHWERK_DIR:-/opt/wachbuch}"
PING_URL="${PING_URL:-}"
CERT_MIN_DAYS="${CERT_MIN_DAYS:-14}"
DISK_MAX_PERCENT="${DISK_MAX_PERCENT:-85}"
BACKUP_MAX_AGE_HOURS="${BACKUP_MAX_AGE_HOURS:-30}"
VERBOSE=0
TEST=0
case "${1:-}" in
    --verbose|-v) VERBOSE=1 ;;
    --test) VERBOSE=1; TEST=1 ;;
    '') ;;
    *) echo "Aufruf: wachwerk-health [--verbose|--test]" >&2; exit 2 ;;
esac

PROBLEMS=""
ok() { [ "$VERBOSE" -eq 0 ] || printf 'OK      %s\n' "$*"; }
bad() {
    printf 'FEHLER  %s\n' "$*" >&2
    PROBLEMS="${PROBLEMS}- $*
"
}

env_get() {
    [ -r "$WACHWERK_DIR/.env" ] || return 0
    sed -n "s/^$1=//p" "$WACHWERK_DIR/.env" | tail -n 1 | sed "s/^['\"]//; s/['\"]\$//"
}

HOST=$(env_get WACHBUCH_HOSTNAME)
HTTPS_PORT=$(env_get HTTPS_PORT)
HTTPS_PORT="${HTTPS_PORT:-443}"
PROJECT=$(env_get COMPOSE_PROJECT_NAME)
PROJECT="${PROJECT:-rettungswache-wachbuch}"

# 1. Erreichbarkeit über Caddy (lokal aufgelöst, damit DNS-Hairpinning egal ist)
if [ -n "${HEALTH_URL:-}" ]; then
    if curl -fsS --max-time 15 -o /dev/null "$HEALTH_URL"; then
        ok "$HEALTH_URL"
    else
        bad "$HEALTH_URL antwortet nicht mit 200"
    fi
elif [ -n "$HOST" ] && [ "$HOST" != "localhost" ]; then
    url="https://$HOST:$HTTPS_PORT/healthz/"
    if curl -fsS --max-time 15 -o /dev/null --resolve "$HOST:$HTTPS_PORT:127.0.0.1" "$url"; then
        ok "$url"
    else
        bad "$url antwortet nicht mit 200 (wachbuch logs caddy / web)"
    fi
else
    bad "WACHBUCH_HOSTNAME fehlt in $WACHWERK_DIR/.env (oder HEALTH_URL in /etc/wachwerk/health.env setzen)"
fi

# 2. Zertifikat
if [ -n "$HOST" ] && [ "$HOST" != "localhost" ] && command -v openssl >/dev/null 2>&1; then
    end=$(echo | openssl s_client -connect "127.0.0.1:$HTTPS_PORT" -servername "$HOST" 2>/dev/null \
        | openssl x509 -noout -enddate 2>/dev/null | sed 's/^notAfter=//')
    if [ -z "$end" ]; then
        bad "TLS-Zertifikat für $HOST nicht lesbar"
    else
        end_s=$(date -d "$end" +%s 2>/dev/null || echo 0)
        days=$(( (end_s - $(date +%s)) / 86400 ))
        if [ "$days" -lt "$CERT_MIN_DAYS" ]; then
            bad "TLS-Zertifikat läuft in $days Tagen ab (Caddy erneuert sonst ab 30 Tagen; wachbuch logs caddy)"
        else
            ok "Zertifikat gilt noch $days Tage"
        fi
    fi
fi

# 3. Container
if command -v docker >/dev/null 2>&1; then
    states=$(docker ps -a --filter "label=com.docker.compose.project=$PROJECT" \
        --filter "label=com.docker.compose.oneoff=False" \
        --format '{{.Label "com.docker.compose.service"}} {{.State}} {{.Status}}' 2>/dev/null)
    if [ -z "$states" ]; then
        bad "keine Container des Projekts $PROJECT gefunden (wachbuch start)"
    else
        services="db web caddy backup"
        [ "$(env_get DEMO_SANDBOX)" != "true" ] || services="$services demo-cleaner"
        for service in $services; do
            line=$(printf '%s\n' "$states" | awk -v s="$service" '$1 == s' | head -n 1)
            case "$line" in
                '') bad "Dienst $service fehlt" ;;
                *"(unhealthy)"*) bad "Dienst $service ist unhealthy" ;;
                *" running "*) ok "Dienst $service läuft" ;;
                *) bad "Dienst $service: ${line#* }" ;;
            esac
        done
        restarting=$(printf '%s\n' "$states" | awk '$2 == "restarting" { print $1 }' | tr '\n' ' ')
        [ -z "$restarting" ] || bad "startet ständig neu: $restarting"
        unhealthy=$(printf '%s\n' "$states" | awk '/\(unhealthy\)/ { print $1 }' | tr '\n' ' ')
        [ -z "$unhealthy" ] || bad "unhealthy: $unhealthy"
    fi

    # 4. Backup-Alter
    mount=$(docker volume inspect -f '{{.Mountpoint}}' "${PROJECT}_backups-data" 2>/dev/null || true)
    if [ -n "$mount" ] && [ -d "$mount" ]; then
        newest=$(find "$mount" -maxdepth 1 -type f -name 'rwsth-*.dump' -printf '%T@ %f\n' 2>/dev/null \
            | sort -n | tail -n 1)
        if [ -z "$newest" ]; then
            bad "noch kein Backup vorhanden (wachbuch backup)"
        else
            age_h=$(( ($(date +%s) - ${newest%%.*}) / 3600 ))
            if [ "$age_h" -ge "$BACKUP_MAX_AGE_HOURS" ]; then
                bad "neuestes Backup ist $age_h Stunden alt (wachbuch logs backup)"
            else
                ok "neuestes Backup: ${newest#* } ($age_h h alt)"
            fi
        fi
    else
        bad "Backup-Volume ${PROJECT}_backups-data nicht gefunden"
    fi
else
    bad "docker fehlt"
fi

# 4b. Offsite-Kopie (offsite-storagebox.sh)
if [ -r /etc/wachwerk/offsite.env ]; then
    marker=/var/lib/wachwerk/offsite-sync.ok
    if [ ! -f "$marker" ]; then
        bad "Offsite-Kopie lief noch nie erfolgreich (journalctl -u wachwerk-offsite)"
    else
        age_h=$(( ($(date +%s) - $(stat -c %Y "$marker")) / 3600 ))
        if [ "$age_h" -ge 3 ]; then
            bad "letzte erfolgreiche Offsite-Kopie vor $age_h Stunden (journalctl -u wachwerk-offsite)"
        else
            ok "Offsite-Kopie vor $age_h h"
        fi
    fi
fi

# 5. Platz
used=$(df -P / | awk 'NR == 2 { gsub("%", "", $5); print $5 }')
if [ "${used:-0}" -ge "$DISK_MAX_PERCENT" ]; then
    bad "Systemplatte zu ${used} % belegt (docker system prune, alte Backups prüfen)"
else
    ok "Systemplatte zu ${used} % belegt"
fi

[ "$TEST" -eq 0 ] || bad "Testmeldung von wachwerk-health --test"

host_label=$(hostname)
if [ -z "$PROBLEMS" ]; then
    [ -z "$PING_URL" ] || curl -fsS --max-time 10 --retry 3 -o /dev/null "$PING_URL" || true
    exit 0
fi
if [ -n "$PING_URL" ]; then
    printf 'Wachwerk auf %s:\n%s' "$host_label" "$PROBLEMS" \
        | curl -fsS --max-time 10 --retry 3 -o /dev/null --data-binary @- "$PING_URL/fail" || true
fi
exit 1
