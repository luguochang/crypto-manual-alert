#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
COMPOSE_PROJECT_NAME="crypto-manual-alert-v2"
AGENT_IMAGE_VERIFIER="$ROOT_DIR/tools/v2/verify_agent_image.sh"
STOP_SCRIPT="$ROOT_DIR/tools/v2/stop_integration_stack.sh"
AEGRA_CONFIG_FILE="${AEGRA_CONFIG_FILE:-${LANGGRAPH_CONFIG_FILE:-$BACKEND_DIR/aegra.json}}"
V2_STACK_PROFILE="${V2_STACK_PROFILE:-production}"
AGENT_LOCAL_IMAGE="crypto-manual-alert-v2-backend:local"
START_WAIT_TIMEOUT_SECONDS=180
export COMPOSE_PROJECT_NAME

case "$V2_STACK_PROFILE" in
  production)
    if [[ "$AEGRA_CONFIG_FILE" != "$BACKEND_DIR/aegra.json" ]]; then
      printf 'production profile only accepts the canonical backend/aegra.json\n' >&2
      exit 65
    fi
    ;;
  task8-multi-interrupt-qa)
    if [[ "$AEGRA_CONFIG_FILE" != "$BACKEND_DIR/aegra.task8-qa.json" ]]; then
      printf 'task8-multi-interrupt-qa profile requires backend/aegra.task8-qa.json\n' >&2
      exit 65
    fi
    ;;
  *)
    printf 'V2_STACK_PROFILE must be production or task8-multi-interrupt-qa\n' >&2
    exit 65
    ;;
esac
if [[ ! -f "$AEGRA_CONFIG_FILE" ]]; then
  printf 'Missing Aegra config: %s\n' "$AEGRA_CONFIG_FILE" >&2
  exit 66
fi
AEGRA_CONFIG_BASENAME="$(basename "$AEGRA_CONFIG_FILE")"
export AEGRA_CONFIG_BASENAME

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

docker compose \
  --project-name "$COMPOSE_PROJECT_NAME" \
  --project-directory "$ROOT_DIR" \
  --file "$ROOT_DIR/docker-compose.yml" \
  build \
  migrate \
  frontend

if [[ "$V2_STACK_PROFILE" == "task8-multi-interrupt-qa" ]]; then
  "$AGENT_IMAGE_VERIFIER" "$AGENT_LOCAL_IMAGE" --allow-multi-interrupt-fixture
else
  "$AGENT_IMAGE_VERIFIER" "$AGENT_LOCAL_IMAGE"
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
