"""Export the single JSON file the static site reads: site/data/rates.json."""
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    from pipelines.daily_brief import advance_state, build_brief, render_rss, update_log
    from pipelines.data_health import detect_anomalies, health_checks
    from pipelines.warehouse import REPO_ROOT, connect
except ImportError:  # run as `python pipelines/export_site_data.py`
    from daily_brief import advance_state, build_brief, render_rss, update_log
    from data_health import detect_anomalies, health_checks
    from warehouse import REPO_ROOT, connect

OUT_PATH = REPO_ROOT / "site" / "data" / "rates.json"
BRIEF_PATH = REPO_ROOT / "site" / "data" / "brief.json"
FEED_PATH = REPO_ROOT / "site" / "data" / "feed.xml"
DBT_RESULTS = REPO_ROOT / "dbt" / "target" / "run_results.json"
SITE_URL = "https://danieldistor.github.io/deposit-pricing-analytics-banking/"
COMPARISON_BANK = "JPMorgan Chase"
TREASURY_SERIES = {12: "GS1", 24: "GS2", 36: "GS3", 60: "GS5"}  # constant-maturity yields

History = dict[str, list[tuple[date, float]]]


def _week(d: date) -> date:
    """Monday of d's week; Bankrate posts each bank's weekly rate on different days."""
    return d - timedelta(days=d.weekday())


def _top3_streak(history: History, bank: str) -> int:
    weekly: dict[date, dict[str, float]] = defaultdict(dict)
    for name, points in history.items():
        for d, rate in sorted(points):
            weekly[_week(d)][name] = rate  # latest point in the week wins
    streak = 0
    for week in sorted(weekly, reverse=True):
        rates = weekly[week]
        if bank not in rates:
            break
        higher = sum(1 for r in rates.values() if r > rates[bank])
        if higher >= 3:
            break
        streak += 1
    return streak


def compute_badge(history: History, bank: str, as_of: date) -> str | None:
    points = sorted(history.get(bank, []))
    if len(points) < 2:
        return None

    (prev_d, prev_r), (last_d, last_r) = points[-2], points[-1]
    if last_r != prev_r and (as_of - last_d).days <= 14:
        word = "up" if last_r > prev_r else "cut"
        return f"Rate {word} {abs(last_r - prev_r):.2f}%"

    top3 = _top3_streak(history, bank)
    if top3 >= 4:
        return f"Top 3 for {top3} weeks"

    steady = 1
    for _, rate in reversed(points[:-1]):
        if rate != last_r:
            break
        steady += 1
    if steady >= 8:
        return f"Steady rate for {steady} weeks"
    return None


def _weekly_leaders(history: History) -> list[dict]:
    """The highest-APY bank each Monday-week (latest point per bank per week)."""
    weekly: dict[date, dict[str, float]] = defaultdict(dict)
    for name, points in history.items():
        for d, rate in sorted(points):
            weekly[_week(d)][name] = rate
    out = []
    for week in sorted(weekly):
        name, apy = min(weekly[week].items(), key=lambda kv: (-kv[1], kv[0]))
        out.append({"week": week.isoformat(), "name": name, "apy": apy})
    return out


def _fred_since(conn, series_id: str, start: date) -> list[dict]:
    rows = conn.execute(
        """SELECT date_day, rate_pct FROM STAGING.stg_fred_observations
           WHERE series_id = ? AND date_day >= ? ORDER BY date_day""",
        [series_id, start.replace(day=1)],
    ).fetchall()
    return [{"date": d.isoformat(), "rate": round(float(r), 2)} for d, r in rows]


def _latest_fred(conn, series_id: str) -> dict | None:
    row = conn.execute(
        """SELECT rate_pct, date_day FROM STAGING.stg_fred_observations
           WHERE series_id = ? ORDER BY date_day DESC LIMIT 1""",
        [series_id],
    ).fetchone()
    return {"rate": round(float(row[0]), 2), "as_of": row[1].isoformat()} if row else None


def _num(x: float) -> float | int:
    return int(x) if float(x).is_integer() else float(x)


def build_payload(conn, today: date | None = None) -> dict:
    today = today or date.today()
    offers = conn.execute(
        """SELECT bank_name, apy_pct, promo_apy_pct, promo_months, promo_expires,
                  min_opening, min_balance_for_apy, min_monthly_deposit, url, snapshot_date
           FROM MART.fct_savings_offers ORDER BY apy_pct DESC, bank_name"""
    ).fetchall()
    if not offers:
        raise SystemExit("MART.fct_savings_offers is empty; refusing to export.")
    as_of = max(o[9] for o in offers)

    history: History = defaultdict(list)
    for name, d, rate in conn.execute(
        "SELECT bank_name, rate_date, apy_pct FROM MART.fct_savings_rate_history"
    ).fetchall():
        history[name].append((d, float(rate)))
    # Flagged one-week spikes stay out of badges and the #1 history, but are
    # published so the site can show them instead of silently hiding them.
    flags = detect_anomalies(history)
    flagged = {(f["bank"], f["date"]) for f in flags}
    history = {n: [(d, r) for d, r in pts if (n, d.isoformat()) not in flagged] for n, pts in history.items()}

    banks = []
    for name, apy, p_apy, p_months, p_exp, min_open, min_apy, min_monthly, url, _ in offers:
        promo = None
        expired = p_exp is not None and p_exp < today  # new sign-ups can't get it anymore
        if p_apy is not None and p_months and not expired:
            promo = {"apy": float(p_apy), "months": int(p_months),
                     "expires": p_exp.isoformat() if p_exp else None}
        banks.append({
            "name": name,
            "apy": float(apy),
            "promo": promo,
            "min_opening": _num(min_open),
            "min_balance_for_apy": _num(min_apy),
            "min_monthly_deposit": _num(min_monthly or 0),
            "url": url,
            "badge": compute_badge(history, name, as_of),
        })

    big_banks = [
        {"name": n, "apy": float(a), "as_of": d.isoformat()}
        for n, a, d in conn.execute(
            """SELECT bank_name, apy_pct, as_of FROM STAGING.stg_big_bank_savings
               ORDER BY bank_name <> ?, bank_name""",
            [COMPARISON_BANK],
        ).fetchall()
    ]

    leaders = _weekly_leaders(history)
    trend = {
        "leaders": leaders,
        "fed_funds": _fred_since(conn, "FEDFUNDS", date.fromisoformat(leaders[0]["week"])) if leaders else [],
        "flags": flags,
    }

    cds = [
        {"name": n, "term_months": int(t), "apy": float(a), "min_deposit": _num(m or 0), "url": u}
        for n, t, a, m, u in conn.execute(
            """SELECT bank_name, term_months, apy_pct, min_deposit, url FROM STAGING.stg_cd_offers
               ORDER BY term_months, apy_pct DESC, bank_name"""
        ).fetchall()
    ]
    treasuries = {str(months): t for months, sid in TREASURY_SERIES.items()
                  if (t := _latest_fred(conn, sid))}

    return {
        "as_of": as_of.isoformat(),
        "fed_funds": _latest_fred(conn, "FEDFUNDS"),
        "treasury_1y": _latest_fred(conn, "GS1"),
        "banks": banks,
        "big_banks": big_banks,
        "trend": trend,
        "cds": cds,
        "treasuries": treasuries,
    }


def _dbt_results() -> dict | None:
    """Pass/fail counts of dbt tests from the run that just happened (absent locally)."""
    if not DBT_RESULTS.exists():
        return None
    results = json.loads(DBT_RESULTS.read_text())["results"]
    tests = [r["status"] for r in results if r["unique_id"].startswith("test.")]
    return {"pass": tests.count("pass"), "fail": len(tests) - tests.count("pass")} if tests else None


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def main() -> None:
    conn = connect()
    try:
        payload = build_payload(conn)
    finally:
        conn.close()
    today = date.today()
    day = today.isoformat()

    payload["health"] = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "checks": health_checks(payload, today, _dbt_results()),
        "history_weeks": len(payload["trend"]["leaders"]),
    }

    brief_state = _read_json(BRIEF_PATH, {})
    prev, state = advance_state(brief_state.get("state", {}), payload, day)
    log = update_log(brief_state.get("log", []), build_brief(prev, payload, day))
    payload["brief"] = log[:7]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    BRIEF_PATH.write_text(json.dumps({"state": state, "log": log}, indent=2) + "\n", encoding="utf-8")
    FEED_PATH.write_text(render_rss(log, SITE_URL), encoding="utf-8")
    failing = [c["name"] for c in payload["health"]["checks"] if not c["ok"]]
    print(f"Wrote {OUT_PATH.relative_to(REPO_ROOT)}: {len(payload['banks'])} banks, "
          f"{len(payload['big_banks'])} big banks, as of {payload['as_of']}; "
          f"{len(payload['trend']['flags'])} flagged points; failing checks: {failing or 'none'}")
    print(f"Brief: {log[0]['headline']}")


if __name__ == "__main__":
    main()
