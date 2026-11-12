import { execFile } from "node:child_process";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { expect, type Page } from "@playwright/test";

const MAIL_DIRS = [
  path.resolve(import.meta.dirname, "../../var/e2e-mail"),
  path.resolve(import.meta.dirname, "../../var/mail"),
];
export const PASSWORD = "correct horse battery"; // pragma: allowlist secret

export function uniqueEmail(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}@example.test`;
}

async function linkFor(address: string): Promise<string | null> {
  for (const mailDir of MAIL_DIRS) {
    const names = await readdir(mailDir).catch(() => [] as string[]);
    for (const name of names) {
      const text = await readFile(path.join(mailDir, name), "utf-8");
      if (text.startsWith(`To: ${address}\n`)) return /http\S+token=\S+/.exec(text)?.[0] ?? null;
    }
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
  await page.getByLabel("Email", { exact: true }).fill(address);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();

  const link = await emailedLink(address);
  try {
    const parsed = new URL(link);
    await page.goto(parsed.pathname + parsed.search);
  } catch {
    await page.goto(link);
  }
  await page.getByRole("button", { name: "Confirm my email" }).click();
  await expect(page.getByRole("heading", { name: "Email confirmed" })).toBeVisible();
  await page.getByRole("link", { name: "Sign in" }).click();

  await page.getByLabel("Email", { exact: true }).fill(address);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/onboarding\/workspace$/);

  await page.getByLabel("Business name").fill(business);
  await page.getByRole("button", { name: "Create workspace" }).click();
  await expect(page).toHaveURL(/\/w\/[0-9a-f-]{36}\/dashboard$/);
  return page.url();
}

/**
 * Test-only: gives every client in the workspace an active contact and marks its invoices as supported by
 * evidence. The app has no screen for either yet, and a draft needs both. Runs as the database owner against
 * the e2e run's own database (see env.sh) with the workspace set, so row security still applies; it never goes through the app.
 */
export async function seedDraftPrerequisites(page: Page): Promise<void> {
  const workspace = /\/w\/([0-9a-f-]{36})\//.exec(page.url())?.[1];
  if (!workspace) throw new Error(`not inside a workspace: ${page.url()}`);
  const script = `
import os, psycopg
with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as db:
    ws = os.environ["SEED_WORKSPACE"]
    db.execute("SELECT set_config('app.workspace_id', %s, true)", [ws])
    db.execute(
        "INSERT INTO client_contacts (workspace_id, client_id, email, name) "
        "SELECT workspace_id, id, 'ap@seeded.example.test', 'Accounts' FROM clients WHERE workspace_id = %s "
        "ON CONFLICT DO NOTHING",
        [ws],
    )
    db.execute("UPDATE invoice_state SET evidence_coverage = 'SUPPORTED' WHERE workspace_id = %s", [ws])
`;
  const root = path.resolve(import.meta.dirname, "../..");
  await new Promise<void>((resolve, reject) => {
    execFile(
      "bash",
      ["-c", '. frontend/e2e/env.sh; cd backend && uv run python -c "$SEED_SCRIPT"'],
      { cwd: root, env: { ...process.env, SEED_SCRIPT: script, SEED_WORKSPACE: workspace } },
      (error, _out, stderr) => (error ? reject(new Error(stderr || String(error))) : resolve()),
    );
  });
}
