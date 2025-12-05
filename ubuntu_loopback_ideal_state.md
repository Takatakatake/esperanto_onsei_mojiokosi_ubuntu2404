# Ubuntu イヤホン運用 引き継ぎメモ

この文書は、Ubuntu 上で「イヤホンでもスピーカーでも PC 再生音を聞きながら、その同じ音声をリアルタイム文字起こしに送る」という理想的な状態を再現するための手順です。PipeWire/PulseAudio 監視と `.env` 設定、サウンド設定アプリ、付属スクリプトを組み合わせれば、どのマシンでも同一状況を再現できます。

## 1. 事前準備

1. 依存パッケージ
   - `python3.11`, `pip`, `virtualenv`
   - `pavucontrol`（必須ではないが、録音ソース確認に便利）
   - `pactl`（PulseAudio/PipeWire 管理に使用。一般的な Ubuntu には標準で入っている）
2. 仮想環境
   ```bash
   python3.11 -m venv .venv311
   source .venv311/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
3. `.env` を以下の方針で編集（値は環境に応じて置き換え）
   ```ini
   TRANSCRIPTION_BACKEND=speechmatics
   SPEECHMATICS_LANGUAGE=eo
   SPEECHMATICS_SAMPLE_RATE=16000
   AUDIO_CAPTURE_MODE=loopback
   AUDIO_DEVICE_INDEX=4          # `python -m transcriber.cli --list-devices` で得た pipewire の番号
   AUDIO_SAMPLE_RATE=16000       # 内部処理レート
   AUDIO_DEVICE_SAMPLE_RATE=48000  # 実ハードのレート（48 kHz 推奨）
   AUDIO_CHANNELS=1
   AUDIO_CHUNK_DURATION_SECONDS=0.5
   ```
   - 16 kHz で Speechmatics に送る一方、デバイス実レートを 48 kHz に固定しておくとノイズ・ドロップを避けやすい（`docs/audio_loopback.md` と `.env` の既存コメントに沿う）。
   - `AUDIO_DEVICE_INDEX` は `pipewire` か `default` を指定する。PipeWire 環境では monitor がこの仮想デバイス配下に現れ、イヤホン／スピーカーの切り替えを透過的に扱える。

## 2. サウンド設定の考え方

- GNOME の「設定 → サウンド」で任意の出力（アナログヘッドフォン／スピーカーなど）を選び、実際に音が鳴ることを確認する。PipeWire は出力シンクごとに `Monitor of <sink>` を用意するため、どの出力を選んでも monitor から同じ音を取得できる。
- 入力デバイスは通常どおりマイクのままで構わない。Transcriber は `AUDIO_DEVICE_INDEX` で指定した monitor を直接開くため、OS の入力設定に干渉しない。
- Bluetooth ヘッドセット利用時は HFP/HSP モードに落ちるとモノラル 16 kHz になるので、A2DP か有線を推奨（`Windows-VBCable  Ubuntu-pavucontrol.txt` の安定性メモを参照）。

## 3. 起動前の確認コマンド

```bash
source .venv311/bin/activate
python -m transcriber.cli --list-devices      # pipewire(default) の index を確認
python -m transcriber.cli --diagnose-audio    # 設定済みデバイスが pipewire になっているか確認
```

診断レポートの「設定済みデバイス」が `#4 pipewire` など期待値なら準備完了。ループバック候補に `pipewire`/`default` が表示されない場合は PipeWire/PulseAudio サービスの再起動や `pactl info` での確認を行う。

## 4. 実行手順

1. イヤホンを装着するか、スピーカーを使用するかを選択し、再生したいアプリ（Zoom/Meet/YouTube 等）の音声を PC で流す。
2. 仮想環境が有効な shell で `python -m transcriber.cli --log-level=INFO` もしくは `./easy_start.sh` を実行。
3. 初回のみ `pavucontrol` を開き「録音」タブで `python -m transcriber.cli` の入力ソースが `Monitor of <出力デバイス>` になっているか確認。ほとんどの環境では自動で monitor が割り当てられる。何らかの理由でマイクが選ばれていたら monitor を選び直す。
4. CLI ログに `Capturing audio from device index 4 (pipewire)` のような行が出て、数秒後に Speechmatics の部分認識／確定認識ログが流れれば OK。
5. イヤホン着脱中も monitor が変わらないことを確認する。もし音が落ちたら `python -m transcriber.cli --diagnose-audio` を再実行し、`pavucontrol` でソースを再指定する。

## 5. 自動復旧と便利スクリプト

- **自動監視機能**: `docs/ubuntu_audio_troubleshooting.md` に記載の通り、アプリはデフォルト入力の変更や無音状態を定期監視し、必要なら再接続する。`AUDIO_DEVICE_CHECK_INTERVAL`（デフォルト 2 秒）で感度を調整できる。
- **既定ソース固定**: どうしても monitor が他の入力に切り替わる環境では、`install -Dm755 scripts/wp-force-monitor.sh ~/bin/wp-force-monitor.sh` を実行し、必要に応じて systemd user サービス化して monitor を常に再設定する。
- **設定リセット**: トラブル時は `bash scripts/reset_audio_defaults.sh` を実行して物理スピーカー/マイクを選び直し、ループバック用の `module-loopback`/`module-null-sink` をアンロードできる。
- **ループバック再構築**: もし monitor が作成されない環境（古い PulseAudio 等）では、`scripts/setup_audio_loopback_linux.sh` を使って `codex_transcribe` という null sink + monitor を明示的に生成し、出力先（HEADPHONE_SINK）をイヤホンに指定することで同じ理想状態を再現できる。

## 6. 検証チェックリスト

1. `pactl info | grep 'Default Source'` → monitor（例: `alsa_output.pci-0000_00_1f.3.analog-stereo.monitor`）になっている。
2. `python -m transcriber.cli --list-devices` → `pipewire`/`default` が IN/OUT デバイスとして見えている。
3. CLI ログに「no data」警告が出ていない。出た場合は `pavucontrol` で monitor を選び直す。
4. イヤホンを抜く → スピーカー再生 → イヤホンを再び挿す、の順に切り替えても認識が途切れない。
5. `logs/meet-session.log` に連続した書き込み（Transcript）が残っている。

## 7. トラブル対処早見表

| 症状 | 想定原因 | 対処 |
| --- | --- | --- |
| イヤホン挿抜で無音になる | GNOME が既定入力をマイクに戻した | `pavucontrol` で monitor を選ぶ／`wp-force-monitor.sh` を実行 |
| ループバック候補に `pipewire` が出ない | PipeWire/PulseAudio が不安定 | `systemctl --user restart pipewire pipewire-pulse` |
| ノイズ・ドロップが増えた | サンプリング不一致 | `.env` の `AUDIO_DEVICE_SAMPLE_RATE=48000` を確認、会議アプリ側も 48 kHz に合わせる |
| 設定が仮想デバイスのまま残る | null-sink をアンロードしていない | `bash scripts/reset_audio_defaults.sh` で戻す |

---

この手順を守れば、配布先の Ubuntu 環境でも「イヤホンで聴きながら同じ音を文字起こしに回す」状態を素早く再現できる。疑問点があれば `docs/audio_loopback.md` と `docs/ubuntu_audio_troubleshooting.md` も併せて参照すること。
