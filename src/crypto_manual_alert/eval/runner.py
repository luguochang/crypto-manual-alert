from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crypto_manual_alert.config import Config
from crypto_manual_alert.journal import Journal

from .case_builder import EvalCaseBuilder
from .errors import EvalRunError
from .guards import assert_eval_environment_safe
from .judges import FixtureLLMJudge, OpenAICompatibleLLMJudge, RuleJudge, build_side_effect_score
from .replay import ReplayRunner
from .reports import cleanup_eval_report, write_eval_report
from .schema import EvalRun, EvalScore
from .store import EvalStore


SUPPORTED_MODES = {"cheap", "judge_only_fixture", "judge_openai"}


class EvalRunner:
    """执行旁路 eval，不调用生产 runner，不发送通知。"""

    def __init__(
        self,
        *,
        journal: Journal,
        store: EvalStore,
        data_dir: str | Path | None = None,
        forbidden_env_names: list[str] | tuple[str, ...] | None = None,
        llm_judge: Any | None = None,
        config: Config | None = None,
    ):
        self.journal = journal
        self.store = store
        self.data_dir = Path(data_dir) if data_dir is not None else store.path.parent.parent
        self.forbidden_env_names = tuple(forbidden_env_names or ())
        self.case_builder = EvalCaseBuilder(journal)
        self.rule_judge = RuleJudge()
        self.fixture_llm_judge = FixtureLLMJudge()
        self.llm_judge = llm_judge
        self.config = config
        self.replay_runner = ReplayRunner(store)

    def run(
        self,
        *,
        dataset_name: str | None = None,
        badcase_ids: list[int] | None = None,
        mode: str = "judge_only_fixture",
        limit: int = 50,
    ) -> EvalRun:
        assert_eval_environment_safe(self.forbidden_env_names)
        cases = self.case_builder.build_cases(dataset=dataset_name, badcase_ids=badcase_ids, limit=limit)
        if not cases:
            raise ValueError("no eval cases selected")
        if mode not in SUPPORTED_MODES:
            raise ValueError(f"unsupported eval mode: {mode}")

        eval_run_id = uuid.uuid4().hex
        started_at = _now_iso()
        before = _prod_counts(self.journal.path)
        self.store.upsert_cases(cases)
        self.store.upsert_frozen_inputs(self.case_builder.last_frozen_inputs)

        scores: list[EvalScore] = []
        replay_outputs = {}
        for case in cases:
            replay_output = self.replay_runner.replay(case)
            replay_outputs[case.case_id] = replay_output.to_public_dict()
            scores.extend(self.rule_judge.evaluate(eval_run_id, case))
            if mode == "judge_only_fixture":
                scores.extend(self.fixture_llm_judge.evaluate(eval_run_id, case))
            if mode == "judge_openai":
                judge = self.llm_judge or self._build_openai_judge()
                scores.extend(judge.evaluate(eval_run_id, case, replay_output=replay_outputs[case.case_id]))

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
        metadata = {
            "judge_provider": _judge_provider(mode),
            "side_effect_deltas": deltas,
            "case_ids": [case.case_id for case in cases],
            "replay": {
                "completed": sum(1 for output in replay_outputs.values() if output["status"] == "completed"),
                "failed": sum(1 for output in replay_outputs.values() if output["status"] != "completed"),
            },
        }
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
            metadata=metadata,
        )
        try:
            report_refs = write_eval_report(data_dir=self.data_dir, run=run, cases=cases, scores=scores)
        except Exception as exc:
            raise EvalRunError(f"failed to write eval report: {type(exc).__name__}") from exc
        run = EvalRun(**{**run.__dict__, "metadata": {**metadata, **report_refs}})
        try:
            self.store.insert_run(run, cases, scores)
        except Exception as exc:
            cleanup_eval_report(data_dir=self.data_dir, refs=report_refs)
            raise EvalRunError(f"failed to persist eval run: {type(exc).__name__}") from exc
        return run

    def _build_openai_judge(self) -> OpenAICompatibleLLMJudge:
        if self.config is None:
            raise ValueError("judge_openai requires EvalRunner config or injected llm_judge")
        return OpenAICompatibleLLMJudge.from_config(self.config)


def eval_store_path(data_dir: str | Path) -> Path:
    return Path(data_dir) / "eval" / "crypto-eval.db"


def _prod_counts(db_path: str | Path) -> dict[str, int]:
    with sqlite3.connect(db_path) as conn:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("plan_runs", "notifications", "manual_outcomes", "traces", "trace_spans", "llm_interactions")
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _judge_provider(mode: str) -> str:
    if mode == "judge_only_fixture":
        return "fixture"
    if mode == "judge_openai":
        return "openai_compatible"
    return "disabled"
