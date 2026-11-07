"""Daily savings APYs for the big four banks, from their Bankrate review pages.

Keeps a small change log in knowledge/raw/big_bank_savings_rates.csv: one row per
rate a bank has had, with first_seen and last_checked dates, so freshness is
provable without storing four ~100 KB pages a day.

  python pipelines/extract_big_banks.py          # scrape, update the CSV
  python pipelines/extract_big_banks.py --load   # load the CSV into DuckDB
"""
import csv
import re
import sys
from datetime import date
from pathlib import Path

import requests

try:
    from pipelines.extract_bankrate import HEADERS, html_to_markdown
    from pipelines.warehouse import connect
except ImportError:  # run as `python pipelines/extract_big_banks.py`
    from extract_bankrate import HEADERS, html_to_markdown
    from warehouse import connect

CSV_PATH = Path(__file__).resolve().parent.parent / "knowledge" / "raw" / "big_bank_savings_rates.csv"
FIELDS = ["bank_name", "apy_pct", "first_seen", "last_checked"]
BIG_BANKS = {
    "JPMorgan Chase": "chase-bank",
    "Bank of America": "bank-of-america",
    "Wells Fargo": "wells-fargo",
    "Citibank": "citibank",
}
SAVINGS_HEADING_RE = re.compile(r"^###\s+(?:\*\*)?.*savings", re.IGNORECASE)
PCT_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)%\s*$")


def parse_review_apy(markdown: str) -> float | None:
    """The 'APY offering' value inside the page's first savings-account block."""
    in_savings = False
    lines = markdown.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("### "):
            in_savings = bool(SAVINGS_HEADING_RE.match(line))
        elif in_savings and line.strip() == "APY offering:":
            nxt = next((l for l in lines[i + 1:] if l.strip()), "")
            m = PCT_RE.match(nxt)
            return float(m.group(1)) if m else None
    return None


def update_rows(rows: list[dict], bank: str, apy: float, today: str) -> list[dict]:
    rows = [dict(r) for r in rows]
    mine = [r for r in rows if r["bank_name"] == bank]
    latest = max(mine, key=lambda r: (r["last_checked"], r["first_seen"]), default=None)
    if latest and float(latest["apy_pct"]) == apy:
        latest["last_checked"] = today
    else:
        rows.append({"bank_name": bank, "apy_pct": apy, "first_seen": today, "last_checked": today})
    return rows


def read_rows() -> list[dict]:
    if not CSV_PATH.exists():
        return []
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        return [{**r, "apy_pct": float(r["apy_pct"])} for r in csv.DictReader(f)]


def scrape() -> None:
    rows, today, ok = read_rows(), date.today().isoformat(), 0
    for bank, slug in BIG_BANKS.items():
        url = f"https://www.bankrate.com/banking/reviews/{slug}/"
        try:
            r = requests.get(url, headers=HEADERS, timeout=60)
            r.raise_for_status()
            apy = parse_review_apy(html_to_markdown(r.text))
        except requests.RequestException as e:
            print(f"{bank}: fetch failed ({e}); keeping last known rate")
            continue
        if apy is None or not 0 <= apy < 10:
            print(f"{bank}: no savings APY found; keeping last known rate")
            continue
        rows = update_rows(rows, bank, apy, today)
        ok += 1
        print(f"{bank}: {apy:.2f}%")
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["bank_name"], r["first_seen"])))
    if not ok:
        raise SystemExit("No big-bank rates scraped (blocked or layout changed).")


def load() -> None:
    rows = read_rows()
    conn = connect()
    try:
        conn.execute("""CREATE OR REPLACE TABLE raw.big_bank_savings_rates (
            bank_name VARCHAR, apy_pct DOUBLE, first_seen DATE, last_checked DATE)""")
        conn.executemany("INSERT INTO raw.big_bank_savings_rates VALUES (?,?,?,?)",
                         [(r["bank_name"], r["apy_pct"], r["first_seen"], r["last_checked"]) for r in rows])
        print(f"Loaded {len(rows)} big-bank rate rows")
    finally:
        conn.close()


if __name__ == "__main__":
    load() if "--load" in sys.argv else scrape()
