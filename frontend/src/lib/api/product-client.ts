import {
  analysisSubmissionSchema,
  forkSubmissionSchema,
  inboxCursorSchema,
  inboxQueryStatusSchema,
  inboxViewSchema,
  productRunListSchema,
  productTaskSchema,
  respondAllInterruptsSchema,
  type AnalysisSubmission,
  type ForkSubmission,
  type InboxQueryStatus,
  type InboxView,
  type ProductRunList,
  type ProductTask,
  type RespondAllInterrupts,
} from "@/lib/schemas/product-api";

type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export class ProductApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ProductApiError";
    this.status = status;
  }
}

export type ListInboxOptions = {
  status?: InboxQueryStatus;
  limit?: number;
  cursor?: string | null;
};

export async function createAnalysis(
  input: AnalysisSubmission,
  fetcher: Fetcher = fetch,
  idempotencyKey: string = crypto.randomUUID(),
): Promise<ProductTask> {
  const submission = analysisSubmissionSchema.parse(input);
  return requestTask(
    "/api/product/api/v2/analysis",
    {
      method: "POST",
      headers: {
        accept: "application/json",
        "content-type": "application/json",
        "idempotency-key": idempotencyKey,
      },
      body: JSON.stringify(submission),
    },
    fetcher,
  );
}

export async function getTask(
  taskId: string,
  fetcher: Fetcher = fetch,
  runId?: string,
): Promise<ProductTask> {
  const runSelection = runId
    ? `?run_id=${encodeURIComponent(runId)}`
    : "";
  return requestTask(
    `/api/product/api/v2/tasks/${encodeURIComponent(taskId)}${runSelection}`,
    {
      method: "GET",
      headers: { accept: "application/json" },
      cache: "no-store",
    },
    fetcher,
  );
}

export async function cancelTask(
  taskId: string,
  fetcher: Fetcher = fetch,
  idempotencyKey: string = crypto.randomUUID(),
): Promise<ProductTask> {
  return requestTask(
    `/api/product/api/v2/tasks/${encodeURIComponent(taskId)}/cancel`,
    {
      method: "POST",
      headers: {
        accept: "application/json",
        "idempotency-key": idempotencyKey,
      },
    },
    fetcher,
  );
}

export async function forkTask(
  taskId: string,
  input: ForkSubmission,
  fetcher: Fetcher = fetch,
  idempotencyKey: string = crypto.randomUUID(),
): Promise<ProductTask> {
  const submission = forkSubmissionSchema.parse(input);
  return requestTask(
    `/api/product/api/v2/tasks/${encodeURIComponent(taskId)}/fork`,
    {
      method: "POST",
      headers: {
        accept: "application/json",
        "content-type": "application/json",
        "idempotency-key": idempotencyKey,
      },
      body: JSON.stringify(submission),
    },
    fetcher,
  );
}

export async function respondAllInterrupts(
  taskId: string,
  input: RespondAllInterrupts,
  fetcher: Fetcher = fetch,
  idempotencyKey: string = crypto.randomUUID(),
): Promise<ProductTask> {
  const response = respondAllInterruptsSchema.parse(input);
  return requestTask(
    `/api/product/api/v2/tasks/${encodeURIComponent(taskId)}/interrupts/respond-all`,
    {
      method: "POST",
      headers: {
        accept: "application/json",
        "content-type": "application/json",
        "idempotency-key": idempotencyKey,
      },
      body: JSON.stringify(response),
    },
    fetcher,
  );
}

export async function listRuns(
  limit = 25,
  fetcher: Fetcher = fetch,
): Promise<ProductRunList> {
  const normalizedLimit = Math.max(1, Math.min(100, Math.trunc(limit)));
  const response = await fetcher(
    `/api/product/api/v2/runs?limit=${normalizedLimit}`,
    {
      method: "GET",
      headers: { accept: "application/json" },
      cache: "no-store",
    },
  );
  const body = await readJson(response);
  if (!response.ok) {
    throw new ProductApiError(readableDetail(body, response.status), response.status);
  }
  const parsed = productRunListSchema.safeParse(body);
  if (!parsed.success) {
    throw new ProductApiError("Product API returned an invalid Run list.", 502);
  }
  return parsed.data;
}

export async function listInbox(
  options: ListInboxOptions = {},
  fetcher: Fetcher = fetch,
): Promise<InboxView> {
  const status = inboxQueryStatusSchema.parse(options.status ?? "active");
  const requestedLimit = options.limit ?? 25;
  const normalizedLimit = Number.isFinite(requestedLimit)
    ? Math.max(1, Math.min(100, Math.trunc(requestedLimit)))
    : 25;
  const query = new URLSearchParams({
    status,
    limit: String(normalizedLimit),
  });
  if (options.cursor !== undefined && options.cursor !== null) {
    query.set("cursor", inboxCursorSchema.parse(options.cursor));
  }

  const response = await fetcher(
    `/api/product/api/v2/inbox?${query.toString()}`,
    {
      method: "GET",
      headers: { accept: "application/json" },
      cache: "no-store",
    },
  );
  const body = await readJson(response);
  if (!response.ok) {
    throw new ProductApiError(readableDetail(body, response.status), response.status);
  }
  const parsed = inboxViewSchema.safeParse(body);
  if (!parsed.success) {
    throw new ProductApiError("Product API returned an invalid Inbox view.", 502);
  }
  return parsed.data;
}

async function requestTask(path: string, init: RequestInit, fetcher: Fetcher): Promise<ProductTask> {
  const response = await fetcher(path, init);
  const body = await readJson(response);

  if (!response.ok) {
    throw new ProductApiError(readableDetail(body, response.status), response.status);
  }

  const parsed = productTaskSchema.safeParse(body);
  if (!parsed.success) {
    throw new ProductApiError("Product API returned an invalid response.", 502);
  }
  return parsed.data;
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
    typeof body === "object" &&
    body !== null &&
    "detail" in body &&
    typeof body.detail === "string" &&
    body.detail.trim()
  ) {
    return body.detail;
  }
  return `Product API request failed (${status}).`;
}
