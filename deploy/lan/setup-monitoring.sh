#!/bin/sh
# Richtet die Überwachung wachwerk-health im Wachen-Netz ein: Raspberry Pi
# (deploy/pi/setup-pi.sh ruft das Skript selbst auf), Thin Client oder PC mit
# install.sh --mode lan oder --mode local. Für einen Server im Internet gilt
# deploy/hetzner/harden-host.sh (docs/HETZNER.md). Anleitung:
# docs/BETRIEB-PI-LAN.md
#
#   sudo sh deploy/lan/setup-monitoring.sh [--dir PFAD] [--ping-url URL] [--yes]
#
# Was das Skript tut (wiederholbar, bestehende PING_URL bleibt):
#   - installiert deploy/hetzner/wachwerk-health.sh als /usr/local/bin/wachwerk-health
#   - schreibt /etc/wachwerk/health.env passend zur Betriebsart (Pi, lan, local)
#   - legt die systemd-Timer an: Prüfung alle 5 Minuten, Wiederherstellungsprobe
#     sonntags (dieselben Units wie harden-host.sh)
#   - setzt WACHWERK_HEALTH_DIR in .env (Pi zusätzlich COMPOSE_FILE) und startet
#     die geänderten Dienste neu: Wachwerk zeigt den Zustand dann den
#     Master-Admins an und meldet Störungen im Posteingang
#   - prüft einmal (wachwerk-health --verbose)
set -eu

say() { printf '\n==> %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf 'Warnung: %s\n' "$*" >&2; }
die() { printf 'Fehler: %s\n' "$*" >&2; exit 1; }

PI_COMPOSE_FILE="docker-compose.yml:compose.build.yml:deploy/pi/docker-compose.pi.yml"
# Pi: ohne feed-/push-worker (brauchen Internet), mit nginx als proxy.
PI_SERVICES="db redis web notify-worker housekeeping backup proxy"
STATUS_DIR="${WACHWERK_HEALTH_STATUS_DIR:-/var/lib/wachwerk-health}"
LAN_CA_FILE="${WACHWERK_LAN_CA_FILE:-/etc/wachwerk/lan-ca.crt}"

# --- Hilfsfunktionen (einzeln geprüft in core/test_lan_scripts.py) -------------

# Wert von SCHLÜSSEL ($2) aus DATEI ($1): letzte Zeile, ohne Anführungszeichen.
file_get() {
    [ -r "$1" ] || return 0
    sed -n "s/^$2=//p" "$1" | tail -n 1 | sed "s/^['\"]//; s/['\"]\$//"
}

# Setzt SCHLÜSSEL ($2) in DATEI ($1) auf WERT ($3), genau einmal; alle anderen
# Zeilen bleiben. Die neue Fassung ersetzt die alte erst vollständig per mv
# (cp -p: gleiche Rechte, gleicher Besitzer).
env_set() {
    env_tmp="$1.tmp.$$"
    if ! cp -p "$1" "$env_tmp" \
        || ! K="$2" V="$3" awk 'BEGIN { k = ENVIRON["K"]; v = ENVIRON["V"] }
            index($0, k "=") == 1 { if (!found) print k "=" v; found = 1; next } { print }
            END { if (!found) print k "=" v }' "$1" >"$env_tmp" \
        || ! mv -f "$env_tmp" "$1"; then
        rm -f "$env_tmp"
        warn "$1 nicht geändert ($2); Platte voll oder Ordner nicht beschreibbar?"
        return 1
    fi
}

# Betriebsart der Installation in Ordner $1: pi, lan oder local.
detect_layout() {
    [ -f "$1/.env" ] || die "In $1 ist Wachwerk nicht eingerichtet (.env fehlt). Ordner mit --dir angeben."
    if [ -f "$1/deploy/pi/docker-compose.pi.yml" ] && [ -n "$(file_get "$1/.env" PI_TLS_DIR)" ]; then
        echo pi
        return 0
    fi
    case "$(file_get "$1/.env" WACHBUCH_MODE)" in
        lan) echo lan ;;
        local|'') echo local ;;
        domain) die "Server im Internet (--mode domain): bitte deploy/hetzner/harden-host.sh verwenden (docs/HETZNER.md)." ;;
        *) die "Unbekannte Betriebsart (WACHBUCH_MODE) in $1/.env." ;;
    esac
}

# Compose-Datei, mit der die Dienste in $1 laufen: auf dem Pi die des Checkouts,
# sonst die von install.sh installierte compose.yml.
compose_file_of() {
    if [ "$2" != pi ] && [ -f "$1/compose.yml" ]; then
        printf '%s\n' "$1/compose.yml"
    else
        printf '%s\n' "$1/docker-compose.yml"
    fi
}

# health.env für Betriebsart $2 schreiben (nur root, 0600). Ohne PING_URL ($4)
# bleibt eine vorhandene erhalten. $5: Wurzelzertifikat von Caddy (lan).
write_lan_health_env() {
    he_file=$1
    he_layout=$2
    he_dir=$3
    he_ping=${4:-}
    he_ca=${5:-}
    [ -n "$he_ping" ] || he_ping=$(file_get "$he_file" PING_URL)
    he_fails=$(file_get "$he_file" FAILS_BEFORE_ALERT)
    case "$he_fails" in ''|*[!0-9]*|0) he_fails=2 ;; esac
    if [ "$he_fails" -gt 2 ]; then
        warn "FAILS_BEFORE_ALERT=$he_fails in $he_file: Ein Ausfall wird dann nicht in unter 15 Minuten gemeldet (empfohlen: 2)."
    fi
    he_port=$(file_get "$he_dir/.env" HTTP_PORT)
    he_tls=$(file_get "$he_dir/.env" PI_TLS_DIR)
    (
        umask 077
        {
            echo "# Wachwerk-Überwachung (wachwerk-health), eingerichtet von deploy/lan/setup-monitoring.sh"
            echo "WACHWERK_DIR=$he_dir"
            echo "PING_URL=$he_ping"
            case "$he_layout" in
                pi)
                    echo "# Pi: nginx mit dem Zertifikat aus setup-pi.sh"
                    echo "HEALTH_URL=https://localhost/healthz/"
                    echo "HEALTH_CA_FILE=${he_tls:-/etc/wachbuch/tls}/wachbuch.crt"
                    echo "HEALTH_SERVICES='$PI_SERVICES'"
                    ;;
                lan)
                    if [ -n "$he_ca" ]; then
                        echo "# https://<WACHBUCH_HOSTNAME>/ lokal aufgelöst, gegen die CA von Caddy"
                        echo "HEALTH_CA_FILE=$he_ca"
                    else
                        echo "# Ohne Wurzelzertifikat von Caddy: web direkt"
                        echo "HEALTH_URL=http://127.0.0.1:${he_port:-8090}/healthz/"
                    fi
                    ;;
                *)
                    echo "HEALTH_URL=http://127.0.0.1:${he_port:-8090}/healthz/"
                    ;;
            esac
            echo "# Meldung, wenn ein Fehler so viele Läufe (je 5 Minuten) in Folge besteht."
            echo "# Mit 2 kommt eine Meldung in unter 15 Minuten an."
            echo "FAILS_BEFORE_ALERT=$he_fails"
            echo "# Optional: Grenzen anpassen"
            echo "#DISK_MAX_PERCENT=85"
            echo "#BACKUP_MAX_AGE_HOURS=30"
            echo "#ERRORS_MAX_15MIN=5"
            echo "# Unhealthy-Container nicht selbst neu starten"
            echo "#AUTO_RESTART=false"
        } >"$he_file.tmp"
    )
    chmod 0600 "$he_file.tmp"
    mv -f "$he_file.tmp" "$he_file"
}

# Wurzelzertifikat der internen CA von Caddy nach $2 kopieren (install.sh
# --mode lan). 1, wenn das nicht geht (Caddy läuft nicht).
copy_lan_ca() {
    install -d -m 0700 "$(dirname "$2")"
    if (cd "$1" && docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt "$2.tmp") >/dev/null 2>&1 \
        && [ -s "$2.tmp" ]; then
        chmod 0644 "$2.tmp"
        mv -f "$2.tmp" "$2"
        return 0
    fi
    rm -f "$2.tmp"
    warn "Wurzelzertifikat von Caddy nicht lesbar – die Überwachung prüft web direkt über 127.0.0.1."
    return 1
}

# WACHWERK_HEALTH_DIR (Pi: auch COMPOSE_FILE) in $1/.env setzen, wenn die
# Compose-Datei den Zustand einbindet. Ergebnis: ENV_CHANGED=1, wenn .env
# geändert wurde; APP_DISPLAY=0, wenn die Installation dafür zu alt ist (dann
# bleibt .env unverändert und nichts wird neu gestartet).
configure_compose_env() {
    ENV_CHANGED=0
    APP_DISPLAY=1
    if ! grep -q '/run/wachwerk-health' "$(compose_file_of "$1" "$2")" 2>/dev/null; then
        APP_DISPLAY=0
        warn "Anzeige in Wachwerk erst ab Version 0.27 – zuerst aktualisieren (wachbuch update), dann dieses Skript erneut starten. Die Prüfung auf dem Server läuft trotzdem (Journal, PING_URL)."
        return 0
    fi
    if [ "$(file_get "$1/.env" WACHWERK_HEALTH_DIR)" != "$3" ]; then
        env_set "$1/.env" WACHWERK_HEALTH_DIR "$3"
        ENV_CHANGED=1
    fi
    # Ohne COMPOSE_FILE würden "docker compose run" (Ersatzweg der Meldung,
    # Wiederherstellungsprobe) im Checkout die Images aus dem Internet ziehen.
    if [ "$2" = pi ] && [ -z "$(file_get "$1/.env" COMPOSE_FILE)" ]; then
        env_set "$1/.env" COMPOSE_FILE "$PI_COMPOSE_FILE"
        ENV_CHANGED=1
    fi
}

# Geänderte Dienste neu starten. Pi: lokal gebaute Images, deshalb --build
# (nach git pull bringt das auch neue Migrationen mit).
recreate_services() {
    if [ "$2" = pi ]; then
        (cd "$1" && docker compose up -d --build)
    else
        (cd "$1" && docker compose up -d)
    fi
}

# Nur die Funktionen laden (Tests): WACHWERK_MONITORING_LIB=1 . setup-monitoring.sh
if [ "${WACHWERK_MONITORING_LIB:-}" = 1 ]; then
    # shellcheck disable=SC2317 # exit nur, falls nicht per "." geladen
    return 0 2>/dev/null || exit 0
fi

usage() {
    cat <<'EOF'
Aufruf: sudo sh deploy/lan/setup-monitoring.sh [Optionen]

  --dir PFAD        Wachwerk-Ordner (Standard: dieser Checkout, wenn dort
                    .env liegt, z. B. auf dem Pi; sonst /opt/wachbuch)
  --ping-url URL    optionaler Ping (z. B. https://hc-ping.com/<uuid>); braucht
                    Internet, bei Fehlern wird URL/fail aufgerufen
  -y, --yes         keine Rückfragen
  -h, --help        diese Hilfe
EOF
}

DIR=""
PING_URL=""
ASSUME_YES=0
while [ $# -gt 0 ]; do
    case "$1" in
        --dir) [ $# -ge 2 ] || die "--dir braucht einen Wert."; DIR="$2"; shift ;;
        --ping-url) [ $# -ge 2 ] || die "--ping-url braucht einen Wert."; PING_URL="$2"; shift ;;
        -y|--yes) ASSUME_YES=1 ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; die "Unbekannte Option: $1" ;;
    esac
    shift
done

[ "$(id -u)" -eq 0 ] || die "Bitte als root ausführen (sudo sh deploy/lan/setup-monitoring.sh …)."
case "$PING_URL" in
    ''|https://*) ;;
    *) die "--ping-url muss mit https:// beginnen." ;;
esac
SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
HETZNER_DIR=$(CDPATH='' cd -- "$SCRIPT_DIR/../hetzner" && pwd)
[ -f "$HETZNER_DIR/wachwerk-health.sh" ] || die "$HETZNER_DIR/wachwerk-health.sh fehlt (vollständigen Checkout verwenden)."
if [ -z "$DIR" ]; then
    checkout=$(CDPATH='' cd -- "$SCRIPT_DIR/../.." && pwd)
    if [ -f "$checkout/.env" ]; then DIR="$checkout"; else DIR=/opt/wachbuch; fi
fi
[ -d "$DIR" ] || die "$DIR ist kein Ordner."
DIR=$(CDPATH='' cd -- "$DIR" && pwd)
LAYOUT=$(detect_layout "$DIR")
command -v docker >/dev/null 2>&1 || die "docker fehlt."
command -v systemctl >/dev/null 2>&1 || die "systemd fehlt (systemctl)."

say "Überwachung für $DIR (Betriebsart: $LAYOUT)"
if [ "$ASSUME_YES" -eq 0 ] && [ -t 0 ]; then
    printf 'Prüfskript, Timer und Anzeige in Wachwerk einrichten? web und notify-worker starten dabei kurz neu. [J/n] '
    read -r answer || answer=n
    case "$answer" in ''|j|J|ja|Ja|y|Y) ;; *) die "Abgebrochen." ;; esac
fi

say "Prüfskript und Einstellungen"
install -m 0755 "$HETZNER_DIR/wachwerk-health.sh" /usr/local/bin/wachwerk-health
install -d -m 0700 /etc/wachwerk
CA_FILE=""
if [ "$LAYOUT" = lan ] && copy_lan_ca "$DIR" "$LAN_CA_FILE"; then
    CA_FILE="$LAN_CA_FILE"
fi
write_lan_health_env /etc/wachwerk/health.env "$LAYOUT" "$DIR" "$PING_URL" "$CA_FILE"
info "/usr/local/bin/wachwerk-health, /etc/wachwerk/health.env"

say "systemd-Timer (alle 5 Minuten, Wiederherstellungsprobe sonntags)"
# Nur write_units aus harden-host.sh (Bibliotheksmodus, ändert nichts).
# shellcheck disable=SC2034 # wird in harden-host.sh gelesen
WACHWERK_HARDEN_LIB=1
# shellcheck source=/dev/null
. "$HETZNER_DIR/harden-host.sh"
write_units /etc/systemd/system
systemctl daemon-reload
install -d -m 0755 "$STATUS_DIR"

say "Anzeige in Wachwerk (Banner, System, Posteingang der Master-Admins)"
configure_compose_env "$DIR" "$LAYOUT" "$STATUS_DIR"
if [ "$ENV_CHANGED" -eq 1 ]; then
    info "WACHWERK_HEALTH_DIR=$STATUS_DIR in $DIR/.env gesetzt; Dienste werden neu gestartet."
    recreate_services "$DIR" "$LAYOUT" || warn "Neustart fehlgeschlagen; bitte selbst starten (docker compose up -d in $DIR)."
elif [ "$APP_DISPLAY" -eq 1 ]; then
    info "bereits eingerichtet"
fi

systemctl enable --now wachwerk-health.timer >/dev/null 2>&1
systemctl enable --now wachwerk-restore-test.timer >/dev/null 2>&1

say "Erste Prüfung"
/usr/local/bin/wachwerk-health --verbose || true

cat <<EOF

Fertig. Die Überwachung prüft alle 5 Minuten.
  Zustand:       sudo wachwerk-health --verbose
  Probemeldung:  sudo wachwerk-health --test
                 (Banner und Posteingang der Master-Admins, danach "behoben")
  Protokoll:     sudo journalctl -u wachwerk-health -n 50
Ohne Internet melden Banner und Posteingang im Browser im Wachen-Netz.
E-Mail (EMAIL_HOST), Signal und PING_URL brauchen Internet.
Anleitung: docs/BETRIEB-PI-LAN.md
EOF
