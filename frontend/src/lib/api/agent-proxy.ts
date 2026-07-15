import "server-only";

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
  const route = matchAgentRoute(pathSegments);
  if (route === null) {
    return Response.json({ detail: "Agent route not found." }, { status: 404 });
  }
  if (request.method !== route.method) {
    return Response.json(
      { detail: "Method not allowed." },
      { status: 405, headers: { allow: route.method } },
    );
  }

  try {
    const authenticatedRuntime = requiresAuthenticatedRuntime();
    const audience = agentAudience();
    const internalAuthorization = authenticatedRuntime;
    const baseUrl = agentServerBaseUrl(internalAuthorization);
    const authorization = internalAuthorization
      ? await resolveAuthorization(request, audience)
      : localAuthorization(baseUrl);
    if (authorization === null) {
      return Response.json({ detail: "Authentication required." }, { status: 401 });
    }

    const body = route.method === "POST" ? await request.arrayBuffer() : undefined;
    const response = await fetcher(buildUpstreamUrl(baseUrl, pathSegments), {
      method: route.method,
      headers: upstreamRequestHeaders(route, authorization),
      body: body && body.byteLength > 0 ? body : undefined,
      cache: "no-store",
      redirect: "manual",
      signal: request.signal,
    });

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: controlledResponseHeaders(response.headers),
    });
  } catch {
    return Response.json(
      { detail: "Agent Server is temporarily unavailable." },
      { status: 502 },
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
  if (!authenticatedRuntime && !isLoopbackHostname(baseUrl.hostname)) {
    throw new Error("Local Agent Server URL must use loopback");
  }
  return baseUrl;
}

function isLoopbackHostname(hostname: string): boolean {
  const normalized = hostname.toLowerCase().replace(/^\[|\]$/g, "");
  if (normalized === "localhost" || normalized === "::1") return true;
  const octets = normalized.split(".");
  return octets.length === 4
    && octets.every((part) => /^\d{1,3}$/.test(part) && Number(part) <= 255)
    && Number(octets[0]) === 127;
}

function localAuthorization(baseUrl: URL): string {
  if (!isLoopbackHostname(baseUrl.hostname)) {
    throw new Error("Local Agent Server URL must use loopback");
  }
  const token = process.env.AGENT_SERVER_LOCAL_TOKEN;
  if (!token?.trim()) throw new Error("Missing local Agent Server token");
  return `Bearer ${token}`;
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

function buildUpstreamUrl(baseUrl: URL, pathSegments: string[]): string {
  const encodedPath = pathSegments.map((segment) => encodeURIComponent(segment)).join("/");
  return new URL(encodedPath, baseUrl).toString();
}

function upstreamRequestHeaders(route: AgentRoute, authorization: string): Headers {
  const headers = new Headers({
    accept: route.kind === "events" ? "text/event-stream" : "application/json",
    authorization,
  });
  if (route.method === "POST") headers.set("content-type", "application/json");
  return headers;
}

function controlledResponseHeaders(upstream: Headers): Headers {
  const headers = new Headers();
  for (const name of ["content-type", "cache-control"]) {
    const value = upstream.get(name);
    if (value) headers.set(name, value);
  }
  return headers;
}
