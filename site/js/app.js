import {
  project, projectBank, rankBanks, fdicSplit, parseShareParams, buildShareQuery, leaderStats, planOptions,
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
  show("dash"); // charts measure their panel, so the screen must be visible first
  renderLeaders(state.data);
  renderBrief(state.data);
  renderHealth(state.data);
  render();
  document.querySelector("#dash .wrap").classList.add("fade");
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
dashMonthly.addEventListener("input", onDashEdit);
dashNeed.addEventListener("change", onDashEdit);

let resizeTimer;
addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => { if (state.data && $("dash").classList.contains("on")) render(); }, 150);
});

$("allBtn").addEventListener("click", () => { state.showAll = !state.showAll; renderAllToggle(); });

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

// ---------- formatting ----------
const pct = (n) => n.toFixed(2) + "%";
const signed = (n) => (Math.round(n) >= 0 ? "+" : "−") + money(Math.abs(n));
const yrsText = (y) => `${y} year${y === 1 ? "" : "s"}`;
const lockedUntil = (months) => {
  const dt = new Date(); dt.setMonth(dt.getMonth() + months);
  return dt.toLocaleDateString("en-US", { month: "short", year: "numeric" });
};
const PRODUCT = { savings: "Savings", cd: "CD", treasury: "Treasury" };
const insurer = (o) => o.kind === "treasury" ? "Backed by the U.S. government"
  : /credit union/i.test(o.name) ? "NCUA insured" : "FDIC insured";

/** Every option for the current inputs, ranked, in one shape. */
function buildOptions(d) {
  const { amount, monthly, need } = state;
  const years = need ? need / 12 : state.years;
  if (need) {
    const { options } = planOptions(d, { principal: amount, monthly, months: need });
    return { years, fallback: null, rows: options.map((o) => ({
      kind: o.kind, name: o.name, apy: o.apy, promo: o.bank?.promo || null,
      min: o.kind === "savings" ? Math.max(o.bank.min_opening || 0, o.bank.min_balance_for_apy || 0) : (o.min_deposit || 0),
      liq: o.kind === "savings" ? "Anytime" : `Locked to ${lockedUntil(need)}`,
      final: o.final, series: o.series, monthlyTo: o.monthlyTo,
    })) };
  }
  const { ranked, fallback, neededFor } = rankBanks(d.banks, { principal: amount, monthly, years });
  return { years, fallback: fallback ? neededFor : null, rows: ranked.map((b) => {
    const series = projectBank(b, { principal: amount, monthly, years });
    return { kind: "savings", name: b.name, apy: b.apy, promo: b.promo,
      min: Math.max(b.min_opening || 0, b.min_balance_for_apy || 0), minMonthly: b.min_monthly_deposit || 0,
      liq: "Anytime", final: series.at(-1), series };
  }) };
}

function render() {
  const d = state.data;
  const { amount, monthly, need } = state;
  const { years, rows, fallback } = buildOptions(d);
  const top = rows[0];
  const chase = comparisonBank(d);
  const chaseSeries = chase ? project({ principal: amount, monthly, apy: chase.apy, promo: null, years }) : null;
  const chaseFinal = chaseSeries ? chaseSeries.at(-1) : null;
  const deposited = amount + monthly * years * 12;
  const fed = d.fed_funds?.rate;

  // #1
  $("pickKind").textContent = `${PRODUCT[top.kind]} · ${top.liq}`;
  $("pickName").textContent = top.kind === "cd" ? `${top.name} · ${need / 12}-year CD` : top.name;
  const stats = [
    ["APY", pct(top.apy), "", top.promo ? `${pct(top.promo.apy)} for ${top.promo.months} mo first` : fed != null ? `${Math.round((top.apy - fed) * 100)} bps over Fed funds` : ""],
    [`Value in ${years} yrs`, money(top.final), "g", `${money(deposited)} deposited`],
    ["Interest earned", money(top.final - deposited), "", `over ${yrsText(years)}`],
    chase && ["vs Chase", signed(top.final - chaseFinal), "g", `Chase pays ${pct(chase.apy)}`],
  ].filter(Boolean);
  $("pickStats").innerHTML = stats.map(([k, v, cls, sub]) =>
    `<div><div class="k">${k}</div><div class="v ${cls}">${v}</div><div class="s">${esc(sub)}</div></div>`).join("");
  const foot = [`${top.min ? money(top.min) + " minimum" : "No minimum"} · ${insurer(top)}`
    + (top.minMonthly ? ` · needs ${money(top.minMonthly)}/mo deposits` : "")];
  if (top.monthlyTo) foot.push(`Your <b>${money(monthly)}/mo</b> goes to <b>${esc(top.monthlyTo)}</b> savings next to it, included above`);
  if (fallback) foot.push(`Most top rates need <b>${money(fallback)}+</b> to earn their full rate`);
  if (amount > FDIC_LIMIT && top.kind !== "treasury") {
    const pool = rows.filter((r) => r.kind === top.kind);
    const { parts, uninsured } = fdicSplit(amount, pool.map((r) => ({ name: r.name })));
    foot.push(`Over the ${money(FDIC_LIMIT)} insurance limit, split it: ${parts.map((x) => `<b>${money(x.amount)}</b> ${esc(x.name)}`).join(", ")}`
      + (uninsured > 0 ? `, <b>${money(uninsured)}</b> uninsured` : ""));
  }
  $("pickFoot").innerHTML = foot.map((f) => `<div>${f}</div>`).join("");

  // #2-#4 and the full list
  $("runHead").textContent = `value in ${years} yrs`;
  $("runRows").innerHTML = rows.slice(1, 4).map((r, k) => `<tr>
    <td class="num dim">${k + 2}</td><td class="inst">${esc(r.name)}</td><td class="dim c-prod">${PRODUCT[r.kind]}</td>
    <td class="num">${pct(r.apy)}</td><td class="num">${money(r.final)}</td><td class="num dim">${signed(r.final - top.final)}</td></tr>`).join("")
    || `<tr><td colspan="6" class="dim">No other options for this amount</td></tr>`;
  const refs = d.big_banks.map((b) => ({ name: b.name, apy: b.apy,
    final: project({ principal: amount, monthly, apy: b.apy, promo: null, years }).at(-1) }));
  $("allHead").textContent = `All options · value in ${years} yrs`;
  $("allRows").innerHTML = rows.map((r, k) => `<tr class="${k === 0 ? "hi" : ""}">
    <td class="num dim">${k + 1}</td><td class="inst">${esc(r.name)}</td><td class="dim c-prod">${PRODUCT[r.kind]}</td>
    <td class="num">${pct(r.apy)}</td><td class="num dim c-min">${r.min ? money(r.min) : "—"}</td><td class="dim c-liq">${esc(r.liq)}</td>
    <td class="num">${money(r.final)}</td><td class="num dim c-gap">${k === 0 ? "—" : signed(r.final - top.final)}</td></tr>`).join("")
    + `<tr class="sep"><td colspan="8"></td></tr>`
    + refs.map((r) => `<tr class="ref"><td></td><td class="inst">${esc(r.name)}</td><td class="c-prod">Savings</td>
      <td class="num">${pct(r.apy)}</td><td class="num c-min">—</td><td class="c-liq">Anytime</td>
      <td class="num">${money(r.final)}</td><td class="num gap c-gap">${signed(r.final - top.final)}</td></tr>`).join("");
  state.optionCount = rows.length;
  renderAllToggle();

  // growth
  const topLabel = top.kind === "cd" ? `${top.name} CD` : top.name;
  $("gTitle").textContent = `Growth · ${topLabel} vs Chase`;
  $("gGap").innerHTML = chase ? `gap in ${years} yrs <b>${signed(top.final - chaseFinal)}</b>` : "";
  $("gLegend").innerHTML = `<span><i style="border-color:#22e07a"></i>${esc(topLabel)}</span>`
    + (chase ? `<span><i style="border-color:#e05252"></i>${esc(chase.name)}</span>` : "");
  const n = top.series.length - 1;
  const xLabel = (i) => { const m = years * 12 * i / n; return m === 0 ? "Today" : `${+(m / 12).toFixed(1)} yr`; };
  const g = drawLines($("chart"), {
    series: [...(chaseSeries ? [{ values: chaseSeries, color: "#e05252", width: 1.6 }] : []), { values: top.series, color: "#22e07a", width: 2.4, fill: true }],
    yFmt: (v) => v >= 1e6 ? "$" + +(v / 1e6).toFixed(2) + "M" : "$" + +(v / 1000).toFixed(1) + "k",
    xTicks: [[0, "Today"], [n / 2, xLabel(n / 2)], [n, xLabel(n)]],
  });
  attachTip($("chart"), $("gTip"), n, (i) => {
    const m = years * 12 * i / n;
    const label = m === 0 ? "Today" : m < 12 ? `Month ${Math.round(m)}` : `Year ${+(m / 12).toFixed(1)}`;
    return tipHtml(label, [["#22e07a", topLabel, money(top.series[i])], ...(chaseSeries ? [["#e05252", chase.name, money(chaseSeries[i])]] : [])]);
  }, g);
  $("tabs").hidden = Boolean(need);
  $("tabs").innerHTML = HORIZONS.map((y) =>
    `<button class="tab ${y === years ? "on" : ""}" data-y="${y}" aria-pressed="${y === years}">${y} yr</button>`).join("");
  $("tabs").querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => { state.years = Number(t.dataset.y); render(); }));

  renderTrend(d);
}

function renderAllToggle() {
  $("allPanel").hidden = !state.showAll;
  $("allBtn").setAttribute("aria-expanded", String(Boolean(state.showAll)));
  $("allBtn").textContent = state.showAll ? "Hide full list ↑" : `See all ${state.optionCount} options ↓`;
}

// ---------- charts ----------
const SVGNS = "http://www.w3.org/2000/svg";

/** Round axis steps (1, 2, 2.5 or 5 × 10^k) so labels read 4.00%, 4.25%... or $30k, $35k... */
function niceTicks(lo, hi, target = 4) {
  if (hi === lo) { hi += Math.abs(hi) * 0.01 || 1; lo -= Math.abs(lo) * 0.01 || 1; }
  const raw = (hi - lo) / target, mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((st) => st >= raw);
  const y0 = Math.floor(lo / step) * step, y1 = Math.ceil(hi / step) * step;
  const ticks = [];
  for (let v = y0; v <= y1 + step / 2; v += step) ticks.push(+v.toFixed(10));
  return { ticks, y0, y1 };
}

/** Draws line series at the panel's real width so text stays 11px everywhere. Returns its margins. */
function drawLines(svg, { series, yFmt, xTicks, markers = [], H = 240 }) {
  const W = Math.max(280, Math.round(svg.parentElement.clientWidth || 600));
  const L = 52, R = 12, T = 10, B = 24;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const all = series.flatMap((s) => s.values).concat(markers.map((m) => m.v)).filter((v) => v != null);
  const { ticks: yTicks, y0, y1 } = niceTicks(Math.min(...all), Math.max(...all));
  const n = series[0].values.length - 1;
  const x = (i) => L + (W - L - R) * i / n;
  const y = (v) => T + (H - T - B) * (1 - (v - y0) / (y1 - y0));
  const grid = yTicks.map((v) => {
    return `<line x1="${L}" x2="${W - R}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" stroke="#161c18"/>`
      + `<text class="ax" x="${L - 8}" y="${(y(v) + 4).toFixed(1)}" text-anchor="end">${yFmt(v)}</text>`;
  }).join("");
  const paths = series.map((s) => {
    const d = s.values.map((v, i) => (s.step && i
      ? `L${x(i).toFixed(1)},${y(s.values[i - 1]).toFixed(1)}L${x(i).toFixed(1)},${y(v).toFixed(1)}`
      : `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`)).join("");
    const area = s.fill ? `<path d="${d}L${x(n)},${H - B}L${x(0)},${H - B}Z" fill="url(#gfill)"/>` : "";
    return area + `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${s.width || 2}" stroke-linejoin="round"/>`;
  }).join("");
  const last = series.at(-1);
  const dot = `<circle cx="${x(n)}" cy="${y(last.values[n])}" r="3.5" fill="${last.color}"/>`;
  const marks = markers.map((m) => `<circle cx="${x(m.i)}" cy="${y(m.v)}" r="4.5" fill="none" stroke="${m.color}" stroke-width="2"/>`
    + `<text class="ax" x="${x(m.i) + 8}" y="${y(m.v) + 4}" style="fill:${m.color}">${esc(m.label)}</text>`).join("");
  const ticks = xTicks.map(([i, t], k) =>
    `<text class="ax" x="${x(i)}" y="${H - 6}" text-anchor="${k === 0 ? "start" : k === xTicks.length - 1 ? "end" : "middle"}">${esc(t)}</text>`).join("");
  svg.innerHTML = `<defs><linearGradient id="gfill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#22e07a" stop-opacity=".18"/><stop offset="1" stop-color="#22e07a" stop-opacity="0"/></linearGradient></defs>`
    + grid + paths + dot + marks + ticks;
  return { L, R, T, B };
}

function tipHtml(label, rows) {
  return `<div class="d">${esc(label)}</div>` + rows.map(([c, name, v]) =>
    `<div class="row2"><i style="border-color:${c}"></i><b>${esc(v)}</b><span>${esc(name)}</span></div>`).join("");
}

/** Crosshair + tooltip that snaps to the nearest of n+1 evenly spaced points. */
function attachTip(svg, tip, n, html, { L = 4, R = 10, T = 10, B = 24 } = {}) {
  const vb = svg.viewBox.baseVal;
  const hair = document.createElementNS(SVGNS, "line");
  hair.setAttribute("stroke", "#5d6a62");
  hair.setAttribute("visibility", "hidden");
  hair.setAttribute("y1", T); hair.setAttribute("y2", vb.height - B);
  svg.appendChild(hair);
  svg.onpointermove = (e) => {
    const r = svg.getBoundingClientRect();
    const fx = ((e.clientX - r.left) / r.width) * vb.width;
    const i = Math.max(0, Math.min(n, Math.round(((fx - L) / (vb.width - L - R)) * n)));
    const x = L + (vb.width - L - R) * i / n;
    hair.setAttribute("x1", x); hair.setAttribute("x2", x); hair.setAttribute("visibility", "visible");
    tip.innerHTML = html(i);
    tip.hidden = false;
    const px = (x / vb.width) * r.width, w = tip.offsetWidth;
    tip.style.left = Math.max(0, Math.min(r.width - w, px + (px > r.width / 2 ? -w - 12 : 12))) + "px";
  };
  svg.onpointerleave = () => { tip.hidden = true; hair.setAttribute("visibility", "hidden"); };
}

function renderTrend(d) {
  const t = d.trend;
  $("trendCard").hidden = !t?.leaders?.length;
  if (!t?.leaders?.length) return;
  const L = t.leaders;
  const fedAt = (iso) => { let r = null; for (const f of t.fed_funds) if (f.date <= iso) r = f.rate; return r ?? t.fed_funds[0]?.rate ?? null; };
  const fed = L.map((l) => fedAt(l.week));
  const weekOf = (iso) => { const dt = new Date(iso + "T00:00:00"); dt.setDate(dt.getDate() - ((dt.getDay() + 6) % 7)); return dt.toISOString().slice(0, 10); };
  const flags = (t.flags || []).map((f) => ({ ...f, i: L.findIndex((l) => l.week === weekOf(f.date)) })).filter((f) => f.i >= 0);
  const n = L.length - 1, mid = Math.round(n / 2);
  const mon = (iso) => fmtDate(iso, { month: "short", year: "2-digit" });
  const g = drawLines($("trend"), {
    series: [{ values: fed, color: "#9aa7a0", width: 1.6, step: true }, { values: L.map((l) => l.apy), color: "#22e07a", width: 2.2 }],
    yFmt: (v) => v.toFixed(2) + "%",
    xTicks: [[0, mon(L[0].week)], [mid, mon(L[mid].week)], [n, mon(L[n].week)]],
    markers: flags.map((f) => ({ i: f.i, v: f.apy, color: "#f0b429", label: "flagged" })),
  });
  attachTip($("trend"), $("trTip"), n, (i) => tipHtml(`Week of ${fmtDate(L[i].week)}`,
    [["#22e07a", L[i].name, pct(L[i].apy)], ["#9aa7a0", "Fed funds", fed[i] == null ? "—" : pct(fed[i])],
      ...flags.filter((f) => f.i === i).map((f) => ["#f0b429", `${f.bank} · flagged, left out`, pct(f.apy)])]), g);
  $("trLegend").innerHTML = `<span><i style="border-color:#22e07a"></i>Best online savings</span><span><i style="border-color:#9aa7a0"></i>Fed funds</span>`
    + (flags.length ? `<span class="flagkey">○ flagged point, left out</span>` : "");
  $("trSpread").innerHTML = fed[n] != null ? `spread <b>${Math.round((L[n].apy - fed[n]) * 100)} bps</b>` : "";
}

function renderLeaders(d) {
  const t = d.trend;
  $("leaderCard").hidden = !t?.leaders?.length;
  if (!t?.leaders?.length) return;
  const st = leaderStats(t.leaders);
  const max = Math.max(...st.weeks.map((w) => w.weeks));
  $("ldChanges").innerHTML = `#1 changed <b>${st.changes}×</b>`;
  $("leaderBars").innerHTML = st.weeks.map((w) => `<div class="hb ${w.name === st.current ? "cur" : ""}">
    <span class="n">${esc(w.name)}</span><div class="track"><div class="fill" style="width:${(100 * w.weeks / max).toFixed(1)}%"></div></div>
    <span class="w num">${w.weeks} wk</span></div>`).join("");
}

function renderBrief(d) {
  const log = d.brief || [];
  $("briefCard").hidden = !log.length;
  $("briefList").innerHTML = log.slice(0, 5).map((e) => `<li><span class="when num">${esc(fmtDate(e.date, { month: "short", day: "numeric" }))}</span>
    <span class="what">${esc(e.headline)}${e.items.length ? `<small>${esc(e.items.join(" "))}</small>` : ""}</span></li>`).join("");
}

function renderHealth(d) {
  const h = d.health;
  $("healthCard").hidden = !h?.checks?.length;
  if (!h?.checks?.length) return;
  const bad = h.checks.filter((c) => !c.ok);
  const st = $("healthStatus");
  st.className = "r " + (bad.length ? "warn" : "ok");
  st.textContent = bad.length ? `! ${bad.length} need${bad.length > 1 ? "" : "s"} attention` : `✓ all ${h.checks.length} passing`;
  $("healthChecks").innerHTML = h.checks.map((c) =>
    `<li class="${c.ok ? "ok" : "bad"}"><b class="ic" aria-label="${c.ok ? "passing" : "needs attention"}">${c.ok ? "✓" : "!"}</b><div>${esc(c.name)} <span>· ${esc(c.detail)}</span></div></li>`).join("");
  $("healthFlags").innerHTML = (d.trend?.flags || []).map((f) =>
    `<div class="flag"><b>! Flagged</b> ${esc(f.bank)} ${pct(f.apy)} on ${esc(fmtDate(f.date))}: ${esc(f.reason.toLowerCase())}, left out of rankings</div>`).join("");
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
