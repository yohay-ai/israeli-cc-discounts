from datetime import datetime, timezone
import html
import json
import os
import re
from hot_scraper import scrape_hot
from htzone_scraper import scrape_htzone
from mcc_scraper import scrape_mcc
from hvr_scraper import scrape_hvr_rechargeable_cards
from max_giftcard_scraper import scrape_max
from buyme_scraper import scrape_buyme_suppliers, stores_to_discounts

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
DISCOUNTS_DIR = os.path.join(DATA_DIR, "discounts")

DOCS_DATA_DIR = os.path.join(BASE_DIR, "docs", "data")
PUBLISHED_FRESHNESS_FILE = os.path.join(DOCS_DATA_DIR, "data_freshness.json")


def clean_discount_text(value):
    """Convert scraper-provided HTML fragments into readable plain text."""
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_dedupe_value(value):
    if value is None:
        return ""
    return str(value).strip().lower().replace("\u00a0", " ")


def deduplicate_records(items):
    seen = set()
    deduped = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key = (
            normalize_dedupe_value(item.get("club")),
            normalize_dedupe_value(item.get("business_name")),
            normalize_dedupe_value(item.get("discount")),
            normalize_dedupe_value(item.get("discount_url")),
            normalize_dedupe_value(item.get("discount_type")),
            normalize_dedupe_value(item.get("discount_value")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def load_existing_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return data
                elif isinstance(data, dict):
                    return data
        except Exception as e:
            print(f"[Warning] Could not load fallback JSON from {filepath}: {e}")
    return None


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(DOCS_DATA_DIR, exist_ok=True)
    print("================ STARTING CARDS COMPARISON SCRAPER ================\n")

    mcc_path = os.path.join(DISCOUNTS_DIR, "mcc_discounts.json")
    hot_path = os.path.join(DISCOUNTS_DIR, "hot_discounts.json")
    htzone_path = os.path.join(DISCOUNTS_DIR, "htzone_discounts.json")
    buyme_path = os.path.join(DISCOUNTS_DIR, "buyme_discounts.json")
    hvr_path = os.path.join(DISCOUNTS_DIR, "hvr_rechargeable_cards.json")
    combined_path = os.path.join(DISCOUNTS_DIR, "all_combined_discounts.json")
    metadata_path = os.path.join(DISCOUNTS_DIR, "scrape_metadata.json")
    publish_combined_path = os.path.join(DOCS_DATA_DIR, "all_combined_discounts.json")


    # Load existing metadata if available
    metadata = load_existing_json(metadata_path)
    if not isinstance(metadata, dict):
        metadata = {}

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. Scrape MCC
    mcc_data = scrape_mcc()
    if mcc_data and len(mcc_data) > 0:
        with open(mcc_path, "w", encoding="utf-8") as f:
            json.dump(mcc_data, f, ensure_ascii=False, indent=4)
        metadata["mcc"] = {
            "last_successful_scrape": now_iso,
            "count": len(mcc_data),
        }
        print(f"--> Saved {len(mcc_data)} normalized MCC items to {mcc_path}.\n")
    else:
        print(
            f"[WARNING] MCC Scraper returned 0 items. Retaining previous data"
            f" from {mcc_path}.\n"
        )
        mcc_data = load_existing_json(mcc_path) or []

    # 2. Scrape HOT
    hot_data = scrape_hot()
    if hot_data and len(hot_data) > 0:
        with open(hot_path, "w", encoding="utf-8") as f:
            json.dump(hot_data, f, ensure_ascii=False, indent=4)
        metadata["hot"] = {
            "last_successful_scrape": now_iso,
            "count": len(hot_data),
        }
        print(f"--> Saved {len(hot_data)} normalized HOT items to {hot_path}.\n")
    else:
        print(
            f"[WARNING] HOT Scraper returned 0 items. Retaining previous data"
            f" from {hot_path}.\n"
        )
        hot_data = load_existing_json(hot_path) or []

    # 3. Scrape HTzone
    htzone_data = scrape_htzone()
    if htzone_data and len(htzone_data) > 0:
        with open(htzone_path, "w", encoding="utf-8") as f:
            json.dump(htzone_data, f, ensure_ascii=False, indent=4)
        metadata["htzone"] = {
            "last_successful_scrape": now_iso,
            "count": len(htzone_data),
        }
        print(
            f"--> Saved {len(htzone_data)} normalized HTzone items to"
            f" {htzone_path}.\n"
        )
    else:
        print(
            f"[WARNING] HTzone Scraper returned 0 items. Retaining previous"
            f" data from {htzone_path}.\n"
        )
        htzone_data = load_existing_json(htzone_path) or []

    # 4. Scrape HVR rechargeable cards (club-linked gift card / prepaid card items)
    hvr_data = scrape_hvr_rechargeable_cards()
    if hvr_data and len(hvr_data) > 0:
        with open(hvr_path, "w", encoding="utf-8") as f:
            json.dump(hvr_data, f, ensure_ascii=False, indent=4)
        metadata["hvr_rechargeable_cards"] = {
            "last_successful_scrape": now_iso,
            "count": len(hvr_data),
            "output_file": os.path.relpath(hvr_path, start=os.path.dirname(__file__)),
        }
        print(f"--> Saved {len(hvr_data)} HVR rechargeable-card items to {hvr_path}.\n")
    else:
        print("[WARNING] HVR rechargeable-card scraper returned 0 items.\n")
        hvr_data = load_existing_json(hvr_path) or []

    # 4.5 Scrape MAX gift cards
    max_path = os.path.join(DISCOUNTS_DIR, "max_discounts.json")
    max_data = scrape_max()
    if max_data and len(max_data) > 0:
        with open(max_path, "w", encoding="utf-8") as f:
            json.dump(max_data, f, ensure_ascii=False, indent=4)
        metadata["max"] = {
            "last_successful_scrape": now_iso,
            "count": len(max_data),
        }
        print(f"--> Saved {len(max_data)} normalized MAX items to {max_path}.\n")
    else:
        print(f"[WARNING] MAX Scraper returned 0 items. Retaining previous data from {max_path}.\n")
        max_data = load_existing_json(max_path) or []

    # 5. Scrape BUYME (voucher-type suppliers)
    buyme_result = scrape_buyme_suppliers(out_dir=DATA_DIR)
    buyme_stores = buyme_result.get("stores", [])
    buyme_counts = buyme_result.get("supplier_counts", {})
    buyme_discounts = stores_to_discounts(buyme_stores) if buyme_stores else []
    if buyme_discounts:
        with open(buyme_path, "w", encoding="utf-8") as f:
            json.dump(buyme_discounts, f, ensure_ascii=False, indent=4)
        print(f"--> Saved {len(buyme_discounts)} normalized BuyMe items to {buyme_path}.")
    else:
        buyme_discounts = load_existing_json(buyme_path) or []
        print("[WARNING] BuyMe scraper returned 0 items; keeping prior normalized file.")
    metadata["buyme"] = {
        "last_successful_scrape": now_iso,
        "supplier_counts": buyme_counts,
        "total_stores": len(buyme_stores),
        "output_file": os.path.relpath(buyme_path, start=os.path.dirname(__file__)),
    }
    print(f"--> Normalized {len(buyme_stores)} BuyMe store entries for the combined dataset.")

    # 6. Create Combined Card Comparison File
    combined_list = mcc_data + hot_data + htzone_data + hvr_data + max_data

    # Append Buyme discounts (normalized) to combined list
    if buyme_discounts:
        combined_list = combined_list + buyme_discounts
        print(f"--> Added {len(buyme_discounts)} buyme discounts to combined dataset.")

    for item in combined_list:
        if isinstance(item, dict):
            item["discount"] = clean_discount_text(item.get("discount"))

    combined_list = deduplicate_records(combined_list)
    print(f"--> Deduplicated combined dataset to {len(combined_list)} unique records.")

    # Normalization pass: canonicalize club names and backfill discount_type/discount_value
    club_aliases = {
        "חבר": "חבר",
        "MCC": "חבר",
        "mcc": "חבר",
        "HOT": "HOT",
        "hot": "HOT",
        "HTzone": "HTzone",
        "htzone": "HTzone",
    }

    for item in combined_list:
        # Normalize club names
        club = (item.get("club") or "").strip()
        item["club"] = club_aliases.get(club, club)

        # Backfill discount_type when missing
        if not item.get("discount_type"):
            item["discount_type"] = "billing_discount"

        # Backfill discount_value when missing (try percent extraction)
        if item.get("discount_value") is None:
            disc = item.get("discount") or ""
            m = re.search(r"(\d+(?:\.\d+)?)\s*%", disc)
            if m:
                try:
                    item["discount_value"] = float(m.group(1))
                except Exception:
                    item["discount_value"] = None
            else:
                item["discount_value"] = None

    if combined_list:
        with open(combined_path, "w", encoding="utf-8") as f:
            json.dump(combined_list, f, ensure_ascii=False, indent=4)
        with open(publish_combined_path, "w", encoding="utf-8") as f:
            json.dump(combined_list, f, ensure_ascii=False, indent=4)
        metadata["all_combined"] = {
            "last_updated": now_iso,
            "total_count": len(combined_list),
        }
        print(
            f"--> Updated combined file {combined_path} and published a static copy to {publish_combined_path} with"
            f" {len(combined_list)} total records."
        )

        # Add counts by discount_type to metadata
        type_counts = {}
        for item in combined_list:
            t = item.get("discount_type") or "unknown"
            type_counts[t] = type_counts.get(t, 0) + 1
        metadata["discount_type_counts"] = type_counts

    # 5. Save Metadata File
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=4)
    print(f"--> Updated scrape metadata in {metadata_path}.")

    freshness = {
        "published_at": metadata.get("all_combined", {}).get("last_updated"),
        "sources": {
            key: value.get("last_successful_scrape")
            for key, value in metadata.items()
            if isinstance(value, dict) and value.get("last_successful_scrape")
        },
    }
    with open(PUBLISHED_FRESHNESS_FILE, "w", encoding="utf-8") as f:
        json.dump(freshness, f, ensure_ascii=False, indent=2)
    print(f"--> Published data freshness metadata to {PUBLISHED_FRESHNESS_FILE}.")

    print("\n================ FINISHED PROCESS ================")
    print(
        f"Total normalized records in combined dataset: {len(combined_list)}"
    )


if __name__ == "__main__":
    main()