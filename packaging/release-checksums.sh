#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <artifact> [artifact...]" >&2
  exit 2
fi

shasum -a 256 "$@"
