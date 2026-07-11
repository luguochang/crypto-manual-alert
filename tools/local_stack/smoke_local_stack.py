from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
LOG_DIR = ROOT / "data" / "dev-server"
TMP_DIR = ROOT / ".tmp" / "smoke"
API_PORT = 8010
FRONTEND_PORT = 3001
MOCK_OPENAI_PORT = 8011
MOCK_OKX_PORT = 8012
MOCK_ERROR_API_PORT = 8013
API_BASE = f"http://127.0.0.1:{API_PORT}"
FRONTEND_BASE = f"http://127.0.0.1:{FRONTEND_PORT}"
MOCK_OPENAI_BASE = f"http://127.0.0.1:{MOCK_OPENAI_PORT}"
MOCK_OKX_BASE = f"http://127.0.0.1:{MOCK_OKX_PORT}"
MOCK_ERROR_API_BASE = f"http://127.0.0.1:{MOCK_ERROR_API_PORT}"
MOCK_OUTCOME_DECISION_REF = "mocked-outcome-seed"


class SmokeSkipped(RuntimeError):
    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__(str(payload.get("skip_reason") or "smoke skipped"))
        self.payload = payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start local API/frontend and smoke-test the manual-alert workflow.")
    parser.add_argument("--keep-running", action="store_true", help="Keep both dev servers running after checks pass.")
    parser.add_argument(
        "--with-bark",
        action="store_true",
        help="Send a real Bark notification during the manual run. Requires BARK_DEVICE_KEY.",
    )
    parser.add_argument(
        "--with-real-llm",
        action="store_true",
        help="Use the configured OpenAI-compatible decision engine. Requires OPENAI_BASE_URL, OPENAI_MODEL, and OPENAI_API_KEY.",
    )
    parser.add_argument(
        "--with-mock-llm",
        action="store_true",
        help="Use a local OpenAI-compatible mock server to exercise the real LLM code path without external secrets.",
    )
    parser.add_argument(
        "--with-real-market",
        action="store_true",
        help="Use the configured public market provider instead of fixture market data. Does not require trade keys.",
    )
    parser.add_argument(
        "--with-actionable-staging",
        action="store_true",
        help="Use a local OKX mock plus no-active-event assertion to prove the manual-review allowed path.",
    )
    parser.add_argument(
        "--prod-actionable",
        action="store_true",
        help="Run the real external actionable proof: real LLM, real OKX public, Bark, and event readiness. Missing readiness emits a structured skip JSON.",
    )
    parser.add_argument(
        "--fail-on-skip",
        action="store_true",
        help="Return a non-zero exit code when a readiness skip occurs. Use with --prod-actionable for release gates.",
    )
    parser.add_argument(
        "--seed-mock-outcome",
        action="store_true",
        help="Seed one explicit mocked eval outcome and verify it renders. Visibility proof only; not a financial-quality proof.",
    )
    parser.add_argument(
        "--collect-outcomes-fixture",
        action="store_true",
        help=(
            "Seed a matured historical alert, run the real collect-outcomes CLI against the local OKX mock, "
            "and verify exchange-native outcome visibility. Local wiring proof only; not production financial quality."
        ),
    )
    args = parser.parse_args(argv)
    if args.with_real_llm and args.with_mock_llm:
        parser.error("--with-real-llm and --with-mock-llm are mutually exclusive")
    if args.with_actionable_staging and args.with_real_market:
        parser.error("--with-actionable-staging already uses okx_public via a local mock; do not combine it with --with-real-market")
    if args.prod_actionable and (args.with_mock_llm or args.with_actionable_staging):
        parser.error("--prod-actionable cannot use local mock LLM or local OKX mock")
    if args.prod_actionable and args.seed_mock_outcome:
        parser.error("--prod-actionable cannot seed mocked eval outcomes")
    if args.prod_actionable and args.collect_outcomes_fixture:
        parser.error("--prod-actionable cannot use local collected outcome fixtures")
    notification_requested = args.with_bark or args.prod_actionable
    api_data_dir = TMP_DIR / "data" if args.seed_mock_outcome or args.collect_outcomes_fixture else None

    _ensure_port_free(API_PORT)
    _ensure_port_free(FRONTEND_PORT)
    if args.with_mock_llm:
        _ensure_port_free(MOCK_OPENAI_PORT)
    if args.with_actionable_staging or args.collect_outcomes_fixture:
        _ensure_port_free(MOCK_OKX_PORT)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    if api_data_dir is not None:
        _reset_smoke_data_dir(api_data_dir)

    api_process: subprocess.Popen[bytes] | None = None
    frontend_process: subprocess.Popen[bytes] | None = None
    mock_openai_process: subprocess.Popen[bytes] | None = None
    mock_okx_process: subprocess.Popen[bytes] | None = None
    try:
        if args.with_mock_llm:
            mock_openai_process = _start_mock_openai()
            _wait_for_json(f"{MOCK_OPENAI_BASE}/health", "mock OpenAI health")
        if args.with_actionable_staging or args.collect_outcomes_fixture:
            mock_okx_process = _start_mock_okx()
            _wait_for_json(f"{MOCK_OKX_BASE}/health", "mock OKX health")
        api_process = _start_api(
            notification_enabled=args.with_bark or args.prod_actionable,
            real_llm_enabled=args.with_real_llm or args.prod_actionable,
            mock_llm_enabled=args.with_mock_llm,
            real_market_enabled=(
                args.with_real_market
                or args.with_actionable_staging
                or args.collect_outcomes_fixture
                or args.prod_actionable
            ),
            actionable_staging_enabled=args.with_actionable_staging or args.collect_outcomes_fixture,
            prod_actionable_enabled=args.prod_actionable,
            data_dir=api_data_dir,
        )
        _wait_for_json(f"{API_BASE}/api/system/health", "API health")
        mock_outcome = (
            _seed_mock_eval_outcome(api_data_dir)
            if args.seed_mock_outcome and api_data_dir is not None
            else None
        )
        collected_outcomes = (
            _collect_exchange_native_outcome_fixture(api_data_dir)
            if args.collect_outcomes_fixture and api_data_dir is not None
            else None
        )

        frontend_process = _start_frontend()
        _wait_for_text(FRONTEND_BASE, "frontend home")

        _assert_cors_preflight()
        _assert_frontend_page("/manual-run")
        _assert_frontend_page("/runs")
        _assert_frontend_page("/eval")
        _assert_frontend_page("/eval?tab=quality")
        if mock_outcome is not None:
            _assert_eval_quality_outcome_visible()
        if collected_outcomes is not None:
            _assert_collected_exchange_outcome_visible()
        trace_id = _assert_manual_run()
        _assert_run_list_contains(trace_id)
        detail = _assert_run_detail(trace_id)
        if args.with_real_llm or args.with_mock_llm or args.prod_actionable:
            _assert_real_llm_detail(detail)
        if args.with_real_llm or args.with_mock_llm:
            _assert_llm_payload_redaction(trace_id)
        if args.with_mock_llm:
            _assert_mock_llm_detail(detail)
        if args.with_real_market or args.prod_actionable:
            _assert_real_market_detail(detail)
        if args.prod_actionable:
            _assert_actionable_staging_detail(detail)
        if args.with_actionable_staging or args.collect_outcomes_fixture:
            _assert_actionable_staging_detail(detail)
        if notification_requested and api_data_dir is not None:
            notification_result = _assert_notification_sent(trace_id, data_dir=api_data_dir)
        elif notification_requested:
            notification_result = _assert_notification_sent(trace_id)
        else:
            notification_result = {"enabled": False}
        trace = detail.get("data", {}).get("trace", {})
        _assert_frontend_summary_page(trace_id, allowed=trace.get("allowed") is True)
        _assert_frontend_agent_audit_page(trace_id)

        config_snapshot = _wait_for_json(f"{API_BASE}/api/system/config", "API config").get("data", {})
        print(
            json.dumps(
                {
                    "ok": True,
                    "smoke_profile": _smoke_profile(
                        real_llm_enabled=args.with_real_llm,
                        mock_llm_enabled=args.with_mock_llm,
                        real_market_enabled=args.with_real_market,
                        actionable_staging_enabled=args.with_actionable_staging,
                        collect_outcomes_fixture_enabled=args.collect_outcomes_fixture,
                        prod_actionable_enabled=args.prod_actionable,
                    ),
                    "api": API_BASE,
                    "frontend": FRONTEND_BASE,
                    "mock_openai": MOCK_OPENAI_BASE if args.with_mock_llm else None,
                    "mock_okx": MOCK_OKX_BASE if args.with_actionable_staging or args.collect_outcomes_fixture else None,
                    **_local_proof_boundary(prod_actionable_enabled=args.prod_actionable),
                    "trace_id": trace_id,
                    "allowed": trace.get("allowed"),
                    "decision_engine": config_snapshot.get("decision", {}).get("engine"),
                    "decision_model": config_snapshot.get("decision", {}).get("openai_model"),
                    "market_provider": config_snapshot.get("market_data", {}).get("provider"),
                    "macro_event_provider": config_snapshot.get("macro_event", {}).get("provider"),
                    "manual_execution_required": config_snapshot.get("trading", {}).get("manual_execution_required"),
                    "auto_order_enabled": config_snapshot.get("trading", {}).get("auto_order_enabled"),
                    "notification": notification_result,
                    "notification_enabled": notification_requested,
                    "mock_outcome_seeded": mock_outcome is not None,
                    "mock_outcome_decision_ref": mock_outcome.get("decision_ref") if mock_outcome else None,
                    "mock_outcome_quality_scope": (
                        "visibility_only_not_financial_quality" if mock_outcome is not None else None
                    ),
                    "outcome_collection_profile": (
                        "local_mock_okx_collector_wiring_only" if collected_outcomes is not None else None
                    ),
                    "collected_exchange_native_outcomes": (
                        collected_outcomes.get("collected") if isinstance(collected_outcomes, dict) else None
                    ),
                    "real_financial_quality_proven": False if collected_outcomes is not None else None,
                    "real_llm_enabled": args.with_real_llm,
                    "mock_llm_enabled": args.with_mock_llm,
                    "real_market_enabled": args.with_real_market,
                    "actionable_staging_enabled": args.with_actionable_staging,
                    "collect_outcomes_fixture_enabled": args.collect_outcomes_fixture,
                    "prod_actionable_enabled": args.prod_actionable,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if args.keep_running:
            print("Servers are still running. Stop them with Ctrl+C in this terminal or run tools/local_stack/stop_local_stack.py.")
            print(json.dumps({"api_pid": api_process.pid, "frontend_pid": frontend_process.pid}, indent=2))
            while True:
                time.sleep(3600)
        return 0
    except SmokeSkipped as exc:
        if exc.payload.get("smoke_profile") == "prod_actionable":
            exc.payload.update(
                {
                    key: value
                    for key, value in _local_proof_boundary(prod_actionable_enabled=True).items()
                    if key not in exc.payload
                }
            )
        exc.payload.setdefault("exit_semantics", "fail_on_skip" if args.fail_on_skip else "skip_exit_0")
        print(json.dumps(exc.payload, ensure_ascii=False, indent=2))
        return 2 if args.fail_on_skip else 0
    finally:
        if not args.keep_running:
            for process in (frontend_process, api_process, mock_openai_process, mock_okx_process):
                if process is not None:
                    _stop_process(process)


def _start_api(
    *,
    notification_enabled: bool,
    real_llm_enabled: bool,
    mock_llm_enabled: bool,
    real_market_enabled: bool,
    actionable_staging_enabled: bool,
    prod_actionable_enabled: bool = False,
    data_dir: Path | None = None,
) -> subprocess.Popen[bytes]:
    env = _build_api_env(
        tmp_dir=TMP_DIR,
        data_dir=data_dir,
        notification_enabled=notification_enabled,
        real_llm_enabled=real_llm_enabled,
        mock_llm_enabled=mock_llm_enabled,
        real_market_enabled=real_market_enabled,
        actionable_staging_enabled=actionable_staging_enabled,
        prod_actionable_enabled=prod_actionable_enabled,
    )
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "crypto_manual_alert.api.app:app", "--host", "127.0.0.1", "--port", str(API_PORT)],
        cwd=ROOT,
        env=env,
        stdout=(LOG_DIR / "api-smoke.out.log").open("wb"),
        stderr=(LOG_DIR / "api-smoke.err.log").open("wb"),
    )


def _reset_smoke_data_dir(data_dir: Path) -> None:
    if data_dir.exists():
        shutil.rmtree(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)


def _build_api_env(
    *,
    tmp_dir: Path,
    data_dir: Path | None = None,
    notification_enabled: bool,
    real_llm_enabled: bool = False,
    mock_llm_enabled: bool = False,
    real_market_enabled: bool = False,
    actionable_staging_enabled: bool = False,
    prod_actionable_enabled: bool = False,
    diagnostic_routes_enabled: bool | None = None,
    base_env: dict[str, str] | None = None,
) -> dict[str, str]:
    """构造本地 API 环境。

    默认 fixture/无通知，只有显式参数才访问真实 LLM、真实行情或 Bark。
    """
    if real_llm_enabled and mock_llm_enabled:
        raise RuntimeError("real_llm_enabled and mock_llm_enabled are mutually exclusive.")
    if prod_actionable_enabled and (mock_llm_enabled or actionable_staging_enabled):
        raise RuntimeError("prod_actionable_enabled cannot use local mock dependencies.")
    env = dict(base_env or os.environ)
    if prod_actionable_enabled:
        _raise_if_prod_actionable_not_ready(env)
        notification_enabled = True
        real_llm_enabled = True
        real_market_enabled = True
    env["PYTHONPATH"] = str(ROOT / "src")
    env["TMP"] = str(tmp_dir)
    env["TEMP"] = str(tmp_dir)
    diagnostics_enabled = (not prod_actionable_enabled) if diagnostic_routes_enabled is None else diagnostic_routes_enabled
    env["DIAGNOSTIC_ROUTES_ENABLED"] = "true" if diagnostics_enabled else "false"
    if data_dir is not None:
        env["DATA_DIR"] = str(data_dir)
    env["MARKET_DATA_PROVIDER"] = env.get("MARKET_DATA_PROVIDER", "fixture") if real_market_enabled else "fixture"
    llm_enabled = real_llm_enabled or mock_llm_enabled
    env["DECISION_ENGINE"] = env.get("DECISION_ENGINE", "openai_compatible") if llm_enabled else "fixture"
    env["NOTIFICATION_ENABLED"] = "true" if notification_enabled else "false"
    if notification_enabled and not env.get("BARK_DEVICE_KEY"):
        raise RuntimeError("BARK_DEVICE_KEY is required when --with-bark is used.")
    if mock_llm_enabled:
        env["OPENAI_BASE_URL"] = MOCK_OPENAI_BASE
        env["OPENAI_MODEL"] = "mock-crypto-plan"
        env["OPENAI_API_KEY_ENV"] = "OPENAI_API_KEY"
        env["OPENAI_API_KEY"] = "local-mock-openai-key"
    if real_llm_enabled:
        _require_env(env, "OPENAI_BASE_URL", "--with-real-llm")
        _require_env(env, "OPENAI_MODEL", "--with-real-llm")
        key_env = env.get("OPENAI_API_KEY_ENV", "OPENAI_API_KEY")
        _require_env(env, key_env, "--with-real-llm")
    if real_market_enabled:
        env.setdefault("MARKET_DATA_PROVIDER", "okx_public")
        if env["MARKET_DATA_PROVIDER"] == "fixture":
            env["MARKET_DATA_PROVIDER"] = "okx_public"
    if prod_actionable_enabled:
        env["MARKET_DATA_PROVIDER"] = "okx_public"
        env["CANDIDATE_SIDECAR_MODE"] = "disabled"
        env.setdefault("MACRO_EVENT_PROVIDER", "no_active_event")
    if actionable_staging_enabled:
        env["MARKET_DATA_PROVIDER"] = "okx_public"
        env["MARKET_DATA_OKX_BASE_URL"] = MOCK_OKX_BASE
        env["MACRO_EVENT_PROVIDER"] = "no_active_event"
    return env


def _seed_mock_eval_outcome(data_dir: str | Path) -> dict[str, Any]:
    """Seed one explicit mocked outcome into the eval sidecar store.

    This is only for local visual/e2e proof that the eval outcome UI can render
    a collected sample. It does not touch the production journal and is not a
    real financial-quality proof.
    """

    src_path = str(ROOT / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    from crypto_manual_alert.eval.outcome_store import OutcomeStore
    from crypto_manual_alert.eval.outcomes import DecisionOutcome, OutcomeWindow
    from crypto_manual_alert.eval.runner import outcome_store_path

    now = datetime.now(timezone.utc).isoformat()
    window = OutcomeWindow(
        name="mocked-6h",
        symbol="ETH-USDT-SWAP",
        interval="1H",
        source_type="mocked_outcome",
        window_start="2026-07-08T00:00:00+00:00",
        window_end="2026-07-08T06:00:00+00:00",
        collected_at=now,
        open_price=3450.0,
        high_price=3568.0,
        low_price=3428.0,
        close_price=3542.0,
        matured=True,
    )
    outcome = DecisionOutcome(
        decision_ref=MOCK_OUTCOME_DECISION_REF,
        evaluation_target="legacy_final",
        symbol="ETH-USDT-SWAP",
        action="trigger long",
        probability=0.62,
        entry_price=3460.0,
        stop_price=3400.0,
        target_1=3600.0,
        target_2=3720.0,
        regime="mocked_local_visual_proof",
        window=window,
    )
    OutcomeStore(outcome_store_path(data_dir)).upsert_outcomes([outcome])
    return outcome.to_public_dict()


def _collect_exchange_native_outcome_fixture(data_dir: str | Path) -> dict[str, Any]:
    """Run real collect-outcomes against a seeded local journal and mock OKX.

    This proves the collector wiring from production journal -> CLI -> OKX history
    candles -> eval sidecar -> API/UI. Because OKX is a local mock, it is not a
    production financial-quality proof.
    """

    src_path = str(ROOT / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    from crypto_manual_alert.storage.journal import Journal

    data_path = Path(data_dir)
    journal = Journal(data_path / "crypto-alert.db")
    trace_id = "smoke-collected-outcome-trace"
    plan_id = "smoke-collected-outcome-plan"
    journal.append_trace(
        trace_id=trace_id,
        created_at="2026-07-06T00:00:00+00:00",
        run_type="manual",
        symbol="ETH-USDT-SWAP",
        horizon="6h",
        status="running",
        metadata={"source": "local_collect_outcomes_fixture"},
    )
    journal.finish_trace(
        trace_id=trace_id,
        ended_at="2026-07-06T06:01:00+00:00",
        status="allowed",
        final_plan_id=plan_id,
        final_action="trigger long",
        allowed=True,
        metadata={"source": "local_collect_outcomes_fixture"},
    )
    journal.append_plan_run(
        plan_id,
        "allowed",
        {
            "trace_id": trace_id,
            "parsed_plan": {
                "instrument": "ETH-USDT-SWAP",
                "main_action": "trigger long",
                "probability": 0.61,
                "entry_trigger": 3500.0,
                "stop_price": 3420.0,
                "target_1": 3600.0,
                "target_2": 3720.0,
            },
            "candidate_final_decision": {
                "artifact_type": "candidate_final_decision",
                "mode": "candidate_final_sidecar",
                "decision_effect": "none",
                "production_final_input": False,
                "input_gate_passed": True,
                "input_ref": f"trace:{trace_id}:pre_final_decision_input",
                "input_hash": "sha256:local-collect-outcomes-fixture",
                "raw_candidate_decision": json.dumps(
                    {
                        "instrument": "ETH-USDT-SWAP",
                        "main_action": "trigger short",
                        "probability": 0.55,
                        "entry_trigger": 3490.0,
                        "stop_price": 3560.0,
                        "target_1": 3380.0,
                        "target_2": 3300.0,
                    },
                    ensure_ascii=False,
                ),
                "error": None,
            },
        },
    )
    with journal.connect() as conn:
        conn.execute("UPDATE plan_runs SET created_at = ? WHERE plan_id = ?", ("2026-07-06T00:00:00+00:00", plan_id))

    config_path = TMP_DIR / "collect-outcomes-fixture.yaml"
    config_path.write_text(
        "\n".join(
            [
                "app:",
                f"  data_dir: {str(data_path).replace(os.sep, '/')}",
                "market_data:",
                "  provider: okx_public",
                f"  okx_base_url: {MOCK_OKX_BASE}",
                "  candle_bar: 1H",
                "",
            ]
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["TMP"] = str(TMP_DIR)
    env["TEMP"] = str(TMP_DIR)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "crypto_manual_alert.cli",
            "--config",
            str(config_path),
            "collect-outcomes",
            "--limit",
            "5",
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            "collect-outcomes fixture command failed: "
            f"returncode={result.returncode} stdout={result.stdout!r} stderr={result.stderr!r}"
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"collect-outcomes fixture returned non-JSON stdout: {result.stdout!r}") from exc
    _assert_collect_outcomes_fixture_payload(payload, plan_id=plan_id)
    return payload


def _assert_collect_outcomes_fixture_payload(payload: Any, *, plan_id: str) -> None:
    if not isinstance(payload, dict):
        raise AssertionError(f"collect-outcomes fixture output must be a JSON object: {payload}")
    expected_counts = {"collected": 3, "skipped": 0, "limit": 5}
    for key, expected in expected_counts.items():
        if payload.get(key) != expected:
            raise AssertionError(f"collect-outcomes fixture output mismatch: {payload}")
    refs = payload.get("collected_refs")
    if not isinstance(refs, list):
        raise AssertionError(f"collect-outcomes fixture missing collected_refs: {payload}")
    expected_refs = [
        (f"{plan_id}:legacy_final", "legacy_final"),
        (f"{plan_id}:swarm_candidate_final", "swarm_candidate_final"),
        (f"{plan_id}:hold_no_trade", "hold_no_trade"),
    ]
    actual_refs = []
    for ref in refs:
        if not isinstance(ref, dict):
            raise AssertionError(f"collect-outcomes fixture collected_refs must contain objects: {payload}")
        actual_refs.append((ref.get("decision_ref"), ref.get("evaluation_target")))
        if ref.get("symbol") != "ETH-USDT-SWAP":
            raise AssertionError(f"collect-outcomes fixture ref must use ETH-USDT-SWAP: {ref}")
        if ref.get("window_name") != "ETH-USDT-SWAP:21600s":
            raise AssertionError(f"collect-outcomes fixture ref must use the 6h window: {ref}")
        collected_at = ref.get("collected_at")
        if not isinstance(collected_at, str) or not _parse_timezone_aware_datetime(collected_at):
            raise AssertionError(f"collect-outcomes fixture ref collected_at must be timezone-aware: {ref}")
    if actual_refs != expected_refs:
        raise AssertionError(f"collect-outcomes fixture collected_refs mismatch: {payload}")


def _parse_timezone_aware_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _raise_if_prod_actionable_not_ready(env: dict[str, str]) -> None:
    missing: list[str] = []
    for name in ("BARK_DEVICE_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"):
        if not env.get(name):
            missing.append(name)
    key_env = env.get("OPENAI_API_KEY_ENV", "OPENAI_API_KEY")
    if not env.get(key_env):
        missing.append(key_env)
    macro_provider = env.get("MACRO_EVENT_PROVIDER")
    if macro_provider != "no_active_event":
        missing.append("MACRO_EVENT_PROVIDER=no_active_event")
    elif not all(env.get(name) for name in _MACRO_EVENT_ASSERTION_METADATA_ENV_NAMES):
        missing.extend([name for name in _MACRO_EVENT_ASSERTION_METADATA_ENV_NAMES if not env.get(name)])
    if missing:
        raise SmokeSkipped(
            {
                "ok": False,
                "smoke_profile": "prod_actionable",
                "skip_reason": "missing_readiness",
                "missing": missing,
                "manual_execution_required": True,
                "auto_order_enabled": False,
                **_local_proof_boundary(prod_actionable_enabled=True),
            }
        )
    unsafe = _prod_actionable_unsafe_endpoint_reasons(env)
    if unsafe:
        raise SmokeSkipped(
            {
                "ok": False,
                "smoke_profile": "prod_actionable",
                "skip_reason": "unsafe_readiness",
                "unsafe": unsafe,
                "manual_execution_required": True,
                "auto_order_enabled": False,
                **_local_proof_boundary(prod_actionable_enabled=True),
            }
        )


_MACRO_EVENT_ASSERTION_METADATA_ENV_NAMES = (
    "MACRO_EVENT_OPERATOR_REF",
    "MACRO_EVENT_CONFIRMED_AT",
    "MACRO_EVENT_SOURCE_REF",
    "MACRO_EVENT_ASSERTION_HORIZON",
    "MACRO_EVENT_VALID_UNTIL",
)


def _prod_actionable_unsafe_endpoint_reasons(env: dict[str, str]) -> list[str]:
    reasons: list[str] = []
    if not _is_public_https_endpoint(env.get("OPENAI_BASE_URL", "")):
        reasons.append("OPENAI_BASE_URL must be a public https endpoint for prod-actionable")
    if env.get("OPENAI_MODEL", "").strip().lower().startswith("mock"):
        reasons.append("OPENAI_MODEL must not be a mock model for prod-actionable")
    okx_base = env.get("MARKET_DATA_OKX_BASE_URL")
    if okx_base and okx_base.rstrip("/") != "https://www.okx.com":
        reasons.append("MARKET_DATA_OKX_BASE_URL must be unset or https://www.okx.com for prod-actionable")
    valid_until = env.get("MACRO_EVENT_VALID_UNTIL", "").strip()
    if valid_until:
        try:
            valid_until_dt = datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
        except ValueError:
            reasons.append("MACRO_EVENT_VALID_UNTIL must be an ISO-8601 datetime with timezone for prod-actionable")
        else:
            if valid_until_dt.tzinfo is None:
                reasons.append("MACRO_EVENT_VALID_UNTIL must include timezone for prod-actionable")
            elif valid_until_dt <= datetime.now(timezone.utc):
                reasons.append("MACRO_EVENT_VALID_UNTIL must be in the future for prod-actionable")
    return reasons


def _is_public_https_endpoint(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not any([ip.is_loopback, ip.is_private, ip.is_link_local, ip.is_reserved, ip.is_multicast, ip.is_unspecified])


def _start_mock_openai() -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [
            sys.executable,
            str(ROOT / "tools" / "local_stack" / "mock_openai_server.py"),
            "--host",
            "127.0.0.1",
            "--port",
            str(MOCK_OPENAI_PORT),
        ],
        cwd=ROOT,
        stdout=(LOG_DIR / "mock-openai-smoke.out.log").open("wb"),
        stderr=(LOG_DIR / "mock-openai-smoke.err.log").open("wb"),
    )


def _start_mock_okx() -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [
            sys.executable,
            str(ROOT / "tools" / "local_stack" / "mock_okx_server.py"),
            "--host",
            "127.0.0.1",
            "--port",
            str(MOCK_OKX_PORT),
        ],
        cwd=ROOT,
        stdout=(LOG_DIR / "mock-okx-smoke.out.log").open("wb"),
        stderr=(LOG_DIR / "mock-okx-smoke.err.log").open("wb"),
    )


def _require_env(env: dict[str, str], name: str, flag: str) -> None:
    if not env.get(name):
        raise RuntimeError(f"{name} is required when {flag} is used.")


def _start_frontend() -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env["NEXT_PUBLIC_API_BASE_URL"] = API_BASE
    npm = "npm.cmd" if os.name == "nt" else "npm"
    return subprocess.Popen(
        [npm, "run", "dev", "--", "--hostname", "127.0.0.1", "--port", str(FRONTEND_PORT)],
        cwd=FRONTEND,
        env=env,
        stdout=(LOG_DIR / "frontend-smoke.out.log").open("wb"),
        stderr=(LOG_DIR / "frontend-smoke.err.log").open("wb"),
    )


def _assert_cors_preflight() -> None:
    request = Request(
        f"{API_BASE}/api/runs/manual",
        method="OPTIONS",
        headers={
            "Origin": FRONTEND_BASE,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    with urlopen(request, timeout=10) as response:
        headers = {key.lower(): value for key, value in response.headers.items()}
        if response.status != 200:
            raise AssertionError(f"CORS preflight returned {response.status}")
        if headers.get("access-control-allow-origin") != FRONTEND_BASE:
            raise AssertionError(f"CORS origin mismatch: {headers}")


def _assert_frontend_page(path: str) -> None:
    body = _wait_for_text(f"{FRONTEND_BASE}{path}", f"frontend {path}")
    _assert_not_raw_json_page(body, f"Frontend page {path}")
    if "__next" not in body and "Crypto" not in body:
        raise AssertionError(f"Frontend page {path} did not look like a Next.js page")
    visible_text = _visible_html_text(body)
    for required in _required_frontend_texts(path):
        if required not in visible_text:
            raise AssertionError(f"Frontend page {path} missing {required}")
    if path == "/eval" and "金融质量" not in visible_text:
        raise AssertionError("Frontend default eval page must open the financial quality panel")
    if path == "/eval?tab=quality" and "金融质量" not in body:
        raise AssertionError("Frontend eval page missing financial quality panel")


def _assert_eval_quality_outcome_visible() -> None:
    body = _wait_for_json(f"{API_BASE}/api/eval/outcomes", "API eval outcomes")
    if not body.get("ok"):
        raise AssertionError(f"eval outcomes API failed: {body}")
    items = body.get("data", {}).get("items", [])
    if not isinstance(items, list):
        raise AssertionError(f"eval outcomes API returned invalid items: {body}")
    seeded = next(
        (item for item in items if isinstance(item, dict) and item.get("decision_ref") == MOCK_OUTCOME_DECISION_REF),
        None,
    )
    if seeded is None:
        raise AssertionError(f"eval outcomes API missing {MOCK_OUTCOME_DECISION_REF}: {body}")
    window = seeded.get("window", {}) if isinstance(seeded.get("window"), dict) else {}
    if window.get("source_type") != "mocked_outcome":
        raise AssertionError(f"mock outcome must use source_type=mocked_outcome: {seeded}")
    if window.get("unscored_reason") != "price_source_not_exchange_native":
        raise AssertionError(f"mock outcome window must stay unscored as mocked data: {seeded}")
    expected = {
        "evaluation_target": "legacy_final",
        "symbol": "ETH-USDT-SWAP",
        "can_score": False,
        "unscored_reason": "price_source_not_exchange_native",
    }
    for key, value in expected.items():
        if seeded.get(key) != value:
            raise AssertionError(f"mock outcome {key} mismatch: expected {value!r}, got {seeded.get(key)!r}")

    html = _wait_for_text(f"{FRONTEND_BASE}/eval?tab=quality", "frontend eval quality outcome")
    _assert_not_raw_json_page(html, "Frontend eval quality page")
    visible_text = _visible_html_text(html)
    for text in (
        "样本 1",
        "最终建议链路",
        "ETH-USDT-SWAP",
    ):
        if text not in visible_text:
            raise AssertionError(f"Frontend eval quality page missing mocked outcome text {text}")
    for text in ("不可评分", "价格不是交易所原生样本", "本地展示样本"):
        if text not in visible_text:
            raise AssertionError(f"Frontend eval quality page missing mocked outcome unscored explanation {text}")
    for text in (
        MOCK_OUTCOME_DECISION_REF,
        "mocked_outcome",
        "price_source_not_exchange_native",
        "legacy_final",
        "swarm_candidate_final",
        "baseline_reference",
        "no_trade",
    ):
        if text in visible_text:
            raise AssertionError(f"Frontend eval quality page leaked internal outcome code {text}")
    if "暂无 outcome 样本" in visible_text:
        raise AssertionError("Frontend eval quality page still shows the empty outcome-sample state")


def _assert_collected_exchange_outcome_visible() -> None:
    body = _wait_for_json(f"{API_BASE}/api/eval/outcomes", "API collected eval outcomes")
    if not body.get("ok"):
        raise AssertionError(f"eval outcomes API failed: {body}")
    items = body.get("data", {}).get("items", [])
    if not isinstance(items, list):
        raise AssertionError(f"eval outcomes API returned invalid items: {body}")
    by_target = {
        item.get("evaluation_target"): item
        for item in items
        if isinstance(item, dict) and str(item.get("decision_ref") or "").startswith("smoke-collected-outcome-plan:")
    }
    expected_targets = {"legacy_final", "swarm_candidate_final", "hold_no_trade"}
    if set(by_target) != expected_targets:
        raise AssertionError(f"collected exchange outcomes missing targets {expected_targets}: {items}")
    for target in ("legacy_final", "swarm_candidate_final"):
        item = by_target[target]
        window = item.get("window", {}) if isinstance(item.get("window"), dict) else {}
        if window.get("source_type") != "exchange_native":
            raise AssertionError(f"{target} outcome must use exchange_native source: {item}")
        if window.get("matured") is not True:
            raise AssertionError(f"{target} outcome must be matured: {item}")
        if window.get("can_score_execution_outcome") is not True:
            raise AssertionError(f"{target} window must be scoreable: {item}")
        if item.get("can_score") is not True:
            raise AssertionError(f"{target} trade outcome must be scoreable: {item}")
    hold = by_target["hold_no_trade"]
    hold_window = hold.get("window", {}) if isinstance(hold.get("window"), dict) else {}
    if hold_window.get("source_type") != "exchange_native":
        raise AssertionError(f"hold_no_trade outcome must still record exchange-native source: {hold}")
    if hold.get("can_score") is not False or hold.get("unscored_reason") != "no_trade_action":
        raise AssertionError(f"hold_no_trade must remain a non-trade advisory baseline: {hold}")

    html = _wait_for_text(f"{FRONTEND_BASE}/eval?tab=quality", "frontend collected eval quality outcome")
    _assert_not_raw_json_page(html, "Frontend eval quality page")
    visible_text = _visible_html_text(html)
    for text in (
        "样本 1",
        "最终建议链路",
        "候选建议链路",
        "不操作基线",
        "交易所原生样本",
        "ETH-USDT-SWAP",
        "可评分 2",
        "不可评分 1",
        "不操作基线，不纳入交易命中评分",
    ):
        if text not in visible_text:
            raise AssertionError(f"Frontend eval quality page missing collected outcome text {text}")
    for text in (
        "smoke-collected-outcome-plan",
        "exchange_native",
        "legacy_final",
        "swarm_candidate_final",
        "hold_no_trade",
        "no_trade_action",
        "decision_ref",
    ):
        if text in visible_text:
            raise AssertionError(f"Frontend eval quality page leaked collected outcome internal code {text}")


def _assert_manual_run() -> str:
    payload = json.dumps(
        {
            "symbol": "ETH-USDT-SWAP",
            "query": "评估 ETH 当前手动操作计划",
            "horizon": "6h/12h/1d/3d",
            "alert_channel": "bark",
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        f"{API_BASE}/api/runs/manual",
        data=payload,
        method="POST",
        headers={"content-type": "application/json", "Origin": FRONTEND_BASE},
    )
    with urlopen(request, timeout=30) as response:
        body = json.loads(response.read().decode("utf-8"))
    if not body.get("ok"):
        raise AssertionError(f"manual run failed: {body}")
    trace_id = body.get("data", {}).get("trace_id")
    if not trace_id:
        raise AssertionError(f"manual run missing trace_id: {body}")
    return str(trace_id)


def _assert_run_list_contains(trace_id: str) -> None:
    body = _wait_for_json(f"{API_BASE}/api/runs?limit=5", "API run list")
    items = body.get("data", {}).get("items", [])
    if not any(item.get("trace_id") == trace_id for item in items):
        raise AssertionError(f"run list does not contain trace_id={trace_id}: {body}")


def _assert_run_detail(trace_id: str) -> dict[str, Any]:
    body = _wait_for_json(f"{API_BASE}/api/runs/{trace_id}", "API run detail")
    if not body.get("ok"):
        raise AssertionError(f"run detail failed: {body}")
    if body.get("data", {}).get("trace", {}).get("trace_id") != trace_id:
        raise AssertionError(f"run detail trace mismatch: {body}")
    _assert_agent_audit_view(body)
    return body


def _assert_agent_audit_view(body: dict[str, Any]) -> None:
    audit = body.get("data", {}).get("plan_run", {}).get("agent_audit_view")
    if not isinstance(audit, dict) or audit.get("available") is not True:
        raise AssertionError(f"run detail missing available agent_audit_view: {body}")

    lead_tasks = audit.get("lead_plan", {}).get("tasks", [])
    if not isinstance(lead_tasks, list) or len(lead_tasks) < 7:
        raise AssertionError(f"agent_audit_view LeadPlan does not expose 7 tasks: {audit}")

    workers = audit.get("workers", [])
    if not isinstance(workers, list) or len(workers) < 7:
        raise AssertionError(f"agent_audit_view does not expose 7 worker results: {audit}")
    worker_names = {str(worker.get("agent_name")) for worker in workers if isinstance(worker, dict)}
    if "ExecutionRiskAgent" not in worker_names:
        raise AssertionError(f"agent_audit_view missing ExecutionRiskAgent: {worker_names}")

    decision_input = audit.get("decision_input")
    if not isinstance(decision_input, dict) or decision_input.get("mode") != "pre_final_candidate":
        raise AssertionError(f"agent_audit_view missing pre_final_candidate DecisionInput: {audit}")

    query_semantics = audit.get("query_semantics")
    if not isinstance(query_semantics, dict) or query_semantics.get("mode") != "audit_note":
        raise AssertionError(f"agent_audit_view missing audit_note query_semantics: {audit}")
    if query_semantics.get("drives_final_input") is not False:
        raise AssertionError(f"agent_audit_view query_semantics must not claim final input control: {audit}")

    gates = audit.get("gates")
    if not isinstance(gates, dict) or "production_control_gate" not in gates:
        raise AssertionError(f"agent_audit_view missing production_control_gate: {audit}")

    for key in (
        "tool_calls",
        "evidence_sources",
        "source_freshness",
        "conflict_edges",
    ):
        if not isinstance(audit.get(key), list):
            raise AssertionError(f"agent_audit_view missing list field {key}: {audit}")

    root_cause_graph = audit.get("root_cause_graph")
    if not isinstance(root_cause_graph, dict) or not isinstance(root_cause_graph.get("nodes"), list):
        raise AssertionError(f"agent_audit_view missing root_cause_graph nodes: {audit}")
    if not isinstance(root_cause_graph.get("edges"), list):
        raise AssertionError(f"agent_audit_view missing root_cause_graph edges: {audit}")

    input_lineage = audit.get("input_lineage")
    if not isinstance(input_lineage, dict) or input_lineage.get("production_final_input_mode") != "legacy_prompt":
        raise AssertionError(f"agent_audit_view missing legacy input_lineage: {audit}")

    release_eval_gate = audit.get("release_eval_gate")
    financial_gate = release_eval_gate.get("financial_quality_gate") if isinstance(release_eval_gate, dict) else None
    if not isinstance(financial_gate, dict) or financial_gate.get("status") != "not_configured":
        raise AssertionError(f"agent_audit_view missing financial quality gate status: {audit}")

    flow_steps = [step for step in audit.get("runtime_flow", []) if isinstance(step, dict)]
    flow_names = [str(step.get("name")) for step in flow_steps if step.get("name")]
    span_tree_steps = [step for step in flow_steps if step.get("source") == "span_tree_refs"]
    if not span_tree_steps:
        raise AssertionError(f"agent_audit_view runtime_flow must come from span_tree_refs: {flow_names}")
    for expected in (
        "market.fetch",
        "decision_input.pre_final",
        "shadow_swarm.worker",
        "decision.final",
        "parser.strict_json",
    ):
        if expected not in flow_names:
            raise AssertionError(f"agent_audit_view runtime_flow missing {expected}: {flow_names}")


def _assert_frontend_summary_page(trace_id: str, *, allowed: bool = False) -> None:
    body = _wait_for_text(f"{FRONTEND_BASE}/runs/{trace_id}", f"frontend run summary {trace_id}")
    _assert_not_raw_json_page(body, f"Frontend run summary {trace_id}")
    if "__next" not in body and "Crypto" not in body:
        raise AssertionError(f"Frontend run summary {trace_id} did not look like a Next.js page")
    visible_text = _visible_html_text(body)
    for text in (
        "提醒详情",
        "建议摘要",
        "当前持仓",
        "风险模式",
        "事实检查",
        "复核门槛",
        "通知",
    ):
        if text not in visible_text:
            raise AssertionError(f"Frontend summary page missing {text}")
    for forbidden in (
        "Trace ID",
        "Trace",
        "LLM 状态",
        "生产最终输入",
        "manual_execution_required",
        "legacy_prompt",
        "decision_input",
        "Worker Matrix",
    ):
        if forbidden in visible_text:
            raise AssertionError(f"Frontend summary page leaked {forbidden}")
    outcome_text = "可人工复核" if allowed else "已阻断：禁止作为操作依据"
    if outcome_text not in visible_text:
        raise AssertionError(f"Frontend summary page missing {outcome_text}")


def _visible_html_text(html: str) -> str:
    without_scripts = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    without_tags = re.sub(r"<[^>]+>", " ", without_scripts)
    return re.sub(r"\s+", " ", without_tags)


def _assert_not_raw_json_page(html: str, label: str) -> None:
    visible_text = _visible_html_text(html).strip()
    raw_text = html.strip()
    if raw_text.startswith(("{", "[")) or visible_text.startswith(("{", "[")):
        raise AssertionError(f"{label} rendered raw JSON instead of a product page")
    json_markers = ('"ok":', '"data":', '"trace_id":', '"error":')
    if any(marker in visible_text for marker in json_markers):
        raise AssertionError(f"{label} rendered a raw JSON/API envelope")


def _required_frontend_texts(path: str) -> tuple[str, ...]:
    anchors = {
        "/manual-run": ("新建提醒", "提醒参数", "生成提醒建议"),
        "/runs": ("提醒记录", "新建提醒", "业务视图"),
        "/eval": ("质量复盘", "金融质量"),
        "/eval?tab=quality": ("金融质量",),
    }
    return anchors.get(path, ())


def _assert_real_llm_detail(body: dict[str, Any]) -> None:
    interactions = body.get("data", {}).get("llm_interactions", [])
    if not isinstance(interactions, list) or not interactions:
        raise AssertionError(f"real LLM smoke expected llm_interactions: {body}")
    latest = interactions[-1]
    if not isinstance(latest, dict):
        raise AssertionError(f"real LLM smoke got invalid interaction row: {latest}")
    if latest.get("provider") != "openai_compatible":
        raise AssertionError(f"real LLM smoke expected openai_compatible provider: {latest}")
    if not latest.get("model") or not latest.get("status"):
        raise AssertionError(f"real LLM smoke missing model/status: {latest}")
    if "request_json" in latest or "response_json" in latest:
        raise AssertionError("real LLM smoke detail must not expose payloads by default")


def _assert_llm_payload_redaction(trace_id: str) -> None:
    body = _wait_for_json(f"{API_BASE}/api/runs/{trace_id}?include_payloads=true", "API run detail with LLM payloads")
    interactions = body.get("data", {}).get("llm_interactions", [])
    if not isinstance(interactions, list) or not interactions:
        raise AssertionError(f"LLM payload redaction smoke expected interactions: {body}")
    rendered = json.dumps(interactions, ensure_ascii=False, default=str)
    if "local-mock-openai-key" in rendered or "Bearer " in rendered:
        raise AssertionError("LLM payload redaction smoke leaked an authorization secret")
    if "request_json" not in interactions[-1] or "response_json" not in interactions[-1]:
        raise AssertionError(f"LLM payload redaction smoke expected explicit payload fields: {interactions[-1]}")


def _assert_mock_llm_detail(body: dict[str, Any]) -> None:
    data = body.get("data", {})
    interactions = data.get("llm_interactions", [])
    if not isinstance(interactions, list) or not interactions:
        raise AssertionError(f"mock LLM smoke expected llm_interactions: {body}")
    if not any(isinstance(item, dict) and item.get("model") == "mock-crypto-plan" for item in interactions):
        raise AssertionError(f"mock LLM smoke expected mock-crypto-plan interaction: {interactions}")
    summary = data.get("plan_run", {}).get("business_summary", {})
    if "mock LLM" not in str(summary.get("mode_notice")):
        raise AssertionError(f"mock LLM smoke expected visible mock mode_notice: {summary}")


def _assert_real_market_detail(body: dict[str, Any]) -> None:
    plan_run = body.get("data", {}).get("plan_run", {})
    audit = plan_run.get("agent_audit_view", {}) if isinstance(plan_run, dict) else {}
    evidence_sources = audit.get("evidence_sources", []) if isinstance(audit, dict) else []
    rendered = json.dumps(evidence_sources, ensure_ascii=False, default=str)
    if "fixture" in rendered:
        raise AssertionError(f"real market smoke should not rely on fixture evidence sources: {evidence_sources}")
    if not evidence_sources:
        raise AssertionError(f"real market smoke expected evidence sources: {body}")


def _assert_actionable_staging_detail(body: dict[str, Any]) -> None:
    data = body.get("data", {})
    trace = data.get("trace", {})
    if trace.get("allowed") is not True:
        raise AssertionError(f"actionable staging smoke expected allowed trace: {trace}")
    plan_run = data.get("plan_run", {})
    verdict = plan_run.get("verdict", {}) if isinstance(plan_run, dict) else {}
    if verdict.get("allowed") is not True:
        raise AssertionError(f"actionable staging smoke expected allowed verdict: {verdict}")
    parsed_plan = plan_run.get("parsed_plan", {}) if isinstance(plan_run, dict) else {}
    if parsed_plan.get("manual_execution_required") is not True:
        raise AssertionError(f"actionable staging smoke must remain manual-only: {parsed_plan}")
    summary = plan_run.get("business_summary", {}) if isinstance(plan_run, dict) else {}
    if summary.get("decision_label") != "可人工复核":
        raise AssertionError(f"actionable staging smoke expected manual-review business label: {summary}")
    audit = plan_run.get("agent_audit_view", {}) if isinstance(plan_run, dict) else {}
    facts_gate = audit.get("facts_gate", {}) if isinstance(audit, dict) else {}
    if facts_gate.get("missing_execution_facts") or facts_gate.get("missing_event_facts"):
        raise AssertionError(f"actionable staging smoke expected no missing facts: {facts_gate}")
    production_gate = audit.get("gates", {}).get("production_control_gate", {}) if isinstance(audit, dict) else {}
    if production_gate.get("allowed") is not True:
        raise AssertionError(f"actionable staging smoke expected production gate allowed: {production_gate}")


def _smoke_profile(
    *,
    real_llm_enabled: bool,
    mock_llm_enabled: bool,
    real_market_enabled: bool,
    actionable_staging_enabled: bool = False,
    collect_outcomes_fixture_enabled: bool = False,
    prod_actionable_enabled: bool = False,
) -> str:
    if prod_actionable_enabled:
        return "prod_actionable"
    if collect_outcomes_fixture_enabled:
        return "collect_outcomes_fixture"
    if actionable_staging_enabled:
        return "actionable_staging"
    if real_llm_enabled and real_market_enabled:
        return "real_external"
    if mock_llm_enabled:
        return "mock_real_engine"
    if real_market_enabled:
        return "real_market_fixture_decision"
    return "fixture"


def _local_proof_boundary(*, prod_actionable_enabled: bool) -> dict[str, Any]:
    if not prod_actionable_enabled:
        return {}
    return {
        "proof_level": "local-prod-actionable-rehearsal",
        "production_success": False,
        "hosted_proof_required": True,
        "does_not_prove": "hosted_prod_actionable",
    }


def _assert_frontend_agent_audit_page(trace_id: str) -> None:
    body = _wait_for_text(
        f"{FRONTEND_BASE}/runs/{trace_id}?tab=matrix&columns=observability",
        f"frontend run detail {trace_id}",
    )
    if "__next" not in body and "Crypto" not in body:
        raise AssertionError(f"Frontend run detail {trace_id} did not look like a Next.js page")
    _assert_frontend_agent_audit_html(body)


def _assert_frontend_agent_audit_html(body: str) -> None:
    for text in (
        "Agent Swarm Audit",
        "LeadPlan",
        "Worker Matrix",
        "Skill Tool Calls",
        "Source Freshness",
        "Root Cause Graph",
        "Conflict Matrix",
        "Candidate Comparison",
        "Input Lineage",
        "Release And Gates",
        "ExecutionRiskAgent",
        "DecisionInput",
        "production_control_gate",
        "audit_note",
    ):
        if text not in body:
            raise AssertionError(f"Frontend agent audit page missing {text}")


def _assert_notification_sent(trace_id: str, *, data_dir: Path | None = None) -> dict[str, Any]:
    detail = _wait_for_json(f"{API_BASE}/api/runs/{trace_id}", "API run detail for notification")
    plan_id = detail.get("data", {}).get("trace", {}).get("final_plan_id")
    if not plan_id:
        raise AssertionError(f"run detail missing final_plan_id: {detail}")

    db_path = Path(data_dir) / "crypto-alert.db" if data_dir is not None else ROOT / "data" / "crypto-alert.db"
    deadline = time.time() + 20
    last_row: dict[str, Any] | None = None
    while time.time() < deadline:
        if db_path.exists():
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    """
                    SELECT ok, status_code, error
                    FROM notifications
                    WHERE plan_id = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (plan_id,),
                ).fetchone()
            if row:
                last_row = dict(row)
                if row["ok"] == 1:
                    return {
                        "enabled": True,
                        "ok": True,
                        "status": "sent",
                        "status_code": row["status_code"],
                        "plan_id": plan_id,
                    }
                raise AssertionError(f"Bark notification failed: {dict(row)}")
        time.sleep(1)
    raise AssertionError(f"Timed out waiting for Bark notification row. plan_id={plan_id}, last_row={last_row}")


def _wait_for_json(url: str, name: str, timeout_seconds: int = 45) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"Timed out waiting for {name}: {last_error}")


def _wait_for_text(url: str, name: str, timeout_seconds: int = 45) -> str:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=5) as response:
                return response.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"Timed out waiting for {name}: {last_error}")


def _ensure_port_free(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        if sock.connect_ex(("127.0.0.1", port)) == 0:
            raise RuntimeError(f"Port {port} is already in use. Stop that process before running smoke tests.")


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
