"""
REST API server for searching credit-card club discounts.

Endpoints:
    GET /                          - API info
    GET /clubs                     - list all clubs with record counts
    GET /discounts                 - search discounts
        Query params:
            q       - free-text search in business name (case-insensitive)
            club    - filter by club (MCC / HOT / HTzone)
            limit   - max results per page (default 50, max 500)
            offset  - pagination offset (default 0)
    GET /businesses                - list unique business names (optionally ?q=)

Run:
    .venv/bin/uvicorn api_server:app --host 0.0.0.0 --port 8000
"""

import json
import os
import re
import math
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from rapidfuzz import fuzz

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
DOCS_DATA_DIR = os.path.join(BASE_DIR, "docs", "data")
DATA_FILE = os.path.join(DATA_DIR, "all_combined_discounts.json")
METADATA_FILE = os.path.join(DATA_DIR, "scrape_metadata.json")
STATIC_DIR = os.path.join(BASE_DIR, "docs")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
BUSINESSES_WITH_DISCOUNTS = os.path.join(DOCS_DATA_DIR, "businesses_with_discounts.json")

templates: Optional[Jinja2Templates] = None
if os.path.exists(TEMPLATES_DIR):
    templates = Jinja2Templates(directory=TEMPLATES_DIR)

# in-memory cache for businesses_with_discounts
_BUSINESSES_CACHE: list[dict] | None = None


def haversine_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    R = 6371.0088
    phi1 = math.radians(a_lat)
    phi2 = math.radians(b_lat)
    dphi = math.radians(b_lat - a_lat)
    dlambda = math.radians(b_lon - a_lon)
    x = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def load_businesses_with_discounts(reload: bool = False) -> list[dict]:
    """Load and cache the precomputed `businesses_with_discounts.json` file.

    If missing, return an empty list.
    """
    global _BUSINESSES_CACHE
    if _BUSINESSES_CACHE is not None and not reload:
        return _BUSINESSES_CACHE
    try:
        with open(BUSINESSES_WITH_DISCOUNTS, encoding="utf-8") as f:
            _BUSINESSES_CACHE = json.load(f)
            return _BUSINESSES_CACHE
    except Exception:
        _BUSINESSES_CACHE = []
        return _BUSINESSES_CACHE

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


app = FastAPI(
    title="Discount Finder API & Web App",
    description="Search discounts available in Israeli credit-card clubs (MCC, HOT, HTzone).",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_data() -> list[dict]:
    """Load the combined discounts JSON from disk on every request,
    so the API always reflects the latest scrape without a restart."""
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Discount data file not found. Run the scraper first.")
    except json.JSONDecodeError:
        raise HTTPException(status_code=503, detail="Discount data file is corrupted.")


def load_metadata() -> dict:
    """Load scrape metadata if available."""
    try:
        with open(METADATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# Mount static directory if it exists
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    # Also expose docs/data at /data so web UI can use the same absolute paths
    data_dir = os.path.join(STATIC_DIR, "data")
    if os.path.exists(data_dir):
        app.mount("/data", StaticFiles(directory=data_dir), name="data")


@app.get("/styles.css")
def get_styles():
    css_file = os.path.join(STATIC_DIR, "styles.css")
    if os.path.exists(css_file):
        return FileResponse(css_file, media_type="text/css")
    raise HTTPException(status_code=404, detail="styles.css not found")


@app.get("/app.js")
def get_app_js():
    js_file = os.path.join(STATIC_DIR, "app.js")
    if os.path.exists(js_file):
        return FileResponse(js_file, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="app.js not found")


@app.get("/")
def index(request: Request):
    """Serve the Web UI interface."""
    if templates and os.path.exists(os.path.join(TEMPLATES_DIR, "index.html")):
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "active_page": "index",
                "subtitle": "חיפוש והשוואת הטבות מועדוני אשראי",
                "deals_label": "הטבות פעילות",
                "stores_label": "עסקים ורשתות",
                "show_status": False,
            },
        )
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {
        "service": "Discount Finder API",
        "message": "Web UI index.html not found. Place static files in static/ directory.",
        "endpoints": {
            "/clubs": "List clubs and their discount counts",
            "/discounts": "Search flat discounts list (?q=text&club=MCC&limit=50&offset=0)",
            "/businesses": "List grouped businesses with all discount options (?q=text&club=HOT)",
            "/api/info": "API description and metadata",
            "/nearme": "Web UI interface for searching nearby discounts",
        },
    }

@app.get("/nearme")
def nearme(request: Request):
    """Serve the Web UI interface."""
    if templates and os.path.exists(os.path.join(TEMPLATES_DIR, "nearme.html")):
        return templates.TemplateResponse(
            request=request,
            name="nearme.html",
            context={
                "active_page": "nearme",
                "subtitle": "חיפוש עסקים והטבות קרובים",
                "deals_label": "הטבות באיזור",
                "stores_label": "עסקים באיזור",
                "show_status": True,
            },
        )
    index_file = os.path.join(STATIC_DIR, "nearme.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {
        "service": "Discount Finder API",
        "message": "Web UI nearme.html not found. Place static files in static/ directory.",
        "endpoints": {
            "/clubs": "List clubs and their discount counts",
            "/discounts": "Search flat discounts list (?q=text&club=MCC&limit=50&offset=0)",
            "/businesses": "List grouped businesses with all discount options (?q=text&club=HOT)",
            "/api/info": "API description and metadata",
            
            "/nearme": "Web UI interface for searching nearby discounts",
        },
    }
@app.get("/api")
@app.get("/api/info")
def api_info():
    meta = load_metadata()
    return {
        "service": "Discount Finder API",
        "version": "1.1.0",
        "metadata": meta,
        "endpoints": {
            "/": "Web UI Interface",
            "/clubs": "List clubs and their discount counts",
            "/discounts": "Search flat discounts list (?q=text&club=MCC&limit=50&offset=0)",
            "/businesses": "List grouped businesses with all discount options (?q=text&club=HOT)",
            
            "/nearme": "Web UI interface for searching nearby discounts",
        },
    }


@app.get("/clubs")
def get_clubs():
    data = load_data()
    counts: dict[str, int] = {}
    for item in data:
        counts[item["club"]] = counts.get(item["club"], 0) + 1
    meta = load_metadata()
    return {
        "total": len(data),
        "clubs": [{"club": c, "count": n} for c, n in sorted(counts.items())],
        "metadata": meta,
    }


@app.get("/discounts")
def search_discounts(
    q: Optional[str] = Query(None, description="Free-text search in business name"),
    club: Optional[str] = Query(None, description="Filter by club: MCC, HOT or HTzone"),
    discount_type: Optional[str] = Query(None, description="Filter by discount type, e.g. billing_discount, voucher, gift_card"),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    data = load_data()

    if club:
        # Case-insensitive club match
        matches = [d for d in data if d["club"].lower() == club.lower()]
        if not matches:
            valid = sorted({d["club"] for d in data})
            raise HTTPException(status_code=404, detail=f"Unknown club '{club}'. Valid clubs: {valid}")
        data = matches

    if discount_type:
        matches = [d for d in data if (d.get("discount_type") or "").lower() == discount_type.lower()]
        if not matches:
            valid_types = sorted({(d.get("discount_type") or "billing_discount") for d in data})
            raise HTTPException(status_code=404, detail=f"Unknown discount_type '{discount_type}'. Valid types: {valid_types}")
        data = matches

    if q:
        data = [d for d in data if fuzzy_match(q, d["business_name"])]

    total = len(data)
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "results": data[offset : offset + limit],
    }


@app.get("/businesses")
def list_businesses(
    q: Optional[str] = Query(None, description="Filter business names"),
    club: Optional[str] = Query(None, description="Filter by club: MCC, HOT or HTzone"),
):
    """List businesses grouped by store name, retaining all discount options
    and URLs from all clubs or a filtered club."""
    data = load_data()
    names: dict[str, dict] = {}

    for d in data:
        name = d["business_name"].strip()
        if not name:
            continue
        entry = names.setdefault(
            name,
            {
                "business_name": name,
                "discounts": [],
                "clubs": set(),
                "best_discount": None,
                "best_discount_value": 0.0,
            },
        )
        entry["discounts"].append(
            {
                "club": d["club"],
                "discount": d["discount"],
                "discount_url": d.get("discount_url", ""),
                "discount_type": d.get("discount_type"),
                "discount_value": d.get("discount_value"),
            }
        )
        entry["clubs"].add(d["club"])

    results = []
    for entry in names.values():
        # Calculate maximum discount percent across all options for this business
        # Prefer structured `discount_value` when available (represents percent)
        percents = []
        for disc in entry["discounts"]:
            val = disc.get("discount_value")
            if val is not None:
                try:
                    percents.append(float(val))
                    continue
                except Exception:
                    pass

            # Fallback: parse percent or any numeric token from the free-text discount
            match = re.search(r"(\d+(?:\.\d+)?)%", disc["discount"])
            if match:
                percents.append(float(match.group(1)))
            else:
                match_any_num = re.search(r"\d+(?:\.\d+)?", disc["discount"])
                if match_any_num:
                    try:
                        percents.append(float(match_any_num.group()))
                    except Exception:
                        pass

        if percents:
            max_val = max(percents)
            entry["best_discount_value"] = max_val
            entry["best_discount"] = f"{max_val:g}%"
        else:
            entry["best_discount_value"] = 0.0
            entry["best_discount"] = entry["discounts"][0]["discount"] if entry["discounts"] else None

        entry["clubs"] = sorted(list(entry["clubs"]))
        results.append(entry)

    if club:
        target_club = club.strip().lower()
        results = [r for r in results if any(c.lower() == target_club for c in r["clubs"])]

    if q:
        results = [r for r in results if fuzzy_match(q, r["business_name"])]

    # Default sort by best discount descending, then business name
    results.sort(key=lambda r: (-r["best_discount_value"], r["business_name"]))
    return {"total": len(results), "results": results}


@app.get("/nearby")
def nearby(
    lat: float = Query(..., description="Latitude of the search center"),
    lon: float = Query(..., description="Longitude of the search center"),
    radius_km: float = Query(2.0, description="Search radius in kilometers"),
    limit: int = Query(50, ge=1, le=1000),
    reload: bool = Query(False, description="Reload the businesses_with_discounts.json from disk"),
):
    """Return businesses_with_discounts within `radius_km` of the provided lat/lon.

    The endpoint expects `docs/data/businesses_with_discounts.json` to exist (created by
    `scripts/join_businesses.py`). Results include `distance_km` and the branch's discounts.
    """
    businesses = load_businesses_with_discounts(reload=reload)
    if not businesses:
        raise HTTPException(status_code=503, detail="businesses_with_discounts.json not found or empty. Run scripts/join_businesses.py first.")

    hits = []
    for b in businesses:
        try:
            b_lat = float(b.get("lat") or b.get("lng") or b.get("latitude"))
            b_lon = float(b.get("lng") or b.get("lon") or b.get("longitude"))
        except Exception:
            continue
        dist_km = haversine_km(lat, lon, b_lat, b_lon)
        if dist_km <= float(radius_km):
            hit = {
                "branch_id": b.get("branch_id") or b.get("id") or b.get("name"),
                "name": b.get("name"),
                "lat": b_lat,
                "lng": b_lon,
                "distance_km": round(dist_km, 4),
                "best_discount_value": b.get("best_discount_value", 0),
                "discounts": b.get("discounts", []),
            }
            hits.append(hit)

    # sort by distance then best_discount_value desc
    hits.sort(key=lambda h: (h["distance_km"], -float(h.get("best_discount_value") or 0)))
    return {"total": len(hits), "limit": limit, "results": hits[:limit]}
