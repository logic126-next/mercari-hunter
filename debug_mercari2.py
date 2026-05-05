#!/usr/bin/env python3
"""Debug Mercari DOM structure - wait longer."""
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
    context = await browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
        viewport={'width': 1920, 'height': 1080},
        locale='ja-JP',
        timezone_id='Asia/Tokyo',
        extra_http_headers={
            'Accept-Language': 'ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7',
        },
    )
    page = await context.new_page()

    # Use domcontentloaded + extended wait
    print("Navigating...")
    await page.goto(
        'https://jp.mercari.com/items?item_name=Apple&sort=created_time&item_types=mercari',
        wait_until='domcontentloaded',
        timeout=30000,
    )

    # Wait progressively for RSC streaming
    for wait_time in [2, 5, 8, 12, 15, 20]:
        await asyncio.sleep(wait_time)
        links = await page.query_selector_all('a[href*="/item/m"]')
        total_a = await page.query_selector_all('a')
        html_len = len(await page.content())
        print(f'  After {wait_time}s: item_links={len(links)}, total_a={len(total_a)}, html_len={html_len}')
        if len(links) > 0:
            break

    # Check URL pattern - maybe it's /items/ not /item/m
    all_links = await page.evaluate("""() => {
        const all = Array.from(document.querySelectorAll('a'));
        return all.map(a => a.href).slice(0, 60);
    }""")
    item_links = [l for l in all_links if 'item' in l.lower() and 'mercari' in l.lower()]
    print(f"\nItem-like links: {len(item_links)}")
    for l in item_links[:10]:
        print(f'  {l}')

    # Check page title and current URL
    print(f"\nTitle: {await page.title()}")
    print(f"URL: {page.url}")

    # Scroll and check
    print("\nScrolling...")
    for _ in range(3):
        await page.evaluate("window.scrollBy(0, 800)")
        await asyncio.sleep(1)

    await asyncio.sleep(3)
    links2 = await page.query_selector_all('a[href*="/item/m"]')
    print(f'After scroll: {len(links2)} item links')

    # Check all links again
    all_links2 = await page.evaluate("""() => {
        const all = Array.from(document.querySelectorAll('a'));
        return all.map(a => ({href: a.href, text: a.textContent.trim().substring(0, 80)}));
    }""")
    print(f"\nTotal links after scroll: {len(all_links2)}")
    for l in all_links2[-20:]:
        if l['text'].strip():
            print(f'  [{l["href"][:120]}] | {l["text"][:70]}')

    await browser.close()
    await p.stop()

asyncio.run(test())
