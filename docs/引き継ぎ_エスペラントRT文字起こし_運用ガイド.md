# 引き継ぎ書（エスペラント会話のリアルタイム文字起こし）

本書は、Google Meet/Zoom の会議音声を PC 内で取り込み、Speechmatics Realtime にストリーミングしてエスペラント語の文字起こしを行うための、セットアップ〜運用〜トラブルシュートまでを網羅した引き継ぎ資料です。後続の方が迷わず運用できるよう、実際に起きたエラーと対処も記載しています。

---

## 1. 現状と成果物（要約）

- リアルタイム文字起こしは稼働済み。
- 主要構成：音声入力(`sounddevice`) → ASR（Speechmatics メイン、Vosk/Whisper 切り替え可）→ パイプライン（ログ/Zoom/翻訳/Web UI/Discord）
- ログ: `logs/meet-session.log` に確定文を追記
- 翻訳: Web UI と Discord 投稿により多言語表示が可能（`TRANSLATION_TARGETS` に従う）

## 0. 最短クイックチェック（5分）

1) 仮想環境を作成して有効化（本ドキュメントでは `.venv311` を使用）:

```bash
python3.11 -m venv .venv311
source .venv311/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

2) 入力デバイスの確認:

```bash
python -m transcriber.cli --list-devices
```

3) `.env` を準備: リポジトリに同梱されているテンプレート `.env.example` をコピーして使用します（`cp .env.example .env`）。実値は絶対にコミットしないでください。

4) 設定例（最低限）:

```ini
SPEECHMATICS_API_KEY=<YOUR_KEY>
SPEECHMATICS_CONNECTION_URL=wss://<region>.rt.speechmatics.com/v2  # region base URL（例: eu2 / us2）。実際の接続は <base>/v2/<language> の形式になります（例: wss://eu2.rt.speechmatics.com/v2/eo）。
SPEECHMATICS_LANGUAGE=eo
AUDIO_DEVICE_INDEX=8
```

5) 設定確認と起動:

```bash
python -m transcriber.cli --show-config
python -m transcriber.cli --log-level=INFO
```

6) （翻訳を使う場合）`.env` に `WEB_UI_ENABLED=true`、`TRANSLATION_ENABLED=true`、`TRANSLATION_PROVIDER=google`、`TRANSLATION_TARGETS=ja,ko` を設定し、Google のサービスアカウント JSON を利用する場合は JSON をリポジトリに入れず、`GOOGLE_APPLICATION_CREDENTIALS` 環境変数などで参照することを推奨します。

---

## 3. セットアップ手順（初回）

1) Python 環境
- Python 3.11 を使う場合の仮想環境作成（本ドキュメントは `.venv311` を前提とします）
  ```bash
  python3.11 -m venv .venv311
  source .venv311/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
  ```

2) 音声ルーティング
- Linux では PipeWire/PulseAudio の loopback を利用し、Meet/Zoom の出力を仮想入力へルーティングします。`--list-devices` でデバイス名を確認し、`.env` の `AUDIO_DEVICE_INDEX` に設定してください。

補足
- Linux（PipeWire）：`pw-loopback` を使い、アプリ出力→ループバック→デフォルト入力を接続。

3) Speechmatics の準備
- Portal で Realtime が有効であることを確認し、**長期 API キー**を取得（キー文字列は rt- で始まらない場合もある）。
- **リージョン**を確認（EU/US）。本番では EU: `eu2` を使用。

4) `.env` を作成
```ini
TRANSCRIPTION_BACKEND=speechmatics
SPEECHMATICS_API_KEY=<長期APIキー>
SPEECHMATICS_CONNECTION_URL=wss://<region>.rt.speechmatics.com/v2  # region base URL（例: eu2 / us2）。実際の接続は <base>/v2/<language> の形式になります。
SPEECHMATICS_LANGUAGE=eo
AUDIO_DEVICE_INDEX=8        # 例: pipewire
ZOOM_CC_ENABLED=false       # Meet利用のため
TRANSCRIPT_LOG_ENABLED=true
TRANSCRIPT_LOG_PATH=logs/meet-session.log
```

- 翻訳を使う場合は `.env` に以下を追記。デフォルト言語はエスペラント（`TRANSLATION_SOURCE_LANGUAGE=eo`）。運用では Google Cloud Translation（サービスアカウント JSON）を使う想定。LibreTranslate を使う場合は `TRANSLATION_PROVIDER=libre` に切り替え、`LIBRETRANSLATE_URL`/APIキーを指定する。
  ```ini
  WEB_UI_ENABLED=true
  TRANSLATION_ENABLED=true
  TRANSLATION_PROVIDER=google
  TRANSLATION_TARGETS=ja,ko
  TRANSLATION_DEFAULT_VISIBILITY=ja:on,ko:off
  # Google service-account JSON: do NOT commit this file to the repository.
  # Prefer supplying credentials via the environment variable GOOGLE_APPLICATION_CREDENTIALS
  GOOGLE_TRANSLATE_CREDENTIALS_PATH=/absolute/path/to/service-account.json
  GOOGLE_TRANSLATE_MODEL=nmt
  # 任意: GOOGLE_TRANSLATE_API_KEY=<APIキーを使う場合>
  # 任意: LIBRETRANSLATE_API_KEY=<LibreTranslateを使う場合>
  DISCORD_WEBHOOK_ENABLED=true
  ```
Web UI を共有するだけで良い場合は Webhook を省略可能。Webhook を設定すると Discord 側に原文と翻訳をまとめたメッセージを数秒単位で投稿する。

### 3.1 GitHub からダウンロードしたユーザー向け（環境構築スクリプト）

オンライン（通常）
- 依存は `requirements.txt` に集約。以下のスクリプトで仮想環境の作成〜インストールまで自動化。
  ```bash
  git clone <このリポジトリ>
  cd <クローン先>
  scripts/bootstrap_env.sh          # .venv311 を作成し依存をインストール
  source .venv311/bin/activate      # 有効化
  cp .env.example .env && vi .env   # 設定（APIキー/リージョン/デバイス）
  ```

オフライン（事前に wheelhouse を同梱する配布形態）
- 配布側（ネット接続できる環境）で wheelhouse を作り、コードと併せて配布。
  ```bash
  scripts/bootstrap_env.sh              # まずは通常の環境で構築
  scripts/offline_prepare_wheels.sh     # ./wheelhouse に必要なホイールを収集
  # => リポジトリ一式 + wheelhouse/ を zip/tar でまとめて配布
  ```
- 利用側（ネット接続なし）
  ```bash
  tar xzf <配布物>.tar.gz
  cd <展開先>
  scripts/offline_install.sh            # wheelhouse から依存をインストール
  source .venv311/bin/activate
  cp .env.example .env && vi .env
  ```

## システム依存パッケージ（補足）

本プロジェクトは Python パッケージの他に PortAudio / libsndfile / ffmpeg 等の OS レベルの依存が必要です。代表的なコマンド例（Linux 向け）を示します。その他プラットフォーム向けのメモは `fuyou/PLATFORM_GUIDES.md` に移動しました。

Debian/Ubuntu の例:
```bash
sudo apt update
sudo apt install -y build-essential libsndfile1-dev libportaudio2 portaudio19-dev ffmpeg
```

また、Python パッケージをインストールする前に pip 等を最新化しておくことを推奨します:
```bash
python -m pip install --upgrade pip setuptools wheel
```

注意
- `.env` と `logs/` は `.gitignore` 済み（機微情報・不要ファイルをコミットしない）。

### 緊急手順: 秘密情報がリポジトリ内で発見された場合（簡易ガイド）

1. まずローカル作業コピーで該当ファイル（例: `*.json`, `.env` 等）を安全な場所へ退避し、リポジトリから削除する（新規コミットを作成して削除する）。
2. 直ちに当該キー/サービスのローテーション（鍵削除・再発行）を行う。Google サービスアカウントであればコンソールで鍵を削除してください。
3. 既にリモート（例: GitHub）へ公開されている場合はチームと連携し、履歴消去（`git-filter-repo` / BFG 等）や対応通知を検討する。履歴書き換えは注意が必要です。
4. 再発防止策として、`.gitignore` に該当パターン（`.env`, `*.json`, `gen-lang-client-*.json` 等）を追加し、Secret scanning や CI のチェックを導入することを推奨します。

(このドキュメントは手順の提示のみで、操作は行いません。実作業をこちらで行う場合は事前承認をお願いします。)

---

## 4. 実行手順

1) 設定確認
```bash
.venv311/bin/python -m transcriber.cli --show-config
```
`speechmatics.connection_url` と `audio.sample_rate=16000` を確認。

2) 起動（Speechmatics）
```bash
.venv311/bin/python -m transcriber.cli --backend=speechmatics --log-level=INFO
```
正常時:
- `Recognition started.` → `Final: ...` が出力され、`logs/meet-session.log` に追記されます。
- `WEB_UI_ENABLED=true` の場合は自動で `http://127.0.0.1:8765` が起動。ブラウザで開くと最新の確定文と翻訳（言語ごとにON/OFF可能なトグル）が表示されます。
- `DISCORD_WEBHOOK_ENABLED=true` の場合は Discord チャンネルに数秒単位で原文＋翻訳をまとめたメッセージが投稿されます（1件あたり最大約350文字で折り返し）。
- 翻訳 API の疎通確認（任意）:
  ```bash
  scripts/test_translation.py "Bonvenon al nia kunsido."
  ```
  `.env` の設定で LibreTranslate へ問い合わせ、各ターゲット言語の訳文を表示します。翻訳対象を指定していない、またはAPIが応答しない場合はその旨を知らせます。

Sanity テスト（任意）
- テスト用に「Ĉu vi aŭdis?」など短いフレーズを発話し、`Final:` 行がログへ追記されることを確認。

3) バックアップ起動（オフライン Vosk）
```bash
# 事前に .env に VOSK_MODEL_PATH を設定
.venv311/bin/python -m transcriber.cli --backend=vosk --log-file logs/offline.log
```

---

## 5. 実装のポイント（Speechmatics Realtime v2）

- 認証: **APIキー→短期JWTの自動取得**に対応
  - `transcriber/asr/speechmatics_backend.py` で管理プラットフォーム `https://mp.speechmatics.com/v1/api_keys?type=rt` に POST し、`key_value`（短期トークン）を取得。
  - 取得トークンは `Authorization: Bearer <JWT>` で WS に付与。
- 接続 URL: `wss://<region>.rt.speechmatics.com/v2` を base に設定し、`SPEECHMATICS_LANGUAGE` で言語（例: `eo`）を指定してください。実装は base URL に言語サフィックス（`/eo` 等）を付加して接続します。
- プロトコルメッセージ
  - StartRecognition を JSON で送信
  - `RecognitionStarted` を受けてから音声送信（非同期イベント待機）
  - 受信は `AddPartialTranscript` / `AddTranscript`（`metadata.transcript`）
- 互換対応
  - `enable_punctuation` はサーバ schema により拒否されたため送信しない（内部で自動句読点）
  - websockets v15 のヘッダーは `additional_headers` を使用
  - Pydantic の URL バリデーションは `wss` を許容するため `str` に変更

---

## 6. Google Meet/Zoom の使い分け

- Google Meet
  - 仮想オーディオ（例: pipewire）に会議音声を流し、`AUDIO_DEVICE_INDEX` で指定
  - Meet 画面への字幕重畳は本実装では未対応（必要なら Electron/OBS でオーバーレイを追加）
- Zoom
  - Zoom 画面内に字幕を出したい場合は、`ZOOM_CC_ENABLED=true` と `ZOOM_CC_POST_URL` を設定して起動
  - CC URL の取得（ホスト）：会議内 → 字幕（CC）を有効化 → 「サードパーティの字幕サービスを使用」→ 生成された URL をコピー → `.env` の `ZOOM_CC_POST_URL` に貼付（`seq` はプログラム側で自動付与）。
- Discord
  - 音声取得は Meet/Zoom と同じく仮想オーディオをループバック（VoiceMeeter/BlackHole/PipeWire 等）。
  - Web UI をブラウザで開き、Discord の画面共有（ウィンドウ/タブ）で参加者に共有するのが最も簡単。
  - `DISCORD_WEBHOOK_ENABLED=true` と `DISCORD_WEBHOOK_URL` を設定すると、最終行を数秒以内にまとめて投稿（バッチング）します。投稿には原文と、設定した翻訳（日本語/韓国語など）が含まれます。

### 6.1 翻訳表示・Discord 共有

- Web UI の翻訳トグル
  - `.env` の `TRANSLATION_TARGETS` を読み込み、起動直後からヘッダ右側に言語別トグル（例: 日本語・한국어）を表示します。初期状態は `TRANSLATION_DEFAULT_VISIBILITY` で制御可能（省略時は ON）。
  - トグルをOFFにすると、メイン画面（最新発話）と履歴の該当言語が同時に非表示になります。設定はブラウザに保存され、再読込時に復元されます。
  - ヘッダ下部に簡易ヘルプカードを追加。主要操作（トグル／フォント／履歴ボタン）を短くまとめているため、初見ユーザーへの案内に便利です。
- 表示レイアウト
  - 左カラムに最新発話（Esperanto＋翻訳）、右カラムに履歴を表示。履歴には最新行が上に追加され、最大500件でローテーションします。
  - ヘッダには「文字サイズ」「ダークテーマ」「途中経過表示」「履歴コピー／保存／クリア」ボタンがあり、操作結果は `localStorage` に保持されます。
  - 翻訳が取得できなかった場合は「翻訳待ち」のプレースホルダで明示し、遅延や失敗が一目で分かるようにしています。
- Discord Webhook
  - 2秒間隔で確定文を蓄積し、まとまった文章単位で投稿。長文や高速連続確定の場合でもチャンネルがスパム化しません。
  - 翻訳を有効化している場合は、`Esperanto:` に続けて各言語の翻訳を折り返しで表示。

---

## 7. 運用チェックリスト（Meet/Zoom/Discord 共通）

- Pre
  - 仮想オーディオの疎通確認（テスト音声→録音できるか）
  - `.env` を最新のキー/リージョン/デバイスに更新
  - 参加者・サーバ管理者へ字幕/録音の実施を事前告知
  - Discord Webhook を使う場合は投稿先チャンネル/権限を確認
  - 翻訳を使う場合は LibreTranslate 等のエンドポイント疎通・利用制限を事前にチェック（`curl https://libretranslate.de/languages` など）
- During
  - パイプライン起動後 `Recognition started.` を確認
  - Web UI を開いて画面共有（タブ共有やCompanionモードが安定）
  - 翻訳と Discord 投稿が期待通りに反映されているか（トグルのON/OFF含む）を確認
  - CPU/GPU/ネットの負荷、ログ（Final/Partial）が進行しているか監視
  - Zoom: CC が表示されているか参加者に確認
- Post
  - ログ（`logs/`）・Discord投稿（必要に応じて削除/まとめ）を整理
  - 誤認識単語を辞書・メモに追加して次回チューニング
  - Speechmatics/翻訳APIの利用量・コストを確認し、継続運用コストを見積もる

---

## 8. トラブルシュート（症状 → 原因 → 対処）

- `404 path not found`（JWT発行時）
  - 原因: 認可エンドポイントのパス違い
  - 対処: 管理プラットフォーム `https://mp.speechmatics.com/v1/api_keys?type=rt` で発行（実装済み）

- `1003 unsupported data`（WS 直後）
  - 原因: StartRecognition の schema 不一致、またはリージョンURL/言語サフィックス不足
  - 対処: StartRecognition 形式に統一、`/v2/<language>` を付与（実装済み）

- `401/403 Unauthorized`
  - 原因: APIキーがRealtime権限なし/無効
  - 対処: Portal で Realtime 有効化とキーの再取得。リージョン（eu2/us2）を確認

- `Speechmatics error: {... "enable_punctuation" is not allowed}`
  - 原因: サーバ schema と不一致
  - 対処: 送信パラメータから `enable_punctuation` を削除（実装済み）

- 音声が無音/誤ったデバイス
  - 原因: デバイス選択ミス
  - 対処: `--list-devices` で確認し `.env` の `AUDIO_DEVICE_INDEX` を修正

- `Recognition did not start in time.`（内部タイムアウト）
  - 原因: StartRecognition 後の `RecognitionStarted` が届かない
  - 対処: URL/リージョン/言語サフィックス、APIキーの権限、ネットワーク（企業プロキシ/ファイアウォール）を確認

- `429 Too Many Requests` / レート超過
  - 原因: 短時間の連続接続/切断
  - 対処: 5〜10秒の待機後に再試行。連続テスト時は間隔を空ける

- 翻訳が表示されない／`Translation to ja failed` ログ
  - 原因: Google Cloud Translation の認証エラー、サービスアカウント権限不足、ターゲット言語コードの入力ミス、LibreTranslate エンドポイント不通
  - 対処: `TRANSLATION_TARGETS` を確認。Google利用時は `GOOGLE_TRANSLATE_CREDENTIALS_PATH`（または API キー）と Cloud Translation API 権限・課金設定を確認。LibreTranslate を使う場合は `curl <LIBRETRANSLATE_URL>/languages` で疎通確認し、必要なら `LIBRETRANSLATE_API_KEY` を設定。

- TLS/プロキシ関連の失敗
  - 原因: 企業プロキシや TLS インスペクション
  - 対処: `HTTPS_PROXY`/`HTTP_PROXY` の設定、`eu2.rt.speechmatics.com` と `mp.speechmatics.com` への 443 通信許可

---

## 9. セキュリティと運用

- `.env` やログに機微情報を残さない
  - 本リポジトリは学習/再現容易性のため、伏せ字入りの `.env` を「追跡」しています（実値は空欄や `*`）。
  - 本番運用では `.env` を追跡しないことを推奨します（例: `.env.local` を使い `.gitignore` に追加）。
  - 実キーの貼付や共有は厳禁。必要に応じてキーのローテーションを行うこと。
- 参加者への通知
  - 録音・字幕の実施を事前に周知
- コスト/クォータ
  - Speechmatics Pro 従量: 例 `$0.24/時`（90分 ≒ $0.36 ≒ 約55円、為替次第）
 - ログ保全方針
   - `logs/` の保存期間・アクセス権・暗号化（必要に応じて）をチームポリシーで定義

---

## 10. 拡張計画（希望があれば対応）

- カスタム辞書登録 UI/設定の追加（固有名詞の誤認を削減）
- Meet 向け字幕オーバーレイ（Electron/OBS）
- Whisper バックエンドの最適化（GPU/Mシリーズで sub-sec 遅延）
- 自動リトライ・再接続の強化、メトリクス収集/監視
- 翻訳の高度化（用語集サポート/キャッシュ/バックアップ翻訳APIとの冗長化）

---

## 11. コマンド チートシート

```bash
# 仮想環境
source .venv311/bin/activate

# デバイス列挙
python -m transcriber.cli --list-devices

# 設定確認
python -m transcriber.cli --show-config

# 起動（Speechmatics）
python -m transcriber.cli --backend=speechmatics --log-level=INFO

# 起動（Vosk オフライン）
python -m transcriber.cli --backend=vosk --log-file logs/offline.log

# デバッグログ
python -m transcriber.cli --backend=speechmatics --log-level=DEBUG
```

### 11.1 Web UI 起動を安定化させるラッパースクリプト

`scripts/run_transcriber.sh` は Web UI の LISTEN ポート（既定 8765）を解放→CLI を起動するラッパーです。ブラウザや Chrome の Network Service が接続を握ったままでも LISTEN している古いプロセスだけを落とし、ポートが空くまで待機してから `python -m transcriber.cli` を実行します。

```bash
install -Dm755 scripts/run_transcriber.sh ~/bin/run-transcriber.sh
source .venv311/bin/activate
~/bin/run-transcriber.sh                # backend=speechmatics, PORT=8765
PORT=8766 ~/bin/run-transcriber.sh      # ポートを変える場合
```

ブラウザはログに表示される URL（例: `http://127.0.0.1:8765`）にアクセスすれば即座に翻訳付きの Web UI が開きます。

`python -m transcriber.cli` を手動で実行したい派は、事前に `scripts/prep_webui.sh` を叩いておくとポート掃除が一発で完了します。

```bash
install -Dm755 scripts/prep_webui.sh ~/bin/prep-webui.sh
source .venv311/bin/activate
~/bin/prep-webui.sh && python -m transcriber.cli --backend=speechmatics --log-level=INFO
```

`prep-webui.sh` は既存の CLI プロセスを終了し、8765 が LISTEN していない状態になるまで待ってからコマンドを返すので、続けて実行する `python -m ...` が必ず 8765 にバインドできます。

「8765 を完全に空にしたいときは、以下 3 行を続けて実行してください」。Chrome の Network Service などが掴んでいる場合でも強制的に開放します。

```bash
# Try graceful shutdown first; force-kill can have side-effects. Prefer SIGTERM before SIGKILL.
pkill -f "python -m transcriber.cli" || true
sleep 0.2
lsof -t -iTCP:8765 | xargs -r kill || true   # SIGTERM
sleep 0.5 && lsof -iTCP:8765 || true
# If the port remains held and you understand the risk, consider kill -9 only after consultation.
```

その後、必要に応じて通常どおり `python -m transcriber.cli ...` を再起動してください。

### 11.2 モニター入力の自動復旧（PipeWire/WirePlumber）

PipeWire が既定ソースを物理マイクに戻すと Speechmatics/Discord が無音化します。`scripts/wp-force-monitor.sh` と systemd ユニットで monitor を固定しておくと安心です。手順は `docs/audio_loopback.md` 参照。概要:

```bash
install -Dm755 scripts/wp-force-monitor.sh ~/bin/wp-force-monitor.sh
~/bin/wp-force-monitor.sh                  # 既定ソースを monitor に設定
cp systemd/wp-force-monitor.{service,path} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now wp-force-monitor.service wp-force-monitor.path
```

`SINK_NAME=... ~/bin/wp-force-monitor.sh` のように実行すると既定シンクも固定できます。WirePlumber が state ファイルを書き換えても数秒で monitor に戻るため、誤ってマイク入力に切り替わる事故を防げます。

---

## 付記: 変更履歴（主要な実装変更）

- WebSockets ヘッダ `extra_headers` → `additional_headers`（websockets 15系）
- Realtime エンドポイントを `wss://eu2.rt.speechmatics.com/v2` に更新
- Pydantic の `HttpUrl` 厳格チェックを緩和（`wss` 許容）
- ZoomCaptionConfig の URL 型を `str` に変更
- API キー → JWT 自動取得を実装（`mp.speechmatics.com/v1/api_keys?type=rt`）
- StartRecognition 形式に更新／`RecognitionStarted` 待機を追加
- `enable_punctuation` 送信を削除（schema 不一致回避）

以上。
