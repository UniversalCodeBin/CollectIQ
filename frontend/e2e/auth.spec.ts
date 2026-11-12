import { expect, test } from "@playwright/test";
import { signUpThroughToDashboard, uniqueEmail } from "./support";

test("sign up, confirm by email, create a workspace and reach the dashboard", async ({ page }) => {
  await signUpThroughToDashboard(page, uniqueEmail("owner"), "Acme Studio");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByRole("banner")).toContainText("Acme Studio");
  await expect(page.getByRole("link", { name: "Dashboard" })).toBeVisible();
});

test("a logged-out visitor is sent to sign in and returned afterwards", async ({ page }) => {
  const address = uniqueEmail("back");
  const dashboard = await signUpThroughToDashboard(page, address, "Return Ltd");
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);

  await page.goto(dashboard);
  await expect(page).toHaveURL(/\/login\?next=/);
  await page.getByLabel("Email", { exact: true }).fill(address);
  await page.getByLabel("Password", { exact: true }).fill("correct horse battery");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(dashboard);
});

test("another workspace's URL shows the same page as an unknown one", async ({ page }) => {
  const first = await signUpThroughToDashboard(page, uniqueEmail("first"), "First Ltd");
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await signUpThroughToDashboard(page, uniqueEmail("second"), "Second Ltd");

  await page.goto(first);
  const heading = await page.getByRole("heading", { level: 1 }).innerText();
  await expect(page.getByText("First Ltd")).toHaveCount(0);

  await page.goto(first.replace(/\/w\/[0-9a-f-]{36}/, "/w/00000000-0000-4000-8000-000000000000"));
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(heading);
});
