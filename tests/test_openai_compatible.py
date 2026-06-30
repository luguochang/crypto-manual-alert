import httpx
import pytest

from crypto_manual_alert.journal import Journal
from crypto_manual_alert.observability import ObservabilityRecorder, use_observability
from crypto_manual_alert.skill_runtime import CommandDecisionEngine, OpenAICompatibleDecisionEngine


def test_openai_compatible_engine_posts_chat_completion_and_returns_content():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url == "https://example.test/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key"
        payload = __import__("json").loads(request.content)
        assert payload["model"] == "gpt-test"
        assert payload["messages"][0]["role"] == "system"
        system_prompt = payload["messages"][0]["content"]
        assert "简体中文" in system_prompt
        assert "why_not_opposite" in system_prompt
        assert "notes" in system_prompt
        assert "market_snapshot" in payload["messages"][1]["content"]
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"instrument":"ETH-USDT-SWAP","main_action":"no trade","manual_execution_required":true}'}}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    engine = OpenAICompatibleDecisionEngine(
        base_url="https://example.test",
        api_key="test-key",
        model="gpt-test",
        timeout_seconds=30,
        client=client,
    )

    content = engine.run({"market_snapshot": {"symbol": "ETH-USDT-SWAP"}})

    assert requests
    assert '"main_action":"no trade"' in content


def test_openai_compatible_engine_records_llm_interaction_when_trace_is_active(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"instrument":"ETH-USDT-SWAP","main_action":"no trade"}'},
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
            },
        )

    journal = Journal(tmp_path / "journal.db")
    recorder = ObservabilityRecorder(journal)
    trace_id = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    engine = OpenAICompatibleDecisionEngine(
        base_url="https://example.test",
        api_key="test-key",
        model="gpt-test",
        timeout_seconds=30,
        client=client,
    )

    with recorder.span(trace_id, "decision.final", "decision.llm") as span:
        with use_observability(recorder, trace_id):
            engine.run({"market_snapshot": {"symbol": "ETH-USDT-SWAP"}})
        span_id = span.span_id

    with journal.connect() as conn:
        row = conn.execute(
            """
            SELECT component, model, status, span_id, request_json, duration_ms,
                   prompt_tokens, completion_tokens, total_tokens, finish_reason, retry_count
            FROM llm_interactions
            """
        ).fetchone()

    assert row["component"] == "decision.final"
    assert row["model"] == "gpt-test"
    assert row["status"] == "ok"
    assert row["span_id"] == span_id
    assert "test-key" not in row["request_json"]
    assert row["duration_ms"] >= 0
    assert row["prompt_tokens"] == 12
    assert row["completion_tokens"] == 8
    assert row["total_tokens"] == 20
    assert row["finish_reason"] == "stop"
    assert row["retry_count"] == 0


def test_command_decision_engine_rejects_shell_string_commands():
    with pytest.raises(ValueError, match="disabled"):
        CommandDecisionEngine("python decide.py", timeout_seconds=30)
