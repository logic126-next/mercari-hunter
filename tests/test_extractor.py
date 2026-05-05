"""Test for MercariExtractor"""
import unittest
from src.extractor import MercariExtractor


class TestMercariExtractor(unittest.TestCase):
    
    def setUp(self):
        self.extractor = MercariExtractor()
    
    def test_parse_price_with_yen_symbol(self):
        """Parse price string with yen symbol and commas"""
        self.assertEqual(self.extractor._parse_price("¥15,000"), 15000)
        self.assertEqual(self.extractor._parse_price("¥3,200"), 3200)
    
    def test_parse_price_without_yen_symbol(self):
        """Parse price string without yen symbol"""
        self.assertEqual(self.extractor._parse_price("15000"), 15000)
        self.assertEqual(self.extractor._parse_price("1,500"), 1500)
    
    def test_parse_empty_price(self):
        """Parse empty/invalid price strings"""
        self.assertEqual(self.extractor._parse_price(""), 0)
        self.assertEqual(self.extractor._parse_price("N/A"), 0)
    
    def test_extract_mercari_id_from_url(self):
        """Extract mercari ID from URL"""
        url = "https://jp.mercari.com/items/c123456789"
        self.assertEqual(
            self.extractor._extract_mercari_id(url), 
            "c123456789"
        )
    
    def test_extract_mercari_id_from_short_url(self):
        """Extract mercari ID from short URL"""  
        url = "/items/c/abcdef123"
        self.assertEqual(
            self.extractor._extract_mercari_id(url),
            "cabcdef123"
        )


if __name__ == '__main__':
    unittest.main()
