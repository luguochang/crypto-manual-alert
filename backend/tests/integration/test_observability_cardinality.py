from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables import RunnableBinding, RunnableLambda

from crypto_alert_v2.observability.callbacks import create_observability_config_factory
from crypto_alert_v2.observability.config import ObservabilityRuntimeConfig


class RecordingHandler(BaseCallbackHandler):
    def __init__(self, *, public_key: str | None = None) -> None:
        self.public_key = public_key


def _runtime() -> ObservabilityRuntimeConfig:
    return ObservabilityRuntimeConfig(
        environment="test",
        release="2.0.0-test",
        langfuse_enabled=True,
        langfuse_public_key="pk-test",
        langfuse_secret_key="sk-test",
    )


def test_root_handler_is_shared_by_children_but_not_across_invocations() -> None:
    root_configs: list[dict[str, Any]] = []
    child_configs: list[dict[str, Any]] = []

    def child(value: str, config: dict[str, Any]) -> str:
        child_configs.append(config)
        return value

    child_runnable = RunnableLambda(child)

    def root(value: str, config: dict[str, Any]) -> str:
        root_configs.append(config)
        return child_runnable.invoke(value, config=config)

    factory = create_observability_config_factory(
        _runtime(),
        handler_factory=RecordingHandler,
        langfuse_client_initializer=lambda runtime: object(),
    )
    runnable = RunnableBinding(
        bound=RunnableLambda(root),
        config_factories=[factory],
    )

    runnable.invoke(
        "direct",
        config={
            "metadata": {
                "correlation_id": "correlation-direct",
                "thread_id": "thread-direct",
            }
        },
    )
    runnable.invoke(
        "retry",
        config={
            "metadata": {
                "correlation_id": "correlation-retry",
                "thread_id": "thread-retry",
                "retry_of_run_id": "run-direct",
            }
        },
    )

    root_handlers = [
        next(
            item
            for item in config["callbacks"].handlers
            if isinstance(item, RecordingHandler)
        )
        for config in root_configs
    ]
    child_handlers = [
        next(
            item
            for item in config["callbacks"].handlers
            if isinstance(item, RecordingHandler)
        )
        for config in child_configs
    ]
    assert root_handlers[0] is child_handlers[0]
    assert root_handlers[1] is child_handlers[1]
    assert root_handlers[0] is not root_handlers[1]


def test_identity_values_stay_metadata_and_do_not_expand_tag_cardinality() -> None:
    factory = create_observability_config_factory(
        _runtime(),
        handler_factory=RecordingHandler,
        langfuse_client_initializer=lambda runtime: object(),
    )

    configs: list[dict[str, Any]] = []
    for index in range(100):
        config: dict[str, Any] = {
            "metadata": {
                "tenant_id": f"tenant-{index}",
                "thread_id": f"thread-{index}",
                "run_id": f"run-{index}",
                "correlation_id": f"correlation-{index}",
            }
        }
        factory(config)
        configs.append(config)

    assert {tuple(config["tags"]) for config in configs} == {
        ("environment:test", "service:crypto-alert-v2")
    }
