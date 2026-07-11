from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PID_FILE = ROOT / "data" / "dev-server" / "pids.json"
PORTS = (8010, 3001, 8011, 8012, 8013)


def main() -> int:
    parser = argparse.ArgumentParser(description="Stop local API/frontend processes started by start_local_stack.py.")
    parser.add_argument(
        "--force-ports",
        action="store_true",
        help="Also verify the local stack ports are closed after stopping pid-file processes.",
    )
    parser.add_argument(
        "--kill-any-listener",
        action="store_true",
        help="Dangerous: with --force-ports, kill any process listening on the local stack ports.",
    )
    args = parser.parse_args()

    stopped = False
    owned_pids: set[int] = set()
    if not PID_FILE.exists():
        print(f"PID file not found: {PID_FILE}")
    else:
        data = json.loads(PID_FILE.read_text(encoding="utf-8"))
        for key in ("frontend_pid", "api_pid", "mock_openai_pid", "mock_okx_pid", "mock_error_api_pid"):
            pid = data.get(key)
            if isinstance(pid, int):
                owned_pids.add(pid)
                _kill_tree(pid)
                stopped = True
        PID_FILE.unlink(missing_ok=True)
    if args.force_ports:
        for port in PORTS:
            for pid in _pids_listening_on_port(port):
                if pid in owned_pids or args.kill_any_listener:
                    _kill_tree(pid)
                    stopped = True
            if not _wait_port_closed(port):
                remaining = ", ".join(str(pid) for pid in _pids_listening_on_port(port)) or "unknown"
                print(f"Port {port} is still in use by pid(s): {remaining}")
    if stopped:
        print("Local stack stopped.")
    return 0


def _kill_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except ProcessLookupError:
        return
    except OSError:
        subprocess.run(["kill", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _wait_port_closed(port: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _pids_listening_on_port(port):
            return True
        time.sleep(0.1)
    return not _pids_listening_on_port(port)


def _pids_listening_on_port(port: int) -> list[int]:
    if os.name == "nt":
        return []
    result = subprocess.run(
        ["lsof", "-tiTCP:%d" % port, "-sTCP:LISTEN"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    pids: list[int] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return pids


if __name__ == "__main__":
    raise SystemExit(main())
