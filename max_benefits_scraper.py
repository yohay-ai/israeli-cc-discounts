"""Scraper for the public MAX (max.co.il) benefits catalog API."""

import re
from typing import Any

from bs4 import BeautifulSoup

try:
    from curl_cffi import requests

    _REQUESTS_KWARGS = {"impersonate": "chrome"}
except ImportError:
    import requests

    _REQUESTS_KWARGS = {}

BASE_URL = "https://www.max.co.il"
LOBBY_URL = f"{BASE_URL}/api/benefits/getLobby"
CATEGORY_URL = (
    f"{BASE_URL}/api/benefits/getCategoriesLobby"
    "?isMobile=false&page={page}&loadLobby=true&category={category}"
    "&club=undefined&region=undefined"
)
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "IsraeliCCDiscounts/1.0 (+https://github.com/yohaybn/israeli-cc-discounts)",
}

CLUB_NAME = "MAX"
MAX_PAGES_PER_CATEGORY = 50

_PERCENT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_ONLINE_ONLY_PATTERN = re.compile(r"אונליין|און-ליין|באתר|באפליקציה|online", re.IGNORECASE)
_CASHBACK_PATTERN = re.compile(r"קאשבק|כסף בחזרה|כסף חזרה")


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _html_to_text(value: str) -> str:
    if not value:
        return ""
    return _clean(BeautifulSoup(value, "html.parser").get_text(" ", strip=True))


def _is_expired(benefit: dict[str, Any], now_iso: str) -> bool:
    if not benefit.get("filterBenefitByDate"):
        return False
    expiration = benefit.get("publishingExpirationDate") or ""
    if expiration.startswith("0001"):
        return False
    return expiration < now_iso


def extract_categories(lobby_payload: dict[str, Any]) -> list[str]:
    """Collect category urlNames from the lobby payload (main + nav bar lists)."""
    result = lobby_payload.get("result") or {}
    url_names: list[str] = []
    seen: set[str] = set()
    for key in ("categories", "navBarCategories"):
        for category in result.get(key) or []:
            if not isinstance(category, dict):
                continue
            url_name = (category.get("urlName") or "").strip()
            if url_name and url_name not in seen:
                seen.add(url_name)
                url_names.append(url_name)
    return url_names


def extract_benefits(category_payload: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    """Return (raw benefits, is_last_page) from one getCategoriesLobby page."""
    result = category_payload.get("result") or {}
    benefits = [b for b in (result.get("benefits") or []) if isinstance(b, dict)]
    return benefits, bool(result.get("isLast"))


def normalize_benefit(benefit: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize one raw MAX benefit into the project's shared schema."""
    business_name = _clean(benefit.get("title") or benefit.get("name") or "")
    discount_text = _clean(benefit.get("subTitle") or "")
    if not business_name or not discount_text:
        return None

    discount_url = _clean(benefit.get("benefitUrl") or "") or BASE_URL

    channel = benefit.get("benefitChannel")
    asterisk = channel.get("asteriskText") if isinstance(channel, dict) else ""
    limitations = _html_to_text(asterisk or "")

    categories = benefit.get("category") or []
    category_name = ""
    if categories and isinstance(categories[0], dict):
        category_name = _clean(categories[0].get("name") or "")

    percent_match = _PERCENT_PATTERN.search(discount_text)
    online_only = bool(_ONLINE_ONLY_PATTERN.search(discount_text))
    discount_type = "billing_discount" if _CASHBACK_PATTERN.search(discount_text) else "voucher"

    record: dict[str, Any] = {
        "club": CLUB_NAME,
        "business_name": business_name,
        "discount": discount_text,
        "discount_url": discount_url,
        "discount_type": discount_type,
        "discount_value": float(percent_match.group(1)) if percent_match else None,
        "has_physical_store": not online_only,
        "branches": [],
        "limitations": limitations,
    }
    if category_name:
        record["category"] = category_name
    return record


def normalize_benefits(
    raw_benefits: list[dict[str, Any]], now_iso: str | None = None
) -> list[dict[str, Any]]:
    """Normalize raw benefits: skip expired/out-of-stock, dedupe by id."""
    records: list[dict[str, Any]] = []
    seen_ids: set[Any] = set()
    for benefit in raw_benefits:
        if benefit.get("isOutOfStock") or (now_iso is not None and _is_expired(benefit, now_iso)):
            continue
        benefit_id = benefit.get("id")
        if benefit_id in seen_ids:
            continue
        seen_ids.add(benefit_id)
        record = normalize_benefit(benefit)
        if record:
            records.append(record)
    return records


def _get_json(session: Any, url: str, timeout: int) -> dict[str, Any]:
    response = session.get(url, headers=HEADERS, timeout=timeout, **_REQUESTS_KWARGS)
    response.raise_for_status()
    return response.json()


def scrape_max_benefits(timeout: int = 30, now_iso: str | None = None) -> list[dict[str, Any]]:
    """Fetch the full public MAX benefits catalog and normalize it."""
    session = requests.Session()
    categories = extract_categories(_get_json(session, LOBBY_URL, timeout))

    raw: list[dict[str, Any]] = []
    for url_name in categories:
        for page in range(MAX_PAGES_PER_CATEGORY):
            payload = _get_json(session, CATEGORY_URL.format(page=page, category=url_name), timeout)
            benefits, is_last = extract_benefits(payload)
            raw.extend(benefits)
            if is_last or not benefits:
                break

    return normalize_benefits(raw, now_iso=now_iso)


if __name__ == "__main__":
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    discounts = scrape_max_benefits(now_iso=now)
    print(f"Extracted {len(discounts)} MAX benefits")
    for item in discounts[:5]:
        print(item)
