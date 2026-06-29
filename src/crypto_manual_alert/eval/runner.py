from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crypto_manual_alert.journal import Journal

from .case_builder import EvalCaseBuilder
from .judges import FixtureLLMJudge, RuleJudge, build_side_effect_score
from .schema import EvalRun, EvalScore
from .store import EvalStore


class EvalRunner:
    """执行旁路 eval，不调用生产 runner，不发送通知。"""

    def __init__(self, *, journal: Journal, store: EvalStore):
        self.journal = journal
        self.store = store
        self.case_builder = EvalCaseBuilder(journal)
        self.rule_judge = RuleJudge()
        self.llm_judge = FixtureLLMJudge()

    def run(
        self,
        *,
        dataset_name: str | None = None,
        badcase_ids: list[int] | None = None,
        mode: str = "judge_only_fixture",
        limit: int = 50,
    ) -> EvalRun:
        cases = self.case_builder.build_cases(dataset=dataset_name, badcase_ids=badcase_ids, limit=limit)
        if not cases:
            raise ValueError("no eval cases selected")
        if mode != "judge_only_fixture":
            raise ValueError(f"unsupported eval mode: {mode}")

        eval_run_id = uuid.uuid4().hex
        started_at = _now_iso()
        before = _prod_counts(self.journal.path)
        self.store.upsert_cases(cases)

        scores: list[EvalScore] = []
        for case in cases:
            scores.extend(self.rule_judge.evaluate(eval_run_id, case))
            if mode == "judge_only_fixture":
                scores.extend(self.llm_judge.evaluate(eval_run_id, case))

        after = _prod_counts(self.journal.path)
        deltas = {table: after[table] - before[table] for table in before}
        for case in cases:
            scores.append(build_side_effect_score(eval_run_id=eval_run_id, case=case, deltas=deltas))

        case_failed = {
            score.case_id
            for score in scores
            if not score.passed and score.judge_name != "eval.side_effect_guard"
        }
        guard_failed = any(score.judge_name == "eval.side_effect_guard" and not score.passed for score in scores)
        fail_count = len(case_failed) + (1 if guard_failed else 0)
        pass_count = max(0, len(cases) - len(case_failed))
        run = EvalRun(
            eval_run_id=eval_run_id,
            dataset_name=dataset_name or "selected_badcases",
            mode=mode,
            status="failed" if fail_count else "passed",
            started_at=started_at,
            ended_at=_now_iso(),
            case_count=len(cases),
            pass_count=pass_count,
            fail_count=fail_count,
            metadata={
                "judge_provider": "fixture",
                "side_effect_deltas": deltas,
                "case_ids": [case.case_id for case in cases],
            },
        )
        self.store.insert_run(run, scores)
        return run


def eval_store_path(data_dir: str | Path) -> Path:
    return Path(data_dir) / "eval" / "crypto-eval.db"


def _prod_counts(db_path: str | Path) -> dict[str, int]:
    with sqlite3.connect(db_path) as conn:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("plan_runs", "notifications", "manual_outcomes")
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
