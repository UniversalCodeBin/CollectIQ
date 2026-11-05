import { expect, type Page, test } from "@playwright/test";
import { signUpThroughToDashboard, uniqueEmail } from "./support";

const CSV = ["Invoice No,Customer,Due,Currency,Amount", "R-001,Northwind Traders,2026-01-15,INR,1000.00", "R-002,Contoso Supplies,2026-01-20,INR,2500.50"].join("\n");

async function importTwoInvoices(page: Page) {
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
  await expect(page.getByText("2 invoices created")).toBeVisible();
}

test("dashboard, receivables, invoice details, cancel and client profile on the real API", async ({ page }) => {
  const dashboardUrl = await signUpThroughToDashboard(page, uniqueEmail("recv"), "Receivables Ltd");
  await importTwoInvoices(page);

  await page.goto(dashboardUrl);
  const inr = page.getByRole("region", { name: "INR" });
  await expect(inr.getByRole("link", { name: /outstanding/i })).toContainText("₹3,500.50");
  await inr.getByRole("link", { name: /overdue/i }).click();
  await expect(page).toHaveURL(/receivables\?.*tile=overdue/);
  await expect(page.getByRole("link", { name: "R-001" })).toBeVisible();
  await expect(page.getByRole("link", { name: "R-002" })).toBeVisible();
  await expect(page.getByText(/mark (as )?paid/i)).toHaveCount(0);

  await page.getByRole("link", { name: "R-001" }).click();
  await expect(page.getByRole("heading", { name: "Invoice R-001" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Where this came from" })).toContainText(/invoices\.csv, row 2/);
  await expect(page.getByRole("region", { name: "From the invoice" })).toContainText("₹1,000.00");

  await page.getByRole("button", { name: "Cancel invoice" }).click();
  await page.getByRole("button", { name: "Cancel this invoice" }).click();
  await expect(page.getByText(/before cancelling/i)).toBeVisible();
  await page.getByLabel("Reason").fill("Raised twice by mistake");
  await page.getByRole("button", { name: "Cancel this invoice" }).click();
  await expect(page.getByText("Cancelled", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Northwind Traders" }).click();
  await expect(page.getByRole("heading", { name: "Northwind Traders" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Contacts" })).toContainText("No contacts yet");
  await expect(page.getByRole("link", { name: "R-001" })).toBeVisible();
});

for (const width of [320, 768, 1024, 1440]) {
  test(`dashboard and receivables do not scroll sideways at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const dashboardUrl = await signUpThroughToDashboard(page, uniqueEmail(`w${width}`), "Width Ltd");
    await importTwoInvoices(page);
    for (const url of [dashboardUrl, dashboardUrl.replace("/dashboard", "/receivables")]) {
      await page.goto(url);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(0);
    }
  });
}
