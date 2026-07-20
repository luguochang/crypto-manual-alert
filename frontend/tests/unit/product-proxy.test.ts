import { generateKeyPairSync } from "node:crypto";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { proxyProductRequest } from "../../src/lib/api/product-proxy";

describe("Product BFF proxy", () => {
  afterEach(() => {
    delete process.env.PRODUCT_API_BASE_URL;
    delete process.env.PRODUCT_API_TIMEOUT_MS;
    delete process.env.APP_ENVIRONMENT;
    delete process.env.DEVELOPMENT_BOOTSTRAP_ENABLED;
    delete process.env.DEVELOPMENT_BOOTSTRAP_PERMISSIONS;
    delete process.env.DEVELOPMENT_BOOTSTRAP_PROFILE;
    delete process.env.DEVELOPMENT_BOOTSTRAP_ROLES;
    delete process.env.DEVELOPMENT_BOOTSTRAP_SUBJECT;
    delete process.env.DEVELOPMENT_BOOTSTRAP_IDENTITY_ISSUER;
    delete process.env.DEVELOPMENT_BOOTSTRAP_CONTEXT_ID;
    delete process.env.DEVELOPMENT_BOOTSTRAP_TENANT_ID;
    delete process.env.DEVELOPMENT_BOOTSTRAP_WORKSPACE_ID;
    delete process.env.AGENT_SERVER_INTERNAL_JWT_AUDIENCE;
    delete process.env.AGENT_SERVER_LOCAL_TOKEN;
    delete process.env.FAILURE_INJECTION_ENABLED;
    delete process.env.V2_E2E_PROFILE;
    delete process.env.INTERNAL_JWT_AUDIENCE;
    delete process.env.INTERNAL_JWT_ISSUER;
    delete process.env.INTERNAL_JWT_KID;
    delete process.env.INTERNAL_JWT_PRIVATE_KEY;
    vi.unstubAllEnvs();
  });

  it("uses identity discovery authority for Compose context routes", async () => {
    const { privateKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
    process.env.APP_ENVIRONMENT = "development";
    process.env.DEVELOPMENT_BOOTSTRAP_ENABLED = "true";
    process.env.DEVELOPMENT_BOOTSTRAP_PROFILE = "local-proof";
    process.env.DEVELOPMENT_BOOTSTRAP_SUBJECT = "dev-user";
    process.env.DEVELOPMENT_BOOTSTRAP_IDENTITY_ISSUER = "crypto-alert-v2-compose";
    process.env.DEVELOPMENT_BOOTSTRAP_CONTEXT_ID = "99999999-9999-4999-8999-999999999999";
    process.env.INTERNAL_JWT_PRIVATE_KEY = privateKey
      .export({ type: "pkcs8", format: "pem" })
      .toString();
    process.env.INTERNAL_JWT_KID = "compose-ephemeral";
    process.env.INTERNAL_JWT_ISSUER = "crypto-alert-v2-compose";
    process.env.PRODUCT_API_BASE_URL = "http://langgraph-api:8000/app";
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return Response.json({ items: [] });
    });

    const response = await proxyProductRequest(
      new Request("http://frontend:3001/api/product/api/v2/auth/contexts"),
      ["api", "v2", "auth", "contexts"],
      fetcher,
    );

    expect(response.status).toBe(200);
    const authorization = new Headers(fetcher.mock.calls[0]?.[1]?.headers)
      .get("authorization") ?? "";
    const payload = JSON.parse(
      Buffer.from(authorization.replace(/^Bearer [^.]+\./, "").split(".")[0] ?? "", "base64url")
        .toString("utf8"),
    ) as Record<string, unknown>;
    expect(payload).toMatchObject({
      aud: "crypto-alert-identity-discovery",
      token_use: "identity_discovery",
    });
    expect(payload).not.toHaveProperty("context_id");
  });

  it("forwards the failure control token only to the exact local test route", async () => {
    process.env.APP_ENVIRONMENT = "test";
    process.env.V2_E2E_PROFILE = "failure-injection";
    process.env.FAILURE_INJECTION_ENABLED = "1";
    const fetcher = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) => {
        void _input;
        void _init;
        return Response.json({ generation: "g1", scenario: "none" });
      },
    );
    const request = new Request(
      "http://127.0.0.1:3001/api/product/api/v2/testing/failure-scenario",
      {
        headers: {
          "x-failure-injection-control-token": "ephemeral-control-token",
          "x-failure-injection-generation": "generation-1",
        },
      },
    );

    const response = await proxyProductRequest(
      request,
      ["api", "v2", "testing", "failure-scenario"],
      fetcher,
    );

    expect(response.status).toBe(200);
    expect(new Headers(fetcher.mock.calls[0]?.[1]?.headers).get(
      "x-failure-injection-control-token",
    )).toBe("ephemeral-control-token");
    expect(new Headers(fetcher.mock.calls[0]?.[1]?.headers).get(
      "x-failure-injection-generation",
    )).toBeNull();

    fetcher.mockClear();
    const resetRequest = new Request(
      "http://127.0.0.1:3001/api/product/api/v2/testing/failure-scenario",
      {
        method: "DELETE",
        headers: {
          "x-failure-injection-control-token": "ephemeral-control-token",
          "x-failure-injection-generation": "generation-1",
        },
      },
    );
    await proxyProductRequest(
      resetRequest,
      ["api", "v2", "testing", "failure-scenario"],
      fetcher,
    );
    expect(new Headers(fetcher.mock.calls[0]?.[1]?.headers).get(
      "x-failure-injection-generation",
    )).toBe("generation-1");
  });

  it("injects the local Agent token only for a development loopback upstream", async () => {
    process.env.APP_ENVIRONMENT = "development";
    process.env.AGENT_SERVER_LOCAL_TOKEN = "server-owned-local-token";
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return Response.json(taskProjection("queued"), { status: 202 });
    });

    const response = await proxyProductRequest(
      new Request("http://127.0.0.1:3001/api/product/api/v2/analysis", {
        method: "POST",
        headers: { authorization: "Bearer browser-forgery" },
        body: "{}",
      }),
      ["api", "v2", "analysis"],
      fetcher,
    );

    expect(response.status).toBe(202);
    const authorization = new Headers(fetcher.mock.calls[0]?.[1]?.headers)
      .get("authorization");
    expect(authorization).toBe("Bearer server-owned-local-token");
  });

  it("forwards the actor-scoped data lifecycle routes and preserves idempotency", async () => {
    process.env.APP_ENVIRONMENT = "development";
    process.env.PRODUCT_API_BASE_URL = "http://127.0.0.1:8125/app";
    process.env.AGENT_SERVER_LOCAL_TOKEN = "server-owned-local-token";
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return Response.json({ status: "queued" }, { status: 202 });
    });
    const exportId = "11111111-1111-4111-8111-111111111111";

    const response = await proxyProductRequest(
      new Request("http://127.0.0.1:3001/api/product/api/v2/data-lifecycle/exports", {
        method: "POST",
        headers: { "idempotency-key": "export-route-1" },
        body: JSON.stringify({ scope: "user_data" }),
      }),
      ["api", "v2", "data-lifecycle", "exports"],
      fetcher,
    );

    expect(response.status).toBe(202);
    expect(fetcher.mock.calls[0]?.[0]).toBe(
      "http://127.0.0.1:8125/app/api/v2/data-lifecycle/exports",
    );
    expect(new Headers(fetcher.mock.calls[0]?.[1]?.headers).get("idempotency-key"))
      .toBe("export-route-1");

    await proxyProductRequest(
      new Request("http://127.0.0.1:3001/api/product/api/v2/data-lifecycle/exports"),
      ["api", "v2", "data-lifecycle", "exports", exportId, "manifest"],
      fetcher,
    );
    expect(fetcher.mock.calls[1]?.[0]).toContain(`/exports/${exportId}/manifest`);
  });

  it("preserves the local Agent Server app base path and strips browser authority headers", async () => {
    const fetcher = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        void input;
        void init;
        return Response.json(taskProjection("queued"), {
          status: 202,
          headers: { "x-upstream-request-id": "upstream-1" },
        });
      },
    );
    const request = new Request("http://127.0.0.1:3101/api/product/api/v2/analysis", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "idempotency-key": "analysis-admission-1",
        "x-request-id": "browser-transport-1",
        "x-correlation-id": "client-owned-correlation",
        authorization: "Bearer browser-forgery",
        "x-api-key": "browser-secret",
        "x-tenant-id": "attacker",
      },
      body: JSON.stringify({ symbol: "BTC-USDT-SWAP" }),
    });

    const response = await proxyProductRequest(
      request,
      ["api", "v2", "analysis"],
      fetcher,
    );

    expect(response.status).toBe(202);
    expect(fetcher).toHaveBeenCalledOnce();
    const [upstreamUrl, upstreamInit] = fetcher.mock.calls[0] ?? [];
    expect(upstreamUrl).toBe("http://127.0.0.1:8123/app/api/v2/analysis");
    const headers = new Headers(upstreamInit?.headers);
    expect(headers.get("authorization")).toBeNull();
    expect(headers.get("x-api-key")).toBeNull();
    expect(headers.get("x-tenant-id")).toBeNull();
    expect(headers.get("content-type")).toBe("application/json");
    expect(headers.get("idempotency-key")).toBe("analysis-admission-1");
    const requestId = headers.get("x-request-id");
    expect(requestId).toMatch(/^[0-9a-f-]{36}$/i);
    expect(requestId).not.toBe("browser-transport-1");
    expect(headers.get("x-correlation-id")).toBeNull();
    expect(response.headers.get("x-request-id")).toBe(requestId);
  });

  it("allows the exact Deep Research Product admission route", async () => {
    const fetcher = vi.fn(async (
      input: RequestInfo | URL,
      init?: RequestInit,
    ) => {
      void input;
      void init;
      return Response.json(taskProjection("queued"), { status: 202 });
    });
    const request = new Request(
      "http://127.0.0.1:3101/api/product/api/v2/deep-research",
      {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "idempotency-key": "deep-research-admission-1",
        },
        body: JSON.stringify({
          task_type: "deep_research",
          symbol: "BTC-USDT-SWAP",
          horizon: "7d",
          query_text: "Research BTC adoption.",
        }),
      },
    );

    const response = await proxyProductRequest(
      request,
      ["api", "v2", "deep-research"],
      fetcher,
    );

    expect(response.status).toBe(202);
    expect(fetcher.mock.calls[0]?.[0]).toBe(
      "http://127.0.0.1:8123/app/api/v2/deep-research",
    );
    expect(new Headers(fetcher.mock.calls[0]?.[1]?.headers).get("idempotency-key"))
      .toBe("deep-research-admission-1");
  });

  it("generates one transport request ID and returns it when upstream is unavailable", async () => {
    const fetcher = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => {
      void _input;
      void _init;
      throw new Error("upstream unavailable");
    });

    const response = await proxyProductRequest(
      new Request("http://127.0.0.1:3101/api/product/api/v2/health"),
      ["api", "v2", "health"],
      fetcher,
    );

    expect(response.status).toBe(502);
    const requestHeaders = new Headers(fetcher.mock.calls[0]?.[1]?.headers);
    const requestId = requestHeaders.get("x-request-id");
    expect(requestId).toMatch(/^[0-9a-f-]{36}$/i);
    expect(response.headers.get("x-request-id")).toBe(requestId);
  });

  it("aborts a hung Product upstream within the server-owned deadline", async () => {
    process.env.PRODUCT_API_TIMEOUT_MS = "100";
    let upstreamSignal: AbortSignal | undefined;
    const fetcher = vi.fn(
      async (_input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
        upstreamSignal = init?.signal ?? undefined;
        return await new Promise<Response>((_resolve, reject) => {
          const rejectAborted = () => reject(upstreamSignal?.reason);
          if (upstreamSignal?.aborted) rejectAborted();
          else upstreamSignal?.addEventListener("abort", rejectAborted, { once: true });
        });
      },
    );
    const startedAt = Date.now();

    const response = await proxyProductRequest(
      new Request("http://127.0.0.1:3101/api/product/api/v2/readiness"),
      ["api", "v2", "readiness"],
      fetcher,
    );

    expect(response.status).toBe(502);
    expect(upstreamSignal?.aborted).toBe(true);
    expect(Date.now() - startedAt).toBeLessThan(1_000);
    await expect(response.json()).resolves.toEqual({
      detail: "Product API is temporarily unavailable.",
    });
  });

  it("uses the local server token instead of bootstrap authority fields", async () => {
    process.env.APP_ENVIRONMENT = "development";
    process.env.AGENT_SERVER_LOCAL_TOKEN = "local-product-token";
    process.env.DEVELOPMENT_BOOTSTRAP_ENABLED = "true";
    process.env.DEVELOPMENT_BOOTSTRAP_PROFILE = "local-proof";
    process.env.DEVELOPMENT_BOOTSTRAP_SUBJECT = "compose-user";
    process.env.DEVELOPMENT_BOOTSTRAP_TENANT_ID = "compose-tenant";
    process.env.DEVELOPMENT_BOOTSTRAP_WORKSPACE_ID = "compose-workspace";
    process.env.DEVELOPMENT_BOOTSTRAP_ROLES = '["member"]';
    process.env.DEVELOPMENT_BOOTSTRAP_PERMISSIONS = '["analysis:read"]';
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return Response.json(taskProjection("queued"), { status: 202 });
    });

    const response = await proxyProductRequest(
      new Request("http://0.0.0.0:3001/api/product/api/v2/analysis", {
        method: "POST",
        body: "{}",
      }),
      ["api", "v2", "analysis"],
      fetcher,
    );

    expect(response.status).toBe(202);
    const authorization = new Headers(fetcher.mock.calls[0]?.[1]?.headers)
      .get("authorization") ?? "";
    expect(authorization).toBe("Bearer local-product-token");
  });

  it.each([
    ["GET", ["api", "v2", "tasks", "00000000-0000-0000-0000-000000000001"], "analysis-admission-1"],
    ["POST", ["api", "v2", "analysis"], "contains spaces"],
    ["POST", ["api", "v2", "analysis"], "x".repeat(256)],
  ])("does not forward an unsupported idempotency key", async (method, path, key) => {
    const fetcher = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        void input;
        void init;
        return Response.json(taskProjection("queued"), { status: 202 });
      },
    );
    const response = await proxyProductRequest(
      new Request(`http://127.0.0.1:3101/api/product/${path.join("/")}`, {
        method,
        headers: { "idempotency-key": key },
        body: method === "POST" ? "{}" : undefined,
      }),
      path,
      fetcher,
    );

    expect(response.status).toBe(202);
    const headers = new Headers(fetcher.mock.calls[0]?.[1]?.headers);
    expect(headers.get("idempotency-key")).toBeNull();
  });

  it("honors a server environment override and returns a readable gateway failure", async () => {
    process.env.PRODUCT_API_BASE_URL = "http://127.0.0.1:8999/app/";
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      throw new Error("upstream included secret model-key-123");
    });

    const response = await proxyProductRequest(
      new Request("http://127.0.0.1:3101/api/product/api/v2/tasks/00000000-0000-0000-0000-000000000001"),
      ["api", "v2", "tasks", "00000000-0000-0000-0000-000000000001"],
      fetcher,
    );

    expect(fetcher).toHaveBeenCalledWith(
      "http://127.0.0.1:8999/app/api/v2/tasks/00000000-0000-0000-0000-000000000001",
      expect.any(Object),
    );
    expect(response.status).toBe(502);
    await expect(response.json()).resolves.toEqual({
      detail: "Product API is temporarily unavailable.",
    });
  });

  it("allows only a bounded Product Run list read and preserves its query", async () => {
    const fetcher = vi.fn(async () => Response.json({ items: [], limit: 25 }));
    const response = await proxyProductRequest(
      new Request("http://127.0.0.1:3101/api/product/api/v2/runs?limit=25"),
      ["api", "v2", "runs"],
      fetcher,
    );

    expect(response.status).toBe(200);
    expect(fetcher).toHaveBeenCalledWith(
      "http://127.0.0.1:8123/app/api/v2/runs?limit=25",
      expect.objectContaining({ method: "GET" }),
    );

    const rejected = await proxyProductRequest(
      new Request("http://127.0.0.1:3101/api/product/api/v2/runs", { method: "POST" }),
      ["api", "v2", "runs"],
      fetcher,
    );
    expect(rejected.status).toBe(404);
  });

  it("allows Home reads and only supported owner-scoped watchlist mutations", async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return Response.json({ watchlist: [] });
    });
    const homeResponse = await proxyProductRequest(
      new Request("http://127.0.0.1:3101/api/product/api/v2/home"),
      ["api", "v2", "home"],
      fetcher,
    );
    const addResponse = await proxyProductRequest(
      new Request("http://127.0.0.1:3101/api/product/api/v2/watchlist/ETH-USDT-SWAP", {
        method: "PUT",
      }),
      ["api", "v2", "watchlist", "ETH-USDT-SWAP"],
      fetcher,
    );
    const rejected = await proxyProductRequest(
      new Request("http://127.0.0.1:3101/api/product/api/v2/watchlist/DOGE-USDT-SWAP", {
        method: "PUT",
      }),
      ["api", "v2", "watchlist", "DOGE-USDT-SWAP"],
      fetcher,
    );

    expect(homeResponse.status).toBe(200);
    expect(addResponse.status).toBe(200);
    expect(rejected.status).toBe(404);
    expect(fetcher.mock.calls[0]?.[0]).toBe(
      "http://127.0.0.1:8123/app/api/v2/home",
    );
    expect(fetcher.mock.calls[1]?.[0]).toBe(
      "http://127.0.0.1:8123/app/api/v2/watchlist/ETH-USDT-SWAP",
    );
  });

  it("allows owner-scoped Run detail and Artifact library reads", async () => {
    const runId = "11111111-1111-4111-8111-111111111111";
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return Response.json({ items: [] });
    });

    const runResponse = await proxyProductRequest(
      new Request(`http://127.0.0.1:3101/api/product/api/v2/runs/${runId}`),
      ["api", "v2", "runs", runId],
      fetcher,
    );
    const artifactResponse = await proxyProductRequest(
      new Request("http://127.0.0.1:3101/api/product/api/v2/artifacts?limit=50"),
      ["api", "v2", "artifacts"],
      fetcher,
    );

    expect(runResponse.status).toBe(200);
    expect(artifactResponse.status).toBe(200);
    expect(fetcher.mock.calls[0]?.[0]).toBe(
      `http://127.0.0.1:8123/app/api/v2/runs/${runId}`,
    );
    expect(fetcher.mock.calls[1]?.[0]).toBe(
      "http://127.0.0.1:8123/app/api/v2/artifacts?limit=50",
    );
  });

  it("allows durable task cancellation but rejects arbitrary task commands", async () => {
    const taskId = "00000000-0000-0000-0000-000000000001";
    const fetcher = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        void input;
        void init;
        return Response.json(taskProjection("running"), { status: 202 });
      },
    );

    const response = await proxyProductRequest(
      new Request(`http://127.0.0.1:3101/api/product/api/v2/tasks/${taskId}/cancel`, {
        method: "POST",
        headers: { "idempotency-key": "cancel-task-1" },
      }),
      ["api", "v2", "tasks", taskId, "cancel"],
      fetcher,
    );
    expect(response.status).toBe(202);
    const headers = new Headers(fetcher.mock.calls[0]?.[1]?.headers);
    expect(headers.get("idempotency-key")).toBe("cancel-task-1");

    const rejected = await proxyProductRequest(
      new Request(`http://127.0.0.1:3101/api/product/api/v2/tasks/${taskId}/unknown`, {
        method: "POST",
      }),
      ["api", "v2", "tasks", taskId, "unknown"],
      fetcher,
    );
    expect(rejected.status).toBe(404);
  });

  it("allows only the owner-scoped Run cancellation route", async () => {
    const runId = "11111111-1111-4111-8111-111111111111";
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return Response.json({ status: "running" }, { status: 202 });
    });
    const response = await proxyProductRequest(
      new Request(`http://127.0.0.1:3101/api/product/api/v2/runs/${runId}/cancel`, {
        method: "POST",
        headers: { "idempotency-key": "cancel-run-1" },
      }),
      ["api", "v2", "runs", runId, "cancel"],
      fetcher,
    );

    expect(response.status).toBe(202);
    expect(fetcher.mock.calls[0]?.[0]).toBe(
      `http://127.0.0.1:8123/app/api/v2/runs/${runId}/cancel`,
    );
    const headers = new Headers(fetcher.mock.calls[0]?.[1]?.headers);
    expect(headers.get("idempotency-key")).toBe("cancel-run-1");
  });

  it("allows only the owner-scoped Run feedback route", async () => {
    const runId = "11111111-1111-4111-8111-111111111111";
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return Response.json({ rating: "positive" }, { status: 201 });
    });
    const response = await proxyProductRequest(
      new Request(`http://127.0.0.1:3101/api/product/api/v2/runs/${runId}/feedback`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "idempotency-key": "feedback-1",
        },
        body: JSON.stringify({ rating: "positive" }),
      }),
      ["api", "v2", "runs", runId, "feedback"],
      fetcher,
    );

    expect(response.status).toBe(201);
    expect(fetcher.mock.calls[0]?.[0]).toBe(
      `http://127.0.0.1:8123/app/api/v2/runs/${runId}/feedback`,
    );
    const headers = new Headers(fetcher.mock.calls[0]?.[1]?.headers);
    expect(headers.get("idempotency-key")).toBe("feedback-1");
    expect(headers.get("content-type")).toBe("application/json");
  });

  it("allows durable task retry and forwards only the server-approved idempotency key", async () => {
    const taskId = "00000000-0000-0000-0000-000000000001";
    const fetcher = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        void input;
        void init;
        return Response.json(taskProjection("queued"), { status: 202 });
      },
    );

    const response = await proxyProductRequest(
      new Request(`http://127.0.0.1:3101/api/product/api/v2/tasks/${taskId}/retry`, {
        method: "POST",
        headers: { "idempotency-key": "retry-task-1" },
      }),
      ["api", "v2", "tasks", taskId, "retry"],
      fetcher,
    );

    expect(response.status).toBe(202);
    expect(fetcher).toHaveBeenCalledWith(
      `http://127.0.0.1:8123/app/api/v2/tasks/${taskId}/retry`,
      expect.objectContaining({ method: "POST" }),
    );
    const headers = new Headers(fetcher.mock.calls[0]?.[1]?.headers);
    expect(headers.get("idempotency-key")).toBe("retry-task-1");
  });

  it("allows only exact notification list and resend routes", async () => {
    const taskId = "22222222-2222-4222-8222-222222222222";
    const notificationId = "77777777-7777-4777-8777-777777777777";
    const fetcher = vi.fn(async () => Response.json({ items: [] }));

    const list = await proxyProductRequest(
      new Request(
        `http://127.0.0.1:3101/api/product/api/v2/tasks/${taskId}/notifications`,
      ),
      ["api", "v2", "tasks", taskId, "notifications"],
      fetcher,
    );
    const resend = await proxyProductRequest(
      new Request(
        `http://127.0.0.1:3101/api/product/api/v2/notifications/${notificationId}/resend`,
        { method: "POST", body: JSON.stringify({ reason: "User retry" }) },
      ),
      ["api", "v2", "notifications", notificationId, "resend"],
      fetcher,
    );
    const rejected = await proxyProductRequest(
      new Request(
        `http://127.0.0.1:3101/api/product/api/v2/notifications/${notificationId}`,
      ),
      ["api", "v2", "notifications", notificationId],
      fetcher,
    );

    expect(list.status).toBe(200);
    expect(resend.status).toBe(200);
    expect(rejected.status).toBe(404);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("forwards only the exact fork route, JSON body, and idempotency key", async () => {
    const taskId = "22222222-2222-4222-8222-222222222222";
    const body = JSON.stringify({
      source_run_id: "11111111-1111-4111-8111-111111111111",
    });
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return Response.json(taskProjection("queued"), { status: 202 });
    });

    const response = await proxyProductRequest(
      new Request(`http://127.0.0.1:3101/api/product/api/v2/tasks/${taskId}/fork`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "idempotency-key": "fork-network-retry-1",
          authorization: "Bearer browser-forgery",
        },
        body,
      }),
      ["api", "v2", "tasks", taskId, "fork"],
      fetcher,
    );

    expect(response.status).toBe(202);
    const [upstreamUrl, upstreamInit] = fetcher.mock.calls[0] ?? [];
    expect(upstreamUrl).toBe(
      `http://127.0.0.1:8123/app/api/v2/tasks/${taskId}/fork`,
    );
    const headers = new Headers(upstreamInit?.headers);
    expect(headers.get("content-type")).toBe("application/json");
    expect(headers.get("idempotency-key")).toBe("fork-network-retry-1");
    expect(headers.get("authorization")).toBeNull();
    expect(new TextDecoder().decode(upstreamInit?.body as ArrayBuffer)).toBe(body);
  });

  it.each([
    ["GET", ["api", "v2", "tasks", "22222222-2222-4222-8222-222222222222", "fork"]],
    ["POST", ["api", "v2", "tasks", "not-a-task", "fork"]],
    ["POST", ["api", "v2", "tasks", "22222222-2222-4222-8222-222222222222", "fork", "extra"]],
    ["POST", ["api", "v2", "runs", "22222222-2222-4222-8222-222222222222", "fork"]],
  ])("rejects a fork lookalike route (%s %j)", async (method, path) => {
    const fetcher = vi.fn();
    const response = await proxyProductRequest(
      new Request(`http://127.0.0.1:3101/api/product/${path.join("/")}`, {
        method,
        body: method === "POST" ? "{}" : undefined,
      }),
      path,
      fetcher,
    );

    expect(response.status).toBe(404);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("forwards only the exact respond-all route, JSON body, and idempotency key", async () => {
    const taskId = "22222222-2222-4222-8222-222222222222";
    const body = JSON.stringify({
      pause_id: "33333333-3333-4333-8333-333333333334",
      pause_version: 7,
      responses: [{
        interrupt_id: "interrupt:review-4",
        response_version: 4,
        response: { action: "approve", comment: null, edits: null },
      }],
    });
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return Response.json(taskProjection("waiting_human"), { status: 202 });
    });

    const response = await proxyProductRequest(
      new Request(
        `http://127.0.0.1:3101/api/product/api/v2/tasks/${taskId}/interrupts/respond-all`,
        {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "idempotency-key": "review-network-retry-4",
            authorization: "Bearer browser-forgery",
          },
          body,
        },
      ),
      ["api", "v2", "tasks", taskId, "interrupts", "respond-all"],
      fetcher,
    );

    expect(response.status).toBe(202);
    expect(fetcher).toHaveBeenCalledOnce();
    const [upstreamUrl, upstreamInit] = fetcher.mock.calls[0] ?? [];
    expect(upstreamUrl).toBe(
      `http://127.0.0.1:8123/app/api/v2/tasks/${taskId}/interrupts/respond-all`,
    );
    const headers = new Headers(upstreamInit?.headers);
    expect(headers.get("content-type")).toBe("application/json");
    expect(headers.get("idempotency-key")).toBe("review-network-retry-4");
    expect(headers.get("authorization")).toBeNull();
    expect(new TextDecoder().decode(upstreamInit?.body as ArrayBuffer)).toBe(body);
  });

  it.each([
    ["GET", ["api", "v2", "tasks", "22222222-2222-4222-8222-222222222222", "interrupts", "respond-all"]],
    ["POST", ["api", "v2", "tasks", "not-a-task", "interrupts", "respond-all"]],
    ["POST", ["api", "v2", "tasks", "22222222-2222-4222-8222-222222222222", "interrupts", "respond"]],
    ["POST", ["api", "v2", "tasks", "22222222-2222-4222-8222-222222222222", "interrupts", "interrupt-1", "respond"]],
    ["POST", ["api", "v2", "tasks", "22222222-2222-4222-8222-222222222222", "interrupts", "respond-all", "extra"]],
  ])("rejects a respond-all lookalike route (%s %j)", async (method, path) => {
    const fetcher = vi.fn();
    const response = await proxyProductRequest(
      new Request(`http://127.0.0.1:3101/api/product/${path.join("/")}`, {
        method,
        body: method === "POST" ? "{}" : undefined,
      }),
      path,
      fetcher,
    );

    expect(response.status).toBe(404);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("forwards only the exact Product-owned Inbox review route and idempotency key", async () => {
    const pauseId = "33333333-3333-4333-8333-333333333334";
    const body = JSON.stringify({
      pause_version: 7,
      response: { action: "approve" },
    });
    const fetcher = vi.fn(async (
      input: RequestInfo | URL,
      init?: RequestInit,
    ) => {
      void input;
      void init;
      return Response.json({
        task_id: "22222222-2222-4222-8222-222222222222",
        pause_id: pauseId,
        pause_version: 7,
        status: "responding",
        responded_at: "2026-07-13T00:01:00Z",
      }, { status: 202 });
    });

    const response = await proxyProductRequest(
      new Request(
        `http://127.0.0.1:3101/api/product/api/v2/inbox/${pauseId}/respond`,
        {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "idempotency-key": "inbox-review-network-retry-1",
            authorization: "Bearer browser-forgery",
          },
          body,
        },
      ),
      ["api", "v2", "inbox", pauseId, "respond"],
      fetcher,
    );

    expect(response.status).toBe(202);
    expect(fetcher).toHaveBeenCalledOnce();
    const [upstreamUrl, upstreamInit] = fetcher.mock.calls[0] ?? [];
    expect(upstreamUrl).toBe(
      `http://127.0.0.1:8123/app/api/v2/inbox/${pauseId}/respond`,
    );
    const headers = new Headers(upstreamInit?.headers);
    expect(headers.get("content-type")).toBe("application/json");
    expect(headers.get("idempotency-key")).toBe("inbox-review-network-retry-1");
    expect(headers.get("authorization")).toBeNull();
    expect(new TextDecoder().decode(upstreamInit?.body as ArrayBuffer)).toBe(body);
  });

  it.each([
    ["GET", ["api", "v2", "inbox", "33333333-3333-4333-8333-333333333334", "respond"]],
    ["POST", ["api", "v2", "inbox", "not-a-pause", "respond"]],
    ["POST", ["api", "v2", "inbox", "33333333-3333-4333-8333-333333333334"]],
    ["POST", ["api", "v2", "inbox", "33333333-3333-4333-8333-333333333334", "respond", "extra"]],
  ])("rejects an Inbox review lookalike route (%s %j)", async (method, path) => {
    const fetcher = vi.fn();
    const response = await proxyProductRequest(
      new Request(`http://127.0.0.1:3101/api/product/${path.join("/")}`, {
        method,
        body: method === "POST" ? "{}" : undefined,
      }),
      path,
      fetcher,
    );

    expect(response.status).toBe(404);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it.each(["staging", "production"])(
    "rejects %s requests without a server-owned identity",
    async (environment) => {
      process.env.APP_ENVIRONMENT = environment;
      const fetcher = vi.fn();
      const resolveAuthorization = vi.fn(async () => null);

      const response = await proxyProductRequest(
        new Request("https://product.example.com/api/product/api/v2/analysis", {
          method: "POST",
          headers: { authorization: "Bearer browser-forgery" },
          body: "{}",
        }),
        ["api", "v2", "analysis"],
        fetcher,
        resolveAuthorization,
      );

      expect(response.status).toBe(401);
      expect(fetcher).not.toHaveBeenCalled();
    },
  );

  it("fails closed when a production build omits APP_ENVIRONMENT", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const fetcher = vi.fn();
    const resolveAuthorization = vi.fn(async () => null);

    const response = await proxyProductRequest(
      new Request("https://product.example.com/api/product/api/v2/analysis", {
        method: "POST",
        headers: { authorization: "Bearer browser-forgery" },
        body: "{}",
      }),
      ["api", "v2", "analysis"],
      fetcher,
      resolveAuthorization,
    );

    expect(response.status).toBe(401);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("replaces browser authority with the signed internal authorization", async () => {
    process.env.APP_ENVIRONMENT = "production";
    const fetcher = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        void input;
        void init;
        return Response.json(taskProjection("queued"), { status: 202 });
      },
    );
    const resolveAuthorization = vi.fn(async () => "Bearer signed-internal-token");

    const response = await proxyProductRequest(
      new Request("https://product.example.com/api/product/api/v2/analysis", {
        method: "POST",
        headers: { authorization: "Bearer browser-forgery", "content-type": "application/json" },
        body: "{}",
      }),
      ["api", "v2", "analysis"],
      fetcher,
      resolveAuthorization,
    );

    expect(response.status).toBe(202);
    const headers = new Headers(fetcher.mock.calls[0]?.[1]?.headers);
    expect(headers.get("authorization")).toBe("Bearer signed-internal-token");
  });

  it("rejects paths outside the explicit Product API allowlist", async () => {
    const fetcher = vi.fn();

    const response = await proxyProductRequest(
      new Request("http://127.0.0.1:3101/api/product/openapi.json"),
      ["openapi.json"],
      fetcher,
    );

    expect(response.status).toBe(404);
    expect(fetcher).not.toHaveBeenCalled();
  });
});

function taskProjection(status: string) {
  return {
    task_id: "task-proxy-1",
    correlation_id: "44444444-4444-5444-8444-444444444444",
    status,
    symbol: "BTC-USDT-SWAP",
    horizon: "4h",
    created_at: "2026-07-13T08:30:00Z",
    artifact: null,
    errors: [],
  };
}
