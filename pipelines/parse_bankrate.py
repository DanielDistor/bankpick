import re
from datetime import date
from pathlib import Path

try:
    from pipelines.warehouse import connect
except ImportError:  # run as `python pipelines/parse_bankrate.py`
    from warehouse import connect

RAW_DIR = Path(__file__).resolve().parent.parent / "knowledge" / "raw"

BANK_NAME_MAP = {
    "sofi": "SoFi",
    "marcus by goldman sachs": "Marcus by Goldman Sachs",
    "marcus": "Marcus by Goldman Sachs",
    "ally": "Ally Bank",
    "discover": "Discover Bank",
    "american express": "American Express",
    "synchrony": "Synchrony Bank",
    "barclays": "Barclays",
    "capital one": "Capital One",
    "cit bank": "CIT Bank",
    "bread savings": "Bread Savings",
    "western alliance": "Western Alliance Bank",
    "everbank": "EverBank",
    "ufb direct": "UFB Direct",
    "varo": "Varo Bank",
    "lendingclub": "LendingClub Bank",
    "bask bank": "Bask Bank",
    "tab bank": "TAB Bank",
    "sallie mae": "Sallie Mae Bank",
    "cibc": "CIBC Bank USA",
    "my banking direct": "My Banking Direct",
    "nbkc": "NBKC Bank",
    "vio bank": "Vio Bank",
    "openbank": "Openbank",
    "limelight bank": "Limelight Bank",
    "popular direct": "Popular Direct",
    "forbright bank": "Forbright Bank",
    "zynlo bank": "Zynlo Bank",
    "peak bank": "Peak Bank",
    "live oak bank": "Live Oak Bank",
    "colorado federal": "Colorado Federal Savings Bank",
    "axos bank": "Axos Bank",
    "axos": "Axos Bank",
}

CD_TERM_MAP = {
    "3-month": 3, "3 month": 3, "3mo": 3,
    "6-month": 6, "6 month": 6, "6mo": 6,
    "1-year": 12, "1 year": 12, "12-month": 12, "12 month": 12,
    "2-year": 24, "2 year": 24, "24-month": 24,
    "3-year": 36, "3 year": 36, "36-month": 36,
    "5-year": 60, "5 year": 60, "60-month": 60,
}

APY_RE = re.compile(r'(\d+\.\d+)\s*%\s*(?:APY|apy)', re.IGNORECASE)
TABLE_ROW_RE = re.compile(r'\|\s*([^|]+?)\s*\|\s*(\d+\.\d+)\s*%', re.IGNORECASE)
DATE_RE = re.compile(r'^\d{2}[/\-]\d{2}[/\-]\d{4}$')
# Matches both linked and plain bank names:
#   - [Bank Name](url) — X.XX% APY, ...
#   - Bank Name — X.XX% – Y.YY% APY, ...
LIST_ITEM_RE = re.compile(
    r'^\s*-\s+(?:\[([^\]]+)\]\([^)]+\)|([^\[\]—–]+?))\s*[—–\-]+\s*'
    r'(?:\d+\.\d+%\s*[–\-]+\s*)?(\d+\.\d+)%\s*APY',
    re.IGNORECASE
)
TERM_NAME_RE = re.compile(r'^\d+\s*(month|year|week|day)s?$', re.IGNORECASE)


def normalize_bank_name(raw: str) -> str:
    lower = raw.lower().strip()
    for key, canonical in BANK_NAME_MAP.items():
        if key in lower:
            return canonical
    words = raw.strip().split()
    return " ".join(words[:3]) if len(words) >= 3 else raw.strip()


def extract_term_months(text: str) -> int | None:
    lower = text.lower()
    for phrase, months in CD_TERM_MAP.items():
        if phrase in lower:
            return months
    return None


def extract_rates_from_markdown(markdown: str, product_type: str, scrape_date: date) -> list[dict]:
    rows = []
    seen_banks = set()

    # Strategy 0: markdown list items with hyperlinked bank names
    # Format: - [Bank Name](url) — X.XX% APY, ...
    for line in markdown.splitlines():
        m = LIST_ITEM_RE.search(line)
        if m:
            bank_raw = (m.group(1) or m.group(2)).replace("\\*", "*").strip()
            apy_str = m.group(3)
            bank = normalize_bank_name(bank_raw)
            if not bank:
                continue
            apy = float(apy_str)
            term = extract_term_months(line) if product_type == "cd" else None
            key = (bank, term)
            if key not in seen_banks:
                seen_banks.add(key)
                rows.append({
                    "bank_name": bank,
                    "product_type": product_type,
                    "term_months": term,
                    "apy_pct": apy,
                    "scrape_date": scrape_date,
                })

    if rows:
        return rows

    # Strategy 1: parse markdown tables
    for line in markdown.splitlines():
        m = TABLE_ROW_RE.match(line.strip())
        if m:
            bank_raw, apy_str = m.group(1), m.group(2)
            if DATE_RE.match(bank_raw.strip()):
                continue  # skip historical date rows
            if TERM_NAME_RE.match(bank_raw.strip()):
                continue  # skip CD term rows (e.g. "3 months", "1 year")
            bank = normalize_bank_name(bank_raw)
            if bank.lower() in ("bank", "institution", "bank name") or not bank:
                continue
            apy = float(apy_str)
            term = extract_term_months(line) if product_type == "cd" else None
            key = (bank, term)
            if key not in seen_banks:
                seen_banks.add(key)
                rows.append({
                    "bank_name": bank,
                    "product_type": product_type,
                    "term_months": term,
                    "apy_pct": apy,
                    "scrape_date": scrape_date,
                })

    if rows:
        return rows

    # Strategy 2: section-based parsing (## Bank Name ... APY%)
    sections = re.split(r'\n#{1,3}\s+', markdown)
    for section in sections:
        lines = section.strip().splitlines()
        if not lines:
            continue
        header = lines[0].strip()
        bank = normalize_bank_name(header)
        if not bank:
            continue

        if any(skip in header.lower() for skip in ["table of contents", "overview", "methodology", "faq", "editorial", "advertiser", "sponsored", "competition", "picks"]):
            continue

        content = "\n".join(lines)
        apy_matches = APY_RE.findall(content)
        if not apy_matches:
            continue

        apy = float(apy_matches[0])
        term = extract_term_months(content) if product_type == "cd" else None
        key = (bank, term)
        if key not in seen_banks:
            seen_banks.add(key)
            rows.append({
                "bank_name": bank,
                "product_type": product_type,
                "term_months": term,
                "apy_pct": apy,
                "scrape_date": scrape_date,
            })

    return rows


def load_to_duckdb(rows: list[dict]) -> None:
    if not rows:
        raise SystemExit("No Bankrate rows parsed; refusing to load an empty table.")

    conn = connect()
    try:
        conn.execute("""
            CREATE OR REPLACE TABLE raw.bankrate_rates (
                bank_name    VARCHAR,
                product_type VARCHAR,
                term_months  INTEGER,
                apy_pct      DOUBLE,
                scrape_date  DATE,
                loaded_at    TIMESTAMP DEFAULT current_timestamp
            )
        """)
        conn.executemany(
            """INSERT INTO raw.bankrate_rates (bank_name, product_type, term_months, apy_pct, scrape_date)
               VALUES (?, ?, ?, ?, ?)""",
            [(r["bank_name"], r["product_type"], r["term_months"], r["apy_pct"], r["scrape_date"])
             for r in rows],
        )
        count = conn.execute("SELECT COUNT(*) FROM raw.bankrate_rates").fetchone()[0]
        print(f"Loaded {count} rows to raw.bankrate_rates")
    finally:
        conn.close()


def main():
    all_rows = []
    for md_file in sorted(RAW_DIR.glob("bankrate_savings_*.md")):
        print(f"Parsing {md_file.name}...")
        scrape_date = date.fromisoformat(md_file.stem.split("_")[-1])
        markdown = md_file.read_text(encoding="utf-8")
        rows = extract_rates_from_markdown(markdown, "savings", scrape_date)
        print(f"  Found {len(rows)} savings rates")
        all_rows.extend(rows)

    for md_file in sorted(RAW_DIR.glob("bankrate_cds_*.md")):
        print(f"Parsing {md_file.name}...")
        scrape_date = date.fromisoformat(md_file.stem.split("_")[-1])
        markdown = md_file.read_text(encoding="utf-8")
        rows = extract_rates_from_markdown(markdown, "cd", scrape_date)
        print(f"  Found {len(rows)} CD rates")
        all_rows.extend(rows)

    print(f"\nTotal: {len(all_rows)} rows across all files")
    load_to_duckdb(all_rows)


if __name__ == "__main__":
    main()
