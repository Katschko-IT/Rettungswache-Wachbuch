#!/bin/sh
# Kopiert die verschlüsselten Backups auf die Storage Box (offsite-storagebox.sh
# installiert das Skript als /usr/local/bin/wachwerk-offsite-sync; Timer
# stündlich). Einstellungen: /etc/wachwerk/offsite.env.
#
# Auf der Storage Box wird nie etwas gelöscht, nur weil es hier fehlt (kein
# rsync --delete): Ein neu aufgesetzter oder geleerter Server darf den Bestand
# außer Haus nicht vernichten. Alte Kopien entfernt der Lauf nach dem
# Zeitstempel im Dateinamen (älter als OFFSITE_KEEP_DAYS) und behält dabei
# immer die OFFSITE_KEEP_MIN neuesten.
set -eu

CONF_DIR="${WACHWERK_CONF_DIR:-/etc/wachwerk}"
STATE_DIR="${WACHWERK_STATE_DIR:-/var/lib/wachwerk}"
# shellcheck disable=SC1091
. "$CONF_DIR/offsite.env"
OFFSITE_KEEP_MIN="${OFFSITE_KEEP_MIN:-7}"
case "$OFFSITE_KEEP_DAYS$OFFSITE_KEEP_MIN" in ''|*[!0-9]*) echo "OFFSITE_KEEP_DAYS/OFFSITE_KEEP_MIN müssen Zahlen sein." >&2; exit 1 ;; esac

BOX="${OFFSITE_TARGET%%:*}"
REMOTE_DIR="${OFFSITE_TARGET#*:}"
REMOTE_DIR="${REMOTE_DIR%/}"
SSH_OPTS="-p 23 -i $OFFSITE_SSH_KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o BatchMode=yes -o ConnectTimeout=30 -o ServerAliveInterval=15 -o ServerAliveCountMax=4"
# -n: ssh darf die Dateiliste der Schleife unten nicht als Eingabe verbrauchen.
# shellcheck disable=SC2086 # SSH_OPTS sind bewusst einzelne Wörter
box() { ssh -n $SSH_OPTS "$BOX" "$@"; }

find "$OFFSITE_DIR" -maxdepth 1 -type f -name 'rwsth-*.dump.gpg' -mtime +"$OFFSITE_KEEP_DAYS" -delete
# Nur verschlüsselte Dateien verlassen den Server.
rsync -a --include='rwsth-*.dump.gpg' --exclude='*' -e "ssh $SSH_OPTS" "$OFFSITE_DIR/" "$OFFSITE_TARGET"
install -d -m 0700 "$STATE_DIR"
touch "$STATE_DIR/offsite-sync.ok"
echo "Offsite-Kopie abgeschlossen: $(find "$OFFSITE_DIR" -maxdepth 1 -name 'rwsth-*.dump.gpg' | wc -l) Dateien hier"

# Aufräumen auf der Storage Box (Namen: rwsth-JJJJMMTTThhmmssZ.dump.gpg, UTC).
cutoff="rwsth-$(date -u -d "-$OFFSITE_KEEP_DAYS days" +%Y%m%dT%H%M%SZ)"
if ! listing=$(box ls "$REMOTE_DIR" 2>/dev/null); then
    echo "Hinweis: Ordner $REMOTE_DIR auf der Storage Box nicht lesbar – alte Kopien bleiben liegen." >&2
    exit 0
fi
old=$(printf '%s\n' "$listing" | grep -E '^rwsth-[0-9]{8}T[0-9]{6}Z\.dump\.gpg$' | sort \
    | awk -v cutoff="$cutoff" -v keep="$OFFSITE_KEEP_MIN" '
        { name[NR] = $0 }
        END { for (i = 1; i <= NR - keep; i++) if (name[i] < cutoff) print name[i] }')
for name in $old; do
    if box rm "$REMOTE_DIR/$name" >/dev/null 2>&1; then
        echo "Auf der Storage Box entfernt (älter als $OFFSITE_KEEP_DAYS Tage): $name"
    else
        echo "Hinweis: $name auf der Storage Box nicht löschbar." >&2
    fi
done
