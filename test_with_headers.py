#!/usr/bin/env python3
"""Test: with extra_http_headers (like crawler)."""
from playwright.sync_api import sync_playwright
import time

p = sync_playwright().start()
b = p.chromium.launch(headless=True, args=[
    '--disable-blink-features=AutomationControlled',
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-infobars',
    '--no-sandbox',
    '--disable-dev-shm-usage',
])
ctx = b.new_context(
    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    viewport={"width": 1920, "height": 1080},
    locale="ja-JP",
    timezone_id="Asia/Tokyo",
    extra_http_headers={
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7',
        'Sec-Ch-Ua': '"Chromium";v="131", "Not-A.Brand";v="99"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"macOS"',
        'Upgrade-Insecure-Requests': '1',
    },
)
ctx.add_init_script("""
Object.defineProperty(navigator, 'webdriver', {get: () => false});
delete navigator.__proto__.webdriver;
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
Object.defineProperty(navigator, 'languages', {get: () => ['ja-JP','ja','en-US','en']});
Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 0});
window.chrome = {runtime: {}};
""")
pg = ctx.new_page()
pg.goto('https://jp.mercari.com/search?keyword=Apple&sort=created_time&item_types=mercari', wait_until='domcontentloaded', timeout=30000)

for i in range(1, 8):
    time.sleep(1)
    count = pg.evaluate("() => document.querySelectorAll('a[href*=\\\"/item/m\\\"]').length")
    html_len = len(pg.content())
    print(f"  {i}s: items={count}, html_len={html_len}")
    if count > 0:
        break

print(f'Final: {count} items')
b.close()
p.stop()
