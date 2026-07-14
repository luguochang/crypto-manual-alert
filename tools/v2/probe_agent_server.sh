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
CONFIG_FILE="$(mktemp "$BACKEND_DIR/.langgraph-auth-probe.XXXXXX.json")"
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

source = Path("langgraph.json")
target = Path(os.environ["PROBE_CONFIG_FILE"])
config = json.loads(source.read_text())
config.pop("http", None)
target.write_text(json.dumps(config))
'
uv run python -m crypto_alert_v2.auth.development_keys \
  "$AUTH_DIR/private" \
  --public-directory "$AUTH_DIR/public"

export APP_ENVIRONMENT=production
export INTERNAL_JWT_KID=probe-ephemeral
export INTERNAL_JWT_ISSUER=crypto-alert-agent-probe
export AGENT_SERVER_INTERNAL_JWT_AUDIENCE=crypto-alert-agent-server
export INTERNAL_JWT_PRIVATE_KEY_FILE="$AUTH_DIR/private/private.pem"
export INTERNAL_JWT_PUBLIC_KEY_FILE="$AUTH_DIR/public/public.pem"

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

ALLOWED_STATUS="$(curl --silent \
  --output "$RESPONSE_FILE" \
  --write-out '%{http_code}' \
  -X POST \
  -H "Authorization: Bearer $ALLOWED_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"limit":10}' \
  "$BASE_URL/assistants/search")"
if [[ "$ALLOWED_STATUS" != "200" ]]; then
  printf 'Expected authorized probe to return 200, got %s\n' \
    "$ALLOWED_STATUS" >&2
  cat "$RESPONSE_FILE" >&2
  exit 1
fi
ASSISTANTS_JSON="$(cat "$RESPONSE_FILE")"

ASSISTANT_ID="$(printf '%s' "$ASSISTANTS_JSON" | uv run python -c '
import json
import sys

assistants = json.load(sys.stdin)
for assistant in assistants:
    if assistant.get("graph_id") == "crypto_analysis":
        print(assistant["assistant_id"])
        break
else:
    raise SystemExit("crypto_analysis assistant was not registered")
')"

curl --fail --silent \
  -H "Authorization: Bearer $ALLOWED_TOKEN" \
  "$BASE_URL/assistants/$ASSISTANT_ID/graph?xray=true" \
  | uv run python -c '
import json
import sys

graph = json.load(sys.stdin)
nodes = {node["id"] for node in graph.get("nodes", [])}
required = {
    "validate_request",
    "collect_market_snapshot",
    "research_events",
    "analyze_market",
    "validate_evidence",
    "apply_risk_policy",
    "build_artifact",
    "complete",
    "complete_failed",
}
missing = required - nodes
if missing:
    raise SystemExit(f"graph schema is missing nodes: {sorted(missing)}")
'

printf '401/403/200 resource auth verified\n'
printf 'Agent Server ready at %s with assistant %s\n' "$BASE_URL" "$ASSISTANT_ID"
