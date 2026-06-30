from __future__ import annotations

import time
import uuid
from typing import Any

from crypto_manual_alert.frozen_input import stable_hash

from .schema import EvalCase, EvalReplayOutput
from .store import EvalStore


class ReplayRunner:
    """Eval 侧回放器，只使用冻结输入和历史观测输出，不访问生产 runner。"""

    def __init__(self, store: EvalStore):
        self.store = store

    def replay(self, case: EvalCase) -> EvalReplayOutput:
        started = time.perf_counter()
        frozen = self.store.get_frozen_input(case.frozen_input_hash)
        if frozen is None:
            output = self._failed(case, "frozen_input_missing", started)
            self.store.insert_replay_output(output)
            return output

        observed = case.input_summary.get("observed_output") if isinstance(case.input_summary, dict) else {}
        parsed_plan = observed.get("parsed_plan") if isinstance(observed, dict) else {}
        verdict = observed.get("verdict") if isinstance(observed, dict) else {}
        output_payload = {
            "frozen_input_hash": frozen.frozen_input_hash,
            "parsed_plan": parsed_plan if isinstance(parsed_plan, dict) else {},
            "verdict": verdict if isinstance(verdict, dict) else {},
            "public_summary": frozen.public_summary,
        }
        final_action = str(output_payload["parsed_plan"].get("main_action") or "") or None
        allowed_value = output_payload["verdict"].get("allowed")
        allowed = allowed_value if isinstance(allowed_value, bool) else None
        output = EvalReplayOutput(
            replay_id=uuid.uuid4().hex,
            case_id=case.case_id,
            source_trace_id=case.source_trace_id,
            source_badcase_id=case.source_badcase_id,
            frozen_input_hash=case.frozen_input_hash,
            status="completed",
            mode="frozen_observed",
            final_action=final_action,
            allowed=allowed,
            output_hash=stable_hash(output_payload),
            reason_summary=_reason_summary(output_payload),
            duration_ms=_duration_ms(started),
            output_payload=output_payload,
            metadata={"source": "eval.frozen_observed_replay"},
        )
        self.store.insert_replay_output(output)
        return output

    def _failed(self, case: EvalCase, message: str, started: float) -> EvalReplayOutput:
        return EvalReplayOutput(
            replay_id=uuid.uuid4().hex,
            case_id=case.case_id,
            source_trace_id=case.source_trace_id,
            source_badcase_id=case.source_badcase_id,
            frozen_input_hash=case.frozen_input_hash,
            status="failed",
            mode="frozen_observed",
            error_message=message,
            duration_ms=_duration_ms(started),
            output_payload={},
            metadata={"source": "eval.replay", "failure_category": message},
        )


def _reason_summary(output_payload: dict[str, Any]) -> str:
    plan = output_payload.get("parsed_plan") if isinstance(output_payload, dict) else {}
    verdict = output_payload.get("verdict") if isinstance(output_payload, dict) else {}
    action = plan.get("main_action") if isinstance(plan, dict) else None
    allowed = verdict.get("allowed") if isinstance(verdict, dict) else None
    return f"Replay uses frozen input and historical parsed output: action={action}, allowed={allowed}."


def _duration_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
