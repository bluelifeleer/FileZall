#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

PYINSTALLER_BIN="${PYINSTALLER_BIN:-}"
if [[ -z "$PYINSTALLER_BIN" ]]; then
  if [[ -x "$REPO_ROOT/.venv/bin/pyinstaller" ]]; then
    PYINSTALLER_BIN="$REPO_ROOT/.venv/bin/pyinstaller"
  else
    PYINSTALLER_BIN="pyinstaller"
  fi
fi

if ! command -v "$PYINSTALLER_BIN" >/dev/null 2>&1; then
  echo "pyinstaller is required. Install it in the build environment before running this script." >&2
  exit 1
fi

export PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR:-$REPO_ROOT/.pyinstaller-cache}"

"$PYINSTALLER_BIN" --clean --noconfirm packaging/filezall.spec

if command -v create-dmg >/dev/null 2>&1; then
  mkdir -p dist/dmg
  create-dmg \
    --volname "FileZall" \
    --window-pos 200 120 \
    --window-size 640 400 \
    --app-drop-link 480 200 \
    "dist/dmg/FileZall.dmg" \
    "dist/FileZall.app"
else
  echo "create-dmg was not found. The .app bundle is available under dist/FileZall.app." >&2
fi
