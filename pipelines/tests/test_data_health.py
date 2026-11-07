from datetime import date, datetime, timezone

from pipelines.data_health import detect_anomalies, health_checks

D = date.fromisoformat


def weekly(rates, start="2026-08-04"):
    s = D(start).toordinal()
    return [(date.fromordinal(s + 7 * i), r) for i, r in enumerate(rates)]


def test_spike_that_reverts_is_flagged():
    h = {"Accordia Bank": weekly([4.00, 4.00, 5.00, 4.00, 4.00]), "Peak Bank": weekly([4.2] * 5)}
    assert detect_anomalies(h) == [{
        "bank": "Accordia Bank", "date": "2026-08-18", "apy": 5.0, "before": 4.0, "after": 4.0,
        "reason": "Jumped 1.00 pts for one week, then reverted",
    }]


def test_dip_that_reverts_is_flagged():
    h = {"A": weekly([4.0, 3.2, 4.0])}
    assert [a["apy"] for a in detect_anomalies(h)] == [3.2]


def test_real_rate_change_is_not_flagged():
    # a cut that sticks is news, not an error
    assert detect_anomalies({"A": weekly([4.2, 4.2, 3.5, 3.5, 3.5])}) == []


def test_small_wiggle_is_not_flagged():
    assert detect_anomalies({"A": weekly([4.0, 4.3, 4.0])}) == []


def test_edges_are_never_flagged():
    # first/last points have only one neighbor; can't tell a spike from a change
    assert detect_anomalies({"A": weekly([5.0, 4.0, 4.0, 5.0])}) == []


def payload(**over):
    p = {
        "as_of": "2026-11-05",
        "fed_funds": {"rate": 3.88, "as_of": "2026-10-01"},
        "banks": [{"name": f"B{i}", "apy": 4.0} for i in range(10)],
        "big_banks": [{"name": "JPMorgan Chase", "apy": 0.01}],
    }
    p.update(over)
    return p


def by_name(checks):
    return {c["name"]: c for c in checks}


def test_health_all_green():
    checks = by_name(health_checks(payload(), today=D("2026-11-06"), dbt={"pass": 32, "fail": 0}))
    assert all(c["ok"] for c in checks.values()), checks
    assert checks["dbt tests"]["detail"] == "32 of 32 passed"
    assert checks["Banks parsed"]["detail"] == "10 banks"


def test_health_flags_stale_rates_and_few_banks_and_bad_apy():
    p = payload(as_of="2026-10-01", banks=[{"name": "A", "apy": 40.0}, {"name": "A", "apy": 4.0}])
    checks = by_name(health_checks(p, today=D("2026-11-06"), dbt=None))
    assert not checks["Rates are fresh"]["ok"]
    assert not checks["Banks parsed"]["ok"]
    assert not checks["APYs in a sane range"]["ok"]
    assert not checks["No duplicate banks"]["ok"]
    assert "dbt tests" not in checks  # no run results available locally -> no claim


def test_health_flags_failed_dbt_tests():
    checks = by_name(health_checks(payload(), today=D("2026-11-06"), dbt={"pass": 30, "fail": 2}))
    assert not checks["dbt tests"]["ok"]
    assert checks["dbt tests"]["detail"] == "30 of 32 passed"
