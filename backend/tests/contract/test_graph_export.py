from importlib import import_module
from types import ModuleType

from langchain_core.callbacks import BaseCallbackHandler, CallbackManager
from langchain_core.runnables.config import var_child_runnable_config
import pytest


def test_graph_factory_is_the_only_production_export() -> None:
    from langgraph.pregel import Pregel

    from crypto_alert_v2.graph import create_graph, graph_factory

    assert isinstance(create_graph(), Pregel)
    request_config = {
        "metadata": {"correlation_id": "factory-contract-correlation"},
        "tags": ["factory-contract"],
    }
    configured = graph_factory(request_config)
    assert isinstance(configured, Pregel)
    assert configured.config is not None
    assert request_config["metadata"]["correlation_id"] == (
        "factory-contract-correlation"
    )
    assert "factory-contract" in request_config["tags"]
    assert configured.config.get("configurable") in (None, {})
    assert configured.config.get("metadata") in (None, {})
    assert configured.config.get("tags") in (None, [])
    graph_module = import_module("crypto_alert_v2.graph.graph")
    graph_package = import_module("crypto_alert_v2.graph")
    assert not hasattr(graph_module, "graph")
    assert graph_package.__all__ == ["create_graph", "graph_factory"]
    assert isinstance(graph_package.graph, ModuleType)


def test_graph_runtime_context_schema_filters_framework_private_keys() -> None:
    from crypto_alert_v2.graph import create_graph
    from crypto_alert_v2.graph.runtime import AnalysisRuntime

    schema = create_graph().get_context_jsonschema()
    assert set(schema["properties"]) == {
        "market_provider",
        "market_fallback_collector",
        "research_collector",
        "analysis_agent",
        "deep_research_executor",
        "deep_research_harness_mode",
        "search_readiness",
    }
    runtime = AnalysisRuntime.model_validate({"__event_streaming_v2": True})
    assert runtime == AnalysisRuntime()


def test_official_graph_factory_binds_root_observability_callbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph_module = import_module("crypto_alert_v2.graph.graph")
    handler = BaseCallbackHandler()
    manager = CallbackManager([handler])
    seen: list[dict[str, object]] = []

    def observed_config(config: dict[str, object]) -> dict[str, object]:
        seen.append(config)
        return {
            "callbacks": manager,
            "metadata": {"observability_bound": True},
        }

    monkeypatch.setattr(
        graph_module,
        "_root_observability_config",
        observed_config,
    )

    request_config = {"metadata": {"correlation_id": "factory-observability-contract"}}
    configured = graph_module.graph_factory(request_config)

    assert len(seen) == 1
    assert seen[0] is request_config
    assert configured.config is not None
    callbacks = configured.config["callbacks"]
    assert isinstance(callbacks, CallbackManager)
    assert callbacks.handlers == [handler]
    assert configured.config["metadata"] == {
        "observability_bound": True,
    }
    assert request_config["metadata"] == {
        "correlation_id": "factory-observability-contract"
    }


def test_graph_factory_does_not_bind_agent_server_execution_config_as_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph_module = import_module("crypto_alert_v2.graph.graph")
    request_handler = BaseCallbackHandler()
    observability_handler = BaseCallbackHandler()
    server_runtime = object()
    server_checkpointer = object()

    def observed_config(config: dict[str, object]) -> dict[str, object]:
        assert config["configurable"] == {
            "__pregel_runtime": server_runtime,
            "__pregel_checkpointer": server_checkpointer,
            "__is_for_execution__": True,
            "thread_id": "agent-server-thread",
            "assistant_id": "agent-server-assistant",
            "graph_id": "crypto_analysis",
        }
        return {
            "callbacks": CallbackManager([observability_handler]),
            "tags": ["observability-bound"],
            "metadata": {
                "thread_id": "agent-server-thread",
                "observability_bound": True,
            },
        }

    monkeypatch.setattr(
        graph_module,
        "_root_observability_config",
        observed_config,
    )

    request_config = {
        "callbacks": [request_handler],
        "tags": ["factory-request"],
        "metadata": {
            "correlation_id": "factory-runtime-contract",
            "tenant_id": "tenant-1",
        },
        "configurable": {
            "__pregel_runtime": server_runtime,
            "__pregel_checkpointer": server_checkpointer,
            "__is_for_execution__": True,
            "thread_id": "agent-server-thread",
            "assistant_id": "agent-server-assistant",
            "graph_id": "crypto_analysis",
        },
    }
    token = var_child_runnable_config.set(request_config)
    try:
        configured = graph_module.graph_factory(request_config)
    finally:
        var_child_runnable_config.reset(token)

    assert configured.config is not None
    assert configured.config.get("configurable") in (None, {})
    callbacks = configured.config["callbacks"]
    assert isinstance(callbacks, CallbackManager)
    assert callbacks.handlers == [observability_handler]
    assert request_handler not in callbacks.handlers
    assert configured.config["tags"] == ["observability-bound"]
    assert configured.config["metadata"] == {
        "thread_id": "agent-server-thread",
        "observability_bound": True,
    }
    assert request_config["callbacks"] == [request_handler]
    assert request_config["tags"] == ["factory-request"]
    assert request_config["metadata"] == {
        "correlation_id": "factory-runtime-contract",
        "tenant_id": "tenant-1",
    }
