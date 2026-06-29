from __future__ import annotations

import json
import os
import subprocess
import sys
import argparse
from pathlib import Path

import smoke_local_stack as smoke


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "data" / "dev-server"
PID_FILE = LOG_DIR / "pids.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Start local API/frontend for manual testing.")
    parser.add_argument(
        "--with-bark",
        action="store_true",
        help="Enable real Bark notifications for manual runs. Requires BARK_DEVICE_KEY.",
    )
    args = parser.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (ROOT / ".tmp" / "dev-server").mkdir(parents=True, exist_ok=True)

    smoke._ensure_port_free(smoke.API_PORT)
    smoke._ensure_port_free(smoke.FRONTEND_PORT)

    api_process = _start_api_detached(notification_enabled=args.with_bark)
    frontend_process: subprocess.Popen[bytes] | None = None
    try:
        smoke._wait_for_json(f"{smoke.API_BASE}/api/system/health", "API health")
        frontend_process = _start_frontend_detached()
        smoke._wait_for_text(smoke.FRONTEND_BASE, "frontend home")

        smoke._assert_cors_preflight()
        smoke._assert_frontend_page("/manual-run")
        smoke._assert_frontend_page("/runs")

        PID_FILE.write_text(
            json.dumps(
                {
                    "api_pid": api_process.pid,
                    "frontend_pid": frontend_process.pid,
                    "api": smoke.API_BASE,
                    "frontend": smoke.FRONTEND_BASE,
                    "notification_enabled": args.with_bark,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(PID_FILE.read_text(encoding="utf-8"))
        return 0
    except Exception:
        if frontend_process is not None:
            _kill_tree(frontend_process.pid)
        _kill_tree(api_process.pid)
        raise


def _start_api_detached(*, notification_enabled: bool) -> subprocess.Popen[bytes]:
    env = smoke._build_api_env(tmp_dir=ROOT / ".tmp" / "dev-server", notification_enabled=notification_enabled)
    return _popen_detached(
        [sys.executable, "-m", "uvicorn", "crypto_manual_alert.api.app:app", "--host", "127.0.0.1", "--port", "8010"],
        cwd=ROOT,
        env=env,
        stdout=LOG_DIR / "api-8010.out.log",
        stderr=LOG_DIR / "api-8010.err.log",
    )


def _start_frontend_detached() -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env["NEXT_PUBLIC_API_BASE_URL"] = smoke.API_BASE
    npm = "npm.cmd" if os.name == "nt" else "npm"
    return _popen_detached(
        [npm, "run", "dev", "--", "--hostname", "127.0.0.1", "--port", "3001"],
        cwd=ROOT / "frontend",
        env=env,
        stdout=LOG_DIR / "frontend-3001.out.log",
        stderr=LOG_DIR / "frontend-3001.err.log",
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
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    return subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=stdout.open("wb"),
        stderr=stderr.open("wb"),
        creationflags=flags,
    )


def _kill_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    subprocess.run(["kill", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    raise SystemExit(main())
