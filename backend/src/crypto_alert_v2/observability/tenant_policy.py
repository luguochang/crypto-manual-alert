from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Literal


DEFAULT_RETENTION_DAYS = 30
MANDATORY_TRACE_STATUSES = frozenset({"blocked", "failed"})
_POLICY_METADATA_KEYS = frozenset(
    {
        "observability_trace_mode",
        "observability_sample_rate",
        "observability_full_capture_until",
        "sensitive_tenant",
    }
)
TraceMode = Literal["full", "hide_io", "disabled"]


@dataclass(frozen=True)
class TenantObservabilityPolicy:
    trace_mode: TraceMode = "full"
    sample_rate: float = 1.0
    retention_days: int = DEFAULT_RETENTION_DAYS

    @property
    def tracing_enabled(self) -> bool:
        return self.trace_mode != "disabled"

    @property
    def hide_io(self) -> bool:
        return self.trace_mode == "hide_io"

    @property
    def langfuse_enabled(self) -> bool:
        # Langfuse masking is shared by its process client. Sensitive request I/O
        # is therefore disabled rather than attached to the shared full-I/O client.
        return self.trace_mode == "full"


def anonymize_user_id(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    digest = sha256(candidate.encode("utf-8")).hexdigest()[:24]
    return f"anon-{digest}"


def resolve_tenant_policy(
    metadata: dict[str, Any],
) -> TenantObservabilityPolicy:
    requested_mode = metadata.get("observability_trace_mode", "full")
    if metadata.get("sensitive_tenant") is True and requested_mode == "full":
        requested_mode = "hide_io"
    trace_mode: TraceMode = (
        requested_mode
        if requested_mode in {"full", "hide_io", "disabled"}
        else "disabled"
    )
    raw_rate = metadata.get("observability_sample_rate", 1.0)
    try:
        sample_rate = float(raw_rate)
    except (TypeError, ValueError):
        sample_rate = 1.0
    sample_rate = min(1.0, max(0.0, sample_rate))
    return TenantObservabilityPolicy(
        trace_mode=trace_mode,
        sample_rate=sample_rate,
    )


def public_trace_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in metadata.items()
        if key not in _POLICY_METADATA_KEYS
    }


def is_mandatory_trace(
    *,
    terminal_status: str | None = None,
    negative_feedback: bool = False,
    release_proof: bool = False,
) -> bool:
    return (
        terminal_status in MANDATORY_TRACE_STATUSES
        or negative_feedback
        or release_proof
    )


def should_sample_trace(
    policy: TenantObservabilityPolicy,
    *,
    correlation_id: str,
    terminal_status: str | None = None,
    negative_feedback: bool = False,
    release_proof: bool = False,
    full_capture_until: datetime | None = None,
    now: datetime | None = None,
) -> bool:
    if not policy.tracing_enabled:
        return False
    if is_mandatory_trace(
        terminal_status=terminal_status,
        negative_feedback=negative_feedback,
        release_proof=release_proof,
    ):
        return True
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=UTC)
    if full_capture_until is not None and full_capture_until.tzinfo is None:
        full_capture_until = full_capture_until.replace(tzinfo=UTC)
    if full_capture_until is not None and current_time <= full_capture_until:
        return True
    if policy.sample_rate >= 1.0:
        return True
    if policy.sample_rate <= 0.0:
        return False
    bucket = int.from_bytes(
        sha256(correlation_id.encode("utf-8")).digest()[:8],
        byteorder="big",
    ) / float(2**64 - 1)
    return bucket < policy.sample_rate
