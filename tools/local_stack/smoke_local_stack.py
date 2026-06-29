from __future__ import annotations

import argparse
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
LOG_DIR = ROOT / "data" / "dev-server"
TMP_DIR = ROOT / ".tmp" / "smoke"
API_PORT = 8010
FRONTEND_PORT = 3001
API_BASE = f"http://127.0.0.1:{API_PORT}"
FRONTEND_BASE = f"http://127.0.0.1:{FRONTEND_PORT}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start local API/frontend and smoke-test the manual-alert workflow.")
    parser.add_argument("--keep-running", action="store_true", help="Keep both dev servers running after checks pass.")
    parser.add_argument(
        "--with-bark",
        action="store_true",
        help="Send a real Bark notification during the manual run. Requires BARK_DEVICE_KEY.",
    )
    args = parser.parse_args(argv)

    _ensure_port_free(API_PORT)
    _ensure_port_free(FRONTEND_PORT)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    api_process: subprocess.Popen[bytes] | None = None
    frontend_process: subprocess.Popen[bytes] | None = None
    try:
        api_process = _start_api(notification_enabled=args.with_bark)
        _wait_for_json(f"{API_BASE}/api/system/health", "API health")

        frontend_process = _start_frontend()
        _wait_for_text(FRONTEND_BASE, "frontend home")

        _assert_cors_preflight()
        _assert_frontend_page("/manual-run")
        _assert_frontend_page("/runs")
        _assert_frontend_page("/eval")
        trace_id = _assert_manual_run()
        _assert_run_list_contains(trace_id)
        _assert_run_detail(trace_id)
        notification_result = _assert_notification_sent(trace_id) if args.with_bark else {"enabled": False}
        _assert_frontend_agent_audit_page(trace_id)

        print(
            json.dumps(
                {"ok": True, "api": API_BASE, "frontend": FRONTEND_BASE, "notification": notification_result},
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
    finally:
        if not args.keep_running:
            for process in (frontend_process, api_process):
                if process is not None:
                    _stop_process(process)


def _start_api(*, notification_enabled: bool) -> subprocess.Popen[bytes]:
    env = _build_api_env(tmp_dir=TMP_DIR, notification_enabled=notification_enabled)
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "crypto_manual_alert.api.app:app", "--host", "127.0.0.1", "--port", str(API_PORT)],
        cwd=ROOT,
        env=env,
        stdout=(LOG_DIR / "api-smoke.out.log").open("wb"),
        stderr=(LOG_DIR / "api-smoke.err.log").open("wb"),
    )


def _build_api_env(
    *,
    tmp_dir: Path,
    notification_enabled: bool,
    base_env: dict[str, str] | None = None,
) -> dict[str, str]:
    """构造本地 API 环境，默认关闭真实通知，只有显式测试 Bark 时才打开。"""
    env = dict(base_env or os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["TMP"] = str(tmp_dir)
    env["TEMP"] = str(tmp_dir)
    env["MARKET_DATA_PROVIDER"] = "fixture"
    env["DECISION_ENGINE"] = "fixture"
    env["NOTIFICATION_ENABLED"] = "true" if notification_enabled else "false"
    if notification_enabled and not env.get("BARK_DEVICE_KEY"):
        raise RuntimeError("BARK_DEVICE_KEY is required when --with-bark is used.")
    return env


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
    if "__next" not in body and "Crypto" not in body:
        raise AssertionError(f"Frontend page {path} did not look like a Next.js page")
    if path == "/eval" and "Financial Quality" not in body:
        raise AssertionError("Frontend eval page missing Financial Quality panel")


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


def _assert_run_detail(trace_id: str) -> None:
    body = _wait_for_json(f"{API_BASE}/api/runs/{trace_id}", "API run detail")
    if not body.get("ok"):
        raise AssertionError(f"run detail failed: {body}")
    if body.get("data", {}).get("trace", {}).get("trace_id") != trace_id:
        raise AssertionError(f"run detail trace mismatch: {body}")
    _assert_agent_audit_view(body)


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

    flow_names = [
        str(step.get("name"))
        for step in audit.get("runtime_flow", [])
        if isinstance(step, dict) and step.get("name")
    ]
    for expected in ("manual_api", "legacy_baseline", "shadow_swarm_audit"):
        if expected not in flow_names:
            raise AssertionError(f"agent_audit_view runtime_flow missing {expected}: {flow_names}")


def _assert_frontend_agent_audit_page(trace_id: str) -> None:
    body = _wait_for_text(f"{FRONTEND_BASE}/runs/{trace_id}", f"frontend run detail {trace_id}")
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


def _assert_notification_sent(trace_id: str) -> dict[str, Any]:
    detail = _wait_for_json(f"{API_BASE}/api/runs/{trace_id}", "API run detail for notification")
    plan_id = detail.get("data", {}).get("trace", {}).get("final_plan_id")
    if not plan_id:
        raise AssertionError(f"run detail missing final_plan_id: {detail}")

    db_path = ROOT / "data" / "crypto-alert.db"
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
                    return {"enabled": True, "ok": True, "status_code": row["status_code"], "plan_id": plan_id}
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
