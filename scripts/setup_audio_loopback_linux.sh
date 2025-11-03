#!/usr/bin/env bash
#
# Create a null sink for PipeWire/PulseAudio and loop audio to the headphone sink
# while exposing the monitor as the default input for transcription.
#
set -euo pipefail

log() { printf '[setup_audio_loopback] %s\n' "$*" >&2; }
need() { command -v "$1" >/dev/null 2>&1 || { log "missing dependency: $1"; exit 1; }; }

need pactl

SINK_NAME="${HEADPHONE_SINK:-}"

if [[ -z "$SINK_NAME" ]]; then
  if ! def_sink_line=$(pactl info | grep -E '^Default Sink:' || true); then
    log "could not read default sink from pactl info"
    def_sink_line=""
  fi
  SINK_NAME=$(sed -E 's/^Default Sink: *//' <<<"$def_sink_line")
  if [[ -z "$SINK_NAME" ]]; then
    log "no default sink detected automatically."
    mapfile -t sinks < <(pactl list short sinks | awk '{print $2}')
    if [[ ${#sinks[@]} -eq 0 ]]; then
      log "pactl reports no sinks; aborting."
      exit 1
    fi
    if [[ ${#sinks[@]} -eq 1 ]]; then
      SINK_NAME="${sinks[0]}"
      log "Auto-selecting the only available sink: $SINK_NAME"
    else
      log "available sinks:"
      for idx in "${!sinks[@]}"; do
        printf '  %d) %s\n' "$((idx + 1))" "${sinks[$idx]}"
      done
      read -r -p "Enter sink number or name [1]: " selection
      if [[ -z "$selection" ]]; then
        SINK_NAME="${sinks[0]}"
      elif [[ "$selection" =~ ^[0-9]+$ ]] && (( selection >= 1 && selection <= ${#sinks[@]} )); then
        SINK_NAME="${sinks[selection-1]}"
      else
        SINK_NAME="$selection"
      fi
      if [[ -z "$SINK_NAME" ]]; then
        log "No sink selected. Run again with HEADPHONE_SINK=<sink_name> if needed."
        exit 1
      fi
    fi
  fi
fi

log "Using headphone/output sink: $SINK_NAME"

VIRT_SINK_NAME=codex_transcribe
if pactl list short sinks | awk '{print $2}' | grep -qx "$VIRT_SINK_NAME"; then
  log "Virtual sink '$VIRT_SINK_NAME' already exists."
else
  log "Creating virtual sink '$VIRT_SINK_NAME'"
  pactl load-module module-null-sink sink_name="$VIRT_SINK_NAME" sink_properties=device.description=CodexTranscribe >/dev/null
fi

VIRT_MONITOR="${VIRT_SINK_NAME}.monitor"
EXISTS_LOOPBACK=$(pactl list short modules | grep -E "module-loopback" | grep -F "$VIRT_MONITOR" | grep -F "$SINK_NAME" || true)
if [[ -z "$EXISTS_LOOPBACK" ]]; then
  log "Creating loopback ${VIRT_MONITOR} -> ${SINK_NAME} (latency 10ms)"
  pactl load-module module-loopback source="$VIRT_MONITOR" sink="$SINK_NAME" latency_msec=10 >/dev/null
else
  log "Loopback from ${VIRT_MONITOR} to ${SINK_NAME} already exists."
fi

log "Setting default sink -> ${VIRT_SINK_NAME}"
pactl set-default-sink "$VIRT_SINK_NAME" || true
log "Setting default source -> ${VIRT_MONITOR}"
pactl set-default-source "$VIRT_MONITOR"

log "Now:"
pactl info | grep -E 'Default Sink|Default Source' || true
log "Complete."
