from __future__ import annotations

import hashlib
import json
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator

from crypto_manual_alert.storage.journal import Journal


SECRET_KEY_HINTS = ("api_key", "authorization", "secret", "token", "passphrase", "device_key", "bark")
MAX_STORED_CHARS = 12000


@dataclass(frozen=True)
class ActiveObservability:
    recorder: "ObservabilityRecorder"
    trace_id: str


@dataclass(frozen=True)
class ActiveSpan:
    trace_id: str
    span_id: str


_active_observability: ContextVar[ActiveObservability | None] = ContextVar("active_observability", default=None)
_active_span: ContextVar[ActiveSpan | None] = ContextVar("active_span", default=None)


@contextmanager
def use_observability(recorder: "ObservabilityRecorder", trace_id: str) -> Iterator[None]:
    token = _active_observability.set(ActiveObservability(recorder=recorder, trace_id=trace_id))
    try:
        yield
    finally:
        _active_observability.reset(token)


def record_llm_interaction(
    *,
    component: str,
    provider: str,
    model: str,
    request_payload: dict[str, Any],
    response_payload: dict[str, Any] | None = None,
    status: str = "ok",
    endpoint: str = "",
    error: Exception | None = None,
    duration_ms: int | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    cost_usd: float | None = None,
    finish_reason: str | None = None,
    retry_count: int = 0,
    metadata: dict[str, Any] | None = None,
) -> None:
    active = _active_observability.get()
    if active is None:
        return
    active.recorder.record_llm_interaction(
        trace_id=active.trace_id,
        component=component,
        provider=provider,
        model=model,
        request_payload=request_payload,
        response_payload=response_payload,
        status=status,
        endpoint=endpoint,
        error=error,
        duration_ms=duration_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=cost_usd,
        finish_reason=finish_reason,
        retry_count=retry_count,
        metadata=metadata,
    )


@dataclass
class SpanHandle:
    recorder: "ObservabilityRecorder"
    trace_id: str
    span_id: str
    span_name: str
    span_type: str
    started_at: datetime
    input_summary: Any = None
    output_summary: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def set_output(self, output_summary: Any) -> None:
        self.output_summary = output_summary


class ObservabilityRecorder:
    def __init__(self, journal: Journal):
        self.journal = journal

    def start_trace(
        self,
        *,
        run_type: str,
        symbol: str,
        horizon: str | None = None,
        metadata: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> str:
        trace_id = trace_id or uuid.uuid4().hex
        self.journal.append_trace(
            trace_id=trace_id,
            created_at=_now_iso(),
            run_type=run_type,
            symbol=symbol,
            horizon=horizon,
            status="running",
            metadata=metadata or {},
        )
        return trace_id

    def finish_trace(
        self,
        trace_id: str,
        *,
        status: str,
        final_plan_id: str | None = None,
        final_action: str | None = None,
        allowed: bool | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.journal.finish_trace(
            trace_id=trace_id,
            ended_at=_now_iso(),
            status=status,
            final_plan_id=final_plan_id,
            final_action=final_action,
            allowed=allowed,
            metadata=metadata or {},
        )

    @contextmanager
    def span(
        self,
        trace_id: str,
        span_name: str,
        span_type: str,
        input_summary: Any = None,
        parent_span_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[SpanHandle]:
        started_at = datetime.now(timezone.utc)
        started_perf = time.perf_counter()
        handle = SpanHandle(
            recorder=self,
            trace_id=trace_id,
            span_id=uuid.uuid4().hex,
            span_name=span_name,
            span_type=span_type,
            started_at=started_at,
            input_summary=input_summary,
            metadata=metadata or {},
        )
        span_token = _active_span.set(ActiveSpan(trace_id=trace_id, span_id=handle.span_id))
        try:
            yield handle
        except Exception as exc:
            self.journal.append_trace_span(
                span_id=handle.span_id,
                trace_id=trace_id,
                parent_span_id=parent_span_id,
                span_name=span_name,
                span_type=span_type,
                started_at=started_at.isoformat(),
                ended_at=_now_iso(),
                duration_ms=_duration_ms(started_perf),
                status="error",
                input_summary=handle.input_summary,
                output_summary=handle.output_summary,
                error_type=type(exc).__name__,
                error_message=str(exc),
                metadata=handle.metadata,
            )
            raise
        else:
            self.journal.append_trace_span(
                span_id=handle.span_id,
                trace_id=trace_id,
                parent_span_id=parent_span_id,
                span_name=span_name,
                span_type=span_type,
                started_at=started_at.isoformat(),
                ended_at=_now_iso(),
                duration_ms=_duration_ms(started_perf),
                status="ok",
                input_summary=handle.input_summary,
                output_summary=handle.output_summary,
                error_type=None,
                error_message=None,
                metadata=handle.metadata,
            )
        finally:
            _active_span.reset(span_token)

    def record_llm_interaction(
        self,
        *,
        trace_id: str,
        span_id: str | None = None,
        component: str,
        provider: str,
        model: str,
        request_payload: dict[str, Any],
        response_payload: dict[str, Any] | None = None,
        status: str = "ok",
        endpoint: str = "",
        error: Exception | None = None,
        duration_ms: int | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        cost_usd: float | None = None,
        finish_reason: str | None = None,
        retry_count: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        sanitized_request = _sanitize(request_payload)
        sanitized_response = _sanitize(response_payload or {})
        request_json = _compact_json(sanitized_request)
        response_json = _compact_json(sanitized_response)
        active_span = _active_span.get()
        linked_span_id = span_id or (
            active_span.span_id if active_span is not None and active_span.trace_id == trace_id else None
        )
        self.journal.append_llm_interaction(
            trace_id=trace_id,
            span_id=linked_span_id,
            created_at=_now_iso(),
            component=component,
            provider=provider,
            model=model,
            endpoint=endpoint,
            status=status,
            input_hash=_hash_text(request_json),
            output_hash=_hash_text(response_json),
            input_summary=_summarize_payload(sanitized_request),
            output_summary=_summarize_payload(sanitized_response),
            request_json=request_json,
            response_json=response_json,
            error_type=type(error).__name__ if error else None,
            error_message=str(error) if error else None,
            duration_ms=duration_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            finish_reason=finish_reason,
            retry_count=retry_count,
            metadata=metadata or {},
        )


def _duration_ms(started_perf: float) -> int:
    return int((time.perf_counter() - started_perf) * 1000)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _compact_json(payload: Any) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    if len(text) <= MAX_STORED_CHARS:
        return text
    half = (MAX_STORED_CHARS - 80) // 2
    return f"{text[:half]}...[truncated for observability storage]...{text[-half:]}"


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).lower()
            if any(hint in normalized for hint in SECRET_KEY_HINTS):
                sanitized[str(key)] = "<redacted>"
            else:
                sanitized[str(key)] = _sanitize(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _summarize_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        summary: dict[str, Any] = {"type": "object", "keys": sorted(str(key) for key in payload)[:20]}
        messages = payload.get("messages")
        if isinstance(messages, list):
            summary["messages"] = [
                {
                    "role": item.get("role"),
                    "content_chars": len(str(item.get("content") or "")),
                }
                for item in messages
                if isinstance(item, dict)
            ][:10]
        if "input" in payload:
            summary["input_chars"] = len(str(payload.get("input") or ""))
        return summary
    if isinstance(payload, list):
        return {"type": "array", "items": len(payload)}
    return {"type": type(payload).__name__, "chars": len(str(payload))}
