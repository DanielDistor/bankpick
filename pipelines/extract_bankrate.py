"""Scrape Bankrate's best-rate pages with plain HTTP and save them as markdown.

Uses requests + html2text (both free) instead of a paid scraping API. Each run
saves a dated snapshot to knowledge/raw/, which parse_bankrate.py reads.
"""
from datetime import date
from pathlib import Path

import html2text
import requests

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


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    for target in TARGETS:
        print(f"Scraping {target['url']}...", flush=True)
        markdown = scrape_page(target["url"])
        out_path = OUTPUT_DIR / f"{target['slug']}_{today}.md"
        out_path.write_text(markdown, encoding="utf-8")
        print(f"  Saved: {out_path} ({len(markdown):,} chars)")

    print("Done!")


if __name__ == "__main__":
    main()
