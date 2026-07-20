import asyncio
from collections.abc import Awaitable
from collections.abc import Callable
from dataclasses import dataclass
import logging
import time
from typing import Literal, TypeVar

from crypto_alert_v2.providers.errors import ProviderUnavailable, ResearchUnavailable

T = TypeVar("T")
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    total_budget_seconds: float = 10.0
    backoff_seconds: tuple[float, ...] = (1.0, 2.0)
    monotonic: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep

    def __post_init__(self) -> None:
        if (
            self.max_attempts < 1
            or self.max_attempts > 3
            or self.total_budget_seconds <= 0
            or self.total_budget_seconds > 10
        ):
            raise ValueError(
                "provider retry budget requires at least 1 attempt, a positive budget, "
                "and allows at most 3 attempts and 10 seconds"
            )
        if not self.backoff_seconds or any(delay < 0 for delay in self.backoff_seconds):
            raise ValueError("provider retry backoff must contain non-negative delays")

    def execute(self, operation: Callable[[float], T]) -> T:
        started_at = self.monotonic()
        deadline = started_at + self.total_budget_seconds
        last_error: ProviderUnavailable | None = None

        for attempt_index in range(self.max_attempts):
            remaining = deadline - self.monotonic()
            if remaining <= 0:
                break

            try:
                return operation(remaining)
            except ProviderUnavailable as exc:
                last_error = exc
                exc.attempt = attempt_index + 1
                if not exc.retryable:
                    exc.retry_exhausted = False
                    raise
                if attempt_index + 1 >= self.max_attempts:
                    exc.retry_exhausted = True
                    raise

            delay = self.backoff_seconds[
                min(attempt_index, len(self.backoff_seconds) - 1)
            ]
            remaining = deadline - self.monotonic()
            if delay >= remaining:
                break
            self.sleep(delay)

        if last_error is not None:
            last_error.retry_exhausted = last_error.retryable
            raise last_error
        raise RuntimeError("retry policy exhausted before its first attempt")


@dataclass(frozen=True, slots=True)
class SearchAttempt:
    provider: str
    attempt: int
    correlation_id: str | None
    remaining_budget_seconds: float
    elapsed_seconds: float
    outcome: Literal["succeeded", "retryable_failure", "terminal_failure"]
    error_type: str | None = None


def _record_search_attempt(attempt: SearchAttempt) -> None:
    logger.info(
        "search_provider_attempt",
        extra={
            "provider": attempt.provider,
            "attempt": attempt.attempt,
            "correlation_id": attempt.correlation_id,
            "remaining_budget_seconds": attempt.remaining_budget_seconds,
            "elapsed_seconds": attempt.elapsed_seconds,
            "outcome": attempt.outcome,
            "error_type": attempt.error_type,
        },
    )


@dataclass(frozen=True, slots=True)
class SearchRetryPolicy:
    """The sole retry owner for built-in and Tavily search calls."""

    max_attempts: int = 3
    total_budget_seconds: float = 30.0
    backoff_seconds: tuple[float, ...] = (1.0, 2.0)
    monotonic: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    async_sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    record_attempt: Callable[[SearchAttempt], None] = _record_search_attempt

    def __post_init__(self) -> None:
        if (
            self.max_attempts < 1
            or self.max_attempts > 3
            or self.total_budget_seconds <= 0
            or self.total_budget_seconds > 30
        ):
            raise ValueError(
                "search retry budget allows at most 3 attempts and 30 seconds"
            )
        if not self.backoff_seconds or any(delay < 0 for delay in self.backoff_seconds):
            raise ValueError("search retry backoff must contain non-negative delays")

    def execute(
        self,
        operation: Callable[[float, int], T],
        *,
        provider: str,
        correlation_id: str | None = None,
    ) -> T:
        started_at = self.monotonic()
        deadline = started_at + self.total_budget_seconds
        last_error: ResearchUnavailable | None = None

        for attempt in range(1, self.max_attempts + 1):
            remaining_before = deadline - self.monotonic()
            if remaining_before <= 0:
                break
            attempt_started = self.monotonic()
            try:
                result = operation(
                    self._attempt_timeout_seconds(remaining_before, attempt),
                    attempt,
                )
            except ResearchUnavailable as exc:
                last_error = exc
                exc.attempt = attempt
                remaining_after = deadline - self.monotonic()
                backoff = self.backoff_seconds[
                    min(attempt - 1, len(self.backoff_seconds) - 1)
                ]
                retry_after = max(0.0, exc.retry_after_seconds or 0.0)
                delay = max(backoff, retry_after)
                can_retry = (
                    exc.retryable
                    and attempt < self.max_attempts
                    and remaining_after > 0
                    and delay < remaining_after
                )
                self.record_attempt(
                    SearchAttempt(
                        provider=provider,
                        attempt=attempt,
                        correlation_id=correlation_id,
                        remaining_budget_seconds=max(0.0, remaining_before),
                        elapsed_seconds=max(0.0, self.monotonic() - attempt_started),
                        outcome=(
                            "retryable_failure" if can_retry else "terminal_failure"
                        ),
                        error_type=exc.error_type or type(exc).__name__,
                    )
                )
                if not can_retry:
                    raise
                self.sleep(delay)
                continue

            self.record_attempt(
                SearchAttempt(
                    provider=provider,
                    attempt=attempt,
                    correlation_id=correlation_id,
                    remaining_budget_seconds=max(0.0, remaining_before),
                    elapsed_seconds=max(0.0, self.monotonic() - attempt_started),
                    outcome="succeeded",
                )
            )
            return result

        if last_error is not None:
            raise last_error
        raise ResearchUnavailable(
            "search retry budget exhausted before its first attempt",
            provider=provider,
            retryable=False,
            error_type="RetryBudgetExhausted",
        )

    def _attempt_timeout_seconds(
        self,
        remaining_budget_seconds: float,
        attempt: int,
    ) -> float:
        attempts_remaining = self.max_attempts - attempt + 1
        future_backoff = sum(
            self.backoff_seconds[min(index, len(self.backoff_seconds) - 1)]
            for index in range(attempt - 1, self.max_attempts - 1)
        )
        reserved_backoff = min(
            future_backoff,
            remaining_budget_seconds / 2,
        )
        # Built-in model-backed search can spend its first turn negotiating the
        # provider tool shape. Give that turn half of the usable budget while a
        # shared deadline still bounds all retries and backoff to 30 seconds.
        timeout_slices = 2 if attempts_remaining == 3 else attempts_remaining
        return (remaining_budget_seconds - reserved_backoff) / timeout_slices

    async def execute_async(
        self,
        operation: Callable[[float, int], Awaitable[T]],
        *,
        provider: str,
        correlation_id: str | None = None,
    ) -> T:
        deadline = self.monotonic() + self.total_budget_seconds
        last_error: ResearchUnavailable | None = None

        for attempt in range(1, self.max_attempts + 1):
            remaining_before = deadline - self.monotonic()
            if remaining_before <= 0:
                break
            attempt_started = self.monotonic()
            try:
                result = await operation(
                    self._attempt_timeout_seconds(remaining_before, attempt),
                    attempt,
                )
            except ResearchUnavailable as exc:
                last_error = exc
                exc.attempt = attempt
                remaining_after = deadline - self.monotonic()
                backoff = self.backoff_seconds[
                    min(attempt - 1, len(self.backoff_seconds) - 1)
                ]
                retry_after = max(0.0, exc.retry_after_seconds or 0.0)
                delay = max(backoff, retry_after)
                can_retry = (
                    exc.retryable
                    and attempt < self.max_attempts
                    and remaining_after > 0
                    and delay < remaining_after
                )
                self.record_attempt(
                    SearchAttempt(
                        provider=provider,
                        attempt=attempt,
                        correlation_id=correlation_id,
                        remaining_budget_seconds=max(0.0, remaining_before),
                        elapsed_seconds=max(
                            0.0,
                            self.monotonic() - attempt_started,
                        ),
                        outcome=(
                            "retryable_failure" if can_retry else "terminal_failure"
                        ),
                        error_type=exc.error_type or type(exc).__name__,
                    )
                )
                if not can_retry:
                    raise
                await self.async_sleep(delay)
                continue

            self.record_attempt(
                SearchAttempt(
                    provider=provider,
                    attempt=attempt,
                    correlation_id=correlation_id,
                    remaining_budget_seconds=max(0.0, remaining_before),
                    elapsed_seconds=max(0.0, self.monotonic() - attempt_started),
                    outcome="succeeded",
                )
            )
            return result

        if last_error is not None:
            raise last_error
        raise ResearchUnavailable(
            "search retry budget exhausted before its first attempt",
            provider=provider,
            retryable=False,
            error_type="RetryBudgetExhausted",
        )
