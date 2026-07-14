from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)


TRANSIENT_MODEL_ERRORS = (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)


class ProviderUnavailable(RuntimeError):
    """A provider call or response could not produce validated typed data."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        endpoint: str,
        retryable: bool,
        correlation_id: str,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.endpoint = endpoint
        self.retryable = retryable
        self.correlation_id = correlation_id


class ResearchUnavailable(RuntimeError):
    """A search attempt failed without producing verified provider evidence."""

    code = "research_unavailable"

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        retryable: bool = False,
        retry_after_seconds: float | None = None,
        error_type: str | None = None,
        attempt: int | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        self.error_type = error_type
        self.attempt = attempt
