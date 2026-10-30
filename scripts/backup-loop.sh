#!/bin/sh
# PostgreSQL-Dumps des Wachbuchs (Dienst "backup", read-only Container).
#
#   rwsth-backup-loop          Dauerschleife: ein Dump je BACKUP_INTERVAL_SECONDS
#   rwsth-backup-loop once     genau ein Dump, z. B. für "wachbuch backup/update"
#
# Fehler beenden die Schleife nie: ein Neustart des Containers würde sonst
# sofort den nächsten Dump auslösen (Dump-Sturm). Stattdessen wird nach
# BACKUP_RETRY_SECONDS erneut versucht. Nach einem Neustart wird erst gedumpt,
# wenn der letzte Dump älter als das Intervall ist.
set -u

BACKUP_DIR="${BACKUP_DIR:-/backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
BACKUP_INTERVAL_SECONDS="${BACKUP_INTERVAL_SECONDS:-86400}"
BACKUP_RETRY_SECONDS="${BACKUP_RETRY_SECONDS:-3600}"
# Öffentliche GnuPG-Schlüssel (*.asc, *.gpg, *.pub) als read-only Mount.
BACKUP_GPG_KEY_DIR="${BACKUP_GPG_KEY_DIR:-/run/backup-gpg}"
# Der Container ist read-only; der Schlüsselbund liegt im tmpfs.
GNUPGHOME="${GNUPGHOME:-/tmp/gnupg}"
export GNUPGHOME

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
err() { log "FEHLER: $*" >&2; }

is_number() {
    case "$1" in
        ''|*[!0-9]*) return 1 ;;
        *) return 0 ;;
    esac
}

prepare_gpg() {
    if [ -z "${BACKUP_GPG_RECIPIENT:-}" ]; then
        err "BACKUP_ENCRYPT_REMOTE=true erfordert BACKUP_GPG_RECIPIENT."
        return 1
    fi
    mkdir -p "$GNUPGHOME" && chmod 700 "$GNUPGHOME" || return 1
    for key in "$BACKUP_GPG_KEY_DIR"/*.asc "$BACKUP_GPG_KEY_DIR"/*.gpg "$BACKUP_GPG_KEY_DIR"/*.pub; do
        [ -f "$key" ] || continue
        gpg --batch --quiet --import "$key" 2>/dev/null \
            || err "Schlüssel $key konnte nicht importiert werden."
    done
    if ! gpg --batch --list-keys "$BACKUP_GPG_RECIPIENT" >/dev/null 2>&1; then
        err "Kein öffentlicher Schlüssel für $BACKUP_GPG_RECIPIENT gefunden. Schlüsseldatei in den Ordner BACKUP_GPG_KEY_DIR (Host) legen."
        return 1
    fi
    warn_if_aead_key || true
}

# GnuPG ab 2.3 verschlüsselt im AEAD-Format (OCB-Paket), sobald der Schlüssel
# dieses Merkmal ankündigt (Voreinstellung neuer Schlüssel ab 2.3). GnuPG 2.2
# (Debian 12) und andere OpenPGP-Programme können solche Dateien nicht öffnen.
# Keine gpg-Option schaltet das beim Verschlüsseln ab (geprüft mit 2.4.4:
# --rfc4880, --openpgp, --compliance=openpgp, --personal-aead-preferences);
# Abhilfe nur am Schlüssel, siehe docs/HETZNER.md, Abschnitt 0.
warn_if_aead_key() {
    features=$(gpg --batch --export "$BACKUP_GPG_RECIPIENT" 2>/dev/null \
        | gpg --batch --list-packets 2>/dev/null \
        | sed -n 's/.*(features: \([0-9A-Fa-f][0-9A-Fa-f]\).*/\1/p')
    for byte in $features; do
        case "$byte" in
            # Bit 0x02 im ersten Merkmal-Byte = AEAD
            ?[2367ABEFabef])
                log "Hinweis: Schlüssel $BACKUP_GPG_RECIPIENT kündigt AEAD an; die verschlüsselten Backups lassen sich nur mit GnuPG 2.3 oder neuer öffnen (nicht mit Debian 12). Abhilfe: docs/HETZNER.md, Abschnitt 0."
                return 0
                ;;
        esac
    done
    return 0
}

encrypt_dump() {
    gpg --batch --yes --trust-model always \
        --compress-algo none \
        --cipher-algo AES256 \
        --recipient "$BACKUP_GPG_RECIPIENT" \
        --output "$2" \
        --encrypt "$1"
}

upload_offsite() {
    dump_path="$1"
    if [ -z "${BACKUP_OFF_TARGET:-}" ]; then
        return 0
    fi
    payload="$dump_path"
    if [ "${BACKUP_ENCRYPT_REMOTE:-false}" = "true" ]; then
        # Ohne funktionierende Verschlüsselung niemals Klartext auslagern.
        prepare_gpg || return 1
        if ! encrypt_dump "$dump_path" "${dump_path}.gpg"; then
            rm -f "${dump_path}.gpg"
            err "Verschlüsselung fehlgeschlagen; Offsite-Kopie übersprungen."
            return 1
        fi
        payload="${dump_path}.gpg"
    fi
    case "$BACKUP_OFF_TARGET" in
        file://*)
            destination="${BACKUP_OFF_TARGET#file://}"
            if [ ! -d "$destination" ] || [ ! -w "$destination" ]; then
                err "Offsite-Ziel $destination fehlt oder ist nicht beschreibbar (BACKUP_OFFSITE_DIR gemountet? Besitzer UID ${BACKUP_UID:-70}?)."
                return 1
            fi
            name="$(basename "$payload")"
            if ! cp "$payload" "$destination/.${name}.tmp" || ! mv "$destination/.${name}.tmp" "$destination/$name"; then
                rm -f "$destination/.${name}.tmp"
                err "Kopie nach $destination fehlgeschlagen."
                return 1
            fi
            ;;
        *)
            err "Unbekanntes BACKUP_OFF_TARGET-Schema: $BACKUP_OFF_TARGET (erlaubt: file://)"
            return 1
            ;;
    esac
    log "Offsite-Kopie nach $BACKUP_OFF_TARGET abgeschlossen ($(basename "$payload"))."
}

prune_old_dumps() {
    # 0 deaktiviert die lokale Aufbewahrung (Ringe bleiben unverändert).
    is_number "$BACKUP_RETENTION_DAYS" || { err "BACKUP_RETENTION_DAYS ist keine Zahl."; return 1; }
    [ "$BACKUP_RETENTION_DAYS" -gt 0 ] || return 0
    find "$BACKUP_DIR" -type f \
        \( -name 'rwsth-*.dump' -o -name 'rwsth-*.dump.gpg' \) \
        -mtime +"$BACKUP_RETENTION_DAYS" -delete
}

create_dump() {
    timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
    temporary="$BACKUP_DIR/.rwsth-${timestamp}.dump.tmp"
    target="$BACKUP_DIR/rwsth-${timestamp}.dump"
    if ! pg_dump \
        --host "$PGHOST" \
        --username "$PGUSER" \
        --dbname "$PGDATABASE" \
        --format custom \
        --no-owner \
        --no-acl \
        --file "$temporary"; then
        rm -f "$temporary"
        err "pg_dump fehlgeschlagen."
        return 1
    fi
    mv "$temporary" "$target" || return 1
    chmod 0600 "$target"
    log "Backup erstellt: $target ($(du -h "$target" | cut -f1))"
    LAST_DUMP="$target"
}

run_once() {
    create_dump || return 1
    upload_offsite "$LAST_DUMP" || err "Offsite-Kopie fehlgeschlagen; lokaler Dump bleibt erhalten."
    prune_old_dumps || true
    return 0
}

# Alter des neuesten Dumps in Sekunden, -1 wenn keiner existiert.
latest_dump_age() {
    newest="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'rwsth-*.dump' 2>/dev/null | sort | tail -n 1)"
    if [ -z "$newest" ]; then
        echo -1
        return
    fi
    echo $(( $(date +%s) - $(stat -c %Y "$newest") ))
}

pause() {
    # Im Hintergrund schlafen, damit SIGTERM sofort beendet.
    sleep "$1" &
    wait $!
}

mkdir -p "$BACKUP_DIR"

if [ "${1:-}" = "once" ]; then
    run_once || exit 1
    echo "BACKUP_FILE=$LAST_DUMP"
    exit 0
fi

trap 'log "Backup-Dienst beendet."; exit 0' TERM INT
is_number "$BACKUP_INTERVAL_SECONDS" || { err "BACKUP_INTERVAL_SECONDS ist keine Zahl, nutze 86400."; BACKUP_INTERVAL_SECONDS=86400; }
is_number "$BACKUP_RETRY_SECONDS" || BACKUP_RETRY_SECONDS=3600
if [ "${BACKUP_ENCRYPT_REMOTE:-false}" = "true" ] && [ -n "${BACKUP_OFF_TARGET:-}" ]; then
    prepare_gpg || err "Offsite-Kopien werden übersprungen, bis der Schlüssel verfügbar ist."
fi

while true; do
    age="$(latest_dump_age)"
    if [ "$age" -ge 0 ] && [ "$age" -lt "$BACKUP_INTERVAL_SECONDS" ]; then
        remaining=$((BACKUP_INTERVAL_SECONDS - age))
        log "Letztes Backup ist ${age} s alt; nächstes in ${remaining} s."
        pause "$remaining"
        continue
    fi
    if ! run_once; then
        err "Neuer Versuch in ${BACKUP_RETRY_SECONDS} s."
        pause "$BACKUP_RETRY_SECONDS"
    fi
done
