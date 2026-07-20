from typing import Final


MONITOR_CONDITION_EVALUATOR_UNAVAILABLE: Final = (
    "monitor_condition_evaluator_unavailable"
)
SUPPORTED_MONITOR_CONDITION_EVALUATORS: Final = frozenset({"scheduled_review"})


class MonitorConditionEvaluatorUnavailableError(ValueError):
    code = MONITOR_CONDITION_EVALUATOR_UNAVAILABLE

    def __init__(self, condition_kind: object) -> None:
        self.condition_kind = (
            condition_kind if isinstance(condition_kind, str) else str(condition_kind)
        )
        super().__init__(
            f"No evaluator is available for monitor condition {self.condition_kind!r}."
        )


def require_monitor_condition_evaluator(condition_kind: object) -> None:
    if not isinstance(condition_kind, str) or (
        condition_kind not in SUPPORTED_MONITOR_CONDITION_EVALUATORS
    ):
        raise MonitorConditionEvaluatorUnavailableError(condition_kind)


__all__ = [
    "MONITOR_CONDITION_EVALUATOR_UNAVAILABLE",
    "SUPPORTED_MONITOR_CONDITION_EVALUATORS",
    "MonitorConditionEvaluatorUnavailableError",
    "require_monitor_condition_evaluator",
]
