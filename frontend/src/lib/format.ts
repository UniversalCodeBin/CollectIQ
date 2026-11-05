const SYMBOLS: Record<string, string> = { INR: "₹", USD: "$" };
const AMOUNT = /^(-?)(\d+)(?:\.(\d{1,2}))?$/;

function group(digits: string, currency: string): string {
  if (currency !== "INR") return digits.replace(/\B(?=(\d{3})+$)/g, ",");
  if (digits.length <= 3) return digits;
  const head = digits.slice(0, -3).replace(/\B(?=(\d{2})+$)/g, ",");
  return `${head},${digits.slice(-3)}`;
}

/** Formats a decimal string exactly. Money never passes through a float. */
export function formatMoney(amount: string, currency: string): string {
  const match = AMOUNT.exec(amount);
  if (!match) throw new Error(`Not a money amount: ${amount}`);
  const [, sign = "", whole = "", fraction = ""] = match;
  const symbol = SYMBOLS[currency] ?? `${currency} `;
  return `${sign}${symbol}${group(whole, currency)}.${fraction.padEnd(2, "0")}`;
}

/** Integer minor units (two decimals) to a display amount. Money never passes through a float. */
export function formatMinor(minor: number, currency: string): string {
  const sign = minor < 0 ? "-" : "";
  const absolute = Math.abs(minor);
  const cents = String(absolute % 100).padStart(2, "0");
  return formatMoney(`${sign}${Math.trunc(absolute / 100)}.${cents}`, currency);
}
