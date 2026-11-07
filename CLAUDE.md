# Project Context

## Project Summary
**BankPick** is a portfolio project: a public, free tool that tells someone which bank, CD or
Treasury to put their money in, based on amount, monthly contributions and when they need it.
It's no longer graded (started as LMU ISBA-4715). Optimize for what a hiring manager or a
regular person sees in the first 10 seconds: a clear answer, clean finance-style dashboard,
solid data underneath.

## Under the hood
The data pipeline still does deposit pricing analytics (bank rates vs the Fed funds rate,
spreads, pass-through, star schema in dbt). That's supporting evidence, not the product.

## Tech Stack
- **Data Warehouse:** DuckDB (free, file-based; migrated from Snowflake after the trial ended)
- **Transformation:** dbt with dbt-duckdb (raw → staging → mart)
- **Orchestration:** GitHub Actions (daily `refresh-data.yml` commits `site/data/rates.json`; `deploy-site.yml` publishes `site/` to GitHub Pages)
- **Front end:** static HTML/CSS/JS savings recommender in `site/` on GitHub Pages (https://danieldistor.github.io/bankpick/); money math in `site/js/calc.js`, tested with `node --test 'site/tests/*.test.mjs'`
- **Constraint:** everything must stay on free tiers (no paid APIs or expiring trials)
- **IDE:** Cursor + Claude Code + Superpowers

## Data Sources
- **Source 1 (API):** FRED API — Federal Reserve rate data, Treasury yields, macro indicators
- **Source 2 (Scrape):** Bank deposit rates from Bankrate (requests + html2text)

## Star Schema
- **Fact table:** deposit rates over time (bank, product type, rate, date)
- **Dimensions:** banks, product types (savings/CD/money market), Fed rate cycles

## Product
**BankPick** (tagline: "Where to put your money"). A public savings recommender: ask how much someone is looking to invest, optional monthly
contributions, and when they'll need it (anytime, 1/2/3/5 years). Anytime recommends the best
high-yield savings account; a timeline compares savings vs. CDs of that exact term vs. the matching
Treasury. Flow is ask -> loading -> dashboard (no other screens). The dashboard adds the gap vs.
Chase/big banks, rate-vs-Fed history, #1 history, a daily "what changed" brief (+ RSS), and a
data-health panel with anomaly flags. Only Bankrate editorial picks are recommended. Keep visuals
purposeful: no decorative animations or eye-candy screens.

## Knowledge Base
- Raw scraped sources stored in `knowledge/raw/` (15+ sources from 3+ sites/authors)
- Claude Code-generated wiki pages in `knowledge/wiki/` (overview, key entities, themes)
- Index at `knowledge/index.md`

### How to Query the Knowledge Base
To answer questions about deposit pricing trends, bank strategies, or Fed rate policy:
1. Read all relevant wiki pages in `knowledge/wiki/`
2. Cross-reference with raw sources in `knowledge/raw/` when more detail is needed
3. Synthesize across sources — do not summarize individual files in isolation
4. Ground answers in specific banks, dates, and rate figures where available

## Directory Structure
```
bankpick/
├── docs/
│   ├── job-posting.pdf
│   ├── proposal.md
│   └── resume.pdf          # added at final submission
├── knowledge/
│   ├── raw/                # scraped sources
│   ├── wiki/               # Claude Code-generated synthesis pages
│   └── index.md
├── dbt/                    # dbt project
├── pipelines/              # GitHub Actions workflows
├── site/                   # static recommender site (GitHub Pages)
├── CLAUDE.md
├── README.md
└── .gitignore
```

## Credentials
The only credential is the free FRED API key, stored in `.env` locally and as a GitHub Actions secret, never committed to git.
