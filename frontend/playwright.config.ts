import { defineConfig, devices } from "@playwright/test";

const frontendBaseUrl = process.env.PLAYWRIGHT_FRONTEND_BASE_URL ?? "http://127.0.0.1:3101";
const externalServer = process.env.PLAYWRIGHT_EXTERNAL_SERVER === "1";

export default defineConfig({
  testDir: "./tests/e2e-v2",
  outputDir: "./test-results",
  timeout: 45_000,
  workers: 1,
  fullyParallel: false,
  forbidOnly: true,
  reporter: [["list"], ["html", { open: "never" }]],
  expect: {
    timeout: 8_000,
  },
  use: {
    baseURL: frontendBaseUrl,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: externalServer
    ? undefined
    : {
        command: "npm run dev -- --hostname 127.0.0.1 --port 3101",
        url: frontendBaseUrl,
        reuseExistingServer: false,
        timeout: 120_000,
        stdout: "pipe",
        stderr: "pipe",
      },
  projects: [
    {
      name: "fixture-desktop",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 1000 },
      },
    },
    {
      name: "fixture-pixel-7",
      use: {
        ...devices["Pixel 7"],
        viewport: { width: 412, height: 915 },
      },
    },
  ],
});
