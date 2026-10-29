#!/bin/sh
# Verschlüsselte Backups außer Haus auf eine Hetzner Storage Box (docs/HETZNER.md).
#
#   sh offsite-storagebox.sh --storagebox u123456 --gpg-key wachwerk-backup.asc
#
# Ablauf:
#   1. Der Backup-Dienst verschlüsselt jeden Tages-Dump mit dem ÖFFENTLICHEN
#      GnuPG-Schlüssel und legt ihn in /var/lib/wachwerk-offsite ab.
#   2. Ein Timer kopiert den Ordner stündlich per rsync/SSH (Port 23) auf die
#      Storage Box. Dort liegen nur verschlüsselte Dateien.
#   3. Der private Schlüssel bleibt bei dir (nie auf dem Server). Ohne ihn kann
#      niemand die Backups lesen – auch Hetzner nicht.
set -eu

say() { printf '\n==> %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }
die() { printf 'Fehler: %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'EOF'
Aufruf: sh offsite-storagebox.sh --storagebox BENUTZER --gpg-key DATEI [Optionen]

  --storagebox BENUTZER  Storage-Box-Benutzer, z. B. u123456 (Host wird
                         u123456.your-storagebox.de) oder BENUTZER@HOST
  --gpg-key DATEI        öffentlicher GnuPG-Schlüssel (.asc) für die Backups
  --remote-dir NAME      Ordner auf der Storage Box (Standard: wachwerk)
  --keep-days N          verschlüsselte Kopien N Tage behalten (Standard 30)
  --dir PFAD             Wachwerk-Ordner (Standard /opt/wachbuch)
  -h, --help             diese Hilfe
EOF
}

BOX=""
GPG_KEY=""
REMOTE_DIR="wachwerk"
KEEP_DAYS=30
WACHWERK_DIR="/opt/wachbuch"
while [ $# -gt 0 ]; do
    case "$1" in
        --storagebox) [ $# -ge 2 ] || die "--storagebox braucht einen Wert."; BOX="$2"; shift ;;
        --gpg-key) [ $# -ge 2 ] || die "--gpg-key braucht einen Wert."; GPG_KEY="$2"; shift ;;
        --remote-dir) [ $# -ge 2 ] || die "--remote-dir braucht einen Wert."; REMOTE_DIR="$2"; shift ;;
        --keep-days) [ $# -ge 2 ] || die "--keep-days braucht einen Wert."; KEEP_DAYS="$2"; shift ;;
        --dir) [ $# -ge 2 ] || die "--dir braucht einen Wert."; WACHWERK_DIR="$2"; shift ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; die "Unbekannte Option: $1" ;;
    esac
    shift
done

[ "$(id -u)" -eq 0 ] || die "Bitte als root ausführen (sudo sh offsite-storagebox.sh ...)."
[ -n "$BOX" ] && [ -n "$GPG_KEY" ] || { usage >&2; die "--storagebox und --gpg-key sind nötig."; }
[ -f "$GPG_KEY" ] || die "$GPG_KEY nicht gefunden."
[ -f "$WACHWERK_DIR/.env" ] || die "$WACHWERK_DIR/.env fehlt – zuerst Wachwerk installieren."
case "$KEEP_DAYS" in ''|*[!0-9]*) die "--keep-days muss eine Zahl sein." ;; esac
case "$REMOTE_DIR" in ''|/*|*..*|*[!A-Za-z0-9._/-]*) die "Ungültiger --remote-dir: $REMOTE_DIR" ;; esac
case "$BOX" in
    *@*) BOX_USER="${BOX%@*}"; BOX_HOST="${BOX#*@}" ;;
    *) BOX_USER="$BOX"; BOX_HOST="$BOX.your-storagebox.de" ;;
esac
case "$BOX_USER$BOX_HOST" in *[!A-Za-z0-9.-]*) die "Ungültige Storage-Box-Angabe: $BOX" ;; esac

command -v gpg >/dev/null 2>&1 || { apt-get install -y -q gnupg >/dev/null; }
command -v rsync >/dev/null 2>&1 || { apt-get install -y -q rsync >/dev/null; }

# --- 1. Schlüssel prüfen und ablegen -------------------------------------------
say "GnuPG-Schlüssel"
if grep -q "PRIVATE KEY" "$GPG_KEY"; then
    die "$GPG_KEY enthält einen PRIVATEN Schlüssel. Auf den Server gehört nur der öffentliche (gpg --armor --export)."
fi
FPR=$(gpg --batch --show-keys --with-colons "$GPG_KEY" 2>/dev/null | awk -F: '/^fpr:/ { print $10; exit }')
[ -n "$FPR" ] || die "$GPG_KEY ist kein lesbarer öffentlicher GnuPG-Schlüssel."
install -d -m 0755 /etc/wachwerk/backup-gpg
install -m 0644 "$GPG_KEY" /etc/wachwerk/backup-gpg/backup.asc
info "Fingerprint $FPR"

# --- 2. Ordner und .env -----------------------------------------------------------
say "Offsite-Ordner und .env"
OFFSITE=/var/lib/wachwerk-offsite
install -d -m 0700 -o 70 -g 70 "$OFFSITE"
env_set() {
    if grep -q "^$1=" "$WACHWERK_DIR/.env"; then
        sed -i "s|^$1=.*|$1=$2|" "$WACHWERK_DIR/.env"
    else
        printf '%s=%s\n' "$1" "$2" >>"$WACHWERK_DIR/.env"
    fi
}
cp "$WACHWERK_DIR/.env" "$WACHWERK_DIR/.env.bak"
env_set BACKUP_OFFSITE_DIR "$OFFSITE"
env_set BACKUP_OFF_TARGET "file:///offsite"
env_set BACKUP_ENCRYPT_REMOTE "true"
env_set BACKUP_GPG_RECIPIENT "$FPR"
env_set BACKUP_GPG_KEY_DIR "/etc/wachwerk/backup-gpg"
chmod 600 "$WACHWERK_DIR/.env"
info "BACKUP_OFFSITE_DIR=$OFFSITE, verschlüsselt für $FPR"

# --- 3. SSH-Schlüssel für die Storage Box ------------------------------------------
say "SSH-Zugang zur Storage Box $BOX_USER@$BOX_HOST"
KEY=/root/.ssh/wachwerk_storagebox
install -d -m 0700 /root/.ssh
[ -f "$KEY" ] || ssh-keygen -q -t ed25519 -N "" -C "wachwerk-offsite@$(hostname)" -f "$KEY"
SSH="ssh -p 23 -i $KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o BatchMode=yes"
if ! $SSH "$BOX_USER@$BOX_HOST" ls >/dev/null 2>&1; then
    info "Schlüssel wird einmalig hinterlegt – dafür das Storage-Box-Passwort eingeben"
    info "(Hetzner Console > Storage Box > SSH-Support und externe Erreichbarkeit einschalten)."
    ssh -p 23 -o StrictHostKeyChecking=accept-new "$BOX_USER@$BOX_HOST" install-ssh-key <"$KEY.pub" \
        || die "Schlüssel konnte nicht hinterlegt werden."
    $SSH "$BOX_USER@$BOX_HOST" ls >/dev/null || die "Anmeldung mit dem Schlüssel klappt nicht."
fi
$SSH "$BOX_USER@$BOX_HOST" mkdir -p "$REMOTE_DIR" >/dev/null 2>&1 || true
info "Anmeldung mit Schlüssel funktioniert"

# --- 4. Sync-Dienst ------------------------------------------------------------------
say "Stündliche Kopie auf die Storage Box"
umask 077
cat >/etc/wachwerk/offsite.env <<EOF
# Wachwerk-Offsite (offsite-storagebox.sh)
OFFSITE_DIR=$OFFSITE
OFFSITE_KEEP_DAYS=$KEEP_DAYS
OFFSITE_TARGET=$BOX_USER@$BOX_HOST:$REMOTE_DIR/
OFFSITE_SSH_KEY=$KEY
EOF
cat >/usr/local/bin/wachwerk-offsite-sync <<'EOF'
#!/bin/sh
# Kopiert die verschlüsselten Backups auf die Storage Box (offsite-storagebox.sh).
set -eu
. /etc/wachwerk/offsite.env
find "$OFFSITE_DIR" -maxdepth 1 -type f -name 'rwsth-*.dump.gpg' -mtime +"$OFFSITE_KEEP_DAYS" -delete
# Nur verschlüsselte Dateien verlassen den Server.
rsync -a --delete --include='rwsth-*.dump.gpg' --exclude='*' \
    -e "ssh -p 23 -i $OFFSITE_SSH_KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o BatchMode=yes" \
    "$OFFSITE_DIR/" "$OFFSITE_TARGET"
install -d -m 0700 /var/lib/wachwerk
touch /var/lib/wachwerk/offsite-sync.ok
echo "Offsite-Kopie abgeschlossen: $(find "$OFFSITE_DIR" -maxdepth 1 -name 'rwsth-*.dump.gpg' | wc -l) Dateien"
EOF
chmod 0755 /usr/local/bin/wachwerk-offsite-sync
cat >/etc/systemd/system/wachwerk-offsite.service <<'EOF'
[Unit]
Description=Wachwerk: verschlüsselte Backups auf die Storage Box kopieren
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/wachwerk-offsite-sync
EOF
cat >/etc/systemd/system/wachwerk-offsite.timer <<'EOF'
[Unit]
Description=Wachwerk-Offsite stündlich

[Timer]
OnBootSec=10min
OnUnitActiveSec=1h
RandomizedDelaySec=5min

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now wachwerk-offsite.timer >/dev/null 2>&1

# --- 5. Erster Durchlauf -------------------------------------------------------------
say "Backup-Dienst neu starten und erstes verschlüsseltes Backup anlegen"
"$WACHWERK_DIR/wachbuch" start >/dev/null
"$WACHWERK_DIR/wachbuch" backup
ls "$OFFSITE"/rwsth-*.dump.gpg >/dev/null 2>&1 \
    || die "Keine verschlüsselte Datei in $OFFSITE (wachbuch logs backup)."
/usr/local/bin/wachwerk-offsite-sync

cat <<EOF

Fertig. Verschlüsselte Backups landen stündlich auf $BOX_USER@$BOX_HOST:$REMOTE_DIR/
  Status:        systemctl list-timers wachwerk-offsite.timer
  Protokoll:     journalctl -u wachwerk-offsite
  Wiederherstellen (docs/HETZNER.md, Abschnitt Backup-Probe):
    1. Datei holen:  sftp -P 23 $BOX_USER@$BOX_HOST
    2. Auf DEINEM Rechner entschlüsseln:  gpg --output rwsth.dump --decrypt rwsth-....dump.gpg
    3. Auf den Server kopieren und:  $WACHWERK_DIR/wachbuch restore rwsth.dump
EOF
