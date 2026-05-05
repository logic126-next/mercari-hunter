#!/usr/bin/env python3
"""Test: Explore Mercari seller page structure."""
import json, re
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1920, "height": 1080})
    page = context.new_page()

    page.goto("https://www.mercari.comjp/search?keyword=iPhone", timeout=30000)
    page.wait_for_timeout(3000)

    html = page.content()

    # Find seller profile links - Mercari JP uses /u/{username}
    seller_urls = set(re.findall(r'href=["\x27](/u/[^\x22\x27]+)["\x27]', html))
    print(f"Found {len(seller_urls)} seller URL patterns")
    for url in sorted(seller_urls)[:10]:
        print(f"  {url}")

    # Check for seller info in search results
    # Try to find seller names near item links
    seller_spans = re.findall(r'class=["\x27][^"\x27]*seller[^"\x27]*["\x27]', html, re.IGNORECASE)
    print(f"\nSeller-related classes: {set(seller_spans[:10])}")

    browser.close()
