from types import SimpleNamespace

from crypto_alert_v2.agents.execution_audit import build_model_execution_audit


def test_model_execution_audit_extracts_only_official_message_metadata() -> None:
    result = {
        "messages": [
            SimpleNamespace(type="human", content="secret prompt"),
            SimpleNamespace(
                type="ai",
                content="secret structured output",
                usage_metadata={
                    "input_tokens": 11,
                    "output_tokens": 7,
                    "total_tokens": 18,
                },
                response_metadata={"id": "resp_1", "authorization": "secret"},
            ),
            SimpleNamespace(
                type="ai",
                content="another secret",
                usage_metadata={
                    "input_tokens": 3,
                    "output_tokens": 2,
                    "total_tokens": 5,
                },
                response_metadata={"id": "resp_2"},
            ),
        ],
        "structured_response": {"private": "must not be inspected"},
    }

    audit = build_model_execution_audit(
        result,
        prompt_version="test-v1",
        started_at=0.0,
    )

    assert audit.prompt_version == "test-v1"
    assert audit.call_count == 2
    assert audit.input_tokens == 14
    assert audit.output_tokens == 9
    assert audit.total_tokens == 23
    assert audit.latency_ms >= 0
    assert audit.observation_ids == ["resp_1", "resp_2"]


def test_model_execution_audit_keeps_missing_usage_nullable() -> None:
    audit = build_model_execution_audit(
        {
            "messages": [
                SimpleNamespace(type="ai", content="not persisted"),
            ]
        },
        prompt_version="test-v1",
        started_at=0.0,
    )

    assert audit.call_count == 1
    assert audit.input_tokens is None
    assert audit.output_tokens is None
    assert audit.total_tokens is None
    assert audit.observation_ids == []
