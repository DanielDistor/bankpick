// Money math for the recommender. Pure functions, no DOM; tested in site/tests.

export const FDIC_LIMIT = 250000;
export const MAX_AMOUNT = 100000000;
export const MAX_MONTHLY = 1000000;

const monthlyRate = (apyPct) => (1 + apyPct / 100) ** (1 / 12) - 1;

/**
 * Month-end balances, length years*12+1, index 0 = principal.
 * A promo rate applies for its first `promo.months` months, then the ongoing APY.
 * Contributions land at each month end, after that month's interest.
 */
export function project({ principal, monthly = 0, apy, promo = null, years }) {
  const base = monthlyRate(apy);
  const boosted = promo ? monthlyRate(promo.apy) : base;
  const promoMonths = promo ? promo.months : 0;
  const balances = [principal];
  let bal = principal;
  for (let m = 1; m <= years * 12; m++) {
    bal = bal * (1 + (m <= promoMonths ? boosted : base)) + monthly;
    balances.push(bal);
  }
  return balances;
}

const finalBalance = (bank, { principal, monthly, years }) =>
  project({ principal, monthly, apy: bank.apy, promo: bank.promo, years }).at(-1);

const threshold = (bank) => Math.max(bank.min_opening || 0, bank.min_balance_for_apy || 0);

function sortByGrowth(banks, opts) {
  return banks
    .map((b) => ({ ...b, final: finalBalance(b, opts) }))
    .sort((a, b) => b.final - a.final || a.name.localeCompare(b.name));
}

/**
 * Rank banks by what the money actually grows to over the horizon.
 * Eligible = amount meets both the minimum to open and the balance needed for the APY.
 * When nothing qualifies, fall back to banks the person can at least open,
 * and report the smallest amount the top-rate banks need.
 */
export function rankBanks(banks, { principal, monthly = 0, years }) {
  const opts = { principal, monthly, years };
  const eligible = banks.filter((b) => principal >= threshold(b));
  if (eligible.length) return { ranked: sortByGrowth(eligible, opts), fallback: false, neededFor: null };

  const topByApy = [...banks].sort((a, b) => b.apy - a.apy).slice(0, 3);
  const neededFor = topByApy.length ? Math.min(...topByApy.map(threshold)) : null;
  const openable = banks.filter((b) => principal >= (b.min_opening || 0));
  return { ranked: sortByGrowth(openable.length ? openable : banks, opts), fallback: true, neededFor };
}

/** Split an amount across ranked banks, at most the FDIC limit each. */
export function fdicSplit(amount, ranked) {
  const parts = [];
  let left = amount;
  for (const b of ranked) {
    if (left <= 0) break;
    const take = Math.min(FDIC_LIMIT, left);
    parts.push({ name: b.name, amount: take });
    left -= take;
  }
  return { parts, uninsured: left };
}

/** A 1-year Treasury line, only when it beats the top bank's real first-year earnings. */
export function treasuryEdge(topBank, treasury1y, principal) {
  if (!topBank || treasury1y == null) return null;
  const bankEarned =
    project({ principal, monthly: 0, apy: topBank.apy, promo: topBank.promo, years: 1 }).at(-1) - principal;
  const extra = Math.round(principal * (treasury1y / 100) - bankEarned);
  return extra > 0 ? { rate: treasury1y, extra } : null;
}

/** Read ?amount=&monthly= ; null when the amount is missing or invalid. */
export function parseShareParams(search) {
  const params = new URLSearchParams(search);
  const rawAmount = params.get("amount");
  if (rawAmount === null || rawAmount.trim() === "") return null;
  const amount = Number(rawAmount);
  if (!Number.isFinite(amount) || amount <= 0) return null;

  const rawMonthly = Number(params.get("monthly") ?? 0);
  const monthly = Number.isFinite(rawMonthly) && rawMonthly >= 0 && rawMonthly <= MAX_MONTHLY
    ? Math.round(rawMonthly) : 0;
  return { amount: Math.min(MAX_AMOUNT, Math.max(1, Math.round(amount))), monthly };
}

export function buildShareQuery({ amount, monthly }) {
  return monthly > 0 ? `?amount=${amount}&monthly=${monthly}` : `?amount=${amount}`;
}

export function rateLabel(bank) {
  const base = `${bank.apy.toFixed(2)}%`;
  if (!bank.promo) return base;
  const m = bank.promo.months;
  return `${bank.promo.apy.toFixed(2)}% for ${m} month${m === 1 ? "" : "s"}, then ${base}`;
}
