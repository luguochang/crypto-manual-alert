import { generateKeyPairSync } from "node:crypto";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { proxyAgentRequest } from "../../src/lib/api/agent-proxy";

const threadId = "6b83a8ca-80f8-4e73-8d3e-f1fd919222b7";

describe("Agent BFF proxy", () => {
  afterEach(() => {
    delete process.env.AGENT_SERVER_INTERNAL_JWT_AUDIENCE;
    delete process.env.AGENT_SERVER_LOCAL_TOKEN;
    delete process.env.AGENT_SERVER_URL;
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
  });

  it("provides one server-only Agent proxy boundary", () => {
    expect(existsSync(resolve(process.cwd(), "src/lib/api/agent-proxy.ts"))).toBe(true);
    expect(existsSync(resolve(process.cwd(), "src/app/api/agent/[...path]/route.ts"))).toBe(true);
  });

  it("allows a local state read only through a loopback Agent URL and server token", async () => {
    process.env.APP_ENVIRONMENT = "development";
    process.env.AGENT_SERVER_URL = "http://127.0.0.1:8123";
    process.env.AGENT_SERVER_LOCAL_TOKEN = "local-agent-secret";
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return Response.json({ values: {}, next: ["analyze"] }, {
        headers: {
          "cache-control": "no-store",
          "x-internal-token": "must-not-leak",
        },
      });
    });
    const request = new Request(`http://127.0.0.1:3101/api/agent/threads/${threadId}/state`, {
      headers: {
        authorization: "Bearer browser-forgery",
        "x-api-key": "browser-key",
        "x-tenant": "attacker-tenant",
        "x-tenant-id": "attacker-tenant-id",
        "x-workspace": "attacker-workspace",
        "x-workspace-id": "attacker-workspace-id",
      },
    });

    const response = await proxyAgentRequest(request, ["threads", threadId, "state"], fetcher);

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ values: {}, next: ["analyze"] });
    expect(fetcher).toHaveBeenCalledOnce();
    const [upstreamUrl, upstreamInit] = fetcher.mock.calls[0] ?? [];
    expect(upstreamUrl).toBe(`http://127.0.0.1:8123/threads/${threadId}/state`);
    const headers = new Headers(upstreamInit?.headers);
    expect(headers.get("authorization")).toBe("Bearer local-agent-secret");
    expect(headers.get("accept")).toBe("application/json");
    expect(headers.get("x-api-key")).toBeNull();
    expect(headers.get("x-tenant")).toBeNull();
    expect(headers.get("x-tenant-id")).toBeNull();
    expect(headers.get("x-workspace")).toBeNull();
    expect(headers.get("x-workspace-id")).toBeNull();
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(response.headers.get("x-internal-token")).toBeNull();
  });

  it("passes history JSON without forwarding browser-owned headers", async () => {
    process.env.AGENT_SERVER_URL = "http://localhost:8123/base/";
    process.env.AGENT_SERVER_LOCAL_TOKEN = "history-token";
    const requestBody = JSON.stringify({ limit: 20 });
    let upstreamBody = "";
    const fetcher = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      upstreamBody = await new Response(init?.body).text();
      return Response.json([{ values: {}, next: [] }], {
        headers: { "content-type": "application/json; charset=utf-8" },
      });
    });
    const request = new Request(`http://127.0.0.1:3101/api/agent/threads/${threadId}/history`, {
      method: "POST",
      body: requestBody,
      headers: {
        accept: "text/plain",
        "content-type": "application/x-www-form-urlencoded",
        authorization: "Basic attacker",
      },
    });

    const response = await proxyAgentRequest(request, ["threads", threadId, "history"], fetcher);

    expect(response.status).toBe(200);
    expect(upstreamBody).toBe(requestBody);
    expect(fetcher.mock.calls[0]?.[0]).toBe(`http://localhost:8123/base/threads/${threadId}/history`);
    const headers = new Headers(fetcher.mock.calls[0]?.[1]?.headers);
    expect(headers.get("authorization")).toBe("Bearer history-token");
    expect(headers.get("accept")).toBe("application/json");
    expect(headers.get("content-type")).toBe("application/json");
    expect(response.headers.get("content-type")).toContain("application/json");
  });

  it("forwards the SSE byte stream, headers, and browser abort signal unchanged", async () => {
    process.env.APP_ENVIRONMENT = "test";
    process.env.AGENT_SERVER_URL = "http://[::1]:8123";
    process.env.AGENT_SERVER_LOCAL_TOKEN = "stream-token";
    const sseBytes = new TextEncoder().encode(
      'event: message\ndata: {"seq":1,"channel":"values","data":{"lifecycle":"running"}}\n\n',
    );
    const upstreamStream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(sseBytes.slice(0, 19));
        controller.enqueue(sseBytes.slice(19));
        controller.close();
      },
    });
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return new Response(upstreamStream, {
        headers: {
          "content-type": "text/event-stream; charset=utf-8",
          "cache-control": "no-cache, no-transform",
          "x-agent-private": "hidden",
        },
      });
    });
    const controller = new AbortController();
    const request = new Request(`http://127.0.0.1:3101/api/agent/threads/${threadId}/stream/events`, {
      method: "POST",
      body: JSON.stringify({ channels: ["values", "lifecycle"], since: 0 }),
      headers: { authorization: "Bearer browser-forgery", "x-api-key": "browser-key" },
      signal: controller.signal,
    });

    const response = await proxyAgentRequest(
      request,
      ["threads", threadId, "stream", "events"],
      fetcher,
    );

    expect(response.headers.get("content-type")).toBe("text/event-stream; charset=utf-8");
    expect(response.headers.get("cache-control")).toBe("no-cache, no-transform");
    expect(response.headers.get("x-agent-private")).toBeNull();
    expect(new Uint8Array(await response.arrayBuffer())).toEqual(sseBytes);
    const init = fetcher.mock.calls[0]?.[1];
    expect(init?.signal).toBe(request.signal);
    const headers = new Headers(init?.headers);
    expect(headers.get("authorization")).toBe("Bearer stream-token");
    expect(headers.get("accept")).toBe("text/event-stream");
    expect(headers.get("content-type")).toBe("application/json");
  });

  it.each([
    ["POST", ["threads", threadId, "state"], 405],
    ["GET", ["threads", threadId, "history"], 405],
    ["GET", ["threads", threadId, "stream", "events"], 405],
    ["POST", ["threads", threadId, "commands"], 404],
    ["POST", ["threads", threadId, "runs"], 404],
    ["POST", ["threads", threadId, "runs", "run-1", "cancel"], 404],
    ["GET", ["assistants", "search"], 404],
    ["POST", ["store", "search"], 404],
    ["GET", ["threads", "not-a-uuid", "state"], 404],
  ])("rejects %s /%s before contacting Agent Server", async (method, path, status) => {
    process.env.AGENT_SERVER_URL = "http://127.0.0.1:8123";
    process.env.AGENT_SERVER_LOCAL_TOKEN = "local-token";
    const fetcher = vi.fn();

    const response = await proxyAgentRequest(
      new Request(`http://127.0.0.1:3101/api/agent/${path.join("/")}`, { method }),
      path,
      fetcher,
    );

    expect(response.status).toBe(status);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it.each([
    ["http://agent-server:8123", "local-token"],
    ["https://127.0.0.1:8123", ""],
  ])("rejects unsafe local Agent authority %s before fetching", async (url, token) => {
    process.env.APP_ENVIRONMENT = "development";
    process.env.AGENT_SERVER_URL = url;
    process.env.AGENT_SERVER_LOCAL_TOKEN = token;
    const fetcher = vi.fn();

    const response = await proxyAgentRequest(
      new Request(`http://127.0.0.1:3101/api/agent/threads/${threadId}/state`),
      ["threads", threadId, "state"],
      fetcher,
    );

    expect(response.status).toBe(502);
    expect(fetcher).not.toHaveBeenCalled();
    const responseBody = JSON.stringify(await response.json());
    if (token) expect(responseBody).not.toContain(token);
  });

  it("uses only production server authorization and the configured Agent audience", async () => {
    process.env.APP_ENVIRONMENT = "production";
    process.env.AGENT_SERVER_URL = "http://agent-server.internal:8123";
    process.env.AGENT_SERVER_INTERNAL_JWT_AUDIENCE = "crypto-alert-agent-server-custom";
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return Response.json({ values: {}, next: [] });
    });
    const resolveAuthorization = vi.fn(async (_request: Request, audience: string) => {
      expect(audience).toBe("crypto-alert-agent-server-custom");
      return "Bearer signed-agent-jwt";
    });
    const request = new Request(`https://product.example.com/api/agent/threads/${threadId}/state`, {
      headers: {
        authorization: "Bearer browser-forgery",
        "x-api-key": "browser-key",
        "x-tenant": "browser-tenant",
        "x-workspace": "browser-workspace",
      },
    });

    const response = await proxyAgentRequest(
      request,
      ["threads", threadId, "state"],
      fetcher,
      resolveAuthorization,
    );

    expect(response.status).toBe(200);
    expect(resolveAuthorization).toHaveBeenCalledOnce();
    const headers = new Headers(fetcher.mock.calls[0]?.[1]?.headers);
    expect(headers.get("authorization")).toBe("Bearer signed-agent-jwt");
    expect(headers.get("x-api-key")).toBeNull();
    expect(headers.get("x-tenant")).toBeNull();
    expect(headers.get("x-workspace")).toBeNull();
  });

  it("does not contact production Agent Server without a current session", async () => {
    process.env.APP_ENVIRONMENT = "production";
    process.env.AGENT_SERVER_URL = "https://agent-server.internal";
    const fetcher = vi.fn();
    const resolveAuthorization = vi.fn(async () => null);

    const response = await proxyAgentRequest(
      new Request(`https://product.example.com/api/agent/threads/${threadId}/state`),
      ["threads", threadId, "state"],
      fetcher,
      resolveAuthorization,
    );

    expect(response.status).toBe(401);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("rejects a non-loopback development Agent URL even with bootstrap fields", async () => {
    const { privateKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
    process.env.APP_ENVIRONMENT = "development";
    process.env.AGENT_SERVER_URL = "http://agent-server:8123";
    process.env.INTERNAL_JWT_PRIVATE_KEY = privateKey
      .export({ type: "pkcs8", format: "pem" })
      .toString();
    process.env.INTERNAL_JWT_KID = "compose-agent-key";
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
      return Response.json({ values: {}, next: [] });
    });

    const response = await proxyAgentRequest(
      new Request(`http://0.0.0.0:3001/api/agent/threads/${threadId}/state`),
      ["threads", threadId, "state"],
      fetcher,
    );

    expect(response.status).toBe(502);
    expect(fetcher).not.toHaveBeenCalled();
  });
});
