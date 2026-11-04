import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = resolve(__dirname, "../..");
const EXTERNAL = /(?:https?:)?\/\/[a-z0-9.-]+\.[a-z]{2,}/i;

function cssUnder(directory: string): string[] {
  return readdirSync(directory, { recursive: true, encoding: "utf-8" })
    .filter((name) => name.endsWith(".css"))
    .map((name) => resolve(directory, name));
}

function fontSheets(): string[] {
  const main = readFileSync(resolve(ROOT, "src/main.tsx"), "utf-8");
  const imports = [...main.matchAll(/import "(@fontsource\/[^"]+\.css)"/g)].map((match) => match[1] as string);
  expect(imports.length).toBeGreaterThan(0);
  return imports.map((name) => resolve(ROOT, "node_modules", name));
}

describe("self-hosting", () => {
  it("index.html and CSS reference no external origin", () => {
    const html = readFileSync(resolve(ROOT, "index.html"), "utf-8");
    expect(html).not.toMatch(EXTERNAL);
    const sheets = cssUnder(resolve(ROOT, "src"));
    expect(sheets.length).toBeGreaterThan(0);
    for (const sheet of [...sheets, ...fontSheets()]) {
      expect(readFileSync(sheet, "utf-8"), sheet).not.toMatch(EXTERNAL);
    }
  });

  it("the fonts resolve to files shipped in the package", () => {
    for (const sheet of fontSheets()) {
      const urls = [...readFileSync(sheet, "utf-8").matchAll(/url\(([^)]+)\)/g)].map((match) => match[1] as string);
      expect(urls.length).toBeGreaterThan(0);
      for (const url of urls) expect(existsSync(resolve(dirname(sheet), url)), url).toBe(true);
    }
  });

  it("no stylesheet uses a gradient or a glass effect", () => {
    for (const sheet of cssUnder(resolve(ROOT, "src"))) {
      expect(readFileSync(sheet, "utf-8"), sheet).not.toMatch(/gradient|backdrop-filter/i);
    }
  });
});
