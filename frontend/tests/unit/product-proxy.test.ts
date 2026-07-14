import { generateKeyPairSync } from "node:crypto";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { proxyProductRequest } from "../../src/lib/api/product-proxy";

describe("Product BFF proxy", () => {
  afterEach(() => {
    delete process.env.PRODUCT_API_BASE_URL;
    delete process.env.APP_ENVIRONMENT;
    delete process.env.DEVELOPMENT_BOOTSTRAP_ENABLED;
    delete process.env.DEVELOPMENT_BOOTSTRAP_PERMISSIONS;
    delete process.env.DEVELOPMENT_BOOTSTRAP_PROFILE;
    delete process.env.DEVELOPMENT_BOOTSTRAP_ROLES;
    delete process.env.DEVELOPMENT_BOOTSTRAP_SUBJECT;
    delete process.env.DEVELOPMENT_BOOTSTRAP_TENANT_ID;
    delete process.env.DEVELOPMENT_BOOTSTRAP_WORKSPACE_ID;
    delete process.env.INTERNAL_JWT_ISSUER;
    delete process.env.INTERNAL_JWT_KID;
    delete process.env.INTERNAL_JWT_PRIVATE_KEY;
    vi.unstubAllEnvs();
  });

  it("uses the server-only loopback base URL and strips browser authority headers", async () => {
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
    expect(upstreamUrl).toBe("http://127.0.0.1:8011/api/v2/analysis");
    const headers = new Headers(upstreamInit?.headers);
    expect(headers.get("authorization")).toBeNull();
    expect(headers.get("x-api-key")).toBeNull();
    expect(headers.get("x-tenant-id")).toBeNull();
    expect(headers.get("content-type")).toBe("application/json");
    expect(headers.get("idempotency-key")).toBe("analysis-admission-1");
  });

  it("signs Product requests for the deployment-controlled development identity", async () => {
    const { privateKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
    process.env.APP_ENVIRONMENT = "development";
    process.env.INTERNAL_JWT_PRIVATE_KEY = privateKey
      .export({ type: "pkcs8", format: "pem" })
      .toString();
    process.env.INTERNAL_JWT_KID = "compose-product-key";
    process.env.INTERNAL_JWT_ISSUER = "compose-local";
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
    expect(authorization).toMatch(/^Bearer [^.]+\.[^.]+\.[^.]+$/);
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
    process.env.PRODUCT_API_BASE_URL = "http://127.0.0.1:8999/base/";
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
      "http://127.0.0.1:8999/base/api/v2/tasks/00000000-0000-0000-0000-000000000001",
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
      "http://127.0.0.1:8011/api/v2/runs?limit=25",
      expect.objectContaining({ method: "GET" }),
    );

    const rejected = await proxyProductRequest(
      new Request("http://127.0.0.1:3101/api/product/api/v2/runs", { method: "POST" }),
      ["api", "v2", "runs"],
      fetcher,
    );
    expect(rejected.status).toBe(404);
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
    status,
    symbol: "BTC-USDT-SWAP",
    horizon: "4h",
    created_at: "2026-07-13T08:30:00Z",
    artifact: null,
    errors: [],
  };
}
