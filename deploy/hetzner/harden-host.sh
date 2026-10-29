#!/bin/sh
# Härtet einen frischen Cloud-Server (Hetzner Cloud o. ä.) für Wachwerk im
# Internet. Läuft auf Debian 12/13 und Ubuntu 22.04/24.04, als root,
# wiederholbar. Anleitung: docs/HETZNER.md
#
#   sh harden-host.sh --user michael [--ping-url https://hc-ping.com/<uuid>]
#
# Was das Skript tut:
#   - Docker Engine + Compose v2 aus dem offiziellen Docker-Repository
#   - Admin-Benutzer mit sudo und SSH-Schlüssel (von root übernommen)
#   - SSH: nur Schlüssel, kein root-Login, nur dieser Benutzer
#   - Firewall (ufw): nur SSH (gedrosselt), HTTP und HTTPS
#   - fail2ban für SSH
#   - automatische Sicherheitsupdates mit Neustart um 04:30
#   - Docker: live-restore, Log-Rotation, no-new-privileges
#   - Swap auf kleinen Servern, Zeitzone Europe/Berlin, Journal-Grenze
#   - Überwachung alle 5 Minuten (wachwerk-health), optional mit
#     Ping an healthchecks.io o. ä., das bei Ausfall eine E-Mail schickt
set -eu

say() { printf '\n==> %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf 'Warnung: %s\n' "$*" >&2; }
die() { printf 'Fehler: %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'EOF'
Aufruf: sh harden-host.sh --user NAME [Optionen]

  --user NAME       Admin-Benutzer für SSH (wird angelegt, falls nötig)
  --ping-url URL    Überwachungs-Ping (z. B. https://hc-ping.com/<uuid>);
                    bei Fehlern wird URL/fail aufgerufen
  --dir PFAD        Wachwerk-Ordner (Standard /opt/wachbuch)
  --no-docker       Docker nicht installieren
  --no-reboot       automatische Updates ohne nächtlichen Neustart
  -y, --yes         keine Rückfragen
  -h, --help        diese Hilfe
EOF
}

ADMIN_USER=""
PING_URL=""
WACHWERK_DIR="/opt/wachbuch"
INSTALL_DOCKER=1
AUTO_REBOOT=true
ASSUME_YES=0

while [ $# -gt 0 ]; do
    case "$1" in
        --user) [ $# -ge 2 ] || die "--user braucht einen Wert."; ADMIN_USER="$2"; shift ;;
        --ping-url) [ $# -ge 2 ] || die "--ping-url braucht einen Wert."; PING_URL="$2"; shift ;;
        --dir) [ $# -ge 2 ] || die "--dir braucht einen Wert."; WACHWERK_DIR="$2"; shift ;;
        --no-docker) INSTALL_DOCKER=0 ;;
        --no-reboot) AUTO_REBOOT=false ;;
        -y|--yes) ASSUME_YES=1 ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; die "Unbekannte Option: $1" ;;
    esac
    shift
done

[ "$(id -u)" -eq 0 ] || die "Bitte als root ausführen (sudo sh harden-host.sh ...)."
[ -n "$ADMIN_USER" ] || { usage >&2; die "--user fehlt."; }
case "$ADMIN_USER" in
    root) die "--user darf nicht root sein." ;;
    ''|*[!a-z0-9_-]*|-*) die "Ungültiger Benutzername: $ADMIN_USER (Kleinbuchstaben, Ziffern, _ und -)." ;;
esac
case "$PING_URL" in
    ''|https://*) ;;
    *) die "--ping-url muss mit https:// beginnen." ;;
esac

[ -r /etc/os-release ] || die "/etc/os-release fehlt; nur Debian und Ubuntu werden unterstützt."
# shellcheck disable=SC1091
. /etc/os-release
case "${ID:-}" in
    debian|ubuntu) ;;
    *) die "Nur Debian und Ubuntu werden unterstützt (gefunden: ${ID:-unbekannt})." ;;
esac
CODENAME="${VERSION_CODENAME:-}"
[ -n "$CODENAME" ] || die "VERSION_CODENAME fehlt in /etc/os-release."

export DEBIAN_FRONTEND=noninteractive
apt_install() { apt-get install -y -q --no-install-recommends "$@" >/dev/null; }

# --- 1. Pakete ---------------------------------------------------------------
say "Systempakete aktualisieren"
apt-get update -q >/dev/null
apt-get upgrade -y -q >/dev/null
apt_install ca-certificates curl gnupg ufw fail2ban python3-systemd \
    unattended-upgrades apt-listchanges rsync openssh-client openssl
info "ufw, fail2ban, unattended-upgrades, rsync installiert"

if [ "$INSTALL_DOCKER" -eq 1 ]; then
    if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
        info "Docker ist schon installiert: $(docker --version)"
    else
        say "Docker aus dem offiziellen Repository installieren"
        install -m 0755 -d /etc/apt/keyrings
        curl -fsSL "https://download.docker.com/linux/$ID/gpg" -o /etc/apt/keyrings/docker.asc
        chmod a+r /etc/apt/keyrings/docker.asc
        printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/%s %s stable\n' \
            "$(dpkg --print-architecture)" "$ID" "$CODENAME" >/etc/apt/sources.list.d/docker.list
        apt-get update -q >/dev/null
        apt_install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
        info "$(docker --version)"
    fi
fi

# --- 2. Docker-Daemon ----------------------------------------------------------
say "Docker-Daemon"
if [ -f /etc/docker/daemon.json ]; then
    info "/etc/docker/daemon.json existiert – bleibt unverändert. Empfohlen:"
    info '{"live-restore": true, "no-new-privileges": true, "log-driver": "json-file", "log-opts": {"max-size": "10m", "max-file": "3"}}'
else
    install -m 0755 -d /etc/docker
    cat >/etc/docker/daemon.json <<'EOF'
{
  "live-restore": true,
  "no-new-privileges": true,
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
EOF
    if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet docker; then
        systemctl restart docker
    fi
    info "live-restore, no-new-privileges und Log-Rotation gesetzt"
fi

# --- 3. Admin-Benutzer ---------------------------------------------------------
say "Admin-Benutzer $ADMIN_USER"
if id "$ADMIN_USER" >/dev/null 2>&1; then
    info "existiert"
else
    adduser --disabled-password --gecos "" "$ADMIN_USER" >/dev/null
    info "angelegt"
fi
usermod -aG sudo "$ADMIN_USER"
if getent group docker >/dev/null 2>&1; then
    usermod -aG docker "$ADMIN_USER"
fi
USER_HOME=$(getent passwd "$ADMIN_USER" | cut -d: -f6)
install -d -m 0700 -o "$ADMIN_USER" -g "$ADMIN_USER" "$USER_HOME/.ssh"
KEYS="$USER_HOME/.ssh/authorized_keys"
if [ ! -s "$KEYS" ] && [ -s /root/.ssh/authorized_keys ]; then
    install -m 0600 -o "$ADMIN_USER" -g "$ADMIN_USER" /root/.ssh/authorized_keys "$KEYS"
    info "SSH-Schlüssel von root übernommen"
fi
[ -s "$KEYS" ] || die "$KEYS ist leer. Ohne SSH-Schlüssel würde die SSH-Härtung dich aussperren. Schlüssel eintragen und erneut starten."
chown "$ADMIN_USER:$ADMIN_USER" "$KEYS"
chmod 0600 "$KEYS"

# sudo braucht ein Passwort; ohne Passwort (Cloud-Standard) hilft NOPASSWD,
# solange SSH nur mit Schlüssel geht.
if passwd -S "$ADMIN_USER" 2>/dev/null | awk '{ exit ($2 == "P") ? 0 : 1 }'; then
    info "Passwort für sudo ist gesetzt"
elif [ "$ASSUME_YES" -eq 0 ] && [ -r /dev/tty ]; then
    info "Passwort für sudo festlegen:"
    passwd "$ADMIN_USER" </dev/tty || warn "Passwort nicht gesetzt; später: passwd $ADMIN_USER"
else
    printf '%s ALL=(ALL) NOPASSWD:ALL\n' "$ADMIN_USER" >"/etc/sudoers.d/90-wachwerk-$ADMIN_USER"
    chmod 0440 "/etc/sudoers.d/90-wachwerk-$ADMIN_USER"
    visudo -cq || { rm -f "/etc/sudoers.d/90-wachwerk-$ADMIN_USER"; die "sudoers-Datei ungültig."; }
    warn "sudo ohne Passwort für $ADMIN_USER (kein Passwort gesetzt). Später: passwd $ADMIN_USER und /etc/sudoers.d/90-wachwerk-$ADMIN_USER löschen."
fi

# --- 4. SSH ----------------------------------------------------------------------
say "SSH: nur Schlüssel, kein root"
install -d -m 0755 /etc/ssh/sshd_config.d
grep -Eq '^[[:space:]]*Include[[:space:]]+/etc/ssh/sshd_config.d/' /etc/ssh/sshd_config \
    || die "/etc/ssh/sshd_config bindet sshd_config.d nicht ein; bitte von Hand härten."
cat >/etc/ssh/sshd_config.d/10-wachwerk.conf <<EOF
# Wachwerk (deploy/hetzner/harden-host.sh)
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
AuthenticationMethods publickey
MaxAuthTries 3
LoginGraceTime 30
X11Forwarding no
AllowAgentForwarding no
AllowUsers $ADMIN_USER
EOF
if ! sshd -t; then
    rm -f /etc/ssh/sshd_config.d/10-wachwerk.conf
    die "sshd-Konfiguration ungültig; Änderung zurückgenommen."
fi
# Ubuntu 24.04 startet sshd per Socket; neue Verbindungen lesen die Datei dann ohnehin neu.
systemctl try-reload-or-restart ssh.service 2>/dev/null \
    || systemctl try-reload-or-restart sshd.service 2>/dev/null || true
info "Anmeldung ab jetzt nur noch: ssh $ADMIN_USER@<server>"

# --- 5. Firewall -----------------------------------------------------------------
say "Firewall (ufw)"
ufw --force default deny incoming >/dev/null
ufw --force default allow outgoing >/dev/null
ufw limit 22/tcp comment 'SSH (gedrosselt)' >/dev/null
ufw allow 80/tcp comment 'HTTP -> HTTPS, Lets Encrypt' >/dev/null
ufw allow 443/tcp comment 'HTTPS Wachwerk' >/dev/null
ufw --force enable >/dev/null
info "offen: 22 (gedrosselt), 80, 443"
info "Docker umgeht ufw für veröffentlichte Ports. Wachwerk veröffentlicht nur"
info "Caddy (80/443); web lauscht auf 127.0.0.1. Zusätzlich die Hetzner-Firewall nutzen."

# --- 6. fail2ban -----------------------------------------------------------------
say "fail2ban für SSH"
cat >/etc/fail2ban/jail.d/wachwerk.local <<'EOF'
[DEFAULT]
bantime = 1h
findtime = 10m
maxretry = 5
banaction = ufw

[sshd]
enabled = true
backend = systemd
EOF
systemctl enable --now fail2ban >/dev/null 2>&1
systemctl restart fail2ban
info "5 Fehlversuche in 10 Minuten -> 1 Stunde gesperrt"

# --- 7. Automatische Updates -----------------------------------------------------
say "Automatische Sicherheitsupdates"
cat >/etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
cat >/etc/apt/apt.conf.d/52wachwerk-unattended <<EOF
// Wachwerk (deploy/hetzner/harden-host.sh)
Unattended-Upgrade::Origins-Pattern {
        "origin=Docker,codename=$CODENAME";
};
Unattended-Upgrade::Remove-Unused-Dependencies "true";
Unattended-Upgrade::Automatic-Reboot "$AUTO_REBOOT";
Unattended-Upgrade::Automatic-Reboot-Time "04:30";
EOF
systemctl enable --now unattended-upgrades >/dev/null 2>&1 || true
if [ "$AUTO_REBOOT" = true ]; then
    info "täglich, bei Bedarf Neustart um 04:30 (Docker startet Wachwerk selbst wieder)"
else
    info "täglich, ohne automatischen Neustart"
fi

# --- 8. System -------------------------------------------------------------------
say "System"
timedatectl set-timezone Europe/Berlin 2>/dev/null || true
timedatectl set-ntp true 2>/dev/null || true
install -d -m 0755 /etc/systemd/journald.conf.d
printf '[Journal]\nSystemMaxUse=500M\n' >/etc/systemd/journald.conf.d/wachwerk.conf
systemctl restart systemd-journald
cat >/etc/sysctl.d/90-wachwerk.conf <<'EOF'
# Wachwerk (deploy/hetzner/harden-host.sh); ip_forward bleibt für Docker an.
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv6.conf.default.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.tcp_syncookies = 1
kernel.kptr_restrict = 2
kernel.dmesg_restrict = 1
fs.protected_hardlinks = 1
fs.protected_symlinks = 1
vm.swappiness = 10
EOF
sysctl --system >/dev/null
info "Zeitzone Europe/Berlin, NTP, Journal max. 500 MB, Netz-Härtung"

mem_kb=$(awk '/^MemTotal:/ { print $2 }' /proc/meminfo)
if [ "$(swapon --show --noheadings | wc -l)" -eq 0 ] && [ "$mem_kb" -lt 4194304 ]; then
    fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null
    swapon /swapfile
    grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >>/etc/fstab
    info "2 GB Swap angelegt (weniger als 4 GB RAM)"
fi

# --- 9. Überwachung ---------------------------------------------------------------
say "Überwachung (wachwerk-health, alle 5 Minuten)"
install -d -m 0700 /etc/wachwerk
script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
if [ -f "$script_dir/wachwerk-health.sh" ]; then
    install -m 0755 "$script_dir/wachwerk-health.sh" /usr/local/bin/wachwerk-health
else
    # Einzeln heruntergeladen: Prüfskript aus demselben Stand holen.
    curl -fsSL "${WACHWERK_BASE_URL:-https://raw.githubusercontent.com/Katschko-IT/Rettungswache-Wachbuch/main}/deploy/hetzner/wachwerk-health.sh" \
        -o /usr/local/bin/wachwerk-health || die "wachwerk-health.sh konnte nicht geladen werden."
    chmod 0755 /usr/local/bin/wachwerk-health
fi
if [ ! -f /etc/wachwerk/health.env ] || [ -n "$PING_URL" ]; then
    umask 077
    {
        echo "# Wachwerk-Überwachung (wachwerk-health)"
        echo "WACHWERK_DIR=$WACHWERK_DIR"
        echo "PING_URL=$PING_URL"
        echo "# Optional: andere Adresse prüfen, Grenzen anpassen"
        echo "#HEALTH_URL=https://demo.example.org/healthz/"
        echo "#CERT_MIN_DAYS=14"
        echo "#DISK_MAX_PERCENT=85"
        echo "#BACKUP_MAX_AGE_HOURS=30"
    } >/etc/wachwerk/health.env
fi
cat >/etc/systemd/system/wachwerk-health.service <<'EOF'
[Unit]
Description=Wachwerk: Erreichbarkeit, Zertifikat, Container, Backup und Platz prüfen
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=oneshot
EnvironmentFile=-/etc/wachwerk/health.env
ExecStart=/usr/local/bin/wachwerk-health
EOF
cat >/etc/systemd/system/wachwerk-health.timer <<'EOF'
[Unit]
Description=Wachwerk-Überwachung alle 5 Minuten

[Timer]
OnBootSec=3min
OnUnitActiveSec=5min
RandomizedDelaySec=30

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now wachwerk-health.timer >/dev/null 2>&1
if [ -n "$PING_URL" ]; then
    info "Ping an $PING_URL (bei Fehlern $PING_URL/fail)"
else
    info "ohne Ping: Ergebnisse nur im Journal (journalctl -u wachwerk-health)"
fi

cat <<EOF

Fertig. Nächste Schritte (docs/HETZNER.md):
  1. In einem ZWEITEN Terminal prüfen:  ssh $ADMIN_USER@<server>
     Erst wenn das klappt, diese Sitzung schließen.
  2. Wachwerk installieren (Schritt 4 der Anleitung).
  3. Status:  sudo wachwerk-health --verbose
EOF
