"""Tests for MarketPriceCalculator"""
import unittest
from src.market_price import MarketPriceCalculator


class TestMarketPriceCalculator(unittest.TestCase):

    def setUp(self):
        self.calc = MarketPriceCalculator({
            "lookback_days": 30,
            "threshold_ratio": 0.7,
            "absolute_threshold_yen": 3000
        })

    # --- Median calculation tests ---

    def test_calculate_median_basic(self):
        """Median of a sorted list"""
        prices = [100, 200, 300, 400, 500]
        self.assertAlmostEqual(self.calc.calculate_median(prices), 300.0)

    def test_calculate_median_even_count(self):
        """Median with even number of items"""
        prices = [100, 200, 300, 400]
        self.assertAlmostEqual(self.calc.calculate_median(prices), 250.0)

    def test_calculate_median_outlier_removal(self):
        """Extreme outliers should be filtered by IQR"""
        prices = [100, 105, 98, 102, 101, 99, 103, 104, 5000]
        median = self.calc.calculate_median(prices)
        # After outlier removal, median should be ~102 not influenced by 5000
        self.assertLess(median, 200)
        self.assertGreater(median, 90)

    def test_calculate_median_too_few_items(self):
        """With < 2 items, should return 0"""
        self.assertAlmostEqual(self.calc.calculate_median([]), 0.0)
        self.assertAlmostEqual(self.calc.calculate_median([100]), 0.0)

    # --- Outlier removal tests ---

    def test_remove_outliers_basic(self):
        """Normal data should have no outliers removed"""
        data = [10, 20, 30, 40, 50]
        cleaned = self.calc._remove_outliers(data)
        # With small dataset (len < 4), returns as-is
        self.assertEqual(len(cleaned), len(data))

    def test_remove_outliers_with_extreme(self):
        """Extreme values should be removed"""
        data = [100, 102, 98, 101, 99, 103, 104, 105, 5000, -500]
        cleaned = self.calc._remove_outliers(data)
        # 5000 and -500 should be removed
        for val in cleaned:
            self.assertGreater(val, 0)
            self.assertLess(val, 2000)

    def test_remove_outliers_small_dataset(self):
        """Small dataset (< 4) returns unchanged"""
        data = [10, 20, 30]
        cleaned = self.calc._remove_outliers(data)
        self.assertEqual(cleaned, data)

    # --- Bargain detection tests ---

    def test_is_bargain_true_ratio_and_absolute(self):
        """Price well below median should be a bargain"""
        # 5000 is 50% of 10000 (below 70%), diff = 5000 (> 3000)
        self.assertTrue(self.calc.is_bargain(5000, 10000))

    def test_is_bargain_false_ratio_ok_but_not_absolute(self):
        """Below ratio but absolute difference too small"""
        # 6900 is 69% of 10000 (below 70%), diff = 3100 (> 3000) -- passes
        self.assertTrue(self.calc.is_bargain(6900, 10000))
        # 6500 is 65% of 8000 (below 70%), diff = 1500 (< 3000) -- fails
        self.assertFalse(self.calc.is_bargain(6500, 8000))

    def test_is_bargain_false_price_above_threshold(self):
        """Price above threshold ratio"""
        # 7100 is 71% of 10000 (above 70%)
        self.assertFalse(self.calc.is_bargain(7100, 10000))

    def test_is_bargain_zero_values(self):
        """Zero/negative prices should not be bargains"""
        self.assertFalse(self.calc.is_bargain(0, 10000))
        self.assertFalse(self.calc.is_bargain(5000, 0))

    # --- Bargain details tests ---

    def test_get_bargain_details_valid(self):
        """Should return correct details for a bargain"""
        details = self.calc.get_bargain_details(5000, 10000)
        self.assertIsNotNone(details)
        self.assertEqual(details["item_price"], 5000)
        self.assertEqual(details["market_median"], 10000)
        self.assertEqual(details["difference_yen"], 5000)
        self.assertAlmostEqual(details["ratio"], 0.5)
        self.assertAlmostEqual(details["discount_percent"], 50.0)

    def test_get_bargain_details_not_bargain(self):
        """Should return None when not a bargain"""
        details = self.calc.get_bargain_details(8000, 10000)
        self.assertIsNone(details)

    # --- Custom threshold tests ---

    def test_custom_threshold_ratio(self):
        """Custom threshold ratio from config"""
        calc = MarketPriceCalculator({
            "lookback_days": 30,
            "threshold_ratio": 0.8,
            "absolute_threshold_yen": 1000
        })
        # 7500 is 75% of 10000, below 80%, diff = 2500 (> 1000)
        self.assertTrue(calc.is_bargain(7500, 10000))

    def test_custom_absolute_threshold(self):
        """Custom absolute threshold from config"""
        calc = MarketPriceCalculator({
            "lookback_days": 30,
            "threshold_ratio": 0.9,
            "absolute_threshold_yen": 5000
        })
        # 8500 is 85% of 10000, below 90%, diff = 1500 (< 5000)
        self.assertFalse(calc.is_bargain(8500, 10000))


if __name__ == "__main__":
    unittest.main()
