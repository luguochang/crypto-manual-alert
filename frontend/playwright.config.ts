import { defineConfig, devices } from "@playwright/test";

const explicitFrontendBaseUrl = process.env.PLAYWRIGHT_FRONTEND_BASE_URL;
const explicitApiBaseUrl = process.env.PLAYWRIGHT_API_BASE_URL;
const frontendBaseUrl = explicitFrontendBaseUrl ?? "http://127.0.0.1:3001";
const reuseExistingStack = process.env.PLAYWRIGHT_REUSE_EXISTING_STACK === "true";
const expectHostedProdActionable = process.env.PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE === "true";
const localStackFlags = process.env.PLAYWRIGHT_LOCAL_STACK_FLAGS ?? "--seed-mock-outcome";

if (expectHostedProdActionable && !reuseExistingStack) {
  throw new Error(
    "PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true requires PLAYWRIGHT_REUSE_EXISTING_STACK=true"
  );
}

if (expectHostedProdActionable && !explicitFrontendBaseUrl) {
  throw new Error(
    "PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true requires PLAYWRIGHT_FRONTEND_BASE_URL"
  );
}

if (expectHostedProdActionable && !explicitApiBaseUrl) {
  throw new Error(
    "PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true requires PLAYWRIGHT_API_BASE_URL"
  );
}

if (expectHostedProdActionable) {
  assertPublicHttpsBaseUrl(
    explicitFrontendBaseUrl,
    "PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true requires PLAYWRIGHT_FRONTEND_BASE_URL to be a public HTTPS URL"
  );
  assertPublicHttpsBaseUrl(
    explicitApiBaseUrl,
    "PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true requires PLAYWRIGHT_API_BASE_URL to be a public HTTPS URL"
  );
}

export default defineConfig({
  testDir: "./tests/e2e",
  outputDir: "./test-results",
  timeout: 60_000,
  // These E2E specs share one API/frontend stack and mutate the same SQLite
  // journal through manual-run submissions. Keep them serial unless each
  // project gets isolated ports/data directories.
  workers: 1,
  expect: {
    timeout: 10_000,
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.02
    }
  },
  fullyParallel: false,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: frontendBaseUrl,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure"
  },
  webServer: expectHostedProdActionable ? undefined : {
    command: `cd .. && python3 tools/local_stack/stop_local_stack.py --force-ports --kill-any-listener && python3 tools/local_stack/start_local_stack.py --frontend-mode production --reset-data ${localStackFlags} --keep-running`,
    url: frontendBaseUrl,
    reuseExistingServer: reuseExistingStack,
    timeout: 120_000,
    stdout: "pipe",
    stderr: "pipe"
  },
  globalTeardown: "./tests/e2e/global-teardown.ts",
  projects: [
    {
      name: "chromium-desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1000 } }
    },
    {
      name: "chromium-mobile",
      use: { ...devices["Pixel 7"], viewport: { width: 412, height: 915 } }
    }
  ]
});

function assertPublicHttpsBaseUrl(value: string | undefined, message: string) {
  if (!value) {
    throw new Error(message);
  }
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error(message);
  }
  if (parsed.protocol !== "https:" || isLocalOrPrivateHostname(parsed.hostname)) {
    throw new Error(message);
  }
}

function isLocalOrPrivateHostname(hostname: string) {
  const normalized = hostname.trim().toLowerCase().replace(/^\[/, "").replace(/\]$/, "").replace(/\.$/, "");
  if (!normalized || normalized === "localhost" || normalized.endsWith(".localhost")) {
    return true;
  }
  if (normalized === "0.0.0.0" || normalized === "::1" || normalized === "0:0:0:0:0:0:0:1") {
    return true;
  }
  const ipv4 = normalized.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (!ipv4) {
    return false;
  }
  const octets = ipv4.slice(1).map((part) => Number(part));
  if (octets.some((part) => !Number.isInteger(part) || part < 0 || part > 255)) {
    return true;
  }
  const [first, second] = octets;
  return (
    first === 0 ||
    first === 10 ||
    first === 127 ||
    (first === 169 && second === 254) ||
    (first === 172 && second >= 16 && second <= 31) ||
    (first === 192 && second === 168)
  );
}
