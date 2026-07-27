from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from crypto_alert_v2.evaluation.experiment import (
    CaseEvaluation,
    METRIC_NAMES,
    OfflineExperimentResult,
)
from crypto_alert_v2.evaluation.frozen_replay import FrozenReplayPacket, rule_judge


class CandidateStatus(StrEnum):
    DRAFT = "draft"
    EVALUATED = "evaluated"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SHADOW = "shadow"
    ACTIVE = "active"
    ROLLED_BACK = "rolled_back"


_TRANSITIONS = {
    CandidateStatus.DRAFT: frozenset({CandidateStatus.EVALUATED}),
    CandidateStatus.EVALUATED: frozenset({CandidateStatus.PENDING_REVIEW}),
    CandidateStatus.PENDING_REVIEW: frozenset(
        {CandidateStatus.APPROVED, CandidateStatus.REJECTED}
    ),
    CandidateStatus.APPROVED: frozenset({CandidateStatus.SHADOW}),
    CandidateStatus.SHADOW: frozenset({CandidateStatus.ACTIVE}),
    CandidateStatus.ACTIVE: frozenset({CandidateStatus.ROLLED_BACK}),
    CandidateStatus.REJECTED: frozenset(),
    CandidateStatus.ROLLED_BACK: frozenset(),
}


@dataclass(frozen=True, slots=True)
class RuleCandidate:
    name: str
    base_version: str
    candidate_version: str
    rollback_target_version: str
    rationale: str
    diff: Mapping[str, Any]
    version_hash: str

    @classmethod
    def create(
        cls,
        *,
        name: str,
        base_version: str,
        candidate_version: str,
        rollback_target_version: str,
        rationale: str,
        diff: Mapping[str, Any],
    ) -> "RuleCandidate":
        payload = {
            "name": name,
            "base_version": base_version,
            "candidate_version": candidate_version,
            "rollback_target_version": rollback_target_version,
            "rationale": rationale,
            "diff": dict(diff),
        }
        return cls(**payload, version_hash=_canonical_hash(payload))


def transition_candidate(
    current: CandidateStatus,
    target: CandidateStatus,
) -> CandidateStatus:
    if target not in _TRANSITIONS[current]:
        raise ValueError(f"candidate transition {current.value}->{target.value} is forbidden")
    return target


def run_frozen_rule_experiment(
    cases: Sequence[tuple[str, FrozenReplayPacket]],
    *,
    candidate: RuleCandidate,
    prompt_version: str,
    git_revision: str,
) -> OfflineExperimentResult:
    if not cases:
        raise ValueError("a frozen rule experiment requires at least one case")
    thresholds = _candidate_thresholds(candidate.diff)
    case_results: list[CaseEvaluation] = []
    seen: set[str] = set()
    for case_name, packet in sorted(cases, key=lambda item: item[0]):
        if case_name in seen:
            raise ValueError(f"duplicate evaluation case: {case_name}")
        seen.add(case_name)
        judged = rule_judge(packet).model_dump()
        scores = {metric: float(judged[metric]) for metric in METRIC_NAMES}
        if any(scores[metric] < thresholds[metric] for metric in METRIC_NAMES):
            scores["product_output"] = 0.0
        case_results.append(CaseEvaluation(case_name=case_name, scores=scores))
    metrics = {
        metric: sum(item.scores[metric] for item in case_results) / len(case_results)
        for metric in METRIC_NAMES
    }
    return OfflineExperimentResult(
        case_results=tuple(case_results),
        metrics=metrics,
        prompt_version=prompt_version,
        git_revision=git_revision,
    )


def _candidate_thresholds(diff: Mapping[str, Any]) -> dict[str, float]:
    raw = diff.get("minimum_scores", {})
    if not isinstance(raw, Mapping) or set(raw) - set(METRIC_NAMES):
        raise ValueError("candidate minimum_scores contains unsupported metrics")
    thresholds = {metric: float(raw.get(metric, 1.0)) for metric in METRIC_NAMES}
    if any(value < 0 or value > 1 for value in thresholds.values()):
        raise ValueError("candidate minimum_scores must be between zero and one")
    return thresholds


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    return sha256(encoded).hexdigest()


__all__ = [
    "CandidateStatus",
    "RuleCandidate",
    "run_frozen_rule_experiment",
    "transition_candidate",
]
