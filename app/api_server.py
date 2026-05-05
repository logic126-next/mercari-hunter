"""Mercari Hunter Dashboard — FastAPI backend

Usage:
    uvicorn app.api_server:app --reload --host 0.0.0.0 --port 8501
"""
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import psycopg2
import psycopg2.extras
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="Mercari Hunter Dashboard")


def get_db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "mercari"),
        user=os.getenv("DB_USER", "mercari"),
        password=os.getenv("DB_PASSWORD", "mercari"),
    )


def query(sql: str, params=None):
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            if cur.description:
                return cur.fetchall()
            return []


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    _template_dir = Path(__file__).resolve().parent / "templates"
    return HTMLResponse(content=(_template_dir / "dashboard.html").read_text(encoding="utf-8"))


# ── API endpoints ──────────────────────────────────────────────

@app.get("/api/summary")
def api_summary():
    """Top-level stats."""
    rows = query("""
        SELECT
            (SELECT COUNT(*) FROM items)                                          AS total_items,
            (SELECT COUNT(*) FROM keywords WHERE enabled)                         AS active_keywords,
            (SELECT COUNT(DISTINCT brand) FROM items WHERE brand IS NOT NULL AND brand != '') AS brands,
            (SELECT MAX(crawled_at) FROM items)                                   AS last_crawl,
            (SELECT MIN(price) FROM items)                                        AS min_price,
            (SELECT MAX(price) FROM items)                                        AS max_price,
            (SELECT ROUND(AVG(price))::int FROM items)                            AS avg_price,
            (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price)::int FROM items) AS median_price,
            (SELECT COUNT(*) FROM items WHERE crawled_at >= NOW() - INTERVAL '1 hour') AS items_last_hour,
            (SELECT COUNT(*) FROM items WHERE crawled_at >= NOW() - INTERVAL '24 hours') AS items_last_24h,
            (SELECT COUNT(*) FROM market_prices)                                  AS market_price_records
    """)
    r = rows[0]
    if r["last_crawl"]:
        r["last_crawl"] = r["last_crawl"].isoformat()
    return dict(r)


@app.get("/api/price_distribution")
def api_price_distribution(bins: int = 15):
    """Log-scale price histogram — items are heavily skewed toward low prices."""
    rows = query(f"""
        SELECT bucket, count,
               CAST(POWER(10, (min_log + (bucket-1) * bin_w)) AS integer) AS bin_start,
               CAST(POWER(10, (min_log + bucket * bin_w)) AS integer) AS bin_end
        FROM (
            SELECT CAST(LOG10(GREATEST(price, 1)) AS integer) AS bucket,
                   COUNT(*) AS count, min_log, bin_w
            FROM items,
                 (SELECT
                      LOG10(MIN(GREATEST(price, 1))) AS min_log,
                      LOG10(MAX(GREATEST(price, 1))) AS max_log,
                      (LOG10(MAX(GREATEST(price, 1))) - LOG10(MIN(GREATEST(price, 1)))) / {bins} AS bin_w
                 FROM items) b
            GROUP BY bucket, min_log, bin_w
        ) sub
        ORDER BY bucket
    """)
    return [{"bucket": int(r["bucket"]), "count": int(r["count"]),
             "bin_start": int(r["bin_start"]), "bin_end": int(r["bin_end"])} for r in rows]


@app.get("/api/brands")
def api_brands(limit: int = 15):
    """Top brands by item count with avg/median price."""
    rows = query("""
        SELECT brand,
               COUNT(*)           AS cnt,
               ROUND(AVG(price))::int   AS avg_price,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price)::int AS median_price,
               MIN(price)         AS min_price,
               MAX(price)         AS max_price
        FROM items
        WHERE brand IS NOT NULL AND brand != ''
        GROUP BY brand
        ORDER BY cnt DESC
        LIMIT %s
    """, (limit,))
    return [dict(r) for r in rows]


@app.get("/api/keywords")
def api_keywords():
    """Keyword status with latest stats."""
    rows = query("""
        SELECT k.name, k.search_term, k.category, k.enabled,
               k.min_price, k.max_price,
               COUNT(i.id)          AS total_items,
               ROUND(AVG(i.price))::int   AS avg_price,
               MAX(i.crawled_at)    AS last_seen
        FROM keywords k
        LEFT JOIN items i ON i.category = k.name
        GROUP BY k.id
        ORDER BY k.id
    """)
    result = []
    for r in rows:
        rd = dict(r)
        if rd["last_seen"]:
            rd["last_seen"] = rd["last_seen"].isoformat()
        result.append(rd)
    return result


@app.get("/api/items")
def api_items(
    offset: int = 0,
    limit: int = 30,
    sort: str = "newest",
    brand: Optional[str] = None,
    category: Optional[str] = None,
    q: Optional[str] = None,
):
    """Paginated item list with filters."""
    sort_map = {
        "newest":  "crawled_at DESC",
        "oldest":  "crawled_at ASC",
        "cheap":   "price ASC",
        "expensive": "price DESC",
    }
    order = sort_map.get(sort, "crawled_at DESC")

    where = ["1=1"]
    params = []
    if brand:
        where.append("brand = %s")
        params.append(brand)
    if category:
        where.append("category = %s")
        params.append(category)
    if q:
        where.append("name ILIKE %s")
        params.append(f"%{q}%")

    where_sql = " AND ".join(where)

    items = query(f"""
        SELECT mercari_id, name, price, brand, model, capacity,
               category, condition, url, image_url, listed_at, crawled_at
        FROM items
        WHERE {where_sql}
        ORDER BY {order}
        LIMIT %s OFFSET %s
    """, params + [limit, offset])

    total = query(f"SELECT COUNT(*) FROM items WHERE {where_sql}", params)[0]["count"]

    result = []
    for r in items:
        rd = dict(r)
        for col in ("listed_at", "crawled_at"):
            if rd.get(col):
                rd[col] = rd[col].isoformat()
        result.append(rd)

    return {"items": result, "total": total, "offset": offset, "limit": limit}


@app.get("/api/price_trend")
def api_price_trend(hours: int = 24):
    """Price trend over time (items crawled per time window + avg price)."""
    rows = query("""
        SELECT DATE_TRUNC('hour', crawled_at) AS hour,
               COUNT(*)                       AS cnt,
               ROUND(AVG(price))::int         AS avg_price
        FROM items
        WHERE crawled_at >= NOW() - INTERVAL '%s hours'
        GROUP BY 1
        ORDER BY 1
    """, (hours,))
    return [{"hour": r["hour"].isoformat(), "cnt": r["cnt"], "avg_price": r["avg_price"]} for r in rows]


@app.get("/api/market_prices")
def api_market_prices(
    offset: int = 0,
    limit: int = 30,
    brand: Optional[str] = None,
):
    """Market price records with optional brand filter."""
    where = "1=1"
    params = []
    if brand:
        where = "brand = %s"
        params = [brand]

    rows = query(f"""
        SELECT item_name, brand, model, capacity,
               price_median, price_mean, price_min, price_max,
               sample_count, calculated_at
        FROM market_prices
        WHERE {where}
        ORDER BY calculated_at DESC
        LIMIT %s OFFSET %s
    """, params + [limit, offset])

    return [dict(r) for r in rows]


@app.get("/api/bargains")
def api_bargains(limit: int = 20):
    """Items flagged as potential bargains (price well below market median)."""
    rows = query("""
        SELECT i.mercari_id, i.name, i.price, i.brand, i.model,
               i.capacity, i.url, i.image_url, i.crawled_at,
               mp.price_median, mp.price_mean
        FROM items i
        JOIN market_prices mp ON i.name = mp.item_name
        WHERE i.price < mp.price_median * 0.7
          AND mp.price_median - i.price > 5000
        ORDER BY mp.price_median - i.price DESC
        LIMIT %s
    """, (limit,))
    return [dict(r) for r in rows]


@app.get("/api/sellers")
def api_sellers():
    """List all sellers with item counts."""
    rows = query("""
        SELECT s.id, s.username, s.name, s.enabled, s.created_at,
               COUNT(i.id) AS total_items,
               ROUND(AVG(i.price))::int AS avg_price,
               MAX(i.crawled_at) AS last_crawled
        FROM sellers s
        LEFT JOIN items i ON i.seller_username = s.username
        GROUP BY s.id
        ORDER BY s.username
    """)
    result = []
    for r in rows:
        rd = dict(r)
        if rd.get("last_crawled"):
            rd["last_crawled"] = rd["last_crawled"].isoformat()
        if rd.get("created_at"):
            rd["created_at"] = rd["created_at"].isoformat()
        result.append(rd)
    return result


@app.get("/api/seller_items")
def api_seller_items(
    username: str,
    offset: int = 0,
    limit: int = 50,
    sort: str = "newest",
):
    """Get items from a specific seller."""
    sort_map = {
        "newest": "crawled_at DESC",
        "oldest": "crawled_at ASC",
        "cheap": "price ASC",
        "expensive": "price DESC",
    }
    order = sort_map.get(sort, "crawled_at DESC")

    items = query(f"""
        SELECT mercari_id, name, price, url, image_url, seller_username, crawled_at
        FROM items
        WHERE seller_username = %s AND price > 0
        ORDER BY {order}
        LIMIT %s OFFSET %s
    """, (username, limit, offset))

    total = query("SELECT COUNT(*) FROM items WHERE seller_username = %s AND price > 0", (username,))[0]["count"]

    result = []
    for r in items:
        rd = dict(r)
        if rd.get("crawled_at"):
            rd["crawled_at"] = rd["crawled_at"].isoformat()
        result.append(rd)

    return {"items": result, "total": total, "offset": offset, "limit": limit, "username": username}


@app.get("/api/categories")
def api_categories():
    """Item count and avg price per category."""
    rows = query("""
        SELECT COALESCE(category, '(未分類)') AS category,
               COUNT(*)                       AS cnt,
               ROUND(AVG(price))::int         AS avg_price,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price)::int AS median_price
        FROM items
        GROUP BY category
        ORDER BY cnt DESC
    """)
    return [dict(r) for r in rows]



