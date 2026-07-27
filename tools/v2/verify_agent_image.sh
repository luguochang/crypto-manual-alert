#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  printf 'Usage: %s <built-agent-image> [--allow-multi-interrupt-fixture]\n' "$0" >&2
  exit 64
fi

agent_image=$1
allow_fixture=0
case "${2:-}" in
  "")
    ;;
  --allow-multi-interrupt-fixture)
    allow_fixture=1
    ;;
  *)
    printf 'Unknown Agent image verifier option: %s\n' "$2" >&2
    exit 64
    ;;
esac

if ! docker image inspect "$agent_image" >/dev/null 2>&1; then
  printf 'Built Aegra image is unavailable: %s\n' "$agent_image" >&2
  exit 66
fi

docker_options=(
  --rm
  --network none
  --read-only
  --cap-drop ALL
  --security-opt no-new-privileges
)
if [[ "$allow_fixture" == "1" ]]; then
  docker_options+=(--env TASK8_ALLOW_MULTI_INTERRUPT_FIXTURE=1)
fi

docker run \
  "${docker_options[@]}" \
  --entrypoint python \
  "$agent_image" \
  -c '
import importlib.metadata
import json
import os
from pathlib import Path

root = Path("/app/backend")
config_name = (
    "aegra.task8-qa.json"
    if os.environ.get("TASK8_ALLOW_MULTI_INTERRUPT_FIXTURE") == "1"
    else "aegra.json"
)
config = json.loads((root / config_name).read_text(encoding="utf-8"))
expected_graphs = {
    "crypto_analysis": "./src/crypto_alert_v2/graph/__init__.py:graph_factory",
    "candidate_review": (
        "./src/crypto_alert_v2/evaluation/review_graph.py:graph_factory"
    ),
}
if os.environ.get("TASK8_ALLOW_MULTI_INTERRUPT_FIXTURE") == "1":
    expected_graphs["single_interrupt_fixture"] = (
        "./src/crypto_alert_v2/testing/multi_interrupt_fixture.py:single_graph"
    )
    expected_graphs["multi_interrupt_fixture"] = (
        "./src/crypto_alert_v2/testing/multi_interrupt_fixture.py:graph"
    )
    expected_graphs["aegra_durability_fixture"] = (
        "./src/crypto_alert_v2/testing/aegra_durability_fixture.py:graph"
    )
if config.get("graphs") != expected_graphs:
    raise SystemExit("unexpected graph mapping")
if config.get("auth") != {
    "path": "./src/crypto_alert_v2/auth/agent_server.py:auth",
    "disable_studio_auth": True,
}:
    raise SystemExit("unexpected auth mapping")
expected_http = None
if os.environ.get("TASK8_ALLOW_MULTI_INTERRUPT_FIXTURE") != "1":
    expected_http = {
        "app": "./src/crypto_alert_v2/http/app.py:app",
        "enable_custom_route_auth": True,
    }
if config.get("http") != expected_http:
    raise SystemExit("unexpected custom HTTP mapping")
targets = [*config["graphs"].values(), config["auth"]["path"]]
if expected_http is not None:
    targets.append(expected_http["app"])
for target in targets:
    path, symbol = target.rsplit(":", 1)
    if not (root / path).is_file() or not symbol:
        raise SystemExit(f"invalid config target: {target}")

required_versions = {
    "aegra-api": "0.9.24",
    "aegra-cli": "0.9.24",
    "crypto-manual-alert-v2": "2.0.0",
    "langgraph": "1.2.9",
    "langgraph-sdk": "0.4.2",
}
for distribution, expected_version in required_versions.items():
    if importlib.metadata.version(distribution) != expected_version:
        raise SystemExit(f"unexpected {distribution} version")

for distribution in (
    "langgraph-api",
    "langgraph-cli",
    "langgraph-runtime-inmem",
    "pytest",
):
    try:
        importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        continue
    raise SystemExit(f"development distribution present: {distribution}")

for forbidden in (
    root / ".env",
    root / ".coverage",
    root / ".langgraph_api",
    root / ".pytest_cache",
    root / "tests",
):
    if forbidden.exists():
        raise SystemExit(f"forbidden build-context path present: {forbidden}")
'
