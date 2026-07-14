#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
COMPOSE_PROJECT_NAME="crypto-manual-alert-v2"
AGENT_IMAGE_LOCK="$ROOT_DIR/deploy/agent-server-image.lock"
AGENT_IMAGE_VERIFIER="$ROOT_DIR/tools/v2/verify_agent_image.sh"
STOP_SCRIPT="$ROOT_DIR/tools/v2/stop_integration_stack.sh"
AGENT_LOCAL_IMAGE="${LANGGRAPH_API_LOCAL_IMAGE:-crypto-manual-alert-v2-langgraph-api:local}"
AGENT_BASE_TAG="langchain/langgraph-api:0.11.0-py3.12"
START_WAIT_TIMEOUT_SECONDS=180
export COMPOSE_PROJECT_NAME

if [[ ! -s "$AGENT_IMAGE_LOCK" ]]; then
  printf 'Missing Agent Server image lock: %s\n' "$AGENT_IMAGE_LOCK" >&2
  exit 66
fi
IFS= read -r AGENT_BASE_IMAGE < "$AGENT_IMAGE_LOCK"
if [[ ! "$AGENT_BASE_IMAGE" =~ ^langchain/langgraph-api@sha256:[0-9a-f]{64}$ ]]; then
  printf 'Invalid Agent Server image lock\n' >&2
  exit 65
fi

if ! docker image inspect "$AGENT_BASE_IMAGE" >/dev/null 2>&1; then
  docker pull "$AGENT_BASE_IMAGE"
fi
docker tag "$AGENT_BASE_IMAGE" "$AGENT_BASE_TAG"

docker compose \
  --project-name "$COMPOSE_PROJECT_NAME" \
  --project-directory "$ROOT_DIR" \
  --file "$ROOT_DIR/docker-compose.yml" \
  build \
  migrate \
  frontend

cd "$BACKEND_DIR"
uv run --frozen langgraph build \
  --config "$BACKEND_DIR/langgraph.json" \
  --api-version "0.11.0" \
  --tag "$AGENT_LOCAL_IMAGE" \
  --no-pull

"$AGENT_IMAGE_VERIFIER" "$AGENT_BASE_IMAGE" "$AGENT_LOCAL_IMAGE"

cd "$ROOT_DIR"
cleanup_failed_start() {
  local status=$?
  trap - EXIT INT TERM
  if ((status != 0)); then
    "$STOP_SCRIPT" || true
  fi
  exit "$status"
}
trap cleanup_failed_start EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

docker compose \
  --project-name "$COMPOSE_PROJECT_NAME" \
  --project-directory "$ROOT_DIR" \
  --file "$ROOT_DIR/docker-compose.yml" \
  up \
  --detach \
  --wait \
  --wait-timeout "$START_WAIT_TIMEOUT_SECONDS" \
  --remove-orphans

trap - EXIT INT TERM
