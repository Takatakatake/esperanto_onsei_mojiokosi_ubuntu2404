#!/usr/bin/env bash
#
# Beginner-friendly bootstrapper for the `.venv311` virtual environment.
# Features:
#   - Detects or validates a Python 3.11 interpreter (or newer)
#   - Offers safe reuse or recreation of an existing venv
#   - Upgrades pip/setuptools/wheel before installing requirements
#   - Provides clear guidance when prerequisites are missing
#
# Usage:
#   scripts/setup_venv311.sh [--force] [--non-interactive] [--venv PATH] [--requirements FILE] [--python PATH]
#
# The script is intentionally chatty so that first-time contributors can follow along.

set -euo pipefail

SCRIPT_NAME=$(basename "${BASH_SOURCE[0]}")
SCRIPT_DIR=$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "${SCRIPT_DIR}/.." && pwd)

DEFAULT_VENV=".venv311"
DEFAULT_REQUIREMENTS="requirements.txt"

VENV_DIR="$DEFAULT_VENV"
REQUIREMENTS_FILE="$DEFAULT_REQUIREMENTS"
PYTHON_REQUESTED="${PYTHON:-}"
FORCE_RECREATE=0
NON_INTERACTIVE=0

LOG_PREFIX="[setup-venv]"

log()   { printf "%s %s\n" "${LOG_PREFIX}" "$*"; }
warn()  { printf "%s warning: %s\n" "${LOG_PREFIX}" "$*" >&2; }
error() { printf "%s error: %s\n" "${LOG_PREFIX}" "$*" >&2; }

die() {
  error "$*"
  exit 1
}

safe_remove_dir() {
  local target="$1"
  if [[ -z "$target" || "$target" == "/" || "$target" == "." ]]; then
    die "Refusing to remove suspicious path: '${target}'"
  fi
  rm -rf "$target"
}

usage() {
  cat <<EOF
Usage: ${SCRIPT_NAME} [options]

Options:
  --venv PATH           Target virtual environment directory (default: ${DEFAULT_VENV})
  --requirements FILE   Requirements file to install (default: ${DEFAULT_REQUIREMENTS})
  --python CMD          Explicit Python interpreter to use (default: auto-detect)
  --force               Recreate the virtual environment even if it already exists
  --non-interactive     Do not prompt; reuse existing environments unless --force is supplied
  --help                Show this help message

Environment variables:
  PYTHON                Shortcut for --python. When set, overrides interpreter detection.

Examples:
  ${SCRIPT_NAME}
  ${SCRIPT_NAME} --force
  PYTHON=/opt/python/3.11/bin/python ${SCRIPT_NAME} --requirements requirements-dev.txt
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --venv)
      [[ $# -ge 2 ]] || die "--venv requires a path argument"
      VENV_DIR="$2"
      shift 2
      ;;
    --requirements)
      [[ $# -ge 2 ]] || die "--requirements requires a file argument"
      REQUIREMENTS_FILE="$2"
      shift 2
      ;;
    --python)
      [[ $# -ge 2 ]] || die "--python requires an interpreter argument"
      PYTHON_REQUESTED="$2"
      shift 2
      ;;
    --force)
      FORCE_RECREATE=1
      shift
      ;;
    --non-interactive)
      NON_INTERACTIVE=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      usage
      die "Unknown option: $1"
      ;;
  esac
done

if [[ -n "$PYTHON_REQUESTED" ]]; then
  log "Python interpreter requested via option: ${PYTHON_REQUESTED}"
fi

prompt_yes_no() {
  local prompt="${1:-Continue?}"
  local default="${2:-y}"

  if (( NON_INTERACTIVE )); then
    [[ "${default,,}" == "y" ]]
    return
  fi

  local reply
  local suffix="[y/N]"
  if [[ "${default,,}" == "y" ]]; then
    suffix="[Y/n]"
  fi

  while true; do
    read -r -p "${prompt} ${suffix} " reply || return 1
    reply=${reply:-$default}
    case "${reply,,}" in
      y|yes) return 0 ;;
      n|no)  return 1 ;;
      *)     printf "Please answer yes or no.\n" ;;
    esac
  done
}

ensure_python_command() {
  local cmd=("$@")
  if ! command -v "${cmd[0]}" >/dev/null 2>&1; then
    return 1
  fi

  if ! "${cmd[@]}" - <<'PYVER' >/dev/null 2>&1
import sys
major, minor = sys.version_info[:2]
if major != 3 or minor < 11:
    raise SystemExit(1)
PYVER
  then
    return 2
  fi
  return 0
}

detect_python() {
  local candidates=()
  if [[ -n "$PYTHON_REQUESTED" ]]; then
    candidates+=("$PYTHON_REQUESTED")
  fi

  candidates+=("python3.11" "python3" "python")

  if command -v py >/dev/null 2>&1; then
    candidates+=("py -3.11" "py -3")
  fi

  local candidate cmd_parts
  for candidate in "${candidates[@]}"; do
    IFS=' ' read -r -a cmd_parts <<< "$candidate"
    ensure_python_command "${cmd_parts[@]}"
    local status=$?
    if [[ $status -eq 0 ]]; then
      PYTHON_CMD=("${cmd_parts[@]}")
      PYTHON_PATH=$("${cmd_parts[@]}" - <<'PYPATH'
import sys
print(sys.executable)
PYPATH
)
      PYTHON_VERSION=$("${cmd_parts[@]}" - <<'PYVER'
import sys
print("{}.{}.{}".format(*sys.version_info[:3]))
PYVER
)
      log "Using Python ${PYTHON_VERSION} at ${PYTHON_PATH}"
      return 0
    elif [[ $status -eq 2 ]]; then
      warn "${candidate} is present but below Python 3.11; skipping"
    fi
  done

  return 1
}

PYTHON_CMD=()
PYTHON_PATH=""
PYTHON_VERSION=""

if ! detect_python; then
  cat <<'EOF' >&2
[setup-venv] error: Could not locate a Python interpreter version 3.11 or newer.

Suggested fixes:
  - (Linux/macOS) Install Python 3.11 via your package manager (e.g., `sudo apt install python3.11 python3.11-venv`)
  - (macOS) Use Homebrew: `brew install python@3.11`
  - (Windows) Install Python 3.11 and re-run this script inside WSL or Git Bash
  - Install pyenv (https://github.com/pyenv/pyenv) and run: `pyenv install 3.11 && pyenv local 3.11`

Once Python 3.11 is available, re-run this script.
EOF
  exit 1
fi

if ! "${PYTHON_CMD[@]}" - <<'PYCHECK'
try:
    import venv  # noqa: F401
except ModuleNotFoundError:
    raise SystemExit(1)
PYCHECK
then
  cat <<'EOF' >&2
[setup-venv] error: The detected Python lacks the `venv` module.

On Debian/Ubuntu:
  sudo apt install python3.11-venv

On macOS (with Homebrew Python):
  brew install python@3.11

After installing the optional component, rerun this script.
EOF
  exit 1
fi

cd "$REPO_ROOT"

log "Project root: ${REPO_ROOT}"
log "Virtual environment directory: ${VENV_DIR}"

if [[ -d "$VENV_DIR" ]]; then
  if (( FORCE_RECREATE )); then
    log "Removing existing virtual environment (forced)"
    safe_remove_dir "$VENV_DIR"
  else
    if prompt_yes_no "Existing virtual environment detected at ${VENV_DIR}. Reuse it?" "y"; then
      log "Reusing existing environment."
    else
      if prompt_yes_no "Delete and recreate ${VENV_DIR}?" "n"; then
        log "Removing old environment..."
        safe_remove_dir "$VENV_DIR"
      else
        die "Aborted by user."
      fi
    fi
  fi
fi

if [[ ! -d "$VENV_DIR" ]]; then
  log "Creating virtual environment..."
  "${PYTHON_CMD[@]}" -m venv "$VENV_DIR"
else
  log "Skipping creation step; environment already exists."
fi

VENV_PYTHON="${VENV_DIR}/bin/python"
if [[ ! -x "$VENV_PYTHON" ]]; then
  die "Virtual environment looks broken: ${VENV_PYTHON} is missing or not executable."
fi

log "Upgrading pip/setuptools/wheel..."
"$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel

if [[ -n "$REQUIREMENTS_FILE" ]]; then
  if [[ -f "$REQUIREMENTS_FILE" ]]; then
    log "Installing dependencies from ${REQUIREMENTS_FILE}..."
    "$VENV_PYTHON" -m pip install -r "$REQUIREMENTS_FILE"
  else
    warn "Requirements file ${REQUIREMENTS_FILE} not found; skipping dependency installation."
  fi
else
  warn "No requirements file specified; skipping dependency installation."
fi

cat <<EOF

${LOG_PREFIX} Success!

Next steps:
  source "${VENV_DIR}/bin/activate"
  python -m transcriber.cli --check-environment

Tip: run \`deactivate\` when you are done.
EOF
