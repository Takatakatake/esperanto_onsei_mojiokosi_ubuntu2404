#!/usr/bin/env bash
#
# Inspect macOS audio loopback prerequisites and print guidance for setup.
#
set -euo pipefail

log() { printf '[setup_audio_loopback] %s\n' "$*" >&2; }

log "macOS ループバック環境を確認しています..."

BLACKHOLE_DRIVER="/Library/Audio/Plug-Ins/HAL/BlackHole2ch.driver"
SOUNDFLOWER_DRIVER="/Library/Audio/Plug-Ins/HAL/Soundflower.driver"

if [[ -d "$BLACKHOLE_DRIVER" ]]; then
  log "BlackHole (2ch) がインストールされています。"
elif [[ -d "$SOUNDFLOWER_DRIVER" ]]; then
  log "Soundflower がインストールされています。BlackHole などの最新ドライバも検討してください。"
else
  log "BlackHole / Soundflower ドライバが見つかりませんでした。"
  if command -v brew >/dev/null 2>&1; then
    log "インストール例: brew install blackhole-2ch"
    log "インストール後は “Audio MIDI 設定” でマルチ出力装置を作成し、ループバック入力を構成します。"
  else
    log "Homebrew が未導入です。https://brew.sh/ からインストールした上で BlackHole を導入してください。"
  fi
fi

log "現在の入力デバイス一覧:"
system_profiler SPAudioDataType 2>/dev/null | awk '/Input Device:/,/^$/' || true

log "マルチ出力装置でスピーカーと BlackHole をまとめ、BlackHole を既定入力に設定することを推奨します。"
log "完了しました。"
