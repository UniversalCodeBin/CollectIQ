import { expect, test } from "@playwright/test";
import { signUpThroughToDashboard, uniqueEmail } from "./support";

const CSV = [
  "Invoice No,Customer,Due,Currency,Amount",
  "E2E-001,Northwind Traders,2026-01-15,INR,1000.00",
  "E2E-002,Contoso Supplies,2026-01-20,INR,2500.50",
  "E2E-003,Contoso Supplies,not a date,INR,300.00",
].join("\n");

test("import a CSV, skip the invalid row, commit, and keep the place on reload", async ({ page }) => {
  await signUpThroughToDashboard(page, uniqueEmail("import"), "Import Ltd");
  await page.getByRole("link", { name: "Import your invoices" }).click();
  await expect(page.getByRole("heading", { name: "Upload your invoices" })).toBeVisible();

  await page.getByLabel("Choose a CSV file").setInputFiles({ name: "invoices.csv", mimeType: "text/csv", buffer: Buffer.from(CSV) });
  await page.getByRole("button", { name: "Upload file" }).click();
  await expect(page.getByRole("heading", { name: "Match your columns" })).toBeVisible();

  await page.getByLabel("Invoice number").selectOption("Invoice No");
  await page.getByLabel("Client name").selectOption("Customer");
  await page.getByLabel("Due date").selectOption("Due");
  await page.getByLabel("Currency").selectOption("Currency");
  await page.getByLabel("Total", { exact: true }).selectOption("Amount");
  await page.getByLabel("Date format").selectOption("YYYY-MM-DD");
  await page.getByRole("button", { name: "Continue to preview" }).click();
  await expect(page.getByRole("heading", { name: "Review before importing" })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("heading", { name: "Review before importing" })).toBeVisible();

  await expect(page.getByRole("button", { name: "Commit Invoices" })).toHaveAttribute("aria-disabled", "true");
  await page.getByLabel(/Skip the 1 invalid row/).check();
  await page.getByRole("button", { name: "Commit Invoices" }).click();
  await expect(page.getByRole("heading", { name: "Import finished" })).toBeVisible();
  await expect(page.getByText("2 invoices created")).toBeVisible();
});
