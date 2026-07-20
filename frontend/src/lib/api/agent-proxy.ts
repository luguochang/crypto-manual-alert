import "server-only";

import { isDevelopmentBootstrapRuntime } from "@/lib/auth/bff-auth";
import { requiresAuthenticatedRuntime } from "@/lib/runtime/app-environment";

type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
export type AgentAuthorizationResolver = (
  request: Request,
  audience: string,
) => Promise<string | null>;

type AgentRoute = {
  kind: "state" | "history" | "events";
  method: "GET" | "POST";
};

const defaultAgentServerUrl = "http://127.0.0.1:8123";
const defaultAgentAudience = "crypto-alert-agent-server";
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function proxyAgentRequest(
  request: Request,
  pathSegments: string[],
  fetcher: Fetcher = fetch,
  resolveAuthorization: AgentAuthorizationResolver = defaultAuthorizationResolver,
): Promise<Response> {
  const requestId = transportRequestId();
  const route = matchAgentRoute(pathSegments);
  if (route === null) {
    return withRequestId(
      Response.json({ detail: "Agent route not found." }, { status: 404 }),
      requestId,
    );
  }
  if (request.method !== route.method) {
    return withRequestId(
      Response.json(
        { detail: "Method not allowed." },
        { status: 405, headers: { allow: route.method } },
      ),
      requestId,
    );
  }

  try {
    const authenticatedRuntime = requiresAuthenticatedRuntime();
    const audience = agentAudience();
    const internalAuthorization = authenticatedRuntime;
    const baseUrl = agentServerBaseUrl(internalAuthorization);
    const authorization = internalAuthorization
      ? await resolveAuthorization(request, audience)
      : localAuthorization(baseUrl)
        ?? await resolveBootstrapAuthorization(audience);
    if (authorization === null) {
      return withRequestId(
        Response.json({ detail: "Authentication required." }, { status: 401 }),
        requestId,
      );
    }

    const body = route.method === "POST" ? await request.arrayBuffer() : undefined;
    const response = await fetcher(buildUpstreamUrl(baseUrl, pathSegments), {
      method: route.method,
      headers: upstreamRequestHeaders(route, authorization, requestId),
      body: body && body.byteLength > 0 ? body : undefined,
      cache: "no-store",
      redirect: "manual",
      signal: request.signal,
    });

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: controlledResponseHeaders(response.headers, requestId),
    });
  } catch {
    return withRequestId(
      Response.json(
        { detail: "Agent Server is temporarily unavailable." },
        { status: 502 },
      ),
      requestId,
    );
  }
}

function matchAgentRoute(pathSegments: string[]): AgentRoute | null {
  if (
    pathSegments.length < 3
    || pathSegments[0] !== "threads"
    || !uuidPattern.test(pathSegments[1] ?? "")
  ) {
    return null;
  }
  if (pathSegments.length === 3 && pathSegments[2] === "state") {
    return { kind: "state", method: "GET" };
  }
  if (pathSegments.length === 3 && pathSegments[2] === "history") {
    return { kind: "history", method: "POST" };
  }
  if (
    pathSegments.length === 4
    && pathSegments[2] === "stream"
    && pathSegments[3] === "events"
  ) {
    return { kind: "events", method: "POST" };
  }
  return null;
}

function agentServerBaseUrl(authenticatedRuntime: boolean): URL {
  const configured = process.env.AGENT_SERVER_URL ?? defaultAgentServerUrl;
  const baseUrl = new URL(configured.endsWith("/") ? configured : `${configured}/`);
  if (
    (baseUrl.protocol !== "http:" && baseUrl.protocol !== "https:")
    || baseUrl.username
    || baseUrl.password
    || baseUrl.search
    || baseUrl.hash
  ) {
    throw new Error("Invalid Agent Server URL");
  }
  if (!authenticatedRuntime && baseUrl.protocol !== "http:") {
    throw new Error("Local Agent Server URL must use HTTP");
  }
  if (
    !authenticatedRuntime
    && !isLoopbackHostname(baseUrl.hostname)
    && !hasDevelopmentBootstrapSigningConfig()
  ) {
    throw new Error("Local Agent Server URL must use loopback");
  }
  return baseUrl;
}

function hasDevelopmentBootstrapSigningConfig(): boolean {
  return isDevelopmentBootstrapRuntime()
    && Boolean(
      process.env.DEVELOPMENT_BOOTSTRAP_SUBJECT?.trim()
      && process.env.DEVELOPMENT_BOOTSTRAP_IDENTITY_ISSUER?.trim()
      && process.env.DEVELOPMENT_BOOTSTRAP_CONTEXT_ID?.trim()
      && process.env.INTERNAL_JWT_KID?.trim()
      && process.env.INTERNAL_JWT_ISSUER?.trim()
      && (
        process.env.INTERNAL_JWT_PRIVATE_KEY?.trim()
        || process.env.INTERNAL_JWT_PRIVATE_KEY_FILE?.trim()
      )
    );
}

function isLoopbackHostname(hostname: string): boolean {
  const normalized = hostname.toLowerCase().replace(/^\[|\]$/g, "");
  if (normalized === "localhost" || normalized === "::1") return true;
  const octets = normalized.split(".");
  return octets.length === 4
    && octets.every((part) => /^\d{1,3}$/.test(part) && Number(part) <= 255)
    && Number(octets[0]) === 127;
}

function localAuthorization(baseUrl: URL): string | null {
  if (!isLoopbackHostname(baseUrl.hostname)) {
    return null;
  }
  const token = process.env.AGENT_SERVER_LOCAL_TOKEN;
  return token?.trim() ? `Bearer ${token}` : null;
}

function agentAudience(): string {
  return process.env.AGENT_SERVER_INTERNAL_JWT_AUDIENCE?.trim()
    || defaultAgentAudience;
}

async function defaultAuthorizationResolver(
  request: Request,
  audience: string,
): Promise<string | null> {
  const { resolveInternalAuthorization } = await import("@/lib/auth/bff-auth");
  return resolveInternalAuthorization(request, undefined, {
    audience,
  });
}

async function resolveBootstrapAuthorization(audience: string): Promise<string | null> {
  const { developmentBootstrapAuthorization } = await import("@/lib/auth/bff-auth");
  return developmentBootstrapAuthorization(audience);
}

function buildUpstreamUrl(baseUrl: URL, pathSegments: string[]): string {
  const encodedPath = pathSegments.map((segment) => encodeURIComponent(segment)).join("/");
  return new URL(encodedPath, baseUrl).toString();
}

function upstreamRequestHeaders(
  route: AgentRoute,
  authorization: string,
  requestId: string,
): Headers {
  const headers = new Headers({
    accept: route.kind === "events" ? "text/event-stream" : "application/json",
    authorization,
    "x-request-id": requestId,
  });
  if (route.method === "POST") headers.set("content-type", "application/json");
  return headers;
}

function controlledResponseHeaders(upstream: Headers, requestId: string): Headers {
  const headers = new Headers();
  for (const name of ["content-type", "cache-control"]) {
    const value = upstream.get(name);
    if (value) headers.set(name, value);
  }
  headers.set("x-request-id", requestId);
  return headers;
}

function transportRequestId(): string {
  return crypto.randomUUID();
}

function withRequestId(response: Response, requestId: string): Response {
  response.headers.set("x-request-id", requestId);
  return response;
}
