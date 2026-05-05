#!/usr/bin/env python3
import sys, time
sys.path.insert(0, 'src')
from crawler import MercariCrawler

c = MercariCrawler({'max_retries': 3})
c._ensure_browser()
page = c._context.new_page()
t0 = time.time()
page.goto('https://jp.mercari.com/search?keyword=Apple&sort=created_time&item_types=mercari',
          wait_until='domcontentloaded', timeout=30000)
print(f'Goto done in {time.time()-t0:.1f}s')

c._human_scroll(page)
print('Scroll done')

count = 0
for i in range(1, 11):
    time.sleep(0.5)
    try:
        count = page.evaluate("() => document.querySelectorAll('a[href*=\\\"/item/m\\\"]').length")
    except Exception as e:
        print(f'  eval error: {e}')
    print(f'  poll {i}: {count} items')
    if count > 0:
        break

page.close()
c.close()
print(f'Final: {count}')
