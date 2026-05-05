"""Mercari Bargain Hunter - Market Price Calculator (Median-based)"""
import statistics
from datetime import datetime, timedelta
from typing import Optional


class MarketPriceCalculator:
    """Calculate market prices using median-based approach for outlier resistance"""
    
    def __init__(self, config: dict):
        self.lookback_days = config.get('lookback_days', 30)
        self.threshold_ratio = config.get('threshold_ratio', 0.7)
        self.absolute_threshold_yen = config.get('absolute_threshold_yen', 3000)
        self.min_samples = config.get('min_samples', 3)
    
    def calculate_median(self, prices: list) -> float:
        """Calculate median price from a list of prices using IQR outlier removal"""
        if not prices or len(prices) < 2:
            return 0.0
        
        cleaned_prices = self._remove_outliers(prices)
        
        if len(cleaned_prices) < 2:
            cleaned_prices = prices[:10]  # Fallback to recent items
        
        return statistics.median(cleaned_prices)
    
    def calculate_statistics(self, prices: list) -> dict:
        """Calculate full statistics for a price list.
        
        Returns:
            dict with median, mean, min, max, std, count
        """
        if not prices or len(prices) < 2:
            return {
                'median': 0.0, 'mean': 0.0, 'min': 0.0, 'max': 0.0,
                'std': 0.0, 'count': len(prices) if prices else 0
            }
        
        cleaned = self._remove_outliers(prices)
        if len(cleaned) < 2:
            cleaned = prices[:10]
        
        return {
            'median': statistics.median(cleaned),
            'mean': statistics.mean(cleaned),
            'min': min(cleaned),
            'max': max(cleaned),
            'std': statistics.stdev(cleaned) if len(cleaned) >= 2 else 0.0,
            'count': len(cleaned),
        }
    
    def _remove_outliers(self, data: list) -> list:
        """Remove outliers using IQR method (Interquartile Range)"""
        if len(data) < 4:
            return data
            
        q1 = statistics.quantiles(data, n=4)[0]  # 25th percentile
        q3 = statistics.quantiles(data, n=4)[2]  # 75th percentile
        iqr = q3 - q1
        
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        
        return [x for x in data if lower_bound <= x <= upper_bound]
    
    def is_bargain(self, item_price: float, market_median: float) -> bool:
        """
        Determine if an item is a bargain based on both ratio and absolute thresholds
        
        Returns True if:
        - Item price is below threshold_ratio of median AND
        - Difference exceeds absolute_threshold_yen
        """
        if market_median <= 0 or item_price <= 0:
            return False
            
        ratio = item_price / market_median
        meets_ratio = ratio <= self.threshold_ratio
        
        difference = market_median - item_price
        meets_absolute = difference >= self.absolute_threshold_yen
        
        return meets_ratio and meets_absolute
    
    def get_bargain_details(self, item_price: float, market_median: float) -> Optional[dict]:
        """Get detailed bargain information.
        
        Returns None if not a bargain.
        """
        if not self.is_bargain(item_price, market_median):
            return None
            
        difference = round(market_median - item_price)
        ratio = item_price / market_median if market_median > 0 else 0
        
        return {
            "item_price": item_price,
            "market_median": round(market_median),
            "difference_yen": difference,
            "ratio": ratio,
            "discount_percent": round((1 - ratio) * 100, 1)
        }
    
    def get_market_summary(self, prices: list) -> dict:
        """Get a summary of market prices for display/reporting.
        
        Args:
            prices: list of historical prices
            
        Returns:
            dict with summary statistics
        """
        stats = self.calculate_statistics(prices)
        
        if stats['count'] == 0:
            return {
                'status': 'insufficient_data',
                'needed_samples': self.min_samples,
                'available_samples': 0,
            }
        
        return {
            'status': 'ready',
            'available_samples': stats['count'],
            'median': stats['median'],
            'mean': stats['mean'],
            'price_range': (stats['min'], stats['max']),
            'threshold_price': stats['median'] * self.threshold_ratio,
            'absolute_threshold': self.absolute_threshold_yen,
        }
