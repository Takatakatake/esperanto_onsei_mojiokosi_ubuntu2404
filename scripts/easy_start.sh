#!/usr/bin/env bash
#
# Quick helper for beginners: run environment checks and start the pipeline.
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ -f ".venv311/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source ".venv311/bin/activate"
fi

PYTHON_BIN="python"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
    printf '[easy_start] Falling back to %s because python was not found on PATH.\n' "$PYTHON_BIN" >&2
  else
    printf '[easy_start] Error: python が見つかりません。`python3` をインストールするか PATH を更新してください。\n' >&2
    exit 127
  fi
fi

if ! "$PYTHON_BIN" -m transcriber.cli --easy-start "$@"; then
  status=$?
  printf '[easy_start] CLI exited with code %d. 詳細は上記ログまたは logs/ ディレクトリを確認してください。\n' "$status" >&2
  exit "$status"
fi
