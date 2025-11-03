#!/usr/bin/env bash
# Convenience wrapper at repo root to invoke the actual reset script.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/scripts/reset_audio_defaults.sh" "$@"
