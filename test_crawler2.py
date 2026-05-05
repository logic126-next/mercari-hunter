#!/usr/bin/env python3
import sys, time
sys.path.insert(0, 'src')
from crawler import MercariCrawler

c = MercariCrawler({'max_retries': 3})
c._ensure_browser()
page = c._context.new_page()
page.goto('https://jp.mercari.com/search?keyword=Apple&sort=created_time&item_types=mercari',
          wait_until='domcontentloaded', timeout=30000)

# Wait 3s for CSR
time.sleep(3)

# Check total links
all_links = page.evaluate("""() => {
    const all = document.querySelectorAll('a');
    return all.length;
}""")
print(f'Total <a> tags: {all_links}')

# Check for item links with different selectors
for sel in [
    'a[href*="/item/m"]',
    'a[href*="/item/"]',
    '.css-1',
    '.Card',
    '.item',
    '.product',
]:
    try:
        count = len(page.query_selector_all(sel))
        print(f'  {sel}: {count}')
    except Exception as e:
        print(f'  {sel}: error - {e}')

# Dump all links with 'mercari' in URL
links = page.evaluate("""() => {
    const all = document.querySelectorAll('a');
    return Array.from(all).map(a => a.href).filter(h => h.includes('mercari') && h.includes('/item')).slice(0, 10);
}""")
print(f'Item links found: {len(links)}')
for l in links:
    print(f'  {l}')

page.close()
c.close()
