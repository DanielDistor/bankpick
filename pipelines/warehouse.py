"""Local DuckDB warehouse shared by the extract/load scripts and dbt.

The database file is rebuilt from scratch on every pipeline run (FRED is a full
reload and Bankrate is re-parsed from the raw markdown snapshots in
knowledge/raw/), so it is not committed. Only the exported site/data/rates.json is committed
for the static site to read.
"""
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "deposit_analytics.duckdb"


def connect() -> duckdb.DuckDBPyConnection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(DB_PATH))
    conn.execute("CREATE SCHEMA IF NOT EXISTS raw")
    return conn
