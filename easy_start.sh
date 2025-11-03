#!/usr/bin/env bash
#
# Convenience wrapper so users can launch from the repository root.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/scripts/easy_start.sh" "$@"
