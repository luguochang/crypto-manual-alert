from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from ..config import ConfigError, load_config
from ..context.request import DecisionRequest
from ..eval.cli import add_eval_subcommands, handle_eval_command
from ..storage.journal import Journal
from ..notification.sinks import BarkNotificationSink
from ..workflow.executor import RunExecutor as WorkflowRunExecutor
from ..workflow.executor import RunResult
from ..workflow.legacy_plan_runner import journal_path
from ..workflow.scheduler import JobLock, run_scheduler

if TYPE_CHECKING:
    from ..workflow.executor import RunExecutor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="crypto-alert")
    parser.add_argument("--config", action="append", default=["config/default.yaml"], help="YAML config path; can be repeated")
    sub = parser.add_subparsers(dest="command", required=True)

    run_once = sub.add_parser("run-once")
    run_once.add_argument("--symbol", default="ETH-USDT-SWAP")

    sub.add_parser("show-config")

    test_bark = sub.add_parser("test-bark")
    test_bark.add_argument("--message", default="Crypto alert Bark test. No trading action.")

    outcome = sub.add_parser("record-outcome")
    outcome.add_argument("--plan-id", required=True)
    outcome.add_argument("--outcome", required=True)
    outcome.add_argument("--notes", default="")

    trace_list = sub.add_parser("trace-list")
    trace_list.add_argument("--limit", type=int, default=20)

    trace_show = sub.add_parser("trace-show")
    trace_show.add_argument("--trace-id", required=True)
    trace_show.add_argument("--include-payloads", action="store_true")

    badcase = sub.add_parser("record-badcase")
    badcase_target = badcase.add_mutually_exclusive_group(required=True)
    badcase_target.add_argument("--trace-id")
    badcase_target.add_argument("--plan-id")
    badcase.add_argument("--category", required=True)
    badcase.add_argument("--severity", required=True)
    badcase.add_argument("--summary")
    badcase.add_argument("--comment")
    badcase.add_argument("--span-id")
    badcase.add_argument("--llm-interaction-id", type=int)
    badcase.add_argument("--source", default="developer")
    badcase.add_argument("--expected")
    badcase.add_argument("--actual")
    badcase.add_argument("--eval-dataset")

    badcase_list = sub.add_parser("badcase-list")
    badcase_list.add_argument("--limit", type=int, default=20)

    scheduler = sub.add_parser("scheduler")
    scheduler.add_argument("--symbol", default="ETH-USDT-SWAP")
    collect = sub.add_parser("collect-outcomes")
    collect.add_argument("--limit", type=int, default=20)
    collect.add_argument("--symbol", default=None)
    add_eval_subcommands(sub)

    args = parser.parse_args(argv)
    try:
        config = load_config(*args.config)
    except ConfigError as exc:
        print(f"CONFIG_ERROR: {exc}")
        return 2

    journal = Journal(journal_path(config))
    eval_exit_code = handle_eval_command(args, config=config, journal=journal)
    if eval_exit_code is not None:
        return eval_exit_code

    if args.command == "show-config":
        print(json.dumps(config.safe_dict(), ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "test-bark":
        sink = BarkNotificationSink(config)
        # Avoid importing domain fixture into CLI test path; this is a direct API smoke action.
        import httpx
        from urllib.parse import quote
        import os

        key = os.getenv(config.notification.bark_device_key_env, "")
        if not key:
            print(f"Missing {config.notification.bark_device_key_env}")
            return 2
        url = f"{config.notification.bark_base_url.rstrip('/')}/{quote(key)}/{quote('Crypto alert test')}/{quote(args.message)}"
        response = httpx.get(url, timeout=config.notification.timeout_seconds)
        print(f"Bark response: {response.status_code}")
        return 0 if response.status_code < 400 else 1
    if args.command == "record-outcome":
        journal.record_outcome(args.plan_id, args.outcome, args.notes)
        print(f"Recorded outcome for {args.plan_id}")
        return 0
    if args.command == "trace-list":
        print(json.dumps(journal.list_traces(limit=args.limit), ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "trace-show":
        detail = journal.get_trace_detail(args.trace_id, include_payloads=args.include_payloads)
        if detail is None:
            print(f"TRACE_NOT_FOUND: {args.trace_id}")
            return 1
        print(json.dumps(detail, ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "record-badcase":
        try:
            badcase_id = journal.record_badcase(
                trace_id=args.trace_id,
                plan_id=args.plan_id,
                span_id=args.span_id,
                llm_interaction_id=args.llm_interaction_id,
                category=args.category,
                severity=args.severity,
                summary=args.summary,
                comment=args.comment,
                source=args.source,
                expected_behavior=args.expected,
                actual_behavior=args.actual,
                eval_dataset_name=args.eval_dataset,
            )
        except ValueError as exc:
            print(f"BADCASE_ERROR: {exc}")
            return 2
        print(
            json.dumps(
                {"badcase_id": badcase_id, "trace_id": args.trace_id, "plan_id": args.plan_id},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "badcase-list":
        print(json.dumps(journal.list_badcases(limit=args.limit), ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "collect-outcomes":
        from ..eval.outcome_collector import OutcomeCollector, PlanOutcomeInput, horizon_seconds
        from ..eval.outcome_store import OutcomeStore

        outcome_store = OutcomeStore(Path(config.app.data_dir) / "crypto-outcomes.db")
        collector = OutcomeCollector(config, outcome_store)
        traces = journal.list_traces(limit=args.limit)
        collected = 0
        skipped = 0
        for summary in traces:
            if args.symbol and summary.get("symbol") != args.symbol:
                continue
            trace_id = summary.get("trace_id")
            if not trace_id:
                continue
            detail = journal.get_trace_detail(trace_id)
            if not detail:
                skipped += 1
                continue
            trace = detail.get("trace") or {}
            plan_run = detail.get("plan_run") or {}
            parsed = plan_run.get("parsed_plan") or {}
            action = parsed.get("main_action")
            h_secs = horizon_seconds(trace.get("horizon"))
            generated_at = _parse_iso(trace.get("created_at"))
            if not action or h_secs is None or generated_at is None:
                skipped += 1
                continue
            plan_input = PlanOutcomeInput(
                decision_ref=plan_run.get("plan_id") or trace_id,
                evaluation_target="legacy_final",
                symbol=trace.get("symbol") or summary.get("symbol") or "",
                action=str(action),
                probability=_to_float_or_none(parsed.get("probability")),
                entry_price=_to_float_or_none(parsed.get("entry_trigger")),
                stop_price=_to_float_or_none(parsed.get("stop_price")),
                target_1=_to_float_or_none(parsed.get("target_1")),
                target_2=_to_float_or_none(parsed.get("target_2")),
                generated_at=generated_at,
                horizon_seconds=h_secs,
            )
            outcome = collector.collect(plan_input)
            if outcome is not None:
                collected += 1
            else:
                skipped += 1
        print(
            json.dumps(
                {"collected": collected, "skipped": skipped, "limit": args.limit},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "run-once":
        result = _run_executor_class()(config=config, journal=journal).submit(
            DecisionRequest(run_type="manual", symbol=args.symbol)
        )
        print(_run_result_to_json(result))
        return 0 if result.verdict.get("allowed") is True else 3
    if args.command == "scheduler":
        lock = JobLock(journal, "plan-run", ttl=timedelta(seconds=config.scheduler.lock_ttl_seconds))
        executor = _run_executor_class()(config=config, journal=journal)

        def job() -> None:
            result = executor.submit(DecisionRequest(run_type="scheduled", symbol=args.symbol))
            print(_run_result_to_json(result))

        run_scheduler(
            config.scheduler.interval_seconds,
            lock,
            job,
            run_on_start=config.scheduler.run_on_start,
            max_iterations=config.scheduler.max_iterations,
        )
        return 0
    return 1


def _run_executor_class():
    package = sys.modules.get("crypto_manual_alert.cli")
    return getattr(package, "RunExecutor", WorkflowRunExecutor) if package is not None else WorkflowRunExecutor


def _run_result_to_json(result: RunResult) -> str:
    return json.dumps(
        {
            "plan_id": result.plan["plan_id"],
            "instrument": result.plan["instrument"],
            "main_action": result.plan["main_action"],
            "allowed": result.verdict.get("allowed"),
            "reasons": result.verdict.get("reasons") or [],
            "warnings": result.verdict.get("warnings") or [],
            "rule_hits": result.verdict.get("rule_hits") or [],
            "expires_at": result.plan["expires_at"],
            "manual_execution_required": result.plan["manual_execution_required"],
        },
        ensure_ascii=False,
        indent=2,
        default=str,
    )


if __name__ == "__main__":
    raise SystemExit(main())


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _to_float_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
