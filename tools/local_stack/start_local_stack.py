from __future__ import annotations

import json
import os
import subprocess
import sys
import argparse
import time
import shutil
from pathlib import Path

import smoke_local_stack as smoke


ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "data" / "dev-server"
PID_FILE = LOG_DIR / "pids.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start local API/frontend for manual testing.")
    parser.add_argument(
        "--with-bark",
        action="store_true",
        help="Enable real Bark notifications for manual runs. Requires BARK_DEVICE_KEY.",
    )
    parser.add_argument(
        "--with-mock-llm",
        action="store_true",
        help="Start a local OpenAI-compatible mock server and point the API at it.",
    )
    parser.add_argument(
        "--frontend-mode",
        choices=("dev", "production"),
        default=os.environ.get("LOCAL_STACK_FRONTEND_MODE", "dev"),
        help="Run the frontend with next dev or next start. Production mode always rebuilds with the local API base URL.",
    )
    parser.add_argument(
        "--keep-running",
        action="store_true",
        help="Keep the launcher process alive for Playwright webServer supervision.",
    )
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("LOCAL_STACK_DATA_DIR", str(ROOT / ".tmp" / "dev-server" / "data")),
        help="Data directory for the local API. Defaults to an isolated .tmp/dev-server/data directory.",
    )
    parser.add_argument(
        "--reset-data",
        action="store_true",
        help="Delete the selected data directory before starting. Intended for deterministic automated tests.",
    )
    parser.add_argument(
        "--seed-mock-outcome",
        action="store_true",
        help="Seed one explicit mocked eval outcome into the sidecar store for local visual/e2e proof. Not a real financial-quality proof.",
    )
    parser.add_argument(
        "--with-actionable-staging",
        action="store_true",
        help="Start a local OKX public-market mock and point the API at the manual-review allowed staging profile.",
    )
    parser.add_argument(
        "--with-error-internal-api",
        action="store_true",
        help=(
            "Start a local failing API and point only the Next.js server-side "
            "API_INTERNAL_BASE_URL at it. Used by Playwright to prove Server "
            "Component first-load error states."
        ),
    )
    parser.add_argument(
        "--diagnostic-routes-disabled",
        action="store_true",
        help="Start the local API with DIAGNOSTIC_ROUTES_ENABLED=false to verify product gates around engineering pages.",
    )
    args = parser.parse_args(argv)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (ROOT / ".tmp" / "dev-server").mkdir(parents=True, exist_ok=True)

    smoke._ensure_port_free(smoke.API_PORT)
    smoke._ensure_port_free(smoke.FRONTEND_PORT)
    if args.with_mock_llm:
        smoke._ensure_port_free(smoke.MOCK_OPENAI_PORT)
    if args.with_actionable_staging:
        smoke._ensure_port_free(smoke.MOCK_OKX_PORT)
    if args.with_error_internal_api:
        smoke._ensure_port_free(smoke.MOCK_ERROR_API_PORT)
    data_dir = Path(args.data_dir)
    if args.reset_data:
        shutil.rmtree(data_dir, ignore_errors=True)

    mock_openai_process: subprocess.Popen[bytes] | None = None
    mock_okx_process: subprocess.Popen[bytes] | None = None
    mock_error_api_process: subprocess.Popen[bytes] | None = None
    if args.with_mock_llm:
        mock_openai_process = _start_mock_openai_detached()
        smoke._wait_for_json(f"{smoke.MOCK_OPENAI_BASE}/health", "mock OpenAI health")
    if args.with_actionable_staging:
        mock_okx_process = _start_mock_okx_detached()
        smoke._wait_for_json(f"{smoke.MOCK_OKX_BASE}/health", "mock OKX health")
    if args.with_error_internal_api:
        mock_error_api_process = _start_mock_error_api_detached()
        smoke._wait_for_json(f"{smoke.MOCK_ERROR_API_BASE}/health", "mock error API health")

    api_process = _start_api_detached(
        notification_enabled=args.with_bark,
        data_dir=data_dir,
        mock_llm_enabled=args.with_mock_llm,
        actionable_staging_enabled=args.with_actionable_staging,
        diagnostic_routes_enabled=not args.diagnostic_routes_disabled,
    )
    frontend_process: subprocess.Popen[bytes] | None = None
    try:
        smoke._wait_for_json(f"{smoke.API_BASE}/api/system/health", "API health")
        mock_outcome = smoke._seed_mock_eval_outcome(data_dir) if args.seed_mock_outcome else None
        frontend_internal_api_base_url = smoke.MOCK_ERROR_API_BASE if args.with_error_internal_api else smoke.API_BASE
        frontend_process = _start_frontend_detached(
            mode=args.frontend_mode,
            internal_api_base_url=frontend_internal_api_base_url,
        )
        smoke._wait_for_text(smoke.FRONTEND_BASE, "frontend home")

        smoke._assert_cors_preflight()
        smoke._assert_frontend_page("/manual-run")
        smoke._assert_frontend_page("/runs")
        config_snapshot = smoke._wait_for_json(f"{smoke.API_BASE}/api/system/config", "API config").get("data", {})

        PID_FILE.write_text(
            json.dumps(
                {
                    "api_pid": api_process.pid,
                    "frontend_pid": frontend_process.pid,
                    "mock_openai_pid": mock_openai_process.pid if mock_openai_process else None,
                    "mock_okx_pid": mock_okx_process.pid if mock_okx_process else None,
                    "mock_error_api_pid": mock_error_api_process.pid if mock_error_api_process else None,
                    "api": smoke.API_BASE,
                    "frontend": smoke.FRONTEND_BASE,
                    "mock_openai": smoke.MOCK_OPENAI_BASE if args.with_mock_llm else None,
                    "mock_okx": smoke.MOCK_OKX_BASE if args.with_actionable_staging else None,
                    "mock_error_api": smoke.MOCK_ERROR_API_BASE if args.with_error_internal_api else None,
                    "frontend_mode": args.frontend_mode,
                    "frontend_api_base_url": smoke.API_BASE,
                    "frontend_internal_api_base_url": frontend_internal_api_base_url,
                    "api_base_embedded_in_frontend": smoke.API_BASE,
                    "mock_outcome_seeded": mock_outcome is not None,
                    "mock_outcome_decision_ref": mock_outcome.get("decision_ref") if mock_outcome else None,
                    "mock_outcome_quality_scope": (
                        "visibility_only_not_financial_quality" if mock_outcome is not None else None
                    ),
                    "notification_enabled": args.with_bark,
                    "decision_engine": config_snapshot.get("decision", {}).get("engine"),
                    "market_provider": config_snapshot.get("market_data", {}).get("provider"),
                    "macro_event_provider": config_snapshot.get("macro_event", {}).get("provider"),
                    "manual_execution_required": config_snapshot.get("trading", {}).get("manual_execution_required"),
                    "auto_order_enabled": config_snapshot.get("trading", {}).get("auto_order_enabled"),
                    "real_llm_enabled": False,
                    "mock_llm_enabled": args.with_mock_llm,
                    "real_market_enabled": False,
                    "actionable_staging_enabled": args.with_actionable_staging,
                    "data_dir": str(data_dir),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(PID_FILE.read_text(encoding="utf-8"))
        if args.keep_running:
            while True:
                time.sleep(3600)
        return 0
    except Exception:
        if frontend_process is not None:
            _kill_tree(frontend_process.pid)
        _kill_tree(api_process.pid)
        if mock_openai_process is not None:
            _kill_tree(mock_openai_process.pid)
        if mock_okx_process is not None:
            _kill_tree(mock_okx_process.pid)
        if mock_error_api_process is not None:
            _kill_tree(mock_error_api_process.pid)
        raise


def _start_api_detached(
    *,
    notification_enabled: bool,
    data_dir: Path | None = None,
    mock_llm_enabled: bool = False,
    actionable_staging_enabled: bool = False,
    diagnostic_routes_enabled: bool = True,
) -> subprocess.Popen[bytes]:
    env = smoke._build_api_env(
        tmp_dir=ROOT / ".tmp" / "dev-server",
        notification_enabled=notification_enabled,
        mock_llm_enabled=mock_llm_enabled,
        actionable_staging_enabled=actionable_staging_enabled,
        diagnostic_routes_enabled=diagnostic_routes_enabled,
    )
    env["DATA_DIR"] = str(data_dir or ROOT / ".tmp" / "dev-server" / "data")
    return _popen_detached(
        [sys.executable, "-m", "uvicorn", "crypto_manual_alert.api.app:app", "--host", "127.0.0.1", "--port", "8010"],
        cwd=ROOT,
        env=env,
        stdout=LOG_DIR / "api-8010.out.log",
        stderr=LOG_DIR / "api-8010.err.log",
    )


def _start_mock_openai_detached() -> subprocess.Popen[bytes]:
    return _popen_detached(
        [
            sys.executable,
            str(ROOT / "tools" / "local_stack" / "mock_openai_server.py"),
            "--host",
            "127.0.0.1",
            "--port",
            str(smoke.MOCK_OPENAI_PORT),
        ],
        cwd=ROOT,
        env=os.environ.copy(),
        stdout=LOG_DIR / "mock-openai-8011.out.log",
        stderr=LOG_DIR / "mock-openai-8011.err.log",
    )


def _start_mock_okx_detached() -> subprocess.Popen[bytes]:
    return _popen_detached(
        [
            sys.executable,
            str(ROOT / "tools" / "local_stack" / "mock_okx_server.py"),
            "--host",
            "127.0.0.1",
            "--port",
            str(smoke.MOCK_OKX_PORT),
        ],
        cwd=ROOT,
        env=os.environ.copy(),
        stdout=LOG_DIR / "mock-okx-8012.out.log",
        stderr=LOG_DIR / "mock-okx-8012.err.log",
    )


def _start_mock_error_api_detached() -> subprocess.Popen[bytes]:
    return _popen_detached(
        [
            sys.executable,
            str(ROOT / "tools" / "local_stack" / "mock_error_api_server.py"),
            "--host",
            "127.0.0.1",
            "--port",
            str(smoke.MOCK_ERROR_API_PORT),
        ],
        cwd=ROOT,
        env=os.environ.copy(),
        stdout=LOG_DIR / "mock-error-api-8013.out.log",
        stderr=LOG_DIR / "mock-error-api-8013.err.log",
    )


def _start_frontend_detached(*, mode: str = "dev", internal_api_base_url: str | None = None) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env["NEXT_PUBLIC_API_BASE_URL"] = smoke.API_BASE
    env["API_INTERNAL_BASE_URL"] = internal_api_base_url or smoke.API_BASE
    npm = "npm.cmd" if os.name == "nt" else "npm"
    command = [npm, "run", "dev", "--", "--hostname", "127.0.0.1", "--port", "3001"]
    if mode == "production":
        _ensure_frontend_production_build(env)
        command = [npm, "exec", "next", "--", "start", "--hostname", "127.0.0.1", "--port", "3001"]
    return _popen_detached(
        command,
        cwd=ROOT / "frontend",
        env=env,
        stdout=LOG_DIR / "frontend-3001.out.log",
        stderr=LOG_DIR / "frontend-3001.err.log",
    )


def _ensure_frontend_production_build(env: dict[str, str]) -> None:
    _run_frontend_build(env)


def _run_frontend_build(env: dict[str, str]) -> None:
    npm = "npm.cmd" if os.name == "nt" else "npm"
    with (LOG_DIR / "frontend-build.out.log").open("wb") as stdout, (LOG_DIR / "frontend-build.err.log").open("wb") as stderr:
        result = subprocess.run(
            [npm, "run", "build"],
            cwd=ROOT / "frontend",
            env=env,
            stdout=stdout,
            stderr=stderr,
            check=False,
        )
    if result.returncode != 0:
        raise RuntimeError(
            "Frontend production build failed. See data/dev-server/frontend-build.out.log "
            "and data/dev-server/frontend-build.err.log."
        )


def _popen_detached(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    stdout: Path,
    stderr: Path,
) -> subprocess.Popen[bytes]:
    flags = 0
    start_new_session = False
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        start_new_session = True
    return subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=stdout.open("wb"),
        stderr=stderr.open("wb"),
        creationflags=flags,
        start_new_session=start_new_session,
    )


def _kill_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    subprocess.run(["kill", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    raise SystemExit(main())
