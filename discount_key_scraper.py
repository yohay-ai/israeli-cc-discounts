"""Scraper for the public Discount Key participating-business list."""

import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
    from curl_cffi import requests
except ImportError:
    import requests

SOURCE_URL = (
    "https://www.discountbank.co.il/private/credit-cards/discount-key/"
    "discount_key-participating_businesses/"
)
HEADERS = {
    "Accept": "text/html,application/xhtml+xml",
    "User-Agent": "IsraeliCCDiscounts/1.0 (+https://github.com/yohaybn/israeli-cc-discounts)",
}


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _split_heading(value: str) -> tuple[str, str | None]:
    heading = _clean(value)
    match = re.match(r"^(.*?)\s*\[([^\[\]]+)\]\s*$", heading)
    if not match:
        return heading, None
    return _clean(match.group(1)), _clean(match.group(2))


def _merchant_url(answer: Any) -> str:
    for link in answer.select("a[href]"):
        href = (link.get("href") or "").strip()
        if href.startswith(("http://", "https://")):
            return href
    return SOURCE_URL


def parse_discount_key_html(html: str) -> list[dict[str, Any]]:
    """Parse Discount Bank's accordion list into the project's normalized schema."""
    soup = BeautifulSoup(html, "html.parser")
    container = soup.select_one(".faq-items-wrap.accordeon")
    if container is None:
        return []

    children = [node for node in container.children if getattr(node, "name", None)]
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, float]] = set()

    for index, node in enumerate(children):
        if "question" not in (node.get("class") or []):
            continue
        answer = next(
            (
                candidate
                for candidate in children[index + 1 :]
                if "answer" in (candidate.get("class") or [])
                or "question" in (candidate.get("class") or [])
            ),
            None,
        )
        if answer is None or "answer" not in (answer.get("class") or []):
            continue

        heading = node.select_one(".question-heading") or node
        business_name, category = _split_heading(heading.get_text(" ", strip=True))
        answer_text = _clean(answer.get_text(" ", strip=True))
        percent_match = re.search(r"(\d+(?:\.\d+)?)\s*%(?:\s*הנחה)?", answer_text)
        if not business_name or percent_match is None:
            continue

        discount_value = float(percent_match.group(1))
        key = (business_name.casefold(), discount_value)
        if key in seen:
            continue
        seen.add(key)

        limitations = re.sub(
            r"^.*?\d+(?:\.\d+)?\s*%(?:\s*הנחה)?\s*(?:למחזיקי מפתח דיסקונט)?",
            "",
            answer_text,
            count=1,
        )
        limitations = re.sub(r"(?:לאתר|באתר|לרכישה באתר)\s*>?\s*$", "", limitations).strip()
        online_only = "באתר בלבד" in answer_text or "רק באתר" in answer_text

        record: dict[str, Any] = {
            "club": "מפתח דיסקונט",
            "business_name": business_name,
            "discount": f"{percent_match.group(1)}% הנחה",
            "discount_url": _merchant_url(answer),
            "discount_type": "billing_discount",
            "discount_value": discount_value,
            "has_physical_store": not online_only,
            "branches": [],
            "limitations": limitations,
        }
        if category:
            record["category"] = category
        records.append(record)

    return records


def scrape_discount_key(timeout: int = 30) -> list[dict[str, Any]]:
    response = requests.get(SOURCE_URL, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return parse_discount_key_html(response.text)


if __name__ == "__main__":
    discounts = scrape_discount_key()
    print(f"Extracted {len(discounts)} Discount Key businesses")
    for item in discounts[:5]:
        print(item)
