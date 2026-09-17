import unittest

from scripts.join_businesses import build_businesses_with_discounts


class BusinessesWithDiscountsTest(unittest.TestCase):
    def test_attaches_named_discounts_and_appends_missing_geocoded_locations(self):
        stores = [
            {"id": 1, "name": "AHAVA", "type": "shop", "lat": 31.45, "lon": 35.38},
            {"id": 2, "name": "Cafe Deluxe", "type": "cafe", "lat": 32.10, "lon": 34.78},
        ]
        discounts = [
            {"business_name": "AHAVA", "discount": "10%", "discount_type": "billing_discount", "discount_value": 10.0, "has_physical_store": True},
            {"business_name": "Cafe Deluxe", "discount": "15%", "discount_type": "billing_discount", "discount_value": 15.0, "has_physical_store": True},
            {"business_name": "Other Brand", "discount": "7%", "discount_type": "billing_discount", "discount_value": 7.0, "has_physical_store": True},
        ]
        geocoded = [
            {"business_name": "Geocoded Only", "lat": 33.0, "lng": 35.0},
            {"business_name": "AHAVA", "lat": 31.45, "lng": 35.38},
        ]

        built = build_businesses_with_discounts(stores, discounts, geocoded)

        self.assertEqual(len(built), 3)
        self.assertTrue(any(item["name"] == "AHAVA" and item["discounts"] for item in built))
        self.assertTrue(any(item["name"] == "Geocoded Only" for item in built))
        self.assertTrue(any(item["name"] == "AHAVA" and item["lat"] == 31.45 and item["lon"] == 35.38 for item in built))

    def test_preserves_child_program_identity_under_parent(self):
        stores = [{"id": 1, "name": "Store", "type": "shop", "lat": 32.1, "lon": 34.8}]
        discounts = [
            {"business_name": "Store", "club": "חבר שלי", "discount": "10%"},
            {"business_name": "Store", "club": "חבר טעמים", "discount": "8%"},
            {"business_name": "Store", "club": "GiftCard max", "discount": "5%"},
        ]
        built = build_businesses_with_discounts(stores, discounts, [])
        by_club = {d["club"]: d for d in built[0]["discounts"]}
        self.assertEqual(by_club["חבר שלי"]["program_id"], "mcc-sheli")
        self.assertEqual(by_club["חבר שלי"]["parent_program_id"], "mcc")
        self.assertEqual(by_club["חבר טעמים"]["program_id"], "mcc-teamim")
        self.assertEqual(by_club["GiftCard max"]["parent_program_id"], "max")
