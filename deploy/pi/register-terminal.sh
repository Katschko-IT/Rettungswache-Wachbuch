#!/usr/bin/env bash
# Registriert den Touch-Bildschirm dieses Pi als Wachenterminal. Der Kiosk-Browser
# öffnet den Start-Link beim nächsten Start einmal und löscht die Datei danach.
#
#   sudo deploy/pi/register-terminal.sh [Bezeichnung]
set -euo pipefail

LABEL="${1:-Wachenterminal}"
KIOSK_USER="${KIOSK_USER:-${SUDO_USER:-}}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE=(docker compose -f "$REPO_DIR/docker-compose.yml" -f "$REPO_DIR/deploy/pi/docker-compose.pi.yml")

[[ $EUID -eq 0 ]] || { echo "Bitte mit sudo ausführen." >&2; exit 1; }
[[ -n "$KIOSK_USER" ]] || { echo "KIOSK_USER fehlt." >&2; exit 1; }
KIOSK_HOME=$(getent passwd "$KIOSK_USER" | cut -d: -f6)

START_PATH=$("${COMPOSE[@]}" exec -T web python manage.py create_terminal --label "$LABEL" | tail -n 1)
[[ "$START_PATH" == /terminal/start/* ]] || { echo "Registrierung fehlgeschlagen: $START_PATH" >&2; exit 1; }

install -d -m 0700 -o "$KIOSK_USER" -g "$KIOSK_USER" "$KIOSK_HOME/.config/wachbuch"
umask 077
printf '%s' "$START_PATH" > "$KIOSK_HOME/.config/wachbuch/terminal-start"
chown "$KIOSK_USER:$KIOSK_USER" "$KIOSK_HOME/.config/wachbuch/terminal-start"
echo "Terminal „$LABEL“ registriert. Beim nächsten Start des Kiosk-Browsers wird es eingerichtet (sudo reboot)."
echo "Widerrufen: Team → Wachenterminals & PINs."
