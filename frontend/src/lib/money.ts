/**
 * Money is integer qəpik everywhere (100 qəpik = 1 manat), exactly as the backend and the
 * contracts keep it. Nothing in the app does arithmetic in manat or in floats: amounts
 * are added and compared as qəpik, and only these formatters turn them into text.
 */
export type Qapik = number;

const whole = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const cents = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** "₼1,250", or "₼1,250.50" when there are qəpik left over (or always with `exact`). */
export function manat(q: Qapik, { exact = false }: { exact?: boolean } = {}): string {
  const sign = q < 0 ? "−" : "";
  const abs = Math.abs(Math.round(q));
  const showCents = exact || abs % 100 !== 0;
  const n = showCents ? cents.format(abs / 100) : whole.format(Math.floor(abs / 100));
  return `${sign}₼${n}`;
}

/** "₼950", "₼48.2K", "₼1.25M": for tight spaces like map tooltips and chips. */
export function manatShort(q: Qapik): string {
  const m = Math.round(q) / 100;
  if (Math.abs(m) < 10_000) return manat(Math.round(q) - (Math.round(q) % 100));
  if (Math.abs(m) < 1_000_000) return `₼${trim(m / 1_000, 1)}K`;
  return `₼${trim(m / 1_000_000, 2)}M`;
}

function trim(n: number, digits: number): string {
  return n.toFixed(digits).replace(/\.?0+$/, "");
}

/** Whole manat typed by a person, to qəpik. Returns null for anything that is not a
 *  positive amount with at most two decimals. */
export function parseManat(text: string): Qapik | null {
  const clean = text.replace(/[₼\s,]/g, "");
  if (!/^\d+(\.\d{1,2})?$/.test(clean)) return null;
  const [m, c = ""] = clean.split(".");
  const q = Number(m) * 100 + Number(c.padEnd(2, "0"));
  return q > 0 && Number.isSafeInteger(q) ? q : null;
}

export const toQapik = (wholeManat: number): Qapik => Math.round(wholeManat) * 100;

/** Share of a goal, 0..100, rounded down so a project is never shown as 100% before it is. */
export function percentOf(part: Qapik, of: Qapik): number {
  if (of <= 0) return 0;
  return Math.max(0, Math.min(100, Math.floor((part * 100) / of)));
}

const count = new Intl.NumberFormat("en-US");
export const fmtCount = (n: number) => count.format(n);
