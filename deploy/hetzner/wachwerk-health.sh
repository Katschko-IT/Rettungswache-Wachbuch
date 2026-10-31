#!/bin/sh
# Wachwerk-Überwachung für einen Server im Internet (docs/HETZNER.md), im
# Wachen-Netz und auf dem Raspberry Pi (docs/BETRIEB-PI-LAN.md).
# Läuft als root per systemd-Timer alle 5 Minuten (harden-host.sh bzw.
# deploy/lan/setup-monitoring.sh) und prüft:
#   - https://<WACHBUCH_HOSTNAME>/healthz/ über Caddy antwortet mit 200
#     (oder HEALTH_URL; HEALTH_CA_FILE vertraut der lokalen CA bzw. dem
#     Zertifikat des Pi)
#   - das TLS-Zertifikat gilt noch mindestens CERT_MIN_DAYS Tage (entfällt
#     bei lokaler CA)
#   - alle Dauerdienste laufen (db, redis, web, Worker, backup und je nach
#     Profil caddy, demo-cleaner, signal; HEALTH_SERVICES ersetzt die
#     Grundliste, z. B. auf dem Pi); keiner ist "unhealthy" oder startet
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
# Zustand für Wachwerk: Jeder Lauf schreibt status.json nach
# WACHWERK_HEALTH_DIR aus .env (Standard /var/lib/wachwerk-health), atomar und
# lesbar (0644). Die Datei enthält nur Codes, Zeiten und Zahlen, nie Texte,
# Hostnamen, Adressen, Pfade oder Geheimnisse. Compose bindet den Ordner nur
# lesend in web und notify-worker ein: Master-Admins sehen dann ein Banner,
# den Abschnitt "Betrieb und Datensicherung" auf /system/ und eine Nachricht
# im Posteingang (dazu E-Mail und Signal, falls eingerichtet). Jede Störung
# hat eine Kennung (UTC-Zeit, zu der sie gemeldet wurde); nach dem Beheben
# bleibt sie als last_alert stehen, damit Wachwerk "behoben" melden kann.
# Läuft der notify-worker selbst nicht, stellt die Prüfung die Meldung einmal
# je Störung über einen eigenen Lauf zu (docker compose run notify-worker).
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
            WACHWERK_DIR|PING_URL|HEALTH_URL|HEALTH_CA_FILE|HEALTH_SERVICES|CERT_MIN_DAYS|\
            DISK_MAX_PERCENT|BACKUP_MAX_AGE_HOURS|ERRORS_MAX_15MIN|FAILS_BEFORE_ALERT|AUTO_RESTART) ;;
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
# Lokale CA bzw. Zertifikat für curl --cacert (Pi, install.sh --mode lan).
HEALTH_CA_FILE="${HEALTH_CA_FILE:-}"
# Ersetzt die Grundliste der Dauerdienste (Pi ohne feed-/push-worker, mit
# proxy); Profile (https, demo, signal) kommen weiter dazu.
HEALTH_SERVICES="${HEALTH_SERVICES:-}"
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

# Texte gehen ins Journal und an PING_URL, die Codes (bereich:art[:wert],
# mehrere durch Leerzeichen getrennt) in den Zustand für Wachwerk. Wachwerk
# übersetzt die Codes selbst (core/host_health.py, PROBLEM_TEXTS).
PROBLEMS=""
NOTES=""
CODES=""
NOTE_CODES=""
ok() { [ "$VERBOSE" -eq 0 ] || printf 'OK      %s\n' "$*"; }
# Ein Code je Zeile, ohne Dateinamen-Expansion (ein Dienstname "*" bliebe
# sonst nicht wörtlich). Läuft nur in $(...), set -f wirkt nicht nach außen.
code_lines() {
    set -f
    # shellcheck disable=SC2086 # ein Code je Wort
    printf '%s\n' $1
}
bad() {  # $1 Code(s), $2 Text
    printf 'FEHLER  %s\n' "$2" >&2
    PROBLEMS="${PROBLEMS}- $2
"
    CODES="${CODES}$(code_lines "$1")
"
}
note() {  # $1 Code(s), $2 Text
    printf 'AKTION  %s\n' "$2"
    NOTES="${NOTES}- $2
"
    NOTE_CODES="${NOTE_CODES}$(code_lines "$1")
"
}
# codes_for bereich:art "a b" -> "bereich:art:a bereich:art:b" (nur in $(...))
codes_for() {
    set -f
    # shellcheck disable=SC2086 # ein Eintrag je Wort
    for item in $2; do printf '%s:%s ' "$1" "$item"; done
}
t() { timeout "$CMD_TIMEOUT" "$@"; }

env_get() {
    [ -r "$WACHWERK_DIR/.env" ] || return 0
    sed -n "s/^$1=//p" "$WACHWERK_DIR/.env" | tail -n 1 | sed "s/^['\"]//; s/['\"]\$//"
}

# Ordner für status.json: derselbe Wert, den Compose einbindet (.env), damit
# Host und Wachwerk nie auf verschiedene Ordner schauen.
# WACHWERK_HEALTH_STATUS_DIR überschreibt ihn nur für Tests.
STATUS_DIR="${WACHWERK_HEALTH_STATUS_DIR:-}"
if [ -z "$STATUS_DIR" ]; then
    STATUS_DIR=$(env_get WACHWERK_HEALTH_DIR)
    case "$STATUS_DIR" in /*) ;; *) STATUS_DIR=/var/lib/wachwerk-health ;; esac
fi

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
        bad update:lock_stale "Sperre des automatischen Updates besteht seit über $AUTO_UPDATE_MAX_MINUTES Minuten – Update hängt oder wurde unterbrochen (wachbuch auto-update status)"
    else
        UPDATE_RUNNING=1
        echo "Hinweis: automatisches Update läuft – Erreichbarkeit, Zertifikat und Container werden diesmal nicht geprüft."
    fi
}

# 1. Erreichbarkeit über Caddy (lokal aufgelöst, damit DNS-Hairpinning egal ist)
# Mit HEALTH_CA_FILE vertraut curl nur dieser lokalen CA bzw. dem Zertifikat
# des Pi (in beiden Zweigen, auch mit --resolve).
curl_health() {
    if [ -n "$HEALTH_CA_FILE" ]; then
        curl -fsS --max-time 15 -o /dev/null --cacert "$HEALTH_CA_FILE" "$@"
    else
        curl -fsS --max-time 15 -o /dev/null "$@"
    fi
}
check_reachability() {
    if [ -n "${HEALTH_URL:-}" ]; then
        if curl_health "$HEALTH_URL"; then
            ok "$HEALTH_URL"
        else
            bad web:unreachable "$HEALTH_URL antwortet nicht mit 200"
        fi
    elif [ -n "$HOST" ] && [ "$HOST" != "localhost" ]; then
        url="https://$HOST:$HTTPS_PORT/healthz/"
        if curl_health --resolve "$HOST:$HTTPS_PORT:127.0.0.1" "$url"; then
            ok "$url"
        else
            bad web:unreachable "$url antwortet nicht mit 200 (wachbuch logs caddy / web)"
        fi
    else
        bad config:hostname "WACHBUCH_HOSTNAME fehlt in $WACHWERK_DIR/.env (oder HEALTH_URL in $CONF_DIR/health.env setzen)"
    fi
}

# 2. Zertifikat. Entfällt bei lokaler CA (HEALTH_CA_FILE, --mode lan): Caddy
# stellt dort Zertifikate mit rund 12 Stunden Laufzeit aus und erneuert sie
# selbst; das Ablaufdatum sagt nichts über ein Problem.
check_certificate() {
    [ -z "$HEALTH_CA_FILE" ] || return 0
    [ "$(env_get WACHBUCH_MODE)" != lan ] || return 0
    [ -n "$HOST" ] && [ "$HOST" != "localhost" ] && command -v openssl >/dev/null 2>&1 || return 0
    end=$(t openssl s_client -connect "127.0.0.1:$HTTPS_PORT" -servername "$HOST" </dev/null 2>/dev/null \
        | openssl x509 -noout -enddate 2>/dev/null | sed 's/^notAfter=//')
    if [ -z "$end" ]; then
        bad certificate:unreadable "TLS-Zertifikat für $HOST nicht lesbar"
        return
    fi
    end_s=$(date -d "$end" +%s 2>/dev/null || echo 0)
    days=$(( (end_s - $(date +%s)) / 86400 ))
    if [ "$days" -lt "$CERT_MIN_DAYS" ]; then
        bad "certificate:expiring:$days" "TLS-Zertifikat läuft in $days Tagen ab (Caddy erneuert sonst ab 30 Tagen; wachbuch logs caddy)"
    else
        ok "Zertifikat gilt noch $days Tage"
    fi
}

# Unhealthy-Container neu starten, höchstens dreimal je Stunde und Dienst.
heal() {  # $1 Dienst, $2 Container-ID
    if [ "$AUTO_RESTART" != true ] || [ "$1" = db ]; then
        bad "service:unhealthy:$1" "Dienst $1 ist unhealthy (wachbuch logs $1)"
        return
    fi
    restarts="$STATE_DIR/restarts"
    now=$(date +%s)
    count=$(awk -v s="$1" -v now="$now" '$2 == s && now - $1 < 3600 { n++ } END { print n + 0 }' \
        "$restarts" 2>/dev/null || echo 0)
    if [ "$count" -ge 3 ]; then
        bad "service:restart_limit:$1" "Dienst $1 bleibt unhealthy, schon $count Neustarts in der letzten Stunde (wachbuch logs $1)"
    elif timeout 120 docker restart -t 30 "$2" >/dev/null 2>&1; then
        printf '%s %s\n' "$now" "$1" >>"$restarts" 2>/dev/null || true
        note "service:restarted:$1" "Dienst $1 war unhealthy und wurde neu gestartet ($((count + 1)). Neustart in einer Stunde)"
    else
        bad "service:restart_failed:$1" "Dienst $1 ist unhealthy, Neustart fehlgeschlagen (wachbuch logs $1)"
    fi
}

# Zustand eines Dienstes aus CONTAINERS: running, unhealthy, restarting,
# exited … oder leer (fehlt). Bei mehreren Containern (Neuanlage) zählt der
# beste Zustand.
service_state() {
    printf '%s\n' "$CONTAINERS" | awk -v s="$1" '
        $1 == s {
            st = $3
            if (st == "running" && $4 == "unhealthy") st = "unhealthy"
            rank = (st == "running") ? 3 : (st == "unhealthy" || st == "restarting") ? 2 : 1
            if (rank > best) { best = rank; result = st }
        }
        END { print result }'
}

# Grundliste der Dauerdienste einer Installation mit install.sh.
default_services() {
    list="db redis web feed-worker notify-worker push-worker backup"
    # housekeeping gibt es erst ab 0.26.0; diese Prüfung kommt aus main, die
    # Installation kann älter sein (compose.yml ist die installierte Fassung).
    if grep -q '^  housekeeping:' "$WACHWERK_DIR/compose.yml" 2>/dev/null; then
        list="$list housekeeping"
    fi
    printf '%s\n' "$list"
}

# 3. Container
check_containers() {
    ids=$(t docker ps -a -q --no-trunc --filter "label=com.docker.compose.project=$PROJECT" \
        --filter "label=com.docker.compose.oneoff=False" 2>/dev/null)
    if [ -z "$ids" ]; then
        bad containers:missing "keine Container des Projekts $PROJECT gefunden (wachbuch start)"
        return
    fi
    # Je Container eine Zeile: Dienst Neustartregel Zustand Gesundheit ID
    # shellcheck disable=SC2086 # jede ID ein eigenes Argument
    CONTAINERS=$(t docker inspect --format '{{index .Config.Labels "com.docker.compose.service"}} {{.HostConfig.RestartPolicy.Name}} {{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}-{{end}} {{.Id}}' $ids 2>/dev/null)
    if [ -z "$CONTAINERS" ]; then
        bad containers:unreadable "Zustand der Container nicht lesbar (docker inspect)"
        return
    fi
    case "$HEALTH_SERVICES" in
        '') services=$(default_services) ;;
        *[!a-z0-9\ -]*)
            bad config:services "HEALTH_SERVICES in $CONF_DIR/health.env enthält ungültige Zeichen (erlaubt: a-z, 0-9, -, Leerzeichen) – geprüft wird die Grundliste"
            services=$(default_services) ;;
        *) services="$HEALTH_SERVICES" ;;
    esac
    if has_profile https; then services="$services caddy"; fi
    if has_profile demo || [ "$(env_get DEMO_SANDBOX)" = "true" ]; then services="$services demo-cleaner"; fi
    if has_profile signal; then services="$services signal"; fi
    # shellcheck disable=SC2086 # Dienstnamen sind geprüft: a-z, 0-9, -
    services=$(printf '%s\n' $services | awk '!seen[$0]++' | tr '\n' ' ')
    for service in $services; do
        state=$(service_state "$service")
        case "$state" in
            running) ok "Dienst $service läuft" ;;
            unhealthy|restarting) ;;  # unten gemeldet
            '') bad "service:missing:$service" "Dienst $service fehlt (wachbuch start)" ;;
            *) bad "service:stopped:$service" "Dienst $service: $state (wachbuch logs $service)" ;;
        esac
    done
    # Alle Dauerdienste, auch solche, die hier nicht aufgezählt sind.
    restarting=$(printf '%s\n' "$CONTAINERS" | awk '$3 == "restarting" { print $1 }' | sort -u | tr '\n' ' ')
    [ -z "$restarting" ] || bad "$(codes_for service:restarting "$restarting")" \
        "startet ständig neu: ${restarting% } (wachbuch logs <dienst>)"
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
        bad "errors:server:$errors" "$errors Serverfehler (5xx) in den letzten 15 Minuten (wachbuch logs web)"
    else
        ok "$errors Serverfehler (5xx) in den letzten 15 Minuten"
    fi
}

# 4. Backup-Alter
check_backup() {
    mount=$(t docker volume inspect -f '{{.Mountpoint}}' "${PROJECT}_backups-data" 2>/dev/null || true)
    if [ -z "$mount" ] || [ ! -d "$mount" ]; then
        bad backup:volume_missing "Backup-Volume ${PROJECT}_backups-data nicht gefunden"
        return
    fi
    newest=$(find "$mount" -maxdepth 1 -type f -name 'rwsth-*.dump' -printf '%T@ %f\n' 2>/dev/null \
        | sort -n | tail -n 1)
    if [ -z "$newest" ]; then
        bad backup:missing "noch kein Backup vorhanden (wachbuch backup)"
        return
    fi
    BACKUP_EPOCH=${newest%%.*}
    age_h=$(( ($(date +%s) - BACKUP_EPOCH) / 3600 ))
    BACKUP_AGE_H=$age_h
    if [ "$age_h" -ge "$BACKUP_MAX_AGE_HOURS" ]; then
        bad "backup:stale:$age_h" "neuestes Backup ist $age_h Stunden alt (wachbuch logs backup)"
    else
        ok "neuestes Backup: ${newest#* } ($age_h h alt)"
    fi
}

# 4b. Offsite-Kopie (offsite-storagebox.sh): Kopie gelungen UND frisch
# verschlüsselt. Der Sync allein ist auch "erfolgreich", wenn seit Tagen keine
# neue Datei mehr entsteht (z. B. Schlüssel fehlt im Backup-Dienst).
check_offsite() {
    [ -r "$CONF_DIR/offsite.env" ] || return 0
    target=$(sed -n 's/^OFFSITE_TARGET=//p' "$CONF_DIR/offsite.env" | tail -n 1)
    case "$target" in
        usb:*) OFFSITE_KIND=usb ;;
        /*) OFFSITE_KIND=path ;;
        *your-storagebox.de*) OFFSITE_KIND=storagebox ;;
        *) OFFSITE_KIND=ssh ;;
    esac
    marker="$STATE_DIR/offsite-sync.ok"
    if [ ! -f "$marker" ]; then
        bad offsite:never "Offsite-Kopie lief noch nie erfolgreich (journalctl -u wachwerk-offsite)"
    else
        age_h=$(( ($(date +%s) - $(stat -c %Y "$marker")) / 3600 ))
        OFFSITE_SYNC_AGE_H=$age_h
        if [ "$age_h" -ge 3 ]; then
            bad "offsite:sync_stale:$age_h" "letzte erfolgreiche Offsite-Kopie vor $age_h Stunden (journalctl -u wachwerk-offsite)"
        else
            ok "Offsite-Kopie vor $age_h h"
        fi
    fi
    offsite_dir=$(sed -n 's/^OFFSITE_DIR=//p' "$CONF_DIR/offsite.env" | tail -n 1)
    offsite_dir="${offsite_dir:-/var/lib/wachwerk-offsite}"
    newest=$(find "$offsite_dir" -maxdepth 1 -type f -name 'rwsth-*.dump.gpg' -printf '%T@ %f\n' 2>/dev/null \
        | sort -n | tail -n 1)
    if [ -z "$newest" ]; then
        bad offsite:copy_missing "keine verschlüsselte Kopie in $offsite_dir (wachbuch logs backup)"
        return
    fi
    OFFSITE_EPOCH=${newest%%.*}
    age_h=$(( ($(date +%s) - OFFSITE_EPOCH) / 3600 ))
    OFFSITE_AGE_H=$age_h
    if [ "$age_h" -ge "$BACKUP_MAX_AGE_HOURS" ]; then
        bad "offsite:copy_stale:$age_h" "neueste verschlüsselte Kopie ist $age_h Stunden alt – Verschlüsselung gescheitert? (wachbuch logs backup)"
    else
        ok "neueste verschlüsselte Kopie: ${newest#* } ($age_h h alt)"
    fi
}

# 4c. Wiederherstellungsprobe (wachwerk-restore-test.timer, wöchentlich)
check_restore_test() {
    status_file="$STATE_DIR/restore-test.status"
    [ -f "$status_file" ] || return 0
    status=$(head -n 1 "$status_file")
    RESTORE_EPOCH=$(stat -c %Y "$status_file")
    RESTORE_OK=false
    age_d=$(( ($(date +%s) - RESTORE_EPOCH) / 86400 ))
    case "$status" in
        ok)
            RESTORE_OK=true
            if [ "$age_d" -ge 8 ]; then
                bad "restore:stale:$age_d" "letzte Wiederherstellungsprobe vor $age_d Tagen (systemctl list-timers wachwerk-restore-test.timer)"
            else
                ok "Wiederherstellungsprobe vor $age_d Tagen gelungen"
            fi
            ;;
        *) bad restore:failed "Wiederherstellungsprobe $status (journalctl -u wachwerk-restore-test)" ;;
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
            bad update:never "automatisches Update lief noch nie (wachbuch auto-update status)"
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
                || bad update:failed "automatisches Update ($stamp): $message (wachbuch auto-update status)" ;;
    esac
    run_s=$(date -d "$stamp" +%s 2>/dev/null || echo 0)
    age_h=$(( ($(date +%s) - run_s) / 3600 ))
    if [ "$UPDATE_RUNNING" -eq 0 ] && [ "$age_h" -ge "$AUTO_UPDATE_MAX_AGE_HOURS" ]; then
        bad "update:stale:$age_h" "automatisches Update lief zuletzt vor $age_h Stunden (wachbuch auto-update status)"
    fi
}

# 6. Platz
check_disk() {
    used=$(df -P / | awk 'NR == 2 { gsub("%", "", $5); print $5 }')
    if [ "${used:-0}" -ge "$DISK_MAX_PERCENT" ]; then
        bad "disk:full:$used" "Systemplatte zu ${used} % belegt (docker image prune -a, alte Backups prüfen)"
    else
        ok "Systemplatte zu ${used} % belegt"
    fi
}

# Werte für den Zustand (status.json); leer = unbekannt
BACKUP_EPOCH=""
BACKUP_AGE_H=""
OFFSITE_KIND=""
OFFSITE_EPOCH=""
OFFSITE_AGE_H=""
OFFSITE_SYNC_AGE_H=""
RESTORE_EPOCH=""
RESTORE_OK=false

if [ "$INSTALLED" -eq 1 ]; then
    check_update_lock
    if [ "$UPDATE_RUNNING" -eq 0 ]; then
        check_reachability
        check_certificate
    fi
    if ! command -v docker >/dev/null 2>&1; then
        bad docker:missing "docker fehlt"
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

[ "$TEST" -eq 0 ] || bad test:alert "Testmeldung von wachwerk-health --test"

send_ping() {  # $1 Adresse, $2 Text (leer: einfacher Aufruf)
    if [ -n "$2" ]; then
        printf '%s' "$2" | curl -fsS --max-time 10 --retry 3 -o /dev/null --data-binary @- "$1"
    else
        curl -fsS --max-time 10 --retry 3 -o /dev/null "$1"
    fi
}

# --- Zustand für Wachwerk (status.json, Schema 1) ------------------------------
word() { printf '%s' "$1" | tr -cd 'a-z0-9_-' | cut -c1-40; }
int_or_null() { case "$1" in ''|*[!0-9]*) printf 'null' ;; *) printf '%s' "$1" ;; esac; }
iso_or_null() {
    case "$1" in
        ''|*[!0-9]*) printf 'null' ;;
        *) date -u -d "@$1" '+"%Y-%m-%dT%H:%M:%SZ"' 2>/dev/null || printf 'null' ;;
    esac
}
# Kennung einer Störung: UTC-Zeit YYYYmmddTHHMMSSZ, sonst leer.
alert_id_or_empty() {
    case "$1" in
        [0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z) printf '%s' "$1" ;;
    esac
}
read_alert_id() { alert_id_or_empty "$(head -n 1 "$1" 2>/dev/null)"; }
read_epoch() {
    value=$(head -n 1 "$1" 2>/dev/null)
    case "$value" in ''|*[!0-9]*) ;; *) printf '%s' "$value" ;; esac
}

# Zeilen bereich:art[:wert] als JSON-Liste. Nur [a-z_] bzw. [a-z0-9-], höchstens
# 20 Einträge: Was aus Docker-Labels o. ä. kommt, gelangt nie roh in die Datei.
items_json() {
    printf '%s\n' "$1" | awk -F: '
        BEGIN { printf "[" }
        NF >= 2 && n < 20 {
            a = $1; i = $2; p = (NF >= 3) ? $3 : ""
            gsub(/[^a-z_]/, "", a); gsub(/[^a-z_]/, "", i); gsub(/[^a-z0-9-]/, "", p)
            if (a == "" || i == "") next
            printf "%s{\"area\":\"%s\",\"issue\":\"%s\",\"param\":\"%s\"}", (n++ ? "," : ""), substr(a, 1, 20), substr(i, 1, 20), substr(p, 1, 40)
        }
        END { printf "]" }'
}

status_json() {  # $1 Zustand ok|problem
    printf '{"schema":1,"checked_at":%s,"state":"%s",' "$(iso_or_null "$NOW_EPOCH")" "$(word "$1")"
    printf '"failing_since":%s,"alert":"%s","last_alert":"%s",' "$(iso_or_null "$FAILING_SINCE")" \
        "$(alert_id_or_empty "$ALERT_ID")" "$(alert_id_or_empty "$LAST_ALERT")"
    printf '"problems":%s,"notes":%s,' "$(items_json "$CODES")" "$(items_json "$NOTE_CODES")"
    printf '"backup":{"newest_at":%s,"age_hours":%s},' "$(iso_or_null "$BACKUP_EPOCH")" "$(int_or_null "$BACKUP_AGE_H")"
    if [ -n "$OFFSITE_KIND" ]; then
        printf '"offsite":{"kind":"%s","newest_at":%s,"age_hours":%s,"sync_age_hours":%s,"away_age_days":null,"media":[]},' \
            "$(word "$OFFSITE_KIND")" "$(iso_or_null "$OFFSITE_EPOCH")" "$(int_or_null "$OFFSITE_AGE_H")" \
            "$(int_or_null "$OFFSITE_SYNC_AGE_H")"
    else
        printf '"offsite":null,'
    fi
    if [ -n "$RESTORE_EPOCH" ]; then
        printf '"restore_test":{"at":%s,"ok":%s,"dump_at":null,"tables":null,"migrations":null,"stations":null,"users":null,"audit":null},' \
            "$(iso_or_null "$RESTORE_EPOCH")" "$RESTORE_OK"
    else
        printf '"restore_test":null,'
    fi
    printf '"restore_probe":null}\n'
}

# Atomar ersetzen (mktemp + mv im selben Ordner). Ein Fehler ändert weder
# Exit-Code noch Ping; er steht nur als Hinweis im Journal.
write_status() {  # $1 Zustand ok|problem
    if ! install -d -m 0755 "$STATUS_DIR" 2>/dev/null \
        || ! tmp=$(mktemp "$STATUS_DIR/.status.XXXXXX" 2>/dev/null); then
        echo "Hinweis: Zustand für Wachwerk nicht geschrieben ($STATUS_DIR)." >&2
        return 0
    fi
    if status_json "$1" >"$tmp" && chmod 0644 "$tmp" && mv -f "$tmp" "$STATUS_DIR/status.json"; then
        return 0
    fi
    rm -f "$tmp"
    echo "Hinweis: Zustand für Wachwerk nicht geschrieben ($STATUS_DIR)." >&2
}

# Läuft der notify-worker nicht (fehlt, beendet, startet neu, unhealthy),
# stellt ein eigener Lauf des Befehls die neue Störung einmal zu: derselbe
# Code und dieselbe Datenbankrolle wie der Dienst, kein SQL vom Host. Nur, wenn
# Wachwerk den Zustand überhaupt einbindet (WACHWERK_HEALTH_DIR in .env) und
# kein Update läuft. Ist die Datenbank aus, bleibt nur PING_URL.
deliver_via_app() {
    if [ "$INSTALLED" -ne 1 ] || [ "$UPDATE_RUNNING" -ne 0 ]; then
        return 0
    fi
    [ -n "$(env_get WACHWERK_HEALTH_DIR)" ] || return 0
    command -v docker >/dev/null 2>&1 || return 0
    if [ "$(service_state notify-worker)" = running ]; then
        return 0
    fi
    echo "Hinweis: notify-worker läuft nicht – die Meldung wird einmal über einen eigenen Lauf zugestellt."
    if (cd "$WACHWERK_DIR" && timeout 180 docker compose run --rm --no-deps -T notify-worker \
        python manage.py notify_crew) >/dev/null 2>&1; then
        echo "Meldung an die Master-Admins in Wachwerk zugestellt."
    else
        echo "Hinweis: Meldung in Wachwerk nicht zugestellt (Datenbank erreichbar?)." >&2
    fi
}

host_label=$(hostname)
fails_file="$STATE_DIR/health.fails"
since_file="$STATE_DIR/health.since"
alert_file="$STATE_DIR/health.alert"
last_alert_file="$STATE_DIR/health.last_alert"
NOW_EPOCH=$(date +%s)
FAILING_SINCE=""
ALERT_ID=""
NEW_ALERT=0
LAST_ALERT=$(read_alert_id "$last_alert_file")
if [ -z "$PROBLEMS" ]; then
    # Behoben: Zähler, Beginn und offene Störung weg; last_alert bleibt.
    rm -f "$fails_file" "$since_file" "$alert_file" 2>/dev/null
    write_status ok
    body=""
    [ -z "$NOTES" ] || body=$(printf 'Wachwerk auf %s hat sich selbst geholfen:\n%s' "$host_label" "$NOTES")
    [ -z "$PING_URL" ] || send_ping "$PING_URL" "$body" || true
    exit 0
fi

if [ "$TEST" -eq 1 ]; then
    # Probemeldung mit eigener Kennung; Zähler und laufende Störung bleiben.
    fails="$FAILS_BEFORE_ALERT"
    FAILING_SINCE=$(read_epoch "$since_file")
    FAILING_SINCE="${FAILING_SINCE:-$NOW_EPOCH}"
    ALERT_ID=$(date -u +%Y%m%dT%H%M%SZ)
    NEW_ALERT=1
    if [ -z "$(read_alert_id "$alert_file")" ]; then
        LAST_ALERT="$ALERT_ID"
        printf '%s\n' "$ALERT_ID" >"$last_alert_file" 2>/dev/null || true
    fi
else
    fails=$(cat "$fails_file" 2>/dev/null)
    case "$fails" in ''|*[!0-9]*) fails=0 ;; esac
    fails=$((fails + 1))
    printf '%s\n' "$fails" >"$fails_file" 2>/dev/null || true
    FAILING_SINCE=$(read_epoch "$since_file")
    if [ -z "$FAILING_SINCE" ]; then
        FAILING_SINCE="$NOW_EPOCH"
        printf '%s\n' "$FAILING_SINCE" >"$since_file" 2>/dev/null || true
    fi
    if [ "$fails" -ge "$FAILS_BEFORE_ALERT" ]; then
        ALERT_ID=$(read_alert_id "$alert_file")
        if [ -z "$ALERT_ID" ]; then
            # Neue Störung: Kennung = Zeitpunkt, zu dem sie gemeldet wird.
            ALERT_ID=$(date -u +%Y%m%dT%H%M%SZ)
            NEW_ALERT=1
            LAST_ALERT="$ALERT_ID"
            printf '%s\n' "$ALERT_ID" >"$alert_file" 2>/dev/null || true
            printf '%s\n' "$ALERT_ID" >"$last_alert_file" 2>/dev/null || true
        fi
    fi
fi
[ "$INSTALLED" -eq 0 ] || write_status problem
[ "$NEW_ALERT" -eq 0 ] || deliver_via_app

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
