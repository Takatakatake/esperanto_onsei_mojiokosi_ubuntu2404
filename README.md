# エスペラント リアルタイム文字起こし

English version: see `README_en.md`

Zoom や Google Meet でのエスペラント会話を、低遅延でリアルタイム文字起こしするためのパイプライン実装です。
本リポジトリの設計は「エスペラント（Esperanto）会話を“常時・高精度・低遅延”に文字起こしするための実現案1.md」に基づいています。

- Speechmatics Realtime STT（エスペラント `eo` 対応、話者分離）
- Vosk オフラインバックエンド（ゼロコスト/隔離環境のバックアップ）
- Zoom Closed Caption API への送出（Zoom 画面にネイティブ字幕を表示）
- Whisper/Google STT 等の追加エンジンにも拡張しやすいパイプライン設計
- ブラウザ表示の字幕ボード（日本語/韓国語などへの翻訳表示、Discord 連携のバッチ投稿対応）

注意:
- Speechmatics と Zoom の各 API には有効な資格情報と会議側の権限が必要です。
- プライバシー/プラットフォームポリシー順守のため、参加者には文字起こし実施を必ず周知してください。

---

## 前提条件（Prerequisites）

 - Python 3.10 以上（CPython 3.10/3.11 で検証）
- Python 3.11 の仮想環境を `.venv311` という名前で作成して利用してください。
- 会議アプリの音声を PC 内へループバックする仕組み（PipeWire/PulseAudio/JACK など）
- Speechmatics アカウント（Realtime の利用権限と API キー）
- Zoom で CC（字幕）URL を取得できるホスト権限（または Recall.ai/Meeting SDK 等でメディア取得）

任意:
- Whisper バックエンドを使う場合は GPU か高性能 CPU（例: RTX 4070+ または Apple M2 Pro+）
- Google Meet Media API（プレビュー）による直接キャプチャが利用可能なら設定
- 完全オフライン運用向けに Vosk Esperanto モデル（`vosk-model-small-eo-0.42` 以上）

---

## 日本語クイックスタート（GitHub から）

```bash
git clone git@github.com:Takatakatake/esperanto_onsei_mojiokosi.git
cd esperanto_onsei_mojiokosi
python3.11 -m venv .venv311
source .venv311/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
# リポジトリには伏せ字入りのテンプレート `.env.example` を同梱しています（安全な雛形）。
# 実運用では `cp .env.example .env` のうえで実値を設定してください。実値を含む `.env` は絶対にコミットしないでください（`.gitignore` に追加することを推奨します）。
# 既に `.env` がある場合は開いて値を置き換えてください
# 無い場合は例からコピーして編集:
test -f .env || cp .env.example .env
```

### 超かんたん実行（初めての方向け）

- **Linux**: ターミナルで `./easy_start.sh` または `bash scripts/easy_start.sh` を実行。必要なら `chmod +x easy_start.sh` で実行権限を付与してください。
- マイク／スピーカーが仮想デバイスのまま残った場合は `bash scripts/reset_audio_defaults.sh` を実行すれば元に戻せます（候補を番号で選ぶだけです）。

※ 各スクリプトは `.venv311` があれば自動で有効化し、`python -m transcriber.cli --easy-start` を呼び出します。対話型の質問に従うだけでセットアップできます。

`.env` の主な編集ポイント（例）:

```ini
SPEECHMATICS_API_KEY=****************************   # 本物のキーに置換
SPEECHMATICS_CONNECTION_URL=wss://<region>.rt.speechmatics.com/v2   # region base URL の形式。例: eu2 または us2
SPEECHMATICS_LANGUAGE=eo                                     # 言語コード（例: eo）。実際の接続先は <base>/v2/<language> の形式になります（例: wss://eu2.rt.speechmatics.com/v2/eo）。
AUDIO_DEVICE_INDEX=8                               # --list-devices の番号
AUDIO_DEVICE_SAMPLE_RATE=48000                     # ハードウェア側の実レート（例: 48000/44100）
AUDIO_CAPTURE_MODE=loopback                        # loopback / microphone / api / auto
AUDIO_AUTO_SETUP_LOOPBACK=true                     # サポートされる OS では仮想ループバックを自動設定
WEB_UI_ENABLED=true
TRANSLATION_ENABLED=true
TRANSLATION_TARGETS=ja,ko
```

デバイス確認と起動:

```bash
python -m transcriber.cli --list-devices
python -m transcriber.cli --diagnose-audio
python -m transcriber.cli --log-level=INFO
```

Web UI は `http://127.0.0.1:8765` で開けます（`.env` の `WEB_UI_OPEN_BROWSER=true` で自動起動）。
`--diagnose-audio` は現在の OS・ループバック候補・設定ミスをまとめて表示します。
Linux では `scripts/setup_audio_loopback_linux.sh` で仮想デバイスを整備できます。

---

## セットアップ（Bootstrap）

```bash
cd /path/to/esperanto_onsei_mojiokosi
python3.11 -m venv .venv311
source .venv311/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
# `.env` はテンプレート `.env.example` を同梱しています。実運用では `cp .env.example .env` の上で実値を設定してください。
test -f .env || cp .env.example .env
```

`.env` を編集（サンプルの伏せ字を実値に置換）:

```ini
TRANSCRIPTION_BACKEND=speechmatics  # or vosk / whisper
SPEECHMATICS_API_KEY=sk_live_************************
SPEECHMATICS_APP_ID=realtime
SPEECHMATICS_LANGUAGE=eo
ZOOM_CC_POST_URL=https://wmcc.zoom.us/closedcaption?...  # ホストが提供する URL
```

任意設定（デフォルトのままでも可）:

```ini
AUDIO_DEVICE_INDEX=8            # --list-devices の番号
AUDIO_SAMPLE_RATE=16000
AUDIO_DEVICE_SAMPLE_RATE=48000
AUDIO_CHUNK_DURATION_SECONDS=0.5
AUDIO_CAPTURE_MODE=loopback
AUDIO_AUTO_SETUP_LOOPBACK=true
# AUDIO_LINUX_LOOPBACK_SINK=alsa_output.pci-0000_00_1f.3.analog-stereo
AUDIO_LEVEL_MONITOR_ENABLED=false
AUDIO_LEVEL_SILENCE_THRESHOLD_DBFS=-45.0
AUDIO_LEVEL_SILENCE_DURATION_SECONDS=6.0
AUDIO_LEVEL_CLIP_THRESHOLD_DBFS=-1.0
AUDIO_LEVEL_CLIP_HOLD_SECONDS=2.0
ZOOM_CC_MIN_POST_INTERVAL_SECONDS=1.0
VOSK_MODEL_PATH=/absolute/path/to/vosk-model-small-eo-0.42
WHISPER_MODEL_SIZE=medium
WHISPER_DEVICE=auto              # cuda / cpu / mps
WHISPER_COMPUTE_TYPE=default     # 例: float16（GPU）
WHISPER_SEGMENT_DURATION=6.0
WHISPER_BEAM_SIZE=1
TRANSCRIPT_LOG_PATH=logs/esperanto-caption.log
WEB_UI_ENABLED=true
TRANSLATION_ENABLED=true
TRANSLATION_PROVIDER=google
TRANSLATION_SOURCE_LANGUAGE=eo
TRANSLATION_TARGETS=ja,ko
TRANSLATION_TIMEOUT_SECONDS=8.0
TRANSLATION_DEFAULT_VISIBILITY=ja:on,ko:off
# Google Cloud Translation service account JSON (do NOT commit to repo).
# Instead prefer setting the file path in the environment variable
# `GOOGLE_APPLICATION_CREDENTIALS` or keep the JSON outside the repository and reference it via an absolute path.
GOOGLE_TRANSLATE_CREDENTIALS_PATH=/absolute/path/to/gen-lang-client-xxxx.json
GOOGLE_TRANSLATE_MODEL=nmt
# API キー派生を使う場合は GOOGLE_TRANSLATE_API_KEY=...
DISCORD_WEBHOOK_ENABLED=true
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
DISCORD_BATCH_FLUSH_INTERVAL=2.0
DISCORD_BATCH_MAX_CHARS=350
```

---

## 使い方（Usage）

- 入力デバイスの一覧とルーティング確認:
  ```bash
  python -m transcriber.cli --list-devices
  ```

- パイプライン起動（確定文を標準出力へ、Zoom に確定文を送出）:
  ```bash
  python -m transcriber.cli --log-level=INFO
  ```

- `WEB_UI_ENABLED=true` のとき、簡易字幕ボードが `http://127.0.0.1:8765` で起動します。最新発話（左カラム）と履歴（右カラム）が同時に確認でき、翻訳トグル・フォントサイズ・テーマ設定が保存されるようになりました。
- 翻訳トグルは `.env` の `TRANSLATION_TARGETS` と `TRANSLATION_DEFAULT_VISIBILITY` に基づいて初期表示されます。履歴のコピー／保存／クリアボタンもヘッダに用意しています。

### Web UI 操作ガイド

- 画面上部のヘルプカードに主要な操作が記載されています。
- 「Partial」をオンにすると途中経過の字幕が表示され、オフで確定文のみになります。
- フォントサイズスライダーとダークテーマ切替はブラウザに保存され、次回以降も継続されます。
- 翻訳トグルは言語ごとに ON/OFF を切り替え可能です（設定はブラウザに保存）。翻訳ターゲットは `.env` の `TRANSLATION_TARGETS` で追加・削除できます。
- 右カラムの履歴には最新行から順に追加され、上部の「履歴をコピー／保存／クリア」ボタンでそのまま共有・リセットできます。
- Discord Webhook を設定すると、確定文を自然な文単位でまとめ、エスペラント原文と各翻訳を 1 つのメッセージにして投稿します。

- バックエンドやログ出力の一時変更:
  ```bash
  python -m transcriber.cli --backend=vosk --log-file=logs/offline.log
  python -m transcriber.cli --backend=whisper --log-level=DEBUG
  ```

- 翻訳スモークテスト（現在の `.env` を使用）:
  ```bash
  scripts/test_translation.py "Bonvenon al nia kunsido."
  ```

### 音声入力のチューニング

- `AUDIO_DEVICE_SAMPLE_RATE` にハードウェア実レート（例: 48000 Hz）を設定すると、内部で 16 kHz へ自動リサンプリングして Speechmatics/Vosk/Whisper の精度を安定させます。デバイスが 44.1 kHz 固定でもそのまま利用可能です。
- `AUDIO_CHUNK_DURATION_SECONDS` は 0.1〜0.5 秒が推奨です。細かくするほど低遅延になりますが、CPU 負荷とネットワーク帯域が増えます。
- `AUDIO_LEVEL_MONITOR_ENABLED=true` で入力レベル監視を有効化すると、一定時間無音（デフォルト -45 dBFS 以下が 6 秒）やクリッピングに達した場合に警告ログを出力します。閾値や検知時間は対応する `.env` 変数で微調整できます。
- Linux で自動ループバックを有効にした場合、パイプライン終了時に既定の入出力デバイスを元に戻します。長時間の録音後でもシステムのサウンド設定が汚れません。

### Linux クイックガイド

- **Linux (PipeWire/PulseAudio)**: `scripts/setup_audio_loopback_linux.sh` が `module-null-sink` を作成し、Monitor を既定入力に切り替えます。`run_transcriber.sh` や `python -m transcriber.cli --easy-start` から呼び出した場合は CLI 側で既定デバイスをスナップショットし、終了時に自動復元します。スクリプト単体で実行した場合は `scripts/reset_audio_defaults.sh` などで明示的に戻してください。`python -m transcriber.cli --diagnose-audio` で `pipewire` や `default` が候補に出るか確認してください。
- 共通: まず `python -m transcriber.cli --check-environment` で依存関係・.env・認証ファイルをチェックし、続けて `--diagnose-audio` でルーティングを確認するとスムーズです。
- ガイド付きセットアップを見たい場合は `python -m transcriber.cli --setup-wizard` を実行すると、必須ステップと推奨ツールが一覧で表示されます。
- マイクやスピーカーを即座に復旧したいときは `scripts/reset_audio_defaults.sh` を実行してください。

-停止は `Ctrl+C`。`Ctrl+Z`（ジョブの一時停止）は安全のため自動的に「終了リクエスト」に読み替えられ、ループバック設定を元に戻して停止します。旧バージョンを利用していて `Ctrl+Z` で停止してしまった場合は `fg` → `Ctrl+C` で再開・終了してください。
-ログには以下が出ます:
- `Final:` 行（Speechmatics が確定セグメントを出したタイミング）
- Zoom への POST 成否（401/403 はトークン期限切れや会議未準備の可能性）
- Transcript ログを有効化している場合は、確定ごとにタイムスタンプ付きで追記

Zoom 固有の手順:
1. ホストが会議で Live Transcription を許可し、Closed Caption API URL を取得
2. その URL を `.env` の `ZOOM_CC_POST_URL` に貼り付けるか、`export ZOOM_CC_POST_URL=...` で起動時に設定
3. 参加者が Zoom UI で字幕を有効化（通常のネットワークで E2E 約 1 秒）

Google Meet の選択肢:
- Meet Media API（プレビュー）が使える場合は、そのストリームを PCM に変換して同じ Speechmatics クライアントに供給
- 現状は OS の仮想ループバック（PipeWire/PulseAudio/JACK 等）で安定運用可能

---

## アーキテクチャ概要

- `transcriber/audio.py`: 16 kHz モノラルの PCM16 を非同期で取得
- `transcriber/asr/speechmatics_backend.py`: Realtime WebSocket クライアント（Bearer JWT、部分/確定を JSON 受信）
- `transcriber/asr/whisper_backend.py`: faster-whisper によるストリーミング認識（GPU/Mシリーズ向け）
- `transcriber/asr/vosk_backend.py`: Vosk/Kaldi ベースの軽量オフライン認識
- `transcriber/pipeline.py`: 入力→ASR→ログ/Zoom/翻訳/Web UI/Discord をオーケストレーション
- `transcriber/zoom_caption.py`: Zoom Closed Caption API へ `text/plain` をスロットリング送出（`seq` 付与）
- `transcriber/translate/service.py`: 非同期翻訳クライアント（LibreTranslate 互換）。Web UI/Discord の多言語出力に利用
- `transcriber/discord/batcher.py`: Discord への投稿をデバウンス/集約して自然な文単位に整形
- `transcriber/cli.py`: デバイス列挙、設定表示、バックエンド切替、グレースフルシャットダウン

拡張予定:
- Whisper ストリーミング、Google STT などの追加バックエンド
- 後処理（エスペラントのダイアクリティカル、句読点の整形）
- 画面表示/翻訳/永続化のためのオブザーバーフック

---

## 検証と次のステップ（Validation）

1. Speechmatics のハンドシェイクを検証（`start` ペイロードが最新スキーマに一致すること）。現状のビルドではカスタム辞書や `operating_point` パラメータ送信には対応していないため、必要な場合は `speechmatics_backend.py` の開始メッセージを拡張してください
2. 録音済みのエスペラント音声でドライリハーサル（WER、話者分離、遅延を測定）
3. 頻出語や固有名詞を Speechmatics の Custom Dictionary に登録。Vosk の後処理にも同語彙を反映
4. オフライン経路を検証（Vosk モデルを用意して `--backend=vosk` で比較）
5. Whisper バックエンドのベンチマークを実施し、ハードウェアごとに `WHISPER_SEGMENT_DURATION` を調整
6. 運用規模拡大時は systemd/pm2 等で常駐化し、永続ログ/メトリクスを整備
7. 参加者同意のワークフローを明文化し、招待メール等で「文字起こし有効」を自動周知
8. 翻訳パイプラインの E2E テスト（`TRANSLATION_TARGETS=ja,ko`、Google Cloud Translation または LibreTranslate の応答確認、Web UI/Discord に二言語が出ることを確認）。
   - Google Cloud Translation を使う場合は `TRANSLATION_PROVIDER=google`、`GOOGLE_TRANSLATE_CREDENTIALS_PATH=/path/to/service-account.json` または `GOOGLE_TRANSLATE_API_KEY` を設定。必要なら `GOOGLE_TRANSLATE_MODEL=nmt` を指定。サービスアカウントに Cloud Translation API 権限が必要です。

補足: Recall.ai/Meet Media API/Whisper 代替経路などは、`audio.py` と `transcriber/asr/` の抽象を再利用することで、制御ロジックを変えずに差し替え可能です。

---

## 推奨起動ワークフロー（固定ポート 8765）

Web UI を常に `8765` で起動し「ポート占有」問題を避けるためのランチャーを同梱:

```bash
install -Dm755 scripts/run_transcriber.sh ~/bin/run-transcriber.sh
source /path/to/.venv311/bin/activate
~/bin/run-transcriber.sh              # backend=speechmatics, log-level=INFO
```

`run_transcriber.sh` は選択ポート（既定 8765）の LISTEN を掃除してから `python -m transcriber.cli` を起動します。ブラウザは常に `http://127.0.0.1:8765` に接続でき、翻訳（Google: ja/ko）もすぐ表示されます。

別ポートや別バックエンドを使う例:

```bash
PORT=8766 LOG_LEVEL=DEBUG BACKEND=whisper ~/bin/run-transcriber.sh
```

手動で `python -m transcriber.cli` を叩きたい場合は、1 回だけ準備スクリプトを使うと安定:

```bash
install -Dm755 scripts/prep_webui.sh ~/bin/prep-webui.sh
source /path/to/.venv311/bin/activate
~/bin/prep-webui.sh && python -m transcriber.cli --backend=speechmatics --log-level=INFO
```

`prep-webui.sh` は 8765 の LISTEN を確実に解放してからコマンドを返すため、直後の `python -m ...` が一発でバインドできます。

どうしても 8765 が開放されない場合は、以下の 3 行で強制的にリセット可能です（Chrome の Network Service などが掴んでいる場合も含む）。

```bash
# まずは穏やかにプロセスを終了する方法を試してください（強制終了は副作用があるため注意）。
pkill -f "python -m transcriber.cli" || true
sleep 0.2
# SIGTERM を送って穏やかに終了させます（プロセスが応答しない場合のみ次の手段を検討）。
lsof -t -iTCP:8765 | xargs -r kill || true
sleep 0.5 && lsof -iTCP:8765 || true
# どうしても解放されない場合のみ、管理者と相談のうえで強制終了（kill -9）を検討してください。なお、`kill -9` はプロセスにクリーンな終了処理をさせないため、一時ファイルやソケットの残存、リソースリークを招く可能性があります。まずは SIGTERM（普通の kill）での終了を試みてください。
```

その後、通常どおり `python -m transcriber.cli ...` を再起動してください。

---

## ループバック安定性（PipeWire/WirePlumber）

PipeWire/WirePlumber が既定入力を物理マイクに戻してしまうと、Meet ループバックが無音になります。既定を固定し、状態ファイル変更にも自動復旧するには `docs/audio_loopback.md` を参照:

```bash
install -Dm755 scripts/wp-force-monitor.sh ~/bin/wp-force-monitor.sh
~/bin/wp-force-monitor.sh                           # 初回: アナログ monitor を強制
cp systemd/wp-force-monitor.{service,path} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now wp-force-monitor.service wp-force-monitor.path
```

`wp-force-monitor` は既定ソースを `alsa_output...analog-stereo.monitor` に固定します（Discord/Speechmatics が常に Meet ループバックを聴ける）。`SINK_NAME=...` を渡さない限り既定シンクはユーザー操作で可変です。

---

## オーディオデバイスのホットリロード（Ubuntu/Linux）

OS 側のデバイス切替でパイプラインが中断されないよう、デバイス変更の自動検知・再接続を実装しています。

### 特徴
- 自動監視: 既定入力デバイスを 2 秒ごとにチェック（調整可能）
- シームレス再接続: 切替検知時に自動的に新デバイスへ再接続
- ヘルスチェック: 音声ストリームが無音/停止したら 5 秒で検知しリスタート
- エラー回復: 例外発生時もリトライで自動復旧

### 設定
`.env` に以下を追加して監視間隔を変更:
```ini
AUDIO_DEVICE_CHECK_INTERVAL=2.0  # デフォルト 2.0 秒
```

### 診断
すべてのデバイスを確認する診断ツール:
```bash
python3 scripts/diagnose_audio.py
```
表示内容:
- 利用可能な入出力デバイス一覧
- 現在の既定デバイス
- 設定に使うデバイス番号
- ループバック構成の推奨

### よくある問題（Ubuntu/PulseAudio）
- 問題: システム設定で出力デバイスを切り替えると無音になる
  - 原因: PulseAudio/PipeWire のルーティングに影響
  - 解決: 2〜5 秒で自動再接続。恒久化したい場合は以下を追加:
    ```bash
    pactl load-module module-loopback latency_msec=1
    ```
- 問題: 再接続が頻発する
  - 解決: 監視間隔を延ばす／特定デバイスを固定
    ```ini
    AUDIO_DEVICE_CHECK_INTERVAL=5.0
    # diagnose_audio.py の結果を見てデバイス固定
    AUDIO_DEVICE_INDEX=8
    ```

詳細は `docs/ubuntu_audio_troubleshooting.md` を参照してください。

---

## システム依存パッケージ（補足）

このプロジェクトは Python パッケージだけでなく、OS レベルの依存（PortAudio、libsndfile、ffmpeg 等）を必要とします。代表的なインストール例を示します（ご利用のディストリビューション/環境に合わせて調整してください）。

- Debian/Ubuntu 系（参考）:
```bash
sudo apt update
sudo apt install -y build-essential libsndfile1-dev libportaudio2 portaudio19-dev ffmpeg
```


また、インストール前に Python のインストーラ周りを最新化しておくとトラブルが少ないため、以下を実行することを推奨します:
```bash
python -m pip install --upgrade pip setuptools wheel
```


---

## 付録 A: ポート 8765 を完全解放する 3 行

Chrome の Network Service 等が掴んでいても確実に 8765 を空にします:
```bash
pkill -f "python -m transcriber.cli" || true
sleep 0.2
# try graceful termination first
lsof -t -iTCP:8765 | xargs -r kill || true
sleep 0.5 && lsof -iTCP:8765    # 何も出なければOK
```
実行後、通常どおり `python -m transcriber.cli ...` を再起動してください。

---

## 付録 B: セキュリティと .env の取り扱い

- 本リポジトリには学習/再現容易性のため、伏せ字入りの `.env` を「追跡」しています（実値は空欄や `*`）。
- 本番運用では `.env` を追跡しない構成を推奨します（例: `.env.local` を使用し `.gitignore` に追加）。
- 実キーはコミット/共有しないでください。必要に応じて定期的なキーのローテーションを行ってください。

### 緊急手順: 秘密情報がリポジトリ内で発見された場合（簡易ガイド）

1. ローカルで該当ファイル（例: `*.json`, `.env` 等）を速やかに退避し、リポジトリから削除してコミットします（例: `git rm --cached` 等で履歴に残さないコミットを行う）。
2. 直ちに対象キー/資格情報をローテーション（無効化・再発行）してください。Google サービスアカウント鍵であれば Cloud Console で鍵を削除してください。
3. 既にリモートへ公開されている場合はチームで対応方針を決め、必要であれば履歴の抹消（`git-filter-repo` / BFG など）を検討してください。履歴書き換えはチーム合意の上で実施してください。
4. 再発防止策として、`.gitignore` に該当パターン（`.env`, `*.json`, `gen-lang-client-*.json` 等）を追加し、Secret scanning や CI による検出ルールを導入することを推奨します。

（注）上記はドキュメント上の簡易手順です。実作業をこちらで行う場合は事前に承認をお願いします。

---

日本語版 README は継続的に更新します。英語版（`README_en.md`）の差分が出た場合は、本ファイルへの反映をご連絡ください。
