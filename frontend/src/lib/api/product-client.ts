import {
  analysisSubmissionSchema,
  deepResearchSubmissionSchema,
  artifactDetailSchema,
  artifactLibrarySchema,
  feedbackSchema,
  feedbackSubmissionSchema,
  forkSubmissionSchema,
  homeViewSchema,
  inboxCursorSchema,
  inboxReviewReceiptSchema,
  inboxReviewSubmissionSchema,
  inboxQueryStatusSchema,
  inboxViewSchema,
  notificationListSchema,
  notificationResendSubmissionSchema,
  notificationSchema,
  notificationSettingsSchema,
  notificationSettingsUpdateSchema,
  dataDeletionSchema,
  dataExportBundleSchema,
  dataExportManifestSchema,
  dataExportSchema,
  dataLifecyclePolicySchema,
  dataLifecyclePolicyUpdateSchema,
  productRunListSchema,
  productTaskSchema,
  runDetailSchema,
  respondAllInterruptsSchema,
  type AnalysisSubmission,
  type DeepResearchSubmission,
  type ArtifactDetail,
  type ArtifactLibrary,
  type Feedback,
  type FeedbackSubmission,
  type ForkSubmission,
  type HomeView,
  type InboxReviewReceipt,
  type InboxReviewSubmission,
  type InboxQueryStatus,
  type InboxView,
  type Notification,
  type NotificationList,
  type NotificationResendSubmission,
  type NotificationSettings,
  type NotificationSettingsUpdate,
  type DataDeletion,
  type DataExport,
  type DataExportBundle,
  type DataExportManifest,
  type DataLifecyclePolicy,
  type DataLifecyclePolicyUpdate,
  type ProductRunList,
  type ProductTask,
  type RunDetail,
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

export async function createDeepResearch(
  input: DeepResearchSubmission,
  fetcher: Fetcher = fetch,
  idempotencyKey: string = crypto.randomUUID(),
): Promise<ProductTask> {
  const submission = deepResearchSubmissionSchema.parse(input);
  return requestTask(
    "/api/product/api/v2/deep-research",
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

export async function cancelRun(
  runId: string,
  fetcher: Fetcher = fetch,
  idempotencyKey: string = crypto.randomUUID(),
): Promise<ProductTask> {
  return requestTask(
    `/api/product/api/v2/runs/${encodeURIComponent(runId)}/cancel`,
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

export async function retryTask(
  taskId: string,
  fetcher: Fetcher = fetch,
  idempotencyKey: string = crypto.randomUUID(),
): Promise<ProductTask> {
  return requestTask(
    `/api/product/api/v2/tasks/${encodeURIComponent(taskId)}/retry`,
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

export async function respondInboxReview(
  pauseId: string,
  input: InboxReviewSubmission,
  fetcher: Fetcher = fetch,
  idempotencyKey: string = crypto.randomUUID(),
): Promise<InboxReviewReceipt> {
  const submission = inboxReviewSubmissionSchema.parse(input);
  const response = await fetcher(
    `/api/product/api/v2/inbox/${encodeURIComponent(pauseId)}/respond`,
    {
      method: "POST",
      headers: {
        accept: "application/json",
        "content-type": "application/json",
        "idempotency-key": idempotencyKey,
      },
      body: JSON.stringify(submission),
    },
  );
  const body = await readJson(response);
  if (!response.ok) {
    throw new ProductApiError(readableDetail(body, response.status), response.status);
  }
  const parsed = inboxReviewReceiptSchema.safeParse(body);
  if (!parsed.success) {
    throw new ProductApiError("Product API returned an invalid Inbox review receipt.", 502);
  }
  return parsed.data;
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

export async function getRun(
  runId: string,
  fetcher: Fetcher = fetch,
): Promise<RunDetail> {
  const response = await fetcher(
    `/api/product/api/v2/runs/${encodeURIComponent(runId)}`,
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
  const parsed = runDetailSchema.safeParse(body);
  if (!parsed.success) {
    throw new ProductApiError("Product API returned an invalid Run detail.", 502);
  }
  return parsed.data;
}

export async function submitFeedback(
  runId: string,
  input: FeedbackSubmission,
  fetcher: Fetcher = fetch,
  idempotencyKey: string = crypto.randomUUID(),
): Promise<Feedback> {
  const submission = feedbackSubmissionSchema.parse(input);
  const response = await fetcher(
    `/api/product/api/v2/runs/${encodeURIComponent(runId)}/feedback`,
    {
      method: "POST",
      headers: {
        accept: "application/json",
        "content-type": "application/json",
        "idempotency-key": idempotencyKey,
      },
      body: JSON.stringify(submission),
    },
  );
  const body = await readJson(response);
  if (!response.ok) {
    throw new ProductApiError(readableDetail(body, response.status), response.status);
  }
  const parsed = feedbackSchema.safeParse(body);
  if (!parsed.success) {
    throw new ProductApiError("Product API returned an invalid feedback response.", 502);
  }
  return parsed.data;
}

export async function listArtifacts(
  limit = 25,
  fetcher: Fetcher = fetch,
): Promise<ArtifactLibrary> {
  const normalizedLimit = Math.max(1, Math.min(100, Math.trunc(limit)));
  const response = await fetcher(
    `/api/product/api/v2/artifacts?limit=${normalizedLimit}`,
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
  const parsed = artifactLibrarySchema.safeParse(body);
  if (!parsed.success) {
    throw new ProductApiError("Product API returned an invalid Artifact library.", 502);
  }
  return parsed.data;
}

export async function getHome(
  fetcher: Fetcher = fetch,
): Promise<HomeView> {
  const response = await fetcher(
    "/api/product/api/v2/home",
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
  const parsed = homeViewSchema.safeParse(body);
  if (!parsed.success) {
    throw new ProductApiError("Product API returned an invalid Home view.", 502);
  }
  return parsed.data;
}

export async function setWatchlistSymbol(
  symbol: HomeView["watchlist"][number]["symbol"],
  included: boolean,
  fetcher: Fetcher = fetch,
): Promise<HomeView> {
  const response = await fetcher(
    `/api/product/api/v2/watchlist/${encodeURIComponent(symbol)}`,
    {
      method: included ? "PUT" : "DELETE",
      headers: { accept: "application/json" },
      cache: "no-store",
    },
  );
  const body = await readJson(response);
  if (!response.ok) {
    throw new ProductApiError(readableDetail(body, response.status), response.status);
  }
  const parsed = homeViewSchema.safeParse(body);
  if (!parsed.success) {
    throw new ProductApiError("Product API returned an invalid Home view.", 502);
  }
  return parsed.data;
}

export async function getArtifact(
  artifactId: string,
  versionNumber?: number,
  fetcher: Fetcher = fetch,
): Promise<ArtifactDetail> {
  const query = versionNumber ? `?version_number=${versionNumber}` : "";
  const response = await fetcher(
    `/api/product/api/v2/artifacts/${encodeURIComponent(artifactId)}${query}`,
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
  const parsed = artifactDetailSchema.safeParse(body);
  if (!parsed.success) {
    throw new ProductApiError("Product API returned an invalid Artifact detail.", 502);
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

export async function listNotifications(
  taskId: string,
  fetcher: Fetcher = fetch,
): Promise<NotificationList> {
  const response = await fetcher(
    `/api/product/api/v2/tasks/${encodeURIComponent(taskId)}/notifications`,
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
  const parsed = notificationListSchema.safeParse(body);
  if (!parsed.success) {
    throw new ProductApiError("Product API returned an invalid notification list.", 502);
  }
  return parsed.data;
}

export async function requestNotificationResend(
  notificationId: string,
  input: NotificationResendSubmission,
  fetcher: Fetcher = fetch,
): Promise<Notification> {
  const submission = notificationResendSubmissionSchema.parse(input);
  const response = await fetcher(
    `/api/product/api/v2/notifications/${encodeURIComponent(notificationId)}/resend`,
    {
      method: "POST",
      headers: {
        accept: "application/json",
        "content-type": "application/json",
      },
      body: JSON.stringify(submission),
    },
  );
  const body = await readJson(response);
  if (!response.ok) {
    throw new ProductApiError(readableDetail(body, response.status), response.status);
  }
  const parsed = notificationSchema.safeParse(body);
  if (!parsed.success) {
    throw new ProductApiError("Product API returned an invalid notification status.", 502);
  }
  return parsed.data;
}

export async function getNotificationSettings(
  fetcher: Fetcher = fetch,
): Promise<NotificationSettings> {
  return requestNotificationSettings(
    {
      method: "GET",
      headers: { accept: "application/json" },
      cache: "no-store",
    },
    fetcher,
  );
}

export async function updateNotificationSettings(
  input: NotificationSettingsUpdate,
  fetcher: Fetcher = fetch,
): Promise<NotificationSettings> {
  const submission = notificationSettingsUpdateSchema.parse(input);
  return requestNotificationSettings(
    {
      method: "PATCH",
      headers: {
        accept: "application/json",
        "content-type": "application/json",
      },
      body: JSON.stringify(submission),
    },
    fetcher,
  );
}

export async function getDataLifecyclePolicy(
  fetcher: Fetcher = fetch,
): Promise<DataLifecyclePolicy> {
  const response = await fetcher(
    "/api/product/api/v2/data-lifecycle/policy",
    { method: "GET", headers: { accept: "application/json" }, cache: "no-store" },
  );
  return parseLifecycleResponse(response, dataLifecyclePolicySchema, "data lifecycle policy");
}

export async function updateDataLifecyclePolicy(
  input: DataLifecyclePolicyUpdate,
  fetcher: Fetcher = fetch,
): Promise<DataLifecyclePolicy> {
  const submission = dataLifecyclePolicyUpdateSchema.parse(input);
  const response = await fetcher(
    "/api/product/api/v2/data-lifecycle/policy",
    {
      method: "PUT",
      headers: { accept: "application/json", "content-type": "application/json" },
      body: JSON.stringify(submission),
    },
  );
  return parseLifecycleResponse(response, dataLifecyclePolicySchema, "data lifecycle policy");
}

export async function createDataExport(
  fetcher: Fetcher = fetch,
  idempotencyKey: string = crypto.randomUUID(),
): Promise<DataExport> {
  const response = await fetcher(
    "/api/product/api/v2/data-lifecycle/exports",
    {
      method: "POST",
      headers: {
        accept: "application/json",
        "content-type": "application/json",
        "idempotency-key": idempotencyKey,
      },
      body: JSON.stringify({ scope: "user_data" }),
    },
  );
  return parseLifecycleResponse(response, dataExportSchema, "data export");
}

export async function getDataExport(
  exportId: string,
  fetcher: Fetcher = fetch,
): Promise<DataExport> {
  const response = await fetcher(
    `/api/product/api/v2/data-lifecycle/exports/${encodeURIComponent(exportId)}`,
    { method: "GET", headers: { accept: "application/json" }, cache: "no-store" },
  );
  return parseLifecycleResponse(response, dataExportSchema, "data export");
}

export async function getDataExportManifest(
  exportId: string,
  fetcher: Fetcher = fetch,
): Promise<DataExportManifest> {
  const response = await fetcher(
    `/api/product/api/v2/data-lifecycle/exports/${encodeURIComponent(exportId)}/manifest`,
    { method: "GET", headers: { accept: "application/json" }, cache: "no-store" },
  );
  return parseLifecycleResponse(response, dataExportManifestSchema, "data export manifest");
}

export async function getDataExportBundle(
  exportId: string,
  fetcher: Fetcher = fetch,
): Promise<DataExportBundle> {
  const response = await fetcher(
    `/api/product/api/v2/data-lifecycle/exports/${encodeURIComponent(exportId)}/bundle`,
    { method: "GET", headers: { accept: "application/json" }, cache: "no-store" },
  );
  return parseLifecycleResponse(response, dataExportBundleSchema, "data export bundle");
}

export async function createDataDeletion(
  confirmation: "DELETE MY DATA",
  fetcher: Fetcher = fetch,
  idempotencyKey: string = crypto.randomUUID(),
): Promise<DataDeletion> {
  const response = await fetcher(
    "/api/product/api/v2/data-lifecycle/deletions",
    {
      method: "POST",
      headers: {
        accept: "application/json",
        "content-type": "application/json",
        "idempotency-key": idempotencyKey,
      },
      body: JSON.stringify({ scope: "user_data", confirmation }),
    },
  );
  return parseLifecycleResponse(response, dataDeletionSchema, "data deletion");
}

export async function getDataDeletion(
  deletionId: string,
  fetcher: Fetcher = fetch,
): Promise<DataDeletion> {
  const response = await fetcher(
    `/api/product/api/v2/data-lifecycle/deletions/${encodeURIComponent(deletionId)}`,
    { method: "GET", headers: { accept: "application/json" }, cache: "no-store" },
  );
  return parseLifecycleResponse(response, dataDeletionSchema, "data deletion");
}

async function parseLifecycleResponse<T>(
  response: Response,
  schema: { safeParse: (value: unknown) => { success: boolean; data?: T } },
  label: string,
): Promise<T> {
  const body = await readJson(response);
  if (!response.ok) {
    throw new ProductApiError(readableDetail(body, response.status), response.status);
  }
  const parsed = schema.safeParse(body);
  if (!parsed.success || parsed.data === undefined) {
    throw new ProductApiError(`Product API returned an invalid ${label}.`, 502);
  }
  return parsed.data;
}

async function requestNotificationSettings(
  init: RequestInit,
  fetcher: Fetcher,
): Promise<NotificationSettings> {
  const response = await fetcher(
    "/api/product/api/v2/settings/notifications",
    init,
  );
  const body = await readJson(response);
  if (!response.ok) {
    throw new ProductApiError(readableDetail(body, response.status), response.status);
  }
  const parsed = notificationSettingsSchema.safeParse(body);
  if (!parsed.success) {
    throw new ProductApiError(
      "Product API returned invalid notification settings.",
      502,
    );
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
