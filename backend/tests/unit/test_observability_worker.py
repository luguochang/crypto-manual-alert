from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from crypto_alert_v2.observability.verification import (
    ObservabilityVerificationResult,
)
from crypto_alert_v2.persistence.repositories import ObservabilityDeliveryLease
from crypto_alert_v2.workers.observability import ObservabilityVerificationWorker


NOW = datetime(2026, 7, 17, tzinfo=UTC)


class FakeStore:
    def __init__(self, lease: ObservabilityDeliveryLease | None) -> None:
        self.lease = lease
        self.transitions: list[tuple[str, dict[str, Any]]] = []

    async def claim_next(self, **kwargs: Any) -> ObservabilityDeliveryLease | None:
        self.transitions.append(("claim", kwargs))
        lease, self.lease = self.lease, None
        return lease

    async def mark_verified(
        self, lease: ObservabilityDeliveryLease, **kwargs: Any
    ) -> bool:
        self.transitions.append(("verified", {"lease": lease, **kwargs}))
        return True

    async def mark_retryable(
        self, lease: ObservabilityDeliveryLease, **kwargs: Any
    ) -> bool:
        self.transitions.append(("retryable", {"lease": lease, **kwargs}))
        return True

    async def mark_terminal(
        self, lease: ObservabilityDeliveryLease, **kwargs: Any
    ) -> bool:
        self.transitions.append(("terminal", {"lease": lease, **kwargs}))
        return True

    async def release_owned_leases(self, **kwargs: Any) -> None:
        self.transitions.append(("release", kwargs))


class FakeVerifier:
    def __init__(self, result: ObservabilityVerificationResult) -> None:
        self.result = result
        self.requests: list[Any] = []

    async def verify(self, request: Any) -> ObservabilityVerificationResult:
        self.requests.append(request)
        return self.result


def lease(
    *,
    provider: str = "langfuse",
    trace_id: str | None = "a" * 32,
    deadline: datetime | None = NOW + timedelta(hours=1),
    attempt_count: int = 1,
) -> ObservabilityDeliveryLease:
    return ObservabilityDeliveryLease(
        delivery_id=uuid4(),
        provider=provider,
        event_type="root_trace",
        event_version=1,
        status="leased",
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        owner_user_id=uuid4(),
        task_id=uuid4(),
        run_id=uuid4(),
        correlation_id=str(uuid4()),
        delivery_key="delivery-key",
        provider_trace_id=trace_id,
        verification_deadline=deadline,
        attempt_count=attempt_count,
        fence_token=1,
        lease_owner="observability-worker",
        lease_expires_at=NOW + timedelta(seconds=30),
    )


def worker(
    store: FakeStore,
    verifier: FakeVerifier | None,
    *,
    provider: str = "langfuse",
    max_attempts: int = 30,
) -> ObservabilityVerificationWorker:
    return ObservabilityVerificationWorker(
        store=store,
        verifiers={} if verifier is None else {provider: verifier},
        worker_id="observability-worker",
        langsmith_project="crypto-alert-v2-test",
        clock=lambda: NOW,
        retry_seconds=5,
        max_attempts=max_attempts,
    )


@pytest.mark.asyncio
async def test_verified_hosted_trace_is_fenced_into_product_state() -> None:
    delivery = lease()
    store = FakeStore(delivery)
    verifier = FakeVerifier(
        ObservabilityVerificationResult(
            provider="langfuse",
            provider_trace_id="a" * 32,
            result="verified",
            code="hosted_trace_visible",
        )
    )

    assert await worker(store, verifier).dispatch_once() is True

    assert [item[0] for item in store.transitions] == ["claim", "verified"]
    assert store.transitions[-1][1]["provider_trace_id"] == "a" * 32
    assert verifier.requests[0].product_run_id == str(delivery.run_id)


@pytest.mark.asyncio
async def test_not_visible_trace_is_retried_without_replaying_trace() -> None:
    store = FakeStore(lease())
    verifier = FakeVerifier(
        ObservabilityVerificationResult(
            provider="langfuse",
            provider_trace_id="a" * 32,
            result="not_visible",
            code="hosted_trace_not_visible",
            error_type="not_found",
        )
    )

    assert await worker(store, verifier).dispatch_once() is True

    transition, values = store.transitions[-1]
    assert transition == "retryable"
    assert values["next_attempt_at"] == NOW + timedelta(seconds=5)
    assert values["error_code"] == "hosted_trace_not_visible"


@pytest.mark.asyncio
async def test_deadline_and_attempt_budget_terminalize_before_network_query() -> None:
    for delivery, code, max_attempts in (
        (lease(deadline=NOW), "hosted_verification_deadline_exceeded", 30),
        (lease(attempt_count=3), "hosted_verification_attempts_exhausted", 3),
    ):
        store = FakeStore(delivery)
        verifier = FakeVerifier(
            ObservabilityVerificationResult(
                provider="langfuse",
                provider_trace_id="a" * 32,
                result="verified",
                code="hosted_trace_visible",
            )
        )

        assert await worker(store, verifier, max_attempts=max_attempts).dispatch_once()
        assert store.transitions[-1][0] == "terminal"
        assert store.transitions[-1][1]["error_code"] == code
        assert verifier.requests == []


@pytest.mark.asyncio
async def test_terminal_provider_failure_does_not_retry_or_raise() -> None:
    store = FakeStore(lease())
    verifier = FakeVerifier(
        ObservabilityVerificationResult(
            provider="langfuse",
            provider_trace_id="a" * 32,
            result="terminal_failure",
            code="hosted_query_authentication_error",
            error_type="authentication",
        )
    )

    assert await worker(store, verifier).dispatch_once()
    assert store.transitions[-1][0] == "terminal"
    assert store.transitions[-1][1]["error_code"] == (
        "hosted_query_authentication_error"
    )


@pytest.mark.asyncio
async def test_missing_verifier_is_an_explicit_terminal_configuration_error() -> None:
    store = FakeStore(lease())

    assert await worker(store, None).dispatch_once()

    assert store.transitions[-1][0] == "terminal"
    assert store.transitions[-1][1]["error_code"] == "hosted_verifier_not_configured"


@pytest.mark.asyncio
async def test_release_owned_leases_delegates_to_durable_store() -> None:
    store = FakeStore(None)
    instance = worker(store, None)

    await instance.release_owned_leases()

    assert store.transitions == [
        ("release", {"worker_id": "observability-worker", "now": NOW})
    ]
