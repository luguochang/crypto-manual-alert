from datetime import UTC, datetime
from uuid import uuid4

import pytest

from crypto_alert_v2.observability.config import ObservabilityRuntimeConfig
from crypto_alert_v2.observability.identity import (
    langfuse_trace_id_for_product_run,
)
from crypto_alert_v2.observability.planning import (
    plan_observability_delivery_intents,
)


def test_delivery_planning_uses_stable_product_identity_without_payloads() -> None:
    task_id = uuid4()
    run_id = uuid4()
    planned = plan_observability_delivery_intents(
        runtime=ObservabilityRuntimeConfig(
            environment="test",
            release="test",
            langsmith_enabled=True,
            langsmith_api_key="langsmith-planning-canary",
            langsmith_project="test-project",
            langfuse_enabled=True,
            langfuse_public_key="pk-test",
            langfuse_secret_key="langfuse-planning-canary",
        ),
        task_id=task_id,
        product_run_id=run_id,
        now=datetime(2026, 7, 17, tzinfo=UTC),
        verification_deadline_seconds=3_600,
    )

    assert [item.provider for item in planned] == ["langsmith", "langfuse"]
    assert all(item.status == "planned" for item in planned)
    assert all(item.correlation_id == planned[0].correlation_id for item in planned)
    assert planned[0].provider_trace_id is None
    assert planned[1].provider_trace_id == langfuse_trace_id_for_product_run(
        str(run_id)
    )
    assert all(str(task_id) in item.delivery_key for item in planned)
    assert all(str(run_id) in item.delivery_key for item in planned)
    rendered = repr(planned)
    assert "langsmith-planning-canary" not in rendered
    assert "langfuse-planning-canary" not in rendered


def test_disabled_providers_create_terminal_not_requested_rows() -> None:
    planned = plan_observability_delivery_intents(
        runtime=ObservabilityRuntimeConfig(environment="test", release="test"),
        task_id=uuid4(),
        product_run_id=uuid4(),
        now=datetime(2026, 7, 17, tzinfo=UTC),
        verification_deadline_seconds=3_600,
    )

    assert all(item.status == "not_requested" for item in planned)
    assert all(item.skip_reason == "provider_disabled" for item in planned)
    assert all(item.verification_deadline is None for item in planned)
    assert all(item.sampled is False for item in planned)


def test_enabled_provider_without_credentials_is_rejected() -> None:
    with pytest.raises(ValueError, match="LangSmith"):
        plan_observability_delivery_intents(
            runtime=ObservabilityRuntimeConfig(
                environment="test",
                release="test",
                langsmith_enabled=True,
            ),
            task_id=uuid4(),
            product_run_id=uuid4(),
            now=datetime(2026, 7, 17, tzinfo=UTC),
            verification_deadline_seconds=3_600,
        )
