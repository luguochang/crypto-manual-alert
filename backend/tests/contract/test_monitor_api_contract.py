from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from crypto_alert_v2.api.schemas import (
    MonitorCreateSubmission,
    MonitorMutationSubmission,
    MonitorQuietHours,
)
from crypto_alert_v2.monitors.conditions import (
    MONITOR_CONDITION_EVALUATOR_UNAVAILABLE,
    MonitorConditionEvaluatorUnavailableError,
    require_monitor_condition_evaluator,
)


def _submission(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "BTC macro review",
        "artifact_id": uuid4(),
        "artifact_version_id": uuid4(),
        "run_task_type": "market_analysis",
        "condition": {
            "kind": "price",
            "operator": "gte",
            "threshold": 70_000,
        },
        "schedule": "0 * * * *",
        "timezone": "Asia/Shanghai",
        "expires_at": datetime.now(UTC) + timedelta(days=30),
        "quiet_hours": {"start": "23:00", "end": "07:00"},
        "destination_ids": [],
    }
    payload.update(overrides)
    return payload


def test_monitor_submission_accepts_typed_product_configuration() -> None:
    submission = MonitorCreateSubmission.model_validate(_submission())

    assert submission.condition.kind == "price"
    assert submission.schedule == "0 * * * *"
    assert submission.timezone == "Asia/Shanghai"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schedule", "1 2 3 4 5", "unsupported monitor schedule"),
        ("timezone", "Mars/Olympus", "valid IANA zone"),
        ("expires_at", datetime(2026, 8, 1), "timezone-aware"),
    ],
)
def test_monitor_submission_rejects_unsupported_runtime_configuration(
    field: str,
    value: object,
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        MonitorCreateSubmission.model_validate(_submission(**{field: value}))


def test_monitor_condition_is_a_strict_discriminated_union() -> None:
    with pytest.raises(ValidationError):
        MonitorCreateSubmission.model_validate(
            _submission(
                condition={
                    "kind": "price",
                    "operator": "gte",
                    "threshold": 70_000,
                    "query": "must never enter cron input",
                }
            )
        )


@pytest.mark.parametrize("condition_kind", ("price", "thesis", "provider_health"))
def test_monitor_condition_requires_an_available_evaluator(
    condition_kind: str,
) -> None:
    condition = {
        "price": {"kind": "price", "operator": "gte", "threshold": 70_000},
        "thesis": {"kind": "thesis", "statement": "BTC remains resilient"},
        "provider_health": {
            "kind": "provider_health",
            "provider": "okx",
            "consecutive_failures": 2,
        },
    }[condition_kind]
    submission = MonitorCreateSubmission.model_validate(_submission(condition=condition))

    with pytest.raises(MonitorConditionEvaluatorUnavailableError) as raised:
        require_monitor_condition_evaluator(submission.condition.kind)

    assert raised.value.code == MONITOR_CONDITION_EVALUATOR_UNAVAILABLE
    assert raised.value.condition_kind == condition_kind


def test_scheduled_review_has_the_only_available_monitor_evaluator() -> None:
    submission = MonitorCreateSubmission.model_validate(
        _submission(condition={"kind": "scheduled_review"})
    )

    require_monitor_condition_evaluator(submission.condition.kind)


def test_monitor_submission_rejects_unknown_top_level_fields() -> None:
    with pytest.raises(ValidationError):
        MonitorCreateSubmission.model_validate(
            _submission(artifact={"content": "must stay server-owned"})
        )


def test_quiet_hours_require_a_real_window() -> None:
    with pytest.raises(ValidationError, match="must differ"):
        MonitorQuietHours(start="09:00", end="09:00")


def test_monitor_mutation_requires_an_optimistic_version() -> None:
    assert MonitorMutationSubmission(expected_version=3).expected_version == 3
    with pytest.raises(ValidationError):
        MonitorMutationSubmission(expected_version=0)
