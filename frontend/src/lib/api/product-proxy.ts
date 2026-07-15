import "server-only";

import { requiresAuthenticatedRuntime } from "@/lib/runtime/app-environment";

type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
export type AuthorizationResolver = (request: Request) => Promise<string | null>;

const defaultProductApiBaseUrl = "http://127.0.0.1:8123/app";
const defaultAgentServerAudience = "crypto-alert-agent-server";
const idempotencyKeyPattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$/;
const taskIdPattern = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;

export async function proxyProductRequest(
  request: Request,
  pathSegments: string[],
  fetcher: Fetcher = fetch,
  resolveAuthorization: AuthorizationResolver = defaultAuthorizationResolver,
): Promise<Response> {
  if (!isAllowedProductRoute(request.method, pathSegments)) {
    return Response.json({ detail: "Product API route not found." }, { status: 404 });
  }
  try {
    const upstreamUrl = buildUpstreamUrl(request, pathSegments);
    const authenticatedRuntime = requiresAuthenticatedRuntime();
    const authorization = localAuthorization(upstreamUrl, authenticatedRuntime)
      ?? await resolveAuthorization(request);
    if (authenticatedRuntime && authorization === null) {
      return Response.json({ detail: "Authentication required." }, { status: 401 });
    }
    const headers = buildServerOwnedHeaders(request, pathSegments, authorization);
    const body = request.method === "GET" || request.method === "HEAD"
      ? undefined
      : await request.arrayBuffer();
    const response = await fetcher(upstreamUrl, {
      method: request.method,
      headers,
      body: body && body.byteLength > 0 ? body : undefined,
      cache: "no-store",
      redirect: "manual",
    });

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders(response.headers),
    });
  } catch {
    return Response.json(
      { detail: "Product API is temporarily unavailable." },
      { status: 502 },
    );
  }
}

function localAuthorization(upstreamUrl: string, authenticatedRuntime: boolean): string | null {
  if (authenticatedRuntime) return null;
  const url = new URL(upstreamUrl);
  if (!isLoopbackHostname(url.hostname)) return null;
  const token = process.env.AGENT_SERVER_LOCAL_TOKEN?.trim();
  return token ? `Bearer ${token}` : null;
}

function isLoopbackHostname(hostname: string): boolean {
  const normalized = hostname.toLowerCase().replace(/^\[|\]$/g, "");
  if (normalized === "localhost" || normalized === "::1") return true;
  const octets = normalized.split(".");
  return octets.length === 4
    && octets.every((part) => /^\d{1,3}$/.test(part) && Number(part) <= 255)
    && Number(octets[0]) === 127;
}

function isAllowedProductRoute(method: string, pathSegments: string[]): boolean {
  const path = pathSegments.join("/");
  if (method === "GET" && path === "api/v2/health") return true;
  if (method === "GET" && path === "api/v2/runs") return true;
  if (method === "GET" && path === "api/v2/inbox") return true;
  if (method === "POST" && path === "api/v2/analysis") return true;
  if (method === "POST" && isTaskCancelRoute(pathSegments)) return true;
  if (method === "POST" && isInterruptRespondAllRoute(pathSegments)) return true;
  return method === "GET" && isTaskReadRoute(pathSegments);
}

function isTaskReadRoute(pathSegments: string[]): boolean {
  return pathSegments.length === 4
    && pathSegments[0] === "api"
    && pathSegments[1] === "v2"
    && pathSegments[2] === "tasks"
    && taskIdPattern.test(pathSegments[3] ?? "");
}

function isTaskCancelRoute(pathSegments: string[]): boolean {
  return pathSegments.length === 5
    && isTaskReadRoute(pathSegments.slice(0, 4))
    && pathSegments[4] === "cancel";
}

function isInterruptRespondAllRoute(pathSegments: string[]): boolean {
  return pathSegments.length === 6
    && pathSegments[0] === "api"
    && pathSegments[1] === "v2"
    && pathSegments[2] === "tasks"
    && taskIdPattern.test(pathSegments[3] ?? "")
    && pathSegments[4] === "interrupts"
    && pathSegments[5] === "respond-all";
}

async function defaultAuthorizationResolver(request: Request): Promise<string | null> {
  const {
    isDevelopmentBootstrapRuntime,
    resolveInternalAuthorization,
  } = await import("@/lib/auth/bff-auth");
  if (
    !requiresAuthenticatedRuntime()
    && !isDevelopmentBootstrapRuntime()
  ) return null;
  return resolveInternalAuthorization(request, undefined, {
    audience: agentServerAudience(),
  });
}

function agentServerAudience(): string {
  return process.env.AGENT_SERVER_INTERNAL_JWT_AUDIENCE?.trim()
    || defaultAgentServerAudience;
}

function buildUpstreamUrl(request: Request, pathSegments: string[]): string {
  if (pathSegments.length === 0 || pathSegments.some((segment) => !segment || segment === "." || segment === "..")) {
    throw new Error("Invalid Product API path");
  }
  const baseUrl = normalizeBaseUrl(process.env.PRODUCT_API_BASE_URL ?? defaultProductApiBaseUrl);
  const encodedPath = pathSegments.map((segment) => encodeURIComponent(segment)).join("/");
  const upstreamUrl = new URL(encodedPath, baseUrl);
  upstreamUrl.search = new URL(request.url).search;
  return upstreamUrl.toString();
}

function normalizeBaseUrl(value: string): URL {
  const baseUrl = new URL(value.endsWith("/") ? value : `${value}/`);
  if (baseUrl.protocol !== "http:" && baseUrl.protocol !== "https:") {
    throw new Error("Invalid Product API protocol");
  }
  baseUrl.username = "";
  baseUrl.password = "";
  baseUrl.search = "";
  baseUrl.hash = "";
  return baseUrl;
}

function buildServerOwnedHeaders(
  request: Request,
  pathSegments: string[],
  authorization: string | null,
): Headers {
  const headers = new Headers();
  for (const name of ["accept", "content-type", "if-none-match", "x-request-id"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  const path = pathSegments.join("/");
  if (
    request.method === "POST"
    && (
      path === "api/v2/analysis"
      || isTaskCancelRoute(pathSegments)
      || isInterruptRespondAllRoute(pathSegments)
    )
  ) {
    const idempotencyKey = request.headers.get("idempotency-key");
    if (idempotencyKey && idempotencyKeyPattern.test(idempotencyKey)) {
      headers.set("idempotency-key", idempotencyKey);
    }
  }

  if (authorization) headers.set("authorization", authorization);
  return headers;
}

function responseHeaders(upstreamHeaders: Headers): Headers {
  const headers = new Headers();
  for (const name of ["cache-control", "content-type", "etag", "x-request-id", "x-upstream-request-id"]) {
    const value = upstreamHeaders.get(name);
    if (value) headers.set(name, value);
  }
  return headers;
}
