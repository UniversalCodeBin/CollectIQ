import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { expect, type Page } from "@playwright/test";

const MAIL = path.resolve(import.meta.dirname, "../../var/e2e-mail");
export const PASSWORD = "correct horse battery"; // pragma: allowlist secret

export function uniqueEmail(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}@example.test`;
}

async function linkFor(address: string): Promise<string | null> {
  const names = await readdir(MAIL).catch(() => [] as string[]);
  for (const name of names) {
    const text = await readFile(path.join(MAIL, name), "utf-8");
    if (text.startsWith(`To: ${address}\n`)) return /http\S+token=\S+/.exec(text)?.[0] ?? null;
  }
  return null;
}

/** Waits for the worker to write the message, then returns the link inside it. */
export async function emailedLink(address: string): Promise<string> {
  await expect.poll(() => linkFor(address), { timeout: 30_000 }).not.toBeNull();
  return (await linkFor(address)) as string;
}

/** Sign up, confirm by the emailed link, sign in, create a workspace. Ends on the dashboard. */
export async function signUpThroughToDashboard(page: Page, address: string, business: string): Promise<string> {
  await page.goto("/signup");
  await page.getByLabel("Email").fill(address);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();

  await page.goto(await emailedLink(address));
  await page.getByRole("button", { name: "Confirm my email" }).click();
  await expect(page.getByRole("heading", { name: "Email confirmed" })).toBeVisible();
  await page.getByRole("link", { name: "Sign in" }).click();

  await page.getByLabel("Email").fill(address);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/onboarding\/workspace$/);

  await page.getByLabel("Business name").fill(business);
  await page.getByRole("button", { name: "Create workspace" }).click();
  await expect(page).toHaveURL(/\/w\/[0-9a-f-]{36}\/dashboard$/);
  return page.url();
}
