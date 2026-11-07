"""The daily "What changed" brief: yesterday's published data vs today's,
written as plain sentences, kept as a 30-day log and published as RSS."""
from datetime import date, datetime, timezone
from email.utils import format_datetime
from xml.etree import ElementTree as ET


def _leader(payload: dict) -> dict:
    return max(payload["banks"], key=lambda b: b["apy"])  # max keeps the first on ties


def _pct(x: float) -> str:
    return f"{x:.2f}%"


def build_brief(prev: dict | None, cur: dict, day: str) -> dict:
    lead = _leader(cur)
    if prev is None:
        return {"date": day, "headline": f"{lead['name']} is #1 at {_pct(lead['apy'])}.", "items": []}

    before = {b["name"]: b for b in prev["banks"]}
    now = {b["name"]: b for b in cur["banks"]}
    items = []

    for b in cur["banks"]:
        old = before.get(b["name"])
        if old and round(b["apy"] - old["apy"], 2):
            diff = b["apy"] - old["apy"]
            verb = "raised" if diff > 0 else "cut"
            items.append(f"{b['name']} {verb} its rate {abs(diff):.2f} pts to {_pct(b['apy'])}.")
    items += [f"{b['name']} joined the list at {_pct(b['apy'])}." for b in cur["banks"] if b["name"] not in before]
    items += [f"{b['name']} dropped off the list." for b in prev["banks"] if b["name"] not in now]

    for b in cur["banks"]:
        old = before.get(b["name"])
        if not old:
            continue
        if b.get("promo") and not old.get("promo"):
            items.append(f"{b['name']} added a promo: {_pct(b['promo']['apy'])} for {b['promo']['months']} months.")
        elif old.get("promo") and not b.get("promo"):
            items.append(f"{b['name']}'s promo rate ended.")

    for key, label in (("fed_funds", "Fed funds rate"), ("treasury_1y", "1-year Treasury")):
        a, z = (prev.get(key) or {}).get("rate"), (cur.get(key) or {}).get("rate")
        if a is not None and z is not None and a != z:
            items.append(f"{label} moved from {_pct(a)} to {_pct(z)}.")

    old_lead = _leader(prev)
    if old_lead["name"] != lead["name"]:
        headline = f"{lead['name']} takes #1 at {_pct(lead['apy'])}, passing {old_lead['name']}."
    elif not items:
        headline = f"No rate changes. {lead['name']} is still #1 at {_pct(lead['apy'])}."
    else:
        headline = f"{lead['name']} is still #1 at {_pct(lead['apy'])}."
    return {"date": day, "headline": headline, "items": items}


def update_log(log: list[dict], entry: dict, keep: int = 30) -> list[dict]:
    rest = [e for e in log if e["date"] != entry["date"]]
    return sorted([entry, *rest], key=lambda e: e["date"], reverse=True)[:keep]


def render_rss(log: list[dict], site_url: str) -> str:
    rss = ET.Element("rss", version="2.0")
    ch = ET.SubElement(rss, "channel")
    ET.SubElement(ch, "title").text = "Where to Grow It · Daily savings rate brief"
    ET.SubElement(ch, "link").text = site_url
    ET.SubElement(ch, "description").text = "What changed in high-yield savings rates today, from Bankrate and FRED."
    for e in log:
        it = ET.SubElement(ch, "item")
        ET.SubElement(it, "title").text = e["headline"]
        ET.SubElement(it, "link").text = site_url
        ET.SubElement(it, "description").text = " ".join(e["items"]) or e["headline"]
        ET.SubElement(it, "guid", isPermaLink="false").text = f"{site_url}#brief-{e['date']}"
        d = date.fromisoformat(e["date"])
        ET.SubElement(it, "pubDate").text = format_datetime(datetime(d.year, d.month, d.day, 12, tzinfo=timezone.utc))
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(rss, encoding="unicode") + "\n"


def _slim(payload: dict) -> dict:
    return {
        "banks": [{"name": b["name"], "apy": b["apy"], "promo": b.get("promo")} for b in payload["banks"]],
        "fed_funds": payload.get("fed_funds"),
        "treasury_1y": payload.get("treasury_1y"),
    }


def advance_state(state: dict, cur: dict, day: str) -> tuple[dict | None, dict]:
    """Return (the payload to compare today against, the new state).
    State keeps the last published day and the one before it, so a same-day
    rerun still compares against yesterday instead of against itself."""
    last, prev = state.get("last"), state.get("prev")
    if last and last["date"] != day:
        prev = last
    base = prev["data"] if prev and prev["date"] < day else None
    return base, {"last": {"date": day, "data": _slim(cur)}, "prev": prev}
