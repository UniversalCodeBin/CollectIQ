import { expect, test } from "@playwright/test";
import { signUpThroughToDashboard, uniqueEmail } from "./support";

const WIDTHS = [320, 360, 768, 1024, 1440];
const ROUTES = [
  "dashboard",
  "receivables",
  "import/invoices",
  "reconciliation/pending",
  "accounts",
  "conversations",
  "cases",
  "followups",
  "inbox",
  "integrations",
  "audit",
  "settings/automation",
];

for (const width of WIDTHS) {
  test(`FL-01/15 every screen fits without sideways scrolling at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    const base = await signUpThroughToDashboard(page, uniqueEmail(`vp${width}`), `Viewport ${width} Ltd`);
    const root = base.replace(/\/dashboard$/, "");
    for (const route of ROUTES) {
      await page.goto(`${root}/${route}`);
      await expect(page.getByRole("heading").first()).toBeVisible();
      await expect(page.getByText("Page not found")).toHaveCount(0);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow, `${route} at ${width}px`).toBeLessThanOrEqual(1);
    }
  });
}
