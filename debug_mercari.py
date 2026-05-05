#!/usr/bin/env python3
"""Debug Mercari DOM structure."""
import asyncio
import sys
sys.path.insert(0, 'src')
from playwright.async_api import async_playwright

async def test():
    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page()
    await page.goto(
        'https://jp.mercari.com/items?item_name=Apple&sort=created_time&item_types=mercari',
        wait_until='domcontentloaded',
        timeout=30000,
    )
    await asyncio.sleep(5)

    # Take snapshot to save
    html = await page.content()
    with open('/tmp/mercari_debug.html', 'w') as f:
        f.write(html[:30000])
    print(f'HTML length: {len(html)}')

    # Check if items are rendered as text or images
    item_count = await page.query_selector_all('a')
    print(f'Total <a> tags: {len(item_count)}')

    # Print first 20 links with href
    links_js = """
    (() => {
        const all = Array.from(document.querySelectorAll('a'));
        return all.slice(0, 25).map(a => ({
            href: a.href,
            text: a.textContent.trim().substring(0, 100)
        }));
    })()
    """
    links = await page.evaluate(links_js)
    for l in links[:20]:
        href = l['href']
        text = l['text']
        if 'item' in href or text.strip():
            print(f'  [{href[:120]}]')
            print(f'    text: {text[:80]}')

    # Check CSS classes on the page
    classes_js = """
    (() => {
        const els = Array.from(document.querySelectorAll('[class]'));
        const classes = new Set();
        for (const el of els.slice(0, 200)) {
            const cls = el.className;
            if (typeof cls === 'string') {
                for (const c of cls.split(' ')) {
                    if (c.startsWith('css-') || c.startsWith('C-')) {
                        classes.add(c);
                    }
                }
            }
        }
        return Array.from(classes).slice(0, 50);
    })()
    """
    classes = await page.evaluate(classes_js)
    print(f'\nCSS modules found: {classes[:20]}')

    await browser.close()
    await p.stop()

asyncio.run(test())
