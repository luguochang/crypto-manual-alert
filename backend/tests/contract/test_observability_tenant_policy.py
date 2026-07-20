from datetime import UTC, datetime, timedelta

import pytest

from crypto_alert_v2.observability.callbacks import create_observability_config_factory
from crypto_alert_v2.observability.config import ObservabilityRuntimeConfig
from crypto_alert_v2.observability.tenant_policy import (
    DEFAULT_RETENTION_DAYS,
    anonymize_user_id,
    public_trace_metadata,
    resolve_tenant_policy,
    should_sample_trace,
)


def test_sensitive_tenant_hides_langsmith_io_and_disables_langfuse_io() -> None:
    policy = resolve_tenant_policy(
        {"tenant_id": "sensitive-tenant", "sensitive_tenant": True}
    )

    assert policy.trace_mode == "hide_io"
    assert policy.hide_io is True
    assert policy.tracing_enabled is True
    assert policy.langfuse_enabled is False
    assert policy.retention_days == DEFAULT_RETENTION_DAYS == 30


def test_tenant_can_disable_all_external_tracing() -> None:
    policy = resolve_tenant_policy({"observability_trace_mode": "disabled"})

    assert policy.tracing_enabled is False
    assert policy.langfuse_enabled is False


def test_policy_controls_are_not_exported_as_trace_metadata() -> None:
    metadata = {
        "tenant_id": "tenant-1",
        "sensitive_tenant": True,
        "observability_trace_mode": "hide_io",
        "observability_sample_rate": 0.25,
    }

    assert public_trace_metadata(metadata) == {"tenant_id": "tenant-1"}


@pytest.mark.parametrize("status", ["failed", "blocked"])
def test_mandatory_statuses_are_preserved_even_at_zero_sample_rate(status: str) -> None:
    policy = resolve_tenant_policy({"observability_sample_rate": 0.0})

    assert should_sample_trace(
        policy,
        correlation_id="correlation-1",
        terminal_status=status,
    )


def test_negative_feedback_and_release_proof_are_always_preserved() -> None:
    policy = resolve_tenant_policy({"observability_sample_rate": 0.0})

    assert should_sample_trace(
        policy,
        correlation_id="negative-feedback",
        negative_feedback=True,
    )
    assert should_sample_trace(
        policy,
        correlation_id="release-proof",
        release_proof=True,
    )


def test_initial_full_capture_overrides_configured_sampling() -> None:
    now = datetime(2026, 7, 16, tzinfo=UTC)
    policy = resolve_tenant_policy({"observability_sample_rate": 0.0})

    assert should_sample_trace(
        policy,
        correlation_id="initial-capture",
        full_capture_until=now + timedelta(days=1),
        now=now,
    )


def test_langfuse_user_id_never_exports_email_or_phone() -> None:
    email = "person@example.test"
    phone = "+86 138 0000 0000"

    assert anonymize_user_id(email).startswith("anon-")
    assert anonymize_user_id(phone).startswith("anon-")
    assert email not in anonymize_user_id(email)
    assert phone not in anonymize_user_id(phone)
    internal = anonymize_user_id("internal-user-uuid")
    assert internal is not None and internal.startswith("anon-")
    assert "internal-user-uuid" not in internal


def test_sampling_policy_controls_callback_injection_after_full_capture() -> None:
    runtime = ObservabilityRuntimeConfig(
        environment="test",
        release="2.0.0-test",
        langfuse_enabled=True,
        langfuse_public_key="pk-test",
        langfuse_secret_key="sk-test",
    )
    initialized = []
    factory = create_observability_config_factory(
        runtime,
        handler_factory=lambda **kwargs: object(),
        langfuse_client_initializer=initialized.append,
    )
    config = {
        "metadata": {
            "correlation_id": "sampled-out",
            "observability_sample_rate": 0.0,
            "observability_full_capture_until": "2020-01-01T00:00:00+00:00",
        }
    }

    addition = factory(config)

    assert addition["callbacks"] == []
    assert initialized == []
    assert "observability_sample_rate" not in config["metadata"]
    assert "observability_full_capture_until" not in config["metadata"]
