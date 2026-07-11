import { z } from "zod";
import {
  type ApiError,
  type ApiResult,
  envelopeSchema
} from "@/lib/schemas/api";

const DEFAULT_ERROR: ApiError = {
  code: "REQUEST_FAILED",
  message: "请求失败，请稍后重试"
};

function getApiBaseUrl() {
  const isServer = typeof window === "undefined";
  const baseUrl = isServer
    ? process.env.API_INTERNAL_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL
    : process.env.NEXT_PUBLIC_API_BASE_URL;

  if (!baseUrl) {
    throw new Error(
      isServer
        ? "缺少 frontend server-side API base；请设置 API_INTERNAL_BASE_URL 或 NEXT_PUBLIC_API_BASE_URL。"
        : "缺少 NEXT_PUBLIC_API_BASE_URL，前端不会读取任何 secret。"
    );
  }

  return baseUrl.replace(/\/$/, "");
}

function normalizeError(error: unknown): ApiError {
  if (error instanceof Error) {
    return { code: "CLIENT_ERROR", message: error.message };
  }

  return DEFAULT_ERROR;
}

function unwrapFastApiErrorEnvelope(json: unknown): unknown {
  if (!json || typeof json !== "object" || !("detail" in json)) {
    return json;
  }
  const detail = (json as { detail?: unknown }).detail;
  if (!detail || typeof detail !== "object" || !("ok" in detail)) {
    return json;
  }
  return detail;
}

// API 边界只接受后端统一信封，业务字段交给调用方 schema 校验。
export async function apiRequest<S extends z.ZodTypeAny>(
  path: string,
  schema: S,
  init?: RequestInit
): Promise<ApiResult<z.output<S>>> {
  try {
    const response = await fetch(`${getApiBaseUrl()}${path}`, {
      ...init,
      headers: {
        "content-type": "application/json",
        ...init?.headers
      },
      cache: "no-store"
    });
    const json = (await response.json()) as unknown;
    const envelope = envelopeSchema(schema).safeParse(unwrapFastApiErrorEnvelope(json));

    if (!envelope.success) {
      return {
        ok: false,
        error: {
          code: "INVALID_RESPONSE",
          message: "后端响应格式不符合约定",
          detail: envelope.error.flatten()
        }
      };
    }

    const parsed = envelope.data;
    const traceId = parsed.trace_id ?? null;

    if (!response.ok || !parsed.ok) {
      return {
        ok: false,
        error: parsed.error ?? {
          code: `HTTP_${response.status}`,
          message: response.statusText || DEFAULT_ERROR.message
        },
        traceId
      };
    }

    if (parsed.data === undefined) {
      return {
        ok: false,
        error: {
          code: "MISSING_DATA",
          message: "后端成功响应缺少 data 字段"
        },
        traceId
      };
    }

    return { ok: true, data: parsed.data, traceId };
  } catch (error) {
    return { ok: false, error: normalizeError(error) };
  }
}
