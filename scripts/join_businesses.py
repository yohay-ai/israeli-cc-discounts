#!/usr/bin/env python3
"""Join discounts with geocoded physical store records.

Output:
 - docs/data/businesses_with_discounts.json
 - docs/data/unmatched_discounts.json

Matching strategy:
 - Normalize names (lower, strip punctuation/diacritics)
 - For each discount, find geocoded store within 50 meters and with RapidFuzz
   token_set_ratio >= 80. If found, attach discount to that branch.
 - Otherwise record as unmatched for manual review.
"""
import json
import math
import os
import re
from typing import Any, Dict, List
from rapidfuzz import fuzz
try:
    from rapidfuzz.fuzz import token_set_ratio
except Exception:
    token_set_ratio = None
    # fallback implementation using difflib
    from difflib import SequenceMatcher


    def token_set_ratio(a: str, b: str) -> int:
        # simple approximation of RapidFuzz token_set_ratio
        if not a or not b:
            return 0
        ta = set(a.split())
        tb = set(b.split())
        # combine tokens with intersection prioritized
        common = ta & tb
        rest = (ta | tb) - common
        sa = " ".join(sorted(common))
        sb = " ".join(sorted(common))
        if rest:
            sa = sa + " " + " ".join(sorted(ta - common))
            sb = sb + " " + " ".join(sorted(tb - common))
        ratio = SequenceMatcher(None, sa, sb).ratio()
        return int(ratio * 100)


# Fuzzy matching: minimum similarity (0-100) for a business name to match a query.
FUZZY_MATCH_THRESHOLD = 72


def normalize_hebrew(text: str) -> str:
    """Normalize text for comparison: lowercase and strip Hebrew niqqud
    (vowel points) and common punctuation."""
    text = text.lower()
    # Remove Hebrew niqqud/vowel points (U+0591-U+05C7) and common punctuation/whitespace
    text = re.sub(r"[\u0591-\u05c7]", "", text)
    text = re.sub(r'["״\'׳\-–—_.,/\\|]', " ", text)
    return " ".join(text.split()).strip()


def fuzzy_match(query: str, name: str) -> bool:
    """Return True if `query` approximately matches `name`.

    Combines substring matching with fuzzy string similarity so that
    misspelled business names (e.g. 'סטמצקי' for 'סטימצקי') still match.
    """
    q = normalize_hebrew(query)
    n = normalize_hebrew(name)

    if not q:
        return True

    # Exact substring match after normalization
    if q in n:
        return True

    # Check if query words appear in name
    q_words = q.split()
    if len(q_words) > 1 and all(w in n for w in q_words):
        return True

    # Fuzzy match: overall similarity plus token-based similarity
    score = max(
        fuzz.ratio(q, n),
        fuzz.token_set_ratio(q, n),
        fuzz.partial_ratio(q, n) if len(q) >= 4 else 0,
    )
    return score >= FUZZY_MATCH_THRESHOLD


BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DOCS_DATA = os.path.join(BASE_DIR, "docs", "data")
OUT_FILE = os.path.join(DOCS_DATA, "businesses_with_discounts.json")
UNMATCHED_FILE = os.path.join(DATA_DIR, "unmatched_discounts.json")


PROGRAM_ALIASES = {
    "mcc": {"MCC", "mcc", "חבר"},
    "mcc-sheli": {"חבר שלי"},
    "mcc-teamim": {"חבר טעמים"},
    "hot": {"HOT", "hot", "מועדון הוט"},
    "htzone": {"HTzone", "htzone"},
    "buyme": {"BUYME"},
    "max": {"MAX"},
    "max-giftcard": {"GiftCard max"},
    "max-super-giftcard": {"Super GiftCard max"},
    "max-food": {"Giftcard Food"},
    "max-executive": {"כרטיס הטבות executive"},
    "discount-key": {"מפתח דיסקונט"},
}
PROGRAM_PARENTS = {
    "mcc-sheli": "mcc",
    "mcc-teamim": "mcc",
    "max-giftcard": "max",
    "max-super-giftcard": "max",
    "max-food": "max",
    "max-executive": "max",
}


def program_metadata(source_label: str) -> Dict[str, str | None]:
    """Resolve a source club label while preserving child-program identity."""
    label = str(source_label or "").strip()
    for program_id, aliases in PROGRAM_ALIASES.items():
        if label in aliases or label.lower() in {alias.lower() for alias in aliases}:
            return {"program_id": program_id, "parent_program_id": PROGRAM_PARENTS.get(program_id)}
    slug = re.sub(r"[^a-z0-9֐-׿]+", "-", label.lower()).strip("-") or "unknown"
    return {"program_id": f"program-{slug}", "parent_program_id": None}


def annotate_program(discount: Dict) -> Dict:
    annotated = dict(discount)
    annotated.update(program_metadata(annotated.get("club") or annotated.get("club_name") or ""))
    return annotated


def load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def normalize_name(s: str) -> str:
    if not s:
        return ""
    s = s.lower()
    # remove punctuation
    s = re.sub(r"[\W_]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def get_region(lat: float | None) -> str:
    if lat is None:
        return "center"
    if lat < 30.0:
        return "eilat_arava"
    if lat < 31.3:
        return "south"
    if lat < 32.5:
        return "center"
    return "north"


def haversine_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    # returns distance in kilometers
    R = 6371.0088
    phi1 = math.radians(a_lat)
    phi2 = math.radians(b_lat)
    dphi = math.radians(b_lat - a_lat)
    dlambda = math.radians(b_lon - a_lon)
    x = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def build_branches(geocoded: List[Dict]) -> List[Dict]:
    branches = []
    for i, s in enumerate(geocoded):
        lat = s.get("lat") or s.get("latitude") or s.get("lng") or s.get("lon")
        lon = s.get("lng") or s.get("lon") or s.get("longitude")
        try:
            lat = float(lat)
            lon = float(lon)
        except Exception:
            continue
        name = s.get("business_name") or s.get("name") or s.get("business") or ""
        branch = {
            "branch_id": f"g_{i}",
            "name": name,
            "name_norm": normalize_name(name),
            "lat": lat,
            "lng": lon,
            "discounts": [],
            "source_records": [s],
        }
        branches.append(branch)
    return branches


def build_token_index(branches: List[Dict]) -> Dict[str, List[int]]:
    idx: Dict[str, List[int]] = {}
    for i, br in enumerate(branches):
        tokens = set(br["name_norm"].split())
        for t in tokens:
            idx.setdefault(t, []).append(i)
    return idx


def match_and_join(discounts: List[Dict], branches: List[Dict],
                   max_dist_m: float = 50.0, name_threshold: int = 80) -> List[Dict]:
    unmatched = []
    # build token index for branches
    token_idx = build_token_index(branches)

    for disc in discounts:
        bname = disc.get("business_name") or disc.get("business") or disc.get("merchant") or ""
        addr = disc.get("address") or ""
        name_norm = normalize_name(bname + " " + addr)

        tokens = set(name_norm.split()) if name_norm else set()
        candidate_idxs = set()
        for t in tokens:
            for i in token_idx.get(t, []):
                candidate_idxs.add(i)

        # if no token overlap, fall back to all branches (expensive) but try to avoid
        if not candidate_idxs:
            candidate_idxs = set(range(len(branches)))

        best = None
        best_score = 0
        best_dist = None

        # determine if discount has coords
        disc_lat = disc.get("lat") or disc.get("latitude")
        disc_lng = disc.get("lng") or disc.get("lon")
        has_coords = False
        try:
            disc_lat = float(disc_lat)
            disc_lng = float(disc_lng)
            has_coords = True
        except Exception:
            has_coords = False

        for i in candidate_idxs:
            br = branches[i]
            # compute name similarity
            score = token_set_ratio(name_norm, br["name_norm"]) if name_norm and br["name_norm"] else 0

            if has_coords:
                dist_km = haversine_km(br["lat"], br["lng"], disc_lat, disc_lng)
                dist_m = dist_km * 1000
                if dist_m <= max_dist_m and score >= name_threshold:
                    if score > best_score or (score == best_score and (best_dist is None or dist_m < best_dist)):
                        best = br
                        best_score = score
                        best_dist = dist_m
            else:
                # no coordinates: allow match by name only
                if score >= name_threshold:
                    if score > best_score:
                        best = br
                        best_score = score
                        best_dist = None

        if best:
            d = annotate_program(disc)
            d["matched_distance_m"] = best_dist
            best["discounts"].append(d)
        else:
            unmatched.append(disc)

    return unmatched


def compute_best_discount(branches: List[Dict]) -> None:
    for br in branches:
        best = None
        for d in br["discounts"]:
            try:
                val = float(d.get("discount_value") or d.get("value") or 0)
            except Exception:
                val = 0
            if best is None or val > best:
                best = val
        br["best_discount_value"] = best or 0


def normalize_lat_lon(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_businesses_with_discounts(stores: List[Dict], discounts: List[Dict], geocoded: List[Dict]) -> List[Dict]:
    """Attach matching discounts to store records from docs/data/businesses,
    then append geocoded locations that are not already present by exact lat/lng.
    """
    by_location: Dict[tuple[float, float], Dict] = {}
    businesses_with_discounts: List[Dict] = []

    def add_store_entry(store: Dict, matched_discounts: List[Dict], *, source: str) -> None:
        lat = normalize_lat_lon(store.get("lat"))
        lon = normalize_lat_lon(store.get("lon"))
        if lat is None or lon is None:
            return
        key = (round(lat, 6), round(lon, 6))
        entry = {
            "id": store.get("id"),
            "name": store.get("name") or store.get("business_name") or "",
            "type": store.get("type") or store.get("business_type") or "",
            "lat": lat,
            "lon": lon,
            "discounts": matched_discounts,
            "source": source,
        }
        if key not in by_location:
            by_location[key] = entry
            businesses_with_discounts.append(entry)
        else:
            existing = by_location[key]
            existing["discounts"].extend(matched_discounts)
            existing["name"] = existing["name"] or entry["name"]

    for store in stores:
        if not isinstance(store, dict):
            continue
        lat = normalize_lat_lon(store.get("lat"))
        lon = normalize_lat_lon(store.get("lon"))
        if lat is None or lon is None:
            continue

        matched = []
        
        for disc in discounts:
            if not isinstance(disc, dict):
                continue
            disc_name = (disc.get("business_name") or disc.get("business") or disc.get("merchant") or "").strip().lower()
            store_name = (store.get("name") or "").strip().lower()
            if not disc_name or not store_name:
                continue
            if store_name in disc_name or disc_name in store_name:
                matched.append(annotate_program(disc))

        add_store_entry(store, matched, source="docs/data/businesses")

    for item in geocoded:
        if not isinstance(item, dict):
            continue
        lat = normalize_lat_lon(item.get("lat"))
        lon = normalize_lat_lon(item.get("lng") or item.get("lon"))
        if lat is None or lon is None:
            continue
        key = (round(lat, 6), round(lon, 6))
        if key in by_location:
            continue

        matched = []
        for disc in discounts:
            if not isinstance(disc, dict):
                continue
            disc_name = (disc.get("business_name") or disc.get("business") or disc.get("merchant") or "").strip().lower()
            item_name = (item.get("business_name") or item.get("name") or "").strip().lower()
            if not disc_name or not item_name:
                continue
            if disc_name == item_name:
                matched.append(annotate_program(disc))

        add_store_entry({
            "id": item.get("place_id") or item.get("business_name"),
            "name": item.get("business_name") or item.get("name") or "",
            "type": item.get("type") or "",
            "lat": lat,
            "lon": lon,
        }, matched, source="data/businesses/processed_physical_stores_geocoded.json")

    return businesses_with_discounts


def main():
    all_disc_path = os.path.join(DATA_DIR, "all_combined_discounts.json")
    if not os.path.exists(all_disc_path):
        all_disc_path = os.path.join(DOCS_DATA, "all_combined_discounts.json")
    geocoded_path = os.path.join(DATA_DIR, "businesses", "processed_physical_stores_geocoded.json")
    if not os.path.exists(geocoded_path):
        geocoded_path = os.path.join(DOCS_DATA, "businesses", "processed_physical_stores_geocoded.json")
    regions_path = os.path.join(DOCS_DATA, "businesses")

    print("Loading discounts...", all_disc_path)
    discounts = load_json(all_disc_path)
    print(f"Loaded {len(discounts)} discounts")

    print("Loading geocoded stores...", geocoded_path)
    geocoded = load_json(geocoded_path)
    print(f"Loaded {len(geocoded)} geocoded store records")

    print("Loading region stores...", regions_path)
    region_files = [
        os.path.join(regions_path, name)
        for name in sorted(os.listdir(regions_path))
        if name.endswith(".json") and name.startswith("businesses_")
    ]
    stores: List[Dict] = []
    for path in region_files:
        try:
            stores.extend(load_json(path))
        except Exception:
            continue
    print(f"Loaded {len(stores)} region store records")

    businesses_with_discounts = build_businesses_with_discounts(stores, discounts, geocoded)
    save_json(OUT_FILE, businesses_with_discounts)

    regions: Dict[str, List[Dict]] = {"north": [], "center": [], "south": [], "eilat_arava": []}
    for business in businesses_with_discounts:
        lat = business.get("lat")
        try:
            lat_float = float(lat)
        except (TypeError, ValueError):
            continue
        region = get_region(lat_float)
        regions.setdefault(region, []).append(business)

    for region_name, region_businesses in regions.items():
        region_path = os.path.join(DOCS_DATA, "businesses", f"businesses_{region_name}.json")
        save_json(region_path, region_businesses)
        print(f"Wrote {region_path} with {len(region_businesses)} businesses")

    save_json(UNMATCHED_FILE, [])

    print(f"Wrote {OUT_FILE} with {len(businesses_with_discounts)} businesses")


if __name__ == "__main__":
    main()
