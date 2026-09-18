# Agent Instructions

Guidance for AI agents (and humans) working in this repository. Read this before making changes.

## What this project is

Discount Finder aggregates discount and benefit offers from Israeli credit-card clubs and loyalty programs into one normalized dataset, served by a small FastAPI backend and a static web UI published from `docs/` via GitHub Pages.

Pipeline: source scrapers -> `main.py` (normalize, dedupe, merge) -> `data/discounts/*.json` + `docs/data/*.json` -> `scripts/join_businesses.py` (business matching) -> `api_server.py` / `docs/index.html`.

## Repository layout

- `*_scraper.py` - one module per source (MCC, HOT, HTzone, HVR, MAX gift cards, MAX benefits, BUYME, Discount Key, American Express).
- `main.py` - runs all scrapers, normalizes, dedupes, writes `data/discounts/` and `docs/data/`, keeps per-source metadata.
- `save_raw_scrapers.py` - saves raw source payloads under `data/raw/` for debugging (`--scrapers <name>` or `--all`).
- `scripts/join_businesses.py` - joins discounts with the business/branch dataset. Owner-run only (see below).
- `api_server.py` - FastAPI service over the generated data; `run_api.sh` starts it.
- `docs/` - static frontend (GitHub Pages). Data files it loads live in `docs/data/`.
- `tests/` - pytest suite with fixtures under `tests/fixtures/`; `tests/smoke_test.py` needs a running API.
- `run_daily.sh`, `scrape_and_sync.sh` - the owner's cron wrappers. Not for use in development.

## The shared schema

Every scraper returns a list of dicts with these fields:

| Field | Type | Notes |
|---|---|---|
| `club` | string | Club/program name as shown to users (e.g. `MAX`, `מפתח דיסקונט`) |
| `business_name` | string | Business or offer title |
| `discount` | string | Human-readable discount text (plain text, no HTML) |
| `discount_url` | string | Canonical link to the offer |
| `discount_type` | enum | `billing_discount`, `rechargeable_card`, `voucher`, `gift_card`, `club_card` |
| `discount_value` | number \| null | Percent value when the discount is a parseable percent |
| `has_physical_store` | bool | `false` for online-only offers |
| `branches` | list | Branch objects when known, otherwise `[]` |
| `limitations` | string | Terms and conditions, plain text |
| `category` | string | Optional source category |

## Adding or changing a scraper

Conventions every source follows (see `amex_scraper.py` or `max_benefits_scraper.py` for a recent example):

1. One `scrape_<name>()` entry point returning normalized records; keep fetch, extract and normalize as separate functions so each is testable.
2. Wire it into `main.py`: run it, write `data/discounts/<name>_discounts.json` only on a non-empty result, record `metadata["<name>"]`, and on failure fall back to the previous file (last-good-data behavior). Never delete or empty an existing data file because one run failed.
3. Add a `save_<name>_raw()` function to `save_raw_scrapers.py` and register it in the `--all` list, the `--scrapers` help text and the dispatch block.
4. Add real (trimmed) fixtures under `tests/fixtures/` and pytest tests that run fully offline: normalization, dedupe, edge cases (expired/out-of-stock/malformed), and a mocked network walk. Live-network checks are manual, not part of the test suite.
5. Document the source in `README.md` (one section per source, including the raw-capture command).

## Hard rules

- Public data only. Never bypass logins, OTP, CAPTCHAs, Cloudflare or any other access control. If a source starts blocking, stop and report - do not work around it.
- Never commit generated data: no `data/` or `docs/data/` changes from local runs in a PR. Data regeneration and `scripts/join_businesses.py` are run by the repo owner on request, not as part of code PRs.
- One concern per PR, based on the latest `main`. Leave PRs open for the owner's manual review; do not merge or enable auto-merge.
- Do not modify the cron wrappers (`run_daily.sh`, `scrape_and_sync.sh`) to point at your environment; they contain the owner's server paths.

## Checks before opening a PR

```bash
python -m pytest -q tests/            # unit tests (offline)
python -m compileall -q <changed .py files>
git diff --check                      # whitespace/errors
```

Then run one live scrape of the changed source and confirm the normalized record count looks sane. Note the count in the PR description.

Some tests depend on generated data existing (`tests/test_combined_discounts.py`, `tests/test_data_layout.py`) and fail on a clean checkout - that is expected and pre-existing; compare against the same failures on `main`.
