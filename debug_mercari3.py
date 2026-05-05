#!/usr/bin/env python3
"""Test Mercari with max stealth."""
from playwright.sync_api import sync_playwright
import time

p = sync_playwright().start()
b = p.chromium.launch(headless=True, args=[
    '--no-sandbox',
    '--disable-blink-features=AutomationControlled',
    '--disable-dev-shm-usage',
])
ctx = b.new_context(
    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    viewport={"width": 1920, "height": 1080},
    locale="ja-JP",
    timezone_id="Asia/Tokyo",
)
ctx.add_init_script("""
Object.defineProperty(navigator, 'webdriver', {get: () => false});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
Object.defineProperty(navigator, 'languages', {get: () => ['ja-JP','ja','en-US','en']});
Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 0});
window.chrome = {runtime: {}};
delete navigator.__proto__.webdriver;
""")
pg = ctx.new_page()
pg.goto('https://jp.mercari.com/search?keyword=Apple&sort=created_time&item_types=mercari', wait_until='domcontentloaded', timeout=30000)

# Wait for CSR
for i in range(1, 11):
    time.sleep(1)
    title = pg.title()
    count = pg.evaluate("() => document.querySelectorAll('a[href*=\\\"/item/m\\\"]').length")
    html_len = len(pg.content())
    print(f"  {i}s: title={title}, items={count}, html_len={html_len}")
    if count > 0:
        break

print(f"\nFinal: {count} items, title={pg.title()}")
b.close()
p.stop()
