import csv
import io
import os

import requests
from dotenv import load_dotenv

try:
    from pipelines.warehouse import connect
except ImportError:  # run as `python pipelines/extract_fred.py`
    from warehouse import connect

load_dotenv()

FRED_API_KEY = os.getenv("FRED_API_KEY")
SERIES = ["FEDFUNDS", "DFF", "TB3MS", "GS1", "GS2", "GS5", "GS10", "DPCREDIT"]
OBSERVATION_START = "2000-01-01"


def fetch_series(series_id: str) -> list[tuple]:
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "observation_start": OBSERVATION_START,
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    observations = r.json()["observations"]
    return [
        (series_id, obs["date"], float(obs["value"]))
        for obs in observations
        if obs["value"] != "."
    ]


def fetch_series_keyless(series_id: str) -> list[tuple]:
    """Fallback: FRED's public CSV download, which needs no API key."""
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv"
    r = requests.get(url, params={"id": series_id, "cosd": OBSERVATION_START}, timeout=60)
    r.raise_for_status()
    reader = csv.reader(io.StringIO(r.text))
    next(reader)  # header: observation_date,<SERIES_ID>
    return [
        (series_id, day, float(value))
        for day, value in reader
        if value not in ("", ".")
    ]


def load_rows(conn, rows: list[tuple]) -> None:
    conn.execute("""
        CREATE OR REPLACE TABLE raw.fred_observations (
            series_id        VARCHAR,
            observation_date DATE,
            value            DOUBLE,
            loaded_at        TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (series_id, observation_date)
        )
    """)
    conn.executemany(
        "INSERT INTO raw.fred_observations (series_id, observation_date, value) VALUES (?, ?, ?)",
        rows,
    )


def main():
    fetch = fetch_series
    if not FRED_API_KEY:
        print("FRED_API_KEY not set; using FRED's keyless CSV endpoint "
              "(free key: https://fred.stlouisfed.org/docs/api/api_key.html)")
        fetch = fetch_series_keyless

    all_rows: list[tuple] = []
    for series_id in SERIES:
        print(f"  Fetching {series_id}...", end=" ", flush=True)
        rows = fetch(series_id)
        all_rows.extend(rows)
        print(f"{len(rows)} observations")

    conn = connect()
    try:
        print(f"\nLoading {len(all_rows)} total rows to DuckDB...")
        load_rows(conn, all_rows)
        count = conn.execute("SELECT COUNT(*) FROM raw.fred_observations").fetchone()[0]
        print(f"Verified: {count} rows in raw.fred_observations")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
