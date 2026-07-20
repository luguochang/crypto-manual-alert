import {
  createMonitorRequestSchema,
  monitorListSchema,
  monitorSchema,
  monitorStatusFilterSchema,
  monitorTriggerListSchema,
  monitorVersionMutationSchema,
  type CreateMonitorRequest,
  type Monitor,
  type MonitorList,
  type MonitorStatusFilter,
  type MonitorTriggerList,
  type MonitorVersionMutation,
} from "@/lib/schemas/monitor-api";

type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export class MonitorApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "MonitorApiError";
    this.status = status;
  }
}

export async function listMonitors(
  status: MonitorStatusFilter,
  fetcher: Fetcher = fetch,
): Promise<MonitorList> {
  const filter = monitorStatusFilterSchema.parse(status);
  return requestParsed(
    `/api/product/api/v2/monitors?status=${encodeURIComponent(filter)}`,
    {
      method: "GET",
      headers: { accept: "application/json" },
      cache: "no-store",
    },
    monitorListSchema,
    "Product API returned an invalid Monitor list.",
    fetcher,
  );
}

export async function createMonitor(
  input: CreateMonitorRequest,
  idempotencyKey: string,
  fetcher: Fetcher = fetch,
): Promise<Monitor> {
  const submission = createMonitorRequestSchema.parse(input);
  return requestMonitor(
    "/api/product/api/v2/monitors",
    {
      method: "POST",
      headers: mutationHeaders(idempotencyKey),
      body: JSON.stringify(submission),
    },
    fetcher,
  );
}

export async function listMonitorTriggers(
  monitorId: string,
  fetcher: Fetcher = fetch,
): Promise<MonitorTriggerList> {
  return requestParsed(
    `/api/product/api/v2/monitors/${encodeURIComponent(monitorId)}/triggers`,
    {
      method: "GET",
      headers: { accept: "application/json" },
      cache: "no-store",
    },
    monitorTriggerListSchema,
    "Product API returned an invalid Monitor trigger list.",
    fetcher,
  );
}

export async function pauseMonitor(
  monitorId: string,
  input: MonitorVersionMutation,
  idempotencyKey: string,
  fetcher: Fetcher = fetch,
): Promise<Monitor> {
  return requestMonitorMutation(monitorId, "pause", input, idempotencyKey, fetcher);
}

export async function resumeMonitor(
  monitorId: string,
  input: MonitorVersionMutation,
  idempotencyKey: string,
  fetcher: Fetcher = fetch,
): Promise<Monitor> {
  return requestMonitorMutation(monitorId, "resume", input, idempotencyKey, fetcher);
}

export async function triggerMonitor(
  monitorId: string,
  idempotencyKey: string,
  fetcher: Fetcher = fetch,
): Promise<Monitor> {
  return requestMonitor(
    `/api/product/api/v2/monitors/${encodeURIComponent(monitorId)}/trigger`,
    {
      method: "POST",
      headers: mutationHeaders(idempotencyKey),
    },
    fetcher,
  );
}

export async function deleteMonitor(
  monitorId: string,
  input: MonitorVersionMutation,
  idempotencyKey: string,
  fetcher: Fetcher = fetch,
): Promise<Monitor> {
  const submission = monitorVersionMutationSchema.parse(input);
  return requestMonitor(
    `/api/product/api/v2/monitors/${encodeURIComponent(monitorId)}`,
    {
      method: "DELETE",
      headers: mutationHeaders(idempotencyKey),
      body: JSON.stringify(submission),
    },
    fetcher,
  );
}

async function requestMonitorMutation(
  monitorId: string,
  action: "pause" | "resume",
  input: MonitorVersionMutation,
  idempotencyKey: string,
  fetcher: Fetcher,
): Promise<Monitor> {
  const submission = monitorVersionMutationSchema.parse(input);
  return requestMonitor(
    `/api/product/api/v2/monitors/${encodeURIComponent(monitorId)}/${action}`,
    {
      method: "POST",
      headers: mutationHeaders(idempotencyKey),
      body: JSON.stringify(submission),
    },
    fetcher,
  );
}

async function requestMonitor(
  path: string,
  init: RequestInit,
  fetcher: Fetcher,
): Promise<Monitor> {
  return requestParsed(
    path,
    init,
    monitorSchema,
    "Product API returned an invalid Monitor.",
    fetcher,
  );
}

async function requestParsed<T>(
  path: string,
  init: RequestInit,
  schema: { safeParse: (value: unknown) => { success: true; data: T } | { success: false } },
  invalidResponseMessage: string,
  fetcher: Fetcher,
): Promise<T> {
  const response = await fetcher(path, init);
  const body = await readJson(response);
  if (!response.ok) {
    throw new MonitorApiError(readableDetail(body, response.status), response.status);
  }
  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    throw new MonitorApiError(invalidResponseMessage, 502);
  }
  return parsed.data;
}

function mutationHeaders(idempotencyKey: string): HeadersInit {
  const normalizedKey = idempotencyKey.trim();
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$/.test(normalizedKey)) {
    throw new TypeError("Invalid Monitor idempotency key");
  }
  return {
    accept: "application/json",
    "content-type": "application/json",
    "idempotency-key": normalizedKey,
  };
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function readableDetail(body: unknown, status: number): string {
  if (
    typeof body === "object"
    && body !== null
    && "detail" in body
    && typeof body.detail === "string"
    && body.detail.trim()
  ) return body.detail.trim();
  return `Monitor API request failed (${status}).`;
}
