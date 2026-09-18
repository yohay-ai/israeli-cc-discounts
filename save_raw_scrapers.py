#!/usr/bin/env python3
"""Save one-page / raw responses for each scraper to `data/raw/` for debugging.

Usage:
  python save_raw_scrapers.py --all
  python save_raw_scrapers.py --scrapers htzone,hot
  python save_raw_scrapers.py --buyme 13438757
"""
import argparse
import json
import os
import re
import time
from typing import Optional

try:
    from curl_cffi import requests
except ImportError:
    import requests


BASE_DIR = os.path.dirname(__file__)
RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
os.makedirs(RAW_DIR, exist_ok=True)


def _write(path: str, data: bytes | str, mode: str = "wb") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, mode) as f:
        if "b" in mode and isinstance(data, str):
            data = data.encode("utf-8")
        f.write(data)


def save_htzone_raw(page_id: int = 62, batch_size: int = 50) -> None:
    """POST the HTzone AJAX endpoint and save the JSON + HTML returned for start=0."""
    URL = "https://www.htzone.co.il/_ajax/ajax.index.php"
    HEADERS = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "origin": "https://www.htzone.co.il",
        "referer": f"https://www.htzone.co.il/sale/{page_id}",
        "user-agent": "Mozilla/5.0",
        "x-requested-with": "XMLHttpRequest",
    }

    session = requests.Session()
    payload = {
        "act": "get_sale_html",
        "start": "0",
        "count": str(batch_size),
        "filter": "1",
        "page_id": str(page_id),
        "brand": "[]",
        "date": "[]",
        "area": "[]",
        "category": "[]",
        "file": "sale",
    }

    try:
        res = session.post(URL, headers=HEADERS, data=payload, timeout=15)
    except Exception as e:
        print(f"[HTzone] Request failed: {e}")
        return

    out_dir = os.path.join(RAW_DIR, "htzone")
    os.makedirs(out_dir, exist_ok=True)
    # save raw response body
    _write(os.path.join(out_dir, f"page_{page_id}_resp.txt"), res.text, mode="w")
    # try save JSON if decodable
    try:
        obj = res.json()
        _write(os.path.join(out_dir, f"page_{page_id}.json"), json.dumps(obj, ensure_ascii=False, indent=2), mode="w")
    except Exception:
        pass
    print(f"[HTzone] Saved raw output to {out_dir}")


def save_hot_raw(page: int = 1) -> None:
    HOT_API_URL = "https://api.hot.co.il/api/website/2.0/getCategoryBenefits/?benefitType=100"
    HEADERS = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "user-agent": "Mozilla/5.0",
    }
    session = requests.Session()
    payload = {"page": str(page), "size": "100", "category": "688", "benefitType": "100", "sessionToken": "null"}
    try:
        res = session.post(HOT_API_URL, headers=HEADERS, json=payload, timeout=15)
    except Exception as e:
        print(f"[HOT] Request failed: {e}")
        return

    out_dir = os.path.join(RAW_DIR, "hot")
    os.makedirs(out_dir, exist_ok=True)
    _write(os.path.join(out_dir, f"page_{page}_resp.txt"), res.text, mode="w")
    try:
        obj = res.json()
        _write(os.path.join(out_dir, f"page_{page}.json"), json.dumps(obj, ensure_ascii=False, indent=2), mode="w")
    except Exception:
        pass
    print(f"[HOT] Saved raw output to {out_dir}")


def save_mcc_raw() -> None:
    MCC_URL = "https://www.mcc.co.il/st_reshet_public.aspx"
    session = requests.Session()
    try:
        main = session.get(MCC_URL, timeout=20)
    except Exception as e:
        print(f"[MCC] Main page request failed: {e}")
        return

    out_dir = os.path.join(RAW_DIR, "mcc")
    os.makedirs(out_dir, exist_ok=True)
    _write(os.path.join(out_dir, "main_page.html"), main.text, mode="w")

    # attempt to find first subcategory and POST once to capture one result page
    js_match = re.search(r"var new_types = new Array\s*\((.*?)\);", main.text, re.DOTALL)
    if js_match:
        raw = js_match.group(1)
        tuples = re.findall(r"new Array\((\d+),(\d+),'([^']+)'\)", raw)
        if tuples:
            main_id, sub_id, _ = tuples[0]
            payload = {
                "is_searching": "0",
                "region": "0",
                "second_type": sub_id,
                "txtSearch": "",
                "cmb_main_type": main_id,
                "cmb_second_type_i": sub_id,
                "cmb_region2": "0",
                "mode": "",
                "search_method": "type",
                "main_type": main_id,
                "second_type_i": sub_id,
                "region2": "0",
            }
            try:
                post = session.post(MCC_URL, data=payload, timeout=15)
                _write(os.path.join(out_dir, f"sub_{sub_id}_resp.html"), post.text, mode="w")
                print(f"[MCC] Saved main page and one subcategory response to {out_dir}")
                return
            except Exception as e:
                print(f"[MCC] Subcategory request failed: {e}")

    print(f"[MCC] Saved main page to {out_dir} (no subcategory response)")


def save_hvr_raw() -> None:
    HVR_BASE = "https://www.hvr.co.il/bs2/datasets"
    datasets = {
        "giftcard": f"{HVR_BASE}/giftcard.json",
        "teamimcard_branches": f"{HVR_BASE}/teamimcard_branches.json",
    }
    session = requests.Session()
    out_dir = os.path.join(RAW_DIR, "hvr")
    os.makedirs(out_dir, exist_ok=True)
    for name, url in datasets.items():
        try:
            res = session.get(url, timeout=20)
            _write(os.path.join(out_dir, f"{name}.json"), res.text, mode="w")
            print(f"[HVR] Saved {name} -> {out_dir}")
        except Exception as e:
            print(f"[HVR] Failed to fetch {url}: {e}")


def save_buyme_raw(supplier_id: int) -> None:
    session = requests.Session()
    base_options = f"https://buyme.co.il/brands/{supplier_id}/options"
    supplier_url = f"https://buyme.co.il/supplier/{supplier_id}"
    out_dir = os.path.join(RAW_DIR, "buyme", str(supplier_id))
    os.makedirs(out_dir, exist_ok=True)

    try:
        opt = session.get(base_options, timeout=15)
        _write(os.path.join(out_dir, "options.json"), opt.text, mode="w")
    except Exception as e:
        print(f"[BUYME] Options fetch failed for {supplier_id}: {e}")

    try:
        sup = session.get(supplier_url, timeout=15)
        _write(os.path.join(out_dir, "supplier_page.html"), sup.text, mode="w")
    except Exception as e:
        print(f"[BUYME] Supplier page fetch failed for {supplier_id}: {e}")

    print(f"[BUYME] Saved raw buyme data for supplier {supplier_id} to {out_dir}")



def save_discount_key_raw() -> None:
    from discount_key_scraper import HEADERS, SOURCE_URL

    out_dir = os.path.join(RAW_DIR, "discount_key")
    os.makedirs(out_dir, exist_ok=True)
    try:
        response = requests.get(SOURCE_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
        _write(os.path.join(out_dir, "participating_businesses.html"), response.text, mode="w")
        print(f"[Discount Key] Saved participating-business page to {out_dir}")
    except Exception as e:
        print(f"[Discount Key] Request failed: {e}")


def save_amex_raw() -> None:
    from amex_scraper import HEADERS, SOURCE_URL, _REQUESTS_KWARGS

    out_dir = os.path.join(RAW_DIR, "amex")
    os.makedirs(out_dir, exist_ok=True)
    try:
        response = requests.get(SOURCE_URL, headers=HEADERS, timeout=30, **_REQUESTS_KWARGS)
        response.raise_for_status()
        _write(os.path.join(out_dir, "rewards_homepage.html"), response.text, mode="w")
        print(f"[Amex] Saved rewards homepage to {out_dir}")
    except Exception as e:
        print(f"[Amex] Request failed: {e}")


def save_max_benefits_raw() -> None:
    from max_benefits_scraper import HEADERS, LOBBY_URL, _REQUESTS_KWARGS

    out_dir = os.path.join(RAW_DIR, "max_benefits")
    os.makedirs(out_dir, exist_ok=True)
    try:
        response = requests.get(LOBBY_URL, headers=HEADERS, timeout=30, **_REQUESTS_KWARGS)
        response.raise_for_status()
        _write(os.path.join(out_dir, "lobby.json"), response.text, mode="w")
        print(f"[MAX Benefits] Saved lobby payload to {out_dir}")
    except Exception as e:
        print(f"[MAX Benefits] Request failed: {e}")


def save_isracard_raw() -> None:
    from isracard_scraper import HEADERS, BASE_URL, _REQUESTS_KWARGS

    out_dir = os.path.join(RAW_DIR, "isracard")
    os.makedirs(out_dir, exist_ok=True)
    try:
        response = requests.get(BASE_URL, headers=HEADERS, timeout=30, **_REQUESTS_KWARGS)
        response.raise_for_status()
        _write(os.path.join(out_dir, "benefits_homepage.html"), response.text, mode="w")
        print(f"[Isracard] Saved benefits homepage to {out_dir}")
    except Exception as e:
        print(f"[Isracard] Request failed: {e}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--all", action="store_true", help="Fetch raw for all supported scrapers")
    p.add_argument("--scrapers", help="Comma-separated list of scrapers to run (htzone,hot,mcc,hvr,buyme,discount_key,amex,max_benefits)")
    p.add_argument("--buyme", type=int, help="Single buyme supplier id to fetch")
    args = p.parse_args()

    to_run = []
    if args.all:
        to_run = ["htzone", "hot", "mcc", "hvr", "buyme", "discount_key", "amex", "max_benefits", "isracard"]
    elif args.scrapers:
        to_run = [s.strip() for s in args.scrapers.split(",") if s.strip()]

    if not to_run:
        print("Nothing to do. Use --all or --scrapers. Example: --scrapers htzone,hot")
        return

    if "discount_key" in to_run:
        save_discount_key_raw()
    if "amex" in to_run:
        save_amex_raw()
    if "isracard" in to_run:
        save_isracard_raw()
    if "max_benefits" in to_run:
        save_max_benefits_raw()
    if "htzone" in to_run:
        save_htzone_raw()
    if "hot" in to_run:
        save_hot_raw()
    if "mcc" in to_run:
        save_mcc_raw()
    if "hvr" in to_run:
        save_hvr_raw()
    if "buyme" in to_run:
        sid = args.buyme or 20620
        save_buyme_raw(sid)


if __name__ == "__main__":
    main()
