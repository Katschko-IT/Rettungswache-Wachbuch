#!/bin/sh
# Wachbuch-Installer: richtet das Rettungswache-Wachbuch mit Docker ein.
#
#   curl -fsSL https://raw.githubusercontent.com/Katschko-IT/Rettungswache-Wachbuch/main/install.sh | sh
#   sh install.sh --yes --name "RW Musterstadt" --mode lan --domain wachbuch.lan
#
# Läuft auf Linux (auch Raspberry Pi OS 64-bit) und macOS mit Docker und
# Compose v2. Wiederholbar: vorhandene .env-Werte und Geheimnisse bleiben
# erhalten, fehlende Schlüssel werden ergänzt. Hilfe: sh install.sh --help
set -eu

REPO_SLUG="Katschko-IT/Rettungswache-Wachbuch"
DEFAULT_BASE_URL="https://raw.githubusercontent.com/${REPO_SLUG}"
MIN_COMPOSE_MAJOR=2
MIN_COMPOSE_MINOR=20

# --- Ausgabe ---------------------------------------------------------------
say() { printf '\n==> %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf 'Warnung: %s\n' "$*" >&2; }
die() { printf 'Fehler: %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'EOF'
Wachbuch-Installer

Aufruf: sh install.sh [Optionen]

  --dir PFAD          Zielordner (Linux: /opt/wachbuch, macOS: ~/wachbuch)
  --name NAME         Name der Wache (Standard: Rettungswache)
  --mode ART          local  = nur dieser Rechner, http://localhost:PORT
                      lan    = im Wachen-Netz per HTTPS mit eigenem Zertifikat
                      domain = öffentliche Domain mit Let's-Encrypt-Zertifikat
  --domain NAME       Hostname, Domain oder IP-Adresse (lan/domain)
  --email ADRESSE     Kontakt für Let's Encrypt (domain)
  --port PORT         lokaler HTTP-Port des Wachbuchs (Standard 8090)
  --https-port PORT   HTTPS-Port des Proxys (Standard 443, lan/domain)
  --http-port PORT    HTTP-Port des Proxys für die Umleitung (Standard 80)
  --version X.Y.Z     Wachbuch-Version (Standard: neueste Veröffentlichung)
  --source PFAD       Dateien aus einem lokalen Checkout statt aus dem Netz
  --base-url URL      andere Download-Quelle (Standard: GitHub raw)
  --build             Images lokal aus --source bauen statt herunterladen
  --project NAME      eigener Compose-Projektname (z. B. für Tests)
  --no-start          nur Dateien und .env anlegen, nichts starten
  -y, --yes           keine Rückfragen, Standardwerte verwenden
  -h, --help          diese Hilfe

Alle Optionen gehen auch als Umgebungsvariablen: WACHBUCH_DIR, WACHBUCH_NAME,
WACHBUCH_MODE, WACHBUCH_DOMAIN, WACHBUCH_EMAIL, WACHBUCH_PORT,
WACHBUCH_VERSION, WACHBUCH_SOURCE, WACHBUCH_BASE_URL.
EOF
}

# --- Optionen --------------------------------------------------------------
TARGET_DIR="${WACHBUCH_DIR:-}"
OPT_NAME="${WACHBUCH_NAME:-}"
OPT_MODE="${WACHBUCH_MODE:-}"
OPT_HOST="${WACHBUCH_DOMAIN:-}"
OPT_EMAIL="${WACHBUCH_EMAIL:-}"
OPT_PORT="${WACHBUCH_PORT:-}"
OPT_HTTPS_PORT=""
OPT_HTTP_PORT=""
OPT_VERSION="${WACHBUCH_VERSION:-}"
SOURCE="${WACHBUCH_SOURCE:-}"
BASE_URL="${WACHBUCH_BASE_URL:-}"
PROJECT=""
BUILD=0
ASSUME_YES=0
NO_START=0

need_value() { [ $# -ge 2 ] && [ -n "$2" ] || die "Option $1 braucht einen Wert."; }

while [ $# -gt 0 ]; do
    case "$1" in
        --dir) need_value "$@"; TARGET_DIR="$2"; shift ;;
        --name) need_value "$@"; OPT_NAME="$2"; shift ;;
        --mode) need_value "$@"; OPT_MODE="$2"; shift ;;
        --domain|--host) need_value "$@"; OPT_HOST="$2"; shift ;;
        --email) need_value "$@"; OPT_EMAIL="$2"; shift ;;
        --port) need_value "$@"; OPT_PORT="$2"; shift ;;
        --https-port) need_value "$@"; OPT_HTTPS_PORT="$2"; shift ;;
        --http-port) need_value "$@"; OPT_HTTP_PORT="$2"; shift ;;
        --version) need_value "$@"; OPT_VERSION="$2"; shift ;;
        --source) need_value "$@"; SOURCE="$2"; shift ;;
        --base-url) need_value "$@"; BASE_URL="$2"; shift ;;
        --project) need_value "$@"; PROJECT="$2"; shift ;;
        --build) BUILD=1 ;;
        --no-start) NO_START=1 ;;
        -y|--yes) ASSUME_YES=1 ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; die "Unbekannte Option: $1" ;;
    esac
    shift
done

# --- Hilfsfunktionen -------------------------------------------------------
have() { command -v "$1" >/dev/null 2>&1; }

is_port() {
    case "$1" in ''|*[!0-9]*) return 1 ;; esac
    [ "$1" -ge 1 ] && [ "$1" -le 65535 ]
}

# Hostname, Domain oder IPv4-Adresse (keine Leerzeichen, kein Schema).
is_hostname() {
    case "$1" in
        ''|*[!A-Za-z0-9.-]*|.*|-*|*.) return 1 ;;
    esac
    return 0
}

is_ipv4() {
    case "$1" in
        *[!0-9.]*|'') return 1 ;;
    esac
    [ "$(printf '%s' "$1" | awk -F. 'NF == 4 { print "ok" }')" = "ok" ]
}

# Interaktiv nur mit Terminal; bei "curl | sh" liest das Skript von /dev/tty.
INTERACTIVE=0
if [ "$ASSUME_YES" -eq 0 ] && [ -r /dev/tty ] && (: </dev/tty) 2>/dev/null; then
    INTERACTIVE=1
fi

ask() {  # ask "Frage" "Standard" -> Antwort auf stdout
    if [ "$INTERACTIVE" -eq 1 ]; then
        printf '%s [%s]: ' "$1" "$2" >/dev/tty
        answer=""
        IFS= read -r answer </dev/tty || answer=""
        printf '%s' "${answer:-$2}"
    else
        printf '%s' "$2"
    fi
}

rand_hex() {
    if have openssl; then
        openssl rand -hex 32
    else
        od -An -N32 -tx1 /dev/urandom | tr -d ' \n'
        echo
    fi
}

# Einrichtungscode: 24 Zeichen (rund 119 Bit) ohne verwechselbare Zeichen
# (0/O, 1/I/L), in Vierergruppen, wie deploy/pi/setup-pi.sh.
setup_code() {
    LC_ALL=C tr -dc 'ABCDEFGHJKMNPQRSTUVWXYZ23456789' </dev/urandom 2>/dev/null \
        | head -c 24 | sed 's/\(....\)/\1-/g; s/-$//'
}

slugify() {
    slug=$(printf '%s' "$1" \
        | sed 's/Ä/ae/g; s/Ö/oe/g; s/Ü/ue/g; s/ä/ae/g; s/ö/oe/g; s/ü/ue/g; s/ß/ss/g' \
        | tr 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' 'abcdefghijklmnopqrstuvwxyz' \
        | LC_ALL=C tr -c 'a-z0-9' '-' | tr -s '-' | sed 's/^-//; s/-$//' | cut -c1-50 | sed 's/-$//')
    printf '%s' "${slug:-rettungswache}"
}

# --- .env lesen und schreiben (ohne sed -i, damit GNU und BSD gleich laufen) ---
ENV_FILE=""

env_has() { [ -f "$ENV_FILE" ] && grep -q "^$1=" "$ENV_FILE"; }

env_get() {  # Wert ohne umschließende Anführungszeichen
    [ -f "$ENV_FILE" ] || return 0
    value=$(sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1)
    case "$value" in
        \'*\') value=${value#\'}; value=${value%\'} ;;
        \"*\") value=${value#\"}; value=${value%\"} ;;
    esac
    printf '%s' "$value"
}

env_set() {  # env_set KEY VALUE  (ersetzt oder hängt an)
    if env_has "$1"; then
        tmp="$ENV_FILE.tmp.$$"
        K="$1" V="$2" awk 'BEGIN { k = ENVIRON["K"]; v = ENVIRON["V"] }
            index($0, k "=") == 1 { print k "=" v; next } { print }' "$ENV_FILE" >"$tmp"
        cat "$tmp" >"$ENV_FILE"
        rm -f "$tmp"
    else
        printf '%s=%s\n' "$1" "$2" >>"$ENV_FILE"
    fi
}

env_default() {  # nur setzen, wenn der Schlüssel fehlt
    env_has "$1" || env_set "$1" "$2"
}

# Schlüssel, die mit einem Beispiel-Platzhalter (replace-...) oder leer
# vorliegen, gelten als fehlend und bekommen einen Zufallswert.
env_secret() {
    current=$(env_get "$1")
    case "$current" in
        ''|replace-*) env_set "$1" "$(rand_hex)" ;;
    esac
}

download() {  # download URL ZIEL
    tmp="$2.download.$$"
    if have curl; then
        curl -fsSL --retry 3 --connect-timeout 15 -o "$tmp" "$1" || { rm -f "$tmp"; return 1; }
    elif have wget; then
        wget -q -O "$tmp" "$1" || { rm -f "$tmp"; return 1; }
    else
        die "Weder curl noch wget gefunden."
    fi
    mv "$tmp" "$2"
}

fetch() {  # fetch REPO_PFAD ZIEL [ausführbar]
    mkdir -p "$(dirname "$2")"
    if [ -n "$SOURCE" ]; then
        [ -f "$SOURCE/$1" ] || die "$SOURCE/$1 fehlt."
        cp "$SOURCE/$1" "$2.copy.$$"
        mv "$2.copy.$$" "$2"
    else
        download "$BASE_URL/$REF/$1" "$2" || die "Download fehlgeschlagen: $BASE_URL/$REF/$1"
    fi
    [ -z "${3:-}" ] || chmod 755 "$2"
}

port_in_use() {
    if have ss; then
        ss -Hltn 2>/dev/null | awk '{ print $4 }' | grep -Eq "[:.]$1\$"
    elif have lsof; then
        lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
    elif have nc; then
        nc -z 127.0.0.1 "$1" >/dev/null 2>&1
    else
        return 1
    fi
}

http_ok() {  # http_ok URL -> 0 bei HTTP 2xx
    if have curl; then
        curl -fsS --max-time 5 -o /dev/null "$1" 2>/dev/null
    elif have wget; then
        wget -q -T 5 -O /dev/null "$1" 2>/dev/null
    else
        return 2
    fi
}

dc() { docker compose "$@"; }

# --- 1. Vorprüfung ---------------------------------------------------------
say "Vorprüfung"
OS=$(uname -s)
case "$OS" in
    Linux|Darwin) ;;
    *) die "Nicht unterstütztes Betriebssystem: $OS (Linux oder macOS nötig)." ;;
esac

have docker || die "Docker fehlt. Linux: https://docs.docker.com/engine/install/ – macOS: Docker Desktop, OrbStack oder Colima."
if ! docker info >/dev/null 2>&1; then
    if docker info 2>&1 | grep -qi 'permission denied'; then
        die "Kein Zugriff auf Docker. Mit sudo starten oder den Benutzer zur Gruppe docker hinzufügen (sudo usermod -aG docker \$USER, danach neu anmelden)."
    fi
    die "Docker läuft nicht (docker info schlägt fehl). Docker starten und erneut versuchen."
fi
docker compose version >/dev/null 2>&1 \
    || die "Docker Compose v2 fehlt (Befehl 'docker compose'). Paket docker-compose-plugin installieren."
compose_version=$(docker compose version --short 2>/dev/null | sed 's/^v//')
compose_major=$(printf '%s' "$compose_version" | cut -d. -f1)
compose_minor=$(printf '%s' "$compose_version" | cut -d. -f2)
case "$compose_major$compose_minor" in
    ''|*[!0-9]*) warn "Compose-Version nicht erkennbar ($compose_version)." ;;
    *)
        if [ "$compose_major" -lt "$MIN_COMPOSE_MAJOR" ] \
            || { [ "$compose_major" -eq "$MIN_COMPOSE_MAJOR" ] && [ "$compose_minor" -lt "$MIN_COMPOSE_MINOR" ]; }; then
            die "Docker Compose $compose_version ist zu alt; mindestens $MIN_COMPOSE_MAJOR.$MIN_COMPOSE_MINOR nötig."
        fi
        ;;
esac
info "Docker $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo '?'), Compose $compose_version"

arch=$(docker info --format '{{.Architecture}}' 2>/dev/null || uname -m)
case "$arch" in
    x86_64|amd64) arch=amd64 ;;
    aarch64|arm64) arch=arm64 ;;
    *) die "Architektur $arch wird nicht unterstützt (amd64 oder arm64 nötig; Raspberry Pi: 64-Bit-System installieren)." ;;
esac
info "Architektur $arch"

mem_bytes=$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)
case "$mem_bytes" in ''|*[!0-9]*) mem_bytes=0 ;; esac
mem_mb=$((mem_bytes / 1048576))
if [ "$mem_mb" -gt 0 ]; then
    info "Arbeitsspeicher für Docker: ${mem_mb} MB"
    if [ "$mem_mb" -lt 900 ]; then
        warn "Weniger als 1 GB RAM für Docker – der Start kann scheitern."
    elif [ "$mem_mb" -lt 1800 ]; then
        warn "Unter 2 GB RAM: Betrieb möglich, für viele Geräte knapp."
    fi
fi

# --- 2. Zielordner ---------------------------------------------------------
if [ -z "$TARGET_DIR" ]; then
    if [ "$OS" = "Darwin" ]; then TARGET_DIR="$HOME/wachbuch"; else TARGET_DIR="/opt/wachbuch"; fi
fi
if ! mkdir -p "$TARGET_DIR" 2>/dev/null || [ ! -w "$TARGET_DIR" ]; then
    die "Zielordner $TARGET_DIR ist nicht beschreibbar. Mit sudo starten oder --dir \$HOME/wachbuch angeben."
fi
TARGET_DIR=$(cd "$TARGET_DIR" && pwd)
ENV_FILE="$TARGET_DIR/.env"
info "Zielordner $TARGET_DIR"

free_kb=$(df -Pk "$TARGET_DIR" 2>/dev/null | awk 'NR == 2 { print $4 }')
case "$free_kb" in ''|*[!0-9]*) free_kb=0 ;; esac
if [ "$free_kb" -gt 0 ] && [ "$free_kb" -lt 3000000 ]; then
    warn "Weniger als 3 GB frei in $TARGET_DIR (Images, Datenbank, Backups)."
fi

if [ -n "$SOURCE" ]; then
    [ -d "$SOURCE" ] || die "--source $SOURCE ist kein Ordner."
    SOURCE=$(cd "$SOURCE" && pwd)
    [ -f "$SOURCE/docker-compose.yml" ] || die "$SOURCE enthält keine docker-compose.yml."
fi
if [ "$BUILD" -eq 1 ] && [ -z "$SOURCE" ]; then
    die "--build braucht --source mit einem Checkout des Repositorys."
fi

# --- 3. Einstellungen festlegen --------------------------------------------
FRESH_ENV=0
[ -f "$ENV_FILE" ] || FRESH_ENV=1
OLD_MODE=$(env_get WACHBUCH_MODE)
OLD_HOST=$(env_get WACHBUCH_HOSTNAME)
OLD_PORT=$(env_get HTTP_PORT)
OLD_HTTPS_PORT=$(env_get HTTPS_PORT)
OLD_EMAIL=$(env_get CADDY_TLS)
case "$OLD_EMAIL" in *@*) ;; *) OLD_EMAIL="" ;; esac

say "Einstellungen"
NAME="$OPT_NAME"
if [ -z "$NAME" ]; then
    NAME=$(env_get DEFAULT_STATION_NAME)
    if [ -z "$NAME" ] || [ "$FRESH_ENV" -eq 1 ]; then
        NAME=$(ask "Name der Wache" "${NAME:-Rettungswache}")
    fi
fi
# In .env einfach gequotet; Hochkomma und Backslash nicht zulassen.
NAME=$(printf '%s' "$NAME" | tr -d "'\\\\" | tr -d '\n\r')
[ -n "$NAME" ] || NAME="Rettungswache"

MODE="$OPT_MODE"
if [ -z "$MODE" ]; then
    MODE="$OLD_MODE"
    if [ -z "$MODE" ]; then
        if [ "$INTERACTIVE" -eq 1 ]; then
            printf '\n  Betriebsart:\n    1) local  - nur auf diesem Rechner (http://localhost)\n    2) lan    - im Netz der Wache per HTTPS mit eigenem Zertifikat\n    3) domain - öffentliche Domain mit Let'"'"'s-Encrypt-Zertifikat\n' >/dev/tty
        fi
        choice=$(ask "Betriebsart (1-3)" "1")
        case "$choice" in
            1|local) MODE=local ;;
            2|lan) MODE=lan ;;
            3|domain) MODE=domain ;;
            *) die "Unbekannte Betriebsart: $choice" ;;
        esac
    fi
fi
case "$MODE" in local|lan|domain) ;; *) die "--mode muss local, lan oder domain sein." ;; esac

PORT="${OPT_PORT:-${OLD_PORT:-8090}}"
is_port "$PORT" || die "Ungültiger Port: $PORT"
HTTPS_PORT="${OPT_HTTPS_PORT:-${OLD_HTTPS_PORT:-443}}"
is_port "$HTTPS_PORT" || die "Ungültiger HTTPS-Port: $HTTPS_PORT"
HTTP_REDIRECT_PORT="${OPT_HTTP_PORT:-$(env_get HTTP_REDIRECT_PORT)}"
HTTP_REDIRECT_PORT="${HTTP_REDIRECT_PORT:-80}"
is_port "$HTTP_REDIRECT_PORT" || die "Ungültiger HTTP-Port: $HTTP_REDIRECT_PORT"

detect_ip() {
    ip=""
    if [ "$OS" = "Darwin" ]; then
        for iface in en0 en1; do
            ip=$(ipconfig getifaddr "$iface" 2>/dev/null || true)
            [ -z "$ip" ] || break
        done
    else
        ip=$(hostname -I 2>/dev/null | awk '{ print $1 }' || true)
    fi
    printf '%s' "$ip"
}

HOST="$OPT_HOST"
EMAIL="$OPT_EMAIL"
case "$MODE" in
    local)
        HOST=localhost
        ;;
    lan)
        if [ -z "$HOST" ]; then
            HOST="$OLD_HOST"
            [ -n "$HOST" ] && [ "$HOST" != "localhost" ] || HOST=$(ask "Hostname oder IP-Adresse im Wachen-Netz" "$(detect_ip)")
        fi
        ;;
    domain)
        if [ -z "$HOST" ]; then
            HOST="$OLD_HOST"
            [ -n "$HOST" ] && [ "$HOST" != "localhost" ] || HOST=$(ask "Domain (z. B. wache.example.org)" "")
        fi
        if [ -z "$EMAIL" ]; then
            EMAIL="$OLD_EMAIL"
            [ -n "$EMAIL" ] || EMAIL=$(ask "E-Mail für Let's Encrypt" "")
        fi
        case "$EMAIL" in *@*.*) ;; *) die "Für --mode domain ist eine gültige --email nötig." ;; esac
        is_ipv4 "$HOST" && die "Let's Encrypt stellt keine Zertifikate für IP-Adressen aus; --mode lan verwenden."
        ;;
esac
HOST=$(printf '%s' "$HOST" | tr 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' 'abcdefghijklmnopqrstuvwxyz')
is_hostname "$HOST" || die "Ungültiger Hostname/IP: '$HOST' (ohne http:// und ohne Pfad angeben)."

if [ "$OS" = "Darwin" ] && [ "$MODE" != "local" ]; then
    case "$TARGET_DIR/" in
        "$HOME"/*) ;;
        *) warn "macOS: Docker Desktop/Colima geben meist nur das Benutzerverzeichnis frei. Der Proxy bindet deploy/caddy/Caddyfile aus $TARGET_DIR ein – liegt der Ordner außerhalb von $HOME, scheitert der Start." ;;
    esac
fi

info "Wache:      $NAME"
info "Betriebsart: $MODE"
[ "$MODE" = "local" ] || info "Adresse:    $HOST"

# Version und Download-Quelle
BASE_URL="${BASE_URL:-$(env_get WACHBUCH_BASE_URL)}"
BASE_URL="${BASE_URL:-$DEFAULT_BASE_URL}"
VERSION=$(printf '%s' "${OPT_VERSION:-$(env_get WACHBUCH_VERSION)}" | sed 's/^v//')
if [ -z "$VERSION" ] && [ -z "$SOURCE" ]; then
    latest=""
    if have curl; then
        latest=$(curl -fsSL --max-time 15 "https://api.github.com/repos/${REPO_SLUG}/releases/latest" 2>/dev/null \
            | sed -n 's/.*"tag_name": *"v\{0,1\}\([0-9][0-9.]*\)".*/\1/p' | head -n 1 || true)
    fi
    VERSION="${latest:-latest}"
fi
VERSION="${VERSION:-latest}"
case "$VERSION" in
    latest) REF=main ;;
    *[!0-9.]*) die "Ungültige Version: $VERSION (Format X.Y.Z)" ;;
    *) REF="v$VERSION" ;;
esac
if [ "$BUILD" -eq 1 ]; then
    info "Images:     lokal gebaut aus $SOURCE"
else
    info "Version:    $VERSION"
fi

# --- 4. Dateien holen ------------------------------------------------------
say "Dateien nach $TARGET_DIR"
cd "$TARGET_DIR"
fetch docker-compose.yml compose.yml
fetch deploy/caddy/Caddyfile deploy/caddy/Caddyfile
fetch scripts/wachbuch wachbuch exec
if [ "$BUILD" -eq 1 ]; then
    fetch compose.build.yml compose.build.yml
fi
info "compose.yml, deploy/caddy/Caddyfile, wachbuch$( [ "$BUILD" -eq 0 ] || echo ', compose.build.yml')"

# --- 5. .env ---------------------------------------------------------------
say "Konfiguration (.env)"
umask 077
if [ "$FRESH_ENV" -eq 1 ]; then
    {
        echo "# Wachbuch-Konfiguration, erzeugt von install.sh am $(date '+%Y-%m-%d %H:%M')."
        echo "# Enthält alle Schlüssel: offline sichern (z. B. USB-Stick im Tresor)."
        echo "# Ohne diese Datei sind Datenbank und Backups nicht mehr nutzbar."
    } >"$ENV_FILE"
    info ".env neu angelegt"
else
    cp "$ENV_FILE" "$ENV_FILE.bak"
    info ".env vorhanden – Geheimnisse bleiben, fehlende Schlüssel werden ergänzt (Kopie: .env.bak)"
fi
chmod 600 "$ENV_FILE"

# Installationsdaten
env_set WACHBUCH_VERSION "$VERSION"
env_default WACHBUCH_BASE_URL "$BASE_URL"
[ -z "$PROJECT" ] || env_set COMPOSE_PROJECT_NAME "$PROJECT"
if [ "$BUILD" -eq 1 ]; then
    env_set COMPOSE_FILE "compose.yml:compose.build.yml"
    env_set WACHBUCH_SOURCE "$SOURCE"
elif [ -n "$SOURCE" ]; then
    env_set WACHBUCH_SOURCE "$SOURCE"
fi

# Datenbankrollen
env_default POSTGRES_DB rwsth
env_default POSTGRES_USER rwsth_owner
env_default APP_DB_USER rwsth_app
env_default FEED_DB_USER rwsth_feed
env_default BACKUP_DB_USER rwsth_backup
env_default PUSH_DB_USER rwsth_push

# Geheimnisse: unabhängige Zufallswerte, bestehende bleiben unverändert.
for key in DJANGO_SECRET_KEY POSTGRES_PASSWORD APP_DB_PASSWORD FEED_DB_PASSWORD \
    BACKUP_DB_PASSWORD PUSH_DB_PASSWORD FEED_WORKER_SECRET_KEY PUSH_WORKER_SECRET_KEY \
    CRYPTO_MASTER_KEY RATELIMIT_KEY_SALT; do
    env_secret "$key"
done
if ! env_has SETUP_BOOTSTRAP_TOKEN; then
    env_set SETUP_BOOTSTRAP_TOKEN "$(setup_code)"
fi

# Wache
if [ -n "$OPT_NAME" ] || ! env_has DEFAULT_STATION_NAME; then
    env_set DEFAULT_STATION_NAME "'$NAME'"
    env_set DEFAULT_STATION_SLUG "$(slugify "$NAME")"
fi
env_default DEFAULT_STATION_SLUG "$(slugify "$NAME")"
env_default DJANGO_DEBUG false
env_default MFA_ENABLED true
env_default DEMO_MODE false
env_default HTTP_BIND_ADDRESS 127.0.0.1

# Netz- und Proxy-Einstellungen aus der Betriebsart ableiten.
if [ "$MODE" = "local" ]; then
    ORIGIN="http://localhost:$PORT"
elif [ "$HTTPS_PORT" = "443" ]; then
    ORIGIN="https://$HOST"
else
    ORIGIN="https://$HOST:$HTTPS_PORT"
fi
case "$MODE" in
    local)
        D_ALLOWED="localhost,127.0.0.1"
        D_CSRF="http://localhost:$PORT,http://127.0.0.1:$PORT"
        D_SECURE=false; D_PROXY=false
        D_WEBAUTHN=true; D_RP_ID=localhost; D_RP_ORIGIN="$ORIGIN"
        D_PROFILES=""; D_TLS=internal
        ;;
    lan)
        D_ALLOWED="$HOST,localhost,127.0.0.1"
        D_CSRF="$ORIGIN"
        D_SECURE=true; D_PROXY=true
        # Passkeys brauchen ein Zertifikat, dem die Geräte ohne Import vertrauen.
        D_WEBAUTHN=false; D_RP_ID=""; D_RP_ORIGIN=""
        D_PROFILES=https; D_TLS=internal
        ;;
    domain)
        D_ALLOWED="$HOST,localhost,127.0.0.1"
        D_CSRF="$ORIGIN"
        D_SECURE=true; D_PROXY=true
        D_WEBAUTHN=true; D_RP_ID="$HOST"; D_RP_ORIGIN="$ORIGIN"
        D_PROFILES=https; D_TLS="$EMAIL"
        ;;
esac

# Bei geänderter Betriebsart/Adresse/Port die abgeleiteten Werte neu setzen,
# sonst nur fehlende ergänzen (von Hand angepasste Werte bleiben erhalten).
REWRITE=0
if [ "$FRESH_ENV" -eq 1 ]; then
    REWRITE=1
elif [ -n "$OLD_MODE" ]; then
    if [ "$MODE" != "$OLD_MODE" ] || [ "$HOST" != "$OLD_HOST" ] || [ "$PORT" != "$OLD_PORT" ] \
        || [ "$HTTPS_PORT" != "${OLD_HTTPS_PORT:-443}" ] || { [ "$MODE" = "domain" ] && [ "$EMAIL" != "$OLD_EMAIL" ]; }; then
        REWRITE=1
        info "Betriebsart oder Adresse geändert – Netzwerkeinstellungen werden neu gesetzt."
    fi
elif [ -n "$OPT_MODE" ]; then
    REWRITE=1
fi
put() { if [ "$REWRITE" -eq 1 ]; then env_set "$1" "$2"; else env_default "$1" "$2"; fi; }
put WACHBUCH_MODE "$MODE"
put WACHBUCH_HOSTNAME "$HOST"
put HTTP_PORT "$PORT"
put HTTPS_PORT "$HTTPS_PORT"
put HTTP_REDIRECT_PORT "$HTTP_REDIRECT_PORT"
put ALLOWED_HOSTS "$D_ALLOWED"
put CSRF_TRUSTED_ORIGINS "$D_CSRF"
put SITE_URL "$ORIGIN"
put SECURE_COOKIES "$D_SECURE"
put TRUSTED_PROXY "$D_PROXY"
put WEBAUTHN_ENABLED "$D_WEBAUTHN"
put WEBAUTHN_RP_ID "$D_RP_ID"
put WEBAUTHN_ORIGIN "$D_RP_ORIGIN"
put COMPOSE_PROFILES "$D_PROFILES"
put CADDY_TLS "$D_TLS"
chmod 600 "$ENV_FILE"
info "Schlüssel gesetzt, Rechte 600"

if [ "$NO_START" -eq 1 ]; then
    say "Fertig (ohne Start). Starten mit: $TARGET_DIR/wachbuch start"
    exit 0
fi

# --- 6. Ports prüfen (nicht, wenn diese Installation schon läuft) ----------
if [ -z "$(dc ps -q 2>/dev/null)" ]; then
    ports="$PORT"
    [ "$MODE" = "local" ] || ports="$ports $HTTPS_PORT $HTTP_REDIRECT_PORT"
    for p in $ports; do
        if port_in_use "$p"; then
            die "Port $p ist belegt. Anderen Port wählen (--port / --https-port / --http-port) oder den Dienst beenden."
        fi
    done
fi

# --- 7. Images und Start ---------------------------------------------------
if [ "$BUILD" -eq 1 ]; then
    say "Images lokal bauen (beim ersten Mal einige Minuten)"
    dc build
else
    say "Images herunterladen"
    dc pull --quiet || die "Images konnten nicht geladen werden (Internet? Version $VERSION vorhanden?)."
fi

say "Wachbuch starten (wartet, bis alle Dienste gesund sind)"
if ! dc up -d --remove-orphans --wait --wait-timeout 600; then
    dc ps -a || true
    dc logs --tail 40 --no-color || true
    die "Start fehlgeschlagen. Logs oben; Hilfe: $TARGET_DIR/wachbuch logs"
fi

say "Healthcheck"
health_url="http://127.0.0.1:$PORT/healthz/"
attempt=0
until http_ok "$health_url"; do
    status=$?
    if [ "$status" -eq 2 ]; then
        dc exec -T web python -c "import urllib.request as u; u.urlopen(u.Request('http://127.0.0.1:8000/healthz/', headers={'Host': 'localhost'}), timeout=5)" \
            && break
    fi
    attempt=$((attempt + 1))
    [ "$attempt" -lt 60 ] || die "$health_url antwortet nicht. Logs: $TARGET_DIR/wachbuch logs web"
    sleep 2
done
info "$health_url antwortet"

CODE=$(env_get SETUP_BOOTSTRAP_TOKEN)
cat <<EOF

Fertig. Das Wachbuch läuft.

  Adresse:           $ORIGIN/
  Ersteinrichtung:   $ORIGIN/setup/
  Einrichtungscode:  ${CODE:-(bereits verwendet)}

  Verwaltung:        $TARGET_DIR/wachbuch status | logs | backup | update | help

WICHTIG: $ENV_FILE enthält alle Schlüssel. Offline sichern
(z. B. USB-Stick im Tresor). Ohne diese Datei sind Datenbank und Backups
nicht mehr nutzbar. Nach der Ersteinrichtung SETUP_BOOTSTRAP_TOKEN in .env
leeren und "$TARGET_DIR/wachbuch start" ausführen.
EOF
case "$MODE" in
    lan)
        cat <<EOF

Hinweis LAN: Das Zertifikat stammt von der eigenen Caddy-CA. Geräte zeigen eine
Warnung, bis die CA importiert ist:
  cd $TARGET_DIR && docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt wachbuch-ca.crt
EOF
        ;;
    domain)
        cat <<EOF

Hinweis Domain: $HOST muss per DNS auf diesen Server zeigen und die Ports
$HTTP_REDIRECT_PORT/$HTTPS_PORT müssen aus dem Internet erreichbar sein, sonst
schlägt das Let's-Encrypt-Zertifikat fehl (Logs: wachbuch logs caddy).
EOF
        ;;
esac
