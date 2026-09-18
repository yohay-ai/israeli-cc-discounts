"""Scraper for the public Isracard benefits site (benefits.isracard.co.il).

The site is server-rendered ASP.NET (Episerver). Its homepage embeds the
entire benefit catalog - roughly 300+ benefits with full descriptions, terms
and per-benefit category - in a `window.epi` JSON object (the same pattern
the Amex source uses). One GET of the homepage yields the whole catalog, so
no category or per-benefit requests are needed.

Access note: isracard.co.il sits behind a Cloudflare rule that blocks
datacenter IPs (ASN-reputation based, not geographic - residential IPs pass,
verified from a US residential exit). Run this from a residential connection;
curl_cffi's chrome impersonation is used when available.
"""

import json
import os
import re
import time
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
    from curl_cffi import requests

    _REQUESTS_KWARGS = {"impersonate": "chrome"}
except ImportError:
    import requests

    _REQUESTS_KWARGS = {}

BASE_URL = "https://benefits.isracard.co.il/"
HEADERS = {
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "he-IL,he;q=0.9",
    "User-Agent": "IsraeliCCDiscounts/1.0 (+https://github.com/yohaybn/israeli-cc-discounts)",
}
# Polite delay before the (single) page fetch; override with ISRCARD_DELAY.
DELAY = float(os.environ.get("ISRCARD_DELAY", "0"))

CLUB_NAME = "ישראכרט"
_ONLINE_CATEGORY = "הטבות אונליין"

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


def _percent_value(*texts: str) -> float | None:
    for text in texts:
        match = _PERCENT_PATTERN.search(text or "")
        if match:
            return float(match.group(1))
    return None


def _fetch(url: str, timeout: int = 30) -> str:
    if DELAY:
        time.sleep(DELAY)
    response = requests.get(url, headers=HEADERS, timeout=timeout, **_REQUESTS_KWARGS)
    response.raise_for_status()
    return response.text


def _normalize_benefit(benefit: dict[str, Any]) -> dict[str, Any] | None:
    discount_text = _clean(benefit.get("MobileBenefitName") or "")
    link = benefit.get("LinkUrl") or ""
    if not discount_text or not link:
        return None
    business = _clean(benefit.get("TitlePart1") or benefit.get("MobileDescription") or "")
    category = _clean((benefit.get("Category") or {}).get("Name") or "")
    limitations = _html_to_text(benefit.get("BenefitPageDescText") or "")
    if benefit.get("IsPremium"):
        limitations = _clean("הטבת פרימיום. " + limitations)
    address = _clean(benefit.get("SupplierAddress") or "")
    if address:
        limitations = _clean(limitations + " כתובת: " + address)
    record = {
        "club": CLUB_NAME,
        "business_name": business or discount_text,
        "discount": discount_text,
        "discount_url": urljoin(BASE_URL, link),
        "discount_type": "voucher",
        "discount_value": _percent_value(discount_text, limitations[:300]),
        "has_physical_store": category != _ONLINE_CATEGORY,
        "branches": [],
        "limitations": limitations,
    }
    if category:
        record["category"] = category
    return record


def parse_homepage(html: str) -> list[dict[str, Any]]:
    """Normalize every benefit embedded in the homepage's `window.epi` payload."""
    epi = _extract_epi_json(html)
    if not epi:
        return []
    benefits = (epi.get("CurrentPage") or {}).get("Benefits") or []
    records = []
    seen: set[str] = set()
    for benefit in benefits:
        if benefit.get("OutOfStock"):
            continue
        record = _normalize_benefit(benefit)
        if record and record["discount_url"] not in seen:
            seen.add(record["discount_url"])
            records.append(record)
    return records


def scrape_isracard(timeout: int = 30) -> list[dict[str, Any]]:
    return parse_homepage(_fetch(BASE_URL, timeout=timeout))


if __name__ == "__main__":
    discounts = scrape_isracard()
    print(f"Extracted {len(discounts)} Isracard benefits")
    for item in discounts[:5]:
        print(item)
