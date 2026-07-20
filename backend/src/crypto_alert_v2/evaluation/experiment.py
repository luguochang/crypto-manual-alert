from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from crypto_alert_v2.evaluation.dataset import EvaluationCase


METRIC_NAMES = ("structure", "evidence", "risk", "product_output")


@dataclass(frozen=True)
class CaseEvaluation:
    case_name: str
    scores: dict[str, float]

    def __post_init__(self) -> None:
        if set(self.scores) != set(METRIC_NAMES):
            raise ValueError("each case must report every release metric")
        if any(score < 0.0 or score > 1.0 for score in self.scores.values()):
            raise ValueError("release metric scores must be between zero and one")


@dataclass(frozen=True)
class OfflineExperimentResult:
    case_results: tuple[CaseEvaluation, ...]
    metrics: dict[str, float]
    prompt_version: str
    git_revision: str


def run_repeatable_offline_experiment(
    cases: Sequence[EvaluationCase],
    *,
    target: Callable[[dict[str, Any]], Mapping[str, Any]],
    evaluator: Callable[[EvaluationCase, Mapping[str, Any]], Mapping[str, float]],
    prompt_version: str,
    git_revision: str,
) -> OfflineExperimentResult:
    seen: set[str] = set()
    case_results: list[CaseEvaluation] = []
    for case in sorted(cases, key=lambda item: item.name):
        if case.name in seen:
            raise ValueError(f"duplicate evaluation case: {case.name}")
        seen.add(case.name)
        output = target(case.inputs)
        scores = {
            metric: float(score) for metric, score in evaluator(case, output).items()
        }
        case_results.append(CaseEvaluation(case_name=case.name, scores=scores))

    if not case_results:
        raise ValueError("an experiment requires at least one case")
    metrics = {
        metric: sum(result.scores[metric] for result in case_results)
        / len(case_results)
        for metric in METRIC_NAMES
    }
    return OfflineExperimentResult(
        case_results=tuple(case_results),
        metrics=metrics,
        prompt_version=prompt_version,
        git_revision=git_revision,
    )


def run_official_langsmith_experiment(
    target: Any,
    *,
    dataset_name: str,
    evaluators: Sequence[Any],
    client: Any,
    experiment_prefix: str,
    prompt_version: str,
    git_revision: str,
) -> Any:
    """Run the platform gate through LangSmith's official evaluate API."""
    return client.evaluate(
        target,
        data=dataset_name,
        evaluators=evaluators,
        experiment_prefix=experiment_prefix,
        metadata={
            "prompt_version": prompt_version,
            "git_revision": git_revision,
            "release_proof": True,
        },
        blocking=True,
        upload_results=True,
    )
