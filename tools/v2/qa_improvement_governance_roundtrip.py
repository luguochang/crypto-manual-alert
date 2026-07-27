"""Run the Product controlled-improvement Dataset/Candidate/Experiment round-trip."""

from __future__ import annotations

import asyncio
import json
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from crypto_alert_v2.api.schemas import (
    ImprovementCandidateSubmission,
    ImprovementDatasetSubmission,
    ImprovementExperimentSubmission,
    ImprovementReviewDecisionSubmission,
    ImprovementReleaseSubmission,
    ImprovementShadowSubmission,
)
from crypto_alert_v2.api.service import ProductAnalysisService
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.config import get_settings
from crypto_alert_v2.evaluation.review_runtime import CandidateReviewRuntime


def _actor() -> ActorContext:
    return ActorContext(
        tenant_id="dev-tenant",
        workspace_id="dev-workspace",
        user_id="dev-user",
        identity_issuer="crypto-alert-v2-compose",
        context_id=UUID("99999999-9999-4999-8999-999999999999"),
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )


async def main() -> None:
    settings = get_settings()
    if settings.product_database_url is None:
        raise RuntimeError("PRODUCT_DATABASE_URL is not configured")
    engine = create_async_engine(settings.product_database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = ProductAnalysisService(
        session_factory=factory,
        candidate_review_runtime=CandidateReviewRuntime.from_settings(settings),
    )
    actor = _actor()
    postmortems = await service.list_postmortems(actor, limit=100)
    replay_ids = [
        item["frozen_replay"]["id"]
        for item in postmortems["items"]
        if item.get("frozen_replay") is not None
    ]
    if not replay_ids:
        raise RuntimeError("no frozen replay is available for a governed experiment")
    dataset = await service.create_improvement_dataset(
        actor,
        ImprovementDatasetSubmission(
            name="qa-frozen-replay-dataset",
            replay_ids=replay_ids[:2],
        ),
        "qa-governance-dataset-v1",
    )
    if dataset is None:
        raise RuntimeError("dataset creation unexpectedly returned no record")
    candidate = await service.create_improvement_candidate(
        actor,
        ImprovementCandidateSubmission(
            name="qa-rule-candidate",
            base_version="rule-v1",
            candidate_version="rule-v2",
            rollback_target_version="rule-v1",
            rationale="Require deterministic frozen replay gates before review.",
            diff={
                "minimum_scores": {
                    "structure": 1.0,
                    "evidence": 1.0,
                    "risk": 1.0,
                    "product_output": 1.0,
                }
            },
        ),
        "qa-governance-candidate-v1",
    )
    if candidate is None:
        raise RuntimeError("candidate creation unexpectedly returned no record")
    evaluated = await service.run_improvement_experiment(
        actor,
        candidate["id"],
        ImprovementExperimentSubmission(
            dataset_id=dataset["id"],
            prompt_version="frozen-rule-v1",
            git_revision="qa-local-revision",
        ),
        "qa-governance-experiment-v1",
    )
    if evaluated is None or evaluated["latest_experiment"] is None:
        raise RuntimeError("experiment did not persist a result")
    review_pending = await service.request_improvement_review(
        actor,
        candidate["id"],
        "qa-governance-review-v1",
    )
    if review_pending is None or review_pending["latest_review"] is None:
        raise RuntimeError("candidate review did not persist an official interrupt")
    reviewed = await service.decide_improvement_review(
        actor,
        candidate["id"],
        ImprovementReviewDecisionSubmission(
            action="approve",
            comment="QA approval for shadow-only validation.",
        ),
    )
    if reviewed is None or reviewed["latest_review"] is None:
        raise RuntimeError("candidate review resume did not persist")
    shadowed = await service.run_improvement_shadow(
        actor,
        candidate["id"],
        ImprovementShadowSubmission(minimum_runs=1),
        "qa-governance-shadow-v1",
    )
    if shadowed is None or shadowed["latest_shadow"] is None:
        raise RuntimeError("candidate shadow did not persist")
    promoted = await service.promote_improvement_candidate(
        actor,
        candidate["id"],
        ImprovementReleaseSubmission(
            reason="QA promotion after approved frozen shadow."
        ),
    )
    if promoted is None:
        raise RuntimeError("candidate promotion did not persist")
    rolled_back = await service.rollback_improvement_candidate(
        actor,
        candidate["id"],
        ImprovementReleaseSubmission(
            reason="QA rollback rehearsal to the declared target."
        ),
    )
    if rolled_back is None:
        raise RuntimeError("candidate rollback did not persist")
    datasets = await service.list_improvement_datasets(actor, limit=100)
    candidates = await service.list_improvement_candidates(actor, limit=100)
    experiment = evaluated["latest_experiment"]
    review = rolled_back["latest_review"]
    shadow = rolled_back["latest_shadow"]
    print(
        json.dumps(
            {
                "dataset_id": str(dataset["id"]),
                "dataset_status": dataset["status"],
                "replay_count": dataset["replay_count"],
                "dataset_listed": any(
                    item["id"] == dataset["id"] for item in datasets["items"]
                ),
                "candidate_id": str(candidate["id"]),
                "candidate_status": rolled_back["status"],
                "candidate_listed": any(
                    item["id"] == candidate["id"] for item in candidates["items"]
                ),
                "experiment_status": experiment["status"],
                "release_gate_approved": experiment["gate_report"]["approved"],
                "release_gate_reasons": experiment["gate_report"]["reasons"],
                "metrics": experiment["metrics"],
                "source_hash_present": bool(experiment["source_hash"]),
                "review_status": review["status"],
                "shadow_status": shadow["status"] if shadow else None,
                "shadow_mode": (
                    shadow["comparison"]["mode"] if shadow is not None else None
                ),
                "release_actions": [
                    event["action"] for event in rolled_back["release_events"]
                ],
                "release_targets": [
                    event["to_version"] for event in rolled_back["release_events"]
                ],
                "official_assistant_id": review["official_assistant_id"],
                "official_thread_id_present": bool(review["official_thread_id"]),
                "official_run_id_present": bool(review["official_run_id"]),
                "official_interrupt_id_present": bool(
                    review["official_interrupt_id"]
                ),
                "frozen_replay_live_fetch": False,
                "frozen_replay_live_side_effects": False,
            },
            sort_keys=True,
        )
    )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
