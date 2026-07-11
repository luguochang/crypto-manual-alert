from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
TMP_DIR = ROOT / ".tmp" / "local-checks" / f"run-{os.getpid()}-{int(time.time())}"
PYTEST_BASETEMP = TMP_DIR / "pytest"
NEXT_BUILD_DIR = FRONTEND / ".next"
LOCAL_PORTS = (8010, 3001, 8011, 8012, 8013)


class CheckSpec:
    def __init__(self, command: list[str], cwd: Path, *, clean_next_build: bool = False) -> None:
        self.command = command
        self.cwd = cwd
        self.clean_next_build = clean_next_build


def main() -> int:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["TMP"] = str(TMP_DIR)
    env["TEMP"] = str(TMP_DIR)

    for port in LOCAL_PORTS:
        if not _is_port_free(port):
            print(f"Port {port} is already in use. Run tools/local_stack/stop_local_stack.py or stop the local server first.")
            return 1

    for spec in _build_checks(_npm_command()):
        if spec.clean_next_build:
            _remove_next_build_dir()
        print(f"\n$ {' '.join(spec.command)}", flush=True)
        result = subprocess.run(spec.command, cwd=spec.cwd, env=env, check=False)
        if result.returncode != 0:
            return result.returncode
    return 0


def _build_checks(npm: str) -> list[CheckSpec]:
    """Return the no-secret local validation matrix.

    The strict prod-actionable gate is intentionally not part of this default
    green path: missing real Bark/OpenAI/event readiness must remain a release
    block, not a surprising local-check failure or a hidden success.
    """

    return [
        CheckSpec([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "--basetemp", str(PYTEST_BASETEMP)], ROOT),
        CheckSpec([npm, "run", "typecheck"], FRONTEND),
        CheckSpec([npm, "run", "build"], FRONTEND, clean_next_build=True),
        CheckSpec([npm, "run", "e2e"], FRONTEND),
        CheckSpec([sys.executable, "tools/local_stack/smoke_local_stack.py"], ROOT),
        CheckSpec([sys.executable, "tools/local_stack/smoke_local_stack.py", "--with-mock-llm"], ROOT),
        CheckSpec([sys.executable, "tools/local_stack/smoke_local_stack.py", "--with-actionable-staging"], ROOT),
        CheckSpec([sys.executable, "tools/local_stack/smoke_local_stack.py", "--seed-mock-outcome"], ROOT),
        CheckSpec([sys.executable, "tools/local_stack/smoke_local_stack.py", "--collect-outcomes-fixture"], ROOT),
    ]


def _npm_command() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


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
