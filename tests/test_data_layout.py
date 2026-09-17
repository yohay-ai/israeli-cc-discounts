import os
import unittest


class DataLayoutTest(unittest.TestCase):
    def test_docs_data_contains_only_frontend_files(self):
        frontend_files = {
            "docs/data/all_combined_discounts.json",
            "docs/data/businesses_with_discounts.json",
            "docs/data/data_freshness.json",
        }
        forbidden_files = {
            "docs/data/mcc_discounts.json",
            "docs/data/hot_discounts.json",
            "docs/data/htzone_discounts.json",
            "docs/data/buyme_discounts.json",
            "docs/data/hvr_rechargeable_cards.json",
            "docs/data/scrape_metadata.json",
            "docs/data/unmatched_discounts.json",
        }

        self.assertTrue(all(os.path.exists(path) for path in frontend_files))
        self.assertFalse(any(os.path.exists(path) for path in forbidden_files))

        self.assertTrue(os.path.exists("data/mcc_discounts.json"))
        self.assertTrue(os.path.exists("data/all_combined_discounts.json"))

        businesses_dir = "docs/data/businesses"
        if os.path.isdir(businesses_dir):
            region_files = {
                "docs/data/businesses/businesses_center.json",
                "docs/data/businesses/businesses_north.json",
                "docs/data/businesses/businesses_south.json",
                "docs/data/businesses/businesses_eilat_arava.json",
            }
            self.assertTrue(any(os.path.exists(path) for path in region_files))
