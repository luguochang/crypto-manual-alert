#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  printf 'Usage: %s <locked-base-image> <built-agent-image>\n' "$0" >&2
  exit 64
fi

base_image=$1
agent_image=$2
if [[ ! "$base_image" =~ ^langchain/langgraph-api@sha256:[0-9a-f]{64}$ ]]; then
  printf 'Invalid locked Agent Server base image\n' >&2
  exit 65
fi

layer_format='{{range .RootFS.Layers}}{{println .}}{{end}}'
base_layers_raw="$(docker image inspect --format "$layer_format" "$base_image")"
agent_layers_raw="$(docker image inspect --format "$layer_format" "$agent_image")"
if [[ -z "$base_layers_raw" || -z "$agent_layers_raw" ]]; then
  printf 'Agent image layer inspection returned no layers\n' >&2
  exit 1
fi

base_layers=()
while IFS= read -r layer; do
  [[ -n "$layer" ]] && base_layers[${#base_layers[@]}]="$layer"
done <<<"$base_layers_raw"
agent_layers=()
while IFS= read -r layer; do
  [[ -n "$layer" ]] && agent_layers[${#agent_layers[@]}]="$layer"
done <<<"$agent_layers_raw"
if ((${#agent_layers[@]} < ${#base_layers[@]})); then
  printf 'Built Agent image has fewer layers than its locked base\n' >&2
  exit 1
fi
for index in "${!base_layers[@]}"; do
  if [[ "${agent_layers[$index]}" != "${base_layers[$index]}" ]]; then
    printf 'Built Agent image does not descend from the locked base digest\n' >&2
    exit 1
  fi
done

docker run \
  --rm \
  --network none \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --entrypoint python \
  "$agent_image" \
  -c '
import importlib.metadata
import json
import os
from pathlib import Path

expected_mappings = {
    "LANGGRAPH_AUTH": {
        "path": "/deps/workspace/src/crypto_alert_v2/auth/agent_server.py:auth",
        "disable_studio_auth": True,
    },
    "LANGGRAPH_HTTP": {
        "app": "/deps/workspace/src/crypto_alert_v2/http/app.py:app",
        "enable_custom_route_auth": True,
    },
    "LANGSERVE_GRAPHS": {
        "crypto_analysis": "/deps/workspace/src/crypto_alert_v2/graph/__init__.py:graph",
    },
}
for name, expected in expected_mappings.items():
    actual = json.loads(os.environ.get(name, "null"))
    if actual != expected:
        raise SystemExit(f"unexpected {name} mapping")
    for target in actual.values():
        if isinstance(target, str) and ":" in target:
            path, symbol = target.rsplit(":", 1)
            if not Path(path).is_file() or not symbol:
                raise SystemExit(f"invalid {name} target")

required_versions = {
    "langgraph-api": "0.11.0",
    "crypto-manual-alert-v2": "2.0.0",
}
for distribution, expected_version in required_versions.items():
    if importlib.metadata.version(distribution) != expected_version:
        raise SystemExit(f"unexpected {distribution} version")

for distribution in ("langgraph-cli", "langgraph-runtime-inmem", "pytest"):
    try:
        importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        continue
    raise SystemExit(f"development distribution present: {distribution}")

for forbidden in (
    "/deps/workspace/.env",
    "/deps/workspace/.coverage",
    "/deps/workspace/.langgraph_api",
    "/deps/workspace/.pytest_cache",
    "/deps/workspace/tests",
):
    if Path(forbidden).exists():
        raise SystemExit(f"forbidden build-context path present: {forbidden}")
'
