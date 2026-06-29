from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
TMP_DIR = ROOT / ".tmp" / "local-checks" / f"run-{os.getpid()}-{int(time.time())}"
PYTEST_BASETEMP = TMP_DIR / "pytest"
NEXT_BUILD_DIR = FRONTEND / ".next"
LOCAL_PORTS = (8010, 3001)


def main() -> int:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["TMP"] = str(TMP_DIR)
    env["TEMP"] = str(TMP_DIR)

    for port in LOCAL_PORTS:
        if not _is_port_free(port):
            print(f"Port {port} is already in use. Run tests/stop_local_stack.py or stop the local server first.")
            return 1

    npm = "npm.cmd" if os.name == "nt" else "npm"
    checks = [
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "--basetemp", str(PYTEST_BASETEMP)],
        [npm, "run", "typecheck"],
        [npm, "run", "build"],
        [sys.executable, "tests/smoke_local_stack.py"],
    ]
    workdirs = [ROOT, FRONTEND, FRONTEND, ROOT]

    for command, cwd in zip(checks, workdirs, strict=True):
        if command == [npm, "run", "build"]:
            _remove_next_build_dir()
        print(f"\n$ {' '.join(command)}", flush=True)
        result = subprocess.run(command, cwd=cwd, env=env, check=False)
        if result.returncode != 0:
            return result.returncode
    return 0


def _is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def _remove_next_build_dir() -> None:
    """构建前清理 Next.js 缓存，避免上次 dev server 遗留锁导致 build 误报。"""
    if not NEXT_BUILD_DIR.exists():
        return
    if NEXT_BUILD_DIR.resolve().parent != FRONTEND.resolve():
        raise RuntimeError(f"Refuse to remove unexpected path: {NEXT_BUILD_DIR}")
    shutil.rmtree(NEXT_BUILD_DIR)


if __name__ == "__main__":
    raise SystemExit(main())
