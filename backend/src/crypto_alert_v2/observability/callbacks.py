from collections.abc import Callable, Mapping
import logging
from typing import Any

from langfuse.langchain import CallbackHandler
from langchain_core.callbacks.base import BaseCallbackManager


logger = logging.getLogger(__name__)


SENSITIVE_KEY_MARKERS = (
    "authorization",
    "cookie",
    "apikey",
    "secret",
    "password",
    "token",
    "barkkey",
    "langsmithkey",
    "langfusekey",
)


def _normalized_key(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def redact_metadata(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, nested in value.items():
            text_key = str(key)
            normalized = _normalized_key(text_key)
            if any(marker in normalized for marker in SENSITIVE_KEY_MARKERS):
                continue
            redacted[text_key] = redact_metadata(nested)
        return redacted
    if isinstance(value, list):
        return [redact_metadata(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_metadata(item) for item in value)
    return value


def _with_langfuse_trace_attributes(metadata: dict[str, Any]) -> dict[str, Any]:
    user_id = metadata.get("user_id")
    if isinstance(user_id, str) and user_id:
        metadata.setdefault("langfuse_user_id", user_id)
    thread_id = metadata.get("thread_id")
    if isinstance(thread_id, str) and thread_id:
        metadata.setdefault("langfuse_session_id", thread_id)
    return metadata


def _has_langfuse_handler(
    callbacks: Any,
    handler_factory: Callable[..., Any],
) -> bool:
    handlers = (
        callbacks.handlers if isinstance(callbacks, BaseCallbackManager) else callbacks
    )
    if not handlers:
        return False
    factory_type = handler_factory if isinstance(handler_factory, type) else None
    return any(
        isinstance(handler, CallbackHandler)
        or (factory_type is not None and isinstance(handler, factory_type))
        for handler in handlers
    )


def build_observability_config(
    base_config: Mapping[str, Any] | None,
    *,
    langfuse_enabled: bool,
    langfuse_public_key: str | None,
    handler_factory: Callable[..., Any] = CallbackHandler,
) -> dict[str, Any]:
    config = dict(base_config or {})
    config["metadata"] = _with_langfuse_trace_attributes(
        redact_metadata(config.get("metadata") or {})
    )
    existing_callbacks = config.get("callbacks")
    callbacks: Any = existing_callbacks if existing_callbacks is not None else []
    if langfuse_enabled and not _has_langfuse_handler(callbacks, handler_factory):
        try:
            handler = handler_factory(public_key=langfuse_public_key)
        except Exception as exc:
            logger.warning(
                "Langfuse callback construction failed; tracing is disabled for this root: %s",
                type(exc).__name__,
            )
            config["callbacks"] = callbacks
            return config
        if isinstance(callbacks, BaseCallbackManager):
            try:
                callbacks = callbacks.copy()
                callbacks.add_handler(handler, inherit=True)
            except Exception as exc:
                logger.warning(
                    "Langfuse callback attachment failed; tracing is disabled for this root: %s",
                    type(exc).__name__,
                )
                callbacks = existing_callbacks
        else:
            callbacks = [*callbacks, handler]
    config["callbacks"] = callbacks
    return config
