"""Mercari Bargain Hunter - Data Extractor"""
from bs4 import BeautifulSoup
import re


class MercariExtractor:
    """Extract product data from mercari search result HTML"""

    # CSS selectors for mercari.jp search results (as of 2026)
    ITEM_CONTAINER = "article._3bqkz9o01, .c-SearchList-item"
    NAME_SELECTOR = ".c-ItemListProduct-name, ._1v5s8l901"
    PRICE_SELECTOR = ".c-Price, .price"
    URL_SELECTOR = "a[href*='/items/']"
    IMAGE_SELECTOR = "img.c-ImageItem-image, img[data-src]"
    CONDITION_SELECTOR = ".c-ItemListProduct-condition, ._2t6q7p401"

    # ── Brand / Model / Capacity extraction patterns ──────────────

    # SSD brands (longer patterns first to avoid partial match)
    SSD_BRANDS = [
        "Samsung", "SanDisk", "Seagate", "Western Digital", "WD_BLACK",
        "WD Blue", "WD Green", "Crucial", "Kingston", "Sabrent",
        "SK Hynix", "Intel", "Corsair", "ADATA", "AData",
        "Transcend", "Patriot", "Micron", "Team Group", "TeamGroup",
        "Lexar", "Phison", "Netac", "Kioxia", "Toshiba",
    ]

    # iPhone models (specific → general)
    IPHONE_MODELS = [
        "iPhone 16 Pro Max", "iPhone 16 Pro", "iPhone 16 Plus", "iPhone 16",
        "iPhone 15 Pro Max", "iPhone 15 Pro", "iPhone 15 Plus", "iPhone 15",
        "iPhone 14 Pro Max", "iPhone 14 Pro", "iPhone 14 Plus", "iPhone 14",
        "iPhone 13 Pro Max", "iPhone 13 Pro", "iPhone 13 mini", "iPhone 13",
        "iPhone 12 Pro Max", "iPhone 12 Pro", "iPhone 12 mini", "iPhone 12",
        "iPhone 11 Pro Max", "iPhone 11 Pro", "iPhone 11",
        "iPhone SE 3", "iPhone SE 2", "iPhone SE",
        "iPhone XS Max", "iPhone XS", "iPhone XR", "iPhone X",
        "iPhone 8 Plus", "iPhone 8", "iPhone 7 Plus", "iPhone 7",
        "iPhone 6s Plus", "iPhone 6s", "iPhone 6 Plus", "iPhone 6",
    ]

    # Gaming PC brands
    GAMING_PC_BRANDS = [
        "ASUS ROG", "ASUS TUF", "ROG",
        "MSI", "Lenovo Legion", "Lenovo",
        "Dell Alienware", "Alienware", "Dell",
        "HP Omen", "Omen", "HP Pavilion", "HP",
        "Acer Predator", "Predator", "Acer Nitro", "Acer",
        "Gigabyte Aorus", "Aorus", "Gigabyte",
        "EVGA", "CyberPowerPC", "iBuyPower",
    ]

    # Capacity patterns
    CAPACITY_PATTERNS = [
        r'\b(\d{1,3}\s*(?:TB|GB|MB))\b',              # 1TB, 500GB, 256 GB
        r'\b(\d{1,3}\s*(?:テラ|ギガ|メガ))\b',          # Japanese: 1テラ, 500ギガ
        r'\b(\d{1,3}\s*(?:T|G)B)\b',                   # 1TB, 500GB (case insensitive handled below)
    ]

    def __init__(self):
        pass

    def extract_items(self, html_content):
        """Extract all items from search result HTML"""
        soup = BeautifulSoup(html_content, 'html.parser')
        items = []

        # Try multiple possible container selectors (mercari structure changes)
        containers = self._find_containers(soup)

        for container in containers:
            try:
                item = self._extract_single_item(container)
                if item and item.price > 0:
                    items.append(item)
            except Exception as e:
                # Skip problematic containers, log but continue
                print(f"[Extractor] Failed to extract item: {e}")
                continue

        return items

    def _find_containers(self, soup):
        """Find all item containers using multiple fallback selectors"""
        for selector in [
            "article._3bqkz9o01",
            ".c-SearchList-item",
            "a[href*='/items/']",  # Fallback: any link to items
            "[data-testid='item-card']",
        ]:
            containers = soup.select(selector)
            if containers:
                return containers
        return []

    def _extract_single_item(self, container):
        """Extract data from a single item container"""
        # Extract name
        name_elem = container.select_one(".c-ItemListProduct-name, .name, h3")
        name = name_elem.get_text(strip=True) if name_elem else ""

        # Extract price (remove yen symbol and commas)
        price_elem = container.select_one(".c-Price, .price, ._2p4q8r501")
        price_text = price_elem.get_text(strip=True) if price_elem else ""
        price = self._parse_price(price_text)

        # Extract URL
        url_elem = container.select_one("a[href*='/items/']")
        url = url_elem['href'] if url_elem and 'href' in url_elem.attrs else ""

        # Extract mercari_id from URL
        mercari_id = self._extract_mercari_id(url)

        # Extract image URL
        img_elem = container.select_one("img.c-ImageItem-image, img[data-src], img")
        image_url = img_elem.get('src') or img_elem.get('data-src', '') if img_elem else ''

        # ── Extract brand / model / capacity from name ───────────
        brand, model, capacity = self._extract_attributes(name)

        from src.models import Item
        return Item(
            mercari_id=mercari_id,
            name=name,
            price=price,
            url=url,
            category="",  # Will be set by config
            condition=self._extract_condition(container),
            description="",  # Would need to visit individual page
            brand=brand,
            model=model,
            capacity=capacity,
        )

    # ── Attribute extraction ─────────────────────────────────────

    def _extract_attributes(self, name: str) -> tuple[str, str, str]:
        """Extract (brand, model, capacity) from item name."""
        name_lower = name.lower()
        brand = ""
        model = ""
        capacity = ""

        # ── 1. Detect category context ──
        is_ssd = bool(re.search(r'\b(?:SSD|NVMe|SATA|solid\.state)\b', name, re.IGNORECASE))
        is_iphone = bool(re.search(r'iPhone', name, re.IGNORECASE))
        is_gaming_pc = bool(re.search(
            r'(?:ゲーミング|gaming|pc\b|自作|自作pc|Alienware|ROG|Legion|Predator|Omen|Aorus|Nitro|TUF|MSI\s+G)',
            name, re.IGNORECASE
        ))
        is_laptop = not is_gaming_pc and bool(re.search(
            r'(?:laptop|ノートPC|ノートパソコン|MacBook|Surface)',
            name, re.IGNORECASE
        ))

        # ── 2. Extract brand ──
        if is_ssd:
            brand = self._extract_brand(name, self.SSD_BRANDS)
        elif is_iphone:
            brand = "Apple"
        elif is_laptop:
            brand = self._extract_brand(name, ["Apple", "Microsoft", "ASUS", "Lenovo", "Dell", "HP", "Acer", "MSI", "Gigabyte"])
        elif is_gaming_pc:
            brand = self._extract_brand(name, self.GAMING_PC_BRANDS)

        # ── 3. Extract model ──
        if is_iphone:
            model = self._extract_iphone_model(name)
        elif is_ssd:
            model = self._extract_ssd_model(name, brand)
        elif is_gaming_pc:
            model = self._extract_pc_model(name, brand)

        # ── 4. Extract capacity ──
        capacity = self._extract_capacity(name)

        return (brand, model, capacity)

    def _extract_brand(self, name: str, brands: list[str]) -> str:
        """Find the first brand that appears in the name (case-insensitive)."""
        name_upper = name.upper()
        # Sort by length descending so longer matches win (e.g. "WD_BLACK" before "WD")
        for b in sorted(brands, key=len, reverse=True):
            if b.upper() in name_upper:
                return b
        return ""

    def _extract_iphone_model(self, name: str) -> str:
        """Extract iPhone model name (e.g. 'iPhone 15 Pro Max')."""
        name_upper = name.upper()
        # Try specific models first (longest first)
        for m in sorted(self.IPHONE_MODELS, key=len, reverse=True):
            if m.upper() in name_upper:
                return m
        # Fallback: try to match "iPhone \d+" pattern
        match = re.search(r'(iPhone\s+\d+(?:\s+(?:Pro\s+Max|Pro|Plus|mini))?)', name, re.IGNORECASE)
        if match:
            return match.group(1)
        return ""

    def _extract_ssd_model(self, name: str, brand: str) -> str:
        """Extract SSD model series name."""
        # Common SSD model series patterns
        model_patterns = [
            # Samsung
            r'(870\s*(?:EVO|QVO|PRO|Plus))',
            r'(860\s*(?:EVO|QVO|PRO))',
            r'(980|970|960|860)\s*EVO\s*Plus',
            r'((?:PM9A1|PM9B1|PM891|PM873|PM893|PM991|PM981))',
            r'(990\s*EVO)',
            # WD
            r'(SN850X?|SN770|SN750|SN580|SN570|SN550|SN350|SN500)',
            r'(WD\s*Black\s*(?:SN770|SN850))',
            # Crucial
            r'(T700|T500|P5\+\??|P3\+\??|MX500|MX300)',
            # Kingston
            r'(NV2|NV2\+|KC3000|KC2500|A2000|A1000)',
            # SanDisk
            r'(Extreme\s*PRO|Ultra\s*(?:3D|II))',
            # Generic NVMe model names
            r'(NVMe\s*\d{3,4})',
        ]
        for pat in model_patterns:
            match = re.search(pat, name, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        # Fallback: try to extract any model-like token after brand
        if brand:
            # Remove brand from name and take remaining tokens
            remaining = name
            for b in sorted(self.SSD_BRANDS, key=len, reverse=True):
                remaining = remaining.replace(b, '', 1)
            tokens = re.findall(r'[A-Za-z]\d{2,}\d?', remaining)
            if tokens:
                return tokens[0]
        return ""

    def _extract_pc_model(self, name: str, brand: str) -> str:
        """Extract gaming PC model if identifiable."""
        # Try to find model series names
        model_patterns = [
            r'(ROG\s*(?:Strix|Zephyrus|G\d{4,6}))',
            r'(TUF\s*(?:Gaming\s+A\d{4}|A15|A17))',
            r'(MSI\s*(?:GP|GS|STEALTH|RAID|THIN))',
            r'(Legion\s*(?:5|7|Pro|Slim))',
            r'(Alienware\s*(?:m15|m17|R14|R15|R17|R18|R19|x15|x17|Ryzen))',
            r'(Omen\s*(?:15|16|Transcend))',
            r'(Predator\s*(?:Helios|Triton|Orion))',
            r'(Nitro\s*(?:5|Plus|500))',
        ]
        for pat in model_patterns:
            match = re.search(pat, name, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    def _extract_capacity(self, name: str) -> str:
        """Extract storage capacity from item name."""
        # Try English patterns first
        match = re.search(
            r'\b(\d{1,3}\s*(?:TB|GB|MB|KB))\b',
            name, re.IGNORECASE
        )
        if match:
            return match.group(1).strip()

        # Try Japanese patterns
        match = re.search(
            r'\b(\d{1,3}\s*(?:テラ|ギガ|メガ|キロ))\b',
            name
        )
        if match:
            return match.group(1).strip()

        return ""

    # ── Legacy helpers ────────────────────────────────────────────

    def _parse_price(self, price_text):
        """Parse price string like '¥15,000' into integer"""
        if not price_text:
            return 0

        # Remove yen symbol and commas
        cleaned = price_text.replace('¥', '').replace(',', '').strip()

        try:
            return int(float(cleaned))
        except ValueError:
            return 0

    def _extract_mercari_id(self, url):
        """Extract mercari item ID from URL like /items/c123456789"""
        match = re.search(r'/c/([a-zA-Z0-9]+)', url)
        if match:
            return f"c{match.group(1)}"

        # Fallback: extract any alphanumeric ID
        match = re.search(r'/([a-zA-Z0-9]{8,})$', url)
        if match:
            return match.group(1)

        return ""

    def _extract_condition(self, container):
        """Extract item condition from the container"""
        condition_elem = container.select_one(".c-ItemListProduct-condition, .condition")
        if condition_elem:
            return condition_elem.get_text(strip=True)

        # Try to find in text content
        text = container.get_text()
        for cond in ["新品・未使用", "未使用に近い", "目立った傷や汚れなし"]:
            if cond in text:
                return cond

        return ""
