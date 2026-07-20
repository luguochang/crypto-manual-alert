from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from crypto_alert_v2.api.request_identity import correlation_id_for_task
from crypto_alert_v2.observability.config import ObservabilityRuntimeConfig
from crypto_alert_v2.observability.identity import (
    langfuse_trace_id_for_product_run,
)
from crypto_alert_v2.persistence.repositories import ObservabilityDeliveryIntent


def plan_observability_delivery_intents(
    *,
    runtime: ObservabilityRuntimeConfig,
    task_id: UUID,
    product_run_id: UUID,
    now: datetime,
    verification_deadline_seconds: int,
) -> tuple[ObservabilityDeliveryIntent, ...]:
    if now.tzinfo is None:
        raise ValueError("observability intent time must be timezone-aware")
    if verification_deadline_seconds < 30:
        raise ValueError(
            "observability verification deadline must be at least 30 seconds"
        )
    if runtime.langsmith_enabled and not runtime.langsmith_api_key:
        raise ValueError("LangSmith delivery is enabled without credentials")
    if runtime.langfuse_enabled and (
        not runtime.langfuse_public_key or not runtime.langfuse_secret_key
    ):
        raise ValueError("Langfuse delivery is enabled without credentials")

    run_id = str(product_run_id)
    correlation_id = correlation_id_for_task(task_id)
    deadline = now + timedelta(seconds=verification_deadline_seconds)
    return (
        _intent(
            provider="langsmith",
            enabled=runtime.langsmith_enabled,
            task_id=task_id,
            product_run_id=product_run_id,
            correlation_id=correlation_id,
            provider_trace_id=None,
            deadline=deadline,
        ),
        _intent(
            provider="langfuse",
            enabled=runtime.langfuse_enabled,
            task_id=task_id,
            product_run_id=product_run_id,
            correlation_id=correlation_id,
            provider_trace_id=(
                langfuse_trace_id_for_product_run(run_id)
                if runtime.langfuse_enabled
                else None
            ),
            deadline=deadline,
        ),
    )


def _intent(
    *,
    provider: str,
    enabled: bool,
    task_id: UUID,
    product_run_id: UUID,
    correlation_id: str,
    provider_trace_id: str | None,
    deadline: datetime,
) -> ObservabilityDeliveryIntent:
    return ObservabilityDeliveryIntent(
        provider=provider,
        status="planned" if enabled else "not_requested",
        skip_reason=None if enabled else "provider_disabled",
        sampled=enabled,
        provider_trace_id=provider_trace_id,
        verification_deadline=deadline if enabled else None,
        delivery_key=(f"root-trace:v1:{task_id}:{product_run_id}:{provider}"),
        correlation_id=correlation_id,
    )


__all__ = ["plan_observability_delivery_intents"]
