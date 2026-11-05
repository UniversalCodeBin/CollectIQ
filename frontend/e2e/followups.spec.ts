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

async function openFollowup(page: Page, number: string) {
  await page.getByRole("link", { name: "Dashboard", exact: true }).click();
  await page.getByRole("link", { name: /^Outstanding/ }).click();
  await page.getByRole("link", { name: number }).click();
  await page.getByRole("link", { name: "Follow-up" }).click();
}

test("a draft is reviewed, approved, copied and recorded as sent by a person; nothing is sent by the app", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  const address = uniqueEmail("followup");
  await signUpThroughToDashboard(page, address, "Followup Ltd");
  await importInvoice(page, "F-001");
  await seedDraftPrerequisites(page);

  await openFollowup(page, "F-001");
  await page.getByRole("button", { name: "Prepare a reminder" }).click();
  await page.getByRole("link", { name: "Review the draft" }).click();

  await expect(page.getByText("Ready to send")).toHaveCount(0);
  const text = page.getByLabel("Message text");
  // Keep the facts (number, amount, due date) and add a line; the app refuses a rewrite that drops them.
  await text.fill(`${await text.inputValue()}\nThank you.`);
  await page.getByRole("button", { name: "Save changes" }).click();
  await page.getByRole("button", { name: "Approve and mark ready to send" }).click();

  await expect(page.getByRole("status").filter({ hasText: "Ready to send" })).toBeVisible();
  await expect(page.getByText(/CollectIQ has not sent this/)).toBeVisible();
  await page.getByRole("button", { name: "Copy message text" }).click();
  await expect(page.getByText("Copied. Nothing has been sent.")).toBeVisible();

  await page.getByRole("button", { name: "I sent it" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Record that I sent it" }).click();
  await expect(page.getByText(/Marked sent by you/)).toBeVisible();
});

test("a paused workspace holds a new draft with a plain reason, and resuming needs an explicit click", async ({
  page,
}) => {
  const address = uniqueEmail("pause");
  await signUpThroughToDashboard(page, address, "Pause Ltd");
  await importInvoice(page, "P-001");
  await seedDraftPrerequisites(page);

  await page.getByRole("button", { name: "Pause automation" }).click();
  await expect(page.getByText(/Automation is paused/)).toBeVisible();

  await openFollowup(page, "P-001");
  await page.getByRole("button", { name: "Prepare a reminder" }).click();
  await expect(page.getByText("No draft was made.")).toBeVisible();
  await expect(page.getByText(/\bG\d{1,2}\b/)).toHaveCount(0);

  // Still paused after a reload: only a click resumes it.
  await page.reload();
  await expect(page.getByText(/Automation is paused/)).toBeVisible();
  await page.getByRole("button", { name: "Resume automation" }).click();
  await expect(page.getByText(/Automation is on/)).toBeVisible();
});
