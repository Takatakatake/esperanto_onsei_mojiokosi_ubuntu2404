#!/usr/bin/env bash
# Convenience launcher so the venv bootstrapper can be executed
# directly from the repository root.
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TARGET="${SCRIPT_DIR}/scripts/setup_venv311.sh"

if [[ ! -f "$TARGET" ]]; then
  echo "[setup-venv-wrapper] error: ${TARGET} not found." >&2
  exit 1
fi

exec "$TARGET" "$@"
