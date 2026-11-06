from datetime import date
from pathlib import Path

from pipelines.parse_savings_offers import (
    canonical_bank_name,
    parse_editorial_offers,
    parse_promos,
    parse_rate_history,
)

FIXTURE = (Path(__file__).parent / "fixtures" / "bankrate_savings_2026-11-05.md").read_text()


def test_editorial_offers_has_12_banks_with_ongoing_apy():
    offers = {o["bank_name"]: o for o in parse_editorial_offers(FIXTURE)}
    assert len(offers) == 12
    assert offers["CIT Bank"]["apy_pct"] == 3.75
    assert offers["CIT Bank"]["min_balance_for_apy"] == 5000
    assert offers["CIT Bank"]["min_opening"] == 100
    assert offers["CIT Bank"]["apy_as_of"] == date(2026, 11, 3)
    assert offers["Happen Bank"]["min_balance_for_apy"] == 250
    assert offers["Vio Bank"]["apy_pct"] == 4.01
    assert "Western State Bank" in offers and "Accordia Bank" in offers


def test_promos_attributed_to_right_bank():
    names = [o["bank_name"] for o in parse_editorial_offers(FIXTURE)]
    promos = parse_promos(FIXTURE, names)
    assert promos["CIT Bank"] == {"promo_apy_pct": 4.35, "promo_months": 6, "promo_expires": date(2026, 12, 15)}
    assert promos["Vio Bank"] == {"promo_apy_pct": 4.25, "promo_months": 3, "promo_expires": None}
    assert "Capital One" not in promos  # sponsored-only bank ignored


def test_rate_history_rows():
    rows = parse_rate_history(FIXTURE)
    cit = [r for r in rows if r["bank_name"] == "CIT Bank"]
    assert cit[0] == {"bank_name": "CIT Bank", "rate_date": date(2026, 11, 3), "apy_pct": 3.75}
    assert len(rows) > 400
    assert {r["bank_name"] for r in rows} == {o["bank_name"] for o in parse_editorial_offers(FIXTURE)}


def test_canonical_bank_name():
    assert canonical_bank_name("CIT Bank Platinum Savings account") == "CIT Bank"
    assert canonical_bank_name("Bread Savings savings") == "Bread Savings"
    assert canonical_bank_name("Live Oak savings") == "Live Oak Bank"
    assert canonical_bank_name("Capital One 360 Performance Savings™") == "Capital One"


def test_no_editorial_section_returns_empty():
    assert parse_editorial_offers("# nothing here") == []
    assert parse_rate_history("# nothing here") == []


def test_monthly_deposit_requirement_from_blurb():
    offers = {o["bank_name"]: o for o in parse_editorial_offers(FIXTURE)}
    assert offers["Happen Bank"]["min_monthly_deposit"] == 250
    assert offers["CIT Bank"]["min_monthly_deposit"] == 0
