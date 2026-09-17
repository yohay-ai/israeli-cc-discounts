import json
import unittest

from main import clean_discount_text


class PublishedDataTest(unittest.TestCase):
    def test_clean_discount_text_removes_html_fragments(self):
        self.assertEqual(
            clean_discount_text('10%<br/> בשימוש באתר &amp; באפליקציה'),
            '10% בשימוש באתר & באפליקציה',
        )
        self.assertEqual(clean_discount_text('מבצע<br>  <strong>מיוחד</strong>'), 'מבצע מיוחד')

    def test_published_freshness_has_timestamp(self):
        with open('docs/data/data_freshness.json', encoding='utf-8') as file:
            freshness = json.load(file)
        self.assertTrue(freshness.get('published_at'))
