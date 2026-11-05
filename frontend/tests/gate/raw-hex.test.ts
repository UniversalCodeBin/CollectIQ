import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { ESLint } from "eslint";
import { describe, expect, it } from "vitest";
import { findRawHex } from "../../eslint-rules/no-raw-hex.js";

const fixture = readFileSync(resolve(__dirname, "fixtures/raw-hex.tsx.txt"), "utf-8");

async function lint(code: string, filePath = "src/features/example/Example.tsx") {
  const eslint = new ESLint({ cwd: resolve(__dirname, "../..") });
  const results = await eslint.lintText(code, { filePath });
  return results.flatMap((result) => result.messages).filter((message) => message.ruleId === "collectiq/no-raw-hex");
}

describe("no-raw-hex", () => {
  it("rejects a raw hex colour in a component", async () => {
    expect((await lint(fixture)).length).toBeGreaterThan(0);
  }, 30_000); // first ESLint load is a cold start and can pass 5 s when other workers are busy

  it("rejects a raw hex colour inside a template literal", async () => {
    expect((await lint("export const c = `1px solid #0E5A6B`;\n")).length).toBeGreaterThan(0);
  });

  it("accepts a token reference", async () => {
    expect(await lint('export const c = "var(--color-primary)";\n')).toEqual([]);
  });

  it("does not mistake an invoice number for a colour", async () => {
    expect(await lint('export const label = "Invoice #1042";\n')).toEqual([]);
  });

  it("allows raw values only in the generated token file", async () => {
    expect(await lint('export const c = "#0E5A6B";\n', "src/styles/tokens.generated.ts")).toEqual([]);
  });

  it("finds no raw colour in any stylesheet except the generated tokens", () => {
    const root = resolve(__dirname, "../../src");
    const sheets = readdirSync(root, { recursive: true, encoding: "utf-8" }).filter(
      (name) => name.endsWith(".css") && !name.endsWith("tokens.generated.css"),
    );
    const offenders = sheets.filter((name) => findRawHex(readFileSync(resolve(root, name), "utf-8")).length > 0);
    expect(offenders).toEqual([]);
  });
});
