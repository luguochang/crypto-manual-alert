import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const frontendBaseUrl = process.env.PLAYWRIGHT_FRONTEND_BASE_URL ?? "http://127.0.0.1:3101";
const externalServer = process.env.PLAYWRIGHT_EXTERNAL_SERVER === "1";
const fixtureMatch = [
  "**/work-product.spec.ts",
  "**/runs-product.spec.ts",
  "**/notification-recovery.spec.ts",
  "**/research-evidence-disclosure.spec.ts",
  "**/background-deep-research.spec.ts",
];
const realProviderMatch = ["**/real-product-flow.spec.ts"];
const realMonitorMatch = ["**/real-monitor-flow.spec.ts"];
const realDataLifecycleMatch = ["**/real-data-lifecycle.spec.ts"];
const failureInjectionMatch = [
  "**/provider-failures.spec.ts",
  "**/database-rollback.spec.ts",
];
const profileMatches = {
  fixture: fixtureMatch,
  "real-provider": realProviderMatch,
  "failure-injection": failureInjectionMatch,
  "real-official-stream": ["**/official-stream-main-flow.spec.ts"],
  "real-cancel": ["**/durable-cancel-flow.spec.ts"],
  "real-hitl": ["**/hitl-review-flow.spec.ts"],
  "real-inbox": ["**/real-inbox-flow.spec.ts"],
  "real-library": ["**/real-library-run-detail.spec.ts"],
  "real-fork": ["**/real-fork-flow.spec.ts"],
  "real-multi-interrupt": ["**/real-multi-interrupt-flow.spec.ts"],
  "controlled-deep-research-hitl": ["**/deep-research-hitl-flow.spec.ts"],
  "real-deep-research": ["**/real-deep-research-flow.spec.ts"],
  "real-monitor": realMonitorMatch,
  "real-data-lifecycle": realDataLifecycleMatch,
  "m4-security": ["**/cross-tenant-security.spec.ts"],
} satisfies Record<string, string[]>;

type E2EProfile = keyof typeof profileMatches;

const requiredEnvironment: Partial<Record<E2EProfile, readonly string[]>> = {
  "real-provider": ["REAL_PRODUCT_E2E"],
  "failure-injection": [
    "FAILURE_INJECTION_ENABLED",
    "FAILURE_INJECTION_CONTROL_TOKEN",
  ],
  "real-official-stream": ["REAL_PRODUCT_E2E"],
  "real-cancel": ["REAL_PRODUCT_E2E"],
  "real-hitl": [
    "REAL_PRODUCT_E2E",
    "HITL_TASK_ID_DESKTOP",
    "HITL_TASK_ID_MOBILE",
  ],
  "real-inbox": ["REAL_PRODUCT_E2E", "REAL_INBOX_TASK_ID"],
  "real-library": ["REAL_LIBRARY_E2E"],
  "real-fork": [
    "REAL_FORK_E2E",
    "REAL_FORK_TASK_ID_DESKTOP",
    "REAL_FORK_SOURCE_RUN_ID_DESKTOP",
    "REAL_FORK_TASK_ID_MOBILE",
    "REAL_FORK_SOURCE_RUN_ID_MOBILE",
  ],
  "real-multi-interrupt": ["REAL_MULTI_INTERRUPT_E2E"],
  "controlled-deep-research-hitl": [
    "REAL_PRODUCT_E2E",
    "CONTROLLED_DEEP_RESEARCH_HITL_E2E",
    "DEEP_RESEARCH_HITL_TASK_ID_DESKTOP",
    "DEEP_RESEARCH_HITL_TASK_ID_MOBILE",
  ],
  "real-deep-research": [
    "REAL_PRODUCT_E2E",
    "REAL_DEEP_RESEARCH_E2E",
    "PLAYWRIGHT_EVIDENCE_DIR",
  ],
  "real-monitor": ["REAL_MONITOR_E2E", "PLAYWRIGHT_EVIDENCE_DIR"],
  "real-data-lifecycle": [
    "REAL_DATA_LIFECYCLE_E2E",
    "PLAYWRIGHT_EVIDENCE_DIR",
    "DATA_LIFECYCLE_E2E_ISOLATED_DATABASE",
    "DATA_LIFECYCLE_E2E_ISOLATION_CONFIRMATION",
    "DATA_LIFECYCLE_E2E_EXPECTED_TENANT_ID",
    "DATA_LIFECYCLE_E2E_EXPECTED_WORKSPACE_ID",
    "DATA_LIFECYCLE_E2E_EXPECTED_OWNER_USER_ID",
  ],
  "m4-security": ["M4_SECURITY_E2E"],
};

const booleanEnvironment = new Set([
  "REAL_PRODUCT_E2E",
  "FAILURE_INJECTION_ENABLED",
  "REAL_LIBRARY_E2E",
  "REAL_FORK_E2E",
  "REAL_MULTI_INTERRUPT_E2E",
  "CONTROLLED_DEEP_RESEARCH_HITL_E2E",
  "REAL_DEEP_RESEARCH_E2E",
  "REAL_MONITOR_E2E",
  "REAL_DATA_LIFECYCLE_E2E",
  "DATA_LIFECYCLE_E2E_ISOLATED_DATABASE",
  "M4_SECURITY_E2E",
]);

const selectedProfile = process.env.V2_E2E_PROFILE ?? "fixture";
if (!Object.hasOwn(profileMatches, selectedProfile)) {
  throw new Error(`Unsupported V2_E2E_PROFILE: ${selectedProfile}`);
}
const profile = selectedProfile as E2EProfile;
const evidenceDirectory = process.env.PLAYWRIGHT_EVIDENCE_DIR?.trim();
const missingEnvironment = (requiredEnvironment[profile] ?? []).filter(
  (name) => booleanEnvironment.has(name)
    ? process.env[name] !== "1"
    : !process.env[name]?.trim(),
);
if (missingEnvironment.length > 0) {
  throw new Error(
    `V2_E2E_PROFILE=${profile} requires ${missingEnvironment.join(", ")}`,
  );
}
const profilesRequiringAbsoluteEvidence = new Set<E2EProfile>([
  "real-deep-research",
  "real-monitor",
  "real-data-lifecycle",
]);
if (
  profilesRequiringAbsoluteEvidence.has(profile)
  && (!evidenceDirectory || !path.isAbsolute(evidenceDirectory))
) {
  throw new Error(
    `V2_E2E_PROFILE=${profile} requires an absolute PLAYWRIGHT_EVIDENCE_DIR`,
  );
}

const fixtureNamedProjects = [
  {
    name: "fixture-desktop",
    testMatch: profileMatches[profile],
    use: {
      ...devices["Desktop Chrome"],
      viewport: { width: 1440, height: 1000 },
    },
  },
  {
    name: "fixture-pixel-7",
    testMatch: profileMatches[profile],
    use: {
      ...devices["Pixel 7"],
      viewport: { width: 412, height: 915 },
    },
  },
];

const projects = profile === "real-provider"
  ? [
      {
        name: "real-provider-desktop",
        testMatch: realProviderMatch,
        use: {
          ...devices["Desktop Chrome"],
          viewport: { width: 1440, height: 1000 },
        },
      },
      {
        name: "real-provider-pixel-7",
        testMatch: realProviderMatch,
        use: {
          ...devices["Pixel 7"],
          viewport: { width: 412, height: 915 },
        },
      },
    ]
  : profile === "failure-injection"
    ? [
        {
          name: "failure-injection-desktop",
          testMatch: failureInjectionMatch,
          use: {
            ...devices["Desktop Chrome"],
            viewport: { width: 1440, height: 1000 },
          },
        },
        {
          name: "failure-injection-pixel-7",
          testMatch: failureInjectionMatch,
          use: {
            ...devices["Pixel 7"],
            viewport: { width: 412, height: 915 },
          },
        },
      ]
    : profile === "real-monitor"
      ? [
          {
            name: "real-monitor-desktop",
            testMatch: realMonitorMatch,
            use: {
              ...devices["Desktop Chrome"],
              viewport: { width: 1440, height: 1000 },
            },
          },
          {
            name: "real-monitor-pixel-7",
            testMatch: realMonitorMatch,
            use: {
              ...devices["Pixel 7"],
              viewport: { width: 412, height: 915 },
            },
          },
        ]
    : profile === "real-data-lifecycle"
      ? [
          {
            name: "real-data-lifecycle-desktop",
            testMatch: realDataLifecycleMatch,
            use: {
              ...devices["Desktop Chrome"],
              viewport: { width: 1440, height: 1000 },
            },
          },
          {
            name: "real-data-lifecycle-pixel-7",
            testMatch: realDataLifecycleMatch,
            use: {
              ...devices["Pixel 7"],
              viewport: { width: 412, height: 915 },
            },
          },
        ]
      : fixtureNamedProjects;

export default defineConfig({
  testDir: "./tests/e2e-v2",
  outputDir: evidenceDirectory
    ? path.join(evidenceDirectory, "test-results")
    : "./test-results",
  timeout: 45_000,
  workers: 1,
  fullyParallel: false,
  forbidOnly: true,
  reporter: evidenceDirectory
    ? [
        ["list"],
        ["html", { open: "never", outputFolder: path.join(evidenceDirectory, "html") }],
        ["junit", { outputFile: path.join(evidenceDirectory, "junit.xml") }],
        ["json", { outputFile: path.join(evidenceDirectory, "results.json") }],
      ]
    : [["list"], ["html", { open: "never" }]],
  expect: {
    timeout: 8_000,
  },
  use: {
    baseURL: frontendBaseUrl,
    trace: evidenceDirectory ? "on" : "retain-on-failure",
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
  projects,
});
