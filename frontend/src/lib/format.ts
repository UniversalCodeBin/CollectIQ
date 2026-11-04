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
