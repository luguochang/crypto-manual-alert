const DEFAULT_SAFE_ERROR = "请求暂时无法完成，请稍后重试。";
const DEFAULT_SAFE_CONTENT = "内容已记录，当前摘要不可读；请以提醒摘要、价位、风险和通知状态为准。";

export const UNSAFE_DISPLAY_PATTERN =
  /SQLITE|Traceback|stack trace|\/(?:Users|var|private|opt|etc|home|srv|app|tmp|Volumes)\/|[A-Za-z]:\\|\.db\b|trace_id|request_json|response_json|parsed_plan|payload|BARK_DEVICE_KEY|device_key|https:\/\/api\.day\.app|Authorization\s*:\s*(?:Basic|Bearer)|Bearer\s+|(?:api[_-]?key|secret|access[_-]?token|refresh[_-]?token|token)\s*[:=]|ECONNREFUSED|ENOTFOUND|Failed to fetch|fetch failed|NetworkError|后端响应格式|invalid response|ZodError|invalid_type/i;

export function safeDisplayError(error: unknown, fallback = DEFAULT_SAFE_ERROR): string {
  const message = extractErrorMessage(error);
  if (!message) {
    return fallback;
  }
  if (hasUnsafeDisplayText(message)) {
    return fallback;
  }
  return message;
}

export function safeDisplayContent(value: unknown, fallback = DEFAULT_SAFE_CONTENT): string {
  const message = extractErrorMessage(value);
  if (!message) {
    return fallback;
  }
  return hasUnsafeDisplayText(message) ? fallback : message;
}

export function hasUnsafeDisplayText(value: unknown): boolean {
  return typeof value === "string" && UNSAFE_DISPLAY_PATTERN.test(value);
}

export function extractErrorMessage(error: unknown): string {
  if (typeof error === "string") {
    return error.trim();
  }
  if (error instanceof Error) {
    return error.message.trim();
  }
  if (error && typeof error === "object" && "message" in error) {
    const value = (error as { message?: unknown }).message;
    return typeof value === "string" ? value.trim() : "";
  }
  return "";
}
