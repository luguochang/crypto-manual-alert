import {
  expect,
  test,
  type Browser,
  type BrowserContext,
  type Page,
  type TestInfo,
} from "@playwright/test";


const enabled = process.env.M4_SECURITY_E2E === "1";
const selectedProject = process.env.M4_SECURITY_PROJECT ?? "fixture-desktop";
const uuidPattern = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;

test.skip(!enabled, "set M4_SECURITY_E2E=1 with real OIDC storage states and dedicated tasks");
test.beforeEach(({}, testInfo) => {
  test.skip(
    testInfo.project.name !== selectedProject,
    `M4 security state is single-use; run only project ${selectedProject}`,
  );
});

interface ProductResponse {
  status: number;
  body: unknown;
}

interface Session {
  context: BrowserContext;
  page: Page;
  directAgentWrites: string[];
  serverErrors: string[];
}

test("real OIDC users can read only their own task, runs, and inbox", async ({ browser }, testInfo) => {
  const ownerTaskId = requiredUuid("M4_OWNER_READ_TASK_ID");
  const peerTaskId = requiredUuid("M4_SAME_TENANT_READ_TASK_ID");
  const crossTenantTaskId = requiredUuid("M4_CROSS_TENANT_READ_TASK_ID");
  const sessions = await createPrincipalSessions(browser, testInfo);

  try {
    const matrix = [
      { principal: "owner", session: sessions.owner, taskId: ownerTaskId },
      { principal: "same-tenant peer", session: sessions.peer, taskId: peerTaskId },
      { principal: "cross-tenant actor", session: sessions.crossTenant, taskId: crossTenantTaskId },
    ];
    for (const row of matrix) {
      const own = await productFetch(row.session.page, `/api/v2/tasks/${row.taskId}`);
      expect(own.status, `${row.principal} must read its own task`).toBe(200);
      expect(requiredRecord(own.body, "task").task_id).toBe(row.taskId);

      for (const foreignTaskId of [ownerTaskId, peerTaskId, crossTenantTaskId]) {
        if (foreignTaskId === row.taskId) continue;
        const denied = await productFetch(
          row.session.page,
          `/api/v2/tasks/${foreignTaskId}`,
        );
        expect(denied.status, `${row.principal} must not read ${foreignTaskId}`).toBe(404);
      }

      const runs = await productFetch(row.session.page, "/api/v2/runs?limit=100");
      const inbox = await productFetch(
        row.session.page,
        "/api/v2/inbox?status=all&limit=100",
      );
      expect(runs.status).toBe(200);
      expect(inbox.status).toBe(200);
      expect(itemTaskIds(runs.body)).toContain(row.taskId);
      expect(itemTaskIds(inbox.body)).toContain(row.taskId);
      for (const foreignTaskId of [ownerTaskId, peerTaskId, crossTenantTaskId]) {
        if (foreignTaskId === row.taskId) continue;
        expect(itemTaskIds(runs.body)).not.toContain(foreignTaskId);
        expect(itemTaskIds(inbox.body)).not.toContain(foreignTaskId);
      }
    }
    assertCleanBrowserBoundaries(Object.values(sessions));
  } finally {
    await closeSessions(Object.values(sessions));
  }
});

test("cross-scope writes are denied before owner respond, cancel, and fork admission", async ({
  browser,
}, testInfo) => {
  const reviewTaskId = requiredUuid("M4_OWNER_REVIEW_TASK_ID");
  const cancelTaskId = requiredUuid("M4_OWNER_CANCEL_TASK_ID");
  const forkTaskId = requiredUuid("M4_OWNER_FORK_TASK_ID");
  const forkBody = {
    source_run_id: requiredUuid("M4_OWNER_FORK_RUN_ID"),
    checkpoint_id: requiredEnv("M4_OWNER_FORK_CHECKPOINT_ID"),
  };
  const sessions = await createPrincipalSessions(browser, testInfo);

  try {
    const review = await productFetch(
      sessions.owner.page,
      `/api/v2/tasks/${reviewTaskId}`,
    );
    expect(review.status).toBe(200);
    const respondBody = buildRespondAllBody(review.body);

    for (const session of [sessions.peer, sessions.crossTenant]) {
      const respond = await productFetch(
        session.page,
        `/api/v2/tasks/${reviewTaskId}/interrupts/respond-all`,
        { method: "POST", body: respondBody, idempotencyKey: crypto.randomUUID() },
      );
      const cancel = await productFetch(
        session.page,
        `/api/v2/tasks/${cancelTaskId}/cancel`,
        { method: "POST", body: {}, idempotencyKey: crypto.randomUUID() },
      );
      const fork = await productFetch(
        session.page,
        `/api/v2/tasks/${forkTaskId}/fork`,
        { method: "POST", body: forkBody, idempotencyKey: crypto.randomUUID() },
      );
      expect(respond.status).toBe(404);
      expect(cancel.status).toBe(404);
      expect(fork.status).toBe(404);
    }

    const ownerRespond = await productFetch(
      sessions.owner.page,
      `/api/v2/tasks/${reviewTaskId}/interrupts/respond-all`,
      { method: "POST", body: respondBody, idempotencyKey: crypto.randomUUID() },
    );
    const ownerCancel = await productFetch(
      sessions.owner.page,
      `/api/v2/tasks/${cancelTaskId}/cancel`,
      { method: "POST", body: {}, idempotencyKey: crypto.randomUUID() },
    );
    const ownerFork = await productFetch(
      sessions.owner.page,
      `/api/v2/tasks/${forkTaskId}/fork`,
      { method: "POST", body: forkBody, idempotencyKey: crypto.randomUUID() },
    );
    expect(ownerRespond.status).toBe(202);
    expect(ownerCancel.status).toBe(202);
    // This is the executable M4 RED until Product fork admission exists.
    expect(ownerFork.status).toBe(202);
    expect(requiredRecord(ownerFork.body, "forked task").task_id).toBe(forkTaskId);
    assertCleanBrowserBoundaries(Object.values(sessions));
  } finally {
    await closeSessions(Object.values(sessions));
  }
});

test("a revoked member cannot keep writing from an already-open page", async ({ browser }, testInfo) => {
  const revokedTaskId = requiredUuid("M4_REVOKED_READ_TASK_ID");
  const revokedCancelTaskId = requiredUuid("M4_REVOKED_CANCEL_TASK_ID");
  const revokedReviewTaskId = requiredUuid("M4_REVOKED_REVIEW_TASK_ID");
  const session = await createSession(
    browser,
    testInfo,
    "M4_REVOKED_STORAGE_STATE",
  );

  try {
    const taskPath = `/api/product/api/v2/tasks/${revokedTaskId}`;
    const taskResponse = session.page.waitForResponse((response) =>
      new URL(response.url()).pathname === taskPath);
    await session.page.goto(`/work?task=${revokedTaskId}`);
    expect((await taskResponse).status()).toBe(403);
    await expect(session.page.getByRole("button", { name: "取消分析" })).toHaveCount(0);

    for (const path of [
      `/api/v2/tasks/${revokedTaskId}`,
      "/api/v2/runs?limit=100",
      "/api/v2/inbox?status=all&limit=100",
    ]) {
      expect((await productFetch(session.page, path)).status).toBe(403);
    }

    const revokedRespondBody = {
      pause_id: requiredUuid("M4_REVOKED_PAUSE_ID"),
      pause_version: requiredPositiveInteger("M4_REVOKED_PAUSE_VERSION"),
      responses: [{
        interrupt_id: requiredEnv("M4_REVOKED_INTERRUPT_ID"),
        response_version: requiredPositiveInteger("M4_REVOKED_RESPONSE_VERSION"),
        response: { action: "approve", comment: "must be rejected after revoke" },
      }],
    };
    const respond = await productFetch(
      session.page,
      `/api/v2/tasks/${revokedReviewTaskId}/interrupts/respond-all`,
      { method: "POST", body: revokedRespondBody, idempotencyKey: crypto.randomUUID() },
    );
    const cancel = await productFetch(
      session.page,
      `/api/v2/tasks/${revokedCancelTaskId}/cancel`,
      { method: "POST", body: {}, idempotencyKey: crypto.randomUUID() },
    );
    const fork = await productFetch(
      session.page,
      `/api/v2/tasks/${revokedTaskId}/fork`,
      {
        method: "POST",
        body: {
          source_run_id: requiredUuid("M4_REVOKED_FORK_RUN_ID"),
          checkpoint_id: requiredEnv("M4_REVOKED_FORK_CHECKPOINT_ID"),
        },
        idempotencyKey: crypto.randomUUID(),
      },
    );
    expect(respond.status).toBe(403);
    expect(cancel.status).toBe(403);
    expect(fork.status).toBe(403);
    assertCleanBrowserBoundaries([session]);
  } finally {
    await closeSessions([session]);
  }
});

async function createPrincipalSessions(browser: Browser, testInfo: TestInfo) {
  const [owner, peer, crossTenant] = await Promise.all([
    createSession(browser, testInfo, "M4_OWNER_STORAGE_STATE"),
    createSession(browser, testInfo, "M4_SAME_TENANT_STORAGE_STATE"),
    createSession(browser, testInfo, "M4_CROSS_TENANT_STORAGE_STATE"),
  ]);
  return { owner, peer, crossTenant };
}

async function createSession(
  browser: Browser,
  testInfo: TestInfo,
  storageStateEnvironment: string,
): Promise<Session> {
  const baseURL = String(
    testInfo.project.use.baseURL
      ?? process.env.PLAYWRIGHT_FRONTEND_BASE_URL
      ?? "",
  );
  if (!/^https:\/\//.test(baseURL)) {
    throw new Error("M4 security E2E requires a public HTTPS frontend baseURL");
  }
  const context = await browser.newContext({
    baseURL,
    storageState: requiredEnv(storageStateEnvironment),
  });
  const page = await context.newPage();
  const directAgentWrites: string[] = [];
  const serverErrors: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (
      url.pathname.startsWith("/api/agent/")
      && !["GET", "HEAD", "OPTIONS"].includes(request.method().toUpperCase())
    ) {
      directAgentWrites.push(`${request.method()} ${url.pathname}`);
    }
  });
  page.on("response", (response) => {
    if (response.status() >= 500) {
      serverErrors.push(`${response.status()} ${new URL(response.url()).pathname}`);
    }
  });
  await page.goto("/work");
  return { context, page, directAgentWrites, serverErrors };
}

async function productFetch(
  page: Page,
  path: string,
  options: Readonly<{
    method?: "GET" | "POST";
    body?: unknown;
    idempotencyKey?: string;
  }> = {},
): Promise<ProductResponse> {
  return page.evaluate(async ({ path, method, body, idempotencyKey }) => {
    const headers = new Headers({ accept: "application/json" });
    if (body !== undefined) headers.set("content-type", "application/json");
    if (idempotencyKey) headers.set("idempotency-key", idempotencyKey);
    const response = await fetch(`/api/product${path}`, {
      method: method ?? "GET",
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
      credentials: "same-origin",
    });
    const text = await response.text();
    let parsed: unknown = null;
    if (text) {
      try {
        parsed = JSON.parse(text);
      } catch {
        parsed = text;
      }
    }
    return { status: response.status, body: parsed };
  }, {
    path,
    method: options.method,
    body: options.body,
    idempotencyKey: options.idempotencyKey,
  });
}

function buildRespondAllBody(value: unknown) {
  const task = requiredRecord(value, "review task");
  const pause = requiredRecord(task.pending_interrupts, "pending interrupt pause");
  if (!Array.isArray(pause.members) || pause.members.length === 0) {
    throw new Error("M4_OWNER_REVIEW_TASK_ID must identify a waiting_human task");
  }
  return {
    pause_id: pause.pause_id,
    pause_version: pause.pause_version,
    responses: pause.members.map((candidate) => {
      const member = requiredRecord(candidate, "interrupt member");
      return {
        interrupt_id: member.interrupt_id,
        response_version: member.response_version,
        response: { action: "approve", comment: "M4 browser security gate" },
      };
    }),
  };
}

function itemTaskIds(value: unknown): string[] {
  const response = requiredRecord(value, "list response");
  if (!Array.isArray(response.items)) throw new Error("list response has no items array");
  return response.items.map((candidate) =>
    String(requiredRecord(candidate, "list item").task_id));
}

function requiredRecord(value: unknown, label: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function requiredEnv(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required for the M4 security E2E gate`);
  return value;
}

function requiredUuid(name: string): string {
  const value = requiredEnv(name);
  if (!uuidPattern.test(value)) throw new Error(`${name} must contain a UUID`);
  return value;
}

function requiredPositiveInteger(name: string): number {
  const value = Number(requiredEnv(name));
  if (!Number.isInteger(value) || value < 1) {
    throw new Error(`${name} must contain a positive integer`);
  }
  return value;
}

function assertCleanBrowserBoundaries(sessions: Session[]) {
  for (const session of sessions) {
    expect(session.directAgentWrites).toEqual([]);
    expect(session.serverErrors).toEqual([]);
  }
}

async function closeSessions(sessions: Session[]) {
  await Promise.all(sessions.map((session) => session.context.close()));
}
