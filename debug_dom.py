#!/usr/bin/env python3
"""Debug Mercari DOM structure."""
import asyncio
import sys
sys.path.insert(0, 'src')
from playwright.async_api import async_playwright

async def test():
    p = await async_playwright().start()
    browser = await p.chromium.launch(
        headless=True,
        args=['--disable-blink-features=AutomationControlled'],
    )
    page = await browser.new_page()

    await page.goto(
        'https://jp.mercari.com/items?item_name=Apple&sort=created_time&item_types=mercari',
        wait_until='domcontentloaded',
        timeout=30000,
    )

    # Wait progressively
    for t in [3, 6, 10, 15]:
        await asyncio.sleep(t)
        all_links = await page.query_selector_all('a')
        item_links = await page.query_selector_all('a[href*="/item/"]')
        cards = await page.query_selector_all('[class*="Card"], [class*="card"], [class*="Item"]')
        html_len = len(await page.content())
        print(f'  After {t}s: total_a={len(all_links)}, item_a={len(item_links)}, cards={len(cards)}, html={html_len}')

    # Print ALL links that have /item/ anywhere
    result = await page.evaluate("""() => {
        const all = Array.from(document.querySelectorAll('a'));
        const itemLinks = all.filter(a => a.href.includes('/item/'));
        return itemLinks.slice(0, 15).map(a => ({
            href: a.href,
            text: a.textContent.trim().substring(0, 120)
        }));
    }""")
    print(f"\nFound {len(result)} /item/ links:")
    for l in result:
        print(f"  {l['href'][:130]}")
        print(f"    text: {l['text'][:100]}")

    # Also check all link classes to find item cards
    all_classes = await page.evaluate("""() => {
        const els = Array.from(document.querySelectorAll('a'));
        const classes = {};
        for (const el of els) {
            const c = el.className;
            if (c && typeof c === 'string') {
                for (const cls of c.split(' ')) {
                    if (cls.includes('css-') || cls.includes('C-') || cls.length > 3) {
                        classes[cls] = (classes[cls] || 0) + 1;
                    }
                }
            }
        }
        return Object.entries(classes).sort((a,b) => b[1] - a[1]).slice(0, 30);
    }""")
    print(f"\nCSS classes on links:")
    for cls, count in all_classes[:20]:
        print(f"  {cls}: {count}")

    # Save HTML for inspection
    html = await page.content()
    with open('/tmp/mercari.html', 'w') as f:
        f.write(html)
    print(f"\nSaved {len(html)} chars to /tmp/mercari.html")

    await browser.close()
    await p.stop()

asyncio.run(test())
