import pytest

from crypto_alert_v2.providers.errors import ProviderUnavailable
from crypto_alert_v2.providers.errors import ResearchUnavailable
from crypto_alert_v2.providers.retry_policy import RetryPolicy, SearchRetryPolicy


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _unavailable(*, retryable: bool, endpoint: str = "ticker") -> ProviderUnavailable:
    return ProviderUnavailable(
        "OKX unavailable",
        provider="okx",
        endpoint=endpoint,
        retryable=retryable,
        correlation_id="corr-retry",
    )


def test_retry_policy_caps_retryable_failures_at_three_attempts() -> None:
    attempts: list[float] = []
    clock = FakeClock()
    policy = RetryPolicy(monotonic=clock.monotonic, sleep=clock.sleep)

    def operation(remaining_seconds: float) -> None:
        attempts.append(remaining_seconds)
        raise _unavailable(retryable=True)

    with pytest.raises(ProviderUnavailable) as raised:
        policy.execute(operation)

    assert len(attempts) == 3
    assert all(0 < remaining <= 10 for remaining in attempts)
    assert raised.value.provider == "okx"
    assert raised.value.endpoint == "ticker"
    assert raised.value.retryable is True
    assert raised.value.correlation_id == "corr-retry"


def test_retry_policy_does_not_retry_non_retryable_failure() -> None:
    attempts = 0
    policy = RetryPolicy(sleep=lambda _: None)

    def operation(_: float) -> None:
        nonlocal attempts
        attempts += 1
        raise _unavailable(retryable=False)

    with pytest.raises(ProviderUnavailable):
        policy.execute(operation)

    assert attempts == 1


def test_retry_policy_never_starts_an_attempt_after_ten_second_budget() -> None:
    attempts = 0
    clock = FakeClock()
    policy = RetryPolicy(monotonic=clock.monotonic, sleep=clock.sleep)

    def operation(_: float) -> None:
        nonlocal attempts
        attempts += 1
        clock.now += 4.5
        raise _unavailable(retryable=True, endpoint="mark")

    with pytest.raises(ProviderUnavailable) as raised:
        policy.execute(operation)

    assert attempts == 2
    assert clock.now <= 10
    assert raised.value.endpoint == "mark"
    assert raised.value.correlation_id == "corr-retry"


def test_retry_policy_returns_only_a_real_operation_success() -> None:
    calls = 0

    def operation(_: float) -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise _unavailable(retryable=True)
        return "typed-result"

    policy = RetryPolicy(sleep=lambda _: None)

    assert policy.execute(operation) == "typed-result"
    assert calls == 3


@pytest.mark.parametrize(
    "over_budget",
    [
        {"max_attempts": 4},
        {"total_budget_seconds": 10.01},
    ],
)
def test_retry_policy_configuration_cannot_exceed_provider_budget(
    over_budget: dict[str, float | int],
) -> None:
    with pytest.raises(ValueError, match="at most 3 attempts and 10 seconds"):
        RetryPolicy(**over_budget)  # type: ignore[arg-type]


def _research_unavailable(
    *, retryable: bool = True, retry_after_seconds: float | None = None
) -> ResearchUnavailable:
    return ResearchUnavailable(
        "search unavailable",
        provider="tavily",
        retryable=retryable,
        retry_after_seconds=retry_after_seconds,
        error_type="TimeoutError",
    )


def test_search_retry_owner_caps_attempts_and_total_budget_at_three_and_thirty() -> None:
    clock = FakeClock()
    records = []
    calls: list[tuple[int, float]] = []
    policy = SearchRetryPolicy(
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        record_attempt=records.append,
    )

    def operation(remaining_seconds: float, attempt: int) -> None:
        calls.append((attempt, remaining_seconds))
        clock.now += 9
        raise _research_unavailable()

    with pytest.raises(ResearchUnavailable) as raised:
        policy.execute(operation, provider="tavily")

    assert [attempt for attempt, _ in calls] == [1, 2, 3]
    assert all(0 < remaining <= 30 for _, remaining in calls)
    assert clock.now <= 30
    assert raised.value.attempt == 3
    assert [record.attempt for record in records] == [1, 2, 3]


def test_search_retry_owner_honors_retry_after_inside_the_same_budget() -> None:
    clock = FakeClock()
    attempts = 0
    policy = SearchRetryPolicy(monotonic=clock.monotonic, sleep=clock.sleep)

    def operation(_: float, __: int) -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _research_unavailable(retry_after_seconds=7)
        return "verified-evidence"

    assert policy.execute(operation, provider="tavily") == "verified-evidence"
    assert attempts == 2
    assert clock.now == 7


@pytest.mark.parametrize(
    "over_budget",
    [
        {"max_attempts": 4},
        {"total_budget_seconds": 30.01},
    ],
)
def test_search_retry_configuration_cannot_exceed_search_budget(
    over_budget: dict[str, float | int],
) -> None:
    with pytest.raises(ValueError, match="at most 3 attempts and 30 seconds"):
        SearchRetryPolicy(**over_budget)  # type: ignore[arg-type]
