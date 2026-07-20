from __future__ import annotations

from collections.abc import Mapping, Sequence
from time import perf_counter
from typing import Any

from crypto_alert_v2.domain.models import ModelExecutionAudit


def start_model_timer() -> float:
    """Return a monotonic start point for one official agent invocation."""

    return perf_counter()


def build_model_execution_audit(
    result: Any,
    *,
    prompt_version: str,
    started_at: float,
) -> ModelExecutionAudit:
    """Extract non-sensitive usage and observation metadata from an agent result.

    LangChain's ``create_agent`` returns a mapping containing ``messages`` and
    ``structured_response``. Only the metadata fields exposed by LangChain are
    inspected here; message content and request payloads are deliberately ignored.
    """

    messages = result.get("messages", ()) if isinstance(result, Mapping) else ()
    if isinstance(messages, (str, bytes)) or not isinstance(messages, Sequence):
        messages = ()

    ai_messages = [message for message in messages if _is_ai_message(message)]
    usage = [_usage_metadata(message) for message in ai_messages]

    return ModelExecutionAudit(
        prompt_version=prompt_version,
        call_count=len(ai_messages),
        input_tokens=_sum_usage(usage, "input_tokens"),
        output_tokens=_sum_usage(usage, "output_tokens"),
        total_tokens=_sum_usage(usage, "total_tokens"),
        latency_ms=round(max(0.0, perf_counter() - started_at) * 1000, 3),
        observation_ids=_observation_ids(ai_messages),
    )


def _is_ai_message(message: Any) -> bool:
    message_type = getattr(message, "type", None)
    if message_type == "ai":
        return True
    if isinstance(message, Mapping):
        return message.get("type") == "ai" or message.get("role") == "assistant"
    return False


def _usage_metadata(message: Any) -> Mapping[str, Any]:
    usage = getattr(message, "usage_metadata", None)
    if isinstance(usage, Mapping):
        return usage
    if isinstance(message, Mapping) and isinstance(
        message.get("usage_metadata"), Mapping
    ):
        return message["usage_metadata"]
    return {}


def _sum_usage(values: Sequence[Mapping[str, Any]], key: str) -> int | None:
    numbers = [
        value
        for usage in values
        for value in [usage.get(key)]
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
    ]
    return sum(numbers) if numbers else None


def _observation_ids(messages: Sequence[Any]) -> list[str]:
    identifiers: list[str] = []
    for message in messages:
        metadata = getattr(message, "response_metadata", None)
        if not isinstance(metadata, Mapping) and isinstance(message, Mapping):
            metadata = message.get("response_metadata")
        if not isinstance(metadata, Mapping):
            continue
        observation_id = metadata.get("id")
        if not isinstance(observation_id, str) or not observation_id.strip():
            continue
        normalized = observation_id.strip()
        if normalized not in identifiers:
            identifiers.append(normalized)
    return identifiers
