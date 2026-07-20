from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from crypto_alert_v2.evaluation.dataset import MINIMUM_RELEASE_CASE_NAMES
from crypto_alert_v2.evaluation.experiment import (
    METRIC_NAMES,
    OfflineExperimentResult,
)


DEFAULT_THRESHOLDS: Mapping[str, float] = {
    "structure": 1.0,
    "evidence": 1.0,
    "risk": 1.0,
    "product_output": 1.0,
}


@dataclass(frozen=True)
class ReleaseGateReport:
    approved: bool
    reasons: tuple[str, ...]
    metrics: dict[str, float]
    thresholds: dict[str, float]
    prompt_version: str
    git_revision: str


@dataclass(frozen=True)
class PlatformCredentialGate:
    ready: bool
    missing: tuple[str, ...] = field(default_factory=tuple)

    def require(self) -> None:
        if not self.ready:
            raise RuntimeError(
                "real observability gate is unavailable: " + ", ".join(self.missing)
            )


def evaluate_release_gate(
    result: OfflineExperimentResult,
    *,
    thresholds: Mapping[str, float] = DEFAULT_THRESHOLDS,
) -> ReleaseGateReport:
    reasons: list[str] = []
    actual_cases = {case.case_name for case in result.case_results}
    missing_cases = set(MINIMUM_RELEASE_CASE_NAMES) - actual_cases
    extra_cases = actual_cases - set(MINIMUM_RELEASE_CASE_NAMES)
    if missing_cases:
        reasons.append("missing_cases:" + ",".join(sorted(missing_cases)))
    if extra_cases:
        reasons.append("unexpected_cases:" + ",".join(sorted(extra_cases)))
    if not result.prompt_version:
        reasons.append("missing_prompt_version")
    if not result.git_revision:
        reasons.append("missing_git_revision")
    if set(result.metrics) != set(METRIC_NAMES):
        reasons.append("incomplete_metrics")
    for metric in METRIC_NAMES:
        score = result.metrics.get(metric)
        threshold = thresholds.get(metric)
        if threshold is None:
            reasons.append(f"missing_threshold:{metric}")
        elif score is None or score < threshold:
            rendered = "missing" if score is None else f"{score:.6f}"
            reasons.append(
                f"metric_below_threshold:{metric}:{rendered}<{threshold:.6f}"
            )
    return ReleaseGateReport(
        approved=not reasons,
        reasons=tuple(reasons),
        metrics=dict(result.metrics),
        thresholds=dict(thresholds),
        prompt_version=result.prompt_version,
        git_revision=result.git_revision,
    )


def assess_real_platform_credentials(
    *,
    langsmith_api_key: str | None,
    langsmith_project: str | None,
    langfuse_public_key: str | None,
    langfuse_secret_key: str | None,
) -> PlatformCredentialGate:
    values = {
        "LANGSMITH_API_KEY": langsmith_api_key,
        "LANGSMITH_PROJECT": langsmith_project,
        "LANGFUSE_PUBLIC_KEY": langfuse_public_key,
        "LANGFUSE_SECRET_KEY": langfuse_secret_key,
    }
    missing = tuple(name for name, value in values.items() if not value)
    return PlatformCredentialGate(ready=not missing, missing=missing)
