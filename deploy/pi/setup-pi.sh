#!/usr/bin/env bash
# Richtet einen Raspberry Pi 4 (4 GB, Raspberry Pi OS 64-bit „Bookworm“ mit
# Desktop) als Wachen-Server ein: eigenes WLAN, lokales Zertifikat, Wachbuch in
# Docker und Kiosk-Browser für den Touch-Bildschirm.
#
#   sudo WLAN_SSID="Wachbuch RW1" deploy/pi/setup-pi.sh
#
# Einstellbar über Umgebungsvariablen (Standard in Klammern):
#   WLAN_SSID (Wachbuch)        Name des WLANs der Wache
#   WLAN_PSK  (zufällig)        WLAN-Passwort, mind. 12 Zeichen
#   WLAN_COUNTRY (DE)           Ländercode für Funkregeln
#   WLAN_IFACE (wlan0)          WLAN-Schnittstelle des Pi
#   AP_ADDRESS (10.42.0.1)      Adresse des Pi im WLAN
#   LAN_NAME (wachbuch.lan)     Name im WLAN
#   KIOSK_USER (Aufrufer)       Desktop-Benutzer, der den Kiosk-Browser startet
#
# Das Skript ist wiederholbar. Bestehende Schlüssel, Zertifikate und .env-Werte
# bleiben erhalten. Für die Einrichtung braucht der Pi einmal Internet (LAN-Kabel).
set -euo pipefail

WLAN_SSID="${WLAN_SSID:-Wachbuch}"
WLAN_PSK="${WLAN_PSK:-}"
WLAN_COUNTRY="${WLAN_COUNTRY:-DE}"
WLAN_IFACE="${WLAN_IFACE:-wlan0}"
AP_ADDRESS="${AP_ADDRESS:-10.42.0.1}"
LAN_NAME="${LAN_NAME:-wachbuch.lan}"
KIOSK_USER="${KIOSK_USER:-${SUDO_USER:-}}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TLS_DIR=/etc/wachbuch/tls
STATE_DIR=/etc/wachbuch
COMPOSE=(docker compose -f "$REPO_DIR/docker-compose.yml" -f "$REPO_DIR/deploy/pi/docker-compose.pi.yml")

say() { printf '\n==> %s\n' "$*"; }
die() { printf 'Fehler: %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Bitte mit sudo ausführen."
[[ "$(uname -m)" == "aarch64" ]] || die "64-Bit-System (aarch64) erforderlich."
[[ -n "$KIOSK_USER" ]] && id "$KIOSK_USER" >/dev/null 2>&1 || die "KIOSK_USER fehlt oder existiert nicht."
mem_kb=$(awk '/MemTotal/ {print $2}' /proc/meminfo)
(( mem_kb > 3500000 )) || echo "Warnung: weniger als 4 GB RAM – der Betrieb kann knapp werden."
if findmnt -no SOURCE / | grep -q mmcblk; then
  echo "Hinweis: System läuft von der SD-Karte. Für Dauerbetrieb mit Datenbank eine SSD (USB 3) verwenden."
fi

say "Pakete installieren (Docker aus dem offiziellen Docker-Repository)"
apt-get update -q
apt-get install -y -q ca-certificates curl gnupg openssl network-manager
if ! command -v docker >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/debian/gpg -o /tmp/docker.gpg
  # Fingerabdruck des Docker-Release-Schlüssels prüfen, bevor er vertraut wird.
  gpg --show-keys --with-colons /tmp/docker.gpg | grep -q '^fpr:::::::::9DC858229FC7DD38854AE2D88D81803C0EBFCD88:' \
    || die "Docker-Schlüssel hat einen unerwarteten Fingerabdruck."
  gpg --dearmor -o /etc/apt/keyrings/docker.gpg < /tmp/docker.gpg
  . /etc/os-release
  echo "deb [arch=arm64 signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi
systemctl enable --now docker
if apt-cache show chromium >/dev/null 2>&1; then
  apt-get install -y -q chromium
else
  apt-get install -y -q chromium-browser
fi
CHROMIUM=$(command -v chromium || command -v chromium-browser)

say "WLAN der Wache einrichten ($WLAN_SSID auf $WLAN_IFACE)"
if command -v raspi-config >/dev/null 2>&1; then
  raspi-config nonint do_wifi_country "$WLAN_COUNTRY" || true
  raspi-config nonint do_blanking 1 || true
fi
install -d -m 0750 "$STATE_DIR"
if [[ -z "$WLAN_PSK" ]]; then
  if [[ -f "$STATE_DIR/wlan-psk" ]]; then
    WLAN_PSK=$(cat "$STATE_DIR/wlan-psk")
  else
    WLAN_PSK=$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-16)
  fi
fi
(( ${#WLAN_PSK} >= 12 )) || die "WLAN_PSK muss mindestens 12 Zeichen haben."
umask 077; printf '%s' "$WLAN_PSK" > "$STATE_DIR/wlan-psk"; umask 022
nmcli connection delete wachbuch-ap >/dev/null 2>&1 || true
nmcli connection add type wifi ifname "$WLAN_IFACE" con-name wachbuch-ap autoconnect yes ssid "$WLAN_SSID" \
  802-11-wireless.mode ap 802-11-wireless.band bg 802-11-wireless.channel 6 \
  802-11-wireless.ap-isolation 1 \
  ipv4.method shared ipv4.addresses "$AP_ADDRESS/24" ipv6.method disabled \
  wifi-sec.key-mgmt wpa-psk wifi-sec.proto rsn wifi-sec.pairwise ccmp wifi-sec.group ccmp \
  wifi-sec.psk "$WLAN_PSK" >/dev/null
# Name im WLAN: wachbuch.lan zeigt auf den Pi (dnsmasq von NetworkManager).
install -d /etc/NetworkManager/dnsmasq-shared.d
printf 'address=/%s/%s\n' "$LAN_NAME" "$AP_ADDRESS" > /etc/NetworkManager/dnsmasq-shared.d/wachbuch.conf
nmcli connection up wachbuch-ap >/dev/null

say "Lokales TLS-Zertifikat"
install -d -m 0755 "$TLS_DIR"
if [[ ! -s "$TLS_DIR/wachbuch.crt" ]]; then
  openssl req -x509 -nodes -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -days 3650 \
    -keyout "$TLS_DIR/wachbuch.key" -out "$TLS_DIR/wachbuch.crt" \
    -subj "/CN=$LAN_NAME/O=Wachbuch" \
    -addext "subjectAltName=DNS:$LAN_NAME,DNS:localhost,IP:$AP_ADDRESS,IP:127.0.0.1" \
    -addext "basicConstraints=critical,CA:FALSE" \
    -addext "keyUsage=critical,digitalSignature" \
    -addext "extendedKeyUsage=serverAuth"
  chmod 600 "$TLS_DIR/wachbuch.key"
fi
CERT_SHA256=$(openssl x509 -in "$TLS_DIR/wachbuch.crt" -outform DER | sha256sum | cut -d' ' -f1)
SPKI_SHA256=$(openssl x509 -in "$TLS_DIR/wachbuch.crt" -pubkey -noout | openssl pkey -pubin -outform DER \
  | openssl dgst -sha256 -binary | base64)

say "Konfiguration (.env)"
ENV_FILE="$REPO_DIR/.env"
[[ -f "$ENV_FILE" ]] || { cp "$REPO_DIR/.env.example" "$ENV_FILE"; chmod 600 "$ENV_FILE"; }
set_env() {  # set_env KEY VALUE [nur-wenn-Platzhalter]
  local key=$1 value=$2 only_placeholder=${3:-}
  if grep -q "^${key}=" "$ENV_FILE"; then
    if [[ -n "$only_placeholder" ]] && ! grep -Eq "^${key}=(replace-|$)" "$ENV_FILE"; then
      return
    fi
    sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}
for key in DJANGO_SECRET_KEY POSTGRES_PASSWORD APP_DB_PASSWORD FEED_DB_PASSWORD BACKUP_DB_PASSWORD \
           PUSH_DB_PASSWORD FEED_WORKER_SECRET_KEY PUSH_WORKER_SECRET_KEY; do
  set_env "$key" "$(openssl rand -hex 32)" placeholder
done
set_env CRYPTO_MASTER_KEY "$(openssl rand -hex 32)" placeholder
set_env ALLOWED_HOSTS "$AP_ADDRESS,$LAN_NAME,localhost,127.0.0.1"
set_env CSRF_TRUSTED_ORIGINS "https://$AP_ADDRESS,https://$LAN_NAME,https://localhost"
# Apps verbinden sich über die Adresse: Android löst ohne Internet keine Namen auf.
set_env SITE_URL "https://$AP_ADDRESS"
set_env SECURE_COOKIES true
set_env TRUSTED_PROXY true
set_env TERMINAL_ENABLED true
set_env LOCAL_TLS_CERT_SHA256 "$CERT_SHA256"
# Passkeys brauchen ein öffentlich vertrauenswürdiges Zertifikat.
set_env WEBAUTHN_ENABLED false
set_env PI_SERVER_NAMES "\"$LAN_NAME localhost $AP_ADDRESS\""
set_env PI_TLS_DIR "$TLS_DIR"
if grep -Eq '^SETUP_BOOTSTRAP_TOKEN=$' "$ENV_FILE" && [[ ! -f "$STATE_DIR/setup-done" ]]; then
  set_env SETUP_BOOTSTRAP_TOKEN "$(openssl rand -hex 24)"
fi

say "Wachbuch bauen und starten (beim ersten Mal 10–20 Minuten)"
"${COMPOSE[@]}" up -d --build

say "Kiosk-Browser für den Touch-Bildschirm"
KIOSK_HOME=$(getent passwd "$KIOSK_USER" | cut -d: -f6)
cat > /usr/local/bin/wachbuch-kiosk <<KIOSK
#!/usr/bin/env bash
# Startet das Wachenterminal im Vollbild. Vertraut nur dem Zertifikat dieses Pi.
until curl -fsk --max-time 3 https://localhost/healthz/ >/dev/null; do sleep 3; done
URL=https://localhost/terminal/
if [[ -s "$KIOSK_HOME/.config/wachbuch/terminal-start" ]]; then
  URL="https://localhost\$(cat "$KIOSK_HOME/.config/wachbuch/terminal-start")"
  rm -f "$KIOSK_HOME/.config/wachbuch/terminal-start"
fi
exec "$CHROMIUM" --kiosk --lang=de --noerrdialogs --disable-infobars --no-first-run \\
  --disable-session-crashed-bubble --disable-features=Translate \\
  --check-for-update-interval=31536000 --password-store=basic \\
  --user-data-dir="$KIOSK_HOME/.local/share/wachbuch-kiosk" \\
  --ignore-certificate-errors-spki-list="$SPKI_SHA256" \\
  "\$URL"
KIOSK
chmod 755 /usr/local/bin/wachbuch-kiosk
for dir in "$KIOSK_HOME/.config/labwc" "$KIOSK_HOME/.config/wachbuch"; do
  install -d -o "$KIOSK_USER" -g "$KIOSK_USER" "$dir"
done
AUTOSTART="$KIOSK_HOME/.config/labwc/autostart"
touch "$AUTOSTART"; chown "$KIOSK_USER:$KIOSK_USER" "$AUTOSTART"
grep -q wachbuch-kiosk "$AUTOSTART" || echo "/usr/local/bin/wachbuch-kiosk &" >> "$AUTOSTART"
WAYFIRE="$KIOSK_HOME/.config/wayfire.ini"
if [[ -f "$WAYFIRE" ]] && ! grep -q wachbuch-kiosk "$WAYFIRE"; then
  printf '\n[autostart]\nwachbuch = /usr/local/bin/wachbuch-kiosk\n' >> "$WAYFIRE"
fi

cat <<DONE

Fertig.
  WLAN:          $WLAN_SSID
  WLAN-Passwort: $WLAN_PSK   (gespeichert in $STATE_DIR/wlan-psk)
  Adresse:       https://$AP_ADDRESS   bzw. https://$LAN_NAME
  Zertifikat:    SHA-256 $CERT_SHA256

Nächste Schritte:
  1. Ersteinrichtung im Browser: https://localhost/setup/ (Token: SETUP_BOOTSTRAP_TOKEN in $ENV_FILE)
     Danach SETUP_BOOTSTRAP_TOKEN in .env leeren und: sudo touch $STATE_DIR/setup-done
  2. Terminal registrieren: sudo deploy/pi/register-terminal.sh
  3. Neu starten: sudo reboot  (der Touch-Bildschirm startet dann das Wachenterminal)
DONE
