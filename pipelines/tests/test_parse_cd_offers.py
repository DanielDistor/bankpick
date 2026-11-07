from pathlib import Path

from pipelines.parse_cd_offers import parse_cd_offers, parse_term

FIXTURE = Path(__file__).parent / "fixtures" / "bankrate_cds_2026-11-05.md"


def test_parse_term():
    assert parse_term("3 year") == 36
    assert parse_term("18 month") == 18
    assert parse_term("1 year") == 12
    assert parse_term("6-month") == 6
    assert parse_term("forever") is None


def offers():
    return {(o["bank_name"], o["term_months"]): o for o in parse_cd_offers(FIXTURE.read_text())}


def test_editorial_picks_carry_term_minimum_and_review_link():
    o = offers()
    happen = o[("Happen Bank", 24)]
    assert happen["apy_pct"] == 4.76 and happen["min_deposit"] == 500
    assert happen["url"] == "https://www.bankrate.com/banking/reviews/happen-bank/"
    assert o[("Synchrony Bank", 60)]["min_deposit"] == 0
    assert o[("E*TRADE", 36)]["apy_pct"] == 4.55
    assert o[("Bread Savings", 18)]["apy_pct"] == 4.85


def test_rates_by_term_table_maps_tabs_to_terms():
    o = offers()
    assert o[("Bank5 Connect", 3)]["apy_pct"] == 4.30
    assert o[("Happen Bank", 6)]["apy_pct"] == 4.40
    assert o[("CFG Bank", 12)]["apy_pct"] == 4.65
    assert o[("CFG Bank", 36)]["apy_pct"] == 4.82
    assert o[("Sallie Mae Bank", 60)]["apy_pct"] == 5.00 and o[("Sallie Mae Bank", 60)]["min_deposit"] == 2500


def test_duplicates_keep_the_best_rate_and_a_link_when_any_source_has_one():
    o = offers()
    # Popular Direct 3-year: pick (4.85, linked) and table (4.85) -> one row with the link
    pd = [v for k, v in o.items() if k == ("Popular Direct", 36)]
    assert len(pd) == 1 and pd[0]["url"].endswith("/reviews/popular-direct/")
    assert len(parse_cd_offers(FIXTURE.read_text())) == len(o)


def test_no_sections_no_rows():
    assert parse_cd_offers("# nothing") == []
