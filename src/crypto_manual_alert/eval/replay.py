from __future__ import annotations

import time
import uuid
from typing import Any

from crypto_manual_alert.decision.decision_input import worker_hard_block_contributions
from crypto_manual_alert.eval.decision_input_experiment import DecisionInputExperimentRunner
from crypto_manual_alert.decision.frozen_input import stable_hash

from .candidate_artifact_consistency import artifact_snapshot_consistency
from .complete_replay_refs import complete_replay_missing_refs, complete_replay_refs
from .context_artifact_consistency import context_artifact_consistency
from .counter_conflict_coverage import counter_conflict_coverage
from .schema import EvalCase, EvalReplayOutput
from .shadow_final_comparison import build_candidate_final_legacy_comparison
from .shadow_final_comparison import build_shadow_legacy_comparison
from .store import EvalStore
from .worker_manifest_consistency import (
    lead_synthesis_artifact,
    lead_synthesis_payload,
    worker_manifest_consistency,
)


class ReplayRunner:
    """Eval 侧回放器，只使用冻结输入和历史观测输出，不访问生产 runner。"""

    def __init__(self, store: EvalStore, *, decision_input_final_adapter: Any | None = None):
        self.store = store
        self.decision_input_final_adapter = decision_input_final_adapter

    def replay(self, case: EvalCase, *, mode: str = "frozen_observed") -> EvalReplayOutput:
        if mode not in {"frozen_observed", "judge_only", "candidate_decision"}:
            raise ValueError(f"unsupported replay mode: {mode}")
        started = time.perf_counter()
        stored_case = self._stored_case(case)
        if mode == "candidate_decision":
            output = self._candidate_decision_replay(stored_case, started)
            self.store.insert_replay_output(output)
            return output

        frozen = self.store.get_frozen_input(stored_case.frozen_input_hash)
        if frozen is None:
            output = self._failed(stored_case, "frozen_input_missing", started, mode=mode)
            self.store.insert_replay_output(output)
            return output

        observed = stored_case.input_summary.get("observed_output") if isinstance(stored_case.input_summary, dict) else {}
        parsed_plan = observed.get("parsed_plan") if isinstance(observed, dict) else {}
        verdict = observed.get("verdict") if isinstance(observed, dict) else {}
        output_payload = {
            "frozen_input_hash": frozen.frozen_input_hash,
            "parsed_plan": parsed_plan if isinstance(parsed_plan, dict) else {},
            "verdict": verdict if isinstance(verdict, dict) else {},
            "candidate_replay": _candidate_replay(
                stored_case.input_summary,
                candidate_artifacts=self._candidate_artifacts(
                    stored_case.case_id,
                ),
            ),
            "public_summary": frozen.public_summary,
        }
        final_action = str(output_payload["parsed_plan"].get("main_action") or "") or None
        allowed_value = output_payload["verdict"].get("allowed")
        allowed = allowed_value if isinstance(allowed_value, bool) else None
        output = EvalReplayOutput(
            replay_id=uuid.uuid4().hex,
            case_id=stored_case.case_id,
            source_trace_id=stored_case.source_trace_id,
            source_badcase_id=stored_case.source_badcase_id,
            frozen_input_hash=stored_case.frozen_input_hash,
            status="completed",
            mode=mode,
            final_action=final_action,
            allowed=allowed,
            output_hash=stable_hash(output_payload),
            reason_summary=_reason_summary(output_payload),
            duration_ms=_duration_ms(started),
            output_payload=output_payload,
            metadata={"source": f"eval.{mode}_replay"},
        )
        self.store.insert_replay_output(output)
        return output

    def _failed(self, case: EvalCase, message: str, started: float, *, mode: str = "frozen_observed") -> EvalReplayOutput:
        return EvalReplayOutput(
            replay_id=uuid.uuid4().hex,
            case_id=case.case_id,
            source_trace_id=case.source_trace_id,
            source_badcase_id=case.source_badcase_id,
            frozen_input_hash=case.frozen_input_hash,
            status="failed",
            mode=mode,
            error_message=message,
            duration_ms=_duration_ms(started),
            output_payload={},
            metadata={"source": "eval.replay", "failure_category": message},
        )

    def _candidate_decision_replay(self, case: EvalCase, started: float) -> EvalReplayOutput:
        candidate_artifacts = self._candidate_artifacts(case.case_id)
        candidate_replay = _candidate_replay(
            case.input_summary,
            candidate_artifacts=candidate_artifacts,
        )
        if candidate_replay.get("status") != "available":
            return self._failed(case, "candidate_replay_artifacts_missing", started, mode="candidate_decision")
        output_payload = {
            "candidate_replay": candidate_replay,
            "candidate_decision": {
                "status": "completed",
                "decision_effect": "none",
                "decision_input_ref": candidate_replay.get("decision_input_ref"),
                "decision_input_hash": candidate_replay.get("decision_input_hash"),
                "replayable_input_ref": candidate_replay.get("replayable_input_ref"),
                "replayable_input_hash": candidate_replay.get("replayable_input_hash"),
                "worker_artifact_count": candidate_replay.get("worker_artifact_count"),
                "worker_manifest_complete": candidate_replay.get("worker_manifest_complete"),
                "worker_manifest_missing_fields": list(
                    candidate_replay.get("worker_manifest_missing_fields") or []
                ),
                "worker_manifest_consistency": dict(
                    candidate_replay.get("worker_manifest_consistency") or {}
                ),
                "context_artifact_consistency": dict(
                    candidate_replay.get("context_artifact_consistency") or {}
                ),
                "artifact_snapshot_consistency": dict(
                    candidate_replay.get("artifact_snapshot_consistency") or {}
                ),
                "counter_conflict_coverage": dict(
                    candidate_replay.get("counter_conflict_coverage") or {}
                ),
                "complete_replay_refs": dict(candidate_replay.get("complete_replay_refs") or {}),
                "complete_replay_missing_refs": list(
                    candidate_replay.get("complete_replay_missing_refs") or []
                ),
                "span_tree_parent_complete": candidate_replay.get("span_tree_parent_complete"),
                "span_tree_missing_parent_count": candidate_replay.get("span_tree_missing_parent_count"),
                "worker_hard_blocks": list(candidate_replay.get("worker_hard_blocks") or []),
                "blocked_actions": list(candidate_replay.get("blocked_actions") or []),
                "missing_facts": list(candidate_replay.get("missing_facts") or []),
                "execution_fact_source_violations": list(
                    candidate_replay.get("execution_fact_source_violations") or []
                ),
                "switch_ready": candidate_replay.get("switch_ready"),
                "blocking_reasons": list(candidate_replay.get("blocking_reasons") or []),
            },
        }
        shadow_final = _run_decision_input_shadow_final(
            candidate_artifacts=candidate_artifacts,
            final_adapter=self.decision_input_final_adapter,
        )
        if shadow_final is not None:
            output_payload["decision_input_shadow_final"] = shadow_final
            shadow_legacy_comparison = build_shadow_legacy_comparison(
                observed_output=case.input_summary.get("observed_output")
                if isinstance(case.input_summary, dict)
                else {},
                shadow_final=shadow_final,
            )
            output_payload["shadow_legacy_comparison"] = shadow_legacy_comparison
        candidate_final_decision = _candidate_final_decision(case.input_summary)
        if candidate_final_decision is not None:
            output_payload["candidate_final_legacy_comparison"] = build_candidate_final_legacy_comparison(
                observed_output=case.input_summary.get("observed_output")
                if isinstance(case.input_summary, dict)
                else {},
                candidate_final_decision=candidate_final_decision,
            )
        return EvalReplayOutput(
            replay_id=uuid.uuid4().hex,
            case_id=case.case_id,
            source_trace_id=case.source_trace_id,
            source_badcase_id=case.source_badcase_id,
            frozen_input_hash=case.frozen_input_hash,
            status="completed",
            mode="candidate_decision",
            output_hash=stable_hash(output_payload),
            reason_summary=_candidate_decision_reason_summary(output_payload),
            duration_ms=_duration_ms(started),
            output_payload=output_payload,
            metadata={"source": "eval.candidate_decision_replay", "decision_effect": "none"},
        )

    def _stored_case(self, case: EvalCase) -> EvalCase:
        get_case = getattr(self.store, "get_case", None)
        if not callable(get_case):
            return case
        return get_case(case.case_id) or case

    def _candidate_artifacts(self, case_id: str) -> dict[str, dict[str, Any]]:
        get_candidate_artifacts = getattr(self.store, "get_candidate_artifacts", None)
        if not callable(get_candidate_artifacts):
            return {}
        return get_candidate_artifacts(case_id, include_store_metadata=True)


def _run_decision_input_shadow_final(
    *,
    candidate_artifacts: dict[str, dict[str, Any]],
    final_adapter: Any | None,
) -> dict[str, Any] | None:
    if final_adapter is None:
        return None
    decision_input = candidate_artifacts.get("decision_input_candidate")
    replayable_input = candidate_artifacts.get("replayable_input_candidate")
    if not isinstance(decision_input, dict) or not isinstance(replayable_input, dict):
        return None
    return DecisionInputExperimentRunner(final_adapter=final_adapter).run(
        decision_input_candidate=_without_store_metadata(decision_input),
        replayable_input_candidate=_without_store_metadata(replayable_input),
    )


def _without_store_metadata(artifact: dict[str, Any]) -> dict[str, Any]:
    clean = dict(artifact)
    clean.pop("stored_artifact_hash", None)
    return clean


def _candidate_final_decision(input_summary: dict[str, Any]) -> dict[str, Any] | None:
    candidate_audit = input_summary.get("candidate_audit") if isinstance(input_summary, dict) else None
    if not isinstance(candidate_audit, dict):
        return None
    candidate_final = candidate_audit.get("candidate_final_decision")
    return candidate_final if isinstance(candidate_final, dict) else None


def _reason_summary(output_payload: dict[str, Any]) -> str:
    plan = output_payload.get("parsed_plan") if isinstance(output_payload, dict) else {}
    verdict = output_payload.get("verdict") if isinstance(output_payload, dict) else {}
    action = plan.get("main_action") if isinstance(plan, dict) else None
    allowed = verdict.get("allowed") if isinstance(verdict, dict) else None
    return f"Replay uses frozen input and historical parsed output: action={action}, allowed={allowed}."


def _candidate_decision_reason_summary(output_payload: dict[str, Any]) -> str:
    candidate = output_payload.get("candidate_decision") if isinstance(output_payload, dict) else {}
    ready = candidate.get("switch_ready") if isinstance(candidate, dict) else None
    worker_count = candidate.get("worker_artifact_count") if isinstance(candidate, dict) else None
    return (
        "Candidate replay uses structured audit artifacts only: "
        f"switch_ready={ready}, worker_artifact_count={worker_count}."
    )


def _candidate_replay(
    input_summary: dict[str, Any],
    *,
    candidate_artifacts: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    candidate_audit = input_summary.get("candidate_audit") if isinstance(input_summary, dict) else None
    if not isinstance(candidate_audit, dict):
        return {"status": "missing"}
    decision_input = candidate_audit.get("decision_input_candidate")
    replayable_input = candidate_audit.get("replayable_input_candidate")
    readiness = candidate_audit.get("final_decision_switch_readiness")
    gate_candidate = candidate_audit.get("gate_candidate")
    if not isinstance(decision_input, dict) or not isinstance(replayable_input, dict):
        return {"status": "missing"}
    context_artifacts = (
        candidate_audit.get("context_artifacts")
        if isinstance(candidate_audit.get("context_artifacts"), dict)
        else {}
    )
    coverage = replayable_input.get("coverage") if isinstance(replayable_input.get("coverage"), dict) else {}
    artifact_refs = (
        replayable_input.get("artifact_refs")
        if isinstance(replayable_input.get("artifact_refs"), dict)
        else {}
    )
    complete_refs = complete_replay_refs(coverage)
    return {
        "status": "available",
        "decision_input_ref": decision_input.get("input_ref"),
        "decision_input_hash": decision_input.get("input_hash"),
        "replayable_input_ref": replayable_input.get("input_ref"),
        "replayable_input_hash": replayable_input.get("input_hash"),
        "worker_artifact_count": coverage.get("worker_artifact_count"),
        "worker_manifest_complete": coverage.get("worker_manifest_complete"),
        "worker_manifest_missing_fields": (
            list(coverage.get("worker_manifest_missing_fields") or [])
            if isinstance(coverage.get("worker_manifest_missing_fields"), list)
            else []
        ),
        "worker_manifest_consistency": worker_manifest_consistency(
            coverage=coverage,
            artifact_refs=artifact_refs,
            decision_input=decision_input,
            candidate_artifacts=candidate_artifacts or {},
        ),
        "context_artifact_consistency": context_artifact_consistency(
            context_artifacts=context_artifacts,
            decision_input=decision_input,
            replayable_input=replayable_input,
            artifact_refs=artifact_refs,
            candidate_artifacts=candidate_artifacts or {},
        ),
        "artifact_snapshot_consistency": artifact_snapshot_consistency(
            candidate_artifacts=candidate_artifacts or {},
            decision_input=decision_input,
            replayable_input=replayable_input,
        ),
        "counter_conflict_coverage": counter_conflict_coverage(
            lead_synthesis_payload(
                decision_input=decision_input,
                candidate_artifacts=candidate_artifacts or {},
            ),
            lead_synthesis_artifact=lead_synthesis_artifact(candidate_artifacts or {}),
        ),
        "complete_replay_refs": complete_refs,
        "complete_replay_missing_refs": complete_replay_missing_refs(complete_refs),
        "span_tree_parent_complete": coverage.get("span_tree_parent_complete"),
        "span_tree_missing_parent_count": coverage.get("span_tree_missing_parent_count"),
        "worker_hard_blocks": worker_hard_block_contributions(
            list(decision_input.get("contribution_refs") or [])
        ),
        "blocked_actions": (
            list(gate_candidate.get("blocked_actions") or [])
            if isinstance(gate_candidate, dict)
            else []
        ),
        "missing_facts": (
            list(gate_candidate.get("missing_facts") or [])
            if isinstance(gate_candidate, dict)
            else []
        ),
        "execution_fact_source_violations": (
            list(decision_input.get("execution_fact_source_violations") or [])
            if isinstance(decision_input, dict)
            else []
        ),
        "switch_ready": readiness.get("ready") if isinstance(readiness, dict) else None,
        "blocking_reasons": (
            list(readiness.get("blocking_reasons") or [])
            if isinstance(readiness, dict)
            else []
        ),
    }


def _duration_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
