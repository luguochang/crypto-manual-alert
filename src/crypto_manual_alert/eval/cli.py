from __future__ import annotations

import argparse
import json

from crypto_manual_alert.config import Config
from crypto_manual_alert.eval.errors import EvalRunError
from crypto_manual_alert.eval.guards import EvalSafetyError
from crypto_manual_alert.journal import Journal

from .runner import EvalRunner, eval_store_path
from .store import EvalStore


def add_eval_subcommands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """注册 eval CLI 子命令，主 CLI 只做分发，不承载业务逻辑。"""

    eval_run = subparsers.add_parser("eval-run")
    eval_run.add_argument("--dataset", dest="dataset_name")
    eval_run.add_argument("--badcase-id", dest="badcase_ids", action="append", type=int)
    eval_run.add_argument("--mode", choices=["cheap", "judge_only_fixture"], default="cheap")
    eval_run.add_argument("--limit", type=int, default=50)

    eval_report = subparsers.add_parser("eval-report")
    eval_report.add_argument("--eval-run-id", required=True)

    eval_list = subparsers.add_parser("eval-list-runs")
    eval_list.add_argument("--limit", type=int, default=20)

    eval_show = subparsers.add_parser("eval-show-run")
    eval_show.add_argument("--eval-run-id", required=True)


def handle_eval_command(args: argparse.Namespace, *, config: Config, journal: Journal) -> int | None:
    """处理 eval CLI 命令；非 eval 命令返回 None 交给主 CLI。"""

    if args.command not in {"eval-run", "eval-report", "eval-list-runs", "eval-show-run"}:
        return None
    store = EvalStore(eval_store_path(config.app.data_dir))
    if args.command == "eval-run":
        runner = EvalRunner(
            journal=journal,
            store=store,
            data_dir=config.app.data_dir,
            forbidden_env_names=config.security.forbidden_env_names,
        )
        try:
            run = runner.run(
                dataset_name=args.dataset_name,
                badcase_ids=args.badcase_ids,
                mode=args.mode,
                limit=args.limit,
            )
        except EvalSafetyError as exc:
            print(json.dumps({"error": exc.code, "message": str(exc)}, ensure_ascii=False, indent=2))
            return 2
        except ValueError as exc:
            code = "eval_no_cases" if str(exc) == "no eval cases selected" else "eval_run_failed"
            print(json.dumps({"error": code, "message": str(exc)}, ensure_ascii=False, indent=2))
            return 2
        except EvalRunError as exc:
            print(json.dumps({"error": exc.code, "message": str(exc)}, ensure_ascii=False, indent=2))
            return 1
        print(json.dumps(run.__dict__, ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "eval-report":
        detail = store.get_run_detail(args.eval_run_id)
        if detail is None:
            print(json.dumps({"error": "eval_run_not_found", "eval_run_id": args.eval_run_id}, ensure_ascii=False))
            return 1
        metadata = detail["run"].get("metadata") or {}
        print(
            json.dumps(
                {
                    "eval_run_id": args.eval_run_id,
                    "report_json_ref": metadata.get("report_json_ref"),
                    "report_markdown_ref": metadata.get("report_markdown_ref"),
                    "status": detail["run"].get("status"),
                    "case_count": detail["run"].get("case_count"),
                    "fail_count": detail["run"].get("fail_count"),
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
        return 0
    if args.command == "eval-list-runs":
        print(json.dumps(store.list_runs(limit=args.limit), ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "eval-show-run":
        detail = store.get_run_detail(args.eval_run_id)
        if detail is None:
            print(json.dumps({"error": "eval_run_not_found", "eval_run_id": args.eval_run_id}, ensure_ascii=False))
            return 1
        print(json.dumps(detail, ensure_ascii=False, indent=2, default=str))
        return 0
    return None
