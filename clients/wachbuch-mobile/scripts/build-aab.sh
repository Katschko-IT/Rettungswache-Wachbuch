#!/usr/bin/env bash
# Build a signed production AAB. Never falls back to the Android debug key.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export ANDROID_HOME="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/Android/Sdk}}"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export REQUIRE_RELEASE_SIGNING=true

if [ ! -f android/key.properties ]; then
  required=(
    ANDROID_KEYSTORE_PATH
    ANDROID_KEYSTORE_PASSWORD
    ANDROID_KEY_ALIAS
    ANDROID_KEY_PASSWORD
  )
  for name in "${required[@]}"; do
    if [ -z "${!name:-}" ]; then
      echo "Missing $name and android/key.properties is not present" >&2
      exit 1
    fi
  done
fi

SOURCE_VERSION=$(awk '/^version:/{print $2; exit}' pubspec.yaml)
DEFAULT_BUILD_NAME=${SOURCE_VERSION%%+*}
DEFAULT_BUILD_NUMBER=${SOURCE_VERSION##*+}
BUILD_NAME="${BUILD_NAME:-$DEFAULT_BUILD_NAME}"
BUILD_NUMBER="${BUILD_NUMBER:-$DEFAULT_BUILD_NUMBER}"

if [ "$SOURCE_VERSION" != "$BUILD_NAME+$BUILD_NUMBER" ]; then
  echo "Requested build $BUILD_NAME+$BUILD_NUMBER does not match pubspec version $SOURCE_VERSION" >&2
  exit 1
fi

flutter pub get
flutter gen-l10n
flutter analyze
flutter test
flutter build appbundle \
  --release \
  --flavor production \
  --build-name "$BUILD_NAME" \
  --build-number "$BUILD_NUMBER" \
  --obfuscate \
  --split-debug-info=build/symbols/production

AAB=$(find build/app/outputs/bundle -type f -name '*production*release*.aab' -print -quit)
if [ -z "$AAB" ]; then
  echo "Production AAB was not created" >&2
  exit 1
fi

jarsigner -verify -strict "$AAB" >/dev/null
rm -rf dist/production-aab
mkdir -p dist/production-aab dist/production-symbols
cp "$AAB" "dist/production-aab/wachbuch-$BUILD_NAME-$BUILD_NUMBER.aab"
cp -R build/symbols/production/. dist/production-symbols/
(
  cd dist/production-aab
  sha256sum *.aab > SHA256SUMS
  ls -lh *.aab SHA256SUMS
)

echo "Signed production AAB ready: $ROOT/dist/production-aab"
