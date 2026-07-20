#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
COMPOSE_PROJECT_NAME="crypto-manual-alert-v2"
AGENT_IMAGE_LOCK="$ROOT_DIR/deploy/agent-server-image.lock"
AGENT_IMAGE_VERIFIER="$ROOT_DIR/tools/v2/verify_agent_image.sh"
STOP_SCRIPT="$ROOT_DIR/tools/v2/stop_integration_stack.sh"
LANGGRAPH_CONFIG_FILE="${LANGGRAPH_CONFIG_FILE:-$BACKEND_DIR/langgraph.json}"
V2_STACK_PROFILE="${V2_STACK_PROFILE:-production}"
AGENT_LOCAL_IMAGE="${LANGGRAPH_API_LOCAL_IMAGE:-crypto-manual-alert-v2-langgraph-api:local}"
AGENT_BASE_TAG="langchain/langgraph-api:0.11.0-py3.12"
START_WAIT_TIMEOUT_SECONDS=180
export COMPOSE_PROJECT_NAME

case "$V2_STACK_PROFILE" in
  production)
    if [[ "$LANGGRAPH_CONFIG_FILE" != "$BACKEND_DIR/langgraph.json" ]]; then
      printf 'production profile only accepts the canonical backend/langgraph.json\n' >&2
      exit 65
    fi
    ;;
  task8-multi-interrupt-qa)
    if [[ "$LANGGRAPH_CONFIG_FILE" != "$BACKEND_DIR/langgraph.multi-interrupt.json" ]]; then
      printf 'task8-multi-interrupt-qa profile requires the multi-interrupt fixture config\n' >&2
      exit 65
    fi
    ;;
  *)
    printf 'V2_STACK_PROFILE must be production or task8-multi-interrupt-qa\n' >&2
    exit 65
    ;;
esac
if [[ ! -f "$LANGGRAPH_CONFIG_FILE" ]]; then
  printf 'Missing LangGraph config: %s\n' "$LANGGRAPH_CONFIG_FILE" >&2
  exit 66
fi

if [[ -z "${LANGGRAPH_CLOUD_LICENSE_KEY:-}" && -z "${LANGSMITH_API_KEY:-}" ]]; then
  printf 'A LangGraph Cloud license key or LangSmith API key with LangGraph Cloud access is required for the production Agent Server\n' >&2
  printf 'Inject LANGGRAPH_CLOUD_LICENSE_KEY or LANGSMITH_API_KEY into this process; the value will not be printed\n' >&2
  exit 78
fi

# The local integration topology runs the production application profile. Keep
# its encrypted notification store usable without asking developers to persist
# a secret, while requiring real deployments to inject their own key through
# Compose/environment secret management.
if [[ -z "${NOTIFICATION_CREDENTIAL_KEY:-}" ]]; then
  if ! command -v openssl >/dev/null 2>&1; then
    printf 'openssl is required to generate the local notification credential key\n' >&2
    exit 66
  fi
  NOTIFICATION_CREDENTIAL_KEY="$({ openssl rand -base64 32 | tr '+/' '-_' | tr -d '='; } 2>/dev/null)"
  export NOTIFICATION_CREDENTIAL_KEY
  export NOTIFICATION_CREDENTIAL_KEY_VERSION="local-ephemeral"
  printf 'Generated an ephemeral notification credential key for this local integration run\n' >&2
fi

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
  --config "$LANGGRAPH_CONFIG_FILE" \
  --api-version "0.11.0" \
  --tag "$AGENT_LOCAL_IMAGE" \
  --no-pull

if [[ "$V2_STACK_PROFILE" == "task8-multi-interrupt-qa" ]]; then
  "$AGENT_IMAGE_VERIFIER" \
    "$AGENT_BASE_IMAGE" \
    "$AGENT_LOCAL_IMAGE" \
    --allow-multi-interrupt-fixture
else
  "$AGENT_IMAGE_VERIFIER" "$AGENT_BASE_IMAGE" "$AGENT_LOCAL_IMAGE"
fi

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
