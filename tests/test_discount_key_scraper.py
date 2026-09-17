from pathlib import Path
from unittest.mock import Mock, patch

from discount_key_scraper import SOURCE_URL, parse_discount_key_html, scrape_discount_key

FIXTURE = Path(__file__).parent / "fixtures" / "discount_key_participating_businesses.html"


def test_parse_discount_key_fixture():
    records = parse_discount_key_html(FIXTURE.read_text(encoding="utf-8"))
    assert len(records) == 2
    assert records[0] == {
        "club": "מפתח דיסקונט",
        "business_name": "סקצ'רס",
        "discount": "5% הנחה",
        "discount_url": "https://www.skechers.co.il/",
        "discount_type": "billing_discount",
        "discount_value": 5.0,
        "has_physical_store": True,
        "branches": [],
        "limitations": "ההנחה אינה תקפה בסניפי עודפים.",
        "category": "אופנה ואביזרים",
    }
    assert records[1]["discount_value"] == 4.5
    assert records[1]["discount_url"] == SOURCE_URL
    assert records[1]["has_physical_store"] is False


def test_parse_returns_empty_when_expected_container_is_missing():
    assert parse_discount_key_html("<html><body>changed markup</body></html>") == []


@patch("discount_key_scraper.requests.get")
def test_scrape_fetches_official_page(mock_get):
    response = Mock(text=FIXTURE.read_text(encoding="utf-8"))
    response.raise_for_status = Mock()
    mock_get.return_value = response
    assert len(scrape_discount_key()) == 2
    mock_get.assert_called_once()
    assert mock_get.call_args.args[0] == SOURCE_URL
    response.raise_for_status.assert_called_once_with()
