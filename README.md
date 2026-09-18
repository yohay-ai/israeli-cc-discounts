# Discount Finder

All your Israeli credit-card discounts and club benefits in one place.

Discount Finder collects discount offers from Israeli credit-card clubs and loyalty programs, normalizes them into a single dataset, and serves them through a fast web UI and API - so you can search every benefit you are entitled to, across every club, in one search.

**See it live: https://yohaybn.github.io/israeli-cc-discounts/**

## What you get

- One searchable catalog of hundreds of offers across all supported clubs
- Filter by club, benefit type (`סוג ההטבה`), category, or physical stores near you
- A JSON API if you want to build on the data yourself

## Data sources

| Source | What it covers |
|---|---|
| MCC (`חבר`) | Club discounts |
| HOT | Member discounts |
| HTzone | Member discounts |
| HVR (hvr.co.il) | Rechargeable and gift card discounts |
| MAX gift cards | Gift-card offers |
| MAX benefits | The full MAX benefits catalog (cashback, vouchers, experiences) |
| BUYME | BUYME supplier discounts |
| Discount Key (מפתח דיסקונט) | Discount Bank participating businesses |
| American Express Israel | The Amex rewards catalog |
| Isracard | The Isracard benefits catalog (benefits.isracard.co.il) |

Every source is public data - no login required. New sources are added over time; each one is documented below.

## Quickstart

1. Create and activate the virtualenv:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the scraper to regenerate the canonical data under `data/` and publish the HTML-facing files under `docs/data/` (this backfills `discount_type` = `billing_discount` when missing):

```bash
.venv/bin/python main.py
```

4. Start the API server:

```bash
.venv/bin/python -m uvicorn api_server:app --host 0.0.0.0 --port 8000
```

5. Run smoke tests (ensure API is running):

```bash
.venv/bin/python tests/smoke_test.py
```

## The web UI

Open `docs/index.html` or the running API root at `http://127.0.0.1:8000`. The toolbar includes a `סוג ההטבה` selector to filter by `discount_type`.

## The data schema

Every offer is normalized to the same shape: `club`, `business_name`, `discount`, `discount_url`, `discount_type` (`billing_discount`, `rechargeable_card`, `voucher`, `gift_card`, `club_card`), `discount_value` (numeric percent when parseable), `has_physical_store`, `branches`, `limitations`, and optional `category`. Fields `discount_type` and `discount_value` were added on 2026-09-02.

## Contributing

Contributions are welcome - new sources, better normalization, UI improvements.

- Working with an AI coding agent? Point it at [`AGENTS.md`](AGENTS.md) - it has the repo conventions, the shared schema, and the checklist for adding a scraper.
- Adding a source by hand? Follow any existing `*_scraper.py`: a `scrape_<name>()` entry point, last-good-data behavior in `main.py`, raw capture in `save_raw_scrapers.py`, offline fixtures + tests, and a section in this README.
- Please open one PR per change and leave it open for manual review.

## Source notes

### MAX Benefits

`max_benefits_scraper.py` reads the public MAX benefits catalog API (`/api/benefits/getLobby` + paged `/api/benefits/getCategoriesLobby` per category) and normalizes each benefit into the shared schema: club `MAX`, discount text from the catalog subtitle, official benefit URL, terms in `limitations`, and `billing_discount` type for cashback offers (otherwise `voucher`). Out-of-stock and date-expired benefits are skipped. A failed or empty refresh keeps the last successful `data/discounts/max_benefits_discounts.json` file. Save the raw lobby payload for debugging with:

```bash
.venv/bin/python save_raw_scrapers.py --scrapers max_benefits
```

### Discount Key

`discount_key_scraper.py` reads Discount Bank's public participating-business page and normalizes each percentage offer into the shared schema. A failed or empty refresh keeps the last successful `data/discounts/discount_key_discounts.json` file. Save the source page for debugging with:

```bash
.venv/bin/python save_raw_scrapers.py --scrapers discount_key
```

### American Express

`amex_scraper.py` reads the public American Express Israel benefits site (https://rewards.americanexpress.co.il/) and normalizes each benefit into the shared schema. The homepage embeds the full benefit catalog as server-rendered JSON (`window.epi`), so no login is required. Out-of-stock benefits are skipped, and regular/premium point pricing is kept in `limitations`. A failed or empty refresh keeps the last successful `data/discounts/amex_discounts.json` file. Save the source page for debugging with:

```bash
.venv/bin/python save_raw_scrapers.py --scrapers amex
```

### Isracard

`isracard_scraper.py` reads the public Isracard benefits site (https://benefits.isracard.co.il/) and normalizes each benefit into the shared schema. Like the Amex source, the homepage embeds the entire catalog (300+ benefits, with descriptions, terms and category) as server-rendered JSON (`window.epi`), so a single request covers everything and no login is required. Out-of-stock benefits are skipped; premium benefits are flagged in `limitations`. Note: isracard.co.il blocks datacenter IPs via Cloudflare (ASN-based, not geographic), so run it from a residential connection. A failed or empty refresh keeps the last successful `data/discounts/isracard_discounts.json` file. Save the source page for debugging with:

```bash
.venv/bin/python save_raw_scrapers.py --scrapers isracard
```
