"""Scrape Bankrate's best-rate pages with plain HTTP and save them as markdown.

Uses requests + html2text (both free) instead of a paid scraping API. Runs daily;
a dated snapshot is saved to knowledge/raw/ only when the parsed rates differ from
the newest existing snapshot, so the repo doesn't fill with identical pages.
"""
from datetime import date
from pathlib import Path

import html2text
import requests

try:
    from pipelines.parse_bankrate import extract_rates_from_markdown
    from pipelines.parse_savings_offers import parse_editorial_offers, parse_promos, parse_rate_history
except ImportError:  # run as `python pipelines/extract_bankrate.py`
    from parse_bankrate import extract_rates_from_markdown
    from parse_savings_offers import parse_editorial_offers, parse_promos, parse_rate_history

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "knowledge" / "raw"

TARGETS = [
    {
        "url": "https://www.bankrate.com/banking/savings/best-high-yield-interests-savings-accounts/",
        "slug": "bankrate_savings",
    },
    {
        "url": "https://www.bankrate.com/banking/cds/best-cd-rates/",
        "slug": "bankrate_cds",
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}


def html_to_markdown(html: str) -> str:
    converter = html2text.HTML2Text()
    converter.body_width = 0       # don't hard-wrap lines; the parser is line-based
    converter.ignore_images = True
    converter.ul_item_mark = "-"   # "- Bank — 4.00% APY" list items
    return converter.handle(html)


def scrape_page(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    markdown = html_to_markdown(r.text)
    if "APY" not in markdown:
        raise ValueError(f"No APY content found at {url} (page layout may have changed or request was blocked)")
    return markdown


def _fingerprint(markdown: str):
    """What we actually use from a page; ignores ads, timestamps, and layout noise."""
    offers = parse_editorial_offers(markdown)
    if offers:
        rates = [(o["bank_name"], o["apy_pct"], o["min_balance_for_apy"], o["min_opening"]) for o in offers]
        promos = parse_promos(markdown, [o["bank_name"] for o in offers])
        history = {(r["bank_name"], r["rate_date"], r["apy_pct"]) for r in parse_rate_history(markdown)}
        return rates, promos, history
    return sorted((r["bank_name"], r["term_months"], r["apy_pct"])
                  for r in extract_rates_from_markdown(markdown, "cd", date.today()))


def should_save(new_md: str, previous_md: str | None) -> bool:
    return previous_md is None or _fingerprint(new_md) != _fingerprint(previous_md)


def _latest_snapshot(slug: str) -> str | None:
    files = sorted(OUTPUT_DIR.glob(f"{slug}_*.md"))
    return files[-1].read_text(encoding="utf-8") if files else None


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    for target in TARGETS:
        print(f"Scraping {target['url']}...", flush=True)
        markdown = scrape_page(target["url"])
        if not should_save(markdown, _latest_snapshot(target["slug"])):
            print("  No rate changes; snapshot not saved.")
            continue
        out_path = OUTPUT_DIR / f"{target['slug']}_{today}.md"
        out_path.write_text(markdown, encoding="utf-8")
        print(f"  Saved: {out_path} ({len(markdown):,} chars)")

    print("Done!")


if __name__ == "__main__":
    main()
