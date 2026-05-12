# Mercari Hunter

Mercari 商品の爬取・相場分析・キーワード通知システム。

## 概要

Mercari.jp を定期的にクロールし、キーワードに一致する掘り出し物商品を検出・記録する。
商品の価格推移を分析し、相場価格と比較して通知を送信する。

## アーキテクチャ

```
┌─────────────────────┐
│    Mercari.jp       │
└─────────┬───────────┘
          │ Playwright (headless)
          ▼
┌─────────────────────────────┐
│   main.py (クローラー)      │
│   - 定期クロール             │
│   - Telegram 通知            │
│   - キーワード管理           │
│   - 相場分析                 │
└─────────┬───────────────────┘
          │ PostgreSQL
          ▼
┌─────────────────────────────┐
│   app/api_server.py          │
│   (Dashboard API, port 8501)│
└─────────┬───────────────────┘
          │
          ▼
┌─────────────────────────────┐
│   templates/dashboard.html   │
│   (Web Dashboard UI)        │
└─────────────────────────────┘
```

## データベース

PostgreSQL `mercari` データベースを使用。

### テーブル

| テーブル | 説明 |
|---------|------|
| `items` | 爬取した商品情報（Mercari ID, 名前, 価格, 状態, 販売者, カテゴリ, 画像URL） |
| `keywords` | 監視キーワード（検索語, 価格帯, 除外語, 通知設定） |
| `price_history` | 商品価格履歴 |
| `market_analysis` | 相場分析結果（カテゴリ別平均価格・中央値・分散） |

## 起動方法

### クローラー (main.py)

```bash
cd ~/workspace/mercari-hunter
source venv/bin/activate
python main.py
```

### Dashboard API

```bash
cd ~/workspace/mercari-hunter
source venv/bin/activate
python -m uvicorn app.api_server:app --host 0.0.0.0 --port 8501
```

## Web Dashboard

**アクセス:** `https://192.168.1.203/mercari/`

### タブ構成

| タブ | 説明 |
|------|------|
| 📦 商品 | 商品一覧（検索・フィルタ・ソート） |
| 📊 相場 | 相場分析・価格統計 |
| 🔑 キーワード | キーワード管理（CRUD・通知設定） |

### 機能

- **商品一覧**: 最新順・価格順でソート / キーワード別フィルタ / タイトル検索 / 価格帯フィルタ
- **相場分析**: カテゴリ別平均価格・中央値・価格分散 / 相場比較グラフ
- **キーワード管理**: CRUD 操作 / 価格帯設定 / 除外キーワード / 通知トリガー設定
- **価格履歴**: 個別商品の価格推移グラフ

## API エンドポイント

| メソッド | エンドポイント | 説明 |
|---------|---------------|------|
| GET | `/` | Dashboard HTML |
| GET | `/api/summary` | 統計サマリー（商品数・価格統計・キーワード数） |
| GET | `/api/items?offset=&limit=&sort=&keyword=&q=&price_min=&price_max=` | 商品一覧 |
| GET | `/api/keywords` | キーワード一覧（統計付き） |
| POST | `/api/keywords` | キーワード追加 |
| PUT | `/api/keywords/{name}` | キーワード更新 |
| DELETE | `/api/keywords/{name}` | キーワード削除 |
| GET | `/api/market-analysis?category=` | 相場分析（カテゴリ別統計） |
| GET | `/api/price_history?mercari_id=` | Mercari ID の価格履歴 |

## 設定

環境変数（または `.env`）:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=mercari
DB_USER=mercari
DB_PASSWORD=<password>

# または MERCARI_DB_ プリフィックスでも可
MERCARI_DB_HOST=localhost
MERCARI_DB_NAME=mercari
MERCARI_DB_USER=mercari
MERCARI_DB_PASSWORD=<password>

# Telegram 通知
TELEGRAM_BOT_TOKEN=<token>
TELEGRAM_CHAT_ID=<chat_id>
```
