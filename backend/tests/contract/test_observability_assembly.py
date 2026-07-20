from dataclasses import dataclass
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler, CallbackManager
from langchain_core.runnables import RunnableBinding, RunnableLambda
from langchain_core.tracers.langchain import LangChainTracer
from langfuse.langchain import CallbackHandler
from pydantic import BaseModel, SecretStr

import crypto_alert_v2.observability.callbacks as callbacks_module
from crypto_alert_v2.observability.callbacks import (
    build_observability_config,
    create_observability_config_factory,
    initialize_langfuse_client,
    initialize_langsmith_client,
    redact_metadata,
)
from crypto_alert_v2.observability.config import ObservabilityRuntimeConfig
from crypto_alert_v2.observability.tenant_policy import (
    anonymize_user_id,
    resolve_tenant_policy,
)


class RecordingHandler(BaseCallbackHandler):
    def __init__(
        self,
        *,
        public_key: str | None = None,
        trace_context: dict[str, str] | None = None,
    ) -> None:
        self.public_key = public_key
        self.trace_context = trace_context


@dataclass(frozen=True)
class DataclassMetadata:
    agent_server_local_token: str
    provider: str


class ModelMetadata(BaseModel):
    device_key: str
    artifact_id: str


class LegacyModelMetadata:
    def model_dump(self) -> dict[str, Any]:
        return {"provider": "okx", "device_key": "legacy-device-canary"}


class NonSerializableRuntime:
    def __deepcopy__(self, memo: dict[int, Any]) -> "NonSerializableRuntime":
        del memo
        raise AssertionError("runtime objects must not be copied into trace metadata")


def runtime_config(**overrides: Any) -> ObservabilityRuntimeConfig:
    values = {
        "environment": "test",
        "release": "2.0.0-test",
        "langsmith_enabled": False,
        "langsmith_api_key": None,
        "langsmith_project": "crypto-alert-v2-test",
        "langfuse_enabled": True,
        "langfuse_public_key": "pk-test",
        "langfuse_secret_key": "sk-test-secret",
        "langfuse_host": "https://langfuse.example.test",
    }
    values.update(overrides)
    return ObservabilityRuntimeConfig(**values)


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


def test_structured_metadata_and_secret_key_variants_are_redacted() -> None:
    canaries = {
        "device": "device-canary-value",
        "local_token": "local-token-canary-value",
        "passphrase": "passphrase-canary-value",
        "bytes": "bytes-canary-value",
        "set": "set-canary-value",
    }
    metadata = {
        "dataclass": DataclassMetadata(
            agent_server_local_token=canaries["local_token"],
            provider="okx",
        ),
        "model": ModelMetadata(
            device_key=canaries["device"],
            artifact_id="artifact-1",
        ),
        "passphrase": canaries["passphrase"],
        "bytes": f"Authorization: Bearer {canaries['bytes']}".encode(),
        "set": {f"device_key={canaries['set']}", "provider:okx"},
        "opaque": SecretStr("secret-wrapper-canary-value"),
        "usage_metadata": {
            "input_tokens": 12,
            "output_token_details": {"reasoning": 4},
        },
    }

    redacted = redact_metadata(metadata)
    serialized = repr(redacted)

    assert redacted["dataclass"] == {"provider": "okx"}
    assert redacted["model"] == {"artifact_id": "artifact-1"}
    assert redacted["opaque"] == "[REDACTED]"
    assert redacted["usage_metadata"] == {
        "input_tokens": 12,
        "output_token_details": {"reasoning": 4},
    }
    assert "passphrase" not in redacted
    assert "secret-wrapper-canary-value" not in serialized
    assert all(value not in serialized for value in canaries.values())


def test_redaction_accepts_langgraph_model_dump_without_mode_argument() -> None:
    metadata = {"legacy": LegacyModelMetadata()}

    assert redact_metadata(metadata) == {"legacy": {"provider": "okx"}}


def test_factory_ignores_non_identity_runtime_objects_in_configurable() -> None:
    result = build_observability_config(
        {
            "configurable": {
                "thread_id": "thread-1",
                "runtime": NonSerializableRuntime(),
            }
        },
        langfuse_enabled=False,
        langfuse_public_key=None,
    )

    assert result["metadata"]["thread_id"] == "thread-1"
    assert "runtime" not in result["metadata"]


def test_runtime_config_repr_never_contains_secret_credentials() -> None:
    runtime = runtime_config(
        langsmith_api_key="langsmith-repr-canary",
        langfuse_secret_key="langfuse-repr-canary",
    )

    rendered = repr(runtime)

    assert "langsmith-repr-canary" not in rendered
    assert "langfuse-repr-canary" not in rendered


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
    actor_ref = anonymize_user_id("anonymous-user-1")

    assert config["metadata"] == {
        **{key: value for key, value in metadata.items() if key != "user_id"},
        "run_id": "product-run-1",
        "actor_ref": actor_ref,
        "langfuse_user_id": actor_ref,
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


def test_runnable_binding_factory_creates_one_new_handler_per_invocation() -> None:
    seen_configs: list[dict[str, Any]] = []
    initialized: list[ObservabilityRuntimeConfig] = []

    def invoke(value: str, config: dict[str, Any]) -> str:
        seen_configs.append(config)
        return value

    factory = create_observability_config_factory(
        runtime_config(),
        handler_factory=RecordingHandler,
        langfuse_client_initializer=initialized.append,
    )
    runnable = RunnableBinding(
        bound=RunnableLambda(invoke),
        config_factories=[factory],
    )

    assert runnable.invoke("first") == "first"
    assert runnable.invoke("second") == "second"

    handlers = [
        next(
            handler
            for handler in config["callbacks"].handlers
            if isinstance(handler, RecordingHandler)
        )
        for config in seen_configs
    ]
    assert handlers[0] is not handlers[1]
    assert len(initialized) == 2


def test_factory_uses_automatic_langsmith_tracer_with_request_metadata() -> None:
    client = object()
    factory = create_observability_config_factory(
        runtime_config(
            langsmith_enabled=True,
            langsmith_api_key="lsv2_test_canary",
            langfuse_enabled=False,
        ),
        langsmith_client_factory=lambda runtime, policy: client,
    )
    config: dict[str, Any] = {
        "metadata": {
            "tenant_id": "tenant-1",
            "thread_id": "thread-1",
            "correlation_id": "correlation-1",
        },
        "tags": ["workflow:analysis"],
    }

    addition = factory(config)

    tracer = next(
        handler
        for handler in addition["callbacks"]
        if isinstance(handler, LangChainTracer)
    )
    assert tracer.client is client
    assert tracer.project_name == "crypto-alert-v2-test"
    assert config["metadata"]["thread_id"] == "thread-1"
    assert config["metadata"]["langfuse_session_id"] == "thread-1"
    assert "workflow:analysis" in config["tags"]
    assert "service:crypto-alert-v2" in config["tags"]


def test_factory_normalizes_cross_system_correlation_metadata(
    monkeypatch: Any,
) -> None:
    langsmith_metadata: list[dict[str, Any]] = []

    def capture_langsmith_metadata(**kwargs: Any) -> list[Any]:
        langsmith_metadata.append(kwargs["metadata"])
        return []

    monkeypatch.setattr(
        callbacks_module,
        "_automatic_langsmith_handlers",
        capture_langsmith_metadata,
    )
    factory = create_observability_config_factory(
        runtime_config(
            langsmith_enabled=True,
            langsmith_api_key="lsv2_test_canary",
        ),
        handler_factory=RecordingHandler,
        langfuse_client_initializer=lambda runtime: object(),
        langsmith_client_factory=lambda runtime, policy: object(),
    )
    config: dict[str, Any] = {
        "configurable": {
            "thread_id": "thread-1",
            "task_id": "task-from-configurable",
        },
        "metadata": {
            "task_id": "task-1",
            "product_run_id": "product-run-1",
            "correlation_id": "correlation-1",
            "provider": "okx",
            "artifact_id": "artifact-1",
        },
    }

    addition = factory(config)

    assert len(addition["callbacks"]) == 1
    assert isinstance(addition["callbacks"][0], RecordingHandler)
    assert config["metadata"] == {
        "artifact_id": "artifact-1",
        "correlation_id": "correlation-1",
        "environment": "test",
        "langfuse_session_id": "thread-1",
        "product_run_id": "product-run-1",
        "provider": "okx",
        "run_id": "product-run-1",
        "task_id": "task-1",
        "thread_id": "thread-1",
        "version": "2.0.0-test",
    }
    assert langsmith_metadata == [config["metadata"]]
    assert addition["callbacks"][0].trace_context is not None
    assert len(addition["callbacks"][0].trace_context["trace_id"]) == 32


def test_langfuse_trace_context_is_stable_per_product_run() -> None:
    factory = create_observability_config_factory(
        runtime_config(langsmith_enabled=False),
        handler_factory=RecordingHandler,
        langfuse_client_initializer=lambda runtime: object(),
    )

    first = factory(
        {"metadata": {"product_run_id": "11111111-1111-4111-8111-111111111111"}}
    )["callbacks"][0]
    second = factory(
        {"metadata": {"product_run_id": "11111111-1111-4111-8111-111111111111"}}
    )["callbacks"][0]
    other = factory(
        {"metadata": {"product_run_id": "22222222-2222-4222-8222-222222222222"}}
    )["callbacks"][0]

    assert first.trace_context == second.trace_context
    assert first.trace_context != other.trace_context


def test_explicit_run_id_wins_over_product_and_official_aliases() -> None:
    factory = create_observability_config_factory(
        runtime_config(langfuse_enabled=False),
    )
    config: dict[str, Any] = {
        "configurable": {
            "thread_id": "thread-1",
            "official_run_id": "official-run-1",
        },
        "metadata": {
            "run_id": "canonical-run-1",
            "product_run_id": "product-run-1",
        },
    }

    factory(config)

    assert config["metadata"]["run_id"] == "canonical-run-1"
    assert config["metadata"]["product_run_id"] == "product-run-1"
    assert config["metadata"]["official_run_id"] == "official-run-1"


def test_official_langfuse_callback_handler_is_new_for_every_root_invocation() -> None:
    factory = create_observability_config_factory(
        runtime_config(),
        langfuse_client_initializer=lambda runtime: object(),
    )

    first = factory({})["callbacks"]
    second = factory({})["callbacks"]

    assert len(first) == len(second) == 1
    assert isinstance(first[0], CallbackHandler)
    assert isinstance(second[0], CallbackHandler)
    assert first[0] is not second[0]


def test_langfuse_process_client_is_initialized_once(
    monkeypatch: Any,
) -> None:
    constructed: list[dict[str, Any]] = []

    class FakeLangfuse:
        def __init__(self, **kwargs: Any) -> None:
            constructed.append(kwargs)

    monkeypatch.setattr(callbacks_module, "Langfuse", FakeLangfuse)
    callbacks_module._initialize_langfuse_client_cached.cache_clear()
    runtime = runtime_config()

    first = initialize_langfuse_client(runtime)
    second = initialize_langfuse_client(runtime)

    assert first is second
    assert len(constructed) == 1
    assert constructed[0]["public_key"] == "pk-test"
    assert constructed[0]["secret_key"] == "sk-test-secret"
    assert callable(constructed[0]["mask"])
    assert callable(constructed[0]["mask_otel_spans"])
    callbacks_module._initialize_langfuse_client_cached.cache_clear()


def test_langsmith_client_uses_official_egress_redaction_and_io_policy(
    monkeypatch: Any,
) -> None:
    constructed: list[dict[str, Any]] = []

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            constructed.append(kwargs)

    monkeypatch.setattr(callbacks_module, "Client", FakeClient)
    callbacks_module._initialize_langsmith_client_cached.cache_clear()
    runtime = runtime_config(
        langsmith_enabled=True,
        langsmith_api_key="lsv2_test_canary",
    )
    policy = resolve_tenant_policy({"sensitive_tenant": True})

    first = initialize_langsmith_client(runtime, policy)
    second = initialize_langsmith_client(runtime, policy)

    assert first is second
    assert len(constructed) == 1
    assert constructed[0]["api_key"] == "lsv2_test_canary"
    assert constructed[0]["hide_inputs"] is True
    assert constructed[0]["hide_outputs"] is True
    assert callable(constructed[0]["anonymizer"])
    assert callable(constructed[0]["hide_metadata"])
    assert callable(constructed[0]["tracing_error_callback"])
    callbacks_module._initialize_langsmith_client_cached.cache_clear()
