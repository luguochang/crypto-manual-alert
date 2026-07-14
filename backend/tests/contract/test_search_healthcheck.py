from datetime import UTC, datetime

import pytest

from crypto_alert_v2.auth.agent_healthcheck import validate_search_readiness_payload


def _payload() -> dict[str, object]:
    return {
        "status": "ready",
        "selected_provider": "tavily",
        "probed_at": datetime(2026, 7, 14, 9, 0, tzinfo=UTC).isoformat(),
        "model": "capability-test",
        "endpoint": "https://model.example",
        "capabilities": {
            "tool_calling": True,
            "structured_output": True,
            "streaming": True,
            "usage_reporting": True,
            "builtin_web_search_invoked": False,
            "builtin_web_search_citation_count": 0,
            "failures": [],
        },
        "tavily_configured": True,
        "tavily_connected": True,
    }


def test_healthcheck_accepts_only_ready_sanitized_selection() -> None:
    readiness = validate_search_readiness_payload(_payload())

    assert readiness.status == "ready"
    assert readiness.selected_provider == "tavily"


@pytest.mark.parametrize(
    "mutation",
    [
        {"api_key": "must-not-appear"},
        {"endpoint": "https://user:password@model.example/v1?token=secret"},
        {"status": "not_checked"},
    ],
)
def test_healthcheck_rejects_unsanitized_or_unready_payload(
    mutation: dict[str, object],
) -> None:
    payload = {**_payload(), **mutation}

    with pytest.raises(RuntimeError, match="sanitized search readiness"):
        validate_search_readiness_payload(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {**_payload(), "tavily_connected": False},
        {
            **_payload(),
            "capabilities": {
                **_payload()["capabilities"],  # type: ignore[dict-item]
                "streaming": False,
            },
        },
    ],
)
def test_healthcheck_rejects_semantically_inconsistent_ready_payload(
    payload: dict[str, object],
) -> None:
    with pytest.raises(RuntimeError, match="sanitized search readiness"):
        validate_search_readiness_payload(payload)
