import { describe, expect, it } from "vitest";
import { formatMoney } from "../../src/lib/format";

describe("formatMoney", () => {
  it("groups INR the Indian way and USD the Western way", () => {
    expect(formatMoney("1234567.50", "INR")).toBe("₹12,34,567.50");
    expect(formatMoney("1234567.50", "USD")).toBe("$1,234,567.50");
  });

  it("keeps every digit of a value a float would corrupt", () => {
    expect(formatMoney("90071992547409931.07", "USD")).toBe("$90,071,992,547,409,931.07");
  });

  it("pads to two decimals and handles small and negative amounts", () => {
    expect(formatMoney("5", "INR")).toBe("₹5.00");
    expect(formatMoney("999.5", "USD")).toBe("$999.50");
    expect(formatMoney("-1000.00", "INR")).toBe("-₹1,000.00");
  });

  it("names a currency it has no symbol for", () => {
    expect(formatMoney("1000.00", "EUR")).toBe("EUR 1,000.00");
  });

  it("refuses a malformed amount rather than guessing", () => {
    expect(() => formatMoney("12,50", "INR")).toThrow();
    expect(() => formatMoney("1.234", "INR")).toThrow();
  });
});
