"""Mercari Bargain Hunter - Playwright-based Crawler with Anti-Detection

Sync API — runs directly in main process. Reuses Chromium across scan cycles.
Anti-detection: UA rotation, fixed viewport, stealth init scripts.
Pagination: cursor-based (page_token=v1:N), up to max_items per keyword.
"""
import random
import re
import time
import urllib.parse


USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
]


class MercariCrawler:
    """Crawl mercari.jp — sync API, reuses a single Chromium instance.

    Supports cursor pagination (page_token=v1:N) for deep pagination.
    Defaults to latest-first sort (sort=created_time), capped at max_items.
    """

    def __init__(self, config: dict):
        self.config = config
        self.max_retries = config.get('max_retries', 3)
        self.max_items = config.get('max_items', 100)  # per keyword per cycle
        self._browser = None
        self._context = None
        self._p = None
        self._ua = random.choice(USER_AGENTS)
        self._last_crawl_time = 0

    @staticmethod
    def _jitter(low: float, high: float) -> float:
        return random.uniform(low, high)

    def _enforce_crawl_gap(self, min_gap: float = 7.0):
        now = time.monotonic()
        elapsed = now - self._last_crawl_time
        if elapsed < min_gap and self._last_crawl_time > 0:
            wait = min_gap - elapsed + self._jitter(0, 2.0)
            time.sleep(wait)
        self._last_crawl_time = time.monotonic()

    def _ensure_browser(self):
        """Launch Chromium if not already running."""
        from playwright.sync_api import sync_playwright

        if self._browser is not None:
            return

        self._p = sync_playwright().start()
        self._browser = self._p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-first-run',
                '--no-default-browser-check',
                '--disable-infobars',
                '--no-sandbox',
                '--disable-dev-shm-usage',
            ],
        )
        vw = 1920
        vh = 1080

        self._context = self._browser.new_context(
            user_agent=self._ua,
            viewport={"width": vw, "height": vh},
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            extra_http_headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7',
                'Sec-Ch-Ua': '"Chromium";v="131", "Not-A.Brand";v="99"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"Windows"' if 'Windows' in self._ua else '"macOS"',
            },
        )
        self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            delete navigator.__proto__.webdriver;
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['ja-JP','ja','en-US','en'] });
            Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });
            window.chrome = { runtime: {} };
        """)

    def _human_scroll(self, page):
        """Human-like scrolling to trigger lazy-loaded content."""
        for _ in range(random.randint(2, 4)):
            offset = random.randint(200, 600)
            page.evaluate(f"window.scrollBy(0, {offset})")
            time.sleep(self._jitter(0.3, 1.2))

    def _reset_browser(self):
        """Kill browser — next crawl will relaunch."""
        try:
            if self._context:
                self._context.close()
        except Exception:
            pass
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._p:
                self._p.stop()
        except Exception:
            pass
        self._browser = None
        self._context = None
        self._p = None

    def _extract_items_from_page(self, page) -> list[dict]:
        """Wait for items to load, then extract from the current page.

        Filters out sold-out items by checking for '売り切れ' in aria-label.
        """
        count = 0
        for _ in range(20):
            time.sleep(random.uniform(0.3, 0.7))
            try:
                count = page.evaluate('''() => document.querySelectorAll("a[href*='/item/m']").length''')
            except Exception:
                pass
            if count > 0:
                break

        if count == 0:
            return []

        return page.evaluate('''() => {
            const items = [];
            const allLinks = document.querySelectorAll('a[href*="/item/m"]');
            const seen = new Set();
            for (const link of allLinks) {
                const href = link.href;
                if (seen.has(href)) continue;
                seen.add(href);
                
                // Skip sold-out items — check aria-label on thumbnail for "売り切れ"
                const thumbnail = link.querySelector('.merItemThumbnail');
                if (thumbnail) {
                    const ariaLabel = thumbnail.getAttribute('aria-label') || '';
                    if (ariaLabel.includes('売り切れ')) continue;
                }
                
                const text = link.textContent.trim();
                if (text.length < 5 || text.length > 500) continue;
                const priceMatch = text.match(/¥\\s*([\\d,]+)/);
                let price = 0;
                if (priceMatch) {
                    price = parseInt(priceMatch[1].replace(/,/g, '')) || 0;
                }
                if (price < 100 || price > 5000000) continue;
                const idMatch = href.match(/\\/item\\/(m\\d+)/);
                const mercariId = idMatch ? idMatch[1] : '';
                const name = text.replace(/¥\\s*[\\d,]+/, '').replace(/\\s+/g, ' ').trim();
                if (!mercariId || name.length < 2) continue;
                items.push({
                    mercari_id: mercariId,
                    name: name.substring(0, 100),
                    price: price,
                    url: href,
                    image_url: (function() {
                        var img = link.querySelector('img[loading="lazy"], img.merItemThumbnail, img');
                        if (img) {
                            return img.getAttribute('data-src') || img.getAttribute('src') || '';
                        }
                        return '';
                    })(),
                });
            }
            return items;
        }''') or []

    def _normalize_search_url(self, search_url: str) -> str:
        """Ensure URL has sort=created_time (latest first), item_types=mercari, and is_soldout=false."""
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

        parsed = urlparse(search_url)
        params = parse_qs(parsed.query, keep_blank_values=True)

        if 'sort' not in params:
            params['sort'] = ['created_time']
        if 'item_types' not in params:
            params['item_types'] = ['mercari']
        if 'is_soldout' not in params:
            params['is_soldout'] = ['false']

        # Remove any existing page_token (we manage it)
        params.pop('page_token', None)

        new_query = urlencode(params, doseq=True)
        return urlunparse(parsed._replace(query=new_query))

    def _build_page_url(self, base_url: str, page_index: int) -> str:
        """Build URL for page N using v1:N cursor token."""
        if page_index == 0:
            return base_url
        token = urllib.parse.quote_plus(f'v1:{page_index}')
        return f"{base_url}&page_token={token}"

    def crawl(self, search_url: str) -> dict:
        """Crawl mercari search with pagination.

        Fetches pages until max_items are collected or no more pages.
        Sort by latest (sort=created_time) by default.

        Returns {"items": [...], "raw_html": ""}
        """
        self._enforce_crawl_gap(min_gap=5.0)

        base_url = self._normalize_search_url(search_url)

        for attempt in range(1, self.max_retries + 1):
            try:
                print(f"[Crawler] Attempt {attempt}/{self.max_retries}: fetching '{base_url}'...")
                self._ensure_browser()

                all_items = []
                seen_ids = set()
                page_idx = 0

                while len(all_items) < self.max_items:
                    page_url = self._build_page_url(base_url, page_idx)
                    print(f"[Crawler]   Page {page_idx + 1}: {page_url}")

                    page = self._context.new_page()
                    try:
                        page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
                        self._human_scroll(page)
                        page_items = self._extract_items_from_page(page)

                        # Deduplicate
                        new_count = 0
                        for item in page_items:
                            mid = item.get('mercari_id', '')
                            if mid and mid not in seen_ids:
                                seen_ids.add(mid)
                                all_items.append(item)
                                new_count += 1

                        print(f"[Crawler]   Page {page_idx + 1}: {len(page_items)} found, {new_count} new (total: {len(all_items)})")

                        if new_count == 0:
                            print(f"[Crawler]   No new items on page {page_idx + 1}, stopping pagination.")
                            break

                        if len(all_items) >= self.max_items:
                            print(f"[Crawler]   Reached max_items={self.max_items}, stopping.")
                            break

                        page_idx += 1
                        time.sleep(self._jitter(1.5, 3.5))

                    finally:
                        try:
                            page.close()
                        except Exception:
                            pass

                valid = [i for i in all_items if i.get('price', 0) > 0]
                if valid:
                    print(f"[Crawler] Extracted {len(valid)} valid items total")
                    return {"items": valid, "raw_html": ""}

                if attempt < self.max_retries:
                    wait = (5 * attempt) + self._jitter(0, 3)
                    print(f"[Crawler] Retrying in {wait:.1f}s...")
                    time.sleep(wait)

            except Exception as e:
                print(f"[Crawler] Attempt {attempt}/{self.max_retries} failed: {e}")
                self._reset_browser()
                if attempt < self.max_retries:
                    wait = (5 * attempt) + self._jitter(0, 3)
                    time.sleep(wait)

        return {"items": [], "raw_html": ""}

    def crawl_seller(self, username: str, max_items: int = 0) -> list[dict]:
        """Crawl a seller's page to get all their listed items.

        Mercari seller pages use pagination with cursor tokens similar to search.
       URL pattern: https://jp.mercari.com/user/profile/{username}?sort=new&is_soldout=false
        Supports pagination via data-cursor attribute.
        Args:
            username: Mercari seller username
            max_items: max items to fetch (0 = no limit, default from config)

        Returns:
            List of item dicts with mercari_id, name, price, url, image_url
        """
        max_items = max_items or self.max_items

        self._enforce_crawl_gap(min_gap=5.0)

        base_url = f"https://jp.mercari.com/user/profile/{urllib.parse.quote(username)}?sort=new&is_soldout=false"
        print(f"[Crawler] Crawl seller '{username}': {base_url}")

        for attempt in range(1, self.max_retries + 1):
            try:
                self._ensure_browser()
                all_items = []
                seen_ids = set()
                page_idx = 0

                while True:
                    if page_idx > 0:
                        token = urllib.parse.quote_plus(f'v1:{page_idx}')
                        page_url = f"{base_url}&page_token={token}"
                    else:
                        page_url = base_url

                    page = self._context.new_page()
                    try:
                        page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
                        self._human_scroll(page)

                        page_items = self._extract_items_from_page(page)

                        new_count = 0
                        for item in page_items:
                            mid = item.get('mercari_id', '')
                            if mid and mid not in seen_ids:
                                seen_ids.add(mid)
                                all_items.append(item)
                                new_count += 1

                        print(f"[Crawler]   Page {page_idx + 1}: {len(page_items)} found, {new_count} new (total: {len(all_items)})")

                        if new_count == 0:
                            print(f"[Crawler]   No new items on page {page_idx + 1}, stopping.")
                            break

                        if max_items and len(all_items) >= max_items:
                            print(f"[Crawler]   Reached max_items={max_items}, stopping.")
                            all_items = all_items[:max_items]
                            break

                        page_idx += 1
                        time.sleep(self._jitter(1.5, 3.5))

                    finally:
                        try:
                            page.close()
                        except Exception:
                            pass

                if all_items:
                    print(f"[Crawler] Seller '{username}': {len(all_items)} items total")
                    return all_items

                if attempt < self.max_retries:
                    wait = (5 * attempt) + self._jitter(0, 3)
                    print(f"[Crawler] Retrying in {wait:.1f}s...")
                    time.sleep(wait)

            except Exception as e:
                print(f"[Crawler] Seller '{username}' attempt {attempt}/{self.max_retries} failed: {e}")
                self._reset_browser()
                if attempt < self.max_retries:
                    wait = (5 * attempt) + self._jitter(0, 3)
                    time.sleep(wait)

        return []

    def close(self):
        """Release playwright resources."""
        self._reset_browser()

    async def async_close(self):
        """No-op for backwards compatibility."""
        self.close()
