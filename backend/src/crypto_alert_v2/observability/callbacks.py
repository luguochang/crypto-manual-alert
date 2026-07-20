from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from langchain_core.callbacks import CallbackManager
from langchain_core.callbacks.base import BaseCallbackManager
from langchain_core.runnables import RunnableConfig
from langchain_core.tracers.langchain import LangChainTracer
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from langsmith import Client, tracing_context

from crypto_alert_v2.observability.config import ObservabilityRuntimeConfig
from crypto_alert_v2.observability.identity import (
    langfuse_trace_id_for_product_run,
)
from crypto_alert_v2.observability.logging import (
    EventSink,
    emit_delivery_failure,
    install_sdk_log_redaction,
)
from crypto_alert_v2.observability.redaction import (
    mask_langfuse_otel_spans,
    mask_langfuse_payload,
    redact_metadata,
    redact_payload,
)
from crypto_alert_v2.observability.tenant_policy import (
    TenantObservabilityPolicy,
    anonymize_user_id,
    public_trace_metadata,
    resolve_tenant_policy,
    should_sample_trace,
)


HandlerFactory = Callable[..., Any]
LangfuseClientInitializer = Callable[[ObservabilityRuntimeConfig], Any]
LangsmithClientFactory = Callable[
    [ObservabilityRuntimeConfig, TenantObservabilityPolicy], Any
]
_TRACE_IDENTITY_KEYS = (
    "correlation_id",
    "thread_id",
    "task_id",
    "run_id",
    "product_run_id",
    "official_run_id",
    "provider",
    "artifact_id",
)


def _with_langfuse_trace_attributes(metadata: dict[str, Any]) -> dict[str, Any]:
    user_id = anonymize_user_id(metadata.pop("user_id", None))
    if user_id:
        metadata.setdefault("actor_ref", user_id)
        metadata.setdefault("langfuse_user_id", user_id)
    thread_id = metadata.get("thread_id")
    if isinstance(thread_id, str) and thread_id:
        metadata.setdefault("langfuse_session_id", thread_id)
    return metadata


def _callback_handlers(callbacks: Any) -> list[Any]:
    if isinstance(callbacks, BaseCallbackManager):
        return list(callbacks.handlers)
    if isinstance(callbacks, list):
        return callbacks
    return []


def _has_handler(callbacks: Any, handler_type: type[Any]) -> bool:
    return any(
        isinstance(handler, handler_type) for handler in _callback_handlers(callbacks)
    )


def _has_factory_handler(callbacks: Any, handler_factory: HandlerFactory) -> bool:
    factory_type = handler_factory if isinstance(handler_factory, type) else None
    return any(
        isinstance(handler, CallbackHandler)
        or (factory_type is not None and isinstance(handler, factory_type))
        for handler in _callback_handlers(callbacks)
    )


def _safe_metadata(value: Any) -> dict[str, Any]:
    redacted = redact_metadata(value or {})
    return dict(redacted) if isinstance(redacted, Mapping) else {}


def _non_empty_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _normalize_trace_identity(
    metadata: dict[str, Any],
    configurable: Any,
) -> dict[str, Any]:
    configurable_identity = (
        {key: configurable[key] for key in _TRACE_IDENTITY_KEYS if key in configurable}
        if isinstance(configurable, Mapping)
        else {}
    )
    safe_configurable = _safe_metadata(configurable_identity)
    for key in _TRACE_IDENTITY_KEYS:
        if _non_empty_string(metadata.get(key)) is not None:
            continue
        if value := _non_empty_string(safe_configurable.get(key)):
            metadata[key] = value

    if _non_empty_string(metadata.get("run_id")) is None:
        for alias in ("product_run_id", "official_run_id"):
            if value := _non_empty_string(metadata.get(alias)):
                metadata["run_id"] = value
                break
    return metadata


def _safe_tags(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return sorted(
        {
            redacted
            for item in value
            if isinstance(item, str) and (redacted := str(redact_payload(item)))
        }
    )


@lru_cache(maxsize=4)
def _initialize_langfuse_client_cached(
    public_key: str,
    secret_key: str,
    host: str | None,
    environment: str,
    release: str,
) -> Langfuse:
    install_sdk_log_redaction()
    return Langfuse(
        public_key=public_key,
        secret_key=secret_key,
        host=host,
        environment=environment,
        release=release,
        mask=mask_langfuse_payload,
        mask_otel_spans=mask_langfuse_otel_spans,
    )


def initialize_langfuse_client(config: ObservabilityRuntimeConfig) -> Langfuse:
    if not config.langfuse_public_key or not config.langfuse_secret_key:
        raise ValueError("Langfuse credentials are not configured")
    return _initialize_langfuse_client_cached(
        config.langfuse_public_key,
        config.langfuse_secret_key,
        config.langfuse_host,
        config.environment,
        config.release,
    )


@lru_cache(maxsize=8)
def _initialize_langsmith_client_cached(
    api_key: str,
    hide_io: bool,
) -> Client:
    install_sdk_log_redaction()
    return Client(
        api_key=api_key,
        anonymizer=redact_payload,
        hide_inputs=hide_io,
        hide_outputs=hide_io,
        hide_metadata=redact_metadata,
        tracing_error_callback=_on_langsmith_tracing_error,
    )


def _on_langsmith_tracing_error(error: Exception) -> None:
    emit_delivery_failure(
        provider="langsmith",
        correlation_id=None,
        error=error,
        stage="transport",
    )


def initialize_langsmith_client(
    config: ObservabilityRuntimeConfig,
    policy: TenantObservabilityPolicy,
) -> Client:
    if not config.langsmith_api_key:
        raise ValueError("LangSmith credentials are not configured")
    return _initialize_langsmith_client_cached(
        config.langsmith_api_key,
        policy.hide_io,
    )


def _automatic_langsmith_handlers(
    *,
    client: Client,
    project_name: str,
    tags: list[str],
    metadata: dict[str, Any],
) -> list[LangChainTracer]:
    # CallbackManager.configure is the LangChain automatic-tracing assembly point.
    # tracing_context supplies its request-scoped Client/project/tags/metadata.
    with tracing_context(
        enabled=True,
        client=client,
        project_name=project_name,
        tags=tags,
        metadata=metadata,
    ):
        manager = CallbackManager.configure()
    return [
        handler for handler in manager.handlers if isinstance(handler, LangChainTracer)
    ]


def _correlation_id(metadata: Mapping[str, Any]) -> str | None:
    value = metadata.get("correlation_id")
    return value if isinstance(value, str) and value else None


def _langfuse_trace_context(metadata: Mapping[str, Any]) -> dict[str, str] | None:
    product_run_id = _non_empty_string(metadata.get("product_run_id"))
    if product_run_id is None:
        return None
    return {"trace_id": langfuse_trace_id_for_product_run(product_run_id)}


def _normalize_root_config(
    config: RunnableConfig,
    runtime: ObservabilityRuntimeConfig,
) -> tuple[dict[str, Any], list[str], TenantObservabilityPolicy, bool]:
    metadata = _normalize_trace_identity(
        _safe_metadata(config.get("metadata")),
        config.get("configurable"),
    )
    metadata.setdefault("environment", runtime.environment)
    metadata.setdefault("version", runtime.release)
    policy = resolve_tenant_policy(metadata)
    full_capture_until = _parse_datetime(
        metadata.get("observability_full_capture_until")
    )
    langfuse_selected = should_sample_trace(
        policy,
        correlation_id=_correlation_id(metadata) or "missing-correlation-id",
        terminal_status=(
            metadata.get("terminal_status")
            if isinstance(metadata.get("terminal_status"), str)
            else None
        ),
        negative_feedback=metadata.get("negative_feedback") is True,
        release_proof=metadata.get("release_proof") is True,
        full_capture_until=full_capture_until,
    )
    metadata = _with_langfuse_trace_attributes(public_trace_metadata(metadata))
    tags = _safe_tags(config.get("tags"))
    tags = sorted(
        set(tags)
        | {
            "service:crypto-alert-v2",
            f"environment:{runtime.environment}",
        }
    )

    # RunnableBinding merges the factory result into this same local config. Mutating
    # these two egress fields ensures removed secret keys cannot survive that merge.
    config["metadata"] = metadata
    config["tags"] = tags
    return metadata, tags, policy, langfuse_selected


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def create_observability_config_factory(
    runtime: ObservabilityRuntimeConfig,
    *,
    handler_factory: HandlerFactory = CallbackHandler,
    langfuse_client_initializer: LangfuseClientInitializer = initialize_langfuse_client,
    langsmith_client_factory: LangsmithClientFactory = initialize_langsmith_client,
    event_sink: EventSink | None = None,
) -> Callable[[RunnableConfig], RunnableConfig]:
    def config_factory(config: RunnableConfig) -> RunnableConfig:
        metadata, tags, policy, langfuse_selected = _normalize_root_config(
            config, runtime
        )
        correlation_id = _correlation_id(metadata)
        callbacks: list[Any] = []
        existing_callbacks = config.get("callbacks")

        if (
            runtime.langsmith_enabled
            and policy.tracing_enabled
            and not _has_handler(existing_callbacks, LangChainTracer)
        ):
            try:
                client = langsmith_client_factory(runtime, policy)
                callbacks.extend(
                    _automatic_langsmith_handlers(
                        client=client,
                        project_name=runtime.langsmith_project,
                        tags=tags,
                        metadata=metadata,
                    )
                )
            except Exception as exc:
                emit_delivery_failure(
                    provider="langsmith",
                    correlation_id=correlation_id,
                    error=exc,
                    stage="bootstrap",
                    event_sink=event_sink,
                )

        if (
            runtime.langfuse_enabled
            and policy.langfuse_enabled
            and langfuse_selected
            and not _has_factory_handler(existing_callbacks, handler_factory)
        ):
            try:
                langfuse_client_initializer(runtime)
                trace_context = _langfuse_trace_context(metadata)
                callbacks.append(
                    handler_factory(
                        public_key=runtime.langfuse_public_key,
                        **(
                            {"trace_context": trace_context}
                            if trace_context is not None
                            else {}
                        ),
                    )
                )
            except Exception as exc:
                emit_delivery_failure(
                    provider="langfuse",
                    correlation_id=correlation_id,
                    error=exc,
                    stage="bootstrap",
                    event_sink=event_sink,
                )

        return {"callbacks": callbacks}

    return config_factory


def build_observability_config(
    base_config: Mapping[str, Any] | None,
    *,
    langfuse_enabled: bool,
    langfuse_public_key: str | None,
    handler_factory: HandlerFactory = CallbackHandler,
) -> dict[str, Any]:
    """Build a standalone RunnableConfig while preserving existing callbacks.

    The canonical graph uses ``create_observability_config_factory`` so every root
    invocation receives a fresh handler. This helper remains useful for callers that
    construct and pass one explicit root config themselves.
    """
    config = dict(base_config or {})
    config["metadata"] = _with_langfuse_trace_attributes(
        _normalize_trace_identity(
            _safe_metadata(config.get("metadata")),
            config.get("configurable"),
        )
    )
    existing_callbacks = config.get("callbacks")
    callbacks: Any = existing_callbacks if existing_callbacks is not None else []
    if langfuse_enabled and not _has_factory_handler(callbacks, handler_factory):
        try:
            handler = handler_factory(public_key=langfuse_public_key)
        except Exception as exc:
            emit_delivery_failure(
                provider="langfuse",
                correlation_id=_correlation_id(config["metadata"]),
                error=exc,
                stage="bootstrap",
            )
            config["callbacks"] = callbacks
            return config
        if isinstance(callbacks, BaseCallbackManager):
            try:
                callbacks = callbacks.copy()
                callbacks.add_handler(handler, inherit=True)
            except Exception as exc:
                emit_delivery_failure(
                    provider="langfuse",
                    correlation_id=_correlation_id(config["metadata"]),
                    error=exc,
                    stage="callback",
                )
                callbacks = existing_callbacks
        else:
            callbacks = [*callbacks, handler]
    config["callbacks"] = callbacks
    return config
