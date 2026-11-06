# Savings Recommender Site Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Streamlit dashboard with a static black-and-green site on GitHub Pages that asks how much you're investing (plus optional monthly contributions), plays a short loading animation, and shows the best high-yield savings account with promo-aware growth projections, track-record badges, open-account links, a Treasury alternative line, and a shareable URL.

**Architecture:** The existing pipeline (FRED + Bankrate → DuckDB → dbt) gains a richer Bankrate parser (ongoing APY, promo, minimum balances, weekly rate history) and new dbt models. A Python export writes one `site/data/rates.json`; badge logic lives there. The site is plain HTML/CSS/JS with a pure, node-tested `calc.js` for all money math. GitHub Actions refreshes data daily and deploys Pages.

**Tech Stack:** Python 3.12, DuckDB, dbt-duckdb, html2text, pytest; vanilla JS (ES modules), Node 25 built-in test runner; GitHub Actions + GitHub Pages.

**Spec:** `docs/superpowers/specs/2026-11-05-savings-recommender-site-design.md`
**Approved visual:** `docs/superpowers/mockups/flow-v3.html`

## Global Constraints

- Everything free: no paid APIs, no trials, no host that sleeps.
- Copy: the question is **"How much are you looking to invest?"**; never "save".
- Colors/fonts: bg `#050605`, accent `#22e07a`, big-bank red `#e05252`, Inter text, JetBrains Mono numbers.
- Single column, max width ~720px on the dashboard; must work at 375px phone width.
- Every number on screen comes from `rates.json`; no hard-coded rates in the site.
- Only Bankrate's **editorial picks** are recommendable; the sponsored offers table is read only for promo details of editorial banks.
- FDIC limit `250000`. Horizons `1, 5, 10, 20` years, default `10`. Default amount `25000`, default monthly `0`.
- Loading animation copy must not claim a live scrape (sub-label "Bankrate · this week"-style, using the data's as-of date).
- Footer: "High-yield savings accounts, FDIC insured. Rates from Bankrate, refreshed daily. Not financial advice."

## Review Focus

1. Amount below every bank's eligibility (e.g. `$100`): show the best bank the person *can* open with a one-line note "Most top rates need $X+ to earn their APY", never a blank page. → test in Task 4 (`rankBanks` returns fallback) and Task 5 render check.
2. Bad share URL (`?amount=abc`, `?amount=-5`, `?monthly=1e9`): invalid amount → show the ask screen; invalid monthly → treat as 0; clamp amount to `1 … 100,000,000`. → Task 4 `parseShareParams` tests.
3. Promo shorter than horizon (CIT 6-mo promo at 1 yr and 10 yr) projects promo-then-base correctly, and the winner may differ by horizon. → Task 4 tests.
4. Very large amounts (`$5,000,000`) exceed `250k × eligible banks`: FDIC note lists every eligible bank and says how much is left uninsured. → Task 4 `fdicSplit` test.
5. `rates.json` fails to load: show "Rates are temporarily unavailable. Try again shortly." instead of a broken page. → Task 5 render check.

---

### Task 1: Parse editorial picks, promos, and rate history

**Files:**
- Create: `pipelines/parse_savings_offers.py`
- Create: `pipelines/tests/fixtures/bankrate_savings_2026-11-05.md` (copy of `knowledge/raw/bankrate_savings_2026-11-05.md`)
- Test: `pipelines/tests/test_parse_savings_offers.py`

**Interfaces:**
- Produces:
  - `parse_editorial_offers(markdown: str) -> list[dict]` → keys `bank_name: str, apy_pct: float, min_balance_for_apy: float, min_opening: float, apy_as_of: date`
  - `parse_promos(markdown: str, bank_names: list[str]) -> dict[str, dict]` → `{bank_name: {promo_apy_pct: float, promo_months: int, promo_expires: date | None}}`
  - `parse_rate_history(markdown: str) -> list[dict]` → keys `bank_name, rate_date: date, apy_pct: float`
  - `canonical_bank_name(raw: str) -> str` (strip trailing " savings", "savings account", "Platinum Savings account", "™"; map via existing `normalize_bank_name` in `parse_bankrate.py`; then append " Bank" where the summary list uses it, e.g. "Western State" → "Western State Bank", "Accordia" → "Accordia Bank", "Live Oak" → "Live Oak Bank")

Structure facts (from the real page): editorial section starts at `## Bankrate’s editorial picks` (curly or straight apostrophe) and ends at the next `## ` heading. Each bank is `### <Name> savings`, followed by `APY as of M/D/YYYY`, value line, `Min. balance for APY…` value line, `Min. opening balance…` value line. Rate history rows look like `11/03/2026| 3.75%| 0.57%`. Promo lines live in the offers table under `## Best savings accounts` as `Limited time offer…` lines; attribute each to the nearest preceding bank-name line; ignore banks not in `bank_names`. Number words (`six`) must parse.

- [ ] **Step 1: Write the failing tests** (`test_parse_savings_offers.py`, reading the fixture)

```python
def test_editorial_offers_has_12_banks_with_ongoing_apy():
    offers = {o["bank_name"]: o for o in parse_editorial_offers(FIXTURE)}
    assert len(offers) == 12
    assert offers["CIT Bank"]["apy_pct"] == 3.75
    assert offers["CIT Bank"]["min_balance_for_apy"] == 5000
    assert offers["CIT Bank"]["min_opening"] == 100
    assert offers["Happen Bank"]["min_balance_for_apy"] == 250
    assert "Western State Bank" in offers and "Accordia Bank" in offers

def test_promos_attributed_to_right_bank():
    names = [o["bank_name"] for o in parse_editorial_offers(FIXTURE)]
    promos = parse_promos(FIXTURE, names)
    assert promos["CIT Bank"] == {"promo_apy_pct": 4.35, "promo_months": 6, "promo_expires": date(2026, 12, 15)}
    assert promos["Vio Bank"] == {"promo_apy_pct": 4.25, "promo_months": 3, "promo_expires": None}
    assert "Capital One" not in promos  # sponsored-only bank ignored

def test_rate_history_rows():
    rows = parse_rate_history(FIXTURE)
    cit = [r for r in rows if r["bank_name"] == "CIT Bank"]
    assert cit[0] == {"bank_name": "CIT Bank", "rate_date": date(2026, 11, 3), "apy_pct": 3.75}
    assert len(rows) > 400
    assert {r["bank_name"] for r in rows} == {o["bank_name"] for o in parse_editorial_offers(FIXTURE)}
```

- [ ] **Step 2:** Run `python -m pytest -q pipelines/tests/test_parse_savings_offers.py` → FAIL (module missing).
- [ ] **Step 3:** Implement the four functions in `pipelines/parse_savings_offers.py` (line-based scanning; no new dependencies).
- [ ] **Step 4:** Run `python -m pytest -q pipelines/tests` → all PASS (existing 9 + new 3).
- [ ] **Step 5:** Commit `feat: parse Bankrate editorial picks, promos, and rate history`.

---

### Task 2: Load to DuckDB and model in dbt

**Files:**
- Modify: `pipelines/parse_savings_offers.py` (add `main()` loader)
- Modify: `.github/workflows/refresh-data.yml` (add `python pipelines/parse_savings_offers.py` after "Parse Bankrate")
- Modify: `dbt/models/staging/sources.yml` (add `bankrate_savings_offers`, `bankrate_rate_history`)
- Create: `dbt/models/staging/stg_savings_offers.sql`, `dbt/models/staging/stg_savings_rate_history.sql`
- Create: `dbt/models/mart/fct_savings_offers.sql`, `dbt/models/mart/fct_savings_rate_history.sql`
- Create: `dbt/seeds/bank_urls.csv` (`bank_name,url`)
- Modify: `dbt/seeds/big_four_rates.csv` (delete the 9 Marcus/Ally/SoFi rows)
- Modify: `dbt/models/mart/schema.yml`

**Interfaces:**
- Consumes: Task 1 functions.
- Produces (DuckDB, schema `MART`):
  - `fct_savings_offers`: `bank_name, apy_pct, promo_apy_pct, promo_months, promo_expires, min_opening, min_balance_for_apy, url, snapshot_date` — one row per editorial bank from the **latest** snapshot file.
  - `fct_savings_rate_history`: `bank_name, rate_date, apy_pct` — distinct rows unioned across all snapshot files.

Loader: `main()` reads every `knowledge/raw/bankrate_savings_*.md` that contains an editorial section; `raw.bankrate_savings_offers` gets the newest file's offers + promos (+ `snapshot_date` from filename); `raw.bankrate_rate_history` gets distinct history rows from all files. `CREATE OR REPLACE` both tables (full rebuild, like the other loaders).

`bank_urls.csv`: official homepage or savings-product URL for each of the 12 current editorial banks. Verify each with `curl -sIL -o /dev/null -w "%{http_code}"` returning 200 before committing; leave a bank out rather than guess. `fct_savings_offers.url` is a left join (null when unmapped).

- [ ] **Step 1:** Add dbt tests to `schema.yml`: `fct_savings_offers.bank_name` `not_null`+`unique`; `apy_pct` `not_null`; `min_balance_for_apy` `not_null`; `fct_savings_rate_history` `not_null` on all three columns.
- [ ] **Step 2:** Run `(cd dbt && dbt build --profiles-dir .)` → FAIL (models missing).
- [ ] **Step 3:** Implement loader `main()`, sources, staging and mart models, seeds.
- [ ] **Step 4:** Run `python pipelines/parse_savings_offers.py && (cd dbt && dbt build --profiles-dir .)` → all PASS; `SELECT count(*) FROM mart.fct_savings_offers` = 12; CIT row has `apy_pct=3.75, promo_apy_pct=4.35, promo_months=6`.
- [ ] **Step 5:** Commit `feat: savings offers and rate history models`.

---

### Task 3: Export `site/data/rates.json` with badges

**Files:**
- Create: `pipelines/export_site_data.py`
- Test: `pipelines/tests/test_export_site_data.py`

**Interfaces:**
- Consumes: `mart.fct_savings_offers`, `mart.fct_savings_rate_history`, `staging.stg_fred_observations`, seed `big_four_rates` (savings rows).
- Produces: `compute_badge(history: dict[str, list[tuple[date, float]]], bank: str, as_of: date) -> str | None` and `build_payload(conn) -> dict`; `main()` writes `site/data/rates.json`:

```json
{
  "as_of": "2026-11-05",
  "fed_funds": {"rate": 3.88, "as_of": "2026-10-01"},
  "treasury_1y": {"rate": 4.46, "as_of": "2026-10-01"},
  "banks": [{"name": "CIT Bank", "apy": 3.75,
             "promo": {"apy": 4.35, "months": 6, "expires": "2026-12-15"},
             "min_opening": 100, "min_balance_for_apy": 5000,
             "url": "https://…", "badge": "Steady rate for 12 weeks"}],
  "big_banks": [{"name": "JPMorgan Chase", "apy": 0.01, "as_of": "2026-04-26"}]
}
```
(`promo` and `url` and `badge` may be `null`; `treasury_1y` from FRED `GS1`; `banks` sorted by `apy` desc.)

Badge rules (first match wins; history dates are weekly):
1. Latest rate differs from the previous point and latest point is within 14 days of `as_of` → `"Rate up 0.10%"` / `"Rate cut 0.10%"` (2-dp absolute change).
2. Bank ranked top 3 by APY among banks with a point on that date, for ≥ 4 consecutive most-recent dates → `"Top 3 for N weeks"`.
3. Same APY for ≥ 8 consecutive most-recent points → `"Steady rate for N weeks"`.
4. Otherwise `None`. Fewer than 2 points → `None`.

- [ ] **Step 1: Write failing tests**

```python
D = lambda s: date.fromisoformat(s)
def test_rate_cut_badge():
    h = {"A": [(D("2026-10-27"), 4.10), (D("2026-11-03"), 4.00)]}
    assert compute_badge(h, "A", D("2026-11-05")) == "Rate cut 0.10%"
def test_top3_streak():
    dates = [D("2026-10-06"), D("2026-10-13"), D("2026-10-20"), D("2026-10-27"), D("2026-11-03")]
    h = {b: [(d, r) for d in dates] for b, r in [("A", 4.3), ("B", 4.2), ("C", 4.1), ("D", 3.0)]}
    assert compute_badge(h, "A", D("2026-11-05")) == "Top 3 for 5 weeks"
    assert compute_badge(h, "D", D("2026-11-05")) is None
def test_single_point_no_badge():
    assert compute_badge({"A": [(D("2026-11-03"), 4.0)]}, "A", D("2026-11-05")) is None
def test_payload_shape(tmp_duckdb_with_marts):   # fixture builds tiny marts in an in-memory DuckDB
    p = build_payload(tmp_duckdb_with_marts)
    assert set(p) == {"as_of", "fed_funds", "treasury_1y", "banks", "big_banks"}
    assert p["banks"][0]["apy"] >= p["banks"][-1]["apy"]
    assert all(b["name"] != "SoFi" for b in p["banks"])
```

- [ ] **Step 2:** Run `python -m pytest -q pipelines/tests/test_export_site_data.py` → FAIL.
- [ ] **Step 3:** Implement `compute_badge`, `build_payload`, `main()`.
- [ ] **Step 4:** Run tests → PASS; run `python pipelines/export_site_data.py` and confirm `site/data/rates.json` has 12 banks and 4 big banks.
- [ ] **Step 5:** Commit `feat: export rates.json for site with track-record badges`.

---

### Task 4: Money math module (`calc.js`)

**Files:**
- Create: `site/js/calc.js` (ES module, no DOM)
- Test: `site/tests/calc.test.mjs` (run with `node --test site/tests`)

**Interfaces:**
- Consumes: `rates.json` shape from Task 3.
- Produces (all exported):
  - `project({principal, monthly, apy, promo, years}) -> number[]` — month-end balances, length `years*12+1`, index 0 = principal. Monthly rate `(1+r/100)^(1/12)-1`; promo rate applies for `promo.months` months then `apy`. Contribution added at each month end after interest.
  - `rankBanks(banks, {principal, monthly, years}) -> {ranked: Bank[], fallback: boolean, neededFor: number|null}` — eligible = `principal >= max(min_opening, min_balance_for_apy)`; sort by final projected balance desc, ties by name. If none eligible: eligible = `principal >= min_opening`, `fallback=true`, `neededFor` = smallest `min_balance_for_apy` among the top 3 APY banks.
  - `fdicSplit(amount, ranked) -> {parts: {name, amount}[], uninsured: number}` — greedy, max `250000` each.
  - `treasuryEdge(topBank, treasury1y, principal) -> {rate, extra}|null` — top bank's effective 1-yr return from `project(...years:1)` with `monthly:0`; return when treasury rate beats it, `extra` = whole-dollar difference over 1 year.
  - `parseShareParams(search: string) -> {amount: number, monthly: number}|null` and `buildShareQuery({amount, monthly}) -> string`.
  - `rateLabel(bank) -> string` — `"4.35% for 6 months, then 3.75%"` or `"3.75%"`.

- [ ] **Step 1: Write failing tests** (key assertions; use `node:test` + `node:assert/strict`):
  - `project({principal:25000, monthly:0, apy:3.75, promo:null, years:10}).at(-1)` ≈ `25000*1.0375**10` within $1.
  - CIT (`principal:25000, apy:3.75, promo:{apy:4.35, months:6}`): 1-yr uplift over base-only ≈ $74.89 ± $1; 10-yr uplift ≈ $104.31 ± $1 (promo must not compound as if permanent; 10-yr end must be far below `25000*1.0435**10` = $38,270).
  - With `principal:25000, monthly:500, years:10, apy:4.0, promo:null` final ≈ $110,354.07 ± $1 and length is 121.
  - `rankBanks` at `principal:1000` excludes CIT (`min_balance_for_apy:5000`); at `principal:100` with all banks needing ≥ 250 → `fallback:true`, `neededFor` set, ranked non-empty.
  - `fdicSplit(5_000_000, 12 banks)` → 12 parts of 250000 and `uninsured: 2_000_000`; `fdicSplit(300000, …)` → `[250000, 50000]`.
  - `treasuryEdge(CIT, 4.46, 25000)` returns `{rate:4.46, extra}` with `extra > 0`; returns `null` when treasury 3.0.
  - `parseShareParams("?amount=abc")` → `null`; `"?amount=-5"` → `null`; `"?amount=25000&monthly=1e9"` → `{amount:25000, monthly:0}`; `"?amount=999999999999"` → amount clamped to `100000000`; `buildShareQuery({amount:25000, monthly:500})` → `"?amount=25000&monthly=500"`.
  - `rateLabel` both forms exactly as above.
- [ ] **Step 2:** Run `node --test site/tests` → FAIL.
- [ ] **Step 3:** Implement `site/js/calc.js`.
- [ ] **Step 4:** Run `node --test site/tests` → PASS.
- [ ] **Step 5:** Commit `feat: promo-aware projection and ranking math`.

---

### Task 5: The site (ask → loading → dashboard)

**Files:**
- Create: `site/index.html`, `site/css/style.css`, `site/js/app.js`
- Reference: `docs/superpowers/mockups/flow-v3.html` (port its markup, CSS and animation; replace hard-coded data with `rates.json` + `calc.js`)

**Interfaces:**
- Consumes: `site/data/rates.json` (Task 3), all `calc.js` exports (Task 4).

Behavior beyond the mockup:
- **Ask screen:** add under the amount: a segmented choice **"No monthly contributions"** (default, selected) | **"Add monthly"**; choosing "Add monthly" reveals a `$ ___ / month` input (default 500).
- **Loading:** step 1 shows `fed_funds.rate`; step 2 ticks through `banks` + `big_banks` names and ends with `"<N> banks"`; sub-label `"Bankrate · as of <Mon D>"`; step 3 counts up to the top pick's 10-yr balance.
- **Dashboard top bar:** amount pill + monthly pill (`$0/mo` allowed), "Rates as of <as_of>". Edits re-render and `history.replaceState` the share query; never replay the animation.
- **Answer:** `Put it in <Bank>`; meta line `rateLabel(bank) · $X to open · FDIC insured · earns $Y in year one`; badge chip; `Open account →` (new tab, `rel="noopener"`) only when `url` non-null.
- **Treasury line** under the answer when `treasuryEdge` non-null: *"Won't need it for a year? A 1-year Treasury pays 4.46%, about $28 more."*
- **Fallback note** when `rankBanks().fallback`: *"Most top rates need $5,000+ to earn their APY."*
- **Growth card:** end balance, `in N years · +$X earned` (earned = end − principal − monthly×months), "At Chase instead $Y" (same contributions), 1/5/10/20 toggles; ranking recomputes per horizon.
- **List:** next 4 ranked banks (name, `rateLabel`, per-year earnings, badge, Open account link), then JPMorgan Chase row in red.
- **FDIC note** when amount > 250000: parts from `fdicSplit`, plus `"$X would be over the insured limit"` when `uninsured > 0`.
- **Load failure:** if `fetch("data/rates.json")` fails, render the message from Review Focus #5.
- **Share URL on load:** valid `parseShareParams` → skip to dashboard; otherwise ask screen.

- [ ] **Step 1:** Port mockup into the three files; wire to data and `calc.js`.
- [ ] **Step 2:** Serve locally `python -m http.server -d site 8000` and check with the Playwright browser tool at 1280px and 375px: ask → loading → dashboard; `?amount=25000&monthly=500` opens dashboard directly; `?amount=100` shows fallback note; `?amount=5000000` shows FDIC split with uninsured remainder; renaming `site/data/rates.json` temporarily shows the unavailable message. No console errors.
- [ ] **Step 3:** Run `node --test site/tests` → PASS (unchanged).
- [ ] **Step 4:** Commit `feat: savings recommender site`.

---

### Task 6: Daily refresh, Pages deploy, retire Streamlit

**Files:**
- Modify: `pipelines/extract_bankrate.py` — skip writing a new snapshot when `parse_editorial_offers` + `parse_promos` of the new page equal those of the newest existing `bankrate_savings_*.md` (CD page: compare `extract_rates_from_markdown` output). Print `"No rate changes; snapshot not saved."`.
- Test: `pipelines/tests/test_extract_bankrate.py` — `should_save(new_md, previous_md) -> bool` false for identical fixture, true when one APY line is altered.
- Modify: `.github/workflows/refresh-data.yml` — cron `'0 12 * * *'`; replace "Export marts" with `python pipelines/export_site_data.py`; `git add knowledge/raw site/data`; add `node --test site/tests` step (setup-node not needed if runner node ≥ 20; else add `actions/setup-node@v4` with `node-version: 22`).
- Create: `.github/workflows/deploy-site.yml` — triggers: `push` to `main` with `paths: [site/**]`, `workflow_run` of "Refresh Data" `completed` (pushes made with `GITHUB_TOKEN` do not trigger `push` workflows), and `workflow_dispatch`; permissions `pages: write, id-token: write, contents: read`; steps `actions/checkout@v4`, `actions/configure-pages@v5`, `actions/upload-pages-artifact@v3` with `path: site`, `actions/deploy-pages@v4`.
- Enable Pages for workflow builds: `gh api -X POST repos/DanielDistor/deposit-pricing-analytics-banking/pages -f build_type=workflow`.
- Delete: `dashboard/`, `.github/workflows/keep-alive.yml`, `pipelines/export_marts.py`; remove streamlit/plotly from `requirements.txt`.
- Modify: `README.md` (live URL `https://danieldistor.github.io/deposit-pricing-analytics-banking/`, stack, pipeline diagram node `site/data/rates.json → GitHub Pages`, drop Streamlit dashboard tabs section, describe the product), `CLAUDE.md` (dashboard line → static site on Pages; daily refresh).

- [ ] **Step 1:** Write `test_extract_bankrate.py` → run → FAIL; implement `should_save`; run → PASS.
- [ ] **Step 2:** Make the workflow, deletion and doc changes; `python -m pytest -q pipelines/tests && node --test site/tests && (cd dbt && dbt build --profiles-dir .)` → all PASS.
- [ ] **Step 3:** Commit `feat: daily refresh, GitHub Pages deploy, retire Streamlit`; push; enable Pages; `gh workflow run refresh-data.yml`; confirm Refresh Data and Deploy Site both succeed (`gh run list`).
- [ ] **Step 4:** Open the live Pages URL with the Playwright browser tool; confirm the dashboard renders with today's `as_of`.
