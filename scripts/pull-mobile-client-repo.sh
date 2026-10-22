#!/usr/bin/env bash
# Spiegelt https://github.com/Katschko-IT/Wachbuch-Client nach clients/wachbuch-mobile/
# (Gegenstück zu publish-mobile-client-repo.sh).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DST="$ROOT/clients/wachbuch-mobile"
REMOTE_URL="${MOBILE_REPO_URL:-https://github.com/Katschko-IT/Wachbuch-Client.git}"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/wachbuch-client-pull.XXXXXX")"

cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

echo "Clone $REMOTE_URL …"
git clone --depth 1 "$REMOTE_URL" "$WORK"

rm -rf "$WORK/.git"
mkdir -p "$DST"
# Replace mirror contents (keep destination directory)
find "$DST" -mindepth 1 -maxdepth 1 ! -name '.dart_tool' ! -name 'build' ! -name 'dist' -exec rm -rf {} +
cp -a "$WORK"/. "$DST"/
rm -rf "$DST/.dart_tool" "$DST/build" "$DST/dist"

echo "Aktualisiert: $DST"
echo "Bitte prüfen und committen."
