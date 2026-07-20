from __future__ import annotations

from dataclasses import dataclass
from typing import Any


MINIMUM_RELEASE_CASE_NAMES = (
    "normal",
    "missing",
    "stale",
    "conflict",
    "model_error",
    "notification_error",
)


@dataclass(frozen=True)
class EvaluationCase:
    name: str
    inputs: dict[str, Any]
    expected: dict[str, Any]

    def as_langsmith_example(self) -> dict[str, Any]:
        return {
            "inputs": self.inputs,
            "outputs": self.expected,
            "metadata": {"case_name": self.name, "suite": "minimum-release"},
        }


def minimum_release_dataset() -> tuple[EvaluationCase, ...]:
    return (
        EvaluationCase(
            name="normal",
            inputs={"fixture": "normal"},
            expected={"terminal_status": "succeeded"},
        ),
        EvaluationCase(
            name="missing",
            inputs={"fixture": "missing"},
            expected={"terminal_status": "blocked", "evidence_sufficient": False},
        ),
        EvaluationCase(
            name="stale",
            inputs={"fixture": "stale"},
            expected={"terminal_status": "blocked", "evidence_sufficient": False},
        ),
        EvaluationCase(
            name="conflict",
            inputs={"fixture": "conflict"},
            expected={"terminal_status": "blocked", "risk_allowed": False},
        ),
        EvaluationCase(
            name="model_error",
            inputs={"fixture": "model_error"},
            expected={"terminal_status": "failed", "failure_code": "model_unavailable"},
        ),
        EvaluationCase(
            name="notification_error",
            inputs={"fixture": "notification_error"},
            expected={
                "terminal_status": "succeeded",
                "notification_status": "failed",
            },
        ),
    )


def upload_minimum_dataset(
    client: Any,
    *,
    dataset_name: str,
    description: str,
) -> Any:
    """Create the official LangSmith Dataset and upload its minimum examples."""
    dataset = client.create_dataset(dataset_name, description=description)
    client.create_examples(
        dataset_id=dataset.id,
        examples=[case.as_langsmith_example() for case in minimum_release_dataset()],
    )
    return dataset
