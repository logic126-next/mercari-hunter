"""Mercari Bargain Hunter - Item Name Normalizer"""
import re
import unicodedata


class ItemNameNormalizer:
    """Normalize item names for market price comparison.
    
    Example: "【即購入OK】Samsung 870 EVO 1TB SSD" → "samsung 870 evo 1tb ssd"
    """
    
    # Japanese full-width to half-width mapping
    FULLWIDTH_MAP = str.maketrans(
        "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ",
        "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
    )
    
    # Common prefixes/suffixes to remove
    IGNORE_WORDS = {
        "即購入OK", "即購入", "即決", "送料無料", "送料込", "新品", "未使用",
        "美品", "良品", "状態良好", "動作確認済", "動作確認済み", "状態良好",
        "本体のみ", "箱付き", "箱あり", "付属品あり", "付属品完備",
        "おまけ", "セット", "まとめ", "まとめ売り", "まとめ買い",
        "【", "】", "(", ")", "（", "）",
    }
    
    def __init__(self, config: dict = None):
        self.config = config or {}
    
    def normalize(self, name: str) -> str:
        """Normalize item name for comparison.
        
        Steps:
        1. Unicode normalization (NFKC)
        2. Full-width to half-width conversion
        3. Lowercase
        4. Remove common prefixes/suffixes
        5. Collapse whitespace
        """
        if not name:
            return ""
        
        # Unicode normalization
        normalized = unicodedata.normalize("NFKC", name)
        
        # Full-width to half-width
        normalized = normalized.translate(self.FULLWIDTH_MAP)
        
        # Lowercase
        normalized = normalized.lower()
        
        # Remove common words
        for word in self.IGNORE_WORDS:
            normalized = normalized.replace(word.lower(), "")
        
        # Collapse whitespace
        normalized = re.sub(r"\s+", " ", normalized).strip()
        
        return normalized
    
    def extract_key_words(self, name: str) -> str:
        """Extract key product identifier words from name.
        
        Keeps brand names, model numbers, and specifications.
        """
        normalized = self.normalize(name)
        
        # Extract brand names
        brands = [
            "samsung", "wd", "sandisk", "kioxia", "toshiba", "adata",
            "crucial", "kingston", "sk hynix", "intel", "patriot",
            "sabrent", "corsair", "silicon power", "lexar",
            "apple", "lenovo", "dynabook", "ne c", "hp", "dell", "asus",
            "sony", "panasonic", "sharp", "fuji film", "canon", "nikon",
            "nintendo", "playstation", "xbox", "sega",
        ]
        
        # Extract model numbers (alphanumeric with hyphens/dots)
        model_pattern = re.findall(
            r"\b([A-Za-z]{1,3}\d{2,4}[-.]?\w*)\b", normalized
        )
        
        # Extract capacity (TB, GB, MB)
        capacity_pattern = re.findall(
            r"\b(\d+\s*(?:tb|gb|mb|tb|gb|mb))\b", normalized
        )
        
        key_parts = []
        
        # Add found brands
        for brand in brands:
            if brand in normalized:
                key_parts.append(brand)
                break  # Only keep the first matching brand
        
        # Add model numbers
        for model in model_pattern[:3]:
            key_parts.append(model.lower())
        
        # Add capacity
        for cap in capacity_pattern[:1]:
            key_parts.append(cap.lower())
        
        return " ".join(key_parts) if key_parts else normalized[:50]
