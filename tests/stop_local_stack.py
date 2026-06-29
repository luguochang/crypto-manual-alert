from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PID_FILE = ROOT / "data" / "dev-server" / "pids.json"


def main() -> int:
    if not PID_FILE.exists():
        print(f"PID file not found: {PID_FILE}")
        return 0
    data = json.loads(PID_FILE.read_text(encoding="utf-8"))
    for key in ("frontend_pid", "api_pid"):
        pid = data.get(key)
        if isinstance(pid, int):
            _kill_tree(pid)
    PID_FILE.unlink(missing_ok=True)
    return 0


def _kill_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    subprocess.run(["kill", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    raise SystemExit(main())
