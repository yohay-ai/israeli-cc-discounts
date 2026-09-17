import json
from pathlib import Path
from unittest.mock import Mock, patch

from max_benefits_scraper import (
    LOBBY_URL,
    extract_benefits,
    extract_categories,
    normalize_benefits,
    scrape_max_benefits,
)

FIXTURES = Path(__file__).parent / "fixtures"
NOW = "2026-09-17T00:00:00"


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _raw_benefits():
    raw, _ = extract_benefits(_load("max_benefits_category_page0.json"))
    raw2, last = extract_benefits(_load("max_benefits_category_page1.json"))
    assert last is True
    return raw + raw2


def test_extract_categories_includes_navbar_and_dedupes():
    categories = extract_categories(_load("max_benefits_lobby.json"))
    assert categories == ["musicshows", "attractions"]


def test_normalize_fixture_benefits():
    records = normalize_benefits(_raw_benefits(), now_iso=NOW)
    by_name = {record["business_name"]: record for record in records}

    # Out-of-stock, expired and subtitle-less benefits are excluded; the
    # cross-page duplicate id collapses to one record.
    assert "הפרויקט של רביבו - קבלת שבת" in by_name
    assert len(records) == 4

    revivo = by_name["הפרויקט של רביבו - קבלת שבת"]
    assert revivo["club"] == "MAX"
    assert revivo["discount"] == "60 ₪ הנחה (תמורת פינוק)"
    assert revivo["discount_url"] == "https://www.max.co.il/benefits/musicshows/revivoshabat"
    assert revivo["discount_type"] == "voucher"
    assert revivo["discount_value"] is None
    assert revivo["has_physical_store"] is True
    assert revivo["branches"] == []
    assert revivo["category"] == "הופעות חיות"
    assert "עד גמר המלאי" in revivo["limitations"]
    assert "<" not in revivo["limitations"]

    travel = by_name["חדש! אתר MAX Travel, מזמינים חופשה ומקבלים כסף חזרה לחופשה הבאה"]
    assert travel["discount_type"] == "billing_discount"
    assert travel["discount_value"] == 10.0
    assert travel["has_physical_store"] is False

    disney = by_name["דיסנילנד פריז"]
    assert disney["discount_type"] == "voucher"
    assert disney["discount_value"] == 10.0


def test_unset_expiration_date_is_not_expired():
    records = normalize_benefits(_raw_benefits(), now_iso=NOW)
    # id 999003 has filterBenefitByDate=true but an unset (0001-01-01) date.
    assert any(record["discount_url"] for record in records)
    assert len([r for r in records]) == 4


def test_extract_benefits_handles_missing_result():
    benefits, is_last = extract_benefits({})
    assert benefits == []
    assert is_last is False


@patch("max_benefits_scraper.requests.Session")
def test_scrape_walks_categories_until_last_page(mock_session_cls):
    session = Mock()
    mock_session_cls.return_value = session
    lobby = _load("max_benefits_lobby.json")
    page0 = _load("max_benefits_category_page0.json")
    page1 = _load("max_benefits_category_page1.json")
    empty = {"result": {"benefits": [], "isLast": True}}

    def respond(url, **kwargs):
        response = Mock()
        response.raise_for_status = Mock()
        if url == LOBBY_URL:
            response.json = Mock(return_value=lobby)
        elif "category=musicshows" in url and "page=0" in url:
            response.json = Mock(return_value=page0)
        elif "category=musicshows" in url and "page=1" in url:
            response.json = Mock(return_value=page1)
        else:
            response.json = Mock(return_value=empty)
        return response

    session.get.side_effect = respond
    records = scrape_max_benefits(now_iso=NOW)
    assert len(records) == 4
    assert session.get.call_count == 4  # lobby + 2 pages musicshows + 1 page attractions


def test_default_now_iso_skips_date_filtering():
    # Without an explicit now_iso, expiration dates must not be applied:
    # the expired fixture benefit is kept (default means "no date filter").
    records = normalize_benefits(_raw_benefits())
    assert len(records) == 5
