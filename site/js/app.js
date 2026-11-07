import {
  project, projectBank, rankBanks, fdicSplit, treasuryEdge, parseShareParams, buildShareQuery, rateLabel, leaderStats, planOptions,
  FDIC_LIMIT, MAX_AMOUNT, MAX_MONTHLY,
} from "./calc.js";

const $ = (id) => document.getElementById(id);
const HORIZONS = [1, 5, 10, 20];
const COMPARISON = "JPMorgan Chase";

const state = { amount: 25000, monthly: 0, need: 0, years: 10, data: null };

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
document.querySelectorAll(".need-btn").forEach((btn) => btn.addEventListener("click", () => {
  document.querySelectorAll(".need-btn").forEach((b) => {
    const on = b === btn;
    b.classList.toggle("on", on);
    b.setAttribute("aria-checked", String(on));
  });
}));
$("askForm").addEventListener("submit", (e) => { e.preventDefault(); start(); });

async function start() {
  state.amount = Math.max(1, num(askInput) || 25000);
  state.monthly = $("monthlyWrap").hidden ? 0 : num(askMonthly);
  state.need = Number(document.querySelector(".need-btn.on")?.dataset.need || 0);
  const d = await dataReady;
  if (!d) return;
  history.replaceState(null, "", buildShareQuery(state));
  await playLoading(d);
  openDashboard();
}

// ---------- 2. loading ----------
async function playLoading(d) {
  show("load");
  const steps = [...document.querySelectorAll(".step")];
  const total = 7000, t0 = performance.now(); // matches the step timings below
  const tick = () => {
    const p = Math.min(1, (performance.now() - t0) / total);
    $("prog").style.width = p * 100 + "%";
    if (p < 1) requestAnimationFrame(tick);
  };
  tick();

  steps[0].classList.add("active");
  $("s1").textContent = d.fed_funds ? `Federal Reserve · ${fmtDate(d.fed_funds.as_of, { month: "short", year: "numeric" })}` : "Federal Reserve";
  await wait(1700);
  steps[0].className = "step done";
  $("r1").textContent = d.fed_funds ? d.fed_funds.rate.toFixed(2) + "%" : "—";

  steps[1].classList.add("active");
  const names = [...d.banks, ...d.big_banks].map((b) => b.name);
  const per = Math.max(120, Math.min(220, 2800 / names.length));
  for (const n of names) { $("s2").textContent = n; await wait(per); }
  $("s2").textContent = `Bankrate · as of ${fmtDate(d.as_of, { month: "short", day: "numeric" })}`;
  steps[1].className = "step done";
  $("r2").textContent = `${names.length} banks`;

  steps[2].classList.add("active");
  const yrs = state.need ? state.need / 12 : 10;
  const target = state.need
    ? planOptions(d, { principal: state.amount, monthly: state.monthly, months: state.need }).top.final
    : projectBank(rankBanks(d.banks, { principal: state.amount, monthly: state.monthly, years: 10 }).ranked[0],
      { principal: state.amount, monthly: state.monthly, years: 10 }).at(-1);
  const inYrs = ` in ${yrs} year${yrs > 1 ? "s" : ""}`;
  const t1 = performance.now();
  while (performance.now() - t1 < 1600) {
    const k = (performance.now() - t1) / 1600;
    $("s3").textContent = money(state.amount + (target - state.amount) * k) + inYrs;
    await wait(30);
  }
  $("s3").textContent = money(target) + inYrs;
  steps[2].className = "step done";
  $("r3").textContent = "✓";
  await wait(900);
}

// ---------- 3. dashboard ----------
const dashInput = $("dashInput"), dashMonthly = $("dashMonthly"), dashNeed = $("dashNeed");

function openDashboard() {
  dashInput.value = state.amount.toLocaleString("en-US");
  dashMonthly.value = state.monthly.toLocaleString("en-US");
  dashNeed.value = String(state.need);
  $("asOf").textContent = `Rates as of ${fmtDate(state.data.as_of)}`;
  renderTrend(state.data);
  renderLeaders(state.data);
  renderBrief(state.data);
  renderHealth(state.data);
  state.animate = true;
  render();
  state.animate = false;
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
  state.need = Number(dashNeed.value) || 0;
  history.replaceState(null, "", buildShareQuery(state));
  render();
}
dashInput.addEventListener("input", onDashEdit);
dashNeed.addEventListener("change", onDashEdit);
let resizeTimer;
addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => { if (state.data && $("dash").classList.contains("on")) renderTrend(state.data); }, 150);
});

// Back to the question, keeping what they typed; drops the share query so a refresh starts fresh too.
$("restart").addEventListener("click", () => {
  history.replaceState(null, "", location.pathname);
  askInput.value = state.amount.toLocaleString("en-US");
  askMonthly.value = (state.monthly || 500).toLocaleString("en-US");
  document.querySelector(`.seg-btn[data-monthly="${state.monthly > 0 ? "yes" : "no"}"]`).click();
  document.querySelector(`.need-btn[data-need="${state.need}"]`)?.click();
  show("ask");
  window.scrollTo(0, 0);
  askInput.focus();
});
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

// ---------- plain-English answer ----------
const yrsText = (y) => `${y} year${y === 1 ? "" : "s"}`;
const whoseMoney = () => `Your <b>${money(state.amount)}</b>` + (state.monthly > 0 ? ` plus <b>${money(state.monthly)} a month</b>` : "");
const ratePhrase = (b) => b.promo
  ? `${b.promo.apy.toFixed(2)}% for ${b.promo.months} month${b.promo.months === 1 ? "" : "s"}, then ${b.apy.toFixed(2)}% a year`
  : `${b.apy.toFixed(2)}% a year`;

// ---------- options for a fixed timeline ----------
const NEED_LABEL = { 0: "anytime", 12: "in 1 year", 24: "in 2 years", 36: "in 3 years", 60: "in 5 years" };
const optName = (o) => (o.kind === "cd" ? `${o.name} CD` : o.name);
const KIND = { savings: "Savings", cd: "CD", treasury: "Treasury" };
const lockedUntil = (months) => {
  const dt = new Date(); dt.setMonth(dt.getMonth() + months);
  return dt.toLocaleDateString("en-US", { month: "short", year: "numeric" });
};
const optTrade = (o) => ({
  savings: "Rate can change anytime · withdraw anytime",
  cd: `Fixed rate · locked until ${lockedUntil(o.term_months)} · penalty to withdraw early`
    + (o.min_deposit ? ` · ${money(o.min_deposit)} minimum` : ""),
  treasury: "Fixed rate · backed by the U.S. government · no state income tax · can sell early at market price",
})[o.kind];
const optLink = (o) => {
  if (!o.url) return "";
  const label = o.kind === "treasury" ? "Buy at TreasuryDirect →" : o.kind === "cd" ? "See details →" : "Open account →";
  return `<a class="open" href="${esc(o.url)}" target="_blank" rel="noopener">${label}</a>`;
};

function answerForPlan(top, plan) {
  const yrs = top.term_months ? top.term_months / 12 : state.need / 12;
  const term = `${yrs}-year`;
  if (top.kind === "cd") {
    $("ansH").innerHTML = `Lock it in a <em>${term} CD</em> at ${esc(top.name)}`;
  } else if (top.kind === "treasury") {
    $("ansH").innerHTML = `Buy a <em>${term} Treasury</em>`;
  } else {
    $("ansH").innerHTML = `Put it in <em>${esc(top.name)}</em>`;
  }
  const lump = `Your <b>${money(state.amount)}</b>`;
  const ending = top.monthlyTo
    ? `With your ${money(state.monthly)} a month going in ${esc(top.monthlyTo)} savings next to it, you'll have <b>${money(top.final)}</b> in ${yrsText(yrs)}`
    : `You'll have <b>${money(top.final)}</b> in ${yrsText(yrs)}`;
  if (top.kind === "cd") {
    $("ansWhy").innerHTML = `${lump} should go in a ${term} CD at ${esc(top.name)}. It's locked in at ${top.apy.toFixed(2)}% a year. ${ending}`;
    $("ansMeta").textContent = [top.min_deposit ? `${money(top.min_deposit)} minimum` : "No minimum",
      /credit union/i.test(top.name) ? "NCUA insured" : "FDIC insured", `locked until ${lockedUntil(top.term_months)}, penalty if you pull it out early`].join(" · ");
  } else if (top.kind === "treasury") {
    $("ansWhy").innerHTML = `${lump} should go in a ${term} Treasury. It pays about ${top.apy.toFixed(2)}% a year, locked in. ${ending}`;
    $("ansMeta").textContent = "Backed by the U.S. government · no state income tax · you can sell early at market price";
  } else {
    $("ansWhy").innerHTML = `${whoseMoney()} should go in ${esc(top.name)}. It pays ${ratePhrase(top.bank)}, so you'll have <b>${money(top.final)}</b> in ${yrsText(yrs)}`;
    $("ansMeta").textContent = `${toOpen(top.bank)} · FDIC insured · the rate can change anytime`;
  }
  $("ansCta").innerHTML = (top.kind === "savings" ? badge(top.bank) : "") + optLink(top);
  $("fallback").hidden = true;

  // why not savings: the trade-off in one line
  const bestSavings = plan.options.find((o) => o.kind === "savings");
  const tr = $("treasury");
  tr.hidden = top.kind === "savings" || !bestSavings;
  if (!tr.hidden) tr.innerHTML = `That's <b>${money(top.final - bestSavings.final)}</b> more than ${esc(bestSavings.name)} savings, and savings rates can drop while this one can't`;
}

function render() {
  const d = state.data;
  const { amount, monthly, need } = state;
  const years = need ? need / 12 : state.years;
  const chase = comparisonBank(d);
  let top, topSeries, listRows, fdicPool, display;

  if (need) {
    const plan = planOptions(d, { principal: amount, monthly, months: need });
    top = plan.top;
    topSeries = top.series;
    display = { name: optName(top), apy: top.apy };
    answerForPlan(top, plan);
    $("listHead").textContent = `Your options for money you need ${NEED_LABEL[need]}`;
    listRows = plan.options.slice(1, 7).map((o) => `
      <div class="row">
        <div class="n">${esc(optName(o))}<span class="kind">${KIND[o.kind]}</span><small>${esc(optTrade(o))}</small>${optLink(o)}</div>
        <div class="a mono">${o.apy.toFixed(2)}%</div>
        <div class="e mono">${money(o.final)}</div>
      </div>`);
    fdicPool = top.kind === "treasury" ? null : plan.options.filter((o) => o.kind === top.kind);
  } else {
    const { ranked, fallback, neededFor } = rankBanks(d.banks, { principal: amount, monthly, years });
    const bank = ranked[0];
    top = bank;
    topSeries = projectBank(bank, { principal: amount, monthly, years });
    display = { name: bank.name, apy: bank.apy };
    $("ansH").innerHTML = `Put it in <em>${esc(bank.name)}</em>`;
    $("ansWhy").innerHTML = `${whoseMoney()} should go in ${esc(bank.name)}. It pays ${ratePhrase(bank)}, so you'll have <b>${money(topSeries.at(-1))}</b> in ${yrsText(years)}`;
    $("ansMeta").textContent = `${toOpen(bank)} · FDIC insured · ${money(firstYearEarned(bank))} in interest the first year`;
    $("ansCta").innerHTML = badge(bank) + openLink(bank);
    const fb = $("fallback");
    fb.hidden = !(fallback && neededFor);
    if (!fb.hidden) fb.innerHTML = `Most top rates need <b>${money(neededFor)}+</b> to earn their full rate`;
    const edge = d.treasury_1y ? treasuryEdge(bank, d.treasury_1y.rate, amount) : null;
    const tr = $("treasury");
    tr.hidden = !edge;
    if (edge) tr.innerHTML = `Won't touch it for a year? A 1-year Treasury pays <b>${edge.rate.toFixed(2)}%</b>, about <b>${money(edge.extra)}</b> more`;
    $("listHead").textContent = "Other great options · first year";
    listRows = ranked.slice(1, 5).map((b) => `
      <div class="row">
        <div class="n">${esc(b.name)}${badge(b)}<small>${esc(rateLabel(b))} APY · ${toOpen(b)}</small>${openLink(b)}</div>
        <div class="a mono">${b.apy.toFixed(2)}%</div>
        <div class="e mono">${money(firstYearEarned(b))}</div>
      </div>`);
    fdicPool = ranked;
  }

  // growth card (a fixed timeline sets the horizon, so the tabs hide)
  $("tabs").hidden = Boolean(need);
  $("tabs").innerHTML = HORIZONS.map((y) =>
    `<button class="tab ${y === years ? "on" : ""}" data-y="${y}" aria-pressed="${y === years}">${y} yr</button>`).join("");
  $("tabs").querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => { state.years = Number(t.dataset.y); render(); }));

  const chaseSeries = chase ? project({ principal: amount, monthly, apy: chase.apy, promo: null, years }) : null;
  const end = topSeries.at(-1);
  const deposited = amount + monthly * years * 12;
  $("gBig").textContent = money(end);
  $("gCap").textContent = `in ${years} year${years > 1 ? "s" : ""} · +${money(end - deposited)} earned`;
  $("gVsLabel").textContent = chase ? `At ${chase.name.replace("JPMorgan ", "")} instead` : "";
  $("gVs").textContent = chaseSeries ? money(chaseSeries.at(-1)) : "";
  drawChart(topSeries, chaseSeries, years);
  $("gLegend").innerHTML = `<span><i style="border-color:#22e07a"></i>${esc(display.name)}</span>`
    + (chase ? `<span><i style="border-color:#e05252"></i>${esc(chase.name)}</span>` : "");
  attachTip($("chart"), $("gTip"), topSeries.length - 1, (i) => {
    const m = years * 12 * i / (topSeries.length - 1);
    const label = m === 0 ? "Today" : m < 12 ? `Month ${Math.round(m)}` : `Year ${(m / 12).toFixed(m % 12 ? 1 : 0)}`;
    return tipHtml(label, [["#22e07a", display.name, money(topSeries[i])], ...(chase ? [["#e05252", chase.name, money(chaseSeries[i])]] : [])]);
  });

  renderTiles(display, chase, topSeries, chaseSeries, years);
  renderBigBars(display, d, end, years);

  if (chase) listRows.push(`
    <div class="row chase">
      <div class="n">${esc(chase.name)}<small>Typical big-bank savings · as of ${fmtDate(chase.as_of)}</small></div>
      <div class="a mono">${chase.apy.toFixed(2)}%</div>
      <div class="e mono">${money(need ? chaseSeries.at(-1) : firstYearEarned({ apy: chase.apy, promo: null }))}</div>
    </div>`);
  $("rows").innerHTML = listRows.join("");

  // FDIC
  const note = $("note");
  note.hidden = amount <= FDIC_LIMIT;
  if (!note.hidden && !fdicPool) {
    note.innerHTML = `<b>Good to know:</b> Treasuries are backed by the U.S. government, so the ${money(FDIC_LIMIT)} FDIC limit doesn't apply.`;
  } else if (!note.hidden) {
    const { parts, uninsured } = fdicSplit(amount, fdicPool.map((o) => ({ name: need ? optName(o) : o.name })));
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
    ${chase ? `<path d="${path(chase)}" stroke="#e05252" stroke-width="2" fill="none" stroke-linecap="round"/>` : ""}
    <path class="${state.animate ? "draw" : ""}" pathLength="1" d="${topPath}" stroke="#22e07a" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="${x(n)}" cy="${y(top.at(-1))}" r="5" fill="#22e07a"/>${ticks}`;
}

// ---------- dashboard extras ----------
const SVGNS = "http://www.w3.org/2000/svg";

function tipHtml(label, rows) {
  return `<div class="d">${esc(label)}</div>` + rows.map(([c, name, v]) =>
    `<div class="row2"><i style="border-color:${c}"></i><b>${esc(v)}</b><span>${esc(name)}</span></div>`).join("");
}

/** Crosshair + tooltip that snaps to the nearest of n+1 evenly spaced points. */
function attachTip(svg, tip, n, html, { L = 4, R = 10, T = 10 } = {}) {
  const vb = svg.viewBox.baseVal;
  let hair = svg.querySelector(".hair");
  if (!hair) {
    hair = document.createElementNS(SVGNS, "line");
    hair.setAttribute("class", "hair");
    hair.setAttribute("stroke", "#56625a");
    hair.setAttribute("stroke-width", "1");
    hair.setAttribute("visibility", "hidden");
  }
  hair.setAttribute("y1", T); hair.setAttribute("y2", vb.height - 24);
  svg.appendChild(hair);
  svg.onpointermove = (e) => {
    const r = svg.getBoundingClientRect();
    const fx = ((e.clientX - r.left) / r.width) * vb.width;
    const i = Math.max(0, Math.min(n, Math.round(((fx - L) / (vb.width - L - R)) * n)));
    const x = L + (vb.width - L - R) * i / n;
    hair.setAttribute("x1", x); hair.setAttribute("x2", x); hair.setAttribute("visibility", "visible");
    tip.innerHTML = html(i);
    tip.hidden = false;
    const px = (x / vb.width) * r.width;
    const w = tip.offsetWidth;
    tip.style.left = Math.max(0, Math.min(r.width - w, px + (px > r.width / 2 ? -w - 12 : 12))) + "px";
  };
  svg.onpointerleave = () => { tip.hidden = true; hair.setAttribute("visibility", "hidden"); };
}

function countUp(el, to, fmt) {
  if (!state.animate || matchMedia("(prefers-reduced-motion: reduce)").matches) { el.textContent = fmt(to); return; }
  const t0 = performance.now(), dur = 900;
  const step = () => {
    const k = Math.min(1, (performance.now() - t0) / dur);
    el.textContent = fmt(to * (1 - (1 - k) ** 3));
    if (k < 1) requestAnimationFrame(step);
  };
  step();
}

const cents = (n) => n < 10 ? "$" + n.toFixed(2) : money(n);

function renderTiles(top, chase, topSeries, chaseSeries, years) {
  const { amount } = state;
  const firstMonth = amount * ((1 + top.apy / 100) ** (1 / 12) - 1);
  const gap = chaseSeries ? topSeries.at(-1) - chaseSeries.at(-1) : null;
  const fed = state.data.fed_funds;
  const tiles = [
    { k: `In ${years} year${years > 1 ? "s" : ""}`, v: topSeries.at(-1), f: money, cls: "up", s: `at ${top.name}` },
    gap != null && { k: "More than Chase", v: gap, f: (n) => "+" + money(n), cls: "up", s: `over ${years} year${years > 1 ? "s" : ""}` },
    { k: "Interest, first month", v: firstMonth, f: money, s: chase ? `vs ${cents(amount * ((1 + chase.apy / 100) ** (1 / 12) - 1))} at Chase` : "" },
    fed && { k: "Fed funds rate", v: fed.rate, f: (n) => n.toFixed(2) + "%", s: `${fmtDate(fed.as_of, { month: "short", year: "numeric" })} · sets savings rates` },
  ].filter(Boolean);
  $("tiles").innerHTML = tiles.map((t, i) =>
    `<div class="tile"><div class="k">${esc(t.k)}</div><div class="v ${t.cls || ""}" id="tv${i}"></div><div class="s">${esc(t.s)}</div></div>`).join("");
  tiles.forEach((t, i) => countUp($("tv" + i), t.v, t.f));
}

function hbars(el, rows, max) {
  el.innerHTML = rows.map((r) => `
    <div class="hb ${r.hi ? "hi" : ""}" title="${esc(r.name)}: ${esc(r.label)}">
      <div class="n">${esc(r.name)}</div>
      <div class="track"><div class="fill" data-w="${(100 * r.value / max).toFixed(2)}"></div></div>
      <div class="v">${esc(r.label)}${r.sub ? `<small>${esc(r.sub)}</small>` : ""}</div>
    </div>`).join("");
  requestAnimationFrame(() => requestAnimationFrame(() =>
    el.querySelectorAll(".fill").forEach((f) => { f.style.width = f.dataset.w + "%"; })));
}

function renderBigBars(top, d, topFinal, years) {
  const { amount, monthly } = state;
  const rows = [{ name: top.name, value: topFinal, label: money(topFinal), sub: `${top.apy.toFixed(2)}% / yr`, hi: true }];
  for (const b of d.big_banks) {
    const v = project({ principal: amount, monthly, apy: b.apy, promo: null, years }).at(-1);
    rows.push({ name: b.name.replace("JPMorgan ", ""), value: v, label: money(v), sub: `−${money(topFinal - v)}` });
  }
  hbars($("bigBars"), rows, Math.max(...rows.map((r) => r.value)));
  const deposited = amount + monthly * years * 12;
  $("bbSub").innerHTML = `What ${money(amount)}${monthly ? ` + ${money(monthly)}/mo` : ""} becomes in ${years} year${years > 1 ? "s" : ""}. `
    + `You put in <b>${money(deposited)}</b>; the big banks pay almost nothing on top.`;
}

function renderTrend(d) {
  const t = d.trend;
  const card = $("trend").closest(".card");
  if (!t?.leaders?.length) { card.hidden = true; return; }
  card.hidden = false;
  const L = t.leaders;
  const fedAt = (iso) => { let r = null; for (const f of t.fed_funds) if (f.date <= iso) r = f.rate; return r ?? t.fed_funds[0]?.rate ?? null; };
  const fed = L.map((l) => fedAt(l.week));
  // draw at roughly the on-screen width so labels stay readable on phones and wide screens
  const W = Math.round(Math.min(1100, Math.max(320, innerWidth - 120))), H = 240, Lm = 48, R = 10, T = 10, B = 24;
  $("trend").setAttribute("viewBox", `0 0 ${W} ${H}`);
  const weekOf = (iso) => { const dt = new Date(iso + "T00:00:00"); dt.setDate(dt.getDate() - ((dt.getDay() + 6) % 7)); return dt.toISOString().slice(0, 10); };
  const flags = (t.flags || []).map((f) => ({ ...f, i: L.findIndex((l) => l.week === weekOf(f.date)) })).filter((f) => f.i >= 0);
  const vals = L.map((l) => l.apy).concat(fed.filter((v) => v != null), flags.map((f) => f.apy));
  const yMin = Math.floor((Math.min(...vals) - 0.15) * 10) / 10, yMax = Math.ceil((Math.max(...vals) + 0.1) * 10) / 10;
  const n = L.length - 1;
  const x = (i) => Lm + (W - Lm - R) * i / n;
  const y = (v) => T + (H - T - B) * (1 - (v - yMin) / (yMax - yMin));
  const line = (arr) => arr.map((v, i) => (i ? "L" : "M") + x(i).toFixed(1) + "," + y(v).toFixed(1)).join("");
  const step = (arr) => arr.map((v, i) => i ? `L${x(i).toFixed(1)},${y(arr[i - 1]).toFixed(1)}L${x(i).toFixed(1)},${y(v).toFixed(1)}` : `M${x(0)},${y(v).toFixed(1)}`).join("");
  const grid = [];
  for (let g = Math.ceil(yMin * 4) / 4; g <= yMax; g += 0.25)
    grid.push(`<line x1="${Lm}" x2="${W - R}" y1="${y(g)}" y2="${y(g)}" stroke="#1a211c"/><text x="0" y="${y(g) + 4}" fill="#56625a" font-size="11" text-anchor="start" font-family="JetBrains Mono, monospace">${g.toFixed(2)}%</text>`);
  const mon = (iso) => fmtDate(iso, { month: "short", year: "2-digit" });
  const ticks = [0, Math.round(n / 2), n].map((i) =>
    `<text x="${x(i)}" y="${H - 4}" fill="#56625a" font-size="12" text-anchor="${i === 0 ? "start" : i === n ? "end" : "middle"}" font-family="JetBrains Mono, monospace">${mon(L[i].week)}</text>`).join("");
  $("trend").innerHTML = grid.join("")
    + `<path d="${step(fed)}" stroke="#9aa7a0" stroke-width="2" fill="none"/>`
    + `<path d="${line(L.map((l) => l.apy))}" stroke="#22e07a" stroke-width="2.5" fill="none" stroke-linejoin="round"/>`
    + `<circle cx="${x(n)}" cy="${y(L[n].apy)}" r="4" fill="#22e07a"/>`
    + flags.map((f) => `<circle cx="${x(f.i)}" cy="${y(f.apy)}" r="5" fill="none" stroke="#f0b429" stroke-width="2"/>`
      + `<text x="${x(f.i) + 9}" y="${y(f.apy) + 4}" fill="#f0b429" font-size="11" font-family="Inter, sans-serif">! flagged</text>`).join("")
    + ticks;
  $("trLegend").innerHTML = `<span><i style="border-color:#22e07a"></i>Best online savings rate</span><span><i style="border-color:#9aa7a0"></i>Fed funds rate</span>`
    + (flags.length ? `<span style="color:#f0b429">○ Flagged data point (left out)</span>` : "");
  attachTip($("trend"), $("trTip"), n, (i) => tipHtml(`Week of ${fmtDate(L[i].week)}`,
    [["#22e07a", L[i].name, L[i].apy.toFixed(2) + "%"], ["#9aa7a0", "Fed funds rate", fed[i] == null ? "—" : fed[i].toFixed(2) + "%"],
      ...flags.filter((f) => f.i === i).map((f) => ["#f0b429", `${f.bank} · flagged, left out`, f.apy.toFixed(2) + "%"])]), { L: Lm, R, T });
  const chase = comparisonBank(d);
  const spread = L[n].apy - (fed[n] ?? 0);
  $("trSub").innerHTML = `The best online banks move with the Fed and pay <b>${spread >= 0 ? "above" : "below"}</b> it today (${L[n].apy.toFixed(2)}% vs ${(fed[n] ?? 0).toFixed(2)}%).`
    + (chase ? ` ${esc(chase.name.replace("JPMorgan ", ""))} pays <b>${chase.apy.toFixed(2)}%</b>.` : "");
}

function renderLeaders(d) {
  const t = d.trend;
  const card = $("leaderBars").closest(".card");
  if (!t?.leaders?.length) { card.hidden = true; return; }
  const st = leaderStats(t.leaders);
  card.hidden = false;
  hbars($("leaderBars"), st.weeks.map((w) => ({
    name: w.name, value: w.weeks, label: `${w.weeks} wk${w.weeks === 1 ? "" : "s"}`, hi: w.name === st.current,
  })), Math.max(...st.weeks.map((w) => w.weeks)));
  $("ldSub").innerHTML = `The top spot changed hands <b>${st.changes} times</b> in ${t.leaders.length} weeks. `
    + `That's why we re-check every day. Current #1: <b>${esc(st.current)}</b>.`;
}

function renderBrief(d) {
  const log = d.brief || [];
  $("briefCard").hidden = !log.length;
  if (!log.length) return;
  const [today, ...older] = log;
  $("briefDate").textContent = fmtDate(today.date, { month: "short", day: "numeric" });
  $("briefHead").textContent = today.headline;
  $("briefItems").innerHTML = today.items.map((t) => `<li>${esc(t)}</li>`).join("");
  $("briefMore").hidden = !older.length;
  $("briefOld").innerHTML = older.map((e) =>
    `<li><b>${esc(fmtDate(e.date, { month: "short", day: "numeric" }))}</b>${esc(e.headline)}${e.items.length ? " " + esc(e.items.join(" ")) : ""}</li>`).join("");
}

function renderHealth(d) {
  const h = d.health;
  $("healthCard").hidden = !h?.checks?.length;
  if (!h?.checks?.length) return;
  const bad = h.checks.filter((c) => !c.ok);
  const st = $("healthStatus");
  st.className = "status " + (bad.length ? "warn" : "good");
  st.textContent = bad.length ? `! ${bad.length} check${bad.length > 1 ? "s" : ""} need${bad.length > 1 ? "" : "s"} attention` : "✓ All checks passing";
  const ran = new Date(h.generated_at);
  $("healthSub").innerHTML = `The pipeline checks its own data every day before publishing. Last run <b>${esc(ran.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }))}</b> · ${h.history_weeks} weeks of rate history.`;
  $("healthChecks").innerHTML = h.checks.map((c) =>
    `<li class="${c.ok ? "ok" : "bad"}"><span class="ic" aria-label="${c.ok ? "passing" : "needs attention"}">${c.ok ? "✓" : "!"}</span><div>${esc(c.name)}<small>${esc(c.detail)}</small></div></li>`).join("");
  const flags = d.trend?.flags || [];
  $("healthFlags").innerHTML = flags.map((f) =>
    `<div class="flag"><b>! Flagged:</b> ${esc(f.bank)} at ${f.apy.toFixed(2)}% on ${esc(fmtDate(f.date))}. ${esc(f.reason)} (${f.before.toFixed(2)}% → ${f.apy.toFixed(2)}% → ${f.after.toFixed(2)}%). Likely a data error, so it's left out of rankings and badges.</div>`).join("");
}

// ---------- boot: a share link skips straight to the dashboard ----------
const shared = parseShareParams(location.search);
if (shared) {
  show(null); // stay black instead of flashing the ask screen
  state.amount = shared.amount;
  state.monthly = shared.monthly;
  state.need = shared.need;
  dataReady.then((d) => { if (d) openDashboard(); });
}
