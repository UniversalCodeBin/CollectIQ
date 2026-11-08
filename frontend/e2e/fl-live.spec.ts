import { expect, type Page, test } from "@playwright/test";
import { signUpThroughToDashboard, uniqueEmail } from "./support";

/**
 * Live-backend slices of FL-03, FL-10, FL-12, FL-13, FL-14 and FL-16. Only what the running app can really
 * do is driven here. The AI-dependent starts (a reply classified as a dispute, a reading to correct) need
 * AI_PROVIDER to be set, and Gmail connect/reconnect is not available (OD-11), so those parts stay covered
 * by the Vitest stub tests and are not claimed as live.
 */

const CSV = ["Invoice No,Customer,Due,Currency,Amount", "FL-001,Northwind Traders,2026-01-15,INR,1000.00"].join("\n");

async function importOne(page: Page) {
  await page.getByRole("link", { name: "Import your invoices" }).click();
  await page.getByLabel("Choose a CSV file").setInputFiles({ name: "invoices.csv", mimeType: "text/csv", buffer: Buffer.from(CSV) });
  await page.getByRole("button", { name: "Upload file" }).click();
  await page.getByLabel("Invoice number").selectOption("Invoice No");
  await page.getByLabel("Client name").selectOption("Customer");
  await page.getByLabel("Due date").selectOption("Due");
  await page.getByLabel("Currency").selectOption("Currency");
  await page.getByLabel("Total", { exact: true }).selectOption("Amount");
  await page.getByLabel("Date format").selectOption("YYYY-MM-DD");
  await page.getByRole("button", { name: "Continue to preview" }).click();
  await page.getByRole("button", { name: "Commit Invoices" }).click();
  await expect(page.getByRole("heading", { name: "Import finished" })).toBeVisible();
}

async function openInvoice(page: Page) {
  await page.getByRole("link", { name: "Dashboard", exact: true }).click();
  await page.getByRole("link", { name: /^Outstanding/ }).click();
  await page.getByRole("link", { name: "FL-001" }).click();
  await expect(page.getByRole("heading", { name: "Invoice FL-001" })).toBeVisible();
}

test("FL-03 (invoice correction): a correction needs a reason, is kept, and is shown as differing from the file", async ({ page }) => {
  await signUpThroughToDashboard(page, uniqueEmail("fl03"), "Correct Ltd");
  await importOne(page);
  await openInvoice(page);

  await page.getByRole("button", { name: "Correct details" }).click();
  await page.getByLabel("PO number").fill("PO-77");
  await page.getByRole("button", { name: "Save correction" }).click();
  await expect(page.getByText(/Say why you are correcting it/)).toBeVisible();

  await page.getByLabel("Reason").fill("PO number was missing from the file");
  await page.getByRole("button", { name: "Save correction" }).click();
  await expect(page.getByText(/Some details were corrected after import: po number/)).toBeVisible();
  await page.reload();
  await expect(page.getByText("PO-77")).toBeVisible();
});

test("FL-12 (uncertain status): an imported invoice with no payment evidence is never shown as paid", async ({ page }) => {
  await signUpThroughToDashboard(page, uniqueEmail("fl12"), "Uncertain Ltd");
  await importOne(page);
  await openInvoice(page);

  await expect(page.getByText("Evidence", { exact: true })).toBeVisible();
  await expect(page.getByText("Recorded as paid").locator("xpath=following-sibling::dd[1]")).toContainText("0.00");
  await expect(page.getByRole("button", { name: /mark.*paid/i })).toHaveCount(0);
});

test("FL-10 (disputes): the cases screen opens on a live backend and starts empty", async ({ page }) => {
  const dashboard = await signUpThroughToDashboard(page, uniqueEmail("fl10"), "Disputes Ltd");
  await page.goto(dashboard.replace(/dashboard$/, "cases"));
  await expect(page.getByRole("heading", { name: "Disputes and questions" })).toBeVisible();
  await expect(page.getByText("Nothing to review")).toBeVisible();
});

test("FL-13/16 (integrations): Gmail is never shown connected without a verified connection, so there is nothing to disconnect", async ({ page }) => {
  const dashboard = await signUpThroughToDashboard(page, uniqueEmail("fl16"), "Integrations Ltd");
  await page.goto(dashboard.replace(/dashboard$/, "integrations"));
  await expect(page.getByRole("heading", { name: "Integrations" })).toBeVisible();
  await expect(page.getByText("Connected and verified")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Disconnect Gmail" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Connect Gmail" })).toBeVisible();
});
