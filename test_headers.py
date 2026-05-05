#!/usr/bin/env python3
"""Test: which header triggers Mercari anti-bot?"""
from playwright.sync_api import sync_playwright
import time

def test_with_headers(headers, label):
    p = sync_playwright().start()
    b = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-blink-features=AutomationControlled'])
    ctx = b.new_context(
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        viewport={"width": 1920, "height": 1080},
        locale="ja-JP",
        timezone_id="Asia/Tokyo",
        extra_http_headers=headers if headers else {},
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
    pg.goto('https://jp.mercari.com/search?keyword=Apple&sort=created_time&item_types=mercari', wait_until='domcontentloaded', timeout=15000)
    time.sleep(3)
    count = pg.evaluate("() => document.querySelectorAll('a[href*=\\\"/item/m\\\"]').length")
    print(f"  {label}: {count} items {'✓' if count > 0 else '✗'}")
    b.close()
    p.stop()

test_with_headers({}, 'no extra headers')
test_with_headers({'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9'}, 'Accept only')
test_with_headers({'Sec-Ch-Ua': '"Chromium";v="131", "Not-A.Brand";v="99"'}, 'Sec-Ch-Ua only')
test_with_headers({'Sec-Ch-Ua-Mobile': '?0'}, 'Sec-Ch-Ua-Mobile only')
test_with_headers({'Sec-Ch-Ua-Platform': '"macOS"'}, 'Sec-Ch-Ua-Platform only')
test_with_headers({'Upgrade-Insecure-Requests': '1'}, 'Upgrade-Insecure only')
test_with_headers({'Accept-Language': 'ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7'}, 'Accept-Language only')
