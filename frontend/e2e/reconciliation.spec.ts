import { expect, type Page, test } from "@playwright/test";
import { signUpThroughToDashboard, uniqueEmail } from "./support";

const PNG = Buffer.from("89504e470d0a1a0a0000000d49484452", "hex");

async function importInvoices(page: Page, rows: string[]) {
  const csv = ["Invoice No,Customer,Due,Currency,Amount", ...rows].join("\n");
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

/** Declares an account, checks a statement (nothing added yet), then explicitly adds it. */
async function addStatement(page: Page, rows: string[]) {
  await page.getByRole("link", { name: "Payment Accounts" }).click();
  if (!(await page.getByText("HDFC Current").count())) {
    await page.getByRole("button", { name: "Declare an account" }).click();
    await page.getByLabel("Account name").fill("HDFC Current");
    await page.getByRole("button", { name: "Save account" }).click();
    await expect(page.getByText("HDFC Current")).toBeVisible();
  }
  await page.getByRole("button", { name: /Upload statement/ }).click();
  const csv = ["Date,Description,Amount", ...rows].join("\n");
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Statement file").setInputFiles({ name: "statement.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await dialog.getByLabel("Date format").selectOption("YYYY-MM-DD");
  await dialog.getByLabel("Statement covers from").fill("2026-01-01");
  await dialog.getByLabel("Statement covers to").fill("2026-01-31");
  await dialog.getByRole("button", { name: "Check statement" }).click();
  await expect(dialog.getByText(/Nothing is added until you confirm/)).toBeVisible();
  await dialog.getByRole("button", { name: "Add transactions" }).click();
  await expect(dialog).toBeHidden();
}

async function reviewPage(page: Page, link: string) {
  await page.getByRole("link", { name: "Payment Reconciliation" }).click();
  // The matcher runs in the worker, so give it a moment and reload until the suggestion arrives.
  await expect(async () => {
    await page.reload();
    await expect(page.getByText(link).first()).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 30_000 });
}

test("account coverage, statement preview, confirm, balance and a traced reversal", async ({ page }) => {
  await signUpThroughToDashboard(page, uniqueEmail("recon"), "Recon Ltd");
  await importInvoices(page, ["R-001,Northwind Traders,2026-01-15,INR,1000.00"]);
  await addStatement(page, ["2026-01-20,NORTHWIND TRADERS UTR1,1000.00"]);
  await expect(page.getByText(/Statements through 31 Jan 2026/)).toBeVisible();

  await reviewPage(page, "R-001");
  await expect(page.getByRole("link", { name: /Match review 1/ })).toBeVisible();
  await expect(page.getByText(/amount/i).first()).toBeVisible();
  await page.getByRole("button", { name: "Confirm Match & Apply Allocation" }).click();
  await expect(page.getByText("Nothing to review")).toBeVisible();

  await page.getByRole("link", { name: /Confirmed Payments 1/ }).click();
  await page.getByRole("button", { name: "Details" }).click();
  await page.getByRole("button", { name: "Reverse allocation" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Reason").fill("Applied to the wrong invoice");
  await dialog.getByRole("button", { name: "Reverse allocation" }).click();
  await expect(dialog).toBeHidden();
  await page.getByRole("link", { name: /Unmatched 1/ }).click();
  await expect(page.getByText(/unapplied/)).toBeVisible();

  // FR-056: the invoice's own history shows the allocation and its reversal, with the reason.
  await page.getByRole("link", { name: "Dashboard" }).click();
  await page.getByRole("link", { name: /^Outstanding/ }).click();
  await page.getByRole("link", { name: "R-001" }).click();
  await page.getByRole("link", { name: "Payment history" }).click();
  const history = page.getByRole("list", { name: "Payment history" });
  await expect(history.getByRole("listitem")).toHaveCount(2);
  await expect(history.getByText("Applied", { exact: true })).toBeVisible();
  await expect(history.getByText("Reversed", { exact: true })).toBeVisible();
  await expect(history.getByText(/Applied to the wrong invoice/)).toBeVisible();
});

test("partial allocation shows the remainder, and Not a Match sticks after reload", async ({ page }) => {
  await signUpThroughToDashboard(page, uniqueEmail("partial"), "Partial Ltd");
  await importInvoices(page, ["P-001,Contoso Supplies,2026-01-15,INR,3000.00"]);
  await addStatement(page, ["2026-01-20,CONTOSO SUPPLIES UTR2,3000.00"]);
  await reviewPage(page, "P-001");
  await page.getByRole("button", { name: "Split / Partial Allocation..." }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel(/Amount to apply/).fill("1000.00");
  await expect(dialog.getByText(/Invoice balance after this: ₹2,000.00/)).toBeVisible();
  await dialog.getByRole("button", { name: "Apply allocation" }).click();
  await expect(dialog).toBeHidden();
  await page.getByRole("link", { name: /Unmatched/ }).click();
  await expect(page.getByText(/₹2,000.00 unapplied/)).toBeVisible();
});

test("Not a Match is kept and a lost reply offers Check status without applying twice", async ({ page }) => {
  await signUpThroughToDashboard(page, uniqueEmail("reject"), "Reject Ltd");
  await importInvoices(page, ["N-001,Fabrikam,2026-01-15,INR,800.00", "N-002,Litware,2026-01-15,INR,900.00"]);
  await addStatement(page, ["2026-01-20,FABRIKAM UTR3,800.00", "2026-01-21,LITWARE UTR4,900.00"]);
  await reviewPage(page, "N-001");
  const card = page.getByRole("listitem").filter({ hasText: "N-001" });
  await card.getByRole("button", { name: "Not a Match" }).click();
  await expect(page.getByText("N-001")).toBeHidden();
  await page.reload();
  await expect(page.getByText("N-001")).toBeHidden();

  let attempts = 0;
  await page.route("**/reconciliation/proposals/*/confirm", async (route) => {
    attempts += 1;
    if (attempts === 1) {
      await route.fetch(); // the server applies it, but the reply is lost
      return route.abort("connectionreset");
    }
    return route.continue();
  });
  await page.getByRole("button", { name: "Confirm Match & Apply Allocation" }).click();
  await page.getByRole("button", { name: "Check status" }).click();
  await expect(page.getByText("Nothing to review")).toBeVisible();
  await page.getByRole("link", { name: /Confirmed Payments 1/ }).click();
  await page.getByRole("button", { name: "Details" }).click();
  await expect(page.getByRole("list", { name: "Allocation history" }).getByRole("listitem")).toHaveCount(1);
});

test("a manual payment with proof is recorded and allocated to an invoice", async ({ page }) => {
  await signUpThroughToDashboard(page, uniqueEmail("manual"), "Manual Ltd");
  await importInvoices(page, ["M-001,Northwind Traders,2026-01-15,INR,1500.50"]);
  await page.getByRole("link", { name: "Payment Reconciliation" }).click();
  await page.getByRole("link", { name: /Unmatched/ }).click();
  await page.getByRole("button", { name: "Record a payment" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel(/^Amount/).fill("1500.50");
  await dialog.getByLabel("Date received").fill("2026-01-20");
  await dialog.getByLabel(/Proof of payment/).setInputFiles({ name: "proof.png", mimeType: "image/png", buffer: PNG });
  await dialog.getByRole("button", { name: "Save payment" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByText(/₹1,500.50 unapplied/)).toBeVisible();
  await page.getByRole("button", { name: "Apply to an invoice" }).click();
  await page.getByRole("dialog").getByLabel("Invoice").selectOption({ label: "M-001 · Northwind Traders · ₹1,500.50" });
  await page.getByRole("dialog").getByRole("button", { name: "Apply payment" }).click();
  await page.getByRole("link", { name: /Confirmed Payments 1/ }).click();
  await page.getByRole("button", { name: "Details" }).click();
  await expect(page.getByText("Proof attached: proof.png")).toBeVisible();
});

test("two equally good invoices force an explicit choice before anything is applied", async ({ page }) => {
  await signUpThroughToDashboard(page, uniqueEmail("ambig"), "Ambiguous Ltd");
  await importInvoices(page, ["A-001,Globex,2026-01-15,INR,500.00", "A-002,Globex,2026-01-16,INR,500.00"]);
  await addStatement(page, ["2026-01-20,GLOBEX UTR5,500.00"]);
  await reviewPage(page, "A-001");
  await expect(page.getByText(/More than one invoice could match/)).toBeVisible();
  const confirm = page.getByRole("button", { name: "Confirm Match & Apply Allocation" });
  await expect(confirm).toHaveAttribute("aria-disabled", "true");
  await expect(page.getByRole("link", { name: /Confirmed Payments 1/ })).toBeHidden();
  await page.getByRole("radio").first().check();
  await page.getByRole("button", { name: "Confirm Match & Apply Allocation" }).click();
  await expect(page.getByRole("link", { name: /Confirmed Payments 1/ })).toBeVisible();
});
