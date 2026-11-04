import { defineConfig, devices } from "@playwright/test";

const WEB = "http://127.0.0.1:5183";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  forbidOnly: true,
  retries: 0,
  reporter: [["line"]],
  use: { baseURL: WEB, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    { command: "bash e2e/serve.sh api", url: "http://127.0.0.1:8100/api/v1/health/live", reuseExistingServer: false, timeout: 120_000 },
    // No URL: the worker serves nothing, and sharing the API's URL would count it as already running.
    { command: "bash e2e/serve.sh worker" },
    {
      command: "npx vite --host 127.0.0.1 --port 5183 --strictPort",
      url: WEB,
      env: { API_PROXY: "http://127.0.0.1:8100" },
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
