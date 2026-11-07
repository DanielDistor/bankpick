from xml.etree import ElementTree as ET

from pipelines.daily_brief import build_brief, update_log, render_rss, advance_state


def p(banks, fed=3.88, t1=4.46, promos=None):
    promos = promos or {}
    return {
        "as_of": "2026-11-05",
        "fed_funds": {"rate": fed, "as_of": "2026-10-01"},
        "treasury_1y": {"rate": t1, "as_of": "2026-10-01"},
        "banks": [{"name": n, "apy": a, "promo": promos.get(n)} for n, a in banks],
    }


BASE = [("Peak Bank", 4.27), ("EverBank", 4.20), ("Vio Bank", 4.01)]


def test_quiet_day_says_so_and_names_the_leader():
    b = build_brief(p(BASE), p(BASE), "2026-11-06")
    assert b["date"] == "2026-11-06"
    assert b["headline"] == "No rate changes. Peak Bank is still #1 at 4.27%."
    assert b["items"] == []


def test_new_leader_and_rate_moves():
    today = [("EverBank", 4.35), ("Peak Bank", 4.27), ("Vio Bank", 3.95)]
    b = build_brief(p(BASE), p(today), "2026-11-06")
    assert b["headline"] == "EverBank takes #1 at 4.35%, passing Peak Bank."
    assert b["items"] == [
        "EverBank raised its rate 0.15 pts to 4.35%.",
        "Vio Bank cut its rate 0.06 pts to 3.95%.",
    ]


def test_banks_added_and_dropped():
    today = [("Peak Bank", 4.27), ("EverBank", 4.20), ("Bask Bank", 3.90)]
    b = build_brief(p(BASE), p(today), "2026-11-06")
    assert "Bask Bank joined the list at 3.90%." in b["items"]
    assert "Vio Bank dropped off the list." in b["items"]


def test_fed_treasury_and_promo_changes():
    promo = {"apy": 4.35, "months": 6, "expires": "2026-12-15"}
    b = build_brief(p(BASE, promos={"Vio Bank": promo}), p(BASE, fed=3.63, t1=4.40), "2026-11-06")
    assert "Fed funds rate moved from 3.88% to 3.63%." in b["items"]
    assert "1-year Treasury moved from 4.46% to 4.40%." in b["items"]
    assert "Vio Bank's promo rate ended." in b["items"]
    b2 = build_brief(p(BASE), p(BASE, promos={"Vio Bank": promo}), "2026-11-06")
    assert "Vio Bank added a promo: 4.35% for 6 months." in b2["items"]
    assert b2["headline"].startswith("Peak Bank is still #1")


def test_first_run_without_yesterday():
    b = build_brief(None, p(BASE), "2026-11-06")
    assert b["headline"] == "Peak Bank is #1 at 4.27%."
    assert b["items"] == []


def test_update_log_replaces_same_day_and_keeps_newest_first_capped():
    log = [{"date": f"2026-10-{d:02d}", "headline": "x", "items": []} for d in range(30, 0, -1)]
    new = {"date": "2026-10-30", "headline": "rerun", "items": []}
    out = update_log(log, new, keep=30)
    assert out[0] == new and len(out) == 30 and [e["date"] for e in out].count("2026-10-30") == 1
    out = update_log(log, {"date": "2026-10-31", "headline": "y", "items": []}, keep=30)
    assert out[0]["date"] == "2026-10-31" and len(out) == 30 and out[-1]["date"] == "2026-10-02"


def test_rss_is_valid_and_escaped():
    log = [{"date": "2026-11-06", "headline": "A & B <up>", "items": ["one", "two"]}]
    xml = render_rss(log, "https://example.com/site/")
    root = ET.fromstring(xml)
    item = root.find("channel/item")
    assert item.find("title").text == "A & B <up>"
    assert "one" in item.find("description").text
    assert item.find("guid").text == "https://example.com/site/#brief-2026-11-06"
    assert item.find("pubDate").text.startswith("Fri, 06 Nov 2026")


def test_advance_state_compares_against_yesterday_even_on_reruns():
    day1, day2 = p(BASE), p([("Peak Bank", 4.30), ("EverBank", 4.20), ("Vio Bank", 4.01)])
    prev, st = advance_state({}, day1, "2026-11-05")
    assert prev is None and st["last"]["date"] == "2026-11-05"
    prev, st = advance_state(st, day2, "2026-11-06")
    assert prev["banks"][0]["apy"] == 4.27              # yesterday
    prev, st2 = advance_state(st, day2, "2026-11-06")   # same-day rerun
    assert prev["banks"][0]["apy"] == 4.27               # still yesterday, not itself
    assert st2["last"]["data"]["banks"][0]["apy"] == 4.30
    assert set(st2["last"]["data"]) == {"banks", "fed_funds", "treasury_1y"}
