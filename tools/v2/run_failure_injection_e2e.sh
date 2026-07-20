#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
SCENARIO_FILE="${FAILURE_INJECTION_SCENARIO_FILE:-/tmp/crypto-alert-v2-failure-scenario.json}"

export APP_ENVIRONMENT=test
export SEARCH_PROVIDER="${SEARCH_PROVIDER:-builtin_web_search}"
export OPENAI_API_KEY=failure-injection-placeholder
export OPENAI_BASE_URL=http://127.0.0.1:9/v1
export MODEL_NAME=failure-injection-placeholder
export PRODUCT_DATABASE_URL="${PRODUCT_DATABASE_URL:-postgresql+asyncpg://crypto_alert@127.0.0.1:55435/crypto_alert_v2}"
export DEVELOPMENT_BOOTSTRAP_ENABLED=true
export DEVELOPMENT_BOOTSTRAP_PROFILE=local-proof
export DEVELOPMENT_BOOTSTRAP_SUBJECT=dev-user
export DEVELOPMENT_BOOTSTRAP_TENANT_ID=dev-tenant
export DEVELOPMENT_BOOTSTRAP_WORKSPACE_ID=dev-workspace
export DEVELOPMENT_BOOTSTRAP_ROLES='["member"]'
export DEVELOPMENT_BOOTSTRAP_PERMISSIONS='["analysis:read","analysis:write","failure_injection:write"]'
export FAILURE_INJECTION_ENABLED=1
export FAILURE_INJECTION_PROFILE=task12
export FAILURE_INJECTION_SCENARIO_FILE="$SCENARIO_FILE"
export FAILURE_INJECTION_CONTROL_TOKEN="${FAILURE_INJECTION_CONTROL_TOKEN:-$(openssl rand -hex 32)}"
export AGENT_SERVER_LOCAL_TOKEN="${AGENT_SERVER_LOCAL_TOKEN:-$(openssl rand -hex 32)}"
export NOTIFICATION_CREDENTIAL_KEY="${NOTIFICATION_CREDENTIAL_KEY:-$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=')}"
export NOTIFICATION_CREDENTIAL_KEY_VERSION="${NOTIFICATION_CREDENTIAL_KEY_VERSION:-failure-injection-v1}"
export V2_E2E_PROFILE=failure-injection
export PLAYWRIGHT_EXTERNAL_SERVER=1
export PLAYWRIGHT_FRONTEND_BASE_URL="${PLAYWRIGHT_FRONTEND_BASE_URL:-http://127.0.0.1:3001}"

agent_pid=""
worker_pid=""
frontend_pid=""
cleanup() {
  trap - EXIT INT TERM
  for pid in "$frontend_pid" "$worker_pid" "$agent_pid"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  wait "$frontend_pid" "$worker_pid" "$agent_pid" 2>/dev/null || true
  rm -f "$SCENARIO_FILE"
}
trap cleanup EXIT INT TERM

cd "$BACKEND_DIR"
uv run langgraph dev --config langgraph.json --host 127.0.0.1 --port 8123 --no-browser --no-reload &
agent_pid=$!
for attempt in $(seq 1 45); do
  if curl -fsS --max-time 1 http://127.0.0.1:8123/docs >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS http://127.0.0.1:8123/docs >/dev/null

uv run python -m crypto_alert_v2.workers --worker-id failure-injection-e2e --poll-interval 0.5 &
worker_pid=$!

cd "$FRONTEND_DIR"
npm run dev -- --hostname 127.0.0.1 --port 3001 &
frontend_pid=$!
for attempt in $(seq 1 45); do
  if curl -fsS --max-time 1 http://127.0.0.1:3001/work >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS http://127.0.0.1:3001/work >/dev/null

node_modules/.bin/playwright test \
  tests/e2e-v2/provider-failures.spec.ts \
  tests/e2e-v2/database-rollback.spec.ts \
  --project=failure-injection-desktop \
  --project=failure-injection-pixel-7 \
  --reporter=line \
  --output=/tmp/crypto-alert-v2-playwright-failure-injection
