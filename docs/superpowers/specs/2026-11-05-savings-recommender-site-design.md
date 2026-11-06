# Savings Recommender Site — Design

**Date:** 2026-11-05
**Status:** Approved by user 2026-11-05 ("do whatever is correct")

## Intent

Turn the project from a class dashboard into a simple public tool for everyday people
and wealth-management clients: **type how much you want to invest, see where it grows
the most.** No longer graded for ISBA-4715, so the descriptive/diagnostic analytics
tabs go away. The value is the recommendation, backed by a real weekly data pipeline.

Success: someone lands on the link, answers one question, and within seconds knows
which bank to use, how much they'll have in N years, and why it's trustworthy. It looks
polished (black + green), reads top-to-bottom with no clutter, and stays up forever at
zero cost.

## Goals

1. Three-step flow: **ask → loading animation → dashboard.**
2. Recommend the best high-yield savings account for the amount, with growth projection.
3. Monthly contributions factored into every projection.
4. Show trust signals (track record over weeks) and a direct "Open account" link.
5. Shareable URL that reopens the same result.
6. Fully free, never sleeps, refreshed **daily** by the existing pipeline.
7. Accurate: projections use the rate a person would actually earn over time.

## Non-goals

- Email/rate alerts, user accounts, logins, saved portfolios.
- After-tax earnings.
- CD recommendations (deferred: current scraper can't tell which term pays which rate).
- Stocks or any market-risk product.
- The old descriptive/diagnostic analytics views.

## Anti-goals (would make it a failure even if it works)

- Busy, multi-panel "analytics" layout. User explicitly rejected the dense dashboard;
  information must flow in one clear column.
- Wording about "saving". The question is about **investing / growing** money.
- Anything that costs money or can expire (paid APIs, trials, hosts that sleep).
- Inaccurate numbers. Every figure must come from the pipeline's data.

## Rate accuracy (decided)

Bankrate's headline APY is often a promo or conditional rate. Example this week:
CIT Bank shows 4.35%, which is a 3.75% base + 0.60% promo code for 6 months
(offer expires 12/15/2026) and requires a $5,000 balance for the APY. Happen Bank's
4.25% is a 3-month promo.

- **Promo-then-base modeling (user chose "whatever is correct" → option A):**
  capture promo rate, promo length, and base rate when Bankrate states them.
  Project using the promo rate for its length, then the base rate. Rank banks by
  what they actually earn over the selected horizon (so the winner can change between
  1 yr and 10 yr). Display as "4.35% for 6 months, then 3.75%".
- If no promo info is stated, the headline APY is treated as the ongoing rate.
- **Minimum balance for APY** governs eligibility: if the amount is below it, the bank
  is not recommended at that rate (exclude it, Claude's call). Minimum to open is shown
  in the meta line. Fall back to minimum to open when no balance-for-APY is listed.
- **Editorial list only:** only Bankrate's editorial "best" list is recommendable;
  the sponsored offers table is used only to read promo/balance details for banks
  already in the editorial list. No paid placements are recommended. (Claude's call.)
- **Chase comparison:** hand-maintained rate (0.01%) from the seed, shown with its own
  as-of date. Stale online-bank rows in `big_four_rates.csv` (SoFi, Marcus, Ally,
  April) are removed. (Claude's call.)

## User flow (decided with user)

### Screen 1 — Ask
- Full black screen, centered.
- Headline: **"How much are you looking to invest?"**, one big dollar input (default 25,000).
- Monthly contribution choice beneath it: a one-click **"No monthly contributions"**
  option, or an amount per month (e.g. $500). Default: no contributions.
- Primary button **"Show me →"**; Enter also submits.

### Screen 2 — Loading animation (~4 s)
Three steps that check off in order, with a thin green progress bar:
1. "Checking the Fed rate" → shows current Fed funds rate (from data).
2. "Scanning bank rates" → bank names tick past quickly → "N banks".
3. "Growing your money" → 10-year total counts up.
Copy must not claim a live scrape is happening; the data is from the weekly refresh
(sub-label e.g. "Bankrate · this week").

### Screen 3 — Dashboard (single column, ~720px wide)
Top to bottom:
1. **Top bar:** editable amount pill + editable monthly pill; "Rates as of <date>".
   Editing updates everything instantly, never replays the animation.
2. **Answer:** eyebrow "Best place for your money", headline **"Put it in <Bank>"**
   (bank in green), one meta line: APY · minimum to open · FDIC insured · earns $X/yr.
   Track-record badge and **Open account →** link on the top pick.
3. **Treasury line** (only when a Treasury beats the top savings APY):
   *"Won't need it for a year? A 1-year Treasury pays 4.46%, about $28 more."*
   Uses FRED 1-year (GS1); if the 3-month (TB3MS) or 2-year (GS2) is the better
   fit, the builder may pick the single most useful one, but show one line only.
4. **Growth card:** big green end balance, caption "in N years · +$X earned",
   "At Chase instead $Y" on the right, line chart (top pick solid green with soft
   fill vs Chase dashed red), horizon toggles **1 / 5 / 10 / 20 yr** (default 10).
5. **Other great options:** next 4 banks (name, minimum, APY, per-year earnings,
   badge, Open account link), then JPMorgan Chase row in muted/red for contrast.
6. **FDIC note** only when amount > $250,000: suggest a split across top banks,
   max $250,000 each.
7. Footer: "High-yield savings accounts, FDIC insured. Rates from Bankrate, refreshed
   weekly. Not financial advice."

Banks whose minimum deposit exceeds the amount are excluded from the recommendation.

### Visual style (approved in mockup `flow-v3`)
Black background (#050605), green accent (#22e07a), red for the big-bank contrast,
Inter for text, JetBrains Mono for numbers. Fade-in on the dashboard. Must work at
phone width.

## Features in detail

### Monthly contributions
Projection = initial amount compounded monthly at the APY's monthly equivalent,
plus contribution added each month. "Earned" = end balance − total deposited.
Applies to the headline total, chart, Chase comparison, list, and Treasury delta
(Treasury delta can be computed on the initial amount over 1 year; builder's call).

### Track-record badge
Computed from the Bankrate snapshots in `knowledge/raw/` (fact table keeps
every `scrape_date`). Show at most one short badge per bank, e.g.
"Top 3 for 8 weeks", "Rate up 0.10%", "Rate cut 0.10% last week", "New this week".
Only show a badge when there are at least two snapshots to compare. History today is
thin (an April snapshot and this week's), so badges will be sparse at first and grow
weekly. Exact badge rules are the builder's call, within "one short, factual badge".

### Open account link
Small maintained mapping of bank name → official website URL, kept in the repo
(e.g. a dbt seed or JSON file). Bankrate only exposes tracking redirects, so we don't
use those. If a bank has no mapped URL, hide the link for that bank (no broken links).
Opens in a new tab.

### Shareable URL
Amount and monthly contribution in the query string (e.g. `?amount=25000&monthly=500`).
A URL with an amount skips screens 1–2 and opens the dashboard directly. Editing
amounts on the dashboard updates the URL without reloading.

## How it's built

### Decided
- **Leave Streamlit.** Static site on **GitHub Pages** (free, never sleeps). New URL
  `https://danieldistor.github.io/deposit-pricing-analytics-banking/` (builder may set a
  nicer one later).
- **Data pipeline stays:** FRED + Bankrate → DuckDB → dbt → export (already working
  via `.github/workflows/refresh-data.yml`), schedule changed from weekly to **daily**.
  A new raw snapshot is committed only when parsed rates changed, to avoid repo bloat.
  Badge wording uses "days"/"weeks" accordingly.
- **Black + green**, single-column flow as in mockup `flow-v3`.

### Claude's calls (user can override)
- Plain HTML/CSS/JavaScript, no framework or build step. Lives in a `site/` folder.
  Start from the approved mockup `docs/superpowers/mockups/flow-v3.html` (copy into the repo as the base).
- Pipeline exports one small JSON file (e.g. `site/data/rates.json`) with: as-of date,
  Fed funds rate, Treasury yields, latest savings rates per bank (APY, minimum, URL,
  badge), and Chase/big-bank rates. The site loads only that file.
- Minimum to open, minimum balance for APY, promo rate/length/base rate must be
  captured by the parser (currently dropped) and carried through raw → staging →
  mart → export.
- Seed rows in `big_four_rates.csv` that are stale online banks (SoFi, Marcus, Ally
  from April) should not be recommended; keep only the big-bank comparison rows or
  date-filter them out.
- Deploy with GitHub Actions to Pages (on push to main and after the weekly refresh).
- Retire the Streamlit app (`dashboard/`) and `keep-alive.yml`; update README link.

## Left to the builder
- File/module structure of the site, animation timing details, chart implementation
  (hand-drawn SVG is fine; no heavy chart library needed).
- Exact badge wording and thresholds.
- How the dbt models change to support minimum deposit and history.
- Tests: parser test for minimum deposit, a check that the exported JSON matches what
  the site expects, and a quick headless render check of all three screens.
