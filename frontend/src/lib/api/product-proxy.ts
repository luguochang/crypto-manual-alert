import "server-only";

import { requiresAuthenticatedRuntime } from "@/lib/runtime/app-environment";

type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
export type AuthorizationResolver = (request: Request) => Promise<string | null>;

const defaultProductApiBaseUrl = "http://127.0.0.1:8123/app";
const defaultAgentServerAudience = "crypto-alert-agent-server";
const defaultProductApiTimeoutMs = 8_000;
const idempotencyKeyPattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$/;
const taskIdPattern = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
const watchlistSymbolPattern = /^(?:BTC|ETH|SOL)-USDT-SWAP$/;

export async function proxyProductRequest(
  request: Request,
  pathSegments: string[],
  fetcher: Fetcher = fetch,
  resolveAuthorization: AuthorizationResolver = defaultAuthorizationResolver,
): Promise<Response> {
  const requestId = transportRequestId();
  if (!isAllowedProductRoute(request.method, pathSegments)) {
    return withRequestId(
      Response.json({ detail: "Product API route not found." }, { status: 404 }),
      requestId,
    );
  }
  try {
    const upstreamUrl = buildUpstreamUrl(request, pathSegments);
    const authenticatedRuntime = requiresAuthenticatedRuntime();
    const authorization = localAuthorization(upstreamUrl, authenticatedRuntime)
      ?? await resolveAuthorization(request);
    if (authenticatedRuntime && authorization === null) {
      return withRequestId(
        Response.json({ detail: "Authentication required." }, { status: 401 }),
        requestId,
      );
    }
    const headers = buildServerOwnedHeaders(
      request,
      pathSegments,
      authorization,
      requestId,
    );
    const body = request.method === "GET" || request.method === "HEAD"
      ? undefined
      : await request.arrayBuffer();
    const upstreamSignal = AbortSignal.any([
      request.signal,
      AbortSignal.timeout(productApiTimeoutMs()),
    ]);
    const response = await fetcher(upstreamUrl, {
      method: request.method,
      headers,
      body: body && body.byteLength > 0 ? body : undefined,
      cache: "no-store",
      redirect: "manual",
      signal: upstreamSignal,
    });

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders(response.headers, requestId),
    });
  } catch {
    return withRequestId(
      Response.json(
        { detail: "Product API is temporarily unavailable." },
        { status: 502 },
      ),
      requestId,
    );
  }
}

function productApiTimeoutMs(): number {
  const configured = Number(process.env.PRODUCT_API_TIMEOUT_MS);
  return Number.isInteger(configured) && configured >= 100 && configured <= 30_000
    ? configured
    : defaultProductApiTimeoutMs;
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
  if (
    method === "GET" &&
    (path === "api/v2/health" || path === "api/v2/readiness")
  ) return true;
  if (
    process.env.V2_E2E_PROFILE === "failure-injection"
    && ["GET", "PUT", "DELETE"].includes(method)
    && path === "api/v2/testing/failure-scenario"
  ) return true;
  if (method === "GET" && path === "api/v2/auth/contexts") return true;
  if (method === "POST" && path === "api/v2/auth/context/select") return true;
  if (method === "GET" && path === "api/v2/runs") return true;
  if (method === "GET" && path === "api/v2/home") return true;
  if ((method === "GET" || method === "POST") && path === "api/v2/monitors") return true;
  if (method === "GET" && isMonitorTriggersRoute(pathSegments)) return true;
  if (method === "POST" && isMonitorActionRoute(pathSegments)) return true;
  if (method === "DELETE" && isMonitorMemberRoute(pathSegments)) return true;
  if ((method === "PUT" || method === "DELETE") && isWatchlistRoute(pathSegments)) return true;
  if (method === "GET" && path === "api/v2/artifacts") return true;
  if (method === "GET" && isArtifactReadRoute(pathSegments)) return true;
  if (method === "GET" && isRunReadRoute(pathSegments)) return true;
  if (method === "POST" && isRunCancelRoute(pathSegments)) return true;
  if (method === "POST" && isRunFeedbackRoute(pathSegments)) return true;
  if (method === "GET" && path === "api/v2/inbox") return true;
  if (method === "POST" && isInboxReviewRoute(pathSegments)) return true;
  if (
    (method === "GET" || method === "PATCH")
    && path === "api/v2/settings/notifications"
  ) return true;
  if (
    (method === "GET" || method === "PUT")
    && path === "api/v2/data-lifecycle/policy"
  ) return true;
  if (method === "POST" && path === "api/v2/data-lifecycle/exports") return true;
  if (method === "POST" && path === "api/v2/data-lifecycle/deletions") return true;
  if (method === "GET" && isDataLifecycleExportRoute(pathSegments)) return true;
  if (method === "GET" && isDataLifecycleDeletionRoute(pathSegments)) return true;
  if (method === "POST" && path === "api/v2/analysis") return true;
  if (method === "POST" && path === "api/v2/deep-research") return true;
  if (method === "POST" && isTaskCancelRoute(pathSegments)) return true;
  if (method === "POST" && isTaskRetryRoute(pathSegments)) return true;
  if (method === "POST" && isTaskForkRoute(pathSegments)) return true;
  if (method === "POST" && isInterruptRespondAllRoute(pathSegments)) return true;
  if (method === "GET" && isTaskNotificationsRoute(pathSegments)) return true;
  if (method === "POST" && isNotificationResendRoute(pathSegments)) return true;
  return method === "GET" && isTaskReadRoute(pathSegments);
}

function isTaskReadRoute(pathSegments: string[]): boolean {
  return pathSegments.length === 4
    && pathSegments[0] === "api"
    && pathSegments[1] === "v2"
    && pathSegments[2] === "tasks"
    && taskIdPattern.test(pathSegments[3] ?? "");
}

function isDataLifecycleExportRoute(pathSegments: string[]): boolean {
  const validShape = pathSegments.length === 5
    || (pathSegments.length === 6 && ["manifest", "bundle"].includes(pathSegments[5] ?? ""));
  return validShape
    && pathSegments[0] === "api"
    && pathSegments[1] === "v2"
    && pathSegments[2] === "data-lifecycle"
    && pathSegments[3] === "exports"
    && taskIdPattern.test(pathSegments[4] ?? "");
}

function isDataLifecycleDeletionRoute(pathSegments: string[]): boolean {
  return pathSegments.length === 5
    && pathSegments[0] === "api"
    && pathSegments[1] === "v2"
    && pathSegments[2] === "data-lifecycle"
    && pathSegments[3] === "deletions"
    && taskIdPattern.test(pathSegments[4] ?? "");
}

function isWatchlistRoute(pathSegments: string[]): boolean {
  return pathSegments.length === 4
    && pathSegments[0] === "api"
    && pathSegments[1] === "v2"
    && pathSegments[2] === "watchlist"
    && watchlistSymbolPattern.test(pathSegments[3] ?? "");
}

function isRunReadRoute(pathSegments: string[]): boolean {
  return pathSegments.length === 4
    && pathSegments[0] === "api"
    && pathSegments[1] === "v2"
    && pathSegments[2] === "runs"
    && taskIdPattern.test(pathSegments[3] ?? "");
}

function isRunCancelRoute(pathSegments: string[]): boolean {
  return pathSegments.length === 5
    && pathSegments[0] === "api"
    && pathSegments[1] === "v2"
    && pathSegments[2] === "runs"
    && taskIdPattern.test(pathSegments[3] ?? "")
    && pathSegments[4] === "cancel";
}

function isRunFeedbackRoute(pathSegments: string[]): boolean {
  return pathSegments.length === 5
    && pathSegments[0] === "api"
    && pathSegments[1] === "v2"
    && pathSegments[2] === "runs"
    && taskIdPattern.test(pathSegments[3] ?? "")
    && pathSegments[4] === "feedback";
}

function isArtifactReadRoute(pathSegments: string[]): boolean {
  return pathSegments.length === 4
    && pathSegments[0] === "api"
    && pathSegments[1] === "v2"
    && pathSegments[2] === "artifacts"
    && taskIdPattern.test(pathSegments[3] ?? "");
}

function isMonitorMemberRoute(pathSegments: string[]): boolean {
  return pathSegments.length === 4
    && pathSegments[0] === "api"
    && pathSegments[1] === "v2"
    && pathSegments[2] === "monitors"
    && taskIdPattern.test(pathSegments[3] ?? "");
}

function isMonitorTriggersRoute(pathSegments: string[]): boolean {
  return pathSegments.length === 5
    && isMonitorMemberRoute(pathSegments.slice(0, 4))
    && pathSegments[4] === "triggers";
}

function isMonitorActionRoute(pathSegments: string[]): boolean {
  return pathSegments.length === 5
    && isMonitorMemberRoute(pathSegments.slice(0, 4))
    && ["pause", "resume", "trigger"].includes(pathSegments[4] ?? "");
}

function isTaskCancelRoute(pathSegments: string[]): boolean {
  return pathSegments.length === 5
    && isTaskReadRoute(pathSegments.slice(0, 4))
    && pathSegments[4] === "cancel";
}

function isTaskRetryRoute(pathSegments: string[]): boolean {
  return pathSegments.length === 5
    && isTaskReadRoute(pathSegments.slice(0, 4))
    && pathSegments[4] === "retry";
}

function isTaskForkRoute(pathSegments: string[]): boolean {
  return pathSegments.length === 5
    && isTaskReadRoute(pathSegments.slice(0, 4))
    && pathSegments[4] === "fork";
}

function isTaskNotificationsRoute(pathSegments: string[]): boolean {
  return pathSegments.length === 5
    && isTaskReadRoute(pathSegments.slice(0, 4))
    && pathSegments[4] === "notifications";
}

function isNotificationResendRoute(pathSegments: string[]): boolean {
  return pathSegments.length === 5
    && pathSegments[0] === "api"
    && pathSegments[1] === "v2"
    && pathSegments[2] === "notifications"
    && taskIdPattern.test(pathSegments[3] ?? "")
    && pathSegments[4] === "resend";
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

function isInboxReviewRoute(pathSegments: string[]): boolean {
  return pathSegments.length === 5
    && pathSegments[0] === "api"
    && pathSegments[1] === "v2"
    && pathSegments[2] === "inbox"
    && taskIdPattern.test(pathSegments[3] ?? "")
    && pathSegments[4] === "respond";
}

async function defaultAuthorizationResolver(request: Request): Promise<string | null> {
  const {
    developmentBootstrapAuthorization,
    developmentBootstrapIdentityAuthorization,
    isDevelopmentBootstrapRuntime,
    resolveIdentityAuthorization,
    resolveInternalAuthorization,
  } = await import("@/lib/auth/bff-auth");
  if (
    !requiresAuthenticatedRuntime()
    && !isDevelopmentBootstrapRuntime()
  ) return null;
  const path = new URL(request.url).pathname;
  if (
    path.endsWith("/api/v2/auth/contexts")
    || path.endsWith("/api/v2/auth/context/select")
  ) {
    return developmentBootstrapIdentityAuthorization()
      ?? await resolveIdentityAuthorization(request);
  }
  const bootstrapAuthorization = developmentBootstrapAuthorization(
    agentServerAudience(),
  );
  if (bootstrapAuthorization) return bootstrapAuthorization;
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
  requestId: string,
): Headers {
  const headers = new Headers();
  for (const name of ["accept", "content-type", "if-none-match"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  headers.set("x-request-id", requestId);

  const path = pathSegments.join("/");
  if (
    (request.method === "POST" || request.method === "DELETE")
    && (
      path === "api/v2/analysis"
      || path === "api/v2/deep-research"
      || path === "api/v2/monitors"
      || isMonitorActionRoute(pathSegments)
      || (request.method === "DELETE" && isMonitorMemberRoute(pathSegments))
      || isTaskCancelRoute(pathSegments)
      || isRunCancelRoute(pathSegments)
      || isRunFeedbackRoute(pathSegments)
      || isTaskRetryRoute(pathSegments)
      || isTaskForkRoute(pathSegments)
      || isInterruptRespondAllRoute(pathSegments)
      || isInboxReviewRoute(pathSegments)
      || path === "api/v2/data-lifecycle/exports"
      || path === "api/v2/data-lifecycle/deletions"
    )
  ) {
    const idempotencyKey = request.headers.get("idempotency-key");
    if (idempotencyKey && idempotencyKeyPattern.test(idempotencyKey)) {
      headers.set("idempotency-key", idempotencyKey);
    }
  }

  if (authorization) headers.set("authorization", authorization);

  if (
    process.env.V2_E2E_PROFILE === "failure-injection"
    && process.env.FAILURE_INJECTION_ENABLED === "1"
    && ["GET", "PUT", "DELETE"].includes(request.method)
    && path === "api/v2/testing/failure-scenario"
  ) {
    const controlToken = request.headers.get("x-failure-injection-control-token");
    if (controlToken) headers.set("x-failure-injection-control-token", controlToken);
    if (request.method === "DELETE") {
      const generation = request.headers.get("x-failure-injection-generation");
      if (generation) headers.set("x-failure-injection-generation", generation);
    }
  }
  return headers;
}

function responseHeaders(upstreamHeaders: Headers, requestId: string): Headers {
  const headers = new Headers();
  for (const name of ["cache-control", "content-type", "etag", "x-upstream-request-id"]) {
    const value = upstreamHeaders.get(name);
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
