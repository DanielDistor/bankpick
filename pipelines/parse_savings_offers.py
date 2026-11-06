"""Parse Bankrate's savings page: editorial picks, promo offers, and rate history.

Only the editorial picks are recommendable. The sponsored offers table is read
solely to find promo terms for banks that are already editorial picks.
"""
import re
from datetime import date, datetime

from pathlib import Path

try:
    from pipelines.parse_bankrate import BANK_NAME_MAP
    from pipelines.warehouse import connect
except ImportError:  # run as `python pipelines/parse_savings_offers.py`
    from parse_bankrate import BANK_NAME_MAP
    from warehouse import connect

RAW_DIR = Path(__file__).resolve().parent.parent / "knowledge" / "raw"

EDITORIAL_HEADING_RE = re.compile(r"^## Bankrate[’']s editorial picks")
OFFERS_HEADING = "## Best savings accounts"
BANK_HEADING_RE = re.compile(r"^### (.+?)\s*$")
PCT_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)%\s*$")
DOLLAR_RE = re.compile(r"^\s*\$([\d,]+(?:\.\d+)?)\s*$")
AS_OF_RE = re.compile(r"APY as of (\d{1,2}/\d{1,2}/\d{4})")
HISTORY_ROW_RE = re.compile(r"^(\d{2}/\d{2}/\d{4})\|\s*(\d+(?:\.\d+)?)%")
SCORE_FDIC_RE = re.compile(r"^Bankrate score: [\d.]+ out of 5\s*Member FDIC")
PROMO_APY_RE = re.compile(r"Earn (?:up to )?(\d+(?:\.\d+)?)% APY", re.IGNORECASE)
PROMO_MONTHS_RE = re.compile(r"(\d+|[a-z]+)[\s-]months?\b", re.IGNORECASE)
PROMO_EXPIRES_RE = re.compile(r"Offer expires (\d{1,2}/\d{1,2}/\d{4})")
MONTHLY_DEPOSIT_RE = re.compile(r"deposits totaling at least \$([\d,]+) (?:per|a|each) month", re.IGNORECASE)
SUFFIX_RE = re.compile(r"\s+(?:platinum\s+)?savings(?:\s+account)?$", re.IGNORECASE)

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "eighteen": 18,
}
# Editorial headings drop "Bank" for some banks; use the name people know.
SHORT_NAMES = {
    "western state": "Western State Bank",
    "accordia": "Accordia Bank",
    "live oak": "Live Oak Bank",
}


def _date(s: str) -> date:
    return datetime.strptime(s, "%m/%d/%Y").date()


def canonical_bank_name(raw: str) -> str:
    name = raw.replace("™", "").replace("®", "").strip()
    lower = name.lower()
    for key, canonical in BANK_NAME_MAP.items():
        if key in lower:
            return canonical
    name = SUFFIX_RE.sub("", name).strip()
    return SHORT_NAMES.get(name.lower(), name)


def _section(lines: list[str], start_re) -> list[str]:
    """Lines after the heading matched by start_re, up to the next '## ' heading."""
    for i, line in enumerate(lines):
        if start_re(line):
            out = []
            for nxt in lines[i + 1:]:
                if nxt.startswith("## ") or nxt.startswith("##  "):
                    break
                out.append(nxt)
            return out
    return []


def _editorial_blocks(markdown: str) -> list[tuple[str, list[str]]]:
    lines = _section(markdown.splitlines(), lambda l: bool(EDITORIAL_HEADING_RE.match(l)))
    blocks: list[tuple[str, list[str]]] = []
    for line in lines:
        m = BANK_HEADING_RE.match(line)
        if m:
            blocks.append((canonical_bank_name(m.group(1)), []))
        elif blocks:
            blocks[-1][1].append(line)
    return blocks


def _value_after(lines: list[str], label: str, value_re) -> re.Match | None:
    for i, line in enumerate(lines):
        if line.startswith(label):
            for nxt in lines[i + 1:]:
                if nxt.strip():
                    return value_re.match(nxt)
            return None
    return None


def _dollars(m: re.Match | None) -> float | None:
    return float(m.group(1).replace(",", "")) if m else None


def parse_editorial_offers(markdown: str) -> list[dict]:
    offers = []
    for bank, lines in _editorial_blocks(markdown):
        as_of = next((AS_OF_RE.search(l) for l in lines if AS_OF_RE.search(l)), None)
        apy = _value_after(lines, "APY as of", PCT_RE)
        if not apy:
            continue
        min_opening = _dollars(_value_after(lines, "Min. opening balance", DOLLAR_RE))
        min_apy = _dollars(_value_after(lines, "Min. balance for APY", DOLLAR_RE))
        monthly = next((MONTHLY_DEPOSIT_RE.search(l) for l in lines if MONTHLY_DEPOSIT_RE.search(l)), None)
        offers.append({
            "bank_name": bank,
            "apy_pct": float(apy.group(1)),
            "min_balance_for_apy": min_apy if min_apy is not None else (min_opening or 0.0),
            "min_opening": min_opening or 0.0,
            "min_monthly_deposit": _dollars(monthly) or 0.0,
            "apy_as_of": _date(as_of.group(1)) if as_of else None,
        })
    return offers


def _parse_months(text: str) -> int | None:
    for m in PROMO_MONTHS_RE.finditer(text):
        token = m.group(1).lower()
        if token.isdigit():
            return int(token)
        if token in NUMBER_WORDS:
            return NUMBER_WORDS[token]
    return None


def parse_promos(markdown: str, bank_names: list[str]) -> dict[str, dict]:
    wanted = set(bank_names)
    lines = _section(markdown.splitlines(), lambda l: l.strip() == OFFERS_HEADING)
    promos: dict[str, dict] = {}
    current = None
    for i, line in enumerate(lines):
        if SCORE_FDIC_RE.match(line):
            # Bank name is the nearest preceding line that isn't the bare score.
            for prev in reversed(lines[:i]):
                p = prev.strip()
                if p and not re.fullmatch(r"[\d.]+", p):
                    current = canonical_bank_name(p)
                    break
        elif line.startswith("Limited time offer") and current in wanted and current not in promos:
            apy = PROMO_APY_RE.search(line)
            months = _parse_months(line)
            if not apy or not months:
                continue
            exp = PROMO_EXPIRES_RE.search(line)
            promos[current] = {
                "promo_apy_pct": float(apy.group(1)),
                "promo_months": months,
                "promo_expires": _date(exp.group(1)) if exp else None,
            }
    return promos


def parse_rate_history(markdown: str) -> list[dict]:
    rows = []
    for bank, lines in _editorial_blocks(markdown):
        for line in lines:
            m = HISTORY_ROW_RE.match(line.strip())
            if m:
                rows.append({"bank_name": bank, "rate_date": _date(m.group(1)), "apy_pct": float(m.group(2))})
    return rows


def main() -> None:
    """Full rebuild of raw.bankrate_savings_offers (newest snapshot) and
    raw.bankrate_rate_history (distinct rows across every snapshot)."""
    snapshots = []
    for md_file in sorted(RAW_DIR.glob("bankrate_savings_*.md")):
        markdown = md_file.read_text(encoding="utf-8")
        offers = parse_editorial_offers(markdown)
        if offers:
            snapshots.append((date.fromisoformat(md_file.stem.split("_")[-1]), markdown, offers))
    if not snapshots:
        raise SystemExit("No Bankrate snapshot has an editorial section; refusing to load.")

    snapshot_date, markdown, offers = snapshots[-1]
    promos = parse_promos(markdown, [o["bank_name"] for o in offers])
    history = sorted({(r["bank_name"], r["rate_date"], r["apy_pct"])
                      for _, md, _ in snapshots for r in parse_rate_history(md)})

    conn = connect()
    try:
        conn.execute("""
            CREATE OR REPLACE TABLE raw.bankrate_savings_offers (
                bank_name VARCHAR, apy_pct DOUBLE, promo_apy_pct DOUBLE, promo_months INTEGER,
                promo_expires DATE, min_opening DOUBLE, min_balance_for_apy DOUBLE,
                min_monthly_deposit DOUBLE, apy_as_of DATE, snapshot_date DATE
            )""")
        rows = []
        for o in offers:
            p = promos.get(o["bank_name"], {})
            rows.append((o["bank_name"], o["apy_pct"], p.get("promo_apy_pct"), p.get("promo_months"),
                         p.get("promo_expires"), o["min_opening"], o["min_balance_for_apy"],
                         o["min_monthly_deposit"],
                         o["apy_as_of"], snapshot_date))
        conn.executemany("INSERT INTO raw.bankrate_savings_offers VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
        conn.execute("""
            CREATE OR REPLACE TABLE raw.bankrate_rate_history (
                bank_name VARCHAR, rate_date DATE, apy_pct DOUBLE
            )""")
        conn.executemany("INSERT INTO raw.bankrate_rate_history VALUES (?,?,?)", history)
        print(f"Loaded {len(rows)} offers ({snapshot_date}) and {len(history)} history rows")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
