from datetime import UTC, datetime

import pytest

from crypto_alert_v2.auth.agent_healthcheck import (
    validate_product_health_payload,
    validate_search_readiness_payload,
)
from crypto_alert_v2.providers.capability_probe import SearchProvider


def _payload(provider: SearchProvider = SearchProvider.TAVILY) -> dict[str, object]:
    builtin = provider is SearchProvider.BUILTIN
    return {
        "status": "ready",
        "selected_provider": provider.value,
        "probed_at": datetime(2026, 7, 14, 9, 0, tzinfo=UTC).isoformat(),
        "model": "capability-test",
        "endpoint": "https://model.example",
        "capabilities": {
            "tool_calling": True,
            "structured_output": True,
            "streaming": True,
            "usage_reporting": True,
            "builtin_web_search_invoked": builtin,
            "builtin_web_search_citation_count": 1 if builtin else 0,
            "failures": [],
        },
        "tavily_configured": not builtin,
        "tavily_connected": not builtin,
    }


@pytest.mark.parametrize(
    "configured_provider",
    [SearchProvider.BUILTIN, SearchProvider.TAVILY],
)
def test_healthcheck_accepts_effective_provider_matching_configuration(
    configured_provider: SearchProvider,
) -> None:
    readiness = validate_search_readiness_payload(
        _payload(configured_provider),
        expected_provider=configured_provider,
    )

    assert readiness.status == "ready"
    assert readiness.selected_provider is configured_provider


def test_healthcheck_rejects_ready_selection_from_a_different_provider() -> None:
    with pytest.raises(RuntimeError, match="sanitized search readiness"):
        validate_search_readiness_payload(
            _payload(),
            expected_provider=SearchProvider.BUILTIN,
        )


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


def test_healthcheck_accepts_strict_product_health_payload() -> None:
    health = validate_product_health_payload({"status": "ok", "version": "2.0.0"})

    assert health == {"status": "ok", "version": "2.0.0"}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"status": "ok"},
        {"status": "degraded", "version": "2.0.0"},
        {"status": "ok", "version": "2.0.1"},
        {"status": "ok", "version": "2.0.0", "detail": "unexpected"},
    ],
)
def test_healthcheck_rejects_invalid_product_health_payload(
    payload: dict[str, object],
) -> None:
    with pytest.raises(RuntimeError, match="invalid Product health"):
        validate_product_health_payload(payload)
