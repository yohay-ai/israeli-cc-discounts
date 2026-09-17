Discount Finder

This project scrapes discount offers from Israeli club sites (`חבר`, `HOT`, `HTzone`, `Buyme`, `מפתח דיסקונט`), normalizes them and provides a small web UI and API.

New fields added (2026-09-02):
- `discount_type`: enum indicating the discount mechanism. Known values: `billing_discount` (legacy/default), `rechargeable_card`, `voucher`, `gift_card`, `club_card`.
- `discount_value`: optional numeric percent when the discount is a percent and can be parsed.

you can see the  [data here](https://yohaybn.github.io/israeli-cc-discounts/)

Quickstart

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

Frontend

Open `docs/index.html` or the running API root at `http://127.0.0.1:8000` to view the UI. The toolbar now includes a `סוג ההטבה` selector to filter by `discount_type`.


## Discount Key

`discount_key_scraper.py` reads Discount Bank's public participating-business page and normalizes each percentage offer into the shared schema. A failed or empty refresh keeps the last successful `data/discounts/discount_key_discounts.json` file. Save the source page for debugging with:

```bash
.venv/bin/python save_raw_scrapers.py --scrapers discount_key
```
