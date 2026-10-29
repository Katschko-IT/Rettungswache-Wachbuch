#!/bin/sh
# Wachwerk-Überwachung für einen Server im Internet (docs/HETZNER.md).
# Läuft als root per systemd-Timer alle 5 Minuten (harden-host.sh) und prüft:
#   - https://<WACHBUCH_HOSTNAME>/healthz/ über Caddy antwortet mit 200
#   - das TLS-Zertifikat gilt noch mindestens CERT_MIN_DAYS Tage
#   - alle Dauerdienste laufen (db, redis, web, Worker, backup und je nach
#     Profil caddy, demo-cleaner, signal); keiner ist "unhealthy" oder startet
#     ständig neu
#   - höchstens ERRORS_MAX_15MIN Serverfehler (5xx) in 15 Minuten
#   - das neueste Backup ist jünger als BACKUP_MAX_AGE_HOURS, ebenso die neueste
#     verschlüsselte Offsite-Kopie (offsite-storagebox.sh)
#   - das letzte automatische Update (wachbuch auto-update) ist gelungen
#   - die wöchentliche Wiederherstellungsprobe ist gelungen
#   - die Systemplatte ist zu weniger als DISK_MAX_PERCENT belegt
# Einen "unhealthy" Container (außer db) startet die Prüfung selbst neu,
# höchstens dreimal je Stunde (AUTO_RESTART=false schaltet das ab). Docker
# startet nur beendete Container neu, nie "unhealthy".
# Alles gut: Aufruf von PING_URL. Fehler: PING_URL/fail mit den Gründen, sobald
# sie FAILS_BEFORE_ALERT Läufe in Folge bestehen (übersteht Neustarts und kurze
# Aussetzer). Bleibt der Ping ganz aus (Server aus, Netz weg), meldet der Dienst
# hinter PING_URL (z. B. healthchecks.io) das ebenfalls.
# Vor der Installation (keine .env) wird nichts geprüft und nichts gemeldet;
# während eines automatischen Updates entfallen Erreichbarkeit und Container.
#
#   wachwerk-health                 still, Exit 1 bei Fehlern (Journal)
#   wachwerk-health --verbose       jede Prüfung anzeigen
#   wachwerk-health --test          Fehlermeldung sofort probeweise senden
#   wachwerk-health --restore-test  Wiederherstellungsprobe (wöchentlicher Timer)
set -u

CONF_DIR="${WACHWERK_CONF_DIR:-/etc/wachwerk}"
STATE_DIR="${WACHWERK_STATE_DIR:-/var/lib/wachwerk}"

# Einstellungen aus health.env lesen, auch beim Aufruf per sudo (sudo leert die
# Umgebung, systemd setzt sie per EnvironmentFile). Gesetzte Variablen gewinnen.
load_settings() {
    [ -r "$1" ] || return 0
    while IFS= read -r line || [ -n "$line" ]; do
        key=${line%%=*}
        [ "$key" != "$line" ] || continue
        case "$key" in
            WACHWERK_DIR|PING_URL|HEALTH_URL|CERT_MIN_DAYS|DISK_MAX_PERCENT|BACKUP_MAX_AGE_HOURS|\
            ERRORS_MAX_15MIN|FAILS_BEFORE_ALERT|AUTO_RESTART) ;;
            *) continue ;;
        esac
        eval "is_set=\${$key+x}"
        [ -z "$is_set" ] || continue
        value=${line#*=}
        case "$value" in
            \"*\") value=${value#\"}; value=${value%\"} ;;
            \'*\') value=${value#\'}; value=${value%\'} ;;
        esac
        eval "$key=\$value"
    done <"$1"
}
load_settings "$CONF_DIR/health.env"

WACHWERK_DIR="${WACHWERK_DIR:-/opt/wachbuch}"
PING_URL="${PING_URL:-}"
CERT_MIN_DAYS="${CERT_MIN_DAYS:-14}"
DISK_MAX_PERCENT="${DISK_MAX_PERCENT:-85}"
BACKUP_MAX_AGE_HOURS="${BACKUP_MAX_AGE_HOURS:-30}"
ERRORS_MAX_15MIN="${ERRORS_MAX_15MIN:-5}"
FAILS_BEFORE_ALERT="${FAILS_BEFORE_ALERT:-2}"
AUTO_RESTART="${AUTO_RESTART:-true}"
# Ein Update mit Backup, Pull und zwei Starts à 10 Minuten dauert keine Stunde.
AUTO_UPDATE_MAX_MINUTES=60
# Der Update-Timer läuft täglich; zwei ausgefallene Läufe sind ein Fehler.
AUTO_UPDATE_MAX_AGE_HOURS=50
# Kein Aufruf darf die Prüfung anhalten (systemd begrenzt den Lauf zusätzlich).
CMD_TIMEOUT="${HEALTH_CMD_TIMEOUT:-30}"
case "$FAILS_BEFORE_ALERT" in ''|*[!0-9]*) FAILS_BEFORE_ALERT=2 ;; 0) FAILS_BEFORE_ALERT=1 ;; esac
case "$ERRORS_MAX_15MIN" in ''|*[!0-9]*) ERRORS_MAX_15MIN=5 ;; esac

VERBOSE=0
TEST=0
MODE=check
case "${1:-}" in
    --verbose|-v) VERBOSE=1 ;;
    --test) VERBOSE=1; TEST=1 ;;
    --restore-test) MODE=restore-test ;;
    '') ;;
    *) echo "Aufruf: wachwerk-health [--verbose|--test|--restore-test]" >&2; exit 2 ;;
esac

INSTALLED=1
if [ ! -e "$WACHWERK_DIR/.env" ]; then
    if [ "$TEST" -eq 0 ]; then
        # Kein Ping: der Check bei healthchecks.io bleibt "new" statt "down".
        if [ "$VERBOSE" -eq 1 ] || [ "$MODE" != check ]; then
            echo "Wachwerk ist in $WACHWERK_DIR noch nicht installiert – nichts zu prüfen."
        fi
        exit 0
    fi
    INSTALLED=0
elif [ ! -r "$WACHWERK_DIR/.env" ]; then
    echo "$WACHWERK_DIR/.env ist nicht lesbar – bitte mit sudo aufrufen." >&2
    exit 2
fi
install -d -m 0700 "$STATE_DIR" 2>/dev/null || true

PROBLEMS=""
NOTES=""
ok() { [ "$VERBOSE" -eq 0 ] || printf 'OK      %s\n' "$*"; }
bad() {
    printf 'FEHLER  %s\n' "$*" >&2
    PROBLEMS="${PROBLEMS}- $*
"
}
note() {
    printf 'AKTION  %s\n' "$*"
    NOTES="${NOTES}- $*
"
}
t() { timeout "$CMD_TIMEOUT" "$@"; }

env_get() {
    [ -r "$WACHWERK_DIR/.env" ] || return 0
    sed -n "s/^$1=//p" "$WACHWERK_DIR/.env" | tail -n 1 | sed "s/^['\"]//; s/['\"]\$//"
}

# Wiederherstellungsprobe: neuestes Backup in eine Testdatenbank einspielen,
# Tabellen zählen, Testdatenbank löschen (scripts/restore-test.sh). Das
# Ergebnis liest die regelmäßige Prüfung aus restore-test.status.
if [ "$MODE" = restore-test ]; then
    if [ -d "$WACHWERK_DIR/logs/auto-update.lock" ]; then
        echo "Automatisches Update läuft – Wiederherstellungsprobe entfällt diesmal."
        exit 0
    fi
    if output=$(cd "$WACHWERK_DIR" && timeout 1800 docker compose run --rm -T restore-test 2>&1); then
        printf '%s\n' "$output" | tail -n 3
        echo ok >"$STATE_DIR/restore-test.status"
        exit 0
    fi
    printf '%s\n' "$output" | tail -n 20 >&2
    printf 'fehlgeschlagen: %s\n' "$(printf '%s\n' "$output" | grep -v '^[[:space:]]*$' | tail -n 1)" \
        >"$STATE_DIR/restore-test.status"
    exit 1
fi

HOST=$(env_get WACHBUCH_HOSTNAME)
HTTPS_PORT=$(env_get HTTPS_PORT)
HTTPS_PORT="${HTTPS_PORT:-443}"
PROJECT=$(env_get COMPOSE_PROJECT_NAME)
PROJECT="${PROJECT:-rettungswache-wachbuch}"
PROFILES=",$(env_get COMPOSE_PROFILES | tr -d ' '),"
has_profile() { case "$PROFILES" in *",$1,"*) return 0 ;; esac; return 1; }
CONTAINERS=""
UPDATE_RUNNING=0

# 0. Läuft gerade ein automatisches Update (scripts/wachbuch, Sperrordner)?
check_update_lock() {
    lock="$WACHWERK_DIR/logs/auto-update.lock"
    [ -d "$lock" ] || return 0
    if [ -n "$(find "$lock" -maxdepth 0 -mmin +"$AUTO_UPDATE_MAX_MINUTES" 2>/dev/null)" ]; then
        bad "Sperre des automatischen Updates besteht seit über $AUTO_UPDATE_MAX_MINUTES Minuten – Update hängt oder wurde unterbrochen (wachbuch auto-update status)"
    else
        UPDATE_RUNNING=1
        echo "Hinweis: automatisches Update läuft – Erreichbarkeit, Zertifikat und Container werden diesmal nicht geprüft."
    fi
}

# 1. Erreichbarkeit über Caddy (lokal aufgelöst, damit DNS-Hairpinning egal ist)
check_reachability() {
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
        bad "WACHBUCH_HOSTNAME fehlt in $WACHWERK_DIR/.env (oder HEALTH_URL in $CONF_DIR/health.env setzen)"
    fi
}

# 2. Zertifikat
check_certificate() {
    [ -n "$HOST" ] && [ "$HOST" != "localhost" ] && command -v openssl >/dev/null 2>&1 || return 0
    end=$(t openssl s_client -connect "127.0.0.1:$HTTPS_PORT" -servername "$HOST" </dev/null 2>/dev/null \
        | openssl x509 -noout -enddate 2>/dev/null | sed 's/^notAfter=//')
    if [ -z "$end" ]; then
        bad "TLS-Zertifikat für $HOST nicht lesbar"
        return
    fi
    end_s=$(date -d "$end" +%s 2>/dev/null || echo 0)
    days=$(( (end_s - $(date +%s)) / 86400 ))
    if [ "$days" -lt "$CERT_MIN_DAYS" ]; then
        bad "TLS-Zertifikat läuft in $days Tagen ab (Caddy erneuert sonst ab 30 Tagen; wachbuch logs caddy)"
    else
        ok "Zertifikat gilt noch $days Tage"
    fi
}

# Unhealthy-Container neu starten, höchstens dreimal je Stunde und Dienst.
heal() {  # $1 Dienst, $2 Container-ID
    if [ "$AUTO_RESTART" != true ] || [ "$1" = db ]; then
        bad "Dienst $1 ist unhealthy (wachbuch logs $1)"
        return
    fi
    restarts="$STATE_DIR/restarts"
    now=$(date +%s)
    count=$(awk -v s="$1" -v now="$now" '$2 == s && now - $1 < 3600 { n++ } END { print n + 0 }' \
        "$restarts" 2>/dev/null || echo 0)
    if [ "$count" -ge 3 ]; then
        bad "Dienst $1 bleibt unhealthy, schon $count Neustarts in der letzten Stunde (wachbuch logs $1)"
    elif timeout 120 docker restart -t 30 "$2" >/dev/null 2>&1; then
        printf '%s %s\n' "$now" "$1" >>"$restarts" 2>/dev/null || true
        note "Dienst $1 war unhealthy und wurde neu gestartet ($((count + 1)). Neustart in einer Stunde)"
    else
        bad "Dienst $1 ist unhealthy, Neustart fehlgeschlagen (wachbuch logs $1)"
    fi
}

# 3. Container
check_containers() {
    ids=$(t docker ps -a -q --no-trunc --filter "label=com.docker.compose.project=$PROJECT" \
        --filter "label=com.docker.compose.oneoff=False" 2>/dev/null)
    if [ -z "$ids" ]; then
        bad "keine Container des Projekts $PROJECT gefunden (wachbuch start)"
        return
    fi
    # Je Container eine Zeile: Dienst Neustartregel Zustand Gesundheit ID
    # shellcheck disable=SC2086 # jede ID ein eigenes Argument
    CONTAINERS=$(t docker inspect --format '{{index .Config.Labels "com.docker.compose.service"}} {{.HostConfig.RestartPolicy.Name}} {{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}-{{end}} {{.Id}}' $ids 2>/dev/null)
    if [ -z "$CONTAINERS" ]; then
        bad "Zustand der Container nicht lesbar (docker inspect)"
        return
    fi
    services="db redis web feed-worker notify-worker push-worker housekeeping backup"
    if has_profile https; then services="$services caddy"; fi
    if has_profile demo || [ "$(env_get DEMO_SANDBOX)" = "true" ]; then services="$services demo-cleaner"; fi
    if has_profile signal; then services="$services signal"; fi
    for service in $services; do
        # Bei mehreren Containern (Neuanlage) zählt der beste Zustand.
        state=$(printf '%s\n' "$CONTAINERS" | awk -v s="$service" '
            $1 == s {
                st = $3
                if (st == "running" && $4 == "unhealthy") st = "unhealthy"
                rank = (st == "running") ? 3 : (st == "unhealthy" || st == "restarting") ? 2 : 1
                if (rank > best) { best = rank; result = st }
            }
            END { print result }')
        case "$state" in
            running) ok "Dienst $service läuft" ;;
            unhealthy|restarting) ;;  # unten gemeldet
            '') bad "Dienst $service fehlt (wachbuch start)" ;;
            *) bad "Dienst $service: $state (wachbuch logs $service)" ;;
        esac
    done
    # Alle Dauerdienste, auch solche, die hier nicht aufgezählt sind.
    restarting=$(printf '%s\n' "$CONTAINERS" | awk '$3 == "restarting" { print $1 }' | sort -u | tr '\n' ' ')
    [ -z "$restarting" ] || bad "startet ständig neu: ${restarting% } (wachbuch logs <dienst>)"
    if [ -f "$STATE_DIR/restarts" ]; then
        now=$(date +%s)
        awk -v now="$now" 'now - $1 < 3600' "$STATE_DIR/restarts" >"$STATE_DIR/restarts.tmp" 2>/dev/null \
            && mv "$STATE_DIR/restarts.tmp" "$STATE_DIR/restarts"
    fi
    unhealthy=$(printf '%s\n' "$CONTAINERS" | awk '$3 == "running" && $4 == "unhealthy" { print $1, $5 }')
    while read -r service id; do
        [ -n "$service" ] || continue
        heal "$service" "$id"
    done <<EOF
$unhealthy
EOF
}

# 3b. Serverfehler: Anzahl der ErrorEvent-Zeilen (nur Zählung, keine Inhalte)
check_server_errors() {
    [ "$ERRORS_MAX_15MIN" -gt 0 ] || return 0
    db_id=$(printf '%s\n' "$CONTAINERS" | awk '$1 == "db" && $3 == "running" { print $5; exit }')
    [ -n "$db_id" ] || return 0
    # shellcheck disable=SC2016 # $POSTGRES_* wertet die Shell im Container aus
    errors=$(t docker exec "$db_id" sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAXc "SELECT count(*) FROM core_errorevent WHERE occurred_at > now() - interval '\''15 minutes'\''"' \
        2>/dev/null | tr -dc '0-9')
    [ -n "$errors" ] || return 0
    if [ "$errors" -ge "$ERRORS_MAX_15MIN" ]; then
        bad "$errors Serverfehler (5xx) in den letzten 15 Minuten (wachbuch logs web)"
    else
        ok "$errors Serverfehler (5xx) in den letzten 15 Minuten"
    fi
}

# 4. Backup-Alter
check_backup() {
    mount=$(t docker volume inspect -f '{{.Mountpoint}}' "${PROJECT}_backups-data" 2>/dev/null || true)
    if [ -z "$mount" ] || [ ! -d "$mount" ]; then
        bad "Backup-Volume ${PROJECT}_backups-data nicht gefunden"
        return
    fi
    newest=$(find "$mount" -maxdepth 1 -type f -name 'rwsth-*.dump' -printf '%T@ %f\n' 2>/dev/null \
        | sort -n | tail -n 1)
    if [ -z "$newest" ]; then
        bad "noch kein Backup vorhanden (wachbuch backup)"
        return
    fi
    age_h=$(( ($(date +%s) - ${newest%%.*}) / 3600 ))
    if [ "$age_h" -ge "$BACKUP_MAX_AGE_HOURS" ]; then
        bad "neuestes Backup ist $age_h Stunden alt (wachbuch logs backup)"
    else
        ok "neuestes Backup: ${newest#* } ($age_h h alt)"
    fi
}

# 4b. Offsite-Kopie (offsite-storagebox.sh): Kopie gelungen UND frisch
# verschlüsselt. Der Sync allein ist auch "erfolgreich", wenn seit Tagen keine
# neue Datei mehr entsteht (z. B. Schlüssel fehlt im Backup-Dienst).
check_offsite() {
    [ -r "$CONF_DIR/offsite.env" ] || return 0
    marker="$STATE_DIR/offsite-sync.ok"
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
    offsite_dir=$(sed -n 's/^OFFSITE_DIR=//p' "$CONF_DIR/offsite.env" | tail -n 1)
    offsite_dir="${offsite_dir:-/var/lib/wachwerk-offsite}"
    newest=$(find "$offsite_dir" -maxdepth 1 -type f -name 'rwsth-*.dump.gpg' -printf '%T@ %f\n' 2>/dev/null \
        | sort -n | tail -n 1)
    if [ -z "$newest" ]; then
        bad "keine verschlüsselte Kopie in $offsite_dir (wachbuch logs backup)"
        return
    fi
    age_h=$(( ($(date +%s) - ${newest%%.*}) / 3600 ))
    if [ "$age_h" -ge "$BACKUP_MAX_AGE_HOURS" ]; then
        bad "neueste verschlüsselte Kopie ist $age_h Stunden alt – Verschlüsselung gescheitert? (wachbuch logs backup)"
    else
        ok "neueste verschlüsselte Kopie: ${newest#* } ($age_h h alt)"
    fi
}

# 4c. Wiederherstellungsprobe (wachwerk-restore-test.timer, wöchentlich)
check_restore_test() {
    status_file="$STATE_DIR/restore-test.status"
    [ -f "$status_file" ] || return 0
    status=$(head -n 1 "$status_file")
    age_d=$(( ($(date +%s) - $(stat -c %Y "$status_file")) / 86400 ))
    case "$status" in
        ok)
            if [ "$age_d" -ge 8 ]; then
                bad "letzte Wiederherstellungsprobe vor $age_d Tagen (systemctl list-timers wachwerk-restore-test.timer)"
            else
                ok "Wiederherstellungsprobe vor $age_d Tagen gelungen"
            fi
            ;;
        *) bad "Wiederherstellungsprobe $status (journalctl -u wachwerk-restore-test)" ;;
    esac
}

# 5. Automatische Updates: letzte Zeile mit Zeitstempel in logs/auto-update.log
# (scripts/wachbuch, auto_log). Alles außer Erfolg, "Übersprungen" und dem
# Hinweis auf eine neue Hauptversion ist ein Fehlschlag, ein Rollback oder ein
# abgebrochener Lauf. core/test_hetzner_scripts.py prüft das gegen die Texte
# in scripts/wachbuch.
check_auto_update() {
    case "$(env_get WACHBUCH_AUTO_UPDATE)" in
        sicherheit|alle) ;;
        *) return 0 ;;
    esac
    last=$(grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} ' \
        "$WACHWERK_DIR/logs/auto-update.log" 2>/dev/null | tail -n 1)
    if [ -z "$last" ]; then
        if [ -n "$(find "$WACHWERK_DIR/.env" -mmin +$((AUTO_UPDATE_MAX_AGE_HOURS * 60)) 2>/dev/null)" ]; then
            bad "automatisches Update lief noch nie (wachbuch auto-update status)"
        else
            ok "automatisches Update: noch kein Lauf"
        fi
        return
    fi
    stamp=$(printf '%s\n' "$last" | cut -c1-19)
    message=$(printf '%s\n' "$last" | cut -c21-)
    case "$message" in
        "Update erfolgreich"*|"Alles aktuell"*|"Übersprungen"*|"Neue Hauptversion"*)
            ok "automatisches Update ($stamp): $message" ;;
        *)
            [ "$UPDATE_RUNNING" -eq 1 ] \
                || bad "automatisches Update ($stamp): $message (wachbuch auto-update status)" ;;
    esac
    run_s=$(date -d "$stamp" +%s 2>/dev/null || echo 0)
    age_h=$(( ($(date +%s) - run_s) / 3600 ))
    if [ "$UPDATE_RUNNING" -eq 0 ] && [ "$age_h" -ge "$AUTO_UPDATE_MAX_AGE_HOURS" ]; then
        bad "automatisches Update lief zuletzt vor $age_h Stunden (wachbuch auto-update status)"
    fi
}

# 6. Platz
check_disk() {
    used=$(df -P / | awk 'NR == 2 { gsub("%", "", $5); print $5 }')
    if [ "${used:-0}" -ge "$DISK_MAX_PERCENT" ]; then
        bad "Systemplatte zu ${used} % belegt (docker image prune -a, alte Backups prüfen)"
    else
        ok "Systemplatte zu ${used} % belegt"
    fi
}

if [ "$INSTALLED" -eq 1 ]; then
    check_update_lock
    if [ "$UPDATE_RUNNING" -eq 0 ]; then
        check_reachability
        check_certificate
    fi
    if ! command -v docker >/dev/null 2>&1; then
        bad "docker fehlt"
    else
        if [ "$UPDATE_RUNNING" -eq 0 ]; then
            check_containers
            check_server_errors
        fi
        check_backup
    fi
    check_offsite
    check_restore_test
    check_auto_update
    check_disk
fi

[ "$TEST" -eq 0 ] || bad "Testmeldung von wachwerk-health --test"

send_ping() {  # $1 Adresse, $2 Text (leer: einfacher Aufruf)
    if [ -n "$2" ]; then
        printf '%s' "$2" | curl -fsS --max-time 10 --retry 3 -o /dev/null --data-binary @- "$1"
    else
        curl -fsS --max-time 10 --retry 3 -o /dev/null "$1"
    fi
}

host_label=$(hostname)
fails_file="$STATE_DIR/health.fails"
if [ -z "$PROBLEMS" ]; then
    rm -f "$fails_file" 2>/dev/null
    body=""
    [ -z "$NOTES" ] || body=$(printf 'Wachwerk auf %s hat sich selbst geholfen:\n%s' "$host_label" "$NOTES")
    [ -z "$PING_URL" ] || send_ping "$PING_URL" "$body" || true
    exit 0
fi

if [ "$TEST" -eq 1 ]; then
    fails="$FAILS_BEFORE_ALERT"
else
    fails=$(cat "$fails_file" 2>/dev/null)
    case "$fails" in ''|*[!0-9]*) fails=0 ;; esac
    fails=$((fails + 1))
    printf '%s\n' "$fails" >"$fails_file" 2>/dev/null || true
fi
if [ "$fails" -lt "$FAILS_BEFORE_ALERT" ]; then
    echo "Noch keine Meldung: Fehler im $fails. Lauf in Folge, gemeldet wird ab dem $FAILS_BEFORE_ALERT. (FAILS_BEFORE_ALERT)."
    exit 1
fi
if [ -z "$PING_URL" ]; then
    [ "$VERBOSE" -eq 0 ] || echo "Hinweis: PING_URL ist nicht gesetzt ($CONF_DIR/health.env) – keine Meldung nach außen." >&2
elif send_ping "$PING_URL/fail" "$(printf 'Wachwerk auf %s:\n%s%s' "$host_label" "$PROBLEMS" "$NOTES")"; then
    [ "$VERBOSE" -eq 0 ] || echo "Meldung an $PING_URL/fail gesendet."
else
    echo "Meldung an $PING_URL/fail konnte nicht gesendet werden." >&2
fi
exit 1
