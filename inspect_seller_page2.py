#!/usr/bin/env python3
"""
Comprehensive inspection of Mercari Japan seller pages.
Strategy:
1. Go to search page, find item links, go to an item page, extract seller info
2. Navigate to seller page and fully inspect the HTML/API structure
"""
import sys
import json
import re
import time
sys.path.insert(0, '/home/logic126/workspace/mercari-hunter/src')

from playwright.sync_api import sync_playwright

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'

def main():
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
    ctx = browser.new_context(
        user_agent=UA,
        viewport={'width': 1920, 'height': 1080},
        locale='ja-JP',
        timezone_id='Asia/Tokyo',
        extra_http_headers={
            'Accept-Language': 'ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7',
        },
    )
    ctx.add_init_script('Object.defineProperty(navigator,"webdriver",{get:()=>false});delete navigator.__proto__.webdriver;')
    page = ctx.new_page()

    api_log = []
    page.on('response', lambda r: api_log.append(r.url) if 'api.mercari' in r.url else None)

    # ---- STEP 1: Go to search, find a real item, extract its seller ----
    print("=" * 70)
    print("STEP 1: Find a real seller via search results")
    print("=" * 70)

    page.goto('https://www.mercari.com/jp/search?keyword=Apple&sort=created_time', wait_until='domcontentloaded', timeout=30000)
    time.sleep(5)

    # Scroll to trigger lazy loading
    for _ in range(4):
        page.evaluate("window.scrollBy(0, 400)")
        time.sleep(0.5)

    # Find item links
    item_links = page.evaluate('''() => {
        const results = [];
        const anchors = document.querySelectorAll('a[href*="/items/"], a[href*="/item/"]');
        for (const a of anchors) {
            const href = a.href || '';
            if (href.match(/\\/items\\/m\\d+/) || href.match(/\\/item\\/m\\d+/)) {
                results.push({
                    href: href,
                    text: (a.textContent || '').trim().substring(0, 120),
                });
            }
        }
        return results;
    }''')
    print(f"\nFound {len(item_links)} item links on search page")
    for il in item_links[:5]:
        print(f"  {il['href']}")
        if il['text']:
            print(f"    {il['text'][:80]}")

    # Try to find seller username on the search page
    seller_links = page.evaluate('''() => {
        const results = [];
        const seen = new Set();
        // Look for /u/ or /user/profile/ patterns
        const allAnchors = document.querySelectorAll('a');
        for (const a of allAnchors) {
            const href = a.href || '';
            const m = href.match(/\\/u\\/([^\\/]+)/);
            if (m && !seen.has(m[1])) {
                seen.add(m[1]);
                results.push({username: m[1], href: href, text: (a.textContent||'').trim().substring(0,60)});
            }
        }
        return results;
    }''')
    print(f"\nFound {len(seller_links)} seller links on search page")
    for sl in seller_links[:5]:
        print(f"  {sl['username']}: {sl['text'][:50]}")

    # If no sellers on search, go to an item page
    target_seller = None
    if seller_links:
        target_seller = seller_links[0]['username']
        print(f"\nFound seller on search page: {target_seller}")
    elif item_links:
        print("\nNo seller links on search page. Going to first item page...")
        page.goto(item_links[0]['href'], wait_until='domcontentloaded', timeout=30000)
        time.sleep(3)

        # On item page, find seller info
        target_seller = page.evaluate('''() => {
            // Look for seller profile links on the item page
            const anchors = document.querySelectorAll('a');
            for (const a of anchors) {
                const href = a.href || '';
                const m = href.match(/\\/u\\/([^\\/]+)/);
                if (m) return m[1];
                const m2 = href.match(/\\/user\\/profile\\/([^\\/]+)/);
                if (m2) return m2[1];
            }
            return null;
        }''')
        if target_seller:
            print(f"Found seller on item page: {target_seller}")
        else:
            # Try from page content
            html = page.content()
            m = re.search(r'"/u/([^"]+)"', html)
            if m:
                target_seller = m.group(1)
                print(f"Found seller from HTML: {target_seller}")

    if not target_seller:
        # Try known sellers / common usernames
        for test_user in ['testuser', 'mercari']:
            api_log.clear()
            page.goto(f'https://www.mercari.com/jp/u/{test_user}', wait_until='domcontentloaded', timeout=15000)
            time.sleep(2)
            # Check if it's a valid page (not 404)
            title = page.title()
            if '404' not in title and 'not found' not in title.lower():
                target_seller = test_user
                print(f"Using test seller: {target_seller}")
                break

    if not target_seller:
        print("ERROR: Could not find a valid seller. Trying to extract from the __next_f data...")
        # Fallback: try to find any user from the initial HTML
        page.goto('https://www.mercari.com/jp/search?keyword=スマホ&sort=created_time', wait_until='domcontentloaded', timeout=30000)
        time.sleep(5)
        for _ in range(4):
            page.evaluate("window.scrollBy(0, 400)")
            time.sleep(0.5)

        html = page.content()
        # Look for any /u/username pattern
        m = re.search(r'["\']\/u\/([^"\']+)["\']', html)
        if m:
            target_seller = m.group(1)
            print(f"Found from HTML: {target_seller}")
        else:
            # Look at the __next_f data more carefully
            next_f = page.evaluate('''() => {
                const f = window.__next_f || [];
                return JSON.stringify(f).substring(0, 10000);
            }''')
            m = re.search(r'"/u/([^"]+)"', next_f)
            if m:
                target_seller = m.group(1)
                print(f"Found from __next_f: {target_seller}")

    print(f"\nUsing seller: {target_seller}")

    # ---- STEP 2: Navigate to seller profile page ----
    print("\n" + "=" * 70)
    print("STEP 2: Inspect seller profile page")
    print("=" * 70)

    api_log.clear()
    seller_url = f"https://www.mercari.com/jp/u/{target_seller}"
    print(f"\nNavigating to: {seller_url}")
    page.goto(seller_url, wait_until='domcontentloaded', timeout=30000)
    time.sleep(3)

    final_url = page.url
    print(f"Final URL: {final_url}")
    title = page.title()
    print(f"Page title: {title}")

    # Scroll to trigger lazy loading
    for _ in range(5):
        page.evaluate("window.scrollBy(0, 400)")
        time.sleep(0.5)

    # ---- STEP 3: Analyze API requests ----
    print("\n--- MERCARI API REQUESTS ---")
    for url in api_log:
        print(f"  {url}")

    # ---- STEP 4: DOM structure ----
    print("\n--- DOM STRUCTURE ---")
    dom = page.evaluate('''() => {
        const result = {};

        // Item links on the seller page
        result.item_links = [];
        const itemAnchors = document.querySelectorAll('a[href*="/items/"], a[href*="/item/"]');
        for (const a of itemAnchors) {
            result.item_links.push({
                href: a.href,
                text: (a.textContent || '').trim().substring(0, 120),
            });
        }

        // data-testid elements
        result.testids = [];
        for (const el of document.querySelectorAll('[data-testid]')) {
            result.testids.push({
                tag: el.tagName.toLowerCase(),
                testid: el.getAttribute('data-testid'),
                text: (el.textContent || '').trim().substring(0, 100),
            });
        }

        // data-location elements
        result.locations = [];
        for (const el of document.querySelectorAll('[data-location]')) {
            result.locations.push({
                tag: el.tagName.toLowerCase(),
                location: el.getAttribute('data-location'),
                text: (el.textContent || '').trim().substring(0, 100),
            });
        }

        // CSS classes
        result.classes = [];
        const allEls = document.querySelectorAll('*');
        const classSet = new Set();
        for (const el of Array.from(allEls).slice(0, 500)) {
            if (el.className && typeof el.className === 'string') {
                for (const c of el.className.split(' ')) {
                    if (c && (c.includes('Item') || c.includes('item') || c.includes('Profile') || c.includes('profile') || c.includes('List') || c.includes('list') || c.includes('Card') || c.includes('card') || c.includes('Seller') || c.includes('seller') || c.startsWith('sc-') || c.startsWith('C-'))) {
                        classSet.add(c);
                    }
                }
            }
        }
        result.classes = Array.from(classSet).slice(0, 80);

        // Extract seller info from the page
        result.seller_info = window.location.href;

        // Check for images with item info
        result.item_images = [];
        for (const img of document.querySelectorAll('img')) {
            if (img.src && (img.src.includes('mercari') || img.src.includes('item') || img.src.includes('res')) ) {
                result.item_images.push({
                    src: img.src.substring(0, 200),
                    alt: img.alt || '',
                });
            }
        }

        return result;
    }''')

    print(f"\nItem links: {len(dom['item_links'])}")
    for il in dom['item_links'][:15]:
        print(f"  {il['href']}")
        if il['text']:
            print(f"    → {il['text'][:80]}")

    print(f"\ndata-testid elements ({len(dom['testids'])}):")
    for t in dom['testids']:
        print(f"  <{t['tag']}> data-testid=\"{t['testid']}\" → {t['text'][:60]}")

    print(f"\ndata-location elements ({len(dom['locations'])}):")
    for loc in dom['locations']:
        print(f"  <{loc['tag']}> data-location=\"{loc['location']}\" → {loc['text'][:60]}")

    print(f"\nCSS classes ({len(dom['classes'])}):")
    for c in dom['classes']:
        print(f"  {c}")

    print(f"\nItem images ({len(dom['item_images'])}):")
    for img in dom['item_images'][:10]:
        print(f"  src={img['src'][:150]} alt=\"{img['alt']}\"")

    # ---- STEP 5: Check RSC hydration data for seller items ----
    print("\n--- NEXT.JS RSC HYDRATION DATA ---")
    rsc_data = page.evaluate('''() => {
        const f = window.__next_f || [];
        const allStr = JSON.stringify(f);
        // Look for item-related data
        const result = {};

        // Search for item IDs
        const itemIds = allStr.match(/m\d{10,}/g);
        result.item_ids = itemIds ? Array.from(new Set(itemIds)).slice(0, 20) : [];

        // Search for seller info
        const sellerMatches = allStr.match(/"seller[^}]*}/g);
        result.seller_json = sellerMatches ? sellerMatches.slice(0, 3) : [];

        // Search for profile data
        const profileMatches = allStr.match(/"profile[^}]*}/g);
        result.profile_json = profileMatches ? profileMatches.slice(0, 3) : [];

        // Search for price patterns
        const prices = allStr.match(/"price":\s*\d+/g);
        result.prices = prices ? prices.slice(0, 10) : [];

        // Search for name/title patterns
        const names = allStr.match(/"name":\s*"[^"]{5,}"/g);
        result.names = names ? names.slice(0, 10) : [];

        // Look for complete item objects
        const items = allStr.match(/\{[^{}]*"id"[^{}]*"name"[^{}]*"price"[^{}]*\}/g);
        result.items = items ? items.slice(0, 3) : [];

        // Full JSON string (truncated)
        result.full_length = allStr.length;
        result.preview = allStr.substring(0, 2000);

        return result;
    }''')

    print(f"Hydration data length: {rsc_data['full_length']}")
    print(f"Item IDs found: {rsc_data['item_ids'][:10]}")
    print(f"Prices: {rsc_data['prices']}")
    print(f"Names: {rsc_data['names'][:5]}")
    if rsc_data.get('seller_json'):
        for sj in rsc_data['seller_json']:
            print(f"Seller JSON: {sj[:200]}")
    if rsc_data.get('profile_json'):
        for pj in rsc_data['profile_json']:
            print(f"Profile JSON: {pj[:200]}")
    if rsc_data.get('items'):
        for it in rsc_data['items']:
            print(f"Item object: {it[:200]}")

    # ---- STEP 6: Save HTML for reference ----
    html = page.content()
    with open('/tmp/mercari_seller_page_final.html', 'w') as f:
        f.write(html[:80000])
    print(f"\nSaved {len(html)} chars to /tmp/mercari_seller_page_final.html")

    # ---- STEP 7: Screenshot ----
    page.screenshot(path='/tmp/mercari_seller_page2.png')
    print("Screenshot saved to /tmp/mercari_seller_page2.png")

    # ---- STEP 8: Try to get a real user_id and test the API ----
    print("\n" + "=" * 70)
    print("STEP 3: Test API endpoints with real user_id")
    print("=" * 70)

    # Extract user_id from the hydration data
    user_id = page.evaluate('''() => {
        const f = window.__next_f || [];
        const allStr = JSON.stringify(f);

        // Try various patterns for user_id
        const patterns = [
            /"user_id":\s*(\d+)/,
            /"userId":\s*(\d+)/,
            /"id":\s*(\d{10,})/,
        ];
        for (const pat of patterns) {
            const match = allStr.match(pat);
            if (match) {
                return match[1];
            }
        }

        // Try from the page HTML
        const html = document.documentElement.innerHTML;
        for (const pat of patterns) {
            const match = html.match(pat);
            if (match) {
                return match[1];
            }
        }

        return null;
    }''')

    if user_id:
        print(f"Extracted user_id: {user_id}")

        # Test the API endpoint
        api_url = f"https://api.mercari.jp/items/get_items?seller_id={user_id}&limit=5&with_auction=true&status=on_sale,trading,sold_out"
        print(f"\nTesting: {api_url}")

        try:
            resp = page.request.get(api_url)
            body = resp.body().decode('utf-8')
            print(f"  Status: {resp.status}")
            print(f"  Body: {body[:2000]}")
        except Exception as e:
            print(f"  Error: {e}")

        # Try with different params
        api_url2 = f"https://api.mercari.jp/users/get_profile?user_id={user_id}&_user_format=profile"
        print(f"\nTesting: {api_url2}")
        try:
            resp = page.request.get(api_url2)
            body = resp.body().decode('utf-8')
            print(f"  Status: {resp.status}")
            print(f"  Body: {body[:2000]}")
        except Exception as e:
            print(f"  Error: {e}")

        # Check if API needs cookies/auth
        cookies = ctx.cookies()
        print(f"\nCookies ({len(cookies)}):")
        for c in cookies[:5]:
            print(f"  {c['name']}={c['value'][:20]}... domain={c['domain']}")
    else:
        print("Could not extract user_id from page")

    # ---- STEP 9: Dump the full RSC data to file ----
    full_rsc = page.evaluate('() => JSON.stringify(window.__next_f)')
    with open('/tmp/mercari_rsc_data.json', 'w') as f:
        f.write(full_rsc[:50000])
    print(f"\nSaved {len(full_rsc)} chars of RSC data to /tmp/mercari_rsc_data.json")

    page.close()
    browser.close()
    p.stop()

if __name__ == '__main__':
    main()
