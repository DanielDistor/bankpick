# Where to Put Your Money

**Tell it how much you have, what you add monthly, and when you need it back. It shows you the savings account, CD or Treasury that pays you the most, with rates pulled fresh every day**

[![Live site](https://img.shields.io/badge/live-danieldistor.github.io-22e07a?style=flat-square)](https://danieldistor.github.io/deposit-pricing-analytics-banking/)
[![Refresh Data](https://github.com/DanielDistor/deposit-pricing-analytics-banking/actions/workflows/refresh-data.yml/badge.svg)](https://github.com/DanielDistor/deposit-pricing-analytics-banking/actions/workflows/refresh-data.yml)
[![Deploy Site](https://github.com/DanielDistor/deposit-pricing-analytics-banking/actions/workflows/deploy-site.yml/badge.svg)](https://github.com/DanielDistor/deposit-pricing-analytics-banking/actions/workflows/deploy-site.yml)

**Live:** https://danieldistor.github.io/deposit-pricing-analytics-banking/

Try it: [$25k + $500 a month](https://danieldistor.github.io/deposit-pricing-analytics-banking/?amount=25000&monthly=500) · [$25k you need in 2 years](https://danieldistor.github.io/deposit-pricing-analytics-banking/?amount=25000&need=24)

![Dashboard](docs/screenshots/dashboard.png)

## Why

Chase pays 0.01% on savings. The best online banks pay over 4%

On $25k plus $500 a month, that's $27,285 more after 10 years just from picking the right bank. Most people never check, so this does it for them

## How it works

| 1. Ask | 2. Load | 3. Answer |
|---|---|---|
| ![Ask](docs/screenshots/ask.png) | ![Loading](docs/screenshots/loading.png) | ![Timeline answer](docs/screenshots/timeline.png) |
| How much, monthly adds, when you need it | Pulls the Fed rate and today's bank rates | Where to put it and how much you end up with |

- **Need it anytime:** best high-yield savings account, with promos and minimums accounted for
- **Need it in 1, 2, 3 or 5 years:** savings vs CDs of that exact length vs the matching Treasury, whichever ends highest wins
- **Monthly adds** can't go into a CD or Treasury, so they get counted in the top savings account next to it
- Change any number right on the dashboard, and every result has its own link to share

## What's on the dashboard

| Your money vs the big banks | Best online rate vs the Fed |
|---|---|
| ![Big banks](docs/screenshots/big-banks.png) | ![Rate vs Fed](docs/screenshots/rate-vs-fed.png) |

- The pick, with an open account link and its track record ("Top 3 for 5 weeks")
- The next 3 best options right under it, with what each gets you and how much less
- **Today's brief:** what changed since yesterday, also as an [RSS feed](https://danieldistor.github.io/deposit-pricing-analytics-banking/data/feed.xml)
- Growth chart vs Chase, plus what the same money does at Chase, BofA, Wells Fargo and Citi
- Best online rate vs the Fed over the past year, and who's held #1
- An FDIC split over $250k, and the data health panel

<p align="center"><img src="docs/screenshots/mobile-ask.png" width="260" alt="Phone: ask"> &nbsp; <img src="docs/screenshots/mobile-dashboard.png" width="260" alt="Phone: dashboard"></p>

## Data quality

The pipeline checks its own data before it publishes anything, and shows you the results

![Data health](docs/screenshots/data-health.png)

- **Fresh:** Bankrate, FRED and big-bank rates each have a max age
- **Sane:** enough banks, rates between 0% and 10%, no duplicates, dbt tests passed
- **Weird spikes get flagged:** a rate that jumps 0.5+ points for one week and snaps back is treated as bad data. It stays on the chart but out of the rankings. First catch was in Bankrate's own data, Accordia Bank at 5.00% for one week in August between two weeks at 4.00%

Only Bankrate's editorial picks get recommended. Sponsored listings are only used to read promo terms

## How it's built

![Pipeline](docs/pipeline_diagram.png)

| Step | Scripts | Output |
|---|---|---|
| Pull | `extract_fred.py`, `extract_bankrate.py`, `extract_big_banks.py` | FRED data, Bankrate page snapshots (only saved when rates change), big-bank rate log |
| Parse + load | `parse_savings_offers.py`, `parse_cd_offers.py`, `parse_bankrate.py` | savings offers, rate history, CD offers, big-bank rates in DuckDB |
| Transform + test | dbt (`dbt-duckdb`) | staging + marts, star schema, 58 models/seeds/tests |
| Publish | `export_site_data.py` | `rates.json` with health checks, flags and the daily brief, plus `feed.xml` |
| Serve | GitHub Pages | plain HTML/CSS/JS, no framework, no build step |

Runs itself: `refresh-data.yml` does the whole pipeline every day at 12:00 UTC, tests first, then `deploy-site.yml` pushes the site live

### Data model

```mermaid
erDiagram
    FACT_DEPOSIT_RATES }o--|| DIM_BANK : bank_key
    FACT_DEPOSIT_RATES }o--|| DIM_PRODUCT : product_key
    FACT_DEPOSIT_RATES }o--|| DIM_DATE : scrape_date
    FACT_DEPOSIT_RATES {
        int bank_key FK
        int product_key FK
        date scrape_date FK
        float apy_pct
        float fed_funds_rate
        float spread_pct
        float passthrough_pct
    }
    DIM_BANK {
        int bank_key PK
        string bank_name
        string bank_type
    }
    DIM_PRODUCT {
        int product_key PK
        string product_name
        int term_months
    }
    DIM_DATE {
        date date_day PK
        int year
        int quarter
        string fed_rate_cycle
    }
```

The site reads `fct_savings_offers`, `fct_savings_rate_history`, `stg_cd_offers`, `stg_big_bank_savings` and `stg_fred_observations`

## Stack

| | |
|---|---|
| Data | FRED API, Bankrate (`requests` + `html2text`) |
| Warehouse | DuckDB |
| Transform + tests | dbt, pytest, `node --test` |
| Automation | GitHub Actions |
| Front end | vanilla JS, hand-drawn SVG charts, GitHub Pages |
| Built with | Cursor + Claude Code |

All free, no trials, no paid APIs. Only key is a free FRED API key, kept in `.env` and GitHub secrets

## Run it yourself

Just the site, using the data already in the repo:

```bash
python -m http.server -d site 8000   # open http://localhost:8000
```

The full pipeline:

```bash
git clone https://github.com/DanielDistor/deposit-pricing-analytics-banking.git
cd deposit-pricing-analytics-banking
pip install -r requirements.txt
echo "FRED_API_KEY=your_free_key" > .env   # optional, falls back to FRED's keyless CSV

python pipelines/extract_fred.py
python pipelines/extract_bankrate.py
python pipelines/extract_big_banks.py && python pipelines/extract_big_banks.py --load
python pipelines/parse_bankrate.py
python pipelines/parse_savings_offers.py
python pipelines/parse_cd_offers.py
(cd dbt && dbt build --profiles-dir .)
python pipelines/export_site_data.py
```

Tests:

```bash
python -m pytest -q pipelines/tests      # parsers, health checks, flags, brief, export (58)
node --test 'site/tests/*.test.mjs'      # money math, promos, minimums, CDs/Treasuries, FDIC (23)
(cd dbt && dbt build --profiles-dir .)   # models + data tests (58)
```

## What's where

```
.github/workflows/   daily pipeline + GitHub Pages deploy
pipelines/           pull, parse, export, health checks, daily brief (+ tests)
dbt/                 staging + mart models, seeds, tests
site/                the site: index.html, css/, js/app.js, js/calc.js (money math), data/
knowledge/           raw page snapshots + notes
docs/                screenshots, diagrams, proposal
```

## Background

Built for LMU ISBA-4715 (Analytics Engineering). Started as "how do banks pass Fed rate changes on to savers" and turned into a tool that just tells you where to put your money

Rates are info, not financial advice
