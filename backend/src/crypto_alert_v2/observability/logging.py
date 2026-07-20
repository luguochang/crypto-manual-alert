from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
import json
import logging
from typing import Any, Literal

from crypto_alert_v2.observability.redaction import redact_payload, redact_text


logger = logging.getLogger("crypto_alert_v2.observability.delivery")
ObservabilityProvider = Literal["langsmith", "langfuse"]
ObservabilityDeliveryStage = Literal[
    "bootstrap",
    "callback",
    "transport",
    "flush",
]
EventSink = Callable[[dict[str, Any]], None]
_LANGFUSE_OTEL_LOGGER = "opentelemetry.exporter.otlp"
_SDK_LOGGER_PREFIXES = (
    "httpcore",
    "httpx",
    "langfuse",
    "langsmith",
    _LANGFUSE_OTEL_LOGGER,
    "urllib3",
)
_DELIVERY_STAGES = frozenset({"bootstrap", "callback", "transport", "flush"})


class SecretRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact_text(record.getMessage())
        except Exception:
            record.msg = "[REDACTED LOG RECORD]"
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        return True


class SdkFailureEventHandler(logging.Handler):
    def __init__(self, provider: ObservabilityProvider) -> None:
        super().__init__(level=logging.ERROR)
        self.provider = provider

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.ERROR:
            return
        try:
            emit_delivery_failure(
                provider=self.provider,
                correlation_id=None,
                error=RuntimeError("SDK delivery error"),
                stage="transport",
            )
        except Exception:
            pass


def install_sdk_log_redaction() -> None:
    _install_sdk_record_factory()
    for logger_name in (
        "httpcore",
        "httpx",
        "langfuse",
        "langsmith",
        "langsmith.client",
        _LANGFUSE_OTEL_LOGGER,
        "urllib3",
        "urllib3.connectionpool",
    ):
        sdk_logger = logging.getLogger(logger_name)
        if not any(
            isinstance(item, SecretRedactionFilter) for item in sdk_logger.filters
        ):
            sdk_logger.addFilter(SecretRedactionFilter())
    langfuse_logger = logging.getLogger("langfuse")
    if not any(
        isinstance(item, SdkFailureEventHandler) for item in langfuse_logger.handlers
    ):
        langfuse_logger.addHandler(SdkFailureEventHandler("langfuse"))
    otel_logger = logging.getLogger(_LANGFUSE_OTEL_LOGGER)
    if not any(
        isinstance(item, SdkFailureEventHandler) for item in otel_logger.handlers
    ):
        otel_logger.addHandler(SdkFailureEventHandler("langfuse"))


def _install_sdk_record_factory() -> None:
    current_factory = logging.getLogRecordFactory()
    if getattr(current_factory, "_crypto_alert_sdk_redaction", False):
        return

    def redacting_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = current_factory(*args, **kwargs)
        if any(
            record.name == prefix or record.name.startswith(f"{prefix}.")
            for prefix in _SDK_LOGGER_PREFIXES
        ):
            SecretRedactionFilter().filter(record)
        return record

    redacting_factory._crypto_alert_sdk_redaction = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(redacting_factory)


def _validated_stage(stage: ObservabilityDeliveryStage) -> ObservabilityDeliveryStage:
    if stage not in _DELIVERY_STAGES:
        raise ValueError(f"Unsupported observability delivery stage: {stage}")
    return stage


def alert_fingerprint(
    provider: ObservabilityProvider,
    error_type: str,
) -> str:
    material = f"observability_delivery_failure:{provider}:{error_type}"
    return sha256(material.encode("utf-8")).hexdigest()[:24]


def build_delivery_failure_event(
    *,
    provider: ObservabilityProvider,
    correlation_id: str | None,
    error: BaseException,
    stage: ObservabilityDeliveryStage = "callback",
    retry_state: str = "exhausted",
    dropped: bool = True,
    sampled: bool = False,
) -> dict[str, Any]:
    stage = _validated_stage(stage)
    error_type = type(error).__name__
    return {
        "event": "observability_delivery_failure",
        "provider": provider,
        "stage": stage,
        "correlation_id": correlation_id or "unknown",
        "retry_state": retry_state,
        "dropped": dropped,
        "sampled": sampled,
        "error_type": error_type,
        "alert_fingerprint": alert_fingerprint(provider, error_type),
    }


def emit_delivery_failure(
    *,
    provider: ObservabilityProvider,
    correlation_id: str | None,
    error: BaseException,
    stage: ObservabilityDeliveryStage = "callback",
    retry_state: str = "exhausted",
    dropped: bool = True,
    sampled: bool = False,
    event_sink: EventSink | None = None,
) -> dict[str, Any]:
    event = build_delivery_failure_event(
        provider=provider,
        correlation_id=correlation_id,
        error=error,
        stage=stage,
        retry_state=retry_state,
        dropped=dropped,
        sampled=sampled,
    )
    safe_event = redact_payload(event)
    try:
        if event_sink is not None:
            event_sink(safe_event)
        else:
            logger.warning(
                json.dumps(safe_event, sort_keys=True, separators=(",", ":"))
            )
    except Exception:
        # A diagnostic sink is never allowed to become a business-path failure.
        pass
    return safe_event
