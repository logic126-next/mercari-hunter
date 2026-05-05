#!/usr/bin/env python3
"""Inspect Mercari Japan seller page structure using Playwright sync API."""
import sys
import json
import re
import time
sys.path.insert(0, '/home/logic126/workspace/mercari-hunter/src')

from playwright.sync_api import sync_playwright

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
]

def inspect_seller_page():
    p = sync_playwright().start()
    browser = p.chromium.launch(
        headless=True,
        args=['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-dev-shm-usage'],
    )
    context = browser.new_context(
        user_agent=USER_AGENTS[0],
        viewport={"width": 1920, "height": 1080},
        locale="ja-JP",
        timezone_id="Asia/Tokyo",
        extra_http_headers={
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7',
        },
    )
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => false });
        delete navigator.__proto__.webdriver;
    """)

    page = context.new_page()

    # ---- Step 1: Find sellers from a search page ----
    print("=" * 60)
    print("STEP 1: Find seller usernames from search results")
    print("=" * 60)

    # Intercept network to find API calls
    api_requests = []
    def on_response(response):
        url = response.url
        if 'api.mercari' in url or '/graphql' in url:
            api_requests.append(url)

    page.on("response", on_response)

    # Search page — look for sellers
    search_url = 'https://www.mercari.com/jp/search?keyword=iPhone&sort=created_time'
    print(f"Loading: {search_url}")
    page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(5)

    # Extract seller usernames from search results
    sellers = page.evaluate('''() => {
        const results = [];
        const seen = new Set();
        // Try multiple selectors for seller links
        const allLinks = document.querySelectorAll('a');
        for (const link of allLinks) {
            const href = link.href || '';
            const match = href.match(/\\.mercari\\.com\\/[\\w\\/]+\\/(?:user\\/profile\\/|u\\/)([^\\/]+)/);
            if (match && !seen.has(match[1])) {
                seen.add(match[1]);
                results.push({
                    username: match[1],
                    url: href,
                    text: (link.textContent || '').trim().substring(0, 60),
                });
            }
        }
        return results.slice(0, 20);
    }''')

    if sellers:
        print(f"Found {len(sellers)} sellers on search page:")
        for s in sellers[:10]:
            print(f"  - {s['username']}: {s['text'][:50]}")
    else:
        print("No seller links found on search page.")

    # ---- Step 2: Navigate to a seller page ----
    print("\n" + "=" * 60)
    print("STEP 2: Inspect seller profile page")
    print("=" * 60)

    # Try to go to a seller page - pick one if found, else try a known pattern
    target_username = sellers[0]['username'] if sellers else 'mercari_official'
    seller_url = f"https://www.mercari.com/jp/u/{target_username}"
    print(f"\nNavigating to: {seller_url}")

    api_requests.clear()

    page.goto(seller_url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)

    # Check if redirected
    final_url = page.url
    print(f"Final URL after redirect: {final_url}")

    # Parse the actual user ID from the URL
    actual_user = page.evaluate('''() => {
        // Try to find user profile info
        const urlParts = window.location.pathname.split('/');
        return {
            pathname: window.location.pathname,
            title: document.title,
        };
    }''')
    print(f"Page info: pathname={actual_user['pathname']}, title={actual_user['title']}")

    # Scroll to load lazy content
    for _ in range(3):
        page.evaluate("window.scrollBy(0, 500)")
        time.sleep(0.5)

    # ---- Step 3: Capture API requests ----
    print("\n--- MERCARI API REQUESTS ---")
    for url in api_requests:
        print(f"  {url}")

    # ---- Step 4: Save HTML for analysis ----
    html = page.content()
    with open('/tmp/mercari_seller_page.html', 'w') as f:
        f.write(html[:60000])
    print(f"\nSaved {len(html)} chars HTML to /tmp/mercari_seller_page.html")

    # ---- Step 5: DOM structure analysis ----
    print("\n--- DOM STRUCTURE ANALYSIS ---")
    dom = page.evaluate('''() => {
        const result = {};

        // Root-level elements in body
        result.body_children = [];
        for (const child of document.body.children) {
            result.body_children.push({
                tag: child.tagName,
                id: child.id || '',
                classes: typeof child.className === 'string' ? child.className.split(' ').filter(c => c.length > 0).join(' ') : '',
            });
        }

        // Find item listing links
        result.item_links = [];
        const itemAnchors = document.querySelectorAll('a[href*="/items/"], a[href*="/item/"]');
        for (const a of itemAnchors) {
            result.item_links.push({
                href: a.href,
                text: (a.textContent || '').trim().substring(0, 100),
            });
        }

        // CSS classes on the page that look relevant
        result.relevant_classes = [];
        const allEls = document.querySelectorAll('*');
        const classSet = new Set();
        for (const el of Array.from(allEls).slice(0, 500)) {
            if (el.className && typeof el.className === 'string') {
                for (const c of el.className.split(' ')) {
                    if (c && (c.includes('Item') || c.includes('item') || c.includes('Seller') || c.includes('seller') || c.includes('Profile') || c.includes('profile') || c.includes('List') || c.includes('list') || c.includes('Card') || c.includes('card') || c.startsWith('sc-') || c.startsWith('C-'))) {
                        classSet.add(c);
                    }
                }
            }
        }
        result.relevant_classes = Array.from(classSet).slice(0, 60);

        // data-* attributes
        result.data_attrs = [];
        for (const el of Array.from(allEls).slice(0, 300)) {
            if (el.attributes) {
                for (const attr of el.attributes) {
                    if (attr.name.startsWith('data-')) {
                        result.data_attrs.push({
                            tag: el.tagName.toLowerCase(),
                            attr: attr.name,
                            value: attr.value.substring(0, 120),
                        });
                    }
                }
            }
        }

        // data-testid elements
        result.testids = [];
        const testidEls = document.querySelectorAll('[data-testid]');
        for (const el of testidEls) {
            result.testids.push({
                tag: el.tagName.toLowerCase(),
                testid: el.getAttribute('data-testid'),
                text: (el.textContent || '').trim().substring(0, 80),
            });
        }

        // data-location elements
        result.locations = [];
        const locEls = document.querySelectorAll('[data-location]');
        for (const el of locEls) {
            result.locations.push({
                tag: el.tagName.toLowerCase(),
                location: el.getAttribute('data-location'),
                text: (el.textContent || '').trim().substring(0, 80),
            });
        }

        return result;
    }''')

    print("\nBody children:")
    for bc in dom['body_children']:
        cls = f" class='{bc['classes']}'" if bc['classes'] else ''
        print(f"  <{bc['tag']}{cls}>")

    print(f"\nItem links found: {len(dom['item_links'])}")
    for il in dom['item_links'][:10]:
        print(f"  {il['href']}")
        if il['text']:
            print(f"    → {il['text'][:60]}")

    print(f"\nRelevant CSS classes ({len(dom['relevant_classes'])}):")
    for c in dom['relevant_classes']:
        print(f"  {c}")

    print(f"\ndata-testid elements ({len(dom['testids'])}):")
    for t in dom['testids']:
        print(f"  <{t['tag']}> data-testid=\"{t['testid']}\" → {t['text'][:50]}")

    print(f"\ndata-location elements ({len(dom['locations'])}):")
    for loc in dom['locations'][:20]:
        print(f"  <{loc['tag']}> data-location=\"{loc['location']}\" → {loc['text'][:50]}")

    print(f"\ndata-* attributes ({len(dom['data_attrs'])}):")
    for da in dom['data_attrs'][:20]:
        print(f"  <{da['tag']}> {da['attr']}=\"{da['value']}\"")

    # ---- Step 6: Check __NEXT_DATA__ and hydration ----
    print("\n--- NEXT.JS HYDRATION DATA ---")
    hydration = page.evaluate('''() => {
        const result = {};

        // Check for __NEXT_DATA__
        const nextData = document.getElementById('__NEXT_DATA__');
        if (nextData) {
            try {
                const data = JSON.parse(nextData.textContent);
                result.has_next_data = true;
                result.props_preview = JSON.stringify(data.props).substring(0, 3000);
            } catch(e) {
                result.has_next_data = true;
                result.preview = nextData.textContent.substring(0, 1000);
            }
        } else {
            result.has_next_data = false;
        }

        // Check window globals
        for (const key of Object.keys(window)) {
            if (key.startsWith('__')) {
                try {
                    result[key] = JSON.stringify(window[key]).substring(0, 300);
                } catch(e) {
                    result[key] = `[${typeof window[key]}]`;
                }
            }
        }

        return result;
    }''')

    if hydration.get('has_next_data'):
        print("Found __NEXT_DATA__ hydration data")
        if hydration.get('props_preview'):
            # Parse to find seller-related data
            try:
                props = json.loads(hydration['props_preview'])
                print(f"Props keys: {list(props.keys())[:20]}")
            except:
                print(f"props_preview: {hydration['props_preview'][:500]}")
        elif hydration.get('preview'):
            print(f"preview: {hydration['preview'][:500]}")
    else:
        print("No __NEXT_DATA__ found")

    for k, v in hydration.items():
        if k.startswith('__'):
            print(f"  window.{k}: {str(v)[:300]}")

    # ---- Step 7: Screenshot ----
    page.screenshot(path='/tmp/mercari_seller_screenshot.png')
    print(f"\nScreenshot saved to /tmp/mercari_seller_screenshot.png")

    # ---- Step 8: Try accessing seller items API directly ----
    print("\n" + "=" * 60)
    print("STEP 3: Try direct API calls for seller items")
    print("=" * 60)

    # First, get the actual user_id from the profile page
    user_id = page.evaluate('''() => {
        // Look for user ID in the page
        const html = document.documentElement.innerHTML;

        // Pattern: "user_id":number
        const userIdMatch = html.match(/"user_id":\\s*(\\d+)/);
        if (userIdMatch) return userIdMatch[1];

        // Pattern: userId in JSON
        const uidMatch = html.match(/"userId":\\s*(\\d+)/);
        if (uidMatch) return uidMatch[1];

        return null;
    }''')

    if user_id:
        print(f"Extracted user_id from page: {user_id}")

        # Try the get_items API endpoint with the real user_id
        api_url = f"https://api.mercari.jp/items/get_items?seller_id={user_id}&limit=5&with_auction=true&status=on_sale,trading,sold_out"
        print(f"\nTrying API: {api_url}")

        try:
            response = page.request.get(api_url)
            body = response.body().decode('utf-8')
            status = response.status
            print(f"  Status: {status}")
            print(f"  Body: {body[:1000]}")
        except Exception as e:
            print(f"  Error: {e}")

        # Also try get_profile
        profile_url = f"https://api.mercari.jp/users/get_profile?user_id={user_id}&_user_format=profile"
        print(f"\nTrying profile API: {profile_url}")
        try:
            response = page.request.get(profile_url)
            body = response.body().decode('utf-8')
            status = response.status
            print(f"  Status: {status}")
            print(f"  Body: {body[:1000]}")
        except Exception as e:
            print(f"  Error: {e}")
    else:
        print("Could not extract user_id from page")

    page.close()
    browser.close()
    p.stop()

if __name__ == '__main__':
    inspect_seller_page()
