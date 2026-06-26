#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

VERSION="${FILEZALL_VERSION:-$(python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')}"
APP_NAME="FileZall"
APP_PATH="dist/${APP_NAME}.app"
ZIP_PATH="dist/${APP_NAME}-${VERSION}-macos-arm64.zip"
DMG_PATH="dist/${APP_NAME}-${VERSION}-macos-arm64.dmg"
LATEST_ZIP_PATH="dist/${APP_NAME}-macos-arm64.zip"
LATEST_DMG_PATH="dist/${APP_NAME}-macos-arm64.dmg"

export FILEZALL_VERSION="$VERSION"
export FILEZALL_MACOS_ENTITLEMENTS="${FILEZALL_MACOS_ENTITLEMENTS:-$REPO_ROOT/packaging/macos/entitlements.plist}"

bash packaging/macos/build.sh

if [[ -n "${FILEZALL_MACOS_CODESIGN_IDENTITY:-}" ]]; then
  codesign --force --deep --options runtime \
    --entitlements "$FILEZALL_MACOS_ENTITLEMENTS" \
    --sign "$FILEZALL_MACOS_CODESIGN_IDENTITY" \
    "$APP_PATH"
elif [[ "${FILEZALL_MACOS_NOTARIZE:-0}" == "1" ]]; then
  echo "FILEZALL_MACOS_CODESIGN_IDENTITY is required when FILEZALL_MACOS_NOTARIZE=1" >&2
  exit 2
fi

codesign --verify --deep --strict --verbose=2 "$APP_PATH"

ditto -c -k --sequesterRsrc --keepParent "$APP_PATH" "$ZIP_PATH"
cp "$ZIP_PATH" "$LATEST_ZIP_PATH"

if [[ "${FILEZALL_MACOS_NOTARIZE:-0}" == "1" ]]; then
  : "${APP_STORE_CONNECT_KEY:?Set APP_STORE_CONNECT_KEY to the .p8 key path}"
  : "${APP_STORE_CONNECT_KEY_ID:?Set APP_STORE_CONNECT_KEY_ID}"
  : "${APP_STORE_CONNECT_ISSUER_ID:?Set APP_STORE_CONNECT_ISSUER_ID}"
  xcrun notarytool submit "$ZIP_PATH" \
    --key "$APP_STORE_CONNECT_KEY" \
    --key-id "$APP_STORE_CONNECT_KEY_ID" \
    --issuer "$APP_STORE_CONNECT_ISSUER_ID" \
    --wait
  xcrun stapler staple "$APP_PATH"
fi

hdiutil create -volname "$APP_NAME" -srcfolder "$APP_PATH" -ov -format UDZO "$DMG_PATH"
cp "$DMG_PATH" "$LATEST_DMG_PATH"

if [[ "${FILEZALL_MACOS_NOTARIZE:-0}" == "1" ]]; then
  xcrun notarytool submit "$DMG_PATH" \
    --key "$APP_STORE_CONNECT_KEY" \
    --key-id "$APP_STORE_CONNECT_KEY_ID" \
    --issuer "$APP_STORE_CONNECT_ISSUER_ID" \
    --wait
  xcrun stapler staple "$DMG_PATH"
  spctl --assess --type execute --verbose "$APP_PATH"
fi

hdiutil verify "$DMG_PATH"

shasum -a 256 "$ZIP_PATH" "$DMG_PATH" > "dist/${APP_NAME}-${VERSION}-macos-SHA256SUMS.txt"
cp "dist/${APP_NAME}-${VERSION}-macos-SHA256SUMS.txt" "dist/${APP_NAME}-macos-SHA256SUMS.txt"

echo "Release artifacts:"
echo "  $ZIP_PATH"
echo "  $DMG_PATH"
echo "  dist/${APP_NAME}-${VERSION}-macos-SHA256SUMS.txt"
