from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
import requests
from langfuse import Langfuse
from langfuse.api import AccessDeniedError, NotFoundError, UnauthorizedError
from langfuse.api.core.api_error import ApiError
from langsmith import Client
from langsmith.utils import (
    LangSmithAuthError,
    LangSmithError,
    LangSmithNotFoundError,
    LangSmithRateLimitError,
)

from crypto_alert_v2.observability.identity import langfuse_trace_id_for_product_run
from crypto_alert_v2.observability.verification import (
    ObservabilityVerificationRequest,
    ObservabilityVerifier,
    create_official_verifier,
)


class FakeAdapter:
    def __init__(
        self,
        provider: str,
        *,
        fetch_outcome: object | BaseException = object(),
        read_outcome: object | BaseException = object(),
        listed_runs: list[object] | BaseException | None = None,
    ) -> None:
        self.provider = provider
        self.fetch_outcome = fetch_outcome
        self.read_outcome = read_outcome
        self.listed_runs = listed_runs or []
        self.fetch_thread_id: int | None = None
        self.list_call: tuple[str, str] | None = None
        self.read_run_ids: list[str] = []

    def fetch(self, trace_id: str) -> object:
        assert trace_id == langfuse_trace_id_for_product_run("product-run-1")
        self.fetch_thread_id = threading.get_ident()
        return _outcome(self.fetch_outcome)

    def read_run(self, run_id: str) -> object:
        self.read_run_ids.append(run_id)
        return _outcome(self.read_outcome)

    def list_root_runs(self, *, project_name: str, filter: str) -> list[object]:
        self.list_call = (project_name, filter)
        if isinstance(self.listed_runs, BaseException):
            raise self.listed_runs
        return self.listed_runs


def _outcome(outcome: object | BaseException) -> object:
    if isinstance(outcome, BaseException):
        raise outcome
    return outcome


def langsmith_request(
    *,
    run_id: str | None = None,
    project_name: str | None = "crypto-alert-v2",
) -> ObservabilityVerificationRequest:
    return ObservabilityVerificationRequest(
        provider="langsmith",
        provider_trace_id=run_id,
        product_run_id="product-run-1",
        correlation_id="correlation-1",
        project_name=project_name,
    )


def langfuse_request(
    *,
    provider_trace_id: str | None = None,
) -> ObservabilityVerificationRequest:
    return ObservabilityVerificationRequest(
        provider="langfuse",
        provider_trace_id=(
            provider_trace_id or langfuse_trace_id_for_product_run("product-run-1")
        ),
        product_run_id="product-run-1",
        correlation_id="correlation-1",
    )


def _langsmith_error_with_status(status_code: int) -> LangSmithError:
    response = requests.Response()
    response.status_code = status_code
    http_error = requests.HTTPError("raw response detail", response=response)
    error = LangSmithError("wrapped SDK detail")
    error.__context__ = http_error
    return error


@pytest.mark.asyncio
async def test_sync_adapter_runs_outside_event_loop_and_langfuse_id_is_deterministic() -> (
    None
):
    adapter = FakeAdapter("langfuse")
    verifier = ObservabilityVerifier(adapter)
    event_loop_thread = threading.get_ident()

    result = await verifier.verify(langfuse_request())

    assert result.result == "verified"
    assert result.code == "hosted_trace_visible"
    assert result.provider_trace_id == langfuse_trace_id_for_product_run(
        "product-run-1"
    )
    assert result.error_type is None
    assert adapter.fetch_thread_id is not None
    assert adapter.fetch_thread_id != event_loop_thread


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            LangSmithNotFoundError("provider detail must not escape"),
            ("not_visible", "hosted_trace_not_visible", "not_found"),
        ),
        (
            LangSmithRateLimitError("provider detail must not escape"),
            ("retryable_failure", "hosted_query_retryable", "LangSmithRateLimitError"),
        ),
        (
            LangSmithAuthError("credential detail must not escape"),
            (
                "terminal_failure",
                "hosted_query_authentication_error",
                "authentication",
            ),
        ),
        (
            requests.exceptions.ConnectionError("endpoint detail must not escape"),
            ("retryable_failure", "hosted_query_transport_error", "ConnectionError"),
        ),
        (
            httpx.HTTPStatusError(
                "response detail must not escape",
                request=httpx.Request("GET", "https://example.test"),
                response=httpx.Response(
                    503,
                    request=httpx.Request("GET", "https://example.test"),
                ),
            ),
            ("retryable_failure", "hosted_query_retryable", "server"),
        ),
        (
            _langsmith_error_with_status(502),
            ("retryable_failure", "hosted_query_retryable", "server"),
        ),
        (
            _langsmith_error_with_status(403),
            (
                "terminal_failure",
                "hosted_query_authentication_error",
                "authentication",
            ),
        ),
    ],
)
async def test_langsmith_failures_are_classified_without_raw_error(
    error: BaseException,
    expected: tuple[str, str, str],
) -> None:
    verifier = ObservabilityVerifier(FakeAdapter("langsmith", read_outcome=error))

    result = await verifier.verify(langsmith_request(run_id="langsmith-run-1"))

    assert (result.result, result.code, result.error_type) == expected
    assert result.provider_trace_id == "langsmith-run-1"
    assert "provider detail" not in repr(result)
    assert "credential detail" not in repr(result)
    assert "endpoint detail" not in repr(result)
    assert "response detail" not in repr(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            NotFoundError(body={"detail": "not visible"}),
            ("not_visible", "hosted_trace_not_visible", "not_found"),
        ),
        (
            UnauthorizedError(body={"detail": "credential detail"}),
            (
                "terminal_failure",
                "hosted_query_authentication_error",
                "authentication",
            ),
        ),
        (
            AccessDeniedError(body={"detail": "access detail"}),
            (
                "terminal_failure",
                "hosted_query_authentication_error",
                "authentication",
            ),
        ),
        (
            ApiError(status_code=429, body={"detail": "rate detail"}),
            ("retryable_failure", "hosted_query_retryable", "rate_limit"),
        ),
        (
            ApiError(status_code=503, body={"detail": "server detail"}),
            ("retryable_failure", "hosted_query_retryable", "server"),
        ),
    ],
)
async def test_langfuse_failures_are_classified_without_raw_error(
    error: BaseException,
    expected: tuple[str, str, str],
) -> None:
    verifier = ObservabilityVerifier(FakeAdapter("langfuse", fetch_outcome=error))

    result = await verifier.verify(langfuse_request())

    assert (result.result, result.code, result.error_type) == expected
    assert "detail" not in repr(result)


@pytest.mark.asyncio
async def test_langsmith_metadata_readback_requires_exact_product_identity() -> None:
    adapter = FakeAdapter(
        "langsmith",
        listed_runs=[
            SimpleNamespace(
                id="matching-run",
                extra={
                    "metadata": {
                        "product_run_id": "product-run-1",
                        "correlation_id": "correlation-1",
                    }
                },
            ),
        ],
    )

    result = await ObservabilityVerifier(adapter).verify(langsmith_request())

    assert result.result == "verified"
    assert result.provider_trace_id == "matching-run"
    assert adapter.list_call is not None
    project_name, filter_value = adapter.list_call
    assert project_name == "crypto-alert-v2"
    assert 'eq(metadata_key, "product_run_id")' in filter_value
    assert 'eq(metadata_value, "product-run-1")' in filter_value
    assert "product_run_id" in filter_value


@pytest.mark.asyncio
async def test_langsmith_metadata_readback_zero_results_is_not_visible() -> None:
    adapter = FakeAdapter(
        "langsmith",
        listed_runs=[],
    )

    result = await ObservabilityVerifier(adapter).verify(langsmith_request())

    assert (result.result, result.code, result.error_type) == (
        "not_visible",
        "hosted_trace_not_visible",
        "not_found",
    )
    assert result.provider_trace_id is None


@pytest.mark.asyncio
async def test_langsmith_metadata_readback_multiple_results_is_correlation_conflict() -> (
    None
):
    matching_metadata = {
        "product_run_id": "product-run-1",
        "correlation_id": "correlation-1",
    }
    adapter = FakeAdapter(
        "langsmith",
        listed_runs=[
            SimpleNamespace(id="matching-run-1", metadata=matching_metadata),
            SimpleNamespace(id="matching-run-2", metadata=matching_metadata),
        ],
    )

    result = await ObservabilityVerifier(adapter).verify(langsmith_request())

    assert (result.result, result.code, result.error_type) == (
        "terminal_failure",
        "hosted_query_correlation_conflict",
        "correlation_conflict",
    )
    assert result.provider_trace_id is None


@pytest.mark.asyncio
async def test_langsmith_metadata_readback_rejects_single_wrong_identity() -> None:
    adapter = FakeAdapter(
        "langsmith",
        listed_runs=[
            {
                "metadata": {
                    "product_run_id": "different-run",
                    "correlation_id": "correlation-1",
                }
            }
        ],
    )

    result = await ObservabilityVerifier(adapter).verify(langsmith_request())

    assert (result.result, result.code, result.error_type) == (
        "terminal_failure",
        "hosted_query_identity_mismatch",
        "identity_mismatch",
    )


def test_official_langsmith_factory_delegates_to_read_run_only_when_explicitly_given() -> (
    None
):
    client = Mock(spec=Client)
    client.read_run.return_value = object()
    verifier = create_official_verifier("langsmith", client)

    result = asyncio.run(
        verifier.verify(langsmith_request(run_id="explicit-langsmith-run"))
    )

    assert result.result == "verified"
    assert result.provider_trace_id == "explicit-langsmith-run"
    client.read_run.assert_called_once_with("explicit-langsmith-run")
    client.list_runs.assert_not_called()


def test_official_langsmith_factory_uses_root_metadata_readback_without_run_id() -> (
    None
):
    client = Mock(spec=Client)
    client.list_runs.return_value = iter(
        [
            SimpleNamespace(
                id="hosted-root-run",
                metadata={
                    "product_run_id": "product-run-1",
                    "correlation_id": "correlation-1",
                },
            )
        ]
    )
    verifier = create_official_verifier("langsmith", client)

    result = asyncio.run(verifier.verify(langsmith_request()))

    assert result.result == "verified"
    assert result.provider_trace_id == "hosted-root-run"
    call = client.list_runs.call_args
    assert call.kwargs["project_name"] == "crypto-alert-v2"
    assert call.kwargs["is_root"] is True
    assert call.kwargs["limit"] == 2
    assert "product_run_id" in call.kwargs["filter"]
    assert "metadata_key" in call.kwargs["filter"]
    assert "metadata_value" in call.kwargs["filter"]
    assert "correlation_id" not in call.kwargs["filter"]
    client.read_run.assert_not_called()


def test_official_langfuse_factory_delegates_to_api_trace_get() -> None:
    client = Mock(spec=Langfuse)
    client.api.trace.get.return_value = object()
    verifier = create_official_verifier("langfuse", client)
    expected_trace_id = langfuse_trace_id_for_product_run("product-run-1")

    result = asyncio.run(verifier.verify(langfuse_request()))

    assert result.result == "verified"
    assert result.provider_trace_id == expected_trace_id
    client.api.trace.get.assert_called_once_with(expected_trace_id)


def test_request_rejects_ambiguous_provider_identity() -> None:
    with pytest.raises(ValueError, match="product_run_id is required"):
        ObservabilityVerificationRequest(
            provider="langsmith",
            provider_trace_id=None,
            product_run_id="",
            correlation_id="correlation-1",
            project_name="crypto-alert-v2",
        )
    with pytest.raises(ValueError, match="project_name is required"):
        langsmith_request(project_name=None)
    with pytest.raises(ValueError, match="provider_trace_id is required"):
        ObservabilityVerificationRequest(
            provider="langfuse",
            provider_trace_id=None,
            product_run_id="product-run-1",
            correlation_id="correlation-1",
        )


def test_result_has_only_stable_fields_and_no_raw_error() -> None:
    result = asyncio.run(
        ObservabilityVerifier(
            FakeAdapter(
                "langsmith",
                read_outcome=ValueError("raw provider detail"),
            )
        ).verify(langsmith_request(run_id="langsmith-run-1"))
    )

    assert result.__slots__ == (
        "provider",
        "provider_trace_id",
        "result",
        "code",
        "error_type",
    )
    assert "raw provider detail" not in repr(result)
