import { defineConfig, devices } from "@playwright/test";

// End-to-end tests run the production build against the synthetic fixture (e2e/backend.sh).
// No test here talks to a real provider or to the development database.
const API = "http://127.0.0.1:8770";
const WEB = "http://127.0.0.1:3100";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: { baseURL: WEB, trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
  webServer: [
    {
      command: "bash e2e/backend.sh",
      url: `${API}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      stdout: "ignore",
      stderr: "pipe",
    },
    {
      command: "npm run build && npm run start -- --hostname 127.0.0.1 --port 3100",
      url: WEB,
      env: { SCOUT_API_URL: API },
      reuseExistingServer: !process.env.CI,
      timeout: 300_000,
    },
  ],
});
