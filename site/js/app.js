import {
  project, projectBank, rankBanks, fdicSplit, treasuryEdge, parseShareParams, buildShareQuery, rateLabel, showdown,
  FDIC_LIMIT, MAX_AMOUNT, MAX_MONTHLY,
} from "./calc.js";

const $ = (id) => document.getElementById(id);
const HORIZONS = [1, 5, 10, 20];
const COMPARISON = "JPMorgan Chase";

const state = { amount: 25000, monthly: 0, years: 10, data: null };

const money = (n) => "$" + Math.round(n).toLocaleString("en-US");
const digits = (s) => s.replace(/[^0-9]/g, "");
const num = (el) => Number(digits(el.value)) || 0;
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const fmtDate = (iso, opts = { month: "short", day: "numeric", year: "numeric" }) =>
  new Date(iso + "T00:00:00").toLocaleDateString("en-US", opts);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const show = (id) => document.querySelectorAll(".screen").forEach((s) => s.classList.toggle("on", s.id === id));

function formatInput(el, max) {
  const v = digits(el.value);
  el.value = v ? Math.min(Number(v), max).toLocaleString("en-US") : "";
}

const dataReady = fetch("data/rates.json", { cache: "no-cache" })
  .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
  .then((d) => { if (!d?.banks?.length) throw new Error("no banks"); state.data = d; return d; })
  .catch((e) => { console.warn("rates.json unavailable:", e.message); show("err"); return null; });

function comparisonBank(d) {
  return d.big_banks.find((b) => b.name === COMPARISON) || d.big_banks[0] || null;
}

// ---------- 1. ask ----------
dataReady.then((d) => {
  if (!d) return;
  const items = [...d.banks.slice(0, 6), ...d.big_banks].map((b) =>
    `<span class="${b.apy < 1 ? "bad" : ""}">${esc(b.name)} <b>${b.apy.toFixed(2)}%</b> <em>/ yr</em></span>`).join("");
  $("ticker").innerHTML = items + items; // doubled so the scroll loops seamlessly
});

const askInput = $("askInput"), askMonthly = $("askMonthly");
askInput.addEventListener("input", () => formatInput(askInput, MAX_AMOUNT));
askMonthly.addEventListener("input", () => formatInput(askMonthly, MAX_MONTHLY));
document.querySelectorAll(".seg-btn").forEach((btn) => btn.addEventListener("click", () => {
  const yes = btn.dataset.monthly === "yes";
  document.querySelectorAll(".seg-btn").forEach((b) => {
    const on = b === btn;
    b.classList.toggle("on", on);
    b.setAttribute("aria-checked", String(on));
  });
  $("monthlyWrap").hidden = !yes;
  if (yes) askMonthly.focus();
}));
$("askForm").addEventListener("submit", (e) => { e.preventDefault(); start(); });

async function start() {
  state.amount = Math.max(1, num(askInput) || 25000);
  state.monthly = $("monthlyWrap").hidden ? 0 : num(askMonthly);
  const d = await dataReady;
  if (!d) return;
  history.replaceState(null, "", buildShareQuery(state));
  await playLoading(d);
  await playShowdown(d);
  openDashboard();
}

// ---------- 2. loading ----------
async function playLoading(d) {
  show("load");
  const steps = [...document.querySelectorAll(".step")];
  const total = 3600, t0 = performance.now();
  const tick = () => {
    const p = Math.min(1, (performance.now() - t0) / total);
    $("prog").style.width = p * 100 + "%";
    if (p < 1) requestAnimationFrame(tick);
  };
  tick();

  steps[0].classList.add("active");
  $("s1").textContent = d.fed_funds ? `Federal Reserve · ${fmtDate(d.fed_funds.as_of, { month: "short", year: "numeric" })}` : "Federal Reserve";
  await wait(900);
  steps[0].className = "step done";
  $("r1").textContent = d.fed_funds ? d.fed_funds.rate.toFixed(2) + "%" : "—";

  steps[1].classList.add("active");
  const names = [...d.banks, ...d.big_banks].map((b) => b.name);
  const per = Math.max(40, Math.min(110, 1400 / names.length));
  for (const n of names) { $("s2").textContent = n; await wait(per); }
  $("s2").textContent = `Bankrate · as of ${fmtDate(d.as_of, { month: "short", day: "numeric" })}`;
  steps[1].className = "step done";
  $("r2").textContent = `${names.length} banks`;

  steps[2].classList.add("active");
  const top = rankBanks(d.banks, { principal: state.amount, monthly: state.monthly, years: 10 }).ranked[0];
  const target = projectBank(top, { principal: state.amount, monthly: state.monthly, years: 10 }).at(-1);
  const t1 = performance.now();
  while (performance.now() - t1 < 700) {
    const k = (performance.now() - t1) / 700;
    $("s3").textContent = money(state.amount + (target - state.amount) * k) + " in 10 years";
    await wait(30);
  }
  $("s3").textContent = money(target) + " in 10 years";
  steps[2].className = "step done";
  $("r3").textContent = "✓";
  await wait(450);
}

// ---------- 2b. showdown ----------
const MARK_X = '<path d="M8 8 L20 20 M20 8 L8 20"/>';
const MARK_OK = '<path d="M6 15 L12 21 L22 8"/>';

function elCard(b) {
  const el = document.createElement("div");
  el.className = "el-card";
  el.innerHTML = `<div class="n">${esc(b.name)}<small>${money(b.final)}</small></div>
    <div class="r mono">${b.apy.toFixed(2)}%</div><svg class="el-mark" viewBox="0 0 28 28" aria-hidden="true"></svg>`;
  $("elCards").appendChild(el);
  requestAnimationFrame(() => requestAnimationFrame(() => el.classList.add("in")));
  return el;
}

async function elRound(title, list) {
  if (!list.length) return;
  $("elHead").textContent = title;
  const els = [];
  for (const b of list) { els.push(elCard(b)); await wait(200); }
  await wait(450);
  for (const el of els) {
    el.querySelector(".el-mark").innerHTML = MARK_X;
    el.classList.add("x");
    await wait(300);
  }
  await wait(400);
  els.forEach((el) => el.classList.add("gone"));
  await wait(380);
  $("elCards").innerHTML = "";
}

async function playShowdown(d) {
  const years = 10;
  const s = showdown(d.banks, d.big_banks, { principal: state.amount, monthly: state.monthly, years });
  const withFinal = (b) => ({ ...b, final: b.final ?? projectBank(b, { principal: state.amount, monthly: state.monthly, years }).at(-1) });
  $("elCards").innerHTML = "";
  $("elColBank").textContent = `Bank · your money in ${years} yrs`;
  show("elim");
  await elRound("Checking the big banks", s.big);
  await elRound("Comparing the top online banks", s.rivals.map(withFinal));
  $("elHead").textContent = "Your best option";
  const w = elCard(withFinal(s.winner));
  await wait(450);
  w.querySelector(".el-mark").innerHTML = MARK_OK;
  w.classList.add("win");
  await wait(1100);
}

// ---------- 3. dashboard ----------
const dashInput = $("dashInput"), dashMonthly = $("dashMonthly");

function openDashboard() {
  dashInput.value = state.amount.toLocaleString("en-US");
  dashMonthly.value = state.monthly.toLocaleString("en-US");
  $("asOf").textContent = `Rates as of ${fmtDate(state.data.as_of)}`;
  render();
  show("dash");
  document.querySelector("#dash .col").classList.add("fade");
}

function onDashEdit() {
  formatInput(dashInput, MAX_AMOUNT);
  formatInput(dashMonthly, MAX_MONTHLY);
  const amount = num(dashInput);
  if (amount < 1) return; // keep the last result while the field is empty
  state.amount = amount;
  state.monthly = num(dashMonthly);
  history.replaceState(null, "", buildShareQuery(state));
  render();
}
dashInput.addEventListener("input", onDashEdit);
dashMonthly.addEventListener("input", onDashEdit);

const toOpen = (b) => {
  const open = b.min_opening ? `${money(b.min_opening)} to open` : "No minimum to open";
  const parts = [open];
  if (b.min_balance_for_apy > b.min_opening) parts.push(`${money(b.min_balance_for_apy)} for APY`);
  if (b.min_monthly_deposit > 0) parts.push(`needs ${money(b.min_monthly_deposit)}/mo deposits`);
  return parts.join(" · ");
};
const openLink = (b) => b.url
  ? `<a class="open" href="${esc(b.url)}" target="_blank" rel="noopener">Open account →</a>` : "";
const badge = (b) => (b.badge ? `<span class="badge">${esc(b.badge)}</span>` : "");

function firstYearEarned(b) {
  const { amount: principal, monthly } = state;
  return projectBank(b, { principal, monthly, years: 1 }).at(-1) - principal - monthly * 12;
}

function render() {
  const d = state.data;
  const { amount, monthly, years } = state;
  const { ranked, fallback, neededFor } = rankBanks(d.banks, { principal: amount, monthly, years });
  const top = ranked[0];
  const chase = comparisonBank(d);

  $("ansH").innerHTML = `Put it in <em>${esc(top.name)}</em>`;
  $("ansWhy").textContent =
    `${rateLabel(top)} APY · ${toOpen(top)} · FDIC insured · earns ${money(firstYearEarned(top))} in year one`;
  $("ansCta").innerHTML = badge(top) + openLink(top);

  const fb = $("fallback");
  fb.hidden = !(fallback && neededFor);
  if (!fb.hidden) fb.innerHTML = `Most top rates need <b>${money(neededFor)}+</b> to earn their APY.`;

  const edge = d.treasury_1y ? treasuryEdge(top, d.treasury_1y.rate, amount) : null;
  const tr = $("treasury");
  tr.hidden = !edge;
  if (edge) tr.innerHTML = `Won't need it for a year? A 1-year Treasury pays <b>${edge.rate.toFixed(2)}%</b>, about <b>${money(edge.extra)}</b> more.`;

  // growth card
  $("tabs").innerHTML = HORIZONS.map((y) =>
    `<button class="tab ${y === years ? "on" : ""}" data-y="${y}" aria-pressed="${y === years}">${y} yr</button>`).join("");
  $("tabs").querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => { state.years = Number(t.dataset.y); render(); }));

  const topSeries = projectBank(top, { principal: amount, monthly, years });
  const chaseSeries = chase ? project({ principal: amount, monthly, apy: chase.apy, promo: null, years }) : null;
  const end = topSeries.at(-1);
  const deposited = amount + monthly * years * 12;
  $("gBig").textContent = money(end);
  $("gCap").textContent = `in ${years} year${years > 1 ? "s" : ""} · +${money(end - deposited)} earned`;
  $("gVsLabel").textContent = chase ? `At ${chase.name.replace("JPMorgan ", "")} instead` : "";
  $("gVs").textContent = chaseSeries ? money(chaseSeries.at(-1)) : "";
  drawChart(topSeries, chaseSeries, years);

  // list
  const rows = ranked.slice(1, 5).map((b) => `
    <div class="row">
      <div class="n">${esc(b.name)}${badge(b)}<small>${esc(rateLabel(b))} APY · ${toOpen(b)}</small>${openLink(b)}</div>
      <div class="a mono">${b.apy.toFixed(2)}%</div>
      <div class="e mono">${money(firstYearEarned(b))}</div>
    </div>`);
  if (chase) rows.push(`
    <div class="row chase">
      <div class="n">${esc(chase.name)}<small>Typical big-bank savings · as of ${fmtDate(chase.as_of)}</small></div>
      <div class="a mono">${chase.apy.toFixed(2)}%</div>
      <div class="e mono">${money(firstYearEarned({ apy: chase.apy, promo: null }))}</div>
    </div>`);
  $("rows").innerHTML = rows.join("");

  // FDIC
  const note = $("note");
  note.hidden = amount <= FDIC_LIMIT;
  if (!note.hidden) {
    const { parts, uninsured } = fdicSplit(amount, ranked);
    const list = parts.map((p) => `<b>${money(p.amount)}</b> at ${esc(p.name)}`).join(", ");
    note.innerHTML = `<b>Tip:</b> the FDIC insures up to ${money(FDIC_LIMIT)} per bank. To keep your money protected, split it: ${list}.`
      + (uninsured > 0 ? ` <b>${money(uninsured)}</b> would be over the insured limit.` : "");
  }
}

function drawChart(top, chase, years) {
  const W = 680, H = 200, L = 4, R = 10, T = 10, B = 24;
  const all = chase ? top.concat(chase) : top;
  const yMin = Math.min(...all) * 0.995, yMax = Math.max(...all) * 1.01;
  const n = top.length - 1;
  const x = (i) => L + (W - L - R) * i / n;
  const y = (v) => T + (H - T - B) * (1 - (v - yMin) / ((yMax - yMin) || 1));
  const path = (s) => s.map((v, i) => (i ? "L" : "M") + x(i).toFixed(1) + "," + y(v).toFixed(1)).join("");
  const topPath = path(top);
  const ticks = [0, n / 2, n].map((i) => {
    const t = years * i / n;
    const label = i === 0 ? "Today" : `${Number.isInteger(t) ? t : t.toFixed(1)} yr`;
    const anchor = i === 0 ? "start" : i === n ? "end" : "middle";
    return `<text x="${x(i)}" y="${H - 4}" fill="#56625a" font-size="12" text-anchor="${anchor}" font-family="JetBrains Mono, monospace">${label}</text>`;
  }).join("");
  $("chart").innerHTML = `<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#22e07a" stop-opacity=".25"/><stop offset="1" stop-color="#22e07a" stop-opacity="0"/></linearGradient></defs>
    <path d="${topPath}L${x(n)},${H - B}L${x(0)},${H - B}Z" fill="url(#g)"/>
    ${chase ? `<path d="${path(chase)}" stroke="#e05252" stroke-width="2" stroke-dasharray="5 5" fill="none"/>` : ""}
    <path d="${topPath}" stroke="#22e07a" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="${x(n)}" cy="${y(top.at(-1))}" r="5" fill="#22e07a"/>${ticks}`;
}

// ---------- boot: a share link skips straight to the dashboard ----------
const shared = parseShareParams(location.search);
if (shared) {
  show(null); // stay black instead of flashing the ask screen
  state.amount = shared.amount;
  state.monthly = shared.monthly;
  dataReady.then((d) => { if (d) openDashboard(); });
}
