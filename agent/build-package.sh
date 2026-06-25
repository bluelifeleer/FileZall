#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$REPO_ROOT/dist"
STAGE_DIR="$DIST_DIR/filezall-agent"

rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR"
cp -R "$REPO_ROOT/agent/filezall_agent" "$STAGE_DIR/"
cp -R "$REPO_ROOT/agent/systemd" "$STAGE_DIR/"
cp -R "$REPO_ROOT/agent/env" "$STAGE_DIR/"

(
  cd "$DIST_DIR"
  tar -czf filezall-agent.tar.gz filezall-agent
)

echo "Created $DIST_DIR/filezall-agent.tar.gz"
