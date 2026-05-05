"""Mercari Bargain Hunter - Filter Engine"""


class FilterEngine:
    """Filter items based on condition, banned words, and other criteria.
    
    Works with both dict and Item objects.
    """
    
    def __init__(self, config: dict):
        self.allowed_conditions = config.get('allowed_conditions', [])
        self.banned_words = [w.lower() for w in config.get('banned_words', [])]
    
    def filter_items(self, items: list[dict]) -> list[dict]:
        """Filter a batch of items (dict or Item objects).
        
        Args:
            items: list of item dicts or Item objects
            
        Returns:
            list of items that pass all filters
        """
        return [item for item in items if not self.should_filter(item)]
    
    def should_filter(self, item) -> bool:
        """
        Return True if the item should be FILTERED OUT (excluded),
        False if it passes all filters.
        
        Filtering criteria:
        - Item condition not in allowed_conditions list
        - Description contains any banned words
        - Seller rating below threshold (if available)
        """
        # Support both dict and object
        name = item.get('name', '') if isinstance(item, dict) else getattr(item, 'name', '')
        condition = item.get('condition', '') if isinstance(item, dict) else getattr(item, 'condition', '')
        description = item.get('description', '') if isinstance(item, dict) else getattr(item, 'description', '')
        seller_rating = item.get('seller_rating', 0) if isinstance(item, dict) else getattr(item, 'seller_rating', 0)
        
        # Condition filter — only apply if we have condition data
        if self.allowed_conditions and condition:
            if not any(cond in condition for cond in self.allowed_conditions):
                return True  # Filter out
        
        # Banned words check in name/description
        text_to_check = f"{name} {description}".lower()
        for word in self.banned_words:
            if word in text_to_check:
                return True  # Filter out
        
        # Seller rating filter (if available)
        if seller_rating and seller_rating > 0:
            if seller_rating < 80.0:
                return True
        
        return False  # Passes all filters
    
    def get_filtered_reasons(self, item) -> list[str]:
        """Get reasons why an item was filtered out"""
        reasons = []
        
        # Support both dict and object
        name = item.get('name', '') if isinstance(item, dict) else getattr(item, 'name', '')
        condition = item.get('condition', '') if isinstance(item, dict) else getattr(item, 'condition', '')
        description = item.get('description', '') if isinstance(item, dict) else getattr(item, 'description', '')
        seller_rating = item.get('seller_rating', 0) if isinstance(item, dict) else getattr(item, 'seller_rating', 0)
        
        if self.allowed_conditions and condition:
            if not any(cond in condition for cond in self.allowed_conditions):
                reasons.append(f"Condition '{condition}' not allowed")
        
        text_to_check = f"{name} {description}".lower()
        for word in self.banned_words:
            if word in text_to_check:
                reasons.append(f"Banned word found: '{word}'")
        
        if seller_rating and seller_rating > 0:
            if seller_rating < 80.0:
                reasons.append(f"Seller rating {seller_rating}% is too low")
        
        return reasons
