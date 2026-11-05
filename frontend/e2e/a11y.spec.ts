import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { signUpThroughToDashboard, uniqueEmail } from "./support";

const PUBLIC = ["/login", "/signup", "/forgot-password"];
const WORKSPACE = [
  "dashboard",
  "receivables",
  "import/invoices",
  "reconciliation/review",
  "accounts",
  "conversations",
  "cases",
  "followups",
  "inbox",
  "integrations",
  "audit",
  "settings/automation",
];
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

async function scan(page: import("@playwright/test").Page, where: string) {
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  const summary = result.violations.map((v) => `${v.id} (${v.impact}): ${v.nodes.length} node(s), e.g. ${v.nodes[0]?.target}`);
  expect(summary, `axe violations on ${where}`).toEqual([]);
}

test("public screens have no automated accessibility violations", async ({ page }) => {
  for (const route of PUBLIC) {
    await page.goto(route);
    await expect(page.getByRole("heading").first()).toBeVisible();
    await scan(page, route);
  }
});

test("workspace screens have no automated accessibility violations and are keyboard reachable", async ({ page }) => {
  const base = await signUpThroughToDashboard(page, uniqueEmail("a11y"), "A11y Ltd");
  const root = base.replace(/\/dashboard$/, "");
  for (const route of WORKSPACE) {
    await page.goto(`${root}/${route}`);
    await expect(page.getByRole("heading").first()).toBeVisible();
    await scan(page, route);
    await page.keyboard.press("Tab");
    const focused = await page.evaluate(() => document.activeElement?.tagName ?? "");
    expect(["A", "BUTTON", "INPUT", "SELECT", "TEXTAREA", "SUMMARY"], `first Tab on ${route}`).toContain(focused);
  }
});
