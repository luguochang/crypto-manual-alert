from __future__ import annotations

from hashlib import sha256
import json
from typing import Annotated, Any, Literal, Mapping

from langgraph.config import get_stream_writer
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


EventName = Literal[
    "task_progress",
    "artifact",
    "evidence",
    "usage",
    "notification",
    "quality",
]


class ProductEventBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    schema_version: Literal["1.0"] = "1.0"
    name: EventName
    event_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    sequence: int = Field(ge=1)
    correlation_id: str = Field(min_length=1, max_length=255)
    task_id: str = Field(min_length=1, max_length=255)
    run_id: str = Field(min_length=1, max_length=255)
    thread_id: str = Field(min_length=1, max_length=255)
    request_id: str = Field(min_length=1, max_length=255)


class TaskProgressEvent(ProductEventBase):
    name: Literal["task_progress"] = "task_progress"
    phase: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    status: Literal["active", "complete", "blocked", "failed"]


class ArtifactEvent(ProductEventBase):
    name: Literal["artifact"] = "artifact"
    status: Literal["draft", "committed"]
    content_version: int = Field(ge=1)


class EvidenceEvent(ProductEventBase):
    name: Literal["evidence"] = "evidence"
    stage: Literal["collected", "validated"]
    verified_source_count: int = Field(ge=0, le=1000)
    sufficient: bool | None = None


class UsageEvent(ProductEventBase):
    name: Literal["usage"] = "usage"
    model_call_count: int = Field(ge=0, le=1000)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    prompt_versions: list[str] = Field(default_factory=list, max_length=16)


class NotificationEvent(ProductEventBase):
    name: Literal["notification"] = "notification"
    status: Literal["requested", "not_requested"]


class QualityEvent(ProductEventBase):
    name: Literal["quality"] = "quality"
    evidence_sufficient: bool
    risk_allowed: bool
    warning_count: int = Field(ge=0, le=1000)
    blocked_reason_count: int = Field(ge=0, le=1000)


ProductCustomEvent = Annotated[
    TaskProgressEvent
    | ArtifactEvent
    | EvidenceEvent
    | UsageEvent
    | NotificationEvent
    | QualityEvent,
    Field(discriminator="name"),
]
_PRODUCT_EVENT_ADAPTER = TypeAdapter(ProductCustomEvent)


def parse_product_event(payload: object) -> ProductCustomEvent:
    return _PRODUCT_EVENT_ADAPTER.validate_python(payload)


def _bounded_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized if 1 <= len(normalized) <= 255 else None


def _identity(
    config: RunnableConfig,
    *,
    name: EventName,
    sequence: int,
) -> dict[str, Any] | None:
    metadata = config.get("metadata") or {}
    configurable = config.get("configurable") or {}
    if not isinstance(metadata, Mapping) or not isinstance(configurable, Mapping):
        return None
    task_id = _bounded_string(metadata.get("task_id"))
    run_id = _bounded_string(metadata.get("product_run_id"))
    thread_id = _bounded_string(
        metadata.get("thread_id") or configurable.get("thread_id")
    )
    request_id = _bounded_string(metadata.get("request_id"))
    correlation_id = _bounded_string(metadata.get("correlation_id"))
    if None in {task_id, run_id, thread_id, request_id, correlation_id}:
        return None
    stable_coordinates = {
        "schema_version": "1.0",
        "name": name,
        "sequence": sequence,
        "correlation_id": correlation_id,
        "task_id": task_id,
        "run_id": run_id,
        "thread_id": thread_id,
        "request_id": request_id,
    }
    event_id = sha256(
        json.dumps(
            stable_coordinates,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {**stable_coordinates, "event_id": event_id}


def _emit(
    config: RunnableConfig,
    event_type: type[ProductEventBase],
    *,
    name: EventName,
    sequence: int,
    **payload: Any,
) -> None:
    identity = _identity(config, name=name, sequence=sequence)
    if identity is None:
        return
    event = event_type.model_validate({**identity, **payload})
    get_stream_writer()(event.model_dump(mode="json"))


def emit_task_progress(
    config: RunnableConfig,
    *,
    sequence: int,
    phase: str,
    status: Literal["active", "complete", "blocked", "failed"],
) -> None:
    _emit(
        config,
        TaskProgressEvent,
        name="task_progress",
        sequence=sequence,
        phase=phase,
        status=status,
    )


def emit_artifact(
    config: RunnableConfig,
    *,
    sequence: int,
    status: Literal["draft", "committed"],
    content_version: int,
) -> None:
    _emit(
        config,
        ArtifactEvent,
        name="artifact",
        sequence=sequence,
        status=status,
        content_version=content_version,
    )


def emit_evidence(
    config: RunnableConfig,
    *,
    sequence: int,
    stage: Literal["collected", "validated"],
    verified_source_count: int,
    sufficient: bool | None = None,
) -> None:
    _emit(
        config,
        EvidenceEvent,
        name="evidence",
        sequence=sequence,
        stage=stage,
        verified_source_count=verified_source_count,
        sufficient=sufficient,
    )


def emit_usage(
    config: RunnableConfig,
    *,
    sequence: int,
    audits: list[dict[str, Any]],
) -> None:
    def total(field: str) -> int | None:
        values = [item.get(field) for item in audits]
        numeric = [value for value in values if isinstance(value, int) and value >= 0]
        return sum(numeric) if numeric else None

    prompt_versions = sorted(
        {
            value
            for item in audits
            if isinstance((value := item.get("prompt_version")), str) and value
        }
    )
    _emit(
        config,
        UsageEvent,
        name="usage",
        sequence=sequence,
        model_call_count=sum(
            value
            for item in audits
            if isinstance((value := item.get("call_count")), int) and value >= 0
        ),
        input_tokens=total("input_tokens"),
        output_tokens=total("output_tokens"),
        total_tokens=total("total_tokens"),
        prompt_versions=prompt_versions,
    )


def emit_notification(
    config: RunnableConfig,
    *,
    sequence: int,
    requested: bool,
) -> None:
    _emit(
        config,
        NotificationEvent,
        name="notification",
        sequence=sequence,
        status="requested" if requested else "not_requested",
    )


def emit_quality(
    config: RunnableConfig,
    *,
    sequence: int,
    evidence_sufficient: bool,
    risk_allowed: bool,
    warning_count: int,
    blocked_reason_count: int,
) -> None:
    _emit(
        config,
        QualityEvent,
        name="quality",
        sequence=sequence,
        evidence_sufficient=evidence_sufficient,
        risk_allowed=risk_allowed,
        warning_count=warning_count,
        blocked_reason_count=blocked_reason_count,
    )


__all__ = [
    "ArtifactEvent",
    "EvidenceEvent",
    "NotificationEvent",
    "ProductCustomEvent",
    "QualityEvent",
    "TaskProgressEvent",
    "UsageEvent",
    "emit_artifact",
    "emit_evidence",
    "emit_notification",
    "emit_quality",
    "emit_task_progress",
    "emit_usage",
    "parse_product_event",
]
