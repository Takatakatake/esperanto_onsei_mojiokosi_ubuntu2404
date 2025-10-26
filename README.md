# Esperanto Realtime Transcription

日本語版 README は `README_ja.md` をご覧ください。

Realtime transcription pipeline tailored for Esperanto conversations on Zoom and Google Meet.  
The implementation follows the design principles captured in *エスペラント（Esperanto）会話を“常時・高精度・低遅延”に文字起こしするための実現案1.md*:

- Speechmatics Realtime STT (official `eo` support, talker diarization, custom dictionary hooks)
- Vosk offline backend as a zero-cost / air-gapped fallback
- Zoom Closed Caption API injection for native on-screen subtitles
- Pipeline abstraction ready for additional engines (e.g., Whisper streaming, Google STT)
- Browser-based caption board with optional Japanese/Korean translations and Discord webhook batching

> ⚠️ Speechmatics and Zoom endpoints require valid credentials and meeting-level permissions.  
> Keep participants informed about live transcription to comply with privacy & platform policies.

---

## 1. Prerequisites

- Python 3.10+ (tested with CPython 3.10/3.11)
- `virtualenv` or `uv` for dependency isolation
- Audio route from Zoom/Meet into the local machine (e.g. VB-Audio, VoiceMeeter, BlackHole, JACK)
- Speechmatics account with realtime entitlement and API key (when using the cloud backend)
- Zoom host privileges to obtain the Closed Caption POST URL (or use Recall.ai/Meeting SDK for media access)

Optional:

- GPU or high-performance CPU if you plan to run the Whisper backend (recommended: RTX 4070+ or Apple M2 Pro+)
- Google Meet Media API (developer preview) for direct audio capture when available
- Vosk Esperanto model (`vosk-model-small-eo-0.42` or later) if you plan to run fully offline

---

## 0. 日本語クイックスタート（GitHub から）

```bash
git clone git@github.com:Takatakatake/esperanto_onsei_mojiokosi.git
cd esperanto_onsei_mojiokosi
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
# リポジトリには伏せ字入りの `.env` を同梱しています（安全な雛形）。
# 既に `.env` がある場合は開いて値を置き換えてください。
# 無い場合は例からコピーして編集します：
test -f .env || cp .env.example .env
```

編集ポイント（例）：

```ini
SPEECHMATICS_API_KEY=****************************   # 本物のキーに置換
SPEECHMATICS_CONNECTION_URL=wss://eu2.rt.speechmatics.com/v2
AUDIO_DEVICE_INDEX=8                               # --list-devices の番号
WEB_UI_ENABLED=true
TRANSLATION_ENABLED=true
TRANSLATION_TARGETS=ja,ko
```

その後、デバイス確認と起動：

```bash
python -m transcriber.cli --list-devices
python -m transcriber.cli --log-level=INFO
```

Web UI は `http://127.0.0.1:8765` で開けます（`.env` の `WEB_UI_OPEN_BROWSER=true` で自動起動）。

---

## 2. Bootstrap

```bash
cd /media/yamada/SSD-PUTA1/CODEX作業用202510
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
# `.env` は本リポジトリに同梱（伏せ字）されています。無い場合のみコピー：
test -f .env || cp .env.example .env
```

Edit `.env` (サンプルは伏せ字。実値に置換してください):

```ini
TRANSCRIPTION_BACKEND=speechmatics  # or vosk / whisper
SPEECHMATICS_API_KEY=sk_live_************************
SPEECHMATICS_APP_ID=realtime
SPEECHMATICS_LANGUAGE=eo
ZOOM_CC_POST_URL=https://wmcc.zoom.us/closedcaption?... (host-provided URL)
```

Optional overrides (all values can be left unset if you stick with defaults):

```ini
AUDIO_DEVICE_INDEX=8            # from --list-devices output
AUDIO_SAMPLE_RATE=16000
AUDIO_CHUNK_DURATION_SECONDS=0.5
ZOOM_CC_MIN_POST_INTERVAL_SECONDS=1.0
VOSK_MODEL_PATH=/absolute/path/to/vosk-model-small-eo-0.42
WHISPER_MODEL_SIZE=medium
WHISPER_DEVICE=auto              # e.g. cuda, cpu, mps
WHISPER_COMPUTE_TYPE=default     # e.g. float16 (for GPU)
WHISPER_SEGMENT_DURATION=6.0
WHISPER_BEAM_SIZE=1
TRANSCRIPT_LOG_PATH=logs/esperanto-caption.log
WEB_UI_ENABLED=true
TRANSLATION_ENABLED=true
TRANSLATION_PROVIDER=google
TRANSLATION_SOURCE_LANGUAGE=eo
TRANSLATION_TARGETS=ja,ko
TRANSLATION_TIMEOUT_SECONDS=8.0
GOOGLE_TRANSLATE_CREDENTIALS_PATH=/absolute/path/to/gen-lang-client-xxxx.json
GOOGLE_TRANSLATE_MODEL=nmt
# (API キー派生の場合は GOOGLE_TRANSLATE_API_KEY=... を設定)
DISCORD_WEBHOOK_ENABLED=true
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
DISCORD_BATCH_FLUSH_INTERVAL=2.0
DISCORD_BATCH_MAX_CHARS=350
```

---

## 3. Usage

List capture devices and verify routing:

```bash
python -m transcriber.cli --list-devices
```

Start the pipeline (prints finals to stdout, pushes finals to Zoom):

```bash
python -m transcriber.cli --log-level=INFO
```

- With `WEB_UI_ENABLED=true` the lightweight caption board runs on `http://127.0.0.1:8765`. It displays the latest final transcript plus optional translations with per-language toggles (e.g. Japanese / Korean).
- When a Discord webhook URL is configured the pipeline batches finals into natural sentences and posts a single message containing the Esperanto line and all enabled translations.

Switch backends or override log output on demand:

```bash
python -m transcriber.cli --backend=vosk --log-file=logs/offline.log
python -m transcriber.cli --backend=whisper --log-level=DEBUG
```

- Translation smoke test (uses current `.env` settings):

```bash
scripts/test_translation.py "Bonvenon al nia kunsido."
```

Stopping with `Ctrl+C` sends a graceful shutdown signal. Logs show:

- `Final:` lines once Speechmatics emits confirmed segments
- Caption POST success/failure (watch for 401/403 → token expired or meeting not ready)
- When transcript logging is enabled, the log file receives timestamped lines for each confirmed utterance.

Zoom-specific steps (per the proposal):

1. Host joins the meeting, enables **Allow participants to request Live Transcription** and copies the Closed Caption API URL.
2. Paste the URL into `.env` or set `ZOOM_CC_POST_URL` at runtime (`export ZOOM_CC_POST_URL=...`).
3. Participants enable subtitles in the Zoom UI. Timing is ~1 s end-to-end in normal network conditions.

Google Meet options:

- **Meet Media API (preview)**: swap the audio frontend to consume the REST/WS media stream, then feed PCM into the same Speechmatics client.
- **Screen overlay**: run this pipeline locally, render the transcript in a floating window (future work) and share it via Meet Companion mode.

---

## 4. Architecture Notes

- `transcriber/audio.py`: pulls `int16` PCM frames from the chosen device at 16 kHz (configurable).  
- `transcriber/asr/speechmatics_backend.py`: realtime WebSocket client (`Authorization: Bearer <API key>`) streaming PCM and parsing partial/final JSON with diarization metadata.  
- `transcriber/asr/whisper_backend.py`: chunked realtime transcription using faster-whisper (GPU/M-series friendly).  
- `transcriber/asr/vosk_backend.py`: lightweight offline recognizer built on Vosk/Kaldi for zero-cost fallback.  
- `transcriber/pipeline.py`: orchestrates audio capture, chosen backend, transcript logging, and caption delivery.  
- `transcriber/zoom_caption.py`: throttled POSTs (`text/plain`, `seq` parameter) to Zoom’s Closed Caption API.  
- `transcriber/translate/service.py`: async translation client (LibreTranslate-compatible) used to enrich Web UI/Discord outputs.  
- `transcriber/discord/batcher.py`: debounce/aggregate Discord webhook posts and align them with translated text.  
- `transcriber/cli.py`: CLI helpers for device discovery, config inspection, backend override, and graceful shutdown.

Anticipated extensions (mirroring the proposal’s roadmap):

- Additional transcription backends (Whisper streaming, Google STT) via the same interface
- Post-processing pipeline (Esperanto diacritics normalisation, punctuation refinements)
- Observer hooks for on-screen display, translation, persistence

---

## 5. Next Steps & Validation

1. Validate Speechmatics handshake: confirm `start` payload matches your tenant’s latest schema (see Docs §Real-time Quickstart). Adjust `transcription_config` as needed (custom dictionary, `operating_point`, etc.).  
2. Run a dry rehearsal with recorded Esperanto audio: measure WER, diarization accuracy, delay. Use logs to capture `raw` payloads for tuning.  
3. Register frequent Esperanto-specific words in the Speechmatics Custom Dictionary (Docs §4) and mirror the same lexicon for Vosk post-processing if required.  
4. Validate the offline path: download the Vosk Esperanto model, run `python -m transcriber.cli --backend=vosk`, and compare WER/latency vs Speechmatics.  
5. Benchmark the Whisper backend on your hardware (`python -m transcriber.cli --backend=whisper`) to understand GPU/CPU load and tune `WHISPER_SEGMENT_DURATION`.  
6. When scaling to production, wrap the CLI with a supervisor (systemd, pm2) and add persistent logging/metrics as emphasised in the guidelines.  
7. Document participant consent workflow; automate “transcription active” notifications inside meeting invites.
8. Test the translation pipeline end-to-end: set `TRANSLATION_TARGETS=ja,ko`, confirm Google Cloud Translation（or LibreTranslate）responds quickly, and verify that Web UI toggles/Discord posts include the expected bilingual lines.
   - Google Cloud Translationを使う場合は `TRANSLATION_PROVIDER=google`、`GOOGLE_TRANSLATE_CREDENTIALS_PATH=/path/to/service-account.json` または `GOOGLE_TRANSLATE_API_KEY` を設定し、必要なら `GOOGLE_TRANSLATE_MODEL=nmt` などを指定します。サービスアカウントには Cloud Translation API の権限を付与してください。

For questions on alternate capture paths (Recall.ai bots, Meet Media API wrappers, Whisper fallback) reuse the abstractions in `audio.py` and `transcriber/asr/`—new producers/consumers slot in without touching the pipeline control logic.

---

## 7. Recommended Launch Workflow

To keep the Web UI on a fixed port (8765) and avoid “already in use” loops, a tiny launcher is provided:

```bash
install -Dm755 scripts/run_transcriber.sh ~/bin/run-transcriber.sh
source /media/yamada/SSD-PUTA1/CODEX作業用202510/.venv311/bin/activate
~/bin/run-transcriber.sh              # defaults to backend=speechmatics, log-level=INFO
```

`run_transcriber.sh` closes stale listeners on the selected port (default 8765), waits for the socket to truly free, and then starts `python -m transcriber.cli`. The browser always connects to `http://127.0.0.1:8765` and translations (Google ja/ko) show up immediately.

Need a different port or backend? Override via environment variables:

```bash
PORT=8766 LOG_LEVEL=DEBUG BACKEND=whisper ~/bin/run-transcriber.sh
```

Prefer to keep manually running `python -m transcriber.cli`? Use the prep script once per run:

```bash
install -Dm755 scripts/prep_webui.sh ~/bin/prep-webui.sh
source /media/yamada/SSD-PUTA1/CODEX作業用202510/.venv311/bin/activate
~/bin/prep-webui.sh && python -m transcriber.cli --backend=speechmatics --log-level=INFO
```

`prep-webui.sh` terminates lingering CLI processes, frees port 8765, and waits until it is available so the subsequent CLI command binds that port on the first try.

8765 を完全に空にしたいときは、以下 3 行を続けて実行してください（Chrome の Network Service などが掴んでいても強制的に開放します）:

```bash
pkill -f "python -m transcriber.cli" || true
lsof -t -iTCP:8765 | xargs -r kill -9 || true
sleep 0.5 && lsof -iTCP:8765    # 何も出なければOK
```

その後、必要なら通常どおり `python -m transcriber.cli ...` を再起動してください。

---

## 8. Audio Loopback Stability

PipeWire/WirePlumber occasionally revert the default input to a hardware mic, which breaks Meet loopback capture. To lock the defaults and auto-heal if the state files change, follow `docs/audio_loopback.md`:

```bash
install -Dm755 scripts/wp-force-monitor.sh ~/bin/wp-force-monitor.sh
~/bin/wp-force-monitor.sh                           # once, forces analog monitor
cp systemd/wp-force-monitor.{service,path} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now wp-force-monitor.service wp-force-monitor.path
```

`wp-force-monitor` keeps the default source on `alsa_output...analog-stereo.monitor` so Discord/Speechmatics always hear the Meet loopback, while leaving the sink under user control unless `SINK_NAME=...` is provided.

---

## 6. Audio Device Hot-Reload (Ubuntu/Linux)

The application includes automatic audio device change detection and reconnection to handle system-level device switching without interrupting the transcription pipeline.

### Features

- **Automatic Device Monitoring**: Checks default input device every 2 seconds (configurable)
- **Seamless Reconnection**: Automatically reconnects to the new device when changed
- **Health Checks**: Detects when the audio stream stops receiving data (5-second timeout) and automatically restarts
- **Error Recovery**: Automatically recovers from stream errors with retry logic

### Configuration

Add to `.env` to customize the monitoring interval:

```ini
AUDIO_DEVICE_CHECK_INTERVAL=2.0  # seconds between device checks (default: 2.0)
```

### Diagnostics

Run the audio device diagnostic tool to see all available devices:

```bash
python3 scripts/diagnose_audio.py
```

This will show:
- All available audio input/output devices
- Current default devices
- Device indices for configuration
- Recommendations for loopback setup

### Common Issues (Ubuntu/PulseAudio)

**Problem**: Audio stops when switching output devices in system settings

**Cause**: Output device switching can affect loopback routing in PulseAudio/PipeWire

**Solution**:
1. The application will automatically reconnect within 2-5 seconds
2. For persistent loopback, add to PulseAudio config:
   ```bash
   pactl load-module module-loopback latency_msec=1
   ```

**Problem**: Frequent reconnections

**Solution**: Increase check interval or pin to a specific device:
```ini
AUDIO_DEVICE_CHECK_INTERVAL=5.0
# Or pin to a specific device (see diagnose_audio.py output)
AUDIO_DEVICE_INDEX=8
```

For detailed troubleshooting, see [docs/ubuntu_audio_troubleshooting.md](docs/ubuntu_audio_troubleshooting.md).
