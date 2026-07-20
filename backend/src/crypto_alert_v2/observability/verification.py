from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal, Protocol, cast, overload

import httpx
import requests
from langfuse import Langfuse
from langfuse.api import (
    AccessDeniedError,
    Error as LangfuseRequestError,
    NotFoundError,
    UnauthorizedError,
)
from langfuse.api.core.api_error import ApiError as LangfuseApiError
from langsmith import Client
from langsmith.utils import (
    LangSmithAPIError,
    LangSmithAuthError,
    LangSmithConnectionError,
    LangSmithNotFoundError,
    LangSmithRateLimitError,
    LangSmithRequestTimeout,
    LangSmithUserError,
)

ObservabilityProvider = Literal["langsmith", "langfuse"]
VerificationOutcome = Literal[
    "verified",
    "not_visible",
    "retryable_failure",
    "terminal_failure",
]


@dataclass(frozen=True, slots=True)
class ObservabilityVerificationRequest:
    """Identity and lookup mode for one hosted trace verification."""

    provider: ObservabilityProvider
    provider_trace_id: str | None
    product_run_id: str
    correlation_id: str
    project_name: str | None = None

    def __post_init__(self) -> None:
        if self.provider not in ("langsmith", "langfuse"):
            raise ValueError("unsupported observability provider")
        if not self.product_run_id.strip():
            raise ValueError("product_run_id is required")
        if not self.correlation_id.strip():
            raise ValueError("correlation_id is required")

        if self.provider == "langsmith":
            if self.provider_trace_id is None and not self._project_name:
                raise ValueError(
                    "project_name is required for LangSmith metadata readback"
                )
            return

        if self.provider_trace_id is None or not self.provider_trace_id.strip():
            raise ValueError("provider_trace_id is required for Langfuse verification")

    @property
    def _project_name(self) -> str | None:
        if self.project_name is None:
            return None
        value = self.project_name.strip()
        return value or None


@dataclass(frozen=True, slots=True)
class ObservabilityVerificationResult:
    """A stable, redacted result from a hosted trace read-after-write check."""

    provider: ObservabilityProvider
    provider_trace_id: str | None
    result: VerificationOutcome
    code: str
    error_type: str | None = None


class LangSmithTraceAdapter(Protocol):
    provider: Literal["langsmith"]

    def read_run(self, run_id: str) -> object:
        """Read a known LangSmith run using the official SDK."""

    def list_root_runs(self, *, project_name: str, filter: str) -> list[object]:
        """List candidate root runs using the official SDK."""


class LangfuseTraceAdapter(Protocol):
    provider: Literal["langfuse"]

    def fetch(self, trace_id: str) -> object:
        """Read a Langfuse trace using the official SDK."""


HostedTraceAdapter = LangSmithTraceAdapter | LangfuseTraceAdapter


class OfficialLangSmithAdapter:
    """Thin adapter over the official synchronous LangSmith Client."""

    provider: Literal["langsmith"] = "langsmith"

    def __init__(self, client: Client) -> None:
        self._client = client

    def read_run(self, run_id: str) -> object:
        return self._client.read_run(run_id)

    def list_root_runs(self, *, project_name: str, filter: str) -> list[object]:
        return list(
            self._client.list_runs(
                project_name=project_name,
                is_root=True,
                filter=filter,
                limit=2,
            )
        )


class OfficialLangfuseAdapter:
    """Thin adapter over the official synchronous Langfuse trace API."""

    provider: Literal["langfuse"] = "langfuse"

    def __init__(self, client: Langfuse) -> None:
        self._client = client

    def fetch(self, trace_id: str) -> object:
        return self._client.api.trace.get(trace_id)


class ObservabilityVerifier:
    """Verify hosted visibility without treating SDK flush as a receipt."""

    def __init__(
        self,
        adapter: HostedTraceAdapter,
        *,
        timeout_seconds: float = 10.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("verification timeout must be positive")
        self._adapter = adapter
        self._timeout_seconds = timeout_seconds

    async def verify(
        self, request: ObservabilityVerificationRequest
    ) -> ObservabilityVerificationResult:
        if request.provider != self._adapter.provider:
            return _result(
                request,
                result="terminal_failure",
                code="hosted_query_provider_mismatch",
                error_type="configuration",
            )

        if request.provider == "langsmith":
            return await self._verify_langsmith(
                cast(LangSmithTraceAdapter, self._adapter), request
            )
        return await self._verify_langfuse(
            cast(LangfuseTraceAdapter, self._adapter), request
        )

    async def _verify_langsmith(
        self,
        adapter: LangSmithTraceAdapter,
        request: ObservabilityVerificationRequest,
    ) -> ObservabilityVerificationResult:
        if request.provider_trace_id is not None:
            try:
                await self._run_sync(adapter.read_run, request.provider_trace_id)
            except Exception as exc:
                return _classified_result(
                    request,
                    exc,
                    provider_trace_id=request.provider_trace_id,
                )
            return _result(
                request,
                provider_trace_id=request.provider_trace_id,
                result="verified",
                code="hosted_trace_visible",
            )

        project_name = request._project_name
        if project_name is None:
            return _result(
                request,
                result="terminal_failure",
                code="hosted_query_invalid_request",
                error_type="invalid_request",
            )

        try:
            runs = await self._run_sync(
                adapter.list_root_runs,
                project_name=project_name,
                filter=_langsmith_identity_filter(request),
            )
        except Exception as exc:
            return _classified_result(request, exc)

        if not runs:
            return _result(
                request,
                result="not_visible",
                code="hosted_trace_not_visible",
                error_type="not_found",
            )
        if len(runs) > 1:
            return _result(
                request,
                result="terminal_failure",
                code="hosted_query_correlation_conflict",
                error_type="correlation_conflict",
            )
        if not _run_matches_identity(runs[0], request):
            return _result(
                request,
                result="terminal_failure",
                code="hosted_query_identity_mismatch",
                error_type="identity_mismatch",
            )
        return _result(
            request,
            provider_trace_id=_run_id(runs[0]),
            result="verified",
            code="hosted_trace_visible",
        )

    async def _verify_langfuse(
        self,
        adapter: LangfuseTraceAdapter,
        request: ObservabilityVerificationRequest,
    ) -> ObservabilityVerificationResult:
        assert request.provider_trace_id is not None
        trace_id = request.provider_trace_id
        try:
            await self._run_sync(adapter.fetch, trace_id)
        except Exception as exc:
            return _classified_result(request, exc, provider_trace_id=trace_id)
        return _result(
            request,
            provider_trace_id=trace_id,
            result="verified",
            code="hosted_trace_visible",
        )

    async def _run_sync(
        self, operation: Callable[..., object], *args: object, **kwargs: object
    ) -> object:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(operation, *args, **kwargs),
                timeout=self._timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise _VerificationTimeout from exc


@overload
def create_official_verifier(
    provider: Literal["langsmith"],
    client: Client,
    *,
    timeout_seconds: float = 10.0,
) -> ObservabilityVerifier: ...


@overload
def create_official_verifier(
    provider: Literal["langfuse"],
    client: Langfuse,
    *,
    timeout_seconds: float = 10.0,
) -> ObservabilityVerifier: ...


def create_official_verifier(
    provider: ObservabilityProvider,
    client: Client | Langfuse,
    *,
    timeout_seconds: float = 10.0,
) -> ObservabilityVerifier:
    """Build a verifier bound to an official provider SDK client."""

    if provider == "langsmith":
        return ObservabilityVerifier(
            OfficialLangSmithAdapter(cast(Client, client)),
            timeout_seconds=timeout_seconds,
        )
    return ObservabilityVerifier(
        OfficialLangfuseAdapter(cast(Langfuse, client)),
        timeout_seconds=timeout_seconds,
    )


class _VerificationTimeout(TimeoutError):
    pass


def _result(
    request: ObservabilityVerificationRequest,
    *,
    result: VerificationOutcome,
    code: str,
    error_type: str | None = None,
    provider_trace_id: str | None = None,
) -> ObservabilityVerificationResult:
    return ObservabilityVerificationResult(
        provider=request.provider,
        provider_trace_id=provider_trace_id,
        result=result,
        code=code,
        error_type=error_type,
    )


def _classified_result(
    request: ObservabilityVerificationRequest,
    exc: Exception,
    *,
    provider_trace_id: str | None = None,
) -> ObservabilityVerificationResult:
    result, code, error_type = _classify_exception(request.provider, exc)
    return _result(
        request,
        provider_trace_id=provider_trace_id,
        result=result,
        code=code,
        error_type=error_type,
    )


def _classify_exception(
    provider: ObservabilityProvider,
    exc: Exception,
) -> tuple[VerificationOutcome, str, str]:
    if isinstance(exc, _VerificationTimeout):
        return "retryable_failure", "hosted_query_timeout", "timeout"

    if provider == "langsmith":
        if isinstance(exc, LangSmithNotFoundError):
            return "not_visible", "hosted_trace_not_visible", "not_found"
        if isinstance(
            exc,
            (
                LangSmithRateLimitError,
                LangSmithAPIError,
                LangSmithConnectionError,
                LangSmithRequestTimeout,
            ),
        ):
            return "retryable_failure", "hosted_query_retryable", _error_type(exc)
        if isinstance(exc, LangSmithAuthError):
            return (
                "terminal_failure",
                "hosted_query_authentication_error",
                "authentication",
            )
        if isinstance(exc, LangSmithUserError):
            return "terminal_failure", "hosted_query_sdk_error", _error_type(exc)

    if provider == "langfuse":
        if isinstance(exc, NotFoundError):
            return "not_visible", "hosted_trace_not_visible", "not_found"
        if isinstance(exc, (UnauthorizedError, AccessDeniedError)):
            return (
                "terminal_failure",
                "hosted_query_authentication_error",
                "authentication",
            )
        if isinstance(exc, LangfuseRequestError):
            return (
                "terminal_failure",
                "hosted_query_invalid_request",
                "invalid_request",
            )

    status_result = _classify_status_code(_status_code(exc))
    if status_result is not None:
        return status_result

    if isinstance(
        exc,
        (
            TimeoutError,
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.ProtocolError,
        ),
    ):
        return "retryable_failure", "hosted_query_transport_error", _error_type(exc)

    if isinstance(exc, (ValueError, TypeError)):
        return "terminal_failure", "hosted_query_invalid_request", _error_type(exc)

    if provider == "langfuse" and isinstance(exc, LangfuseApiError):
        return "terminal_failure", "hosted_query_sdk_error", _error_type(exc)

    return "terminal_failure", "hosted_query_unexpected_error", _error_type(exc)


def _classify_status_code(
    status_code: int | None,
) -> tuple[VerificationOutcome, str, str] | None:
    if status_code is None:
        return None
    if status_code == 404:
        return "not_visible", "hosted_trace_not_visible", "not_found"
    if status_code in (408, 409, 429) or status_code >= 500:
        error_type = "rate_limit" if status_code == 429 else "server"
        if status_code == 408:
            error_type = "timeout"
        return "retryable_failure", "hosted_query_retryable", error_type
    if status_code in (401, 403):
        return (
            "terminal_failure",
            "hosted_query_authentication_error",
            "authentication",
        )
    if 400 <= status_code < 500:
        return "terminal_failure", "hosted_query_invalid_request", "invalid_request"
    return "terminal_failure", "hosted_query_http_error", "http_error"


def _status_code(exc: Exception) -> int | None:
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        status_code = getattr(current, "status_code", None)
        if isinstance(status_code, int):
            return status_code
        response = getattr(current, "response", None)
        response_status = getattr(response, "status_code", None)
        if isinstance(response_status, int):
            return response_status
        current = current.__cause__ or current.__context__
    return None


def _langsmith_identity_filter(
    request: ObservabilityVerificationRequest,
) -> str:
    value_literal = _langsmith_filter_literal(request.product_run_id)
    return (
        f'and(eq(metadata_key, "product_run_id"), eq(metadata_value, {value_literal}))'
    )


def _langsmith_filter_literal(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )
    return f'"{escaped}"'


def _run_matches_identity(
    run: object,
    request: ObservabilityVerificationRequest,
) -> bool:
    metadata = _run_metadata(run)
    return (
        isinstance(metadata.get("product_run_id"), str)
        and metadata["product_run_id"] == request.product_run_id
        and isinstance(metadata.get("correlation_id"), str)
        and metadata["correlation_id"] == request.correlation_id
    )


def _run_metadata(run: object) -> Mapping[str, object]:
    if isinstance(run, Mapping):
        metadata = run.get("metadata")
        if isinstance(metadata, Mapping):
            return metadata
        extra = run.get("extra")
        if isinstance(extra, Mapping) and isinstance(extra.get("metadata"), Mapping):
            return cast(Mapping[str, object], extra["metadata"])
        return {}

    metadata = getattr(run, "metadata", None)
    if isinstance(metadata, Mapping):
        return metadata
    extra = getattr(run, "extra", None)
    if isinstance(extra, Mapping) and isinstance(extra.get("metadata"), Mapping):
        return cast(Mapping[str, object], extra["metadata"])
    return {}


def _run_id(run: object) -> str | None:
    value: object
    if isinstance(run, Mapping):
        value = run.get("id")
    else:
        value = getattr(run, "id", None)
    return str(value) if value is not None else None


def _error_type(exc: Exception) -> str:
    return type(exc).__name__


__all__ = [
    "HostedTraceAdapter",
    "LangSmithTraceAdapter",
    "LangfuseTraceAdapter",
    "ObservabilityProvider",
    "ObservabilityVerificationRequest",
    "ObservabilityVerificationResult",
    "ObservabilityVerifier",
    "OfficialLangSmithAdapter",
    "OfficialLangfuseAdapter",
    "VerificationOutcome",
    "create_official_verifier",
]
