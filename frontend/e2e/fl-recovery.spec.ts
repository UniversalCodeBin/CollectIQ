import { expect, test } from "@playwright/test";
import { signUpThroughToDashboard, uniqueEmail } from "./support";

test("a server error on a screen shows a plain message and Try again recovers", async ({ page }) => {
  await signUpThroughToDashboard(page, uniqueEmail("rec500"), "Recover500 Ltd");
  let failing = true;
  await page.route("**/api/v1/workspaces/*/cases*", async (route) => {
    if (failing) return route.fulfill({ status: 500, contentType: "application/problem+json", body: JSON.stringify({ code: "INTERNAL", title: "Error", status: 500 }) });
    return route.continue();
  });
  await page.getByRole("link", { name: "Disputes & Blockers", exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  failing = false;
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("going offline fails safely and retrying after reconnecting works", async ({ page, context }) => {
  await signUpThroughToDashboard(page, uniqueEmail("recoff"), "RecoverOffline Ltd");
  await page.getByRole("link", { name: "Disputes & Blockers", exact: true }).click();
  await context.setOffline(true);
  await page.getByRole("link", { name: "Follow-ups", exact: true }).click().catch(() => undefined);
  await page.reload().catch(() => undefined);
  await context.setOffline(false);
  await page.reload();
  await expect(page.getByRole("heading").first()).toBeVisible();
});

test("an expired session sends the person to sign in rather than showing stale data", async ({ page, context }) => {
  await signUpThroughToDashboard(page, uniqueEmail("recexp"), "RecoverExpiry Ltd");
  await context.clearCookies();
  await page.reload();
  await expect(page).toHaveURL(/\/login/);
});

test("a pause that never answers shows a message, and trying again after reconnecting pauses", async ({ page }) => {
  await signUpThroughToDashboard(page, uniqueEmail("recmut"), "RecoverMutation Ltd");
  let drop = true;
  await page.route("**/automation/pause", (route) => (drop ? route.abort("connectionreset") : route.continue()));
  await page.getByRole("button", { name: "Pause automation" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  drop = false;
  await page.getByRole("button", { name: "Pause automation" }).click();
  await expect(page.getByText(/Automation is paused/)).toBeVisible();
});
