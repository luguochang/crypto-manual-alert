from __future__ import annotations

import argparse
import json
from datetime import timedelta

from .config import ConfigError, load_config
from .journal import Journal
from .notifier import BarkNotificationSink
from .runner import PlanRunner, journal_path, plan_to_json
from .scheduler import JobLock, run_scheduler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jiami-alert")
    parser.add_argument("--config", action="append", default=["config/default.yaml"], help="YAML config path; can be repeated")
    sub = parser.add_subparsers(dest="command", required=True)

    run_once = sub.add_parser("run-once")
    run_once.add_argument("--symbol", default="ETH-USDT-SWAP")

    sub.add_parser("show-config")

    test_bark = sub.add_parser("test-bark")
    test_bark.add_argument("--message", default="Jiami alert Bark test. No trading action.")

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

    args = parser.parse_args(argv)
    try:
        config = load_config(*args.config)
    except ConfigError as exc:
        print(f"CONFIG_ERROR: {exc}")
        return 2

    journal = Journal(journal_path(config))

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
        url = f"{config.notification.bark_base_url.rstrip('/')}/{quote(key)}/{quote('Jiami alert test')}/{quote(args.message)}"
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
    if args.command == "run-once":
        runner = PlanRunner(config, journal)
        plan, verdict = runner.run_once(args.symbol)
        print(plan_to_json(plan, verdict))
        return 0 if verdict.allowed else 3
    if args.command == "scheduler":
        lock = JobLock(journal, "plan-run", ttl=timedelta(seconds=config.scheduler.lock_ttl_seconds))
        runner = PlanRunner(config, journal)

        def job() -> None:
            plan, verdict = runner.run_once(args.symbol)
            print(plan_to_json(plan, verdict))

        run_scheduler(
            config.scheduler.interval_seconds,
            lock,
            job,
            run_on_start=config.scheduler.run_on_start,
            max_iterations=config.scheduler.max_iterations,
        )
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
