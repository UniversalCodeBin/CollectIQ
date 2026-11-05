/** Typed amount ("1500.50") to integer minor units. Money never passes through a float. */
export function parseMinor(text: string): number | null {
  const match = /^(\d{1,12})(?:\.(\d{1,2}))?$/.exec(text.trim().replace(/,/g, ""));
  if (!match) return null;
  const minor = Number(match[1]) * 100 + Number((match[2] ?? "").padEnd(2, "0"));
  return minor > 0 && Number.isSafeInteger(minor) ? minor : null;
}

/** Minor units back to the text a person types, without a currency symbol. */
export function minorToText(minor: number): string {
  return `${Math.trunc(minor / 100)}.${String(minor % 100).padStart(2, "0")}`;
}
