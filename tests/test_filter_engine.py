"""Tests for FilterEngine"""
import unittest
from src.filter_engine import FilterEngine
from src.models import Item


def make_item(name="テスト商品", price=5000, condition="", description="", seller_rating=95.0):
    """Helper to create an Item quickly"""
    return Item(
        mercari_id=f"c{hash(name) & 0xFFFFFFFF:08x}",
        name=name,
        price=price,
        url="https://jp.mercari.com/items/test",
        condition=condition,
        description=description,
        seller_rating=seller_rating
    )


class TestFilterEngine(unittest.TestCase):

    def setUp(self):
        self.engine = FilterEngine({
            "allowed_conditions": ["新品・未使用", "未使用に近い", "目立った傷や汚れなし"],
            "banned_words": ["ジャンク", "動作未確認", "壊れている", "部品取り", "故障"]
        })

    # --- Condition filter tests ---

    def test_allowed_condition_passes(self):
        """Allowed conditions should not be filtered out"""
        for cond in ["新品・未使用", "未使用に近い", "目立った傷や汚れなし"]:
            item = make_item(condition=cond)
            self.assertFalse(self.engine.should_filter(item))

    def test_disallowed_condition_filtered(self):
        """Disallowed conditions should be filtered out"""
        for cond in ["やや傷や汚れあり", "大きな傷や汚れあり", "使用不可"]:
            item = make_item(condition=cond)
            self.assertTrue(self.engine.should_filter(item))

    def test_empty_condition_passes(self):
        """Empty condition should pass (no info available)"""
        item = make_item(condition="")
        self.assertFalse(self.engine.should_filter(item))

    # --- Banned words tests ---

    def test_banned_word_in_name_filtered(self):
        """Banned word in name should be filtered out"""
        item = make_item(name="ジャンク iPhone 13")
        self.assertTrue(self.engine.should_filter(item))

    def test_banned_word_in_description_filtered(self):
        """Banned word in description should be filtered out"""
        item = make_item(description="動作未確認のためお値下げします")
        self.assertTrue(self.engine.should_filter(item))

    def test_no_banned_words_passes(self):
        """Normal text without banned words should pass"""
        item = make_item(
            name="iPhone 13 Pro",
            description="美品です。箱付き。すぐに発送できます。"
        )
        self.assertFalse(self.engine.should_filter(item))

    def test_banned_word_case_insensitive(self):
        """Banned words should be matched case-insensitively"""
        item = make_item(description="壊れているのでお値下げ")
        self.assertTrue(self.engine.should_filter(item))

    # --- Seller rating tests ---

    def test_good_seller_rating_passes(self):
        """High seller rating should pass"""
        item = make_item(seller_rating=95.0)
        self.assertFalse(self.engine.should_filter(item))

    def test_bad_seller_rating_filtered(self):
        """Low seller rating (< 80%) should be filtered out"""
        item = make_item(seller_rating=70.0)
        self.assertTrue(self.engine.should_filter(item))

    def test_zero_seller_rating_passes(self):
        """Zero/seller rating of 0 means unknown, should pass"""
        item = make_item(seller_rating=0.0)
        # No condition and no banned words, so should pass
        self.assertFalse(self.engine.should_filter(item))

    # --- Combined filter tests ---

    def test_multiple_filters_applied(self):
        """Multiple filter conditions are all checked"""
        item = make_item(
            name="ジャンク",  # banned word
            condition="大きな傷や汚れあり",  # bad condition
            seller_rating=50.0,  # low rating
        )
        self.assertTrue(self.engine.should_filter(item))

    def test_perfect_item_passes_all_filters(self):
        """A perfect item should pass all filters"""
        item = make_item(
            name="iPhone 14 Pro",
            condition="新品・未使用",
            description="箱付き、未開封です。",
            seller_rating=99.0
        )
        self.assertFalse(self.engine.should_filter(item))

    # --- Filter reasons tests ---

    def test_get_filtered_reasons_banned_word(self):
        """Should report banned word as filter reason"""
        item = make_item(name="ジャンク品")
        reasons = self.engine.get_filtered_reasons(item)
        self.assertTrue(any("banned" in r.lower() for r in reasons))

    def test_get_filtered_reasons_condition(self):
        """Should report bad condition as filter reason"""
        item = make_item(condition="使用不可")
        reasons = self.engine.get_filtered_reasons(item)
        self.assertTrue(any("condition" in r.lower() for r in reasons))

    def test_get_filtered_reasons_empty_for_passing(self):
        """No filter reasons if item passes"""
        item = make_item(
            name="iPhone 13",
            condition="新品・未使用",
            seller_rating=95.0
        )
        reasons = self.engine.get_filtered_reasons(item)
        self.assertEqual(reasons, [])

    # --- Config customization tests ---

    def test_custom_banned_words(self):
        """Custom banned words from config"""
        engine = FilterEngine({
            "allowed_conditions": [],
            "banned_words": ["修理"]
        })
        item = make_item(name="修理済み")
        self.assertTrue(engine.should_filter(item))

    def test_empty_allowed_conditions(self):
        """No allowed conditions means all pass"""
        engine = FilterEngine({
            "allowed_conditions": [],
            "banned_words": []
        })
        item = make_item(condition="使用不可")
        self.assertFalse(engine.should_filter(item))


if __name__ == "__main__":
    unittest.main()
