# Deposit Pricing Analytics

> Tracking how major U.S. banks respond to Federal Reserve rate changes and identifying where client deposits earn the most.

**Live Dashboard:** [deposit-pricing-analytics-banking.streamlit.app](https://deposit-pricing-analytics-banking.streamlit.app)

---

## Business Question

Where should a client deposit their money right now to get the most growth out of it?

This project tracks how major U.S. banks responded to Federal Reserve rate changes and builds the case for where client deposits should go. The Fed funds rate directly affects the APY banks offer on savings accounts. The APY is what determines how much a deposit grows over any given number of years. Bank choice is the only variable a client controls.

---

## Tech Stack

| Layer | Tool |
|-------|------|
| IDE | Cursor + Claude Code |
| Data Warehouse | DuckDB (free, file-based) |
| Transformation | dbt (`dbt-duckdb`) |
| Orchestration | GitHub Actions (weekly refresh + keep-alive) |
| Dashboard | Streamlit (Community Cloud) |
| Knowledge Base | Claude Code |
| Version Control | Git + GitHub |

The whole stack runs on free tiers with no expiring trials or paid APIs, so the live dashboard stays up indefinitely.

---

## Data Sources

| Source | Type | Destination |
|--------|------|-------------|
| [FRED API](https://fred.stlouisfed.org/) | REST API (free key; keyless CSV fallback) | `raw.fred_observations` |
| [Bankrate](https://www.bankrate.com/) | Web scrape (`requests` + `html2text`) | `knowledge/raw/` → `raw.bankrate_rates` |

FRED series loaded: Fed Funds Rate (monthly + daily), 3-Month/1-Year/2-Year/5-Year/10-Year Treasury yields, Discount Window Rate.

---

## Pipeline Diagram

> Mermaid renders natively on GitHub. The PNG below is a static backup for environments that do not support Mermaid rendering.

```mermaid
flowchart LR
    FRED[FRED API\nFederal Reserve] -->|extract_fred.py\nGitHub Actions| RAW_FRED[(raw.fred_observations\nDuckDB)]
    BANKRATE[Bankrate\nWeb Scrape] -->|extract_bankrate.py\nGitHub Actions| KB[knowledge/raw/\nMarkdown Files]
    KB -->|parse_bankrate.py| RAW_BANK[(raw.bankrate_rates\nDuckDB)]
    RAW_FRED --> STG_FRED[stg_fred_observations\ndbt Staging]
    RAW_BANK --> STG_BANK[stg_bankrate_rates\ndbt Staging]
    STG_FRED --> FACT[fact_deposit_rates\ndbt Mart]
    STG_BANK --> FACT
    STG_BANK --> DIM_BANK[dim_bank]
    STG_BANK --> DIM_PROD[dim_product]
    STG_FRED --> DIM_DATE[dim_date]
    DIM_BANK --> FACT
    DIM_PROD --> FACT
    DIM_DATE --> FACT
    FACT -->|export_marts.py| CSV[dashboard/data/*.csv\ncommitted weekly]
    CSV -->|DuckDB SQL| DASH[Dashboard\nStreamlit Cloud]
```

![Pipeline Diagram](docs/pipeline_diagram.png)

---

## ERD

> Mermaid renders natively on GitHub. The PNG below is a static backup for environments that do not support Mermaid rendering.

```mermaid
erDiagram
    FACT_DEPOSIT_RATES {
        int bank_key FK
        int product_key FK
        date scrape_date FK
        float apy_pct
        float fed_funds_rate
        float spread_pct
        float passthrough_pct
        string source_name
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
        string product_display_name
    }
    DIM_DATE {
        date date_day PK
        int year
        int month
        int quarter
        string fed_rate_cycle
    }

    FACT_DEPOSIT_RATES }o--|| DIM_BANK : "bank_key"
    FACT_DEPOSIT_RATES }o--|| DIM_PRODUCT : "product_key"
    FACT_DEPOSIT_RATES }o--|| DIM_DATE : "scrape_date"
```

![ERD](docs/erd.png)

---

## Key Insights

_Figures as of the November 2026 refresh (Fed funds rate 3.88%); the dashboard updates weekly._

- **Pass-through rate explains the APY gap:** The Fed funds rate sets the benchmark. Banks decide how much of it to share with depositors. Top online banks now pass through 100% to 112% of the Fed rate, meaning their savings APY matches or exceeds the Fed rate itself. JPMorgan Chase, Bank of America, and Wells Fargo pass through under 1%, keeping nearly the entire rate as profit margin.
- **Every online bank outperforms every traditional bank on savings APY:** CIT Bank leads at 4.35% APY, and every online bank in the dataset falls between 3.90% and 4.35%. JPMorgan Chase, BofA, and Wells Fargo sit at 0.01%, with Citibank at 0.04%.
- **The dollar impact on $10,000 is immediate:** A $10,000 deposit at CIT Bank earns $435 per year. The same deposit at JPMorgan Chase earns $1 per year. Same deposit, same year, different bank.
- **Compounding widens the gap over time:** The difference between a 4.30% APY and a 0.01% APY compounds significantly. Over 10 years, the gap between the best and worst savings account on $10,000 grows to over $5,000.
- **Bank choice is the only variable a client controls:** The Fed rate moves on its own. The bank's pass-through policy is fixed. The only decision available to a client is which bank holds their deposit.

---

## Dashboard

**Live URL:** [deposit-pricing-analytics-banking.streamlit.app](https://deposit-pricing-analytics-banking.streamlit.app)

Four tabs, all focused on savings accounts:

1. **Descriptive: Which Bank Pays the Most?** — Ranked APY table with color gradient + bar chart. All banks, savings accounts only.
2. **Descriptive: How Much Will I Earn?** — Lollipop chart showing annual dollar earnings on a $10,000 deposit across all banks.
3. **Diagnostic: Why Do Some Banks Pay More?** — Pass-through rate chart with zone bands (Low / Medium / High) + ranked data table with annual earnings column.
4. **Where Should I Deposit My Money?** — Enter a deposit amount, get the top 5 savings accounts with projected growth over 1, 5, and 10 years.

---

## Pipeline Setup (Local)

```bash
# Clone and install
git clone https://github.com/DanielDistor/deposit-pricing-analytics-banking.git
cd deposit-pricing-analytics-banking
pip install -r requirements.txt

# Optional: FRED_API_KEY in .env (free). Without it, FRED's keyless CSV endpoint is used.
# No other credentials are needed. The warehouse is a local DuckDB file in data/.

# Extract + load
python pipelines/extract_fred.py
python pipelines/extract_bankrate.py
python pipelines/parse_bankrate.py

# Transform + test
(cd dbt && dbt build --profiles-dir .)

# Export marts for the dashboard, then run it
python pipelines/export_marts.py
streamlit run dashboard/app.py
```

In production, `.github/workflows/refresh-data.yml` runs these same steps every Sunday and commits the refreshed CSVs, which triggers a Streamlit Cloud redeploy. `.github/workflows/keep-alive.yml` visits the app every 8 hours so it never sleeps.

---

## Knowledge Base

Scraped sources and synthesized wiki pages are in `knowledge/`. Raw sources cover savings rate data from Bankrate, NerdWallet, and individual bank pages. Wiki pages synthesize trends across the Fed rate cycle, key entities, and bank behavior.

See [`knowledge/index.md`](knowledge/index.md) for all sources and wiki pages.

---

## Project Context

Built for LMU ISBA-4715 (Analytics Engineering), targeting the **JPMorgan Chase Wealth Management Deposit Pricing Analytics Associate** role. The project demonstrates SQL, dimensional modeling, data pipelines, and analytics skills directly required by the posting.
