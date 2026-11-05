import re
import pytest
from datetime import date
from pipelines.parse_bankrate import extract_rates_from_markdown, normalize_bank_name

SAMPLE_SAVINGS_MARKDOWN = """
## SoFi Checking and Savings
**APY:** 3.80% APY
Minimum balance: $0

## Ally High Yield Savings Account
Up to 4.00% APY
No minimum balance required

## Marcus by Goldman Sachs Online Savings Account
4.10% APY
"""

SAMPLE_CD_MARKDOWN = """
## Barclays Online CD
**APY:** 4.20% APY
Term: 1 year (12 months)

## Ally Bank CD
4.00% APY
12-month term
"""

SAMPLE_TABLE_MARKDOWN = """
| Bank | APY | Min. Balance |
|------|-----|-------------|
| SoFi Checking and Savings | 3.80% | $0 |
| Marcus by Goldman Sachs | 4.10% | $0 |
| Ally Bank | 4.00% | $0 |
"""


def test_extract_savings_from_sections():
    rows = extract_rates_from_markdown(SAMPLE_SAVINGS_MARKDOWN, "savings", date(2026, 4, 26))
    assert len(rows) >= 2
    apys = [r["apy_pct"] for r in rows]
    assert 3.80 in apys or any(abs(a - 3.80) < 0.01 for a in apys)


def test_extract_rates_from_table():
    rows = extract_rates_from_markdown(SAMPLE_TABLE_MARKDOWN, "savings", date(2026, 4, 26))
    assert len(rows) >= 2


def test_extract_cd_rates():
    rows = extract_rates_from_markdown(SAMPLE_CD_MARKDOWN, "cd", date(2026, 4, 26))
    assert len(rows) >= 1
    assert all(r["product_type"] == "cd" for r in rows)


def test_row_schema():
    rows = extract_rates_from_markdown(SAMPLE_SAVINGS_MARKDOWN, "savings", date(2026, 4, 26))
    for row in rows:
        assert "bank_name" in row
        assert "product_type" in row
        assert "apy_pct" in row
        assert "scrape_date" in row
        assert isinstance(row["apy_pct"], float)


def test_normalize_bank_name():
    assert normalize_bank_name("Marcus by Goldman Sachs Online Savings Account") == "Marcus by Goldman Sachs"
    assert normalize_bank_name("Ally High Yield Savings Account") == "Ally Bank"
    assert normalize_bank_name("SoFi Checking and Savings") == "SoFi"


SAMPLE_DATE_TABLE_MARKDOWN = """
| Date | National average APY | Top rate APY |
|------|---------------------|-------------|
| 02/13/2026 | 4.03% | 0.60% |
| 01/23/2026 | 4.02% | 0.59% |
| 12/26/2025 | 3.95% | 0.55% |
"""

SAMPLE_LIST_MARKDOWN = """
- [Vio Bank](https://www.bankrate.com/...) — 4.03% APY, $100 minimum deposit
- [LendingClub](https://www.bankrate.com/...) — 4.00% APY, No minimum deposit
- [Bread Savings](https://www.bankrate.com/...) — 4.00% APY, $100 minimum deposit
- [EverBank](https://www.bankrate.com/...) — 3.90% APY, No minimum deposit
"""


def test_rejects_date_table_rows():
    rows = extract_rates_from_markdown(SAMPLE_DATE_TABLE_MARKDOWN, "savings", date(2026, 4, 26))
    for row in rows:
        # bank_name should never be a date string
        assert not re.match(r'^\d{2}[/\-]\d{2}[/\-]\d{4}$', row["bank_name"]), \
            f"Date string leaked into bank_name: {row['bank_name']}"


def test_extract_from_list_items():
    rows = extract_rates_from_markdown(SAMPLE_LIST_MARKDOWN, "savings", date(2026, 4, 26))
    assert len(rows) == 4
    bank_names = [r["bank_name"] for r in rows]
    assert "Vio Bank" in bank_names or any("vio" in n.lower() for n in bank_names)
    apys = [r["apy_pct"] for r in rows]
    assert 4.03 in apys
    assert all(r["product_type"] == "savings" for r in rows)


SAMPLE_CD_RANGE_MARKDOWN = """
- [Marcus by Goldman Sachs](https://www.bankrate.com/...) — 3.40% – 4.15% APY, $500 minimum
- [Ally Bank](https://www.bankrate.com/...) — 3.00% – 4.00% APY, No minimum
"""


def test_extract_cd_range_apy():
    rows = extract_rates_from_markdown(SAMPLE_CD_RANGE_MARKDOWN, "cd", date(2026, 4, 26))
    assert len(rows) == 2
    apys = [r["apy_pct"] for r in rows]
    assert 4.15 in apys
    assert 4.00 in apys


SAMPLE_PLAIN_LIST_MARKDOWN = """
  - CIT Bank — 4.35% APY, $100 minimum deposit
  - E\\*TRADE — 4.20% – 4.80% APY, No minimum deposit — 6 months - 5 years
  - Decent to competitive APYs.
"""


def test_extract_plain_list_items_from_requests_scrape():
    """html2text output (free scraper) has unlinked bank names in list items."""
    savings = extract_rates_from_markdown(SAMPLE_PLAIN_LIST_MARKDOWN, "savings", date(2026, 11, 5))
    by_bank = {r["bank_name"]: r["apy_pct"] for r in savings}
    assert by_bank == {"CIT Bank": 4.35, "E*TRADE": 4.80}

    cds = extract_rates_from_markdown(SAMPLE_PLAIN_LIST_MARKDOWN, "cd", date(2026, 11, 5))
    assert {r["bank_name"]: r["term_months"] for r in cds}["E*TRADE"] == 6
