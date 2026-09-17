from pathlib import Path
from unittest.mock import Mock, patch

from amex_scraper import SOURCE_URL, parse_amex_html, scrape_amex

FIXTURE = Path(__file__).parent / "fixtures" / "amex_rewards_homepage.html"


def test_parse_amex_fixture():
    records = parse_amex_html(FIXTURE.read_text(encoding="utf-8"))

    # The fixture holds three benefits; the out-of-stock one is excluded.
    assert len(records) == 2

    first = records[0]
    assert first["club"] == "אמריקן אקספרס"
    assert first["business_name"] == "קו רקיע 2026"
    assert first["discount"] == '60 ש"ח הנחה לכרטיס ומשקה ראשון חינם תמורת בונוס'
    assert (
        first["discount_url"]
        == "https://rewards.americanexpress.co.il/link/cdb45007482a49b7ba820a81b3750cd1.aspx"
    )
    assert first["discount_type"] == "voucher"
    assert first["discount_value"] is None
    assert first["has_physical_store"] is True
    assert first["branches"] == []
    assert first["category"] == "הופעות והצגות"
    assert "תמורת הטבת בונוס" in first["limitations"]
    assert "<" not in first["limitations"]

    second = records[1]
    assert second["business_name"] == "שרית חדד בפארק הירקון"
    assert second["discount"] == '50 ש"ח הנחה לכרטיס בתוספת נקודות'
    # Tier pricing from RegularBenefitDesc / PremiumBenefitDesc lands in limitations.
    assert "לכלל הלקוחות בתוספת 300 נקודות" in second["limitations"]
    assert "ללקוחות סנטוריון ופלטינה בתוספת 80 נקודות" in second["limitations"]

    business_names = [record["business_name"] for record in records]
    assert "forever tango" not in " ".join(business_names).lower()


def test_parse_returns_empty_when_epi_payload_is_missing():
    assert parse_amex_html("<html><body>changed markup</body></html>") == []


def test_parse_returns_empty_when_epi_payload_is_not_json():
    assert parse_amex_html("<script>window.epi = {not valid json;</script>") == []


@patch("amex_scraper.requests.get")
def test_scrape_fetches_official_page(mock_get):
    response = Mock(text=FIXTURE.read_text(encoding="utf-8"))
    response.raise_for_status = Mock()
    mock_get.return_value = response
    assert len(scrape_amex()) == 2
    mock_get.assert_called_once()
    assert mock_get.call_args.args[0] == SOURCE_URL
    response.raise_for_status.assert_called_once_with()
