from __future__ import annotations

import sys

import crypto_manual_alert.telemetry.llm as canonical_llm_telemetry
import crypto_manual_alert.telemetry.observability as canonical_observability


def test_telemetry_package_import_does_not_eagerly_import_implementation_modules():
    previous_llm = sys.modules.pop("crypto_manual_alert.telemetry.llm", None)
    previous_observability = sys.modules.pop("crypto_manual_alert.telemetry.observability", None)
    sys.modules.pop("crypto_manual_alert.telemetry", None)
    try:
        __import__("crypto_manual_alert.telemetry")

        assert "crypto_manual_alert.telemetry.llm" not in sys.modules
        assert "crypto_manual_alert.telemetry.observability" not in sys.modules
    finally:
        sys.modules.pop("crypto_manual_alert.telemetry", None)
        if previous_llm is not None:
            sys.modules["crypto_manual_alert.telemetry.llm"] = previous_llm
        if previous_observability is not None:
            sys.modules["crypto_manual_alert.telemetry.observability"] = previous_observability


def test_llm_telemetry_package_exports_canonical_objects():
    assert canonical_llm_telemetry.LlmTelemetry
    assert canonical_llm_telemetry.extract_chat_completion_telemetry
    assert canonical_llm_telemetry.extract_responses_telemetry


def test_observability_package_exports_canonical_objects():
    assert canonical_observability.ObservabilityRecorder
    assert canonical_observability.SpanHandle
    assert canonical_observability.use_observability
    assert canonical_observability.record_llm_interaction
