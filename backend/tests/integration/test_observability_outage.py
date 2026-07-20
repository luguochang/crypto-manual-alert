from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables import RunnableBinding, RunnableLambda
from langchain_core.tracers.langchain import LangChainTracer
import pytest

from crypto_alert_v2.observability.callbacks import create_observability_config_factory
from crypto_alert_v2.observability.config import ObservabilityRuntimeConfig


class RecordingHandler(BaseCallbackHandler):
    def __init__(self, *, public_key: str | None = None) -> None:
        self.public_key = public_key


class HealthyLangsmithClient:
    def create_run(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs

    def update_run(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs


class FailingHandler:
    def __init__(self, *, public_key: str | None = None) -> None:
        del public_key
        raise ConnectionError("handler unavailable with Bearer test-outage-secret")


def test_langsmith_bootstrap_failure_is_fail_open_and_keeps_langfuse_callback() -> None:
    events: list[dict[str, Any]] = []
    runtime = ObservabilityRuntimeConfig(
        environment="test",
        release="2.0.0-test",
        langsmith_enabled=True,
        langsmith_api_key="lsv2_test-outage-secret",
        langfuse_enabled=True,
        langfuse_public_key="pk-test-outage",
        langfuse_secret_key="sk-test-outage",
    )

    def fail_langsmith(runtime: Any, policy: Any) -> Any:
        del runtime, policy
        raise TimeoutError("langsmith unavailable api_key=test-outage-secret")

    factory = create_observability_config_factory(
        runtime,
        handler_factory=RecordingHandler,
        langfuse_client_initializer=lambda runtime: object(),
        langsmith_client_factory=fail_langsmith,
        event_sink=events.append,
    )
    seen_config: dict[str, Any] = {}

    def business(value: str, config: dict[str, Any]) -> dict[str, Any]:
        seen_config.update(config)
        return {
            "terminal_status": "succeeded",
            "artifact": value,
        }

    runnable = RunnableBinding(
        bound=RunnableLambda(business),
        config_factories=[factory],
    )

    result = runnable.invoke(
        "committed-artifact",
        config={"metadata": {"correlation_id": "correlation-outage"}},
    )

    assert result == {
        "terminal_status": "succeeded",
        "artifact": "committed-artifact",
    }
    callbacks = seen_config["callbacks"].handlers
    assert any(isinstance(callback, RecordingHandler) for callback in callbacks)
    assert len(events) == 1
    event = events[0]
    assert event["event"] == "observability_delivery_failure"
    assert event["provider"] == "langsmith"
    assert event["stage"] == "bootstrap"
    assert event["correlation_id"] == "correlation-outage"
    assert event["retry_state"] == "exhausted"
    assert event["dropped"] is True
    assert event["error_type"] == "TimeoutError"
    assert len(event["alert_fingerprint"]) == 24
    assert "test-outage-secret" not in repr(events)


@pytest.mark.asyncio
async def test_langfuse_bootstrap_failure_is_fail_open_and_keeps_langsmith_callback() -> (
    None
):
    events: list[dict[str, Any]] = []
    runtime = ObservabilityRuntimeConfig(
        environment="test",
        release="2.0.0-test",
        langsmith_enabled=True,
        langsmith_api_key="lsv2_async-test",
        langfuse_enabled=True,
        langfuse_public_key="pk-async-test",
        langfuse_secret_key="sk-async-test",
    )

    def fail_client(runtime: Any) -> Any:
        del runtime
        raise TimeoutError("Cookie: async-secret")

    langsmith_client = HealthyLangsmithClient()
    factory = create_observability_config_factory(
        runtime,
        handler_factory=FailingHandler,
        langfuse_client_initializer=fail_client,
        langsmith_client_factory=lambda runtime, policy: langsmith_client,
        event_sink=events.append,
    )
    seen_config: dict[str, Any] = {}

    async def business(value: str, config: dict[str, Any]) -> dict[str, Any]:
        seen_config.update(config)
        return {"terminal_status": "blocked", "value": value}

    runnable = RunnableBinding(
        bound=RunnableLambda(business),
        config_factories=[factory],
    )

    result = await runnable.ainvoke(
        "policy-result",
        config={"metadata": {"correlation_id": "correlation-async"}},
    )

    assert result == {"terminal_status": "blocked", "value": "policy-result"}
    callbacks = seen_config["callbacks"].handlers
    assert any(isinstance(callback, LangChainTracer) for callback in callbacks)
    assert len(events) == 1
    assert events[0]["provider"] == "langfuse"
    assert events[0]["stage"] == "bootstrap"
    assert events[0]["correlation_id"] == "correlation-async"
    assert events[0]["retry_state"] == "exhausted"
    assert events[0]["dropped"] is True
    assert events[0]["error_type"] == "TimeoutError"
    assert len(events[0]["alert_fingerprint"]) == 24
    assert "async-secret" not in repr(events)
