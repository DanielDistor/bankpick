"""Parse Bankrate's CD page into one row per (bank, term): the editorial picks
(each bank's featured CD, with term, minimum and a review link) plus the
"Compare top CD rates today by term" table (top 3 per term)."""
import re
from datetime import date
from pathlib import Path

try:
    from pipelines.parse_savings_offers import (
        DOLLAR_RE, EDITORIAL_HEADING_RE, PCT_RE, _section, _value_after, canonical_bank_name,
    )
    from pipelines.warehouse import connect
except ImportError:  # run as `python pipelines/parse_cd_offers.py`
    from parse_savings_offers import DOLLAR_RE, EDITORIAL_HEADING_RE, PCT_RE, _section, _value_after, canonical_bank_name
    from warehouse import connect

RAW_DIR = Path(__file__).resolve().parent.parent / "knowledge" / "raw"
TERM_RE = re.compile(r"(\d+)[\s-]*(month|year)", re.IGNORECASE)
REVIEW_RE = re.compile(r"(https://www\.bankrate\.com/banking/reviews/[\w-]+/)")
BY_TERM_HEADING_RE = re.compile(r"^##\s+Compare top CD rates today by term")
TAB_RE = re.compile(r"^\s*-\s*(\d+-(?:month|year)) rates")
TABLE_ROW_RE = re.compile(r"^(.+?)\s*\|\s*(\d+(?:\.\d+)?)% APY\s*\|\s*\$([\d,]+)")
CD_NAMES = {"e*trade": "E*TRADE"}


def parse_term(text: str) -> int | None:
    m = TERM_RE.search(text)
    if not m:
        return None
    n = int(m.group(1))
    return n * 12 if m.group(2).lower() == "year" else n


def _cd_name(raw: str) -> str:
    name = re.sub(r"\s+CD$", "", raw.strip())
    for key, canonical in CD_NAMES.items():
        if key in name.lower():
            return canonical
    return canonical_bank_name(name)


def _picks(lines: list[str]) -> list[dict]:
    blocks: list[tuple[str, list[str]]] = []
    for line in _section(lines, lambda l: bool(EDITORIAL_HEADING_RE.match(l))):
        if line.startswith("### "):
            blocks.append((line[4:].strip(), []))
        elif blocks:
            blocks[-1][1].append(line)
    rows = []
    for heading, body in blocks:
        apy = _value_after(body, "APY as of", PCT_RE)
        term_line = next((body[i + 1:] for i, l in enumerate(body) if l.strip() == "Term"), [])
        term = parse_term(next((l for l in term_line if l.strip()), ""))
        if not apy or not term:
            continue
        mins = _value_after(body, "Min. opening balance", DOLLAR_RE)
        link = next((REVIEW_RE.search(l) for l in body if REVIEW_RE.search(l)), None)
        rows.append({"bank_name": _cd_name(heading), "term_months": term, "apy_pct": float(apy.group(1)),
                     "min_deposit": float(mins.group(1).replace(",", "")) if mins else 0.0,
                     "url": link.group(1) if link else None})
    return rows


def _by_term_table(lines: list[str]) -> list[dict]:
    section = _section(lines, lambda l: bool(BY_TERM_HEADING_RE.match(l)))
    terms = [parse_term(m.group(1)) for m in (TAB_RE.match(l) for l in section) if m]
    rows, table = [], -1
    for line in section:
        if line.startswith("Institution | APY"):
            table += 1
            continue
        m = TABLE_ROW_RE.match(line.strip())
        if m and 0 <= table < len(terms):
            rows.append({"bank_name": _cd_name(m.group(1)), "term_months": terms[table],
                         "apy_pct": float(m.group(2)), "min_deposit": float(m.group(3).replace(",", "")),
                         "url": None})
    return rows


def parse_cd_offers(markdown: str) -> list[dict]:
    lines = markdown.splitlines()
    best: dict[tuple[str, int], dict] = {}
    for row in _picks(lines) + _by_term_table(lines):
        key = (row["bank_name"], row["term_months"])
        cur = best.get(key)
        if cur is None or row["apy_pct"] > cur["apy_pct"]:
            best[key] = {**row, "url": row["url"] or (cur or {}).get("url")}
        elif row["url"] and not cur["url"]:
            cur["url"] = row["url"]
    return sorted(best.values(), key=lambda r: (r["term_months"], -r["apy_pct"], r["bank_name"]))


def main() -> None:
    snapshots = sorted(RAW_DIR.glob("bankrate_cds_*.md"))
    for md_file in reversed(snapshots):  # newest snapshot that parses
        rows = parse_cd_offers(md_file.read_text(encoding="utf-8"))
        if rows:
            break
    else:
        raise SystemExit("No Bankrate CD snapshot parsed; refusing to load.")
    snapshot_date = date.fromisoformat(md_file.stem.split("_")[-1])
    conn = connect()
    try:
        conn.execute("""CREATE OR REPLACE TABLE raw.bankrate_cd_offers (
            bank_name VARCHAR, term_months INTEGER, apy_pct DOUBLE, min_deposit DOUBLE,
            url VARCHAR, snapshot_date DATE)""")
        conn.executemany("INSERT INTO raw.bankrate_cd_offers VALUES (?,?,?,?,?,?)",
                         [(r["bank_name"], r["term_months"], r["apy_pct"], r["min_deposit"], r["url"], snapshot_date)
                          for r in rows])
        print(f"Loaded {len(rows)} CD offers ({snapshot_date})")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
