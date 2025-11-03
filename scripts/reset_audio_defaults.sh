#!/usr/bin/env bash
#
# Restore PipeWire/PulseAudio defaults after using the virtual loopback helper.
# Provides simple interactive prompts to pick sink (output) and source (input).
#
set -euo pipefail

log() { printf '[reset_audio_defaults] %s\n' "$*" >&2; }
need() { command -v "$1" >/dev/null 2>&1 || { log "missing dependency: $1"; exit 1; }; }

need pactl

select_from_list() {
  local prompt="$1"; shift
  local entries=("$@")
  if [[ "${#entries[@]}" -eq 0 ]]; then
    echo ""
    return 0
  fi
  if [[ "${#entries[@]}" -eq 1 ]]; then
    log "$prompt -> ${entries[0]}"
    echo "${entries[0]}"
    return 0
  fi
  log "$prompt"
  local i
  for ((i = 0; i < ${#entries[@]}; i++)); do
    printf '  %d) %s\n' "$((i + 1))" "${entries[$i]}" >&2
  done
  read -r -p "Enter number or name [1]: " selection
  if [[ -z "$selection" ]]; then
    echo "${entries[0]}"
    return 0
  fi
  if [[ "$selection" =~ ^[0-9]+$ ]] && (( selection >= 1 && selection <= ${#entries[@]} )); then
    echo "${entries[selection-1]}"
    return 0
  fi
  echo "$selection"
}

log "Listing available output devices (sinks)"
mapfile -t sinks_raw < <(pactl list short sinks | awk '{print $2}')
if [[ ${#sinks_raw[@]} -eq 0 ]]; then
  log "No sinks reported by pactl."
  exit 1
fi
sinks=()
others=()
for sink in "${sinks_raw[@]}"; do
  if [[ "$sink" == codex_transcribe* ]]; then
    others+=("$sink")
  else
    sinks+=("$sink")
  fi
done
sinks+=("${others[@]}")
sink_choice=$(select_from_list "Select default output" "${sinks[@]}")
if [[ -z "$sink_choice" ]]; then
  log "No sink selected; aborting."
  exit 1
fi

log "Listing available input devices (sources)"
mapfile -t sources_raw < <(pactl list short sources | awk '{print $2}')
if [[ ${#sources_raw[@]} -eq 0 ]]; then
  log "No sources reported by pactl."
  exit 1
fi
sources=()
others=()
for source in "${sources_raw[@]}"; do
  if [[ "$source" == *".monitor"* || "$source" == codex_transcribe* ]]; then
    others+=("$source")
  else
    sources+=("$source")
  fi
done
sources+=("${others[@]}")
source_choice=$(select_from_list "Select default input" "${sources[@]}")
if [[ -z "$source_choice" ]]; then
  log "No source selected; aborting."
  exit 1
fi

log "Setting default sink -> $sink_choice"
pactl set-default-sink "$sink_choice" || log "Failed to set default sink"

log "Setting default source -> $source_choice"
pactl set-default-source "$source_choice" || log "Failed to set default source"

read -r -p "Unload virtual loopback modules (module-loopback/module-null-sink)? [y/N]: " unload
if [[ "$unload" == "y" || "$unload" == "Y" ]]; then
  pactl unload-module module-loopback 2>/dev/null || true
  pactl unload-module module-null-sink 2>/dev/null || true
  log "Loopback modules unloaded (if they were loaded)."
fi

log "Done."
