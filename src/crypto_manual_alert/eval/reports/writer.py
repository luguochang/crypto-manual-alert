from __future__ import annotations

import json
from contextlib import suppress
from pathlib import Path
from typing import Any

from crypto_manual_alert.eval.schema import EvalCase, EvalRun, EvalScore


def write_eval_report(
    *,
    data_dir: str | Path,
    run: EvalRun,
    cases: list[EvalCase],
    scores: list[EvalScore],
) -> dict[str, str]:
    """写入 JSON/Markdown 报告，供 CLI、页面和后续 release gate 复用。"""

    reports_dir = Path(data_dir) / "eval" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_ref = Path("eval") / "reports" / f"{run.eval_run_id}.json"
    markdown_ref = Path("eval") / "reports" / f"{run.eval_run_id}.md"
    json_path = Path(data_dir) / json_ref
    markdown_path = Path(data_dir) / markdown_ref

    payload = {
        "run": run.__dict__,
        "cases": [_case_payload(case) for case in cases],
        "scores": [_score_payload(score) for score in scores],
        "summary": {
            "case_count": run.case_count,
            "pass_count": run.pass_count,
            "fail_count": run.fail_count,
            "side_effect_deltas": run.metadata.get("side_effect_deltas", {}),
            "failed_judges": [score.judge_name for score in scores if not score.passed],
        },
    }
    try:
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        markdown_path.write_text(_markdown(payload), encoding="utf-8")
    except Exception:
        cleanup_eval_report(data_dir=data_dir, refs={"report_json_ref": _ref(json_ref), "report_markdown_ref": _ref(markdown_ref)})
        raise
    return {"report_json_ref": _ref(json_ref), "report_markdown_ref": _ref(markdown_ref)}


def cleanup_eval_report(*, data_dir: str | Path, refs: dict[str, str]) -> None:
    """删除本次 eval 已生成但不应保留的报告半成品。"""

    for key in ("report_json_ref", "report_markdown_ref"):
        ref = refs.get(key)
        if not ref:
            continue
        path = Path(data_dir) / ref
        if _is_inside_data_dir(Path(data_dir), path):
            with suppress(FileNotFoundError):
                path.unlink()


def _case_payload(case: EvalCase) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "dataset_name": case.dataset_name,
        "source_trace_id": case.source_trace_id,
        "source_badcase_id": case.source_badcase_id,
        "symbol": case.symbol,
        "severity": case.severity,
        "failure_category": case.failure_category,
        "expected_behavior": case.expected_behavior,
        "actual_behavior": case.actual_behavior,
        "frozen_input_hash": case.frozen_input_hash,
    }


def _score_payload(score: EvalScore) -> dict[str, Any]:
    return {
        "score_id": score.score_id,
        "eval_run_id": score.eval_run_id,
        "case_id": score.case_id,
        "source_trace_id": score.source_trace_id,
        "source_badcase_id": score.source_badcase_id,
        "judge_name": score.judge_name,
        "judge_type": score.judge_type,
        "score": score.score,
        "passed": score.passed,
        "severity": score.severity,
        "failure_category": score.failure_category,
        "reason_summary": score.reason_summary,
        "evidence_refs": score.evidence_refs,
        "needs_human_review": score.needs_human_review,
        "metadata": score.metadata,
    }


def _markdown(payload: dict[str, Any]) -> str:
    run = payload["run"]
    summary = payload["summary"]
    lines = [
        f"# Eval Report {run['eval_run_id']}",
        "",
        f"- Dataset: {run['dataset_name']}",
        f"- Mode: {run['mode']}",
        f"- Status: {run['status']}",
        f"- Cases: {summary['case_count']}",
        f"- Pass / Fail: {summary['pass_count']} / {summary['fail_count']}",
        f"- Side-effect deltas: `{json.dumps(summary['side_effect_deltas'], ensure_ascii=False, sort_keys=True)}`",
        "",
        "## Failed Scores",
    ]
    failed = [score for score in payload["scores"] if not score["passed"]]
    if not failed:
        lines.extend(["", "No failed scores."])
    for score in failed:
        lines.extend(
            [
                "",
                f"- `{score['judge_name']}` on `{score['case_id']}`",
                f"  - Severity: {score['severity']}",
                f"  - Category: {score['failure_category']}",
                f"  - Reason: {score['reason_summary']}",
                f"  - Evidence refs: `{', '.join(score['evidence_refs'])}`",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def _ref(path: Path) -> str:
    return str(path).replace("\\", "/")


def _is_inside_data_dir(data_dir: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(data_dir.resolve())
        return True
    except ValueError:
        return False
