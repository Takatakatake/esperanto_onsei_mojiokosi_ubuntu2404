# Ubuntu 音声デバイス切り替え問題のトラブルシューティング

## 問題の説明

Ubuntuのシステム設定で音声出力デバイスを切り替えると、文字起こしアプリケーションが音声を受信できなくなる問題が発生することがあります。

事前チェックとして `python -m transcriber.cli --check-environment` を実行し依存関係と `.env` を確認し、続けて `python -m transcriber.cli --diagnose-audio` でルーティング状態を把握しておくと、トラブルシューティングが容易になります。

初めて利用する場合は リポジトリ直下の `./easy_start.sh`（または `python -m transcriber.cli --easy-start`）を実行すると、環境チェック → 音声診断 → 起動まで順に案内されます。

仮想デバイスが既定のまま残ってしまった場合は `bash scripts/reset_audio_defaults.sh` を実行し、元に戻したい出力／入力を番号で選び直してください。

## 実装された対策

このアプリケーションには以下の自動復旧機能が実装されています：

### 1. デバイス変更の自動検知
- デフォルト音声入力デバイスを2秒ごとに監視
- デバイス変更を検知したら自動的に再接続

### 2. ストリームヘルスチェック
- 5秒間音声データが受信されない場合、ストリームが停止していると判断
- 自動的にストリームを再起動
- 再起動に失敗した場合、別の利用可能なデバイスを試行

### 3. エラー自動復旧
- ストリームエラー発生時に自動的に再接続
- ロック機構により複数の再接続が同時実行されるのを防止

## 設定方法

### 監視間隔の調整

`.env`ファイルに以下を追加してデバイスチェック間隔を調整できます：

```bash
# デバイスチェック間隔（秒）
AUDIO_DEVICE_CHECK_INTERVAL=2.0
```

- デフォルト: 2.0秒
- 最小値: 0.5秒（より頻繁にチェック、CPU使用率が若干上がる）
- 最大値: 10.0秒（チェック頻度を下げる）

### ストリームタイムアウトの調整

ソースコード内のタイムアウト値を変更することも可能です（`transcriber/audio.py`の`_chunk_timeout`）。

## Ubuntu特有の対策

### PulseAudio/PipeWireの設定確認

1. **使用している音声システムの確認**
```bash
# PulseAudioの場合
pulseaudio --version

# PipeWireの場合
pipewire --version
```

2. **デフォルト入力デバイスの確認**
```bash
# PulseAudioの場合
pactl list sources short

# 現在のデフォルトを確認
pactl info | grep "Default Source"
```

3. **ループバックデバイスの設定（必要な場合）**

Zoom/Google Meetなどの音声をキャプチャする場合、PulseAudioのループバックモジュールが必要です：

```bash
# PulseAudioループバックモジュールをロード
pactl load-module module-loopback latency_msec=1

# または永続的に設定
echo "load-module module-loopback latency_msec=1" >> ~/.config/pulse/default.pa
```

### システム設定での対策

1. **音声設定を開く**
   - システム設定 → サウンド

2. **入力デバイスの固定**
   - 「入力」タブで使用するマイク/ループバックデバイスを選択
   - このデバイスを固定したい場合は、`.env`ファイルに以下を追加：

```bash
# 特定のデバイスインデックスを指定（デバイスリストで確認）
AUDIO_DEVICE_INDEX=8
# 物理マイクのみを使う場合:
# AUDIO_CAPTURE_MODE=microphone
```

3. **デバイスインデックスの確認方法**

Pythonで確認：
```bash
python3 -c "import sounddevice as sd; print(sd.query_devices())"
```

または、アプリケーション起動時のログを確認：
```bash
python3 -m transcriber.cli
# ログに "Starting audio stream on device: ..." が表示されます
```

## よくある問題と解決策

### 問題1: 出力デバイスを切り替えると音が鳴らなくなる

**原因**: 出力デバイスの切り替えにより、音声ルーティングが変更され、ループバックデバイスへの入力が停止する。

**解決策**:
1. ループバックモジュールを再起動：
```bash
pactl unload-module module-loopback
pactl load-module module-loopback latency_msec=1
```

2. アプリケーションは自動的にストリームを再接続します（5秒以内）

### 問題2: デバイス切り替え後、完全に音声が取得できない

**原因**: システムレベルで音声ルーティングが壊れている可能性。

**解決策**:
1. PulseAudioを再起動：
```bash
pulseaudio --kill
pulseaudio --start
```

2. または、システムの音声サービスを再起動：
```bash
systemctl --user restart pulseaudio.service
```

### 問題3: 頻繁に再接続が発生する

**原因**: デバイスが不安定、またはチェック間隔が短すぎる。

**解決策**:
1. チェック間隔を長くする：
```bash
AUDIO_DEVICE_CHECK_INTERVAL=5.0
```

2. 特定のデバイスを指定して固定：
```bash
AUDIO_DEVICE_INDEX=8
```

## ログの確認

アプリケーション実行時のログで以下のメッセージを確認できます：

```
# 正常な起動
Starting audio stream on device: Built-in Audio (index=10)
Audio stream started successfully

# デバイス変更検知
Default audio device changed from 10 to 15, reconnecting...
Starting audio stream on device: HDMI Audio (index=15)
Audio stream reconnected to new device

# ヘルスチェックによる自動復旧
Audio stream appears dead (no data for 5.0 seconds), attempting reconnect...
Audio stream reconnected after timeout
```

## パフォーマンスへの影響

この自動復旧機能による追加のリソース使用：

- **CPU**: ほぼ無視できるレベル（2秒ごとの軽量チェック）
- **メモリ**: 追加で数KB程度
- **レイテンシ**: 再接続時に最大2-3秒の音声途切れが発生する可能性

## 高度な設定

### 特定のデバイスのみを使用

複数の音声デバイスがある環境で、特定のデバイスだけを使用したい場合：

1. デバイス状態を診断：
```bash
python -m transcriber.cli --diagnose-audio
# もしくは従来通り一覧だけを確認する場合:
python -m transcriber.cli --list-devices
```

2. `.env`で指定：
```bash
AUDIO_DEVICE_INDEX=8  # 使用したいデバイスのインデックス
```

この設定を行うと、自動デバイス切り替えは無効になり、指定したデバイスに固定されます。

あわせて `AUDIO_DEVICE_SAMPLE_RATE` にハード実レート（例: 48000）を指定すると、内部で 16 kHz へ自動変換されます。`AUDIO_LEVEL_MONITOR_ENABLED=true` を有効化すると、無音状態やクリッピングが継続した際にログへ警告が記録され、ルーティングミスや過大入力を検知しやすくなります。

### PipeWireを使用している場合

Ubuntu 22.04以降ではPipeWireがデフォルトの場合があります：

```bash
# PipeWireの状態確認
systemctl --user status pipewire

# 必要に応じて再起動
systemctl --user restart pipewire pipewire-pulse
```

## まとめ

このアプリケーションは、Ubuntuの音声デバイス切り替え時の問題に対して以下の対策を提供します：

1. ✅ 自動デバイス変更検知と再接続
2. ✅ ストリームヘルスチェックと自動復旧
3. ✅ エラー時の自動リトライ
4. ✅ 詳細なログ出力

これらの機能により、ほとんどのケースで手動介入なしに音声キャプチャが継続されます。
