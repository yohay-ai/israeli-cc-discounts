"""Scraper for the public American Express Israel benefits site."""

import json
import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
    from curl_cffi import requests

    _REQUESTS_KWARGS = {"impersonate": "chrome"}
except ImportError:
    import requests

    _REQUESTS_KWARGS = {}

SOURCE_URL = "https://rewards.americanexpress.co.il/"
HEADERS = {
    "Accept": "text/html,application/xhtml+xml",
    "User-Agent": "IsraeliCCDiscounts/1.0 (+https://github.com/yohaybn/israeli-cc-discounts)",
}

CLUB_NAME = "אמריקן אקספרס"

_ONLINE_ONLY_PATTERN = re.compile(r"אונליין|באתר בלבד|רק באתר|online", re.IGNORECASE)
_PERCENT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _html_to_text(value: str) -> str:
    """Convert an HTML fragment from the embedded payload into plain text."""
    if not value:
        return ""
    return _clean(BeautifulSoup(value, "html.parser").get_text(" ", strip=True))


def _extract_epi_json(html: str) -> dict[str, Any] | None:
    """Pull the `window.epi` JSON object out of the server-rendered page."""
    marker = "window.epi = "
    index = html.find(marker)
    if index == -1:
        return None
    start = html.find("{", index + len(marker))
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False
    for position in range(start, len(html)):
        char = html[position]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        else:
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        payload = json.loads(html[start : position + 1])
                    except (ValueError, TypeError):
                        return None
                    return payload if isinstance(payload, dict) else None
    return None


def _split_name(full_name: str) -> tuple[str, str]:
    """Split 'business - discount text' into its two parts.

    The separator dash is not always followed by a space (e.g. 'ברנר -50 ש"ח'),
    so split on the first whitespace-preceded dash.
    """
    name = _clean(full_name)
    parts = re.split(r"\s+-\s*", name, maxsplit=1)
    if len(parts) == 2:
        return _clean(parts[0]), _clean(parts[1])
    return name, ""


def _tier_descriptions(benefit: dict[str, Any]) -> list[str]:
    tiers = []
    for key in ("RegularBenefitDesc", "PremiumBenefitDesc", "BonusBenefitDesc"):
        text = _clean(benefit.get(key) or "")
        if text:
            tiers.append(text)
    return tiers


def parse_amex_html(html: str) -> list[dict[str, Any]]:
    """Parse the Amex rewards homepage into the project's normalized schema."""
    payload = _extract_epi_json(html)
    if not payload:
        return []

    benefits = ((payload.get("CurrentPage") or {}).get("Benefits")) or []
    records: list[dict[str, Any]] = []
    seen_ids: set[Any] = set()

    for benefit in benefits:
        if not isinstance(benefit, dict):
            continue
        if benefit.get("OutOfStock"):
            continue

        benefit_id = benefit.get("BenefitId")
        if benefit_id in seen_ids:
            continue
        seen_ids.add(benefit_id)

        business_name, discount_text = _split_name(benefit.get("MobileBenefitName") or "")
        if not business_name:
            continue
        if not discount_text:
            discount_text = " / ".join(_tier_descriptions(benefit))
        if not discount_text:
            continue

        link_path = (benefit.get("LinkUrl") or "").strip()
        discount_url = urljoin(SOURCE_URL, link_path) if link_path else SOURCE_URL

        description_text = _html_to_text(benefit.get("BenefitPageDescText") or "")
        conditions = _html_to_text(benefit.get("BenefitConditionText") or "")
        limitations_parts = _tier_descriptions(benefit)
        if conditions:
            limitations_parts.append(conditions)
        limitations = " | ".join(limitations_parts)

        percent_match = _PERCENT_PATTERN.search(discount_text)
        online_only = bool(
            _ONLINE_ONLY_PATTERN.search(discount_text)
            or _ONLINE_ONLY_PATTERN.search(description_text)
        )

        record: dict[str, Any] = {
            "club": CLUB_NAME,
            "business_name": business_name,
            "discount": discount_text,
            "discount_url": discount_url,
            "discount_type": "voucher",
            "discount_value": float(percent_match.group(1)) if percent_match else None,
            "has_physical_store": not online_only,
            "branches": [],
            "limitations": limitations,
        }

        category = benefit.get("Category") or {}
        category_name = _clean(category.get("Name") or "")
        if category_name:
            record["category"] = category_name

        records.append(record)

    return records


def scrape_amex(timeout: int = 30) -> list[dict[str, Any]]:
    response = requests.get(SOURCE_URL, headers=HEADERS, timeout=timeout, **_REQUESTS_KWARGS)
    response.raise_for_status()
    return parse_amex_html(response.text)


if __name__ == "__main__":
    discounts = scrape_amex()
    print(f"Extracted {len(discounts)} American Express benefits")
    for item in discounts[:5]:
        print(item)
