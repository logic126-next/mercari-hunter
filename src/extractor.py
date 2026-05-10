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

    # ── New category brand lists ──────────────────────────────────

    # iPad / Apple tablet models (longest first)
    IPAD_MODELS = [
        "iPad Pro 13インチ", "iPad Pro 12.9インチ", "iPad Pro 11インチ",
        "iPad Pro 12インチ", "iPad Pro 10.5インチ", "iPad Pro 9.7インチ",
        "iPad Pro M4", "iPad Pro M2", "iPad Pro M1",
        "iPad Air 13インチ", "iPad Air 11インチ", "iPad Air M2",
        "iPad Air 10.9インチ",
        "iPad mini 6", "iPad mini 5", "iPad mini A17",
        "iPad 10", "iPad 9", "iPad 8", "iPad 7", "iPad 6",
        "iPad Pro", "iPad Air", "iPad mini",
    ]

    # Nintendo / gaming console brands
    CONSOLE_BRANDS = [
        "Nintendo", "Sony", "Microsoft", "Valve",
    ]
    # Nintendo Switch models (longest first)
    SWITCH_MODELS = [
        "Switch OLED", "Switch Lite",
        "Switch 2", "Switch",
        "Switch OLEDモデル", "Switch Liteモデル",
        "Nintendo Switch OLED", "Nintendo Switch Lite",
        "Nintendo Switch 2", "Nintendo Switch",
    ]

    # Monitor brands
    MONITOR_BRANDS = [
        "LG", "Dell", "Samsung", "ASUS", "BenQ", "AOC",
        "MSI", "Gigabyte", "HP", "ViewSonic", "EIZO",
        "NEC", "Fujitsu", "Sony",
    ]

    # Keyboard / mouse / peripheral brands
    PERIPHERAL_BRANDS = [
        "Logitech", "Razer", "Corsair", "SteelSeries",
        "HyperX", "Ducky", "Keychron", "Filco",
        "Cherry", "HHKB", "Topre", "Realforce",
        "TMTC", " Leopold", " Leopold FC",
        "Microsoft", "Apple", "Jelly Comb",
        "Anker", "Aukey", "Rii",
    ]

    # Camera brands
    CAMERA_BRANDS = [
        "Sony", "Canon", "Nikon", "Fujifilm", "FUJIFILM",
        "Pentax", "Olympus", "Panasonic", "Leica",
        "Hasselblad", "GoPro", "DJI", "Ricoh",
        "Sigma", "Tamron", "Tokina", "Viltrox", "LAOWA",
    ]

    # Audio brands
    AUDIO_BRANDS = [
        "Sony", "Bose", "Sennheiser", "Beats",
        "Audio-Technica", "JBL", "Marshall", "Jabra",
        "Shure", "AKG", "Denon", "Yamaha", "Focal",
        "Bang & Olufsen", "B&O", "Plantronics",
        "Anker", "Soundcore", "Jabra",
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
            image_url=image_url,
            brand=brand,
            model=model,
            capacity=capacity,
        )

    # ── Attribute extraction ─────────────────────────────────────

    def _extract_attributes(self, name: str) -> tuple[str, str, str]:
        """Extract (brand, model, capacity) from item name.

        Covers many categories: SSD, iPhone, iPad, gaming PC, laptop,
        Nintendo Switch/Steam Deck, monitors, keyboards/mice, cameras,
        audio, and general electronics.
        """
        name_lower = name.lower()
        brand = ""
        model = ""
        capacity = ""

        # ── 1. Detect category context ──
        is_ssd = bool(re.search(r'\b(?:SSD|NVMe|SATA|solid\.state|SSD\s*[Ss]olid)\b', name, re.IGNORECASE))
        is_iphone = bool(re.search(r'iPhone', name, re.IGNORECASE))
        is_ipad = not is_iphone and bool(re.search(r'iPad', name, re.IGNORECASE))
        is_console = bool(re.search(
            r'(?:Nintendo\s*Switch|Switch\s*(?:OLED|Lite)|Steam\s*Deck|PS5|PS4|Xbox|Nintendo Switch 2)',
            name, re.IGNORECASE
        ))
        is_monitor = bool(re.search(
            r'(?:monitor|モニター|ディスプレイ|27インチ|32インチ|24インチ|4K\s*(?:モニター|モニタ|UHD)|WQHD|UHD\s*モニター|IPS\s*モニター|VA\s*モニター|OLED\s*モニター|HDR\s*モニター)',
            name, re.IGNORECASE
        ))
        is_peripheral = bool(re.search(
            r'(?:keyboard|キーボード|mouse|マウス|headset|ヘッドセット|webcam|ウェブカメラ|Bluetooth.*キー|ワイヤレス.*キー|メカニカル|mechanical|macro|RGB.*キー)',
            name, re.IGNORECASE
        ))
        is_camera = bool(re.search(
            r'(?:camera|カメラ|DSLR|ミラーレス|一眼|レンズ|lens|GFX|GH\d|ZV-|A7\s*(?:IV|III|II|I|S|R|C|CR|M\d)|A6\d{2}|A9\s*(?:II|III|IV)|EOS\s|R5\b|R6\b|D850|D7|D6|X-T|X-E|X-Pro|X100|X-T5|X-T4|F\d{2,}|GoPro)',
            name, re.IGNORECASE
        ))
        is_audio = bool(re.search(
            r'(?:headphone|イヤーホン|イヤホン|earbuds|earphones|スピーカー|speaker|audio|ワイヤレス|Bluetooth|noise\s*cancelling|ノイズキャンセリング|WH-1000|WF-1000|WH-\d+|WF-\d+|QC-\d+|QuietComfort|Quiet\s*Comfort|Soundcore|WH-CH|WH-H9)',
            name, re.IGNORECASE
        ))
        is_gaming_pc = bool(re.search(
            r'(?:ゲーミング|gaming|pc\b|自作|自作pc|Alienware|ROG|Legion|Predator|Omen|Aorus|Nitro|TUF|MSI\s+G)',
            name, re.IGNORECASE
        ))
        is_laptop = not is_gaming_pc and bool(re.search(
            r'(?:laptop|ノートPC|ノートパソコン|MacBook|Surface|XPS|Latitude|ThinkPad|Spectre|EliteBook|Swift|Aspire|Yoga|ZenBook|VivoBook)',
            name, re.IGNORECASE
        ))

        # ── 2. Extract brand ──
        # First, try brand-based fallback: if a known brand appears but no
        # category matched yet, assign to the appropriate category.
        if not any([is_ssd, is_iphone, is_ipad, is_console, is_monitor,
                     is_peripheral, is_camera, is_audio, is_gaming_pc, is_laptop]):
            # Check if any known brand is present and assign category
            if self._extract_brand(name, self.PERIPHERAL_BRANDS):
                is_peripheral = True
            elif self._extract_brand(name, self.AUDIO_BRANDS):
                is_audio = True
            elif self._extract_brand(name, self.CAMERA_BRANDS):
                is_camera = True
            elif self._extract_brand(name, self.SSD_BRANDS):
                is_ssd = True
            elif self._extract_brand(name, self.MONITOR_BRANDS):
                is_monitor = True
            elif self._extract_brand(name, self.CONSOLE_BRANDS):
                is_console = True

        if is_ssd:
            brand = self._extract_brand(name, self.SSD_BRANDS)
        elif is_iphone:
            brand = "Apple"
        elif is_ipad:
            brand = "Apple"
        elif is_console:
            brand = self._extract_brand(name, self.CONSOLE_BRANDS)
            if not brand and re.search(r'Steam\s*Deck', name, re.IGNORECASE):
                brand = "Valve"
        elif is_monitor:
            brand = self._extract_brand(name, self.MONITOR_BRANDS)
        elif is_peripheral:
            brand = self._extract_brand(name, self.PERIPHERAL_BRANDS)
        elif is_camera:
            brand = self._extract_brand(name, self.CAMERA_BRANDS)
        elif is_audio:
            brand = self._extract_brand(name, self.AUDIO_BRANDS)
        elif is_laptop:
            laptop_brands = ["Apple", "Microsoft", "ASUS", "Lenovo", "Dell", "HP", "Acer", "MSI", "Gigabyte"]
            brand = self._extract_brand(name, laptop_brands)
            if not brand and re.search(r'MacBook', name, re.IGNORECASE):
                brand = "Apple"
        elif is_gaming_pc:
            brand = self._extract_brand(name, self.GAMING_PC_BRANDS)

        # ── 3. Extract model ──
        if is_iphone:
            model = self._extract_iphone_model(name)
        elif is_ipad:
            model = self._extract_ipad_model(name)
        elif is_ssd:
            model = self._extract_ssd_model(name, brand)
        elif is_gaming_pc:
            model = self._extract_pc_model(name, brand)
        elif is_console:
            model = self._extract_console_model(name)
        elif is_monitor:
            model = self._extract_monitor_model(name, brand)
        elif is_peripheral:
            model = self._extract_peripheral_model(name, brand)
        elif is_camera:
            model = self._extract_camera_model(name, brand)
        elif is_audio:
            model = self._extract_audio_model(name, brand)
        elif is_laptop:
            model = self._extract_laptop_model(name, brand)

        # ── 4. Extract capacity ──
        # Skip capacity extraction for monitors — screen size belongs in model, not capacity.
        if not is_monitor:
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

    def _extract_ipad_model(self, name: str) -> str:
        """Extract iPad model name (e.g. 'iPad Pro 11インチ')."""
        name_upper = name.upper()
        for m in sorted(self.IPAD_MODELS, key=len, reverse=True):
            if m.upper() in name_upper:
                return m
        # Fallback: try iPad with size
        match = re.search(r'(iPad\s+(?:Pro|Air|mini)\s*(?:\d+|M\d|第\d世代)?)', name, re.IGNORECASE)
        if match:
            return match.group(1)
        return ""

    def _extract_ssd_model(self, name: str, brand: str) -> str:
        """Extract SSD model series name."""
        # Common SSD model series patterns
        model_patterns = [
            # Samsung
            r'(990\s*(?:EVO|PRO)?)',
            r'(980\s*(?:PRO|EVO\s*Plus)?)',
            r'(970\s*(?:EVO\s*Plus|PRO)?)',
            r'(960\s*(?:EVO)?)',
            r'(870\s*(?:EVO\s*(?:Plus|Max)|QVO|PRO)?)',
            r'(860\s*(?:EVO\s*Plus|QVO|PRO)?)',
            r'((?:PM9A1|PM9B1|PM891|PM873|PM893|PM991|PM981))',
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

    def _extract_console_model(self, name: str) -> str:
        """Extract gaming console model (Switch, PS5, Xbox, Steam Deck)."""
        name_upper = name.upper()
        for m in sorted(self.SWITCH_MODELS, key=len, reverse=True):
            if m.upper() in name_upper:
                return m
        # PlayStation
        ps_match = re.search(r'(PS5\s*(?:Slim|Digital|デジタル|スリム)?|PS4\s*(?:Pro|Slim|スリム)?)', name, re.IGNORECASE)
        if ps_match:
            return ps_match.group(1)
        # Xbox
        xbox_match = re.search(r'(Xbox\s*(?:Series\s*[XS]|One\s*(?:X|S|Xbox)?))', name, re.IGNORECASE)
        if xbox_match:
            return xbox_match.group(1)
        # Steam Deck
        if re.search(r'Steam\s*Deck', name, re.IGNORECASE):
            return "Steam Deck"
        return ""

    def _extract_monitor_model(self, name: str, brand: str) -> str:
        """Extract monitor model info (size, resolution, panel type)."""
        parts = []

        # Screen size
        size_match = re.search(r'(\d{1,2}(?:\.\d+)?)\s*インチ', name)
        if size_match:
            parts.append(f"{size_match.group(1)}インチ")

        # Resolution
        res_match = re.search(r'\b((?:4K|UHD|WQHD|QHD|FHD|2K|1080p|1440p|2160p))\b', name, re.IGNORECASE)
        if res_match:
            parts.append(res_match.group(1))

        # Panel type
        panel_match = re.search(r'\b((?:IPS|VA|TN|OLED|Nano\s*IPS|Fast\s*IPS))\b', name, re.IGNORECASE)
        if panel_match:
            parts.append(panel_match.group(1))

        # Refresh rate
        hz_match = re.search(r'(\d{2,4})\s*Hz', name, re.IGNORECASE)
        if hz_match:
            parts.append(f"{hz_match.group(1)}Hz")

        # Model number (e.g. LG 27GP850, Dell U2723QE)
        model_num = re.search(r'([A-Z]{1,3}\d{3,5}[A-Z0-9]*)', name)
        if model_num and not parts:
            candidate = model_num.group(1)
            # Filter out things that look like capacity or other numbers
            if not re.match(r'^(?:4K|UHD|WQHD|1080|1440|2160)$', candidate):
                parts.append(candidate)

        return " ".join(parts) if parts else ""

    def _extract_peripheral_model(self, name: str, brand: str) -> str:
        """Extract keyboard/mouse/peripheral model."""
        model_patterns = [
            # Logitech
            r'(MX\s*(?:Keys|Master|Anywhere|Keys\s*S|Master\s*S))',
            r'(K830|K780|K380|K375|K380)',
            r'(G\s*(?:Pro\s*X|502|304|903|910|604|305|502))',
            r'(Crosstype|CRS)',
            # Razer
            r'(BlackWidow\s*(?:V3|V4|Mini|Lite|X|Chroma)?)',
            r'(DeathAdder\s*(?:V2|Elite|Essential|X|V3)?)',
            r'(Huntsman\s*(?:V2|Mini|Tactial|Optical)?)',
            r'(Kitty|Kraken)',
            # Corsair
            r'(K70|K95|K65|K60|K100|K101|K102)',
            r'(Scimitar|Harpoon|Sabre|Dark\s*Core)',
            # SteelSeries
            r'(Apex\s*(?:Pro|75|Mini|Plus|TKL|7))',
            r'(Rival\s*(?:600|300|310|500|650|700|Pro|Mini))',
            # Ducky / mechanical
            r'(One|Shine|Me-chan)',
            # Keychron
            r'(K\d{2}|K\d{3}|Q\d{2}|Q\d{3}|C\d{2})',
            # Cherry
            r'(MX\s*(?:Board|Speed|Board\s*3.0|Board\s*3.1s))',
            # HHKB
            r'(HHKB|HYBRID|Professional)',
        ]
        for pat in model_patterns:
            match = re.search(pat, name, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        # Fallback: try to find model-like alphanumeric codes
        model_match = re.search(r'([A-Z]{1,3}\d{2,4}[A-Z0-9]*)', name)
        if model_match:
            return model_match.group(1)
        return ""

    def _extract_camera_model(self, name: str, brand: str) -> str:
        """Extract camera model name."""
        model_patterns = [
            # Sony
            r'(A7\s*(?:IV|III|II|I|S|R|C|CR|M4|M3|M2|M1)?)',
            r'(A6\d{2}(?:M\d|V)?)',
            r'(A9\s*(?:II|III)?)',
            r'(ZV-1|ZV-E10|ZV-E1)',
            r'(RX100\s*\d+)',
            r'(Alpha\s*\d+)',
            # Canon
            r'(EOS\s*(?:R5|RP|R6|R\d|Rp|R\dC|M\d|Rebel\s*\d+))',
            r'(EOS\s*M\d)',
            r'(PowerShot\s*\w+)',
            r'(G7\s*X|G5\s*X|G1\s*X)',
            # Nikon
            r'(Z\d{2,3}(?:II|FL|ft)?|Zf|Z8|Z6|Z5|Z7)',
            r'(D850|D780|D750|D610|D5600|D5300|D5200|D3500)',
            # Fujifilm
            r'(X-T\d+(?:II|III|IV)?)',
            r'(X-E\d+)',
            r'(X-Pro\d+)',
            r'(X100(?:VI|V|IV|III|II|F)?)',
            r'(X-H\d|X-S\d)',
            r'(GFX\d{3})',
            r'(Instax\s*\w+)',
            # Panasonic
            r'(GH\d|G9|GX\d|FZ\d)',
            # Olympus
            r'(OM-D\s*\w+|OM-\d|E-\d{4}|PEN\s*\w+)',
            # GoPro
            r'(Hero\d+(?:Black|White|Silver)?)',
            # DJI
            r'(Mini\s*\d+|Air\s*\d+|Mavic\s*\w+)',
            # Lens
            r'(\d{2,3}[Ff]\.\d{1,2}|STM|USM|OSS|VR|IS\s*USM)',
        ]
        for pat in model_patterns:
            match = re.search(pat, name, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    def _extract_audio_model(self, name: str, brand: str) -> str:
        """Extract audio device model."""
        model_patterns = [
            # Sony
            r'(WH-1000XM\d)',
            r'(WF-1000XM\d)',
            r'(WH-CH\d+)',
            r'(LinkBuds|LinkBuds\s*S)',
            # Bose
            r'(QuietComfort\s*(?:Ultra|45|35|SE)?)',
            r'(SoundLink\s*(?:Mini|Revolve|Flex|Sport|Revolve+))',
            r'(700|500|200|300|400)',
            # Sennheiser
            r'(Momentum\s*(?:4|3|True|Cancelling|TW)?)',
            r'(PXC-5\d{2})',
            r'(HD\s*\d{3,4})',
            # Beats
            r'(Studio\s*(?:Pro|Plus|3|Ultra)?)',
            r'(Solo\s*(?:Pro|4|3|Ultra)?)',
            r'(Powerbeats\s*(?:Pro|3)?)',
            r'(Fit\s*(?:Pro|True)?)',
            # Audio-Technica
            r'(ATH-M\d{3}|ATH-ANC\d{3}|ATH-CKS\d{3})',
            # JBL
            r'(Tune\s*\d{3}|Live\s*\d{3}|Flip\s*\d|Charge\s*\d|Boombox\s*\d)',
            # Marshall
            r'(Major\s*IV|Minor\s*IV|Athena|Stanmore|Kilburn|Acton|Emberton|Woburn)',
            # Jabra
            r'(Elite\s*\d+|Evolve\s*\d+|Vox\s*\d+)',
            # Shure
            r'(SE\d{4}|SE\s*\d{4})',
            # B&O / Bang & Olufsen
            r'(Beoplay\s*\w+|A\d{2}|B\d{2}|E\d{2}|H\d{2})',
        ]
        for pat in model_patterns:
            match = re.search(pat, name, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    def _extract_laptop_model(self, name: str, brand: str) -> str:
        """Extract laptop model name."""
        model_patterns = [
            # MacBook (longer patterns first!)
            r'(MacBook\s*Pro\s*(?:14|16|13|15|16-inch|14-inch|13-inch|15-inch))',
            r'(MacBook\s*Air\s*(?:M\d|M\d+\s*chip|13|15)?)',
            r'(MacBook\s*(?:Pro|Air))',
            # Surface
            r'(Surface\s*(?:Pro\s*\d+|Laptop\s*\d+|Go|Book|Laptop))',
            # ASUS
            r'(ZenBook|ROG\s*(?:Zephyrus|Scar|Strix|Flow))',
            r'(VivoBook|ExpertBook|ProArt)',
            # Lenovo
            r'(ThinkPad\s*(?:X\d|T\d|P\d|Z\d|E\d|X1|W\d)|Legion\s*(?:5|7|Slim|Pro|Y\d))',
            r'(IdeaPad|Yoga)',
            # Dell
            r'(XPS\s*\d{2,4}|Inspiron|Latitude|Precision)',
            # HP
            r'(Spectre|x360|Pavilion|EliteBook|ProBook|Envy)',
            # Acer
            r'(Swift|Aspire|Spin|Nitro|Predator)',
            # MSI
            r'(Stealth|Prestige|Modern|Raider|Crosshair)',
        ]
        for pat in model_patterns:
            match = re.search(pat, name, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    def _extract_capacity(self, name: str) -> str:
        """Extract storage/memory capacity from item name.

        Handles:
        - English: 1TB, 500GB, 256 GB, 8GB RAM
        - Japanese: 256ギガ, 1テラ
        - Full-width chars: ＴＢ, ＧＢ
        - Bracketed: (256GB), [256GB]
        - Memory: 8GB RAM, 16GB メモリ
        - Screen sizes: 11インチ, 13インチ (for laptops/tablets)
        """
        # Normalize full-width characters to half-width
        normalized = self._normalize_fullwidth(name)

        # ── 1. Storage capacity patterns ──
        # Match capacity in brackets/parentheses: (256GB), [512GB]
        match = re.search(
            r'[\(\[](\d{1,3}\s*(?:TB|GB|MB|KB))[\)\]]',
            normalized, re.IGNORECASE
        )
        if match:
            return match.group(1).strip()

        # Match standard capacity: 1TB, 500GB, 256 GB, 512GB
        match = re.search(
            r'(?<!\w)(\d{1,3}\s*(?:TB|GB|MB|KB))(?!\w)',
            normalized, re.IGNORECASE
        )
        if match:
            return match.group(1).strip()

        # ── 2. Japanese storage patterns ──
        # 256ギガ, 1テラ, 500メガ, 1024キロ
        match = re.search(
            r'(?<!\w)(\d{1,3}\s*(?:テラ|ギガ|メガ|キロ))(?!\w)',
            normalized
        )
        if match:
            return match.group(1).strip()

        # ── 3. Memory/RAM patterns ──
        # 8GB RAM, 16GBメモリ, 32GB メモリ, 8GBメモリ
        match = re.search(
            r'(?<!\w)(\d{1,3}\s*(?:GB|MB))\s*(?:RAM|メモリ|メモリー|メモ)\b',
            normalized, re.IGNORECASE
        )
        if match:
            return match.group(1).strip()

        # ── 4. Screen size (for laptops/tablets/monitors) ──
        # 11インチ, 13インチ, 15インチ, 27インチ, 32インチ
        match = re.search(
            r'(?<!\w)(\d{1,2}(?:\.\d+)?)\s*インチ',
            normalized
        )
        if match:
            return match.group(1).strip() + "インチ"

        # ── 5. Japanese full-width capacity in original name ──
        match = re.search(
            r'(\d{1,3}\s*(?:ＴＢ|ＧＢ|ＭＢ|ＫＢ|テラ|ギガ|メガ|キロ))',
            name
        )
        if match:
            # Normalize the full-width result
            return self._normalize_fullwidth(match.group(1).strip())

        return ""
    @staticmethod
    def _normalize_fullwidth(s: str) -> str:
        """Convert full-width characters to half-width for matching."""
        result = []
        for ch in s:
            code = ord(ch)
            # Full-width alphanumerics: Ａ(0xFF21)～Ｚ(0xFF3A), ａ(0xFF41)～ｚ(0xFF5A), ０(0xFF10)～９(0xFF19)
            if 0xFF21 <= code <= 0xFF3A:  # Full-width A-Z
                result.append(chr(code - 0xFF21 + ord('A')))
            elif 0xFF41 <= code <= 0xFF5A:  # Full-width a-z
                result.append(chr(code - 0xFF41 + ord('a')))
            elif 0xFF10 <= code <= 0xFF19:  # Full-width 0-9
                result.append(chr(code - 0xFF10 + ord('0')))
            # Full-width space
            elif code == 0x3000:
                result.append(' ')
            else:
                result.append(ch)
        return ''.join(result)

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
