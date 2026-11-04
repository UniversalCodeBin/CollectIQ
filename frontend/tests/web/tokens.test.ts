import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { renderCss, renderTs } from "../../scripts/tokens.mjs";
import { tokens as generated } from "../../src/styles/tokens.generated";
import source from "../../src/styles/tokens.json";

const STYLES = resolve(__dirname, "../../src/styles");

function channel(value: number) {
  const unit = value / 255;
  return unit <= 0.03928 ? unit / 12.92 : ((unit + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string) {
  const parts = [1, 3, 5].map((start) => parseInt(hex.slice(start, start + 2), 16));
  const [red = 0, green = 0, blue = 0] = parts.map(channel);
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}

function contrast(a: string, b: string) {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (high + 0.05) / (low + 0.05);
}

describe("design tokens", () => {
  it("holds the directive values", () => {
    expect(source.color.bg.toUpperCase()).toBe("#F6F4EF");
    expect(source.color.primary.toUpperCase()).toBe("#0E5A6B");
    expect(source.color.text.toUpperCase()).toBe("#1B1F27");
    expect(source.color.secondary.toUpperCase()).toBe("#505968");
    expect(source.radius.md).toBe("8px");
    expect(source.font.sans).toMatch(/^"IBM Plex Sans"/);
    expect(source.font.mono).toMatch(/^"IBM Plex Mono"/);
  });

  it("spacing moves in 4px steps", () => {
    for (const value of Object.values(source.space)) expect(parseInt(value, 10) % 4).toBe(0);
  });

  it("the generated files match the source", () => {
    expect(readFileSync(resolve(STYLES, "tokens.generated.css"), "utf-8")).toBe(renderCss(source));
    expect(readFileSync(resolve(STYLES, "tokens.generated.ts"), "utf-8")).toBe(renderTs(source));
    expect(generated.color.primary).toBe(source.color.primary);
  });

  it("text and status pairs meet 4.5:1", () => {
    const { color, status } = source;
    expect(contrast(color.text, color.bg)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(color.secondary, color.bg)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(color.primary, color.bg)).toBeGreaterThanOrEqual(4.5);
    expect(contrast("#FFFFFF", color.primary)).toBeGreaterThanOrEqual(4.5);
    for (const [name, pair] of Object.entries(status)) {
      expect(contrast(pair.fg, pair.bg), name).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("control borders and status icons meet 3:1", () => {
    const { color, status } = source;
    expect(contrast(color.borderControl, color.bg)).toBeGreaterThanOrEqual(3);
    for (const [name, pair] of Object.entries(status)) {
      expect(contrast(pair.icon, pair.bg), name).toBeGreaterThanOrEqual(3);
    }
  });
});
