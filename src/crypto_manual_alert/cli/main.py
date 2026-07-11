from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from ..config import Config, ConfigError, load_config
from ..context.request import DecisionRequest
from ..eval.cli import add_eval_subcommands, handle_eval_command
from ..eval.outcome_store import OutcomeStore
from ..eval.runner import outcome_store_path
from ..storage.business_summary import build_business_summary
from ..storage.journal import Journal
from ..storage.query_repository import JournalQueryRepository
from ..storage.result_review import result_review_from_outcomes
from ..notification.sinks import BarkNotificationSink
from ..workflow.executor import RunExecutor as WorkflowRunExecutor
from ..workflow.executor import RunResult
from ..workflow.legacy_plan_runner import journal_path
from ..workflow.scheduler import JobLock, run_scheduler

if TYPE_CHECKING:
    from ..workflow.executor import RunExecutor


class CliProjectionError(RuntimeError):
    def __init__(self, code: str, message: str, *, trace_id: str):
        super().__init__(message)
        self.code = code
        self.trace_id = trace_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="crypto-alert")
    parser.add_argument("--config", action="append", default=["config/default.yaml"], help="YAML config path; can be repeated")
    sub = parser.add_subparsers(dest="command", required=True)

    run_once = sub.add_parser("run-once")
    run_once.add_argument("--symbol", default="ETH-USDT-SWAP")
    run_once.add_argument(
        "--query",
        default="",
        help="Operator audit note for this manual alert. Current planning is still driven by symbol/horizon/config.",
    )
    run_once.add_argument("--horizon", default=None, help="Optional manual review horizon, for example 6h or 6h/12h/1d.")

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
        detail = JournalQueryRepository(
            journal,
            OutcomeStore(outcome_store_path(config.app.data_dir)),
            config=config,
        ).get_run_detail(args.trace_id, include_payloads=args.include_payloads)
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
        from ..eval.outcome_collector import OutcomeCollector, PlanOutcomeInput, horizon_seconds_values

        outcome_store = OutcomeStore(outcome_store_path(config.app.data_dir))
        collector = OutcomeCollector(config, outcome_store)
        traces = journal.list_traces(limit=args.limit)
        collected = 0
        skipped = 0
        collected_refs: list[dict[str, object]] = []
        errors: list[dict[str, object]] = []
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
            if not _trace_outcome_eligible(trace, plan_run):
                skipped += 1
                continue
            horizon_values = horizon_seconds_values(trace.get("horizon"))
            generated_at = _parse_iso(plan_run.get("created_at")) or _parse_iso(trace.get("created_at"))
            if not horizon_values or generated_at is None:
                skipped += 1
                continue
            payload = journal.get_plan_run_payload(str(plan_run.get("plan_id") or "")) or {}
            trace_had_input = False
            for h_secs in horizon_values:
                plan_inputs = _outcome_plan_inputs_for_trace(
                    trace=trace,
                    summary=summary,
                    plan_run=plan_run,
                    payload=payload,
                    generated_at=generated_at,
                    horizon_seconds_value=h_secs,
                    plan_input_cls=PlanOutcomeInput,
                )
                if not plan_inputs:
                    continue
                trace_had_input = True
                for plan_input in plan_inputs:
                    try:
                        outcome = collector.collect(plan_input)
                    except Exception as exc:
                        skipped += 1
                        errors.append(
                            {
                                "trace_id": trace_id,
                                "plan_id": plan_run.get("plan_id"),
                                "decision_ref": getattr(plan_input, "decision_ref", None),
                                "error_type": type(exc).__name__,
                                "error_message": str(exc),
                            }
                        )
                        continue
                    if outcome is not None:
                        collected += 1
                        ref = _collected_outcome_ref(outcome)
                        if ref is not None:
                            collected_refs.append(ref)
                    else:
                        skipped += 1
            if not trace_had_input:
                skipped += 1
        output: dict[str, object] = {"collected": collected, "skipped": skipped, "limit": args.limit}
        if collected_refs:
            output["collected_refs"] = collected_refs
        if errors:
            output["errors"] = errors
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    if args.command == "run-once":
        executor_cls = _run_executor_class()
        result = executor_cls(config=config, journal=journal).submit(
            DecisionRequest(run_type="manual", symbol=args.symbol, query_text=args.query, horizon=args.horizon)
        )
        try:
            output = _run_result_to_json(
                result,
                config=config,
                journal=journal,
                require_persisted=executor_cls is WorkflowRunExecutor,
            )
        except CliProjectionError as exc:
            print(_projection_error_to_json(exc))
            return 2
        print(output)
        return 0 if result.verdict.get("allowed") is True else 3
    if args.command == "scheduler":
        if not config.scheduler.enabled:
            print(
                "SCHEDULER_DISABLED: scheduler.enabled=false; set SCHEDULER_ENABLED=true "
                "or use a config overlay with scheduler.enabled=true before starting background polling."
            )
            return 2
        lock = JobLock(journal, "plan-run", ttl=timedelta(seconds=config.scheduler.lock_ttl_seconds))
        executor_cls = _run_executor_class()
        executor = executor_cls(config=config, journal=journal)

        def job() -> None:
            result = executor.submit(DecisionRequest(run_type="scheduled", symbol=args.symbol))
            print(_run_result_to_json(result, config=config, journal=journal, require_persisted=executor_cls is WorkflowRunExecutor))

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


def _run_result_to_json(
    result: RunResult,
    *,
    config: Config | None = None,
    journal: Journal | None = None,
    require_persisted: bool = False,
) -> str:
    detail = _detail_projection(result, config=config, journal=journal, require_persisted=require_persisted)
    plan = detail["plan"]
    verdict = detail["verdict"]
    business_summary = detail["business_summary"]
    notification = detail["notification"]
    result_review = detail["result_review"]
    requested_horizon = result.context.get("horizon") if isinstance(result.context, dict) else None
    plan_horizon = plan.get("horizon")
    return json.dumps(
        {
            "trace_id": result.trace_id,
            "plan_id": plan["plan_id"],
            "instrument": plan["instrument"],
            "main_action": plan["main_action"],
            "horizon": plan_horizon,
            "plan_horizon": plan_horizon,
            "requested_horizon": requested_horizon,
            "horizon_semantics": {
                "requested_horizon_drives_final_plan": False,
                "explanation": (
                    "requested_horizon is retained as manual review context; current final plan horizon "
                    "comes from the generated plan until query/horizon intent is wired into final input."
                ),
            },
            "allowed": verdict.get("allowed"),
            "reasons": verdict.get("reasons") or [],
            "warnings": verdict.get("warnings") or [],
            "rule_hits": verdict.get("rule_hits") or [],
            "expires_at": plan["expires_at"],
            "manual_execution_required": plan["manual_execution_required"],
            "business_summary": business_summary,
            "notification": notification,
            "result_review": result_review,
        },
        ensure_ascii=False,
        indent=2,
        default=str,
    )


def _projection_error_to_json(exc: CliProjectionError) -> str:
    return json.dumps(
        {
            "ok": False,
            "trace_id": exc.trace_id,
            "error": {
                "code": exc.code,
                "message": str(exc),
            },
        },
        ensure_ascii=False,
        indent=2,
    )


def _detail_projection(
    result: RunResult,
    *,
    config: Config | None,
    journal: Journal | None,
    require_persisted: bool,
) -> dict[str, object]:
    plan = dict(result.plan)
    verdict = dict(result.verdict)
    business_summary: dict[str, object] | None = None
    result_review: dict[str, object] | None = None

    if config is not None and journal is not None:
        detail = JournalQueryRepository(
            journal,
            OutcomeStore(outcome_store_path(config.app.data_dir)),
            config=config,
        ).get_run_detail(result.trace_id)
        if require_persisted and not isinstance(detail, dict):
            raise CliProjectionError(
                "cli_projection_missing_detail",
                "run completed but persisted run detail could not be read back",
                trace_id=result.trace_id,
            )
        if isinstance(detail, dict):
            plan_run = detail.get("plan_run")
            if require_persisted and not isinstance(plan_run, dict):
                raise CliProjectionError(
                    "cli_projection_missing_plan_run",
                    "run completed but persisted plan_run projection is missing",
                    trace_id=result.trace_id,
                )
            if isinstance(plan_run, dict):
                parsed_plan = plan_run.get("parsed_plan")
                if isinstance(parsed_plan, dict):
                    plan = {**parsed_plan, **plan}
                stored_verdict = plan_run.get("verdict")
                if isinstance(stored_verdict, dict):
                    verdict = stored_verdict
                stored_summary = plan_run.get("business_summary")
                if isinstance(stored_summary, dict):
                    business_summary = stored_summary
            if require_persisted and business_summary is None:
                raise CliProjectionError(
                    "cli_projection_missing_business_summary",
                    "run completed but persisted business_summary projection is missing",
                    trace_id=result.trace_id,
                )
            stored_review = detail.get("result_review")
            if isinstance(stored_review, dict):
                result_review = stored_review
            if require_persisted and result_review is None:
                raise CliProjectionError(
                    "cli_projection_missing_result_review",
                    "run completed but result_review projection is missing",
                    trace_id=result.trace_id,
                )

    if business_summary is None:
        notification = journal.get_latest_notification(plan.get("plan_id")) if journal is not None else None
        business_summary = build_business_summary(
            plan=plan,
            verdict=verdict,
            config=config,
            notification=notification,
        )
    notification_summary = business_summary.get("notification")
    if not isinstance(notification_summary, dict):
        notification_summary = {"status": "not_recorded", "message": "通知状态未记录。"}
    if result_review is None:
        result_review = result_review_from_outcomes([])

    return {
        "plan": plan,
        "verdict": verdict,
        "business_summary": business_summary,
        "notification": notification_summary,
        "result_review": result_review,
    }


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _collected_outcome_ref(outcome: object) -> dict[str, object] | None:
    decision_ref = getattr(outcome, "decision_ref", None)
    evaluation_target = getattr(outcome, "evaluation_target", None)
    symbol = getattr(outcome, "symbol", None)
    window = getattr(outcome, "window", None)
    window_name = getattr(window, "name", None)
    collected_at = getattr(window, "collected_at", None)
    if not all(isinstance(value, str) and value for value in (decision_ref, evaluation_target, symbol)):
        return None
    ref: dict[str, object] = {
        "decision_ref": decision_ref,
        "evaluation_target": evaluation_target,
        "symbol": symbol,
    }
    if isinstance(window_name, str) and window_name:
        ref["window_name"] = window_name
    if isinstance(collected_at, str) and collected_at:
        ref["collected_at"] = collected_at
    return ref


def _to_float_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _outcome_plan_inputs_for_trace(
    *,
    trace: dict[str, object],
    summary: dict[str, object],
    plan_run: dict[str, object],
    payload: dict[str, object],
    generated_at: datetime,
    horizon_seconds_value: float,
    plan_input_cls,
) -> list[object]:
    plan_id = str(plan_run.get("plan_id") or trace.get("final_plan_id") or trace.get("trace_id") or "")
    trace_id = str(trace.get("trace_id") or summary.get("trace_id") or "")
    symbol = str(trace.get("symbol") or summary.get("symbol") or "")
    parsed_plan = _mapping(plan_run.get("parsed_plan")) or _mapping(payload.get("parsed_plan"))
    inputs: list[object] = []
    legacy = _plan_outcome_input(
        plan_input_cls=plan_input_cls,
        decision_ref=f"{plan_id or trace_id}:legacy_final",
        evaluation_target="legacy_final",
        symbol=symbol,
        parsed_plan=parsed_plan,
        generated_at=generated_at,
        horizon_seconds_value=horizon_seconds_value,
    )
    if legacy is not None:
        inputs.append(legacy)
    candidate_plan = _candidate_plan_from_payload(payload)
    candidate = _plan_outcome_input(
        plan_input_cls=plan_input_cls,
        decision_ref=f"{plan_id or trace_id}:swarm_candidate_final",
        evaluation_target="swarm_candidate_final",
        symbol=symbol,
        parsed_plan=candidate_plan,
        generated_at=generated_at,
        horizon_seconds_value=horizon_seconds_value,
    )
    if candidate is not None:
        inputs.append(candidate)
    if inputs and symbol:
        inputs.append(
            plan_input_cls(
                decision_ref=f"{plan_id or trace_id}:hold_no_trade",
                evaluation_target="hold_no_trade",
                symbol=symbol,
                action="no trade",
                probability=0.5,
                entry_price=None,
                stop_price=None,
                target_1=None,
                target_2=None,
                generated_at=generated_at,
                horizon_seconds=horizon_seconds_value,
            )
        )
    return inputs


def _plan_outcome_input(
    *,
    plan_input_cls,
    decision_ref: str,
    evaluation_target: str,
    symbol: str,
    parsed_plan: dict[str, object],
    generated_at: datetime,
    horizon_seconds_value: float,
) -> object | None:
    action = parsed_plan.get("main_action")
    if not action or not symbol:
        return None
    return plan_input_cls(
        decision_ref=decision_ref,
        evaluation_target=evaluation_target,
        symbol=symbol,
        action=str(action),
        probability=_to_float_or_none(parsed_plan.get("probability")),
        entry_price=_to_float_or_none(parsed_plan.get("entry_trigger")),
        stop_price=_to_float_or_none(parsed_plan.get("stop_price")),
        target_1=_to_float_or_none(parsed_plan.get("target_1")),
        target_2=_to_float_or_none(parsed_plan.get("target_2")),
        generated_at=generated_at,
        horizon_seconds=horizon_seconds_value,
    )


def _candidate_plan_from_payload(payload: dict[str, object]) -> dict[str, object]:
    sidecar = _mapping(payload.get("candidate_final_decision"))
    if (
        sidecar.get("artifact_type") != "candidate_final_decision"
        or sidecar.get("mode") != "candidate_final_sidecar"
        or sidecar.get("decision_effect") != "none"
        or sidecar.get("production_final_input") is not False
        or sidecar.get("input_gate_passed") is not True
        or sidecar.get("error") is not None
    ):
        return {}
    summary = _mapping(sidecar.get("candidate_final_summary"))
    if summary:
        return summary
    return _json_mapping(sidecar.get("raw_candidate_decision"))


def _mapping(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _trace_outcome_eligible(trace: dict[str, object], plan_run: dict[str, object]) -> bool:
    if trace.get("status") not in {"allowed", "blocked"}:
        return False
    if not trace.get("ended_at"):
        return False
    if not trace.get("final_plan_id"):
        return False
    if not plan_run.get("plan_id"):
        return False
    if plan_run.get("plan_id") != trace.get("final_plan_id"):
        return False
    if plan_run.get("status") not in {"allowed", "blocked"}:
        return False
    return True


def _json_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


if __name__ == "__main__":
    raise SystemExit(main())
