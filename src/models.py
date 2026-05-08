"""Mercari Bargain Hunter - Database Models (PostgreSQL)"""
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone
from dataclasses import dataclass

# PostgreSQL schema creation SQL
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS keywords (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    search_term TEXT NOT NULL,
    search_url TEXT,
    min_price INTEGER,
    max_price INTEGER,
    category TEXT DEFAULT '',
    notify_on TEXT DEFAULT '[\"new\",\"bargain\"]',
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sellers (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    name TEXT DEFAULT '',
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS items (
    id SERIAL PRIMARY KEY,
    mercari_id VARCHAR(255) UNIQUE NOT NULL,
    name TEXT NOT NULL,
    price INTEGER NOT NULL,
    url TEXT NOT NULL,
    category TEXT,
    condition TEXT,
    description TEXT,
    image_url TEXT,
    seller_id TEXT,
    seller_rating REAL,
    listed_at TIMESTAMP,
    crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_flagged BOOLEAN DEFAULT FALSE,
    -- Attribute fields for structured price comparison
    brand TEXT,
    model TEXT,
    capacity TEXT,
    attributes TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS market_prices (
    id SERIAL PRIMARY KEY,
    item_name TEXT NOT NULL,
    brand TEXT,
    model TEXT,
    capacity TEXT,
    category TEXT,
    price_median REAL NOT NULL,
    price_mean REAL,
    price_min REAL,
    price_max REAL,
    sample_count INTEGER,
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_items_crawled_at ON items(crawled_at);
CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);
CREATE INDEX IF NOT EXISTS idx_keywords_enabled ON keywords(enabled);
"""

# Indexes that depend on brand/model/capacity columns — run after migration + commit
POST_MIGRATION_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_items_brand_model ON items(brand, model, capacity);
CREATE INDEX IF NOT EXISTS idx_market_prices_group ON market_prices(brand, model, capacity, category);
"""

# Additional migration: add last_notified_price column
MIGRATION_NOTIFIED = [
    ("items", "last_notified_price", "INTEGER"),
]


@dataclass
class Keyword:
    """Search keyword configuration stored in DB."""
    name: str
    search_term: str
    search_url: str = ""
    min_price: int = 0
    max_price: int = 0
    category: str = ""
    notify_on: str = '["new","bargain"]'
    enabled: bool = True
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)

    def to_db_tuple(self):
        return (
            self.name,
            self.search_term,
            self.search_url,
            self.min_price,
            self.max_price,
            self.category,
            self.notify_on,
            self.enabled,
        )


@dataclass
class Item:
    mercari_id: str
    name: str
    price: int
    url: str
    category: str = ""
    condition: str = ""
    description: str = ""
    image_url: str = ""
    seller_id: str = ""
    seller_rating: float = 0.0
    listed_at: str = None
    # Attribute fields
    brand: str = ""
    model: str = ""
    capacity: str = ""
    attributes: list = None

    def __post_init__(self):
        if self.attributes is None:
            self.attributes = []
        if self.listed_at is None:
            self.listed_at = None

    def to_db_tuple(self):
        import json
        return (
            self.mercari_id, self.name, self.price, self.url,
            self.category, self.condition, self.description,
            self.image_url, self.seller_id, self.seller_rating,
            self.listed_at,
            self.brand, self.model, self.capacity,
            json.dumps(self.attributes)
        )


@dataclass
class MarketPrice:
    item_name: str
    price_median: float
    price_mean: float = 0.0
    price_min: float = 0.0
    price_max: float = 0.0
    sample_count: int = 0
    calculated_at: datetime = None

    def __post_init__(self):
        if self.calculated_at is None:
            self.calculated_at = datetime.now(timezone.utc)


class DatabaseManager:
    """PostgreSQL database manager for Mercari data"""

    def __init__(self, dsn=None, **kwargs):
        # Key mapping: psycopg2 uses 'dbname' not 'database'
        KEY_MAP = {"database": "dbname"}
        
        if isinstance(dsn, dict):
            parts = []
            for key, value in dsn.items():
                if value is not None:
                    ps_key = KEY_MAP.get(key, key)
                    parts.append(f"{ps_key}={value}")
            self.dsn = " ".join(parts)
        elif dsn is not None:
            self.dsn = dsn
        else:
            # Build DSN from keyword arguments
            parts = []
            for key, value in kwargs.items():
                if value is not None:
                    ps_key = KEY_MAP.get(key, key)
                    parts.append(f"{ps_key}={value}")
            self.dsn = " ".join(parts)

    def get_connection(self):
        conn = psycopg2.connect(self.dsn)
        conn.autocommit = False
        return conn

    def initialize(self):
        """Create tables if they don't exist; add missing columns to existing tables."""
        conn = self.get_connection()
        try:
            # Step 1: Create tables first (IF NOT EXISTS is idempotent)
            with conn.cursor() as cur:
                cur.execute(SCHEMA_SQL)
                cur.execute(POST_MIGRATION_INDEXES)
            conn.commit()

            # Step 2: Add missing columns to existing tables (backward compat migration)
            MIGRATION_COLS = [
                ("items", "brand", "TEXT"),
                ("items", "model", "TEXT"),
                ("items", "capacity", "TEXT"),
                ("items", "attributes", "TEXT DEFAULT '[]'"),
            ]
            for tbl, col_name, col_type in MIGRATION_COLS:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name = %s AND column_name = %s
                        )
                    """, (tbl, col_name))
                    if not cur.fetchone()[0]:
                        with conn.cursor() as cur2:
                            cur2.execute(
                                f'ALTER TABLE {tbl} ADD COLUMN {col_name} {col_type}'
                            )
                        print(f"[DB] Added missing column: {tbl}.{col_name}")

            conn.commit()

            # Step 3: Add last_notified_price column if missing
            for tbl, col_name, col_type in MIGRATION_NOTIFIED:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name = %s AND column_name = %s
                        )
                    """, (tbl, col_name))
                    if not cur.fetchone()[0]:
                        with conn.cursor() as cur2:
                            cur2.execute(
                                f'ALTER TABLE {tbl} ADD COLUMN {col_name} {col_type}'
                            )
                        print(f"[DB] Added missing column: {tbl}.{col_name}")

            conn.commit()
        except psycopg2.Error as e:
            conn.rollback()
            print(f"[DB] Initialize error: {e}")
            raise
        finally:
            conn.close()

    def insert_item(self, item: Item) -> bool:
        """Insert item, skip if already exists (returns True if inserted)"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO items
                    (mercari_id, name, price, url, category, condition, description,
                     image_url, seller_id, seller_rating, listed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, item.to_db_tuple())
            conn.commit()
            return True
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            return False
        except psycopg2.Error as e:
            print(f"DB insert error: {e}")
            return False
        finally:
            conn.close()

    def new_item_from_dict(self, data: dict) -> Item:
        """Create an Item from a dict (crawler output)."""
        try:
            from src.extractor import MercariExtractor
        except ImportError:
            from extractor import MercariExtractor

        item_data = {
            "mercari_id": data.get("mercari_id", ""),
            "name": data.get("name", ""),
            "price": data.get("price", 0),
            "url": data.get("url", ""),
            "category": data.get("category", ""),
            "condition": data.get("condition", ""),
            "description": data.get("description", ""),
            "image_url": data.get("image_url", ""),
            "seller_id": data.get("seller_id", ""),
            "seller_rating": data.get("seller_rating", 0.0),
            "listed_at": data.get("listed_at"),
            "attributes": data.get("attributes", []),
        }

        # Extract brand/model/capacity if not already set
        if not data.get("brand") and data.get("name"):
            ext = MercariExtractor()
            brand, model, capacity = ext._extract_attributes(data["name"])
            item_data["brand"] = brand
            item_data["model"] = model
            item_data["capacity"] = capacity

        return Item(**item_data)

    def save_items(self, items: list[Item]) -> int:
        """Batch save items using ON CONFLICT DO NOTHING.
        
        Returns number of items inserted.
        """
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                tuples = [item.to_db_tuple() for item in items]
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO items
                    (mercari_id, name, price, url, category, condition, description,
                     image_url, seller_id, seller_rating, listed_at,
                     brand, model, capacity, attributes)
                    VALUES %s
                    ON CONFLICT (mercari_id) DO UPDATE SET
                        name        = EXCLUDED.name,
                        price       = EXCLUDED.price,
                        url         = EXCLUDED.url,
                        category    = EXCLUDED.category,
                        condition   = EXCLUDED.condition,
                        description = EXCLUDED.description,
                        image_url   = EXCLUDED.image_url,
                        seller_id   = EXCLUDED.seller_id,
                        seller_rating = EXCLUDED.seller_rating,
                        listed_at   = EXCLUDED.listed_at,
                        brand       = EXCLUDED.brand,
                        model       = EXCLUDED.model,
                        capacity    = EXCLUDED.capacity,
                        attributes  = EXCLUDED.attributes,
                        crawled_at  = CURRENT_TIMESTAMP
                    """,
                    tuples,
                    page_size=50,
                )
            conn.commit()
            return cur.rowcount
        except psycopg2.Error as e:
            conn.rollback()
            print(f"DB batch insert error: {e}")
            return 0
        finally:
            conn.close()

    def save_market_prices_for_names(
        self, normalized_names: list[str], keyword_name: str, lookback_days: int = 30,
        brand: str = "", model: str = "", capacity: str = "",
    ) -> int:
        """Calculate and UPSERT market prices for items, grouped by brand+model+capacity.

        Returns number of market prices saved.
        """
        import statistics
        saved = 0
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                # Build WHERE clause with brand/model/capacity filters
                where_parts = ["price > 0"]
                params = []

                if brand:
                    where_parts.append("brand ILIKE %s")
                    params.append(f"%{brand}%")
                if model:
                    where_parts.append("model ILIKE %s")
                    params.append(f"%{model}%")
                if capacity:
                    where_parts.append("capacity ILIKE %s")
                    params.append(f"%{capacity}%")

                if lookback_days:
                    where_parts.append(f"crawled_at >= CURRENT_TIMESTAMP - INTERVAL '{lookback_days} days'")

                query = f"SELECT price, brand, model, capacity FROM items WHERE {' AND '.join(where_parts)} ORDER BY crawled_at DESC LIMIT 500"

                cur.execute(query, params)
                rows = cur.fetchall()

                if not rows:
                    return 0

                # Group prices by (brand, model, capacity)
                groups: dict[tuple, list[float]] = {}
                for price, b, m, c in rows:
                    # Use raw values (may be None/empty) for grouping
                    key = (b or "", m or "", c or "")
                    groups.setdefault(key, []).append(price)

                for (b, m, c), prices in groups.items():
                    if len(prices) < 1:
                        continue

                    # Skip items where ALL attributes are missing —
                    # these would produce meaningless "unknown unknown unknown" entries.
                    if not b.strip() and not m.strip() and not c.strip():
                        continue

                    # Use display-friendly labels: empty → None (stored as NULL),
                    # not "unknown".  If brand is empty but model/capacity are
                    # known, just use what we have.
                    b_label = b if b and b.strip() else None
                    m_label = m if m and m.strip() else None
                    c_label = c if c and c.strip() else None

                    # Build a readable item_name from whatever we have
                    parts = [p for p in (b_label, m_label, c_label) if p]
                    item_name = " ".join(parts) if parts else "unidentified"

                    median = statistics.median(prices)
                    mean = statistics.mean(prices)

                    mp = MarketPrice(
                        item_name=item_name,
                        price_median=median,
                        price_mean=mean,
                        price_min=min(prices),
                        price_max=max(prices),
                        sample_count=len(prices),
                    )

                    # UPSERT by brand+model+capacity+category
                    cur.execute("""
                        SELECT id FROM market_prices
                        WHERE brand = %s AND model = %s AND capacity = %s
                        ORDER BY calculated_at DESC LIMIT 1
                    """, (b_label, m_label, c_label))
                    row = cur.fetchone()

                    if row:
                        cur.execute("""
                            UPDATE market_prices SET
                                price_median = %s,
                                price_mean = %s,
                                price_min = %s,
                                price_max = %s,
                                sample_count = %s,
                                calculated_at = %s
                            WHERE id = %s
                        """, (mp.price_median, mp.price_mean, mp.price_min,
                              mp.price_max, mp.sample_count, mp.calculated_at, row[0]))
                    else:
                        cur.execute("""
                            INSERT INTO market_prices
                            (item_name, brand, model, capacity, category,
                             price_median, price_mean, price_min, price_max, sample_count)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (mp.item_name, b_label, m_label, c_label, keyword_name,
                              mp.price_median, mp.price_mean,
                              mp.price_min, mp.price_max, mp.sample_count))
                    saved += 1
            conn.commit()
        except psycopg2.Error as e:
            conn.rollback()
            print(f"DB market price error: {e}")
        finally:
            conn.close()
        return saved

    def check_bargain_for_item(
        self, item_dict: dict, normalized_name: str, category: str, market_calc
    ) -> dict | None:
        """Check if an item is a bargain using DB market price data.
        
        Returns bargain details dict if bargain, None otherwise.
        """
        # Get market median from DB
        market_record = self.get_latest_market_price(normalized_name)
        
        if market_record:
            median = market_record.get('price_median', 0)
        else:
            # Fallback: calculate from raw prices
            prices = self.get_prices_by_normalized_name(
                normalized_name, category=category, lookback_days=30
            )
            if prices:
                import statistics
                median = statistics.median(prices)
            else:
                return None
        
        if median <= 0:
            return None
        
        details = market_calc.get_bargain_details(item_dict['price'], median)
        if details:
            details['mercari_id'] = item_dict['mercari_id']
            details['item_name'] = item_dict['name']
            details['item_url'] = item_dict['url']
            details['price'] = item_dict['price']
            details['condition'] = item_dict.get('condition', '')
            details['listed_at'] = item_dict.get('listed_at', '')
            details['image_url'] = item_dict.get('image_url', '')
        
        return details

    def get_items_by_date_range(self, start_date: str, end_date: str):
        """Get all items within a date range"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM items
                    WHERE crawled_at BETWEEN %s AND %s
                    ORDER BY crawled_at DESC
                """, (start_date, end_date))
                return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()

    def get_prices_by_normalized_name(self, normalized_name: str,
                                        category: str = None, lookback_days: int = 30):
        """Get prices for a specific normalized item name with optional filters.
        
        Args:
            normalized_name: partial name to match against
            category: filter by category (e.g. "SSD")
            lookback_days: only include items from the last N days
        """
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                query = """
                    SELECT price FROM items
                    WHERE name ILIKE %s AND price > 0
                """
                params = [f"%{normalized_name}%"]

                if category:
                    query += " AND category = %s"
                    params.append(category)

                if lookback_days:
                    query += f" AND crawled_at >= CURRENT_TIMESTAMP - INTERVAL '{lookback_days} days'"

                query += " ORDER BY crawled_at DESC LIMIT 200"

                cur.execute(query, params)
                return [row['price'] for row in cur.fetchall()]
        finally:
            conn.close()

    def get_category_stats(self, category: str) -> dict:
        """Get statistics for a category."""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        count(*) as total_items,
                        MIN(price) as min_price,
                        MAX(price) as max_price,
                        AVG(price) as avg_price,
                        MIN(crawled_at) as earliest,
                        MAX(crawled_at) as latest
                    FROM items
                    WHERE category = %s AND price > 0
                """, (category,))
                row = cur.fetchone()
                return dict(row) if row else {}
        finally:
            conn.close()

    def get_distinct_market_names(self) -> list[str]:
        """Get distinct item names that have market price records."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT item_name FROM market_prices
                    ORDER BY item_name
                """)
                return [row[0] for row in cur.fetchall()]
        finally:
            conn.close()

    def upsert_market_price(self, mp: MarketPrice):
        """UPSERT market price — merge with latest record for same item_name.
        
        Keeps the most recent calculation. Old rows are auto-pruned by
        `prune_stale_market_prices()` which should be called periodically.
        """
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                # Get the latest record for this item_name
                cur.execute("""
                    SELECT id FROM market_prices
                    WHERE item_name = %s
                    ORDER BY calculated_at DESC LIMIT 1
                """, (mp.item_name,))
                row = cur.fetchone()

                if row:
                    # UPDATE existing latest record
                    cur.execute("""
                        UPDATE market_prices SET
                            price_median = %s,
                            price_mean = %s,
                            price_min = %s,
                            price_max = %s,
                            sample_count = %s,
                            calculated_at = %s
                        WHERE id = %s
                    """, (mp.price_median, mp.price_mean, mp.price_min,
                          mp.price_max, mp.sample_count, mp.calculated_at, row[0]))
                else:
                    # INSERT new record
                    cur.execute("""
                        INSERT INTO market_prices
                        (item_name, price_median, price_mean, price_min, price_max, sample_count)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (mp.item_name, mp.price_median, mp.price_mean,
                          mp.price_min, mp.price_max, mp.sample_count))
            conn.commit()
        finally:
            conn.close()

    def get_latest_market_price(self, item_name: str) -> dict:
        """Get the latest market price record for an item name."""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM market_prices
                    WHERE item_name = %s
                    ORDER BY calculated_at DESC LIMIT 1
                """, (item_name,))
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            conn.close()

    def prune_stale_market_prices(self, keep_per_name: int = 3):
        """Delete old market_price records, keeping only the latest N per item_name."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(f"""
                    DELETE FROM market_prices
                    WHERE id NOT IN (
                        SELECT id FROM (
                            SELECT id, ROW_NUMBER() OVER (
                                PARTITION BY item_name ORDER BY calculated_at DESC
                            ) AS rn
                            FROM market_prices
                        ) sub
                        WHERE sub.rn <= {keep_per_name}
                    )
                """)
            conn.commit()
        finally:
            conn.close()

    # ── Keyword CRUD ──────────────────────────────────────────────

    def upsert_keyword(self, kw: Keyword) -> int:
        """Insert or update a keyword. Returns the keyword's DB id."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO keywords (name, search_term, search_url, min_price, max_price,
                                         category, notify_on, enabled)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (name) DO UPDATE SET
                        search_term  = EXCLUDED.search_term,
                        search_url   = EXCLUDED.search_url,
                        min_price    = EXCLUDED.min_price,
                        max_price    = EXCLUDED.max_price,
                        category     = EXCLUDED.category,
                        notify_on    = EXCLUDED.notify_on,
                        enabled      = EXCLUDED.enabled
                    RETURNING id
                """, kw.to_db_tuple())
                kid = cur.fetchone()[0]
            conn.commit()
            return kid
        except psycopg2.Error as e:
            conn.rollback()
            print(f"[DB] Upsert keyword error: {e}")
            raise

    def get_keywords(self, enabled_only: bool = True) -> list[dict]:
        """Return all keywords as dicts. Set enabled_only=False to include disabled ones."""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = "SELECT * FROM keywords"
                params: list = []
                if enabled_only:
                    sql += " WHERE enabled = TRUE"
                sql += " ORDER BY name"
                cur.execute(sql, params)
                return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()

    def get_keyword(self, name: str) -> dict | None:
        """Return a single keyword by name, or None."""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM keywords WHERE name = %s", (name,))
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            conn.close()

    def update_keyword_enabled(self, name: str, enabled: bool) -> bool:
        """Toggle a keyword's enabled flag. Returns True if a row was updated."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE keywords SET enabled = %s WHERE name = %s",
                    (enabled, name),
                )
                updated = cur.rowcount > 0
            conn.commit()
            return updated
        except psycopg2.Error as e:
            conn.rollback()
            print(f"[DB] Update keyword enabled error: {e}")
            return False

    def delete_keyword(self, name: str) -> bool:
        """Delete a keyword by name. Returns True if a row was deleted."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM keywords WHERE name = %s", (name,))
                deleted = cur.rowcount > 0
            conn.commit()
            return deleted
        except psycopg2.Error as e:
            conn.rollback()
            print(f"[DB] Delete keyword error: {e}")
            return False

    # ── Notification dedup ────────────────────────────────────────

    def should_notify(self, mercari_id: str, current_price: int, min_drop_percent: float = 10.0) -> bool:
        """Check if an item should be notified again.

        Rules:
        - First time seen → always notify
        - If last_notified_price is NULL → always notify
        - If current_price dropped >= min_drop_percent from last_notified_price → notify
        - Otherwise → skip (already notified at this price level)

        Returns True if the notification should proceed.
        """
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT last_notified_price FROM items WHERE mercari_id = %s",
                    (mercari_id,),
                )
                row = cur.fetchone()
                if row is None or row[0] is None:
                    return True  # first time

                last_price = row[0]
                if last_price <= 0:
                    return True

                drop_pct = (last_price - current_price) / last_price * 100
                return drop_pct >= min_drop_percent
        except psycopg2.Error as e:
            print(f"[DB] should_notify error: {e}")
            return True  # fail open — prefer to notify
        finally:
            conn.close()

    def update_notified_price(self, mercari_id: str, price: int) -> bool:
        """Record the price at which the item was last notified."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE items SET last_notified_price = %s WHERE mercari_id = %s",
                    (price, mercari_id),
                )
                updated = cur.rowcount > 0
            conn.commit()
            return updated
        except psycopg2.Error as e:
            conn.rollback()
            print(f"[DB] update_notified_price error: {e}")
            return False
        finally:
            conn.close()

    # ── Seller CRUD ───────────────────────────────────────────────

    def upsert_seller(self, username: str, name: str = "") -> int:
        """Insert or update a seller. Returns the seller's DB id."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO sellers (username, name)
                    VALUES (%s, %s)
                    ON CONFLICT (username) DO UPDATE SET
                        name = EXCLUDED.name
                    RETURNING id
                """, (username, name))
                sid = cur.fetchone()[0]
            conn.commit()
            return sid
        except psycopg2.Error as e:
            conn.rollback()
            print(f"[DB] Upsert seller error: {e}")
            raise

    def get_sellers(self, enabled_only: bool = True) -> list[dict]:
        """Return all sellers as dicts."""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = "SELECT * FROM sellers"
                params: list = []
                if enabled_only:
                    sql += " WHERE enabled = TRUE"
                sql += " ORDER BY username"
                cur.execute(sql, params)
                return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()

    def update_seller_enabled(self, username: str, enabled: bool) -> bool:
        """Toggle a seller's enabled flag."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE sellers SET enabled = %s WHERE username = %s",
                    (enabled, username),
                )
                updated = cur.rowcount > 0
            conn.commit()
            return updated
        except psycopg2.Error as e:
            conn.rollback()
            print(f"[DB] Update seller enabled error: {e}")
            return False

    def delete_seller(self, username: str) -> bool:
        """Delete a seller by username."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM sellers WHERE username = %s", (username,))
                deleted = cur.rowcount > 0
            conn.commit()
            return deleted
        except psycopg2.Error as e:
            conn.rollback()
            print(f"[DB] Delete seller error: {e}")
            return False

    def save_seller_items(self, seller_username: str, items: list) -> int:
        """Save/update items crawled from a specific seller. Returns count of items saved."""
        if not items:
            return 0
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                for item in items:
                    mercari_id = item.get("mercari_id", "")
                    name = item.get("name", "")
                    price = item.get("price", 0)
                    url = item.get("url", "")
                    image_url = item.get("image_url", "")

                    cur.execute("""
                        INSERT INTO items (mercari_id, name, price, url, image_url, seller_id, seller_username, crawled_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (mercari_id) DO UPDATE SET
                            name = EXCLUDED.name,
                            price = EXCLUDED.price,
                            url = EXCLUDED.url,
                            image_url = EXCLUDED.image_url,
                            seller_id = EXCLUDED.seller_id,
                            seller_username = EXCLUDED.seller_username,
                            crawled_at = NOW()
                    """, (mercari_id, name, price, url, image_url, seller_username, seller_username))
                count = cur.rowcount + 1  # rowcount is 1 for last INSERT, approximate
            conn.commit()
            return len(items)
        except psycopg2.Error as e:
            conn.rollback()
            print(f"[DB] save_seller_items error: {e}")
            return 0
        finally:
            conn.close()

    def get_seller_items(self, username: str, limit: int = 200) -> list[dict]:
        """Get items from a specific seller, ordered by latest crawl."""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT mercari_id, name, price, url, image_url, seller_id, seller_username, crawled_at
                    FROM items
                    WHERE seller_username = %s AND price > 0
                    ORDER BY crawled_at DESC
                    LIMIT %s
                """, (username, limit))
                return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()
