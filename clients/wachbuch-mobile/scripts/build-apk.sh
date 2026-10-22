#!/usr/bin/env bash
# Build installable internal APKs with a separate package ID and debug key.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export ANDROID_HOME="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/Android/Sdk}}"
export ANDROID_SDK_ROOT="$ANDROID_HOME"

flutter pub get
flutter test
flutter build apk \
  --release \
  --flavor internal \
  --split-per-abi \
  --obfuscate \
  --split-debug-info=build/symbols/internal

rm -rf dist/internal-apk
mkdir -p dist/internal-apk
find build/app/outputs/flutter-apk \
  -type f \
  -name '*internal*release.apk' \
  -exec cp -f {} dist/internal-apk/ \;

count=$(find dist/internal-apk -type f -name '*.apk' | wc -l | tr -d ' ')
if [ "$count" -lt 3 ]; then
  echo "Expected split APKs for all supported ABIs, found $count" >&2
  exit 1
fi

(
  cd dist/internal-apk
  sha256sum *.apk > SHA256SUMS
  ls -lh *.apk SHA256SUMS
)

echo "Internal APKs ready: $ROOT/dist/internal-apk"
