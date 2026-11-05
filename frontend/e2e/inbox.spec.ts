import { expect, type Page, test } from "@playwright/test";
import { seedDraftPrerequisites, signUpThroughToDashboard, uniqueEmail } from "./support";

async function importInvoice(page: Page, number: string) {
  const csv = ["Invoice No,Customer,Due,Currency,Amount", `${number},Northwind Traders,2026-01-15,INR,1000.00`].join("\n");
  await page.getByRole("link", { name: "Import your invoices" }).click();
  await page.getByLabel("Choose a CSV file").setInputFiles({ name: "invoices.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
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


test("onboarding reaches a usable dashboard with every step skippable", async ({ page }) => {
  await signUpThroughToDashboard(page, uniqueEmail("onboard"), "Onboard Ltd");
  await expect(page.getByRole("heading", { name: "Getting started" })).toBeVisible();
  await page.getByRole("button", { name: "Skip Add payment evidence" }).click();
  await expect(page.getByText("Skipped")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Skipped")).toBeVisible();
  await page.getByRole("button", { name: "Hide this checklist" }).click();
  await page.getByRole("link", { name: "Review the queue" }).click();
  await expect(page).toHaveURL(/\/receivables/);
  await page.getByRole("link", { name: "Review Inbox" }).click();
  await expect(page.getByText("Nothing needs your review")).toBeVisible();
});

test("a waiting draft appears in the inbox, opens its review, and leaves the inbox once resolved", async ({ page }) => {
  const address = uniqueEmail("inbox");
  await signUpThroughToDashboard(page, address, "Inbox Ltd");
  await importInvoice(page, "I-001");
  await seedDraftPrerequisites(page);

  await page.getByRole("link", { name: "Dashboard", exact: true }).click();
  await page.getByRole("link", { name: /^Outstanding/ }).click();
  await page.getByRole("link", { name: "I-001" }).click();
  await page.getByRole("link", { name: "Follow-up", exact: true }).click();
  await page.getByRole("button", { name: "Prepare a reminder" }).click();
  await expect(page.getByRole("link", { name: "Review the draft" })).toBeVisible();

  await page.getByRole("link", { name: "Review Inbox" }).click();
  await expect(page.getByRole("heading", { name: /^Reminder drafts/ })).toBeVisible();
  await page.getByRole("link", { name: "Approve or reject the draft" }).click();
  await page.getByRole("button", { name: "Reject draft" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Reject draft" }).click();

  await page.getByRole("link", { name: "Review Inbox" }).click();
  await expect(page.getByText("Nothing needs your review")).toBeVisible();
});
