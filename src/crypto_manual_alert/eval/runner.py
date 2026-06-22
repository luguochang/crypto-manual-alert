from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crypto_manual_alert.config import Config, EvalConfig
from crypto_manual_alert.storage.journal import Journal

from .case_builder import EvalCaseBuilder
from .errors import EvalRunError
from .financial_quality_summary import build_financial_quality_summary
from .guards import assert_eval_environment_safe
from .judges import FixtureLLMJudge, OpenAICompatibleLLMJudge, RuleJudge, build_side_effect_score
from .promotion_artifacts import build_shadow_candidate_comparison
from .release_gate import build_release_gate_summary
from .replay import ReplayRunner
from .reports import cleanup_eval_report, write_eval_report
from .schema import EvalRun, EvalScore
from .side_effect_proof import (
    PRODUCTION_SIDE_EFFECT_TABLES,
    build_no_production_side_effect_proof,
    fingerprint_rows,
)
from .store import EvalStore


SUPPORTED_MODES = {"cheap", "judge_only_fixture", "judge_openai"}


class EvalRunner:
    """执行旁路 eval，不调用生产 runner，不发送通知。"""

    def __init__(
        self,
        *,
        journal: Journal,
        store: EvalStore,
        outcome_store: Any | None = None,
        data_dir: str | Path | None = None,
        forbidden_env_names: list[str] | tuple[str, ...] | None = None,
        llm_judge: Any | None = None,
        config: Config | None = None,
        eval_config: EvalConfig | None = None,
    ):
        self.journal = journal
        self.store = store
        self.outcome_store = outcome_store
        self.data_dir = Path(data_dir) if data_dir is not None else store.path.parent.parent
        self.forbidden_env_names = tuple(forbidden_env_names or ())
        self.case_builder = EvalCaseBuilder(journal)
        self.rule_judge = RuleJudge()
        self.fixture_llm_judge = FixtureLLMJudge()
        self.llm_judge = llm_judge
        self.config = config
        self.eval_config = eval_config or (config.eval if config is not None else EvalConfig())
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
        before_snapshot = _prod_snapshot(self.journal.path)
        before = before_snapshot["counts"]
        self.store.upsert_cases(cases)
        self.store.upsert_frozen_inputs(self.case_builder.last_frozen_inputs)

        scores: list[EvalScore] = []
        replay_outputs = {}
        candidate_replay_outputs = {}
        replay_output_payloads = {}
        for case in cases:
            replay_output = self.replay_runner.replay(case)
            replay_outputs[case.case_id] = replay_output
            candidate_replay_output = self.replay_runner.replay(case, mode="candidate_decision")
            candidate_replay_outputs[case.case_id] = candidate_replay_output
            replay_output_payloads[case.case_id] = replay_output.to_public_dict()
            scores.extend(self.rule_judge.evaluate(eval_run_id, case))
            if mode == "judge_only_fixture":
                scores.extend(self.fixture_llm_judge.evaluate(eval_run_id, case))
            if mode == "judge_openai":
                judge = self.llm_judge or self._build_openai_judge()
                scores.extend(judge.evaluate(eval_run_id, case, replay_output=replay_output_payloads[case.case_id]))

        after_snapshot = _prod_snapshot(self.journal.path)
        after = after_snapshot["counts"]
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
        promotion_artifacts = {
            "no_production_side_effect_proof": build_no_production_side_effect_proof(
                eval_run_id=eval_run_id,
                before_counts=before,
                after_counts=after,
                before_fingerprints=before_snapshot["fingerprints"],
                after_fingerprints=after_snapshot["fingerprints"],
            ),
            "shadow_candidate_comparison": build_shadow_candidate_comparison(
                eval_run_id=eval_run_id,
                replay_outputs=candidate_replay_outputs,
            )
        }
        metadata = {
            "judge_provider": _judge_provider(mode),
            "side_effect_deltas": deltas,
            "case_ids": [case.case_id for case in cases],
            "replay": {
                "completed": sum(1 for output in replay_output_payloads.values() if output["status"] == "completed"),
                "failed": sum(1 for output in replay_output_payloads.values() if output["status"] != "completed"),
                "candidate_decision_completed": sum(
                    1 for output in candidate_replay_outputs.values() if output.status == "completed"
                ),
                "candidate_decision_failed": sum(
                    1 for output in candidate_replay_outputs.values() if output.status != "completed"
                ),
            },
            "promotion_artifacts": promotion_artifacts,
            "release_gate": build_release_gate_summary(
                scores=scores,
                replay_outputs=candidate_replay_outputs,
                cases=cases,
                eval_run_id=eval_run_id,
                promotion_artifacts=promotion_artifacts,
                minimum_case_count=self.eval_config.release_gate.minimum_case_count,
                schema_valid_rate_threshold=self.eval_config.release_gate.schema_valid_rate_threshold,
                required_badcase_severities=self.eval_config.release_gate.required_badcase_severities,
            ),
            "financial_quality_gate": build_financial_quality_summary(
                outcome_store=self.outcome_store,
                config=self.eval_config.financial_quality,
            ),
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


def outcome_store_path(data_dir: str | Path) -> Path:
    return Path(data_dir) / "eval" / "crypto-outcomes.db"


def _prod_counts(db_path: str | Path) -> dict[str, int]:
    return _prod_snapshot(db_path)["counts"]


def _prod_snapshot(db_path: str | Path) -> dict[str, dict[str, int] | dict[str, str]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        counts = {
            table: _table_count(conn, table)
            for table in PRODUCTION_SIDE_EFFECT_TABLES
        }
        fingerprints = {
            table: _table_fingerprint(conn, table)
            for table in PRODUCTION_SIDE_EFFECT_TABLES
        }
        return {"counts": counts, "fingerprints": fingerprints}


def _table_count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _table_fingerprint(conn: sqlite3.Connection, table: str) -> str:
    columns = [str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if not columns:
        return fingerprint_rows([])
    order_by = ", ".join(columns)
    rows = [
        {column: row[column] for column in columns}
        for row in conn.execute(f"SELECT * FROM {table} ORDER BY {order_by}").fetchall()
    ]
    return fingerprint_rows(rows)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _judge_provider(mode: str) -> str:
    if mode == "judge_only_fixture":
        return "fixture"
    if mode == "judge_openai":
        return "openai_compatible"
    return "disabled"
