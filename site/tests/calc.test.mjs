import { test } from "node:test";
import assert from "node:assert/strict";
import {
  project, projectBank, rankBanks, fdicSplit, treasuryEdge, parseShareParams, buildShareQuery, rateLabel, showdown, leaderStats,
} from "../js/calc.js";

const near = (actual, expected, tol = 1) =>
  assert.ok(Math.abs(actual - expected) <= tol, `${actual} not within ${tol} of ${expected}`);

const CIT = { name: "CIT Bank", apy: 3.75, promo: { apy: 4.35, months: 6, expires: "2026-12-15" },
  min_opening: 100, min_balance_for_apy: 5000, url: "https://www.cit.com/", badge: null };
const bank = (name, apy, extra = {}) =>
  ({ name, apy, promo: null, min_opening: 0, min_balance_for_apy: 0, url: null, badge: null, ...extra });

test("project: plain compounding matches APY", () => {
  const b = project({ principal: 25000, monthly: 0, apy: 3.75, promo: null, years: 10 });
  assert.equal(b.length, 121);
  assert.equal(b[0], 25000);
  near(b.at(-1), 25000 * 1.0375 ** 10);
});

test("project: promo applies only for its months, then base", () => {
  const base1 = project({ principal: 25000, monthly: 0, apy: 3.75, promo: null, years: 1 }).at(-1);
  const promo1 = project({ principal: 25000, monthly: 0, apy: 3.75, promo: CIT.promo, years: 1 }).at(-1);
  near(promo1 - base1, 74.89);
  const base10 = project({ principal: 25000, monthly: 0, apy: 3.75, promo: null, years: 10 }).at(-1);
  const promo10 = project({ principal: 25000, monthly: 0, apy: 3.75, promo: CIT.promo, years: 10 }).at(-1);
  near(promo10 - base10, 104.31);
  assert.ok(promo10 < 25000 * 1.0435 ** 10 - 1000);
});

test("project: monthly contributions", () => {
  const b = project({ principal: 25000, monthly: 500, apy: 4.0, promo: null, years: 10 });
  assert.equal(b.length, 121);
  near(b.at(-1), 110354.07);
});

test("rankBanks: excludes banks whose balance-for-APY exceeds the amount", () => {
  const banks = [CIT, bank("Peak Bank", 4.27, { min_opening: 100 }), bank("TAB Bank", 3.95)];
  const r = rankBanks(banks, { principal: 1000, monthly: 0, years: 10 });
  assert.equal(r.fallback, false);
  assert.deepEqual(r.ranked.map((b) => b.name), ["Peak Bank", "TAB Bank"]);
});

test("rankBanks: promo-aware winner can change with horizon", () => {
  const banks = [CIT, bank("Steady", 3.85)];
  const short = rankBanks(banks, { principal: 25000, monthly: 0, years: 1 });
  const long = rankBanks(banks, { principal: 25000, monthly: 0, years: 10 });
  assert.equal(short.ranked[0].name, "CIT Bank");
  assert.equal(long.ranked[0].name, "Steady");
});

test("rankBanks: falls back when nothing is eligible", () => {
  const banks = [
    bank("A", 4.3, { min_balance_for_apy: 5000 }),
    bank("B", 4.2, { min_balance_for_apy: 250 }),
    bank("C", 4.1, { min_balance_for_apy: 1000, min_opening: 500 }),
  ];
  const r = rankBanks(banks, { principal: 100, monthly: 0, years: 10 });
  assert.equal(r.fallback, true);
  assert.equal(r.neededFor, 250);
  assert.ok(r.ranked.length > 0);
  assert.ok(r.ranked.every((b) => b.min_opening <= 100));
});

test("rankBanks: never empty even below every minimum to open", () => {
  const r = rankBanks([bank("A", 4.3, { min_opening: 500, min_balance_for_apy: 500 })],
    { principal: 1, monthly: 0, years: 10 });
  assert.equal(r.fallback, true);
  assert.equal(r.ranked.length, 1);
});

test("fdicSplit: greedy 250k parts with uninsured remainder", () => {
  const twelve = Array.from({ length: 12 }, (_, i) => bank(`B${i}`, 4));
  const big = fdicSplit(5_000_000, twelve);
  assert.equal(big.parts.length, 12);
  assert.ok(big.parts.every((p) => p.amount === 250000));
  assert.equal(big.uninsured, 2_000_000);
  const small = fdicSplit(300000, twelve);
  assert.deepEqual(small.parts.map((p) => p.amount), [250000, 50000]);
  assert.equal(small.uninsured, 0);
});

test("treasuryEdge: only when the Treasury beats the top bank", () => {
  const edge = treasuryEdge(CIT, 4.46, 25000);
  assert.equal(edge.rate, 4.46);
  assert.ok(edge.extra > 0);
  assert.ok(Number.isInteger(edge.extra));
  assert.equal(treasuryEdge(CIT, 3.0, 25000), null);
  assert.equal(treasuryEdge(CIT, null, 25000), null);
});

test("parseShareParams: validates and clamps", () => {
  assert.equal(parseShareParams("?amount=abc"), null);
  assert.equal(parseShareParams("?amount=-5"), null);
  assert.equal(parseShareParams(""), null);
  assert.deepEqual(parseShareParams("?amount=25000&monthly=1e9"), { amount: 25000, monthly: 0 });
  assert.deepEqual(parseShareParams("?amount=25000&monthly=500"), { amount: 25000, monthly: 500 });
  assert.deepEqual(parseShareParams("?amount=999999999999"), { amount: 100000000, monthly: 0 });
  assert.deepEqual(parseShareParams("?amount=25000&monthly=-3"), { amount: 25000, monthly: 0 });
});

test("buildShareQuery", () => {
  assert.equal(buildShareQuery({ amount: 25000, monthly: 500 }), "?amount=25000&monthly=500");
  assert.equal(buildShareQuery({ amount: 25000, monthly: 0 }), "?amount=25000");
});

test("rateLabel", () => {
  assert.equal(rateLabel(CIT), "4.35% for 6 months, then 3.75%");
  assert.equal(rateLabel(bank("X", 3.75)), "3.75%");
});

test("fallback never credits an APY below its balance requirement", () => {
  const banks = [bank("A", 5.0, { min_balance_for_apy: 5000 })];
  const r = rankBanks(banks, { principal: 100, monthly: 0, years: 1 });
  assert.equal(r.fallback, true);
  assert.equal(r.ranked[0].final, 100); // earns nothing it isn't eligible for
  assert.equal(projectBank(banks[0], { principal: 100, monthly: 0, years: 1 }).at(-1), 100);
  // monthly deposits that cross the threshold start earning from that point
  const grown = projectBank(banks[0], { principal: 100, monthly: 1000, years: 1 }).at(-1);
  assert.ok(grown > 100 + 12000 && grown < 100 + 12000 + 0.05 * 12100);
});

test("rankBanks: monthly-deposit requirement gates eligibility", () => {
  const banks = [bank("Happen", 4.2, { min_monthly_deposit: 250 }), bank("Other", 4.0)];
  assert.deepEqual(rankBanks(banks, { principal: 25000, monthly: 0, years: 10 }).ranked.map((b) => b.name), ["Other"]);
  assert.equal(rankBanks(banks, { principal: 25000, monthly: 250, years: 10 }).ranked[0].name, "Happen");
});

test("showdown: big banks, then the next 4 ranked banks weakest first, then the winner", () => {
  const banks = [bank("A", 4.27), bank("B", 4.2), bank("C", 4.1), bank("D", 4.0), bank("E", 3.9), bank("F", 3.8)];
  const big = [{ name: "JPMorgan Chase", apy: 0.01, as_of: "2026-04-26" }, { name: "Citibank", apy: 0.04, as_of: "2026-04-26" }];
  const s = showdown(banks, big, { principal: 25000, monthly: 0, years: 10 });
  assert.deepEqual(s.big.map((b) => b.name), ["JPMorgan Chase", "Citibank"]);
  assert.deepEqual(s.rivals.map((b) => b.name), ["E", "D", "C", "B"]);
  assert.equal(s.winner.name, "A");
  near(s.big[0].final, 25000 * 1.0001 ** 10);
  near(s.winner.final, 25000 * 1.0427 ** 10);
  assert.ok(s.rivals.every((r) => r.final < s.winner.final));
});

test("showdown: winner matches rankBanks even when the highest APY is ineligible", () => {
  const banks = [bank("Rich", 5, { min_balance_for_apy: 100000 }), bank("A", 4.27), bank("B", 4.2)];
  const s = showdown(banks, [], { principal: 25000, monthly: 0, years: 10 });
  assert.equal(s.winner.name, "A");
  assert.deepEqual(s.rivals.map((b) => b.name), ["B"]);
  assert.deepEqual(s.big, []);
});

test("leaderStats: weeks at #1 per bank, most first, and how often #1 changed", () => {
  const L = (name) => ({ week: "x", name, apy: 4 });
  const s = leaderStats([L("Vio"), L("Vio"), L("Peak"), L("Vio"), L("Peak"), L("Peak"), L("Peak")]);
  assert.deepEqual(s.weeks, [{ name: "Peak", weeks: 4 }, { name: "Vio", weeks: 3 }]);
  assert.equal(s.changes, 3);
  assert.equal(s.current, "Peak");
  assert.deepEqual(leaderStats([]), { weeks: [], changes: 0, current: null });
});
