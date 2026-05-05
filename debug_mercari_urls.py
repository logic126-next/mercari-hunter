#!/usr/bin/env python3
"""Debug Mercari item URL patterns."""
from playwright.sync_api import sync_playwright
import time
import re

p = sync_playwright().start()
b = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
ctx = b.new_context(
    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    locale='ja-JP', timezone_id='Asia/Tokyo',
)
page = ctx.new_page()
page.goto('https://jp.mercari.com/search?brand_id=3272&sort=created_time&item_types=mercari', wait_until='domcontentloaded', timeout=15000)
time.sleep(5)

print(f"Title: {page.title()}")
print(f"URL: {page.url}")

# Check different selectors
for sel in ['a[href="/item/m"]', 'a[href*="/item/m"]', 'a[href*="/item/"', 'a[class*="item"]', 'a[class*="card"]', 'a[href*="item"]']:
    count = len(page.query_selector_all(sel))
    print(f'{sel}: {count}')

# Extract hrefs from HTML
html = page.content()
hrefs = re.findall(r'href=["\x27]([^"\x27]*)["\x27]', html)
item_hrefs = [h for h in hrefs if 'item' in h.lower()]
print(f'\nItem-related hrefs ({len(item_hrefs)}):')
for h in item_hrefs[:20]:
    print(f'  {h}')

# Check page text
texts = page.evaluate("""() => {
    const els = document.querySelectorAll('a');
    return Array.from(els).slice(0, 30).map(a => ({href: a.href, text: a.textContent.trim().substring(0,60)}));
}""")
print('\nFirst 30 links:')
for t in texts:
    print(f'  {t["text"][:60]} -> {t["href"][:80]}')

b.close()
p.stop()
