import io
import json
import logging

from langfuse.types import MaskOtelSpansParams, OtelSpanData, OtelSpanIdentifier

from crypto_alert_v2.observability.logging import (
    SdkFailureEventHandler,
    SecretRedactionFilter,
    install_sdk_log_redaction,
)
from crypto_alert_v2.observability.redaction import (
    REDACTED,
    mask_langfuse_otel_spans,
    mask_langfuse_payload,
    redact_metadata,
    redact_payload,
    redact_text,
    redact_with_event,
)


CANARY = "canary-secret-20260716"


def test_legacy_bark_path_credential_is_removed_from_text() -> None:
    rendered = redact_text(f"POST https://api.day.app/{CANARY}?title=done")

    assert CANARY not in rendered
    assert rendered == f"POST https://api.day.app/{REDACTED}"


def test_all_observability_egress_surfaces_are_redacted_before_serialization() -> None:
    payload = {
        "headers": {
            "Authorization": f"Bearer {CANARY}",
            "Cookie": f"session={CANARY}",
            "X-API-Key": CANARY,
        },
        "prompt": f"Use api_key={CANARY} for this prompt",
        "tool_result": f"Cookie: session={CANARY}",
        "model_output": f"Bearer {CANARY}",
        "url": f"https://user:{CANARY}@example.test/path?api_key={CANARY}",
        "database_url": f"postgresql://user:{CANARY}@db.example.test/app?ssl=true",
        "pii": {
            "email": "trader@example.com",
            "credit_card": "4111 1111 1111 1111",
            "ip": "203.0.113.42",
            "mac": "00:1A:2B:3C:4D:5E",
            "phone": "+86 138 0013 8000",
        },
        "nested": [{"client_secret": CANARY}],
    }

    result = redact_with_event(payload, boundary="trace_export")
    serialized = json.dumps(result.value, sort_keys=True)

    assert CANARY not in serialized
    assert "user:" not in serialized
    assert "?api_key" not in serialized
    assert "trader@example.com" not in serialized
    assert "4111 1111 1111 1111" not in serialized
    assert "203.0.113.42" not in serialized
    assert "00:1A:2B:3C:4D:5E" not in serialized
    assert "+86 138 0013 8000" not in serialized
    assert serialized.count(REDACTED) >= 6
    assert result.event.event == "observability_egress_redaction"
    assert result.event.boundary == "trace_export"
    assert result.event.redaction_count >= 6
    assert {
        "bearer",
        "header",
        "pii_credit_card",
        "pii_email",
        "pii_ip",
        "pii_mac_address",
        "pii_phone",
        "sensitive_key",
        "url",
    } <= set(result.event.categories)


def test_trace_metadata_drops_sensitive_keys_and_keeps_usage_metrics() -> None:
    metadata = {
        "tenant_id": "tenant-1",
        "langsmith_api_key": CANARY,
        "nested": {"cookie": CANARY, "input_tokens": 42},
    }
    assert redact_metadata(metadata) == {
        "tenant_id": "tenant-1",
        "nested": {"input_tokens": 42},
    }


def test_langfuse_otel_exporter_masks_sensitive_span_attributes() -> None:
    result = mask_langfuse_otel_spans(
        params=MaskOtelSpansParams(
            spans={
                OtelSpanIdentifier(trace_id="trace-1", span_id="span-1"): OtelSpanData(
                    trace_id="trace-1",
                    span_id="span-1",
                    parent_span_id=None,
                    name="chat model",
                    instrumentation_scope_name="langchain",
                    instrumentation_scope_version=None,
                    attributes={
                        "gen_ai.prompt.0.content": f"api_key={CANARY}",
                        "authorization": f"Bearer {CANARY}",
                        "gen_ai.usage.input_tokens": 42,
                    },
                    resource_attributes={"service.name": "crypto-alert-v2"},
                )
            }
        )
    )

    assert result is not None
    patch = next(iter(result.span_patches.values()))
    assert patch is not None
    serialized = json.dumps(patch.set_attributes, sort_keys=True)
    assert CANARY not in serialized
    assert patch.set_attributes["authorization"] == REDACTED
    assert "gen_ai.usage.input_tokens" not in patch.set_attributes


def test_langfuse_payload_mask_accepts_the_official_keyword_contract() -> None:
    assert mask_langfuse_payload(data={"authorization": f"Bearer {CANARY}"}) == {
        "authorization": REDACTED
    }


def test_redaction_does_not_mutate_business_payload() -> None:
    payload = {"terminal_status": "succeeded", "output": f"Bearer {CANARY}"}

    redacted = redact_payload(payload)

    assert payload["terminal_status"] == "succeeded"
    assert payload["output"] == f"Bearer {CANARY}"
    assert redacted == {"terminal_status": "succeeded", "output": f"Bearer {REDACTED}"}


def test_log_filter_removes_secrets_from_message_and_exception() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(SecretRedactionFilter())
    test_logger = logging.getLogger("tests.secret-redaction")
    test_logger.handlers = [handler]
    test_logger.propagate = False
    test_logger.setLevel(logging.INFO)

    try:
        raise RuntimeError(f"request failed Authorization: Bearer {CANARY}")
    except RuntimeError:
        test_logger.exception("model output api_key=%s", CANARY)

    rendered = stream.getvalue()
    assert CANARY not in rendered
    assert REDACTED in rendered


def test_sdk_log_redaction_installation_is_idempotent() -> None:
    install_sdk_log_redaction()
    install_sdk_log_redaction()

    for logger_name in (
        "httpx",
        "langfuse",
        "langsmith.client",
        "opentelemetry.exporter.otlp",
    ):
        filters = [
            item
            for item in logging.getLogger(logger_name).filters
            if isinstance(item, SecretRedactionFilter)
        ]
        assert len(filters) == 1
    handlers = [
        item
        for item in logging.getLogger("langfuse").handlers
        if isinstance(item, SdkFailureEventHandler)
    ]
    assert len(handlers) == 1
    otel_handlers = [
        item
        for item in logging.getLogger("opentelemetry.exporter.otlp").handlers
        if isinstance(item, SdkFailureEventHandler)
    ]
    assert len(otel_handlers) == 1


def test_sdk_child_logger_is_redacted_before_any_handler_formats_it() -> None:
    install_sdk_log_redaction()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    child_logger = logging.getLogger("langsmith.run_helpers.transport")
    original_handlers = child_logger.handlers
    original_propagate = child_logger.propagate
    child_logger.handlers = [handler]
    child_logger.propagate = False
    child_logger.setLevel(logging.ERROR)
    try:
        child_logger.error("Authorization: Bearer %s", CANARY)
    finally:
        child_logger.handlers = original_handlers
        child_logger.propagate = original_propagate

    rendered = stream.getvalue()
    assert CANARY not in rendered
    assert REDACTED in rendered
