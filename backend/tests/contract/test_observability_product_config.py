from pydantic import SecretStr, ValidationError
import pytest

from crypto_alert_v2.config import Settings
from crypto_alert_v2.observability.identity import (
    langfuse_trace_id_for_product_run,
)


def test_observability_provider_flags_require_complete_credentials() -> None:
    with pytest.raises(ValidationError, match="LANGSMITH_API_KEY"):
        Settings(
            app_environment="test",
            langsmith_tracing=True,
            langsmith_api_key=None,
            _env_file=None,
        )

    with pytest.raises(ValidationError, match="LANGFUSE_PUBLIC_KEY"):
        Settings(
            app_environment="test",
            langfuse_enabled=True,
            langfuse_public_key="pk-test",
            langfuse_secret_key=None,
            _env_file=None,
        )


def test_observability_verification_settings_are_bounded() -> None:
    settings = Settings(
        app_environment="test",
        langsmith_tracing=True,
        langsmith_api_key=SecretStr("langsmith-config-canary"),
        langfuse_enabled=True,
        langfuse_public_key="pk-test",
        langfuse_secret_key=SecretStr("langfuse-config-canary"),
        observability_verification_lease_seconds=30,
        observability_verification_deadline_seconds=3_600,
        observability_verification_retry_seconds=5.0,
        observability_verification_max_attempts=30,
        _env_file=None,
    )

    assert settings.observability_verification_deadline_seconds == 3_600
    assert "langsmith-config-canary" not in repr(settings)
    assert "langfuse-config-canary" not in repr(settings)


def test_langfuse_product_run_trace_id_uses_official_deterministic_format() -> None:
    first = langfuse_trace_id_for_product_run("11111111-1111-4111-8111-111111111111")
    repeated = langfuse_trace_id_for_product_run("11111111-1111-4111-8111-111111111111")
    other = langfuse_trace_id_for_product_run("22222222-2222-4222-8222-222222222222")

    assert first == repeated
    assert first != other
    assert len(first) == 32
    assert first == first.lower()
    assert all(character in "0123456789abcdef" for character in first)
