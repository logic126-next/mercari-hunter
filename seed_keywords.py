#!/usr/bin/env python3
"""Seed keywords into the database.

Usage:
    python3 seed_keywords.py            # Import default keywords
    python3 seed_keywords.py --add "Samsung SSD" --url "https://..."  # Add one
    python3 seed_keywords.py --list     # List all keywords
    python3 seed_keywords.py --enable "SSD"     # Enable a keyword
    python3 seed_keywords.py --disable "SSD"    # Disable a keyword
    python3 seed_keywords.py --delete "SSD"     # Delete a keyword
"""
import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

sys.path.insert(0, str(Path(__file__).parent / "src"))

from models import DatabaseManager, Keyword

# Default seed keywords
DEFAULT_KEYWORDS = [
    {
        "name": "SSD",
        "search_term": "SSD",
        "category": "SSD",
    },
    {
        "name": "iPhone",
        "search_term": "iPhone",
        "category": "iPhone",
    },
    {
        "name": "ゲーミングPC",
        "search_term": "ゲーミングPC",
        "category": "ゲーミングPC",
    },
]


def main():
    import yaml
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    if "database" in config and "dbname" in config["database"]:
        config["database"]["database"] = config["database"]["dbname"]

    db = DatabaseManager(config["database"])
    db.initialize()

    parser = argparse.ArgumentParser(description="Manage Mercari search keywords")
    parser.add_argument("--list", action="store_true", help="List all keywords")
    parser.add_argument("--add", type=str, help="Add a keyword (name)")
    parser.add_argument("--url", type=str, default="", help="Search URL for --add")
    parser.add_argument("--category", type=str, default="", help="Category for --add")
    parser.add_argument("--min-price", type=int, default=0, help="Min price for --add")
    parser.add_argument("--max-price", type=int, default=0, help="Max price for --add")
    parser.add_argument("--enable", type=str, help="Enable a keyword by name")
    parser.add_argument("--disable", type=str, help="Disable a keyword by name")
    parser.add_argument("--delete", type=str, help="Delete a keyword by name")
    parser.add_argument("--seed", action="store_true", help="Import default seed keywords")
    args = parser.parse_args()

    # ── List ──
    if args.list:
        rows = db.get_keywords(enabled_only=False)
        if not rows:
            print("No keywords found. Use --seed to import defaults.")
            return
        print(f"{'Name':<20} {'Search Term':<20} {'Category':<15} {'Enabled':<8} {'Min Price':<10} {'Max Price':<10}")
        print("-" * 83)
        for r in rows:
            print(f"{r['name']:<20} {r['search_term']:<20} {r.get('category',''):<15} {r['enabled']:<8} {r.get('min_price',0):<10} {r.get('max_price',0):<10}")
        return

    # ── Add ──
    if args.add:
        kw = Keyword(
            name=args.add,
            search_term=args.add,
            search_url=args.url,
            category=args.category or args.add,
            min_price=args.min_price,
            max_price=args.max_price,
        )
        kid = db.upsert_keyword(kw)
        print(f"Added/updated keyword: '{args.add}' (id={kid})")
        return

    # ── Enable ──
    if args.enable:
        ok = db.update_keyword_enabled(args.enable, True)
        print(f"{'Enabled' if ok else 'Not found'}: '{args.enable}'")
        return

    # ── Disable ──
    if args.disable:
        ok = db.update_keyword_enabled(args.disable, False)
        print(f"{'Disabled' if ok else 'Not found'}: '{args.disable}'")
        return

    # ── Delete ──
    if args.delete:
        ok = db.delete_keyword(args.delete)
        print(f"{'Deleted' if ok else 'Not found'}: '{args.delete}'")
        return

    # ── Seed (default) ──
    if args.seed:
        existing = db.get_keywords(enabled_only=False)
        existing_names = {r["name"] for r in existing}
        count = 0
        for kw_data in DEFAULT_KEYWORDS:
            if kw_data["name"] not in existing_names:
                kw = Keyword(
                    name=kw_data["name"],
                    search_term=kw_data["search_term"],
                    category=kw_data.get("category", ""),
                )
                kid = db.upsert_keyword(kw)
                print(f"Inserted: '{kw_data['name']}' (id={kid})")
                count += 1
            else:
                print(f"Already exists: '{kw_data['name']}'")
        print(f"\nSeeded {count}/{len(DEFAULT_KEYWORDS)} new keyword(s).")
        return

    # No args — default to seed
    print("No action specified. Defaulting to --seed.")
    args.seed = True
    existing = db.get_keywords(enabled_only=False)
    existing_names = {r["name"] for r in existing}
    count = 0
    for kw_data in DEFAULT_KEYWORDS:
        if kw_data["name"] not in existing_names:
            kw = Keyword(
                name=kw_data["name"],
                search_term=kw_data["search_term"],
                category=kw_data.get("category", ""),
            )
            kid = db.upsert_keyword(kw)
            print(f"Inserted: '{kw_data['name']}' (id={kid})")
            count += 1
        else:
            print(f"Already exists: '{kw_data['name']}'")
    print(f"\nSeeded {count}/{len(DEFAULT_KEYWORDS)} new keyword(s).")


if __name__ == "__main__":
    main()
