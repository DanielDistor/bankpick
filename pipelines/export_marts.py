"""Export the dbt mart tables to CSV for the Streamlit dashboard.

The dashboard reads these committed CSVs with DuckDB, so it needs no database
server or credentials and keeps working indefinitely on Streamlit Community Cloud.
"""
try:
    from pipelines.warehouse import REPO_ROOT, connect
except ImportError:  # run as `python pipelines/export_marts.py`
    from warehouse import REPO_ROOT, connect

OUT_DIR = REPO_ROOT / "dashboard" / "data"

EXPORTS = {
    "fact_deposit_rates": "SELECT * FROM mart.fact_deposit_rates ORDER BY bank_key, product_key, scrape_date",
    "dim_bank": "SELECT * FROM mart.dim_bank ORDER BY bank_key",
    "dim_product": "SELECT * FROM mart.dim_product ORDER BY product_key",
    "dim_date": "SELECT * FROM mart.dim_date ORDER BY date_day",
    "fed_funds_history": """
        SELECT date_day, rate_pct, series_name
        FROM staging.stg_fred_observations
        WHERE series_id = 'FEDFUNDS'
        ORDER BY date_day
    """,
}


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect()
    try:
        for name, sql in EXPORTS.items():
            out = OUT_DIR / f"{name}.csv"
            conn.execute(f"COPY ({sql}) TO '{out}' (HEADER, DELIMITER ',')")
            n = conn.execute(f"SELECT COUNT(*) FROM read_csv_auto('{out}')").fetchone()[0]
            print(f"  {out.relative_to(REPO_ROOT)}: {n} rows")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
