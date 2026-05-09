"""Mercari Bargain Hunter - Main Entry Point

Pure synchronous main loop — compatible with Playwright sync API.
Reuses a single Chromium browser across scan cycles.

Usage:
    python3 main.py              # Run in loop mode
    python3 main.py --test       # Run single scan (first keyword only)
    python3 main.py --add "keyword"  # Add a new keyword
    python3 main.py --remove "keyword"  # Remove a keyword
    python3 main.py --list           # List all keywords
    python3 main.py --enable "keyword"     # Enable a keyword
    python3 main.py --disable "keyword"    # Disable a keyword
"""
import argparse
import logging
import os
import random
import statistics
import time

from dotenv import load_dotenv
load_dotenv()  # 加载 .env 文件中的环境变量（TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID）

import psycopg2
import psycopg2.extras
import yaml

from src.models import DatabaseManager
from src.market_price import MarketPriceCalculator
from src.notifier import TelegramNotifier
from src.filter_engine import FilterEngine
from src.crawler import MercariCrawler


logger = logging.getLogger(__name__)


def setup_logging():
    """Configure logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler("logs/hunter.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def load_config() -> dict:
    """Load configuration from config.yaml."""
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)


def list_keywords(db: DatabaseManager):
    """List all keywords."""
    keywords = db.get_keywords(enabled_only=False)
    if not keywords:
        print("No keywords configured.")
        return
    print(f"{'ID':<4} {'Name':<30} {'Enabled':<8} {'Min':<8} {'Max':<8}")
    print("-" * 60)
    for kw in keywords:
        status = "ON" if kw.get("enabled", True) else "OFF"
        min_p = kw.get("min_price", 0) or 0
        max_p = kw.get("max_price", 0) or 0
        min_str = f"¥{min_p}" if min_p else "-"
        max_str = f"¥{max_p}" if max_p else "-"
        print(f"{kw['id']:<4} {kw['name']:<30} {status:<8} {min_str:<8} {max_str:<8}")


def list_sellers(db: DatabaseManager):
    """List all sellers."""
    sellers = db.get_sellers(enabled_only=False)
    if not sellers:
        print("No sellers configured.")
        return
    print(f"{'ID':<4} {'Username':<25} {'Name':<25} {'Enabled':<8}")
    print("-" * 62)
    for s in sellers:
        status = "ON" if s.get("enabled", True) else "OFF"
        print(f"{s['id']:<4} {s['username']:<25} {s.get('name', ''):<25} {status:<8}")


def process_seller(username: str, crawler: MercariCrawler,
                   db: DatabaseManager, filter_engine: FilterEngine) -> dict:
    """Process a single seller — crawl all listed items, filter, save."""
    logger.info(f"Crawling seller: {username}")

    items = crawler.crawl_seller(username)
    if not items:
        logger.warning(f"No items found for seller '{username}'")
        return {"username": username, "crawled": 0, "saved": 0}

    logger.info(f"Crawled {len(items)} items from seller '{username}'")

    filtered_items = filter_engine.filter_items(items)
    logger.info(f"Filtered to {len(filtered_items)} items for seller '{username}'")

    saved = db.save_seller_items(username, filtered_items)
    logger.info(f"Saved/updated {saved} items from seller '{username}'")

    return {"username": username, "crawled": len(items), "saved": saved}


def _get_market_median_for_item(db: DatabaseManager, item: dict) -> float | None:
    """Find the best matching market median price for an item.
    
    Strategy: 
    1. Exact brand+model+capacity match in market_prices
    2. Fuzzy brand+model match (ILIKE substring)
    3. Fallback: compute median from items table by name similarity
    """
    brand = item.get("brand", "").strip()
    model = item.get("model", "").strip()
    capacity = item.get("capacity", "").strip()
    name = item.get("name", "")

    conn = db.get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Strategy 1: Exact match on brand+model+capacity
            if brand and model and capacity:
                cur.execute("""
                    SELECT price_median, price_mean FROM market_prices
                    WHERE brand = %s AND model = %s AND capacity = %s
                      AND price_median > 0
                    ORDER BY calculated_at DESC LIMIT 1
                """, (brand, model, capacity))
                row = cur.fetchone()
                if row:
                    return dict(row)

            # Strategy 2: Brand+model match (capacity fuzzy)
            if brand and model:
                cur.execute("""
                    SELECT price_median, price_mean FROM market_prices
                    WHERE brand ILIKE %s AND model ILIKE %s
                      AND price_median > 0
                    ORDER BY calculated_at DESC LIMIT 1
                """, (f"%{brand}%", f"%{model}%"))
                row = cur.fetchone()
                if row:
                    return dict(row)

            # Strategy 3: Brand only (from market_prices)
            if brand:
                cur.execute("""
                    SELECT price_median, price_mean FROM market_prices
                    WHERE brand ILIKE %s AND brand != 'unknown'
                      AND price_median > 0
                    ORDER BY calculated_at DESC LIMIT 5
                """, (f"%{brand}%",))
                rows = [dict(r) for r in cur.fetchall()]
                if rows:
                    # Average medians of closest matches
                    medians = [r["price_median"] for r in rows if r["price_median"] > 0]
                    if medians:
                        return {
                            "price_median": statistics.median(medians),
                            "price_mean": statistics.mean([r["price_mean"] for r in rows]),
                        }

            # Strategy 4: Fallback — compute from items table by name
            cur.execute("""
                SELECT price FROM items
                WHERE name ILIKE %s AND price > 0
                ORDER BY crawled_at DESC LIMIT 200
            """, (f"%{name}%",))
            price_rows = cur.fetchall()
            if price_rows:
                prices = [r["price"] for r in price_rows]
                return {
                    "price_median": statistics.median(prices),
                    "price_mean": statistics.mean(prices),
                }

            # Strategy 5: Keyword name from DB
            kw_name = name.split()[0] if name else ""
            if kw_name:
                cur.execute("""
                    SELECT price FROM items
                    WHERE name ILIKE %s AND price > 0
                    ORDER BY crawled_at DESC LIMIT 200
                """, (f"%{kw_name}%",))
                price_rows = cur.fetchall()
                if price_rows:
                    prices = [r["price"] for r in price_rows]
                    return {
                        "price_median": statistics.median(prices),
                        "price_mean": statistics.mean(prices),
                    }

            return None

    except Exception as e:
        logger.debug(f"Market price lookup failed: {e}")
        return None
    finally:
        conn.close()


def process_keyword(keyword: dict, crawler: MercariCrawler,
                    db: DatabaseManager, notifier: TelegramNotifier,
                    filter_engine: FilterEngine, config: dict) -> dict:
    """Process a single keyword through the full pipeline."""
    name = keyword["name"]
    search_url = keyword["search_url"]
    logger.info(f"Processing keyword: {name}")

    # 1. Crawl
    crawl_result = crawler.crawl(search_url)
    raw_items = crawl_result["items"]

    if not raw_items:
        logger.warning(f"No items extracted for '{name}'")
        return {"name": name, "extracted": 0, "filtered": 0, "bargains": 0}

    logger.info(f"Crawled {len(raw_items)} items for '{name}'")

    # 2. Filter
    kw_min_price = keyword.get("min_price", 0) or 0
    kw_max_price = keyword.get("max_price", 0) or 0
    filtered_items = filter_engine.filter_items(raw_items, min_price=kw_min_price, max_price=kw_max_price)
    logger.info(f"Filtered to {len(filtered_items)} items for '{name}' (price range: {kw_min_price or '∞'} - {kw_max_price or '∞'})")

    # 3. Save items (upsert)
    items_to_save = []
    for item in filtered_items:
        try:
            item_obj = db.new_item_from_dict(item)
            items_to_save.append(item_obj)
        except Exception as e:
            logger.debug(f"Failed to build Item from dict: {e}")

    saved = db.save_items(items_to_save) if items_to_save else 0
    logger.info(f"Saved/updated {saved} items in DB for '{name}'")

    # 4. Market price calculation
    mp_calc = MarketPriceCalculator(config.get("market_price", {}))
    prices = [it.get("price", 0) for it in filtered_items if it.get("price", 0) > 0]
    stats = mp_calc.calculate_statistics(prices) if prices else {}

    # 5. Save market prices
    mp_saved = db.save_market_prices_for_names(
        normalized_names=[name],
        keyword_name=name,
        lookback_days=30,
    )
    logger.info(f"Updated {mp_saved} market price records for '{name}'")

    # 6. Bargain detection
    bargains = []
    threshold_ratio = config.get("threshold_ratio", 0.7)
    absolute_threshold = config.get("absolute_threshold_yen", 10000)

    for item in filtered_items:
        item_price = item.get("price", 0)
        if item_price <= 0:
            continue

        market_info = _get_market_median_for_item(db, item)
        if not market_info:
            continue

        median = market_info.get("price_median", 0)
        if median <= 0:
            continue

        # Must satisfy BOTH thresholds
        price_ratio = item_price / median
        if price_ratio > threshold_ratio:
            continue
        if median - item_price < absolute_threshold:
            continue

        discount_pct = round((1 - price_ratio) * 100, 1)

        bargain = {
            "mercari_id": item.get("mercari_id", ""),
            "item_name": item.get("name", ""),
            "item_url": item.get("url", ""),
            "price": item_price,
            "market_median": int(median),
            "market_mean": int(market_info.get("price_mean", 0)),
            "discount_pct": discount_pct,
            "discount_yen": int(median - item_price),
            "difference_yen": int(median - item_price),
            "difference": int(median - item_price),
            "discount_percent": discount_pct,
            "condition": item.get("condition", ""),
            "listed_at": item.get("listed_at", ""),
            "image_url": item.get("image_url", ""),
        }
        bargains.append(bargain)

    logger.info(f"Found {len(bargains)} bargains for '{name}'")
    for b in bargains[:5]:
        logger.info(
            f"  Bargain: {b['item_name']} ¥{b['price']:,} "
            f"(median: ¥{b['market_median']:,}, -{b['discount_pct']}%)"
        )

    # 7. Notification dedup
    min_drop = config.get("min_drop_percent", 10.0)
    new_bargains = []
    for bargain in bargains:
        mercari_id = bargain.get("mercari_id")
        price = bargain.get("price", 0)
        if mercari_id and db.should_notify(mercari_id, price, min_drop / 100.0):
            new_bargains.append(bargain)
        else:
            logger.info(f"Skipping notify for {mercari_id}")

    # 8. Send notifications
    if new_bargains:
        notifier.send_bargain_alerts_sync(new_bargains)
        for bargain in new_bargains:
            mercari_id = bargain.get("mercari_id")
            price = bargain.get("price", 0)
            if mercari_id:
                db.update_notified_price(mercari_id, price)
            time.sleep(0.5)

    return {
        "name": name,
        "extracted": len(raw_items),
        "filtered": len(filtered_items),
        "bargains": len(new_bargains),
    }


def main():
    parser = argparse.ArgumentParser(description="Mercari Bargain Hunter")
    parser.add_argument("--test", action="store_true", help="Run single scan with first keyword only")
    parser.add_argument("--add", type=str, help="Add a keyword")
    parser.add_argument("--remove", type=str, help="Remove a keyword")
    parser.add_argument("--list", action="store_true", help="List all keywords")
    parser.add_argument("--enable", type=str, help="Enable a keyword")
    parser.add_argument("--disable", type=str, help="Disable a keyword")
    parser.add_argument("--add-seller", type=str, help="Add a seller (username)")
    parser.add_argument("--list-sellers", action="store_true", help="List all sellers")
    parser.add_argument("--remove-seller", type=str, help="Remove a seller")
    parser.add_argument("--enable-seller", type=str, help="Enable a seller")
    parser.add_argument("--disable-seller", type=str, help="Disable a seller")
    parser.add_argument("--test-seller", type=str, help="Test crawl a seller (single run)")
    args = parser.parse_args()

    setup_logging()
    config = load_config()

    # Override DB credentials from environment variables
    db_cfg = dict(config.get("database", {}))
    for env_key, cfg_key in [
        ("MERCARI_DB_HOST", "host"),
        ("MERCARI_DB_PORT", "port"),
        ("MERCARI_DB_NAME", "dbname"),
        ("MERCARI_DB_USER", "user"),
        ("MERCARI_DB_PASSWORD", "password"),
    ]:
        val = os.environ.get(env_key)
        if val:
            db_cfg[cfg_key] = int(val) if cfg_key == "port" else val
    config["database"] = db_cfg

    db = DatabaseManager(config["database"])

    # CLI commands
    if args.list:
        list_keywords(db)
        return
    if args.add:
        from src.models import Keyword
        kw = Keyword(name=args.add, search_term=args.add,
                     search_url=f"https://jp.mercari.com/items?item_name={args.add}",
                     enabled=True)
        kid = db.upsert_keyword(kw)
        print(f"Added keyword: {args.add} (id={kid})")
        return
    if args.remove:
        ok = db.delete_keyword(args.remove)
        print(f"Removed keyword: {args.remove}" if ok else f"Keyword not found: {args.remove}")
        return
    if args.enable:
        ok = db.update_keyword_enabled(args.enable, True)
        print(f"Enabled: {args.enable}" if ok else f"Not found: {args.enable}")
        return
    if args.disable:
        ok = db.update_keyword_enabled(args.disable, False)
        print(f"Disabled: {args.disable}" if ok else f"Not found: {args.disable}")
        return

    # ── Seller CLI commands ──
    if args.list_sellers:
        list_sellers(db)
        return
    if args.add_seller:
        username = args.add_seller.split("/").pop().strip()
        sid = db.upsert_seller(username)
        print(f"Added seller: {username} (id={sid})")
        return
    if args.remove_seller:
        ok = db.delete_seller(args.remove_seller)
        print(f"Removed seller: {args.remove_seller}" if ok else f"Seller not found: {args.remove_seller}")
        return
    if args.enable_seller:
        ok = db.update_seller_enabled(args.enable_seller, True)
        print(f"Enabled seller: {args.enable_seller}" if ok else f"Not found: {args.enable_seller}")
        return
    if args.disable_seller:
        ok = db.update_seller_enabled(args.disable_seller, False)
        print(f"Disabled seller: {args.disable_seller}" if ok else f"Not found: {args.disable_seller}")
        return

    crawler = MercariCrawler(config["crawler"])
    notifier = TelegramNotifier(config["notification"])
    filter_engine = FilterEngine(config["filtering"])

    keywords = db.get_keywords(enabled_only=True)
    sellers = db.get_sellers(enabled_only=True)

    if args.test_seller:
        logger.info(f"Running in TEST-SELLER mode: {args.test_seller}")
        result = process_seller(args.test_seller, crawler, db, filter_engine)
        logger.info(f"Test result: {result}")
        crawler.close()
        return

    if not keywords and not sellers:
        logger.error("No active keywords or sellers. Add with --add 'keyword' or --add-seller 'username'.")
        crawler.close()
        return

    # Process keywords
    if args.test:
        keywords = keywords[:1]
        sellers = []  # test mode = keywords only
        logger.info("Running in TEST mode (single scan, first keyword only)")

    if keywords or sellers:
        logger.info(f"Starting scan: {len(keywords)} keyword(s), {len(sellers)} seller(s)")
    else:
        logger.info("No targets to scan.")

    results = []
    for keyword in keywords:
        result = process_keyword(
            keyword, crawler, db, notifier, filter_engine, config,
        )
        results.append(result)

        if keyword != keywords[-1]:
            sleep_time = random.randint(
                config.get("wait_min", 20),
                config.get("wait_max", 40),
            )
            logger.info(f"Waiting {sleep_time}s before next keyword...")
            time.sleep(sleep_time)

    # Process sellers
    seller_results = []
    for seller in sellers:
        result = process_seller(seller["username"], crawler, db, filter_engine)
        seller_results.append(result)

        sleep_time = random.randint(
            config.get("wait_min", 20),
            config.get("wait_max", 40),
        )
        logger.info(f"Waiting {sleep_time}s before next seller...")
        time.sleep(sleep_time)

    logger.info("Scan complete. Summary:")
    total_extracted = sum(r["extracted"] for r in results)
    total_filtered = sum(r["filtered"] for r in results)
    total_bargains = sum(r["bargains"] for r in results)
    total_seller_crawled = sum(r["crawled"] for r in seller_results)
    total_seller_saved = sum(r["saved"] for r in seller_results)
    logger.info(f"  Keywords: {len(keywords)}, extracted: {total_extracted}, filtered: {total_filtered}, bargains: {total_bargains}")
    logger.info(f"  Sellers: {len(sellers)}, crawled: {total_seller_crawled}, saved: {total_seller_saved}")

    crawler.close()

     # Run in loop mode
    if not args.test:
        logger.info("Entering scan loop...")
        while True:
            time.sleep(random.randint(
                config.get("interval_seconds", 30),
                config.get("interval_seconds", 30) + 10,
            ))
            keywords = db.get_keywords(enabled_only=True)
            sellers = db.get_sellers(enabled_only=True)
            if not keywords and not sellers:
                logger.warning("No keywords or sellers — sleeping...")
                time.sleep(60)
                continue

            logger.info(f"Starting scan: {len(keywords)} keyword(s), {len(sellers)} seller(s)")
            results = []
            for keyword in keywords:
                try:
                    result = process_keyword(
                        keyword, crawler, db, notifier, filter_engine, config,
                    )
                except Exception as e:
                    logger.error(f"Error processing '{keyword['name']}': {e}", exc_info=True)
                    result = {"name": keyword["name"], "extracted": 0, "filtered": 0, "bargains": 0}
                results.append(result)

                if keyword != keywords[-1]:
                    sleep_time = random.randint(
                        config.get("wait_min", 20),
                        config.get("wait_max", 40),
                    )
                    logger.info(f"Waiting {sleep_time}s before next keyword...")
                    time.sleep(sleep_time)

            # Process sellers
            seller_results = []
            for seller in sellers:
                try:
                    result = process_seller(seller["username"], crawler, db, filter_engine)
                except Exception as e:
                    logger.error(f"Error processing seller '{seller['username']}': {e}", exc_info=True)
                    result = {"username": seller["username"], "crawled": 0, "saved": 0}
                seller_results.append(result)

                sleep_time = random.randint(
                    config.get("wait_min", 20),
                    config.get("wait_max", 40),
                )
                logger.info(f"Waiting {sleep_time}s before next seller...")
                time.sleep(sleep_time)

            total_extracted = sum(r["extracted"] for r in results)
            total_bargains = sum(r["bargains"] for r in results)
            total_seller_crawled = sum(r["crawled"] for r in seller_results)
            logger.info(f"Scan done: {total_extracted} items, {total_bargains} bargains, {total_seller_crawled} seller items")


if __name__ == "__main__":
    main()
