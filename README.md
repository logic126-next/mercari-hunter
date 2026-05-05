# Mercari Bargain Hunter

メルカリ上の「相場より明らかに安い商品」を自動検知・通知するサービス。

## 機能

- **キーワード登録** — データベースで管理（複数キーワード同時監視）
- **Mercari 検索** — キーワードごとに検索ページをクロールして商品データを取得
- **ページネーション対応** — `page_token` ベースの複数ページ巡回、`max_items` 上限付き（デフォルト 100 件）
- **最新順ソート** — `sort=created_time` で最新出品順に取得
- **属性抽出** — 商品名からブランド・型番・容量を regex で自動解析
- **相場判定** — ブランド+型番+容量でグループ化し中央値を計算（IQR 外れ値除去）
- **掘り出し物検知** — 5-level matching（exact → brand+model → brand → category → fallback）で相場的な安値を検出
- **防重複** — 同一商品は `ON CONFLICT DO UPDATE` で上書
- **Telegram 通知** — 掘り出し物を画像付きで即時通知
- **主ループ型定期実行** — 設定間隔でランダムウェイト付き自動巡回（80〜120秒程度）
- **動的キーワード管理** — DB 追加・削除・有効/無効でリアルタイム反映（リSTART不要）

## 仕組み

```
┌─────────────┐     ┌──────────────────┐     ┌──────────┐     ┌──────────┐
│   Main Loop  │────▶│  Crawler (multi- │────▶│ Extract  │────▶│ Notifier │
│ (random wait)│     │  page pagination)│   │(attribute)│    │(Telegram)│
└─────────────┘     └──────────────────┘     └──────────┘     └──────────┘
                         │                      │
                         ▼                      ▼
                    ┌──────────────┐        ┌──────────┐
                    │  PostgreSQL   │        │ Telegram  │
                    │  (items,      │        │ Bot API   │
                    │  market_      │        │           │
                    │  prices,      │        │           │
                    │  keywords)    │        │           │
                    └──────────────┘        └──────────┘
```

## 環境

- Python 3.11+（venv）
- PostgreSQL 15+
- Playwright（Chromium）
- Telegram Bot Token & Chat ID

## セットアップ

```bash
# 1. PostgreSQL にユーザーと DB を作成
sudo -u postgres psql -c "CREATE USER mercari WITH PASSWORD 'mercari';"
sudo -u postgres psql -c "CREATE DATABASE mercari OWNER mercari;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE mercari TO mercari;"

# 2. venv を作成して依存をインストール
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# 3. 環境変数を設定
cp .env.example .env
# .env に Telegram Bot Token / Chat ID を入力

# 4. キーワードをデータベースに追加
python3 main.py --add "Apple" "https://jp.mercari.com/search?brand_id=3272"
python3 main.py --add "SSD" "SSD"
python3 main.py --add "iPhone" "iPhone"
python3 main.py --add "ゲーミングPC" "ゲーミングPC"

# 5. （オプション）config.yaml を編集（閾値・通知・ページネーション等）
python3 main.py --test

# 6. 本番起動
tmux new -s mercari_hunter 'source .venv/bin/activate && python3 main.py'
```

## 使い方

| コマンド | 説明 |
|---------|------|
| `python3 main.py` | 本番モード（ランダムウェイト付きループ実行） |
| `python3 main.py --test` | 1回だけスキャンして終了（最初のキーワードのみ） |
| `python3 main.py --list` | 登録キーワード一覧表示 |
| `python3 main.py --add NAME TERM` | キーワード追加（TERM は検索語または URL） |
| `python3 main.py --remove NAME` | キーワード削除 |
| `python3 main.py --enable NAME` | キーワード有効化 |
| `python3 main.py --disable NAME` | キーワード無効化 |
| `tmux attach -t mercari_hunter` | 実行中のログを確認（`Ctrl+B` → `D` でデタッチ） |
| `tmux kill-session -t mercari_hunter` | 停止 |

## 運用管理

### サービス状態確認

| 操作 | コマンド |
|------|---------|
| 動作中か確認 | `tmux has-session -t mercari_hunter 2>&1 && echo "✅ 運行中" || echo "❌ 停止中"` |
| 最近のログを表示 | `tmux capture-pane -t mercari_hunter -p \| tail -10` |
| 実行中のプロセス確認 | `ps aux \| grep python \| grep -v grep` |
| ログファイル確認 | `tail -f logs/hunter.log` |

### サービス操作

| 操作 | コマンド |
|------|---------|
| 本番起動 | `tmux new -s mercari_hunter 'source .venv/bin/activate && python3 main.py'` |
| 実行ログを見る | `tmux attach -t mercari_hunter`（`Ctrl+B` → `D` でデタッチ） |
| 停止 | `tmux kill-session -t mercari_hunter` |
| 再起動 | 停止 → 起動（設定変更は次回スキャン時に自動反映） |

## キーワード管理

すべてのキーワードは PostgreSQL `keywords` テーブルで管理します。

### CLI 経由で管理

```bash
# 一覧
python3 main.py --list

# 追加（検索語または URL）
python3 main.py --add "Apple" "https://jp.mercari.com/search?brand_id=3272"
python3 main.py --add "SSD" "SSD"

# 削除
python3 main.py --remove "SSD"

# 有効/無効
python3 main.py --enable "SSD"
python3 main.py --disable "SSD"
```

### SQL 直接操作

```bash
# 一覧表示
psql -U mercari -d mercari -c "SELECT name, search_term, category, enabled, min_price, max_price FROM keywords;"

# 追加
psql -U mercari -d mercari -c \
  "INSERT INTO keywords (name, search_term, category) VALUES ('Nintendo Switch', 'Nintendo Switch', 'ゲーム')
   ON CONFLICT (name) DO UPDATE SET search_term = EXCLUDED.search_term, category = EXCLUDED.category;"

# 有効/無効
psql -U mercari -d mercari -c "UPDATE keywords SET enabled = false WHERE name = 'SSD';"
psql -U mercari -d mercari -c "UPDATE keywords SET enabled = true  WHERE name = 'SSD';"

# 削除
psql -U mercari -d mercari -c "DELETE FROM keywords WHERE name = 'Nintendo Switch';"
```

### キーワードテーブル構造

| カラム | 型 | 説明 | デフォルト |
|--------|------|------|-----------|
| `name` | TEXT | キーワード名（一意） | — |
| `search_term` | TEXT | 検索クエリ | — |
| `search_url` | TEXT | 検索 URL（オプション） | `""` |
| `min_price` | INT | 最低価格（円） | `0` |
| `max_price` | INT | 最高価格（円） | `0` |
| `category` | TEXT | 分類名 | `""` |
| `notify_on` | TEXT | 通知トリガー | `'["new","bargain"]'` |
| `enabled` | BOOL | 有効/無効 | `TRUE` |

## クローラー設定

- **ページネーション** — `page_token` 游标分页，自动翻页直到 `max_items` 上限或无新商品
- **デフォルト max_items** — 100 件/キーワード/スキャン（config.yaml `crawler.max_items` で調整）
- **ソート** — 常に `sort=created_time`（最新出品順）
- **ビューポート** — 固定 1920×1080
- **反検知** — UA 固定、webdriver フラグ削除、stealth init script、人間のようなスクロール

## 設定（config.yaml）

| セクション | 説明 |
|-----------|------|
| `crawler` | スクレイピング設定（`max_items`, `max_retries`, `timeout`, `wait_min`, `wait_max`） |
| `market_price` | 相場判定閾値（`lookback_days`, `threshold_ratio`, `absolute_threshold_yen`） |
| `filtering` | フィルター（許可状態、除外キーワード） |
| `notification` | 通知チャネル設定（Telegram Bot Token / Chat ID） |
| `warmup` | ウォームアップ回数（通知 OFF でデータ収集） |
| `database` | PostgreSQL 接続情報 |

設定変更は次回スキャン時に自動的に反映されます（リSTART不要）。

## プロジェクト構造

```
mercari-hunter/
├── main.py              # エントリポイント・主ループ
├── config.yaml          # 設定ファイル
├── .env                 # シークレット（git 除外）
├── .env.example
├── docker-compose.yml   # Docker デプロイ用
├── src/
│   ├── crawler.py       # Playwright スクレイパー（ページネーション対応）
│   ├── extractor.py     # 属性抽出（ブランド・型番・容量）
│   ├── filter_engine.py # フィルター（状態・禁止ワード）
│   ├── market_price.py  # 相場計算（中央値・IQR 外れ値除去）
│   ├── models.py        # PostgreSQL ORM（items, market_prices, keywords）
│   ├── normalizer.py    # 商品名正規化
│   └── notifier.py      # Telegram 通知
├── logs/
│   └── hunter.log       # 実行ログ
└── tests/
```

## データベーススキーマ

| テーブル | 説明 |
|---|---|
| `keywords` | 検索キーワード（動的管理） |
| `items` | クロールした全商品（`mercari_id`, `name`, `price`, `brand`, `model`, `capacity`, `attributes`, `last_notified_price` 等 19 カラム） |
| `market_prices` | 属性ごとの相場データ（`item_name`, `brand`, `model`, `price_median`, `price_mean`, `sample_count`） |

## 注意

- Mercari の HTML 構造が変更された場合は `crawler.py` のセレクタを更新する必要があります
- 適度なアクセス間隔を守ってください（`wait_min` / `wait_max` で調整）
- 大量のキーワードを監視する場合はウェイト間隔を広げてください
- **ページネーション** — 各キーワードごとに最大 `max_items` 件まで複数ページ巡回（デフォルト 100 件）
- **掘り出し物検知** — 価格が相場中央値の `threshold_ratio`（デフォルト 0.7 倍）以下 **かつ** `absolute_threshold_yen`（デフォルト 10,000 円）以上の差がある場合

## Mac mini へのデプロイ

Mac mini で常時稼働させる場合の手順です。

### 前提条件

- macOS 13+（Intel / Apple Silicon 両対応）
- Homebrew がインストール済み
- SSH でログインできる（またはローカルから直接操作）

### インストール手順

```bash
# 1. 依存パッケージのインストール
brew install python@3.12 postgresql@15

# 2. PostgreSQL を起動
brew services start postgresql@15

# 3. ユーザーと DB を作成
createuser -s $(whoami)
createdb mercari
```

```bash
# 4. リポジトリをクローンして依存をインストール
git clone <repo-url> mercari-hunter
cd mercari-hunter
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

```bash
# 5. 環境変数・キーワード設定
cp .env.example .env
# .env に Telegram Bot Token / Chat ID を入力
python3 main.py --add "Apple" "https://jp.mercari.com/search?brand_id=3272"
python3 main.py --add "SSD" "SSD"
python3 main.py --add "iPhone" "iPhone"
python3 main.py --add "ゲーミングPC" "ゲーミングPC"

# 6. テスト実行
python3 main.py --test
```

### launchd での常時稼働

macOS は systemd ではなく launchd を使用します。plist ファイルを作成：

```bash
mkdir -p ~/Library/LaunchAgents
```

`~/Library/LaunchAgents/com.mercari.hunter.plist` を作成：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.mercari.hunter</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/$(whoami)/workspace/mercari-hunter/.venv/bin/python3</string>
        <string>/Users/$(whoami)/workspace/mercari-hunter/main.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/$(whoami)/workspace/mercari-hunter</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/mercari_hunter.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/mercari_hunter_err.log</string>
</dict>
</plist>
```

```bash
# launchd に登録・起動
launchctl load ~/Library/LaunchAgents/com.mercari.hunter.plist

# 動作確認
launchctl list | grep mercari

# ログ確認
tail -f /tmp/mercari_hunter.log

# 停止
launchctl stop com.mercari.hunter

# 再起動
launchctl stop com.mercari.hunter && launchctl start com.mercari.hunter

# 登録解除
launchctl unload ~/Library/LaunchAgents/com.mercari.hunter.plist
```

> **注意**: plist の `$(whoami)` は展開しないでそのまま記述。コピー後 `sed` で置換してください：
> ```bash
> sed -i '' "s/\$(whoami)/$(whoami)/g" ~/Library/LaunchAgents/com.mercari.hunter.plist
> ```

### Docker Compose でのデプロイ（推奨）

`docker-compose.yml` が含まれている場合は、よりクリーンなデプロイが可能です：

```bash
docker compose up -d
```

詳細は `docker-compose.yml` を参照してください。

## ライセンス

MIT
