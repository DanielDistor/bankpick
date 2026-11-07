from datetime import date

import duckdb
import pytest

from pipelines.export_site_data import build_payload, compute_badge

D = date.fromisoformat


def test_rate_cut_badge():
    h = {"A": [(D("2026-10-27"), 4.10), (D("2026-11-03"), 4.00)]}
    assert compute_badge(h, "A", D("2026-11-05")) == "Rate cut 0.10%"


def test_rate_up_badge():
    h = {"A": [(D("2026-10-27"), 4.00), (D("2026-11-03"), 4.25)]}
    assert compute_badge(h, "A", D("2026-11-05")) == "Rate up 0.25%"


def test_old_change_is_not_news():
    h = {"A": [(D("2026-09-01"), 4.10), (D("2026-09-08"), 4.00)]}
    assert compute_badge(h, "A", D("2026-11-05")) is None


def test_top3_streak():
    dates = [D("2026-10-06"), D("2026-10-13"), D("2026-10-20"), D("2026-10-27"), D("2026-11-03")]
    h = {b: [(d, r) for d in dates] for b, r in [("A", 4.3), ("B", 4.2), ("C", 4.1), ("D", 3.0)]}
    assert compute_badge(h, "A", D("2026-11-05")) == "Top 3 for 5 weeks"
    assert compute_badge(h, "D", D("2026-11-05")) is None


def test_top3_tolerates_banks_reporting_on_different_weekdays():
    weeks = [D("2026-10-05"), D("2026-10-12"), D("2026-10-19"), D("2026-10-26")]
    h = {
        "A": [(d, 4.3) for d in weeks],
        "B": [(date.fromordinal(d.toordinal() + 2), 4.2) for d in weeks],
        "C": [(date.fromordinal(d.toordinal() + 1), 4.1) for d in weeks],
    }
    assert compute_badge(h, "B", D("2026-11-05")) == "Top 3 for 4 weeks"


def test_steady_rate():
    pts = [(date.fromordinal(D("2026-08-03").toordinal() + 7 * i), 3.9) for i in range(10)]
    h = {"A": pts, **{f"X{i}": [(d, 5.0) for d, _ in pts] for i in range(3)}}
    assert compute_badge(h, "A", D("2026-10-10")) == "Steady rate for 10 weeks"


def test_single_point_no_badge():
    assert compute_badge({"A": [(D("2026-11-03"), 4.0)]}, "A", D("2026-11-05")) is None


@pytest.fixture
def tmp_duckdb_with_marts():
    c = duckdb.connect()
    c.execute("CREATE SCHEMA MART; CREATE SCHEMA STAGING")
    c.execute("""CREATE TABLE MART.fct_savings_offers AS SELECT * FROM (VALUES
        ('CIT Bank', 3.75, 4.35, 6, DATE '2026-12-15', 100.0, 5000.0, 0.0, 'https://www.cit.com/', DATE '2026-11-03', DATE '2026-11-05'),
        ('Peak Bank', 4.27, NULL, NULL, NULL, 100.0, 0.0, 0.0, NULL, DATE '2026-11-03', DATE '2026-11-05')
      ) t(bank_name, apy_pct, promo_apy_pct, promo_months, promo_expires, min_opening, min_balance_for_apy, min_monthly_deposit, url, apy_as_of, snapshot_date)""")
    c.execute("""CREATE TABLE MART.fct_savings_rate_history AS SELECT * FROM (VALUES
        ('CIT Bank', DATE '2026-10-27', 3.75), ('CIT Bank', DATE '2026-11-03', 3.75),
        ('Peak Bank', DATE '2026-10-27', 4.27), ('Peak Bank', DATE '2026-11-03', 4.27)
      ) t(bank_name, rate_date, apy_pct)""")
    c.execute("""CREATE TABLE STAGING.stg_fred_observations AS SELECT * FROM (VALUES
        ('FEDFUNDS', DATE '2026-09-01', 4.10), ('FEDFUNDS', DATE '2026-10-01', 3.88),
        ('GS1', DATE '2026-10-01', 4.46)
      ) t(series_id, date_day, rate_pct)""")
    c.execute("""CREATE TABLE STAGING.stg_big_bank_savings AS SELECT * FROM (VALUES
        ('Citibank', 0.05, DATE '2026-11-06'),
        ('JPMorgan Chase', 0.01, DATE '2026-11-06')
      ) t(bank_name, apy_pct, as_of)""")
    yield c
    c.close()


def test_payload_shape(tmp_duckdb_with_marts):
    p = build_payload(tmp_duckdb_with_marts, today=D("2026-11-05"))
    assert set(p) == {"as_of", "fed_funds", "treasury_1y", "banks", "big_banks", "trend"}
    assert p["as_of"] == "2026-11-05"
    assert p["fed_funds"] == {"rate": 3.88, "as_of": "2026-10-01"}
    assert p["treasury_1y"] == {"rate": 4.46, "as_of": "2026-10-01"}
    assert [b["name"] for b in p["banks"]] == ["Peak Bank", "CIT Bank"]
    cit = p["banks"][1]
    assert cit["promo"] == {"apy": 4.35, "months": 6, "expires": "2026-12-15"}
    assert cit["min_balance_for_apy"] == 5000 and cit["min_opening"] == 100
    assert p["banks"][0]["promo"] is None and p["banks"][0]["url"] is None
    assert p["big_banks"] == [
        {"name": "JPMorgan Chase", "apy": 0.01, "as_of": "2026-11-06"},
        {"name": "Citibank", "apy": 0.05, "as_of": "2026-11-06"},
    ]


def test_expired_promo_is_dropped(tmp_duckdb_with_marts):
    p = build_payload(tmp_duckdb_with_marts, today=D("2026-12-16"))
    assert p["banks"][1]["name"] == "CIT Bank" and p["banks"][1]["promo"] is None
    p = build_payload(tmp_duckdb_with_marts, today=D("2026-12-15"))
    assert p["banks"][1]["promo"] is not None


def test_monthly_deposit_requirement_exported(tmp_duckdb_with_marts):
    p = build_payload(tmp_duckdb_with_marts, today=D("2026-11-05"))
    assert p["banks"][0]["min_monthly_deposit"] == 0


def test_trend_weekly_leader_and_fed_funds(tmp_duckdb_with_marts):
    c = tmp_duckdb_with_marts
    # CIT raises mid-week (latest point in the week wins) and the raise sticks
    c.execute("INSERT INTO MART.fct_savings_rate_history VALUES ('CIT Bank', DATE '2026-10-29', 4.40)")
    c.execute("UPDATE MART.fct_savings_rate_history SET apy_pct = 4.40 WHERE bank_name = 'CIT Bank' AND rate_date = DATE '2026-11-03'")
    p = build_payload(c, today=D("2026-11-05"))
    assert p["trend"]["leaders"] == [
        {"week": "2026-10-26", "name": "CIT Bank", "apy": 4.4},
        {"week": "2026-11-02", "name": "CIT Bank", "apy": 4.4},
    ]
    assert p["trend"]["flags"] == []
    # Fed funds from the month the history starts
    assert p["trend"]["fed_funds"] == [{"date": "2026-10-01", "rate": 3.88}]


def test_flagged_spike_is_excluded_from_leaders_but_reported(tmp_duckdb_with_marts):
    c = tmp_duckdb_with_marts
    c.execute("""INSERT INTO MART.fct_savings_rate_history VALUES
        ('CIT Bank', DATE '2026-10-13', 3.75), ('CIT Bank', DATE '2026-10-20', 5.00),
        ('Peak Bank', DATE '2026-10-13', 4.27), ('Peak Bank', DATE '2026-10-20', 4.27)""")
    p = build_payload(c, today=D("2026-11-05"))
    week_1019 = [l for l in p["trend"]["leaders"] if l["week"] == "2026-10-19"]
    assert week_1019 == [{"week": "2026-10-19", "name": "Peak Bank", "apy": 4.27}]
    assert [(f["bank"], f["date"], f["apy"]) for f in p["trend"]["flags"]] == [("CIT Bank", "2026-10-20", 5.0)]
