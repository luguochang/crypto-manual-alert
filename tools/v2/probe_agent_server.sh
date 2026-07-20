#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
HOST="${LANGGRAPH_PROBE_HOST:-127.0.0.1}"
PORT="${LANGGRAPH_PROBE_PORT:-8123}"
BASE_URL="http://$HOST:$PORT"
LOG_FILE="$(mktemp -t crypto-alert-langgraph.XXXXXX.log)"
RESPONSE_FILE="$(mktemp -t crypto-alert-langgraph-response.XXXXXX.json)"
AUTH_DIR="$(mktemp -d -t crypto-alert-langgraph-auth.XXXXXX)"
CONFIG_FILE="$AUTH_DIR/langgraph.json"
SERVER_PID=""

cleanup() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -f "$LOG_FILE" "$RESPONSE_FILE" "$CONFIG_FILE"
  rm -rf "$AUTH_DIR"
}
trap cleanup EXIT INT TERM

cd "$BACKEND_DIR"
PROBE_CONFIG_FILE="$CONFIG_FILE" uv run python -c '
import json
import os
from pathlib import Path

source = Path(
    "langgraph.multi-interrupt.json"
    if os.environ.get("TASK8_PROTOCOL_V2_PROBE") == "1"
    else "langgraph.json"
)
target = Path(os.environ["PROBE_CONFIG_FILE"])
config = json.loads(source.read_text())
config.pop("http", None)
config.pop("env", None)
target.write_text(json.dumps(config))
'
uv run python -m crypto_alert_v2.auth.development_keys \
  "$AUTH_DIR/private" \
  --public-directory "$AUTH_DIR/public"

export APP_ENVIRONMENT=production
export CRYPTO_ALERT_DISABLE_DOTENV=1
export INTERNAL_JWT_KID=probe-ephemeral
export INTERNAL_JWT_ISSUER=crypto-alert-agent-probe
export AGENT_SERVER_INTERNAL_JWT_AUDIENCE=crypto-alert-agent-server
export INTERNAL_JWT_PRIVATE_KEY_FILE="$AUTH_DIR/private/private.pem"
export INTERNAL_JWT_PUBLIC_KEY_FILE="$AUTH_DIR/public/public.pem"
# The production custom Product app requires an encryption key even though this
# probe never stores a notification destination. Keep the key process-local.
export NOTIFICATION_CREDENTIAL_KEY="$(uv run python -c '
import base64
import secrets

print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("="))
')"
export NOTIFICATION_CREDENTIAL_KEY_VERSION=probe-v1

issue_token() {
  local permissions_json="$1"
  PROBE_PERMISSIONS_JSON="$permissions_json" uv run python -c '
import json
import os

from crypto_alert_v2.auth.internal_token import InternalTokenIssuer
from crypto_alert_v2.config import get_settings

settings = get_settings()
private_key = settings.internal_jwt_private_key
key_id = settings.internal_jwt_key_id
if private_key is None or key_id is None:
    raise SystemExit("probe JWT signing is not configured")
issuer = InternalTokenIssuer(
    private_key=private_key.get_secret_value(),
    key_id=key_id,
    issuer=settings.internal_jwt_issuer,
    audience=settings.agent_server_internal_jwt_audience,
    ttl_seconds=60,
)
print(issuer.issue(
    subject="probe-user",
    tenant_id="probe-tenant",
    workspace_id="probe-workspace",
    roles=("member",),
    permissions=tuple(json.loads(os.environ["PROBE_PERMISSIONS_JSON"])),
))
'
}

READINESS_TOKEN="$(issue_token '["analysis:read"]')"
uv run langgraph dev --config "$CONFIG_FILE" --host "$HOST" --port "$PORT" \
  --no-browser >"$LOG_FILE" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 90); do
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    cat "$LOG_FILE" >&2
    exit 1
  fi
  if grep --fixed-strings --quiet "Port $PORT is already in use" "$LOG_FILE"; then
    cat "$LOG_FILE" >&2
    exit 1
  fi
  if grep --fixed-strings --quiet "$BASE_URL" "$LOG_FILE" \
    && curl --fail --silent \
      -H "Authorization: Bearer $READINESS_TOKEN" \
      "$BASE_URL/ok" >/dev/null; then
    break
  fi
  sleep 1
done

DENIED_TOKEN="$(issue_token '[]')"
ALLOWED_TOKEN="$(issue_token '["analysis:read"]')"

UNAUTHENTICATED_STATUS="$(curl --silent \
  --output "$RESPONSE_FILE" \
  --write-out '%{http_code}' \
  -X POST \
  -H 'Content-Type: application/json' \
  -d '{"limit":10}' \
  "$BASE_URL/assistants/search")"
if [[ "$UNAUTHENTICATED_STATUS" != "401" ]]; then
  printf 'Expected unauthenticated probe to return 401, got %s\n' \
    "$UNAUTHENTICATED_STATUS" >&2
  cat "$RESPONSE_FILE" >&2
  exit 1
fi

FORBIDDEN_STATUS="$(curl --silent \
  --output "$RESPONSE_FILE" \
  --write-out '%{http_code}' \
  -X POST \
  -H "Authorization: Bearer $DENIED_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"limit":10}' \
  "$BASE_URL/assistants/search")"
if [[ "$FORBIDDEN_STATUS" != "403" ]]; then
  printf 'Expected underprivileged probe to return 403, got %s\n' \
    "$FORBIDDEN_STATUS" >&2
  cat "$RESPONSE_FILE" >&2
  exit 1
fi

ALLOWED_STATUS=""
ASSISTANTS_READY=0
for _ in $(seq 1 30); do
  ALLOWED_STATUS="$(curl --silent \
    --output "$RESPONSE_FILE" \
    --write-out '%{http_code}' \
    -X POST \
    -H "Authorization: Bearer $ALLOWED_TOKEN" \
    -H 'Content-Type: application/json' \
    -d '{"limit":10}' \
    "$BASE_URL/assistants/search")"
  if [[ "$ALLOWED_STATUS" == "200" ]] && [[ -s "$RESPONSE_FILE" ]] && \
    uv run python -c 'import json, sys; data = json.load(open(sys.argv[1], encoding="utf-8")); raise SystemExit(0 if any(item.get("graph_id") == "crypto_analysis" for item in data) else 1)' "$RESPONSE_FILE"; then
    ASSISTANTS_READY=1
    break
  fi
  sleep 1
done
if [[ "$ASSISTANTS_READY" != "1" ]]; then
  printf 'Expected authorized probe to return a non-empty 200 response, got %s\n' \
    "$ALLOWED_STATUS" >&2
  printf 'Response body:\n' >&2
  sed -n '1,80p' "$RESPONSE_FILE" >&2
  printf 'Agent Server log:\n' >&2
  cat "$LOG_FILE" >&2
  exit 1
fi
ASSISTANT_ID="$(uv run python -c '
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    assistants = json.load(stream)
for assistant in assistants:
    if assistant.get("graph_id") == "crypto_analysis":
        print(assistant["assistant_id"])
        break
else:
    raise SystemExit("crypto_analysis assistant was not registered")
' "$RESPONSE_FILE")"

printf '401/403/200 resource auth verified\n'
printf 'Agent Server ready at %s with assistant %s\n' "$BASE_URL" "$ASSISTANT_ID"

if [[ "${TASK8_PROTOCOL_V2_PROBE:-0}" == "1" ]]; then
  NODE_PROBE="$ROOT_DIR/tools/v2/probe_protocol_v2.mjs"
  if ! command -v node >/dev/null 2>&1 || [[ ! -x "$NODE_PROBE" ]]; then
    printf 'Task 8 Protocol probe requires Node.js and %s\n' "$NODE_PROBE" >&2
    exit 69
  fi
  if [[ ! -d "$ROOT_DIR/frontend/node_modules/@langchain/langgraph-sdk" ]]; then
    printf 'Task 8 Protocol probe requires frontend npm ci dependencies\n' >&2
    exit 69
  fi
  READ_ONLY_THREAD_ID="$(uv run python -c 'import uuid; print(uuid.uuid4())')"
  READ_ONLY_CREATE_STATUS="$(curl --silent \
    --output "$RESPONSE_FILE" \
    --write-out '%{http_code}' \
    -X POST \
    -H "Authorization: Bearer $ALLOWED_TOKEN" \
    -H 'Content-Type: application/json' \
    -d "{\"thread_id\":\"$READ_ONLY_THREAD_ID\",\"metadata\":{\"graph_id\":\"crypto_analysis\"}}" \
    "$BASE_URL/threads")"
  if [[ "$READ_ONLY_CREATE_STATUS" != "403" ]]; then
    printf 'Expected read-only Thread create to return 403, got %s\n' \
      "$READ_ONLY_CREATE_STATUS" >&2
    sed -n '1,80p' "$RESPONSE_FILE" >&2
    exit 1
  fi
  PROTOCOL_TOKEN="$(issue_token '["analysis:read","analysis:write"]')"
  TASK8_AGENT_URL="$BASE_URL" \
  TASK8_AGENT_TOKEN="$PROTOCOL_TOKEN" \
  TASK8_SINGLE_GRAPH_ID="${TASK8_PROTOCOL_SINGLE_GRAPH_ID:-crypto_analysis}" \
  TASK8_BATCH_GRAPH_ID="${TASK8_PROTOCOL_BATCH_GRAPH_ID:-multi_interrupt_fixture}" \
  TASK8_EXPECTED_BATCH_INTERRUPTS=2 \
  TASK8_EXPECTED_SDK_VERSION="${TASK8_EXPECTED_SDK_VERSION:-1.9.25}" \
  TASK8_EXPECTED_PROTOCOL_VERSION="${TASK8_EXPECTED_PROTOCOL_VERSION:-0.0.18}" \
  TASK8_PROBE_TIMEOUT_MS="${TASK8_PROBE_TIMEOUT_MS:-30000}" \
    node "$NODE_PROBE" || {
      PROTOCOL_STATUS=$?
      printf 'Agent Server log after Protocol probe failure:\n' >&2
      tail -n 240 "$LOG_FILE" >&2
      exit "$PROTOCOL_STATUS"
    }
  printf 'Task 8 Protocol v2 development Runtime probe verified\n'
fi
