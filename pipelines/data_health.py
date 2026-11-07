"""Self-checks the daily pipeline publishes with the data, so the site can show
whether today's numbers deserve trust, and flag suspicious points instead of
silently plotting (or silently dropping) them."""
from datetime import date

History = dict[str, list[tuple[date, float]]]

SPIKE_PTS = 0.5      # a one-week move this big...
REVERT_PTS = 0.1     # ...that lands back within this of where it started


def detect_anomalies(history: History) -> list[dict]:
    """One-week spikes or dips that revert the next week: almost always a data
    error or a one-off, not a real rate change. Edge points have only one
    neighbor, so a real change can't be told apart there; they're never flagged."""
    flags = []
    for bank, points in history.items():
        pts = sorted(points)
        for (_, before), (d, cur), (_, after) in zip(pts, pts[1:], pts[2:]):
            if (abs(before - after) <= REVERT_PTS
                    and abs(cur - before) >= SPIKE_PTS and abs(cur - after) >= SPIKE_PTS):
                verb = "Jumped" if cur > before else "Dropped"
                flags.append({
                    "bank": bank, "date": d.isoformat(), "apy": cur, "before": before, "after": after,
                    "reason": f"{verb} {abs(cur - before):.2f} pts for one week, then reverted",
                })
    return sorted(flags, key=lambda f: (f["date"], f["bank"]))


def _age(iso: str, today: date) -> int:
    return (today - date.fromisoformat(iso)).days


def _check(name: str, ok: bool, detail: str) -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail}


def health_checks(payload: dict, today: date, dbt: dict | None) -> list[dict]:
    banks = payload["banks"]
    names = [b["name"] for b in banks]
    checks = []

    age = _age(payload["as_of"], today)
    checks.append(_check("Rates are fresh", age <= 14,
                         f"Bankrate rates as of {payload['as_of']}" + ("" if age <= 14 else f" ({age} days old)")))
    checks.append(_check("Banks parsed", len(set(names)) >= 8, f"{len(set(names))} banks"))
    bad = [b["name"] for b in banks if not 0 < b["apy"] < 10]
    checks.append(_check("APYs in a sane range", not bad, "all between 0% and 10%" if not bad else "out of range: " + ", ".join(bad)))
    dupes = sorted({n for n in names if names.count(n) > 1})
    checks.append(_check("No duplicate banks", not dupes, "none" if not dupes else ", ".join(dupes)))

    fed = payload.get("fed_funds")
    if fed:
        fage = _age(fed["as_of"], today)
        checks.append(_check("Fed data is current", fage <= 62, f"FRED, {fed['as_of']}"))

    big_dates = [b["as_of"] for b in payload.get("big_banks", []) if b.get("as_of")]
    if big_dates:
        bage = _age(min(big_dates), today)
        checks.append(_check("Big-bank rates are fresh", bage <= 90,
                             f"as of {min(big_dates)}" + ("" if bage <= 90 else f" ({bage} days old)")))

    if dbt:
        total = dbt["pass"] + dbt["fail"]
        checks.append(_check("dbt tests", dbt["fail"] == 0 and total > 0, f"{dbt['pass']} of {total} passed"))
    return checks
