from typing import Any

from langchain_core.callbacks import CallbackManager

from crypto_alert_v2.observability.callbacks import (
    build_observability_config,
    redact_metadata,
)


class RecordingHandler:
    def __init__(self, *, public_key: str | None = None) -> None:
        self.public_key = public_key


def test_langfuse_handler_is_created_at_most_once_per_root_config() -> None:
    first = build_observability_config(
        {"metadata": {"task_id": "task-1", "run_id": "run-1"}, "callbacks": []},
        langfuse_enabled=True,
        langfuse_public_key="pk-test",
        handler_factory=RecordingHandler,
    )
    second = build_observability_config(
        first,
        langfuse_enabled=True,
        langfuse_public_key="pk-test",
        handler_factory=RecordingHandler,
    )

    assert len(second["callbacks"]) == 1
    assert second["callbacks"][0] is first["callbacks"][0]
    assert isinstance(second["callbacks"][0], RecordingHandler)
    assert second["metadata"] == {"task_id": "task-1", "run_id": "run-1"}


def test_disabled_langfuse_does_not_add_callback() -> None:
    config = build_observability_config(
        {"metadata": {"task_id": "task-1"}},
        langfuse_enabled=False,
        langfuse_public_key=None,
        handler_factory=RecordingHandler,
    )

    assert config["callbacks"] == []


def test_existing_official_callback_manager_is_preserved() -> None:
    manager = CallbackManager([])

    config = build_observability_config(
        {"callbacks": manager, "metadata": {"task_id": "task-1"}},
        langfuse_enabled=False,
        langfuse_public_key=None,
        handler_factory=RecordingHandler,
    )

    assert config["callbacks"] is manager


def test_sensitive_metadata_is_removed_recursively() -> None:
    metadata: dict[str, Any] = {
        "task_id": "task-1",
        "Authorization": "Bearer secret",
        "nested": {
            "api_key": "secret",
            "cookie": "session=secret",
            "correlation_id": "corr-1",
        },
    }

    assert redact_metadata(metadata) == {
        "task_id": "task-1",
        "nested": {"correlation_id": "corr-1"},
    }


def test_official_run_metadata_and_langfuse_attributes_share_root_config() -> None:
    metadata = {
        "tenant_id": "tenant-1",
        "user_id": "anonymous-user-1",
        "thread_id": "thread-1",
        "task_id": "task-1",
        "product_run_id": "product-run-1",
        "official_run_id": "official-run-1",
        "correlation_id": "correlation-1",
        "environment": "production",
        "version": "2.0.0",
    }

    config = build_observability_config(
        {"metadata": metadata},
        langfuse_enabled=True,
        langfuse_public_key="pk-test",
        handler_factory=RecordingHandler,
    )

    assert config["metadata"] == {
        **metadata,
        "langfuse_user_id": "anonymous-user-1",
        "langfuse_session_id": "thread-1",
    }


def test_handler_construction_failure_is_fail_open() -> None:
    existing = object()

    def failing_factory(*, public_key: str | None = None) -> RecordingHandler:
        del public_key
        raise RuntimeError("observability unavailable")

    config = build_observability_config(
        {
            "metadata": {
                "task_id": "task-1",
                "nested": {"authorization": "Bearer secret"},
            },
            "callbacks": [existing],
        },
        langfuse_enabled=True,
        langfuse_public_key="pk-test",
        handler_factory=failing_factory,
    )

    assert config["callbacks"] == [existing]
    assert config["metadata"] == {"task_id": "task-1", "nested": {}}
