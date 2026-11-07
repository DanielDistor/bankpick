from pathlib import Path

from pipelines.extract_big_banks import parse_review_apy, update_rows

FIXTURE = Path(__file__).parent / "fixtures" / "bankrate_review_wells_fargo_snippet.md"


def test_parses_savings_apy_from_review_page():
    assert parse_review_apy(FIXTURE.read_text()) == 0.01


def test_ignores_apy_outside_the_savings_block():
    md = "### Wells Fargo CDs\n\nAPY offering:\n\n4.00%\n\n### Wells Fargo Way2Save Savings Account\n\nAPY offering:\n\n0.01%\n"
    assert parse_review_apy(md) == 0.01


def test_bold_savings_heading_and_missing_value():
    assert parse_review_apy("### **Chase Savings**\n\nAPY offering:\n\n0.01%\n") == 0.01
    assert parse_review_apy("### **Chase Savings**\n\nAPY offering:\n\nN/A\n") is None
    assert parse_review_apy("nothing here") is None


def test_same_rate_only_bumps_last_checked():
    rows = [{"bank_name": "Wells Fargo", "apy_pct": 0.01, "first_seen": "2026-04-26", "last_checked": "2026-04-26"}]
    out = update_rows(rows, "Wells Fargo", 0.01, "2026-11-06")
    assert out == [{"bank_name": "Wells Fargo", "apy_pct": 0.01, "first_seen": "2026-04-26", "last_checked": "2026-11-06"}]


def test_changed_rate_appends_a_new_row_and_keeps_history():
    rows = [{"bank_name": "Bank of America", "apy_pct": 0.01, "first_seen": "2026-04-26", "last_checked": "2026-04-26"}]
    out = update_rows(rows, "Bank of America", 0.04, "2026-11-06")
    assert out == rows + [{"bank_name": "Bank of America", "apy_pct": 0.04, "first_seen": "2026-11-06", "last_checked": "2026-11-06"}]
    assert update_rows([], "Citibank", 0.05, "2026-11-06")[0]["first_seen"] == "2026-11-06"
