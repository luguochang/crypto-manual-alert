#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"
QA_COMPOSE_FILE="$ROOT_DIR/deploy/docker-compose.task8-qa.yml"
IMAGE="crypto-manual-alert-v2-backend:local"
IMAGE_VERIFIER="$ROOT_DIR/tools/v2/verify_agent_image.sh"
CLIENT_PROBE="$ROOT_DIR/tools/v2/aegra_durability_probe.py"
REPLAY_PROBE="$ROOT_DIR/tools/v2/probe_aegra_replay.mjs"
PROTOCOL_PROBE="$ROOT_DIR/tools/v2/probe_protocol_v2.mjs"
EVIDENCE_DIR=""
PROJECT_NAME="crypto-manual-alert-v2-task8-$$"
STACK_STARTED=0
EVIDENCE_FINALIZED=0

usage() {
  printf 'Usage: %s --evidence-dir PATH\n' "$0"
}

die() {
  local status=$1
  shift
  printf '%s\n' "$*" >&2
  exit "$status"
}

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  if [[ "$STACK_STARTED" == "1" ]]; then
    if [[ "$EVIDENCE_FINALIZED" != "1" ]]; then
      "${compose[@]}" logs --no-color langgraph-api 2>&1 \
        | sed -E \
          -e 's#(postgres(ql)?(\+asyncpg)?://[^:]+:)[^@]+@#\1[REDACTED]@#Ig' \
          -e 's/(Bearer )[A-Za-z0-9._~+\/-]+/\1[REDACTED]/g' \
        >"$EVIDENCE_DIR/aegra.log" || true
    fi
    "${compose[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

while (($# > 0)); do
  case "$1" in
    --evidence-dir)
      (($# >= 2)) || die 64 '--evidence-dir requires a path'
      EVIDENCE_DIR=$2
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      usage >&2
      die 64 "Unknown option: $1"
      ;;
  esac
done
[[ -n "$EVIDENCE_DIR" ]] || die 64 '--evidence-dir is required'
mkdir -p "$EVIDENCE_DIR"
[[ -z "$(ls -A "$EVIDENCE_DIR")" ]] || die 64 '--evidence-dir must be empty'
EVIDENCE_DIR="$(cd "$EVIDENCE_DIR" && pwd -P)"

for command_name in docker curl node openssl rg sed sha256sum; do
  command -v "$command_name" >/dev/null 2>&1 \
    || die 69 "Required tool is unavailable: $command_name"
done
if command -v python >/dev/null 2>&1; then
  host_python=python
elif command -v python3 >/dev/null 2>&1; then
  host_python=python3
else
  die 69 'Required tool is unavailable: python or python3'
fi
docker compose version >/dev/null 2>&1 || die 69 'Docker Compose v2 is required'
docker info >/dev/null 2>&1 || die 69 'Docker daemon is unavailable'
[[ -d "$ROOT_DIR/frontend/node_modules/@langchain/langgraph-sdk" ]] \
  || die 69 'Run npm ci in frontend before the Aegra durability probe'

export COMPOSE_DISABLE_ENV_FILE=1
export COMPOSE_PROJECT_NAME="$PROJECT_NAME"
export AEGRA_CONFIG_BASENAME=aegra.task8-qa.json
export AGENT_SERVER_PORT="${AEGRA_PROBE_PORT:-18123}"
export AEGRA_WORKER_COUNT=1
export AEGRA_JOBS_PER_WORKER=1
export AEGRA_LEASE_DURATION_SECONDS="${AEGRA_PROBE_LEASE_SECONDS:-9}"
export AEGRA_HEARTBEAT_INTERVAL_SECONDS="${AEGRA_PROBE_HEARTBEAT_SECONDS:-3}"
export AEGRA_REAPER_INTERVAL_SECONDS="${AEGRA_PROBE_REAPER_SECONDS:-2}"
export AEGRA_STUCK_PENDING_THRESHOLD_SECONDS=15
export SEARCH_PROVIDER=builtin_web_search
export NOTIFICATION_CREDENTIAL_KEY="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=')"
export NOTIFICATION_CREDENTIAL_KEY_VERSION=task8-ephemeral

compose=(
  docker compose
  --project-name "$PROJECT_NAME"
  --project-directory "$ROOT_DIR"
  --file "$COMPOSE_FILE"
  --file "$QA_COMPOSE_FILE"
)

"${compose[@]}" build migrate
"$IMAGE_VERIFIER" "$IMAGE" --allow-multi-interrupt-fixture
STACK_STARTED=1
"${compose[@]}" up --detach --wait --wait-timeout 180 langgraph-api

agent_target="$("${compose[@]}" port langgraph-api 8000)"
[[ -n "$agent_target" ]] || die 70 'Aegra service has no published port'
agent_url="http://$agent_target"
[[ "$agent_url" == "http://127.0.0.1:$AGENT_SERVER_PORT" ]] \
  || die 70 'Aegra service is not bound to the requested loopback port'
container_before="$("${compose[@]}" ps -q langgraph-api)"
image_id="$(docker inspect --format '{{.Image}}' "$container_before")"
generation_before="$(docker inspect --format '{{.Id}}:{{.State.StartedAt}}' "$container_before")"

owner_context_id=99999999-9999-4999-8999-999999999999
peer_context_id=88888888-8888-4888-8888-888888888888
cross_context_id=77777777-7777-4777-8777-777777777777

bootstrap_member() {
  local subject=$1
  local context_id=$2
  local tenant_id=$3
  local workspace_id=$4
  "${compose[@]}" run --rm --no-deps -T \
    --env DEVELOPMENT_BOOTSTRAP_SUBJECT="$subject" \
    --env DEVELOPMENT_BOOTSTRAP_CONTEXT_ID="$context_id" \
    --env DEVELOPMENT_BOOTSTRAP_TENANT_ID="$tenant_id" \
    --env DEVELOPMENT_BOOTSTRAP_WORKSPACE_ID="$workspace_id" \
    --env DEVELOPMENT_BOOTSTRAP_IDENTITY_ISSUER=crypto-alert-v2-compose \
    development-bootstrap >/dev/null
}

bootstrap_member task8-peer-user "$peer_context_id" dev-tenant dev-workspace
bootstrap_member \
  task8-cross-tenant-user \
  "$cross_context_id" \
  task8-cross-tenant \
  task8-cross-tenant-workspace

private_volume="${PROJECT_NAME}_internal-jwt-private"
network_name="${PROJECT_NAME}_default"
probe_id="task8-$(date -u +%Y%m%dT%H%M%S)-$$"
client_probe_mount="$CLIENT_PROBE"
evidence_mount="$EVIDENCE_DIR"
if command -v cygpath >/dev/null 2>&1; then
  client_probe_mount="$(cygpath -m "$CLIENT_PROBE")"
  evidence_mount="$(cygpath -m "$EVIDENCE_DIR")"
fi
common_client=(
  env MSYS_NO_PATHCONV=1 docker run --rm -i
  --network "$network_name"
  --volume "$private_volume:/keys:ro"
  --volume "$evidence_mount:/evidence"
  --volume "$client_probe_mount:/probe.py:ro"
  --env AEGRA_PROBE_URL="http://langgraph-api:8000"
  --env AEGRA_PROBE_PRIVATE_KEY_FILE=//keys/private.pem
  --env AEGRA_PROBE_JWT_KID=compose-ephemeral
  --env AEGRA_PROBE_JWT_ISSUER=crypto-manual-alert-v2-compose
  --env AEGRA_PROBE_JWT_AUDIENCE=crypto-alert-agent-server
  --env AEGRA_PROBE_USER_ID=dev-user
  --env AEGRA_PROBE_TENANT_ID=dev-tenant
  --env AEGRA_PROBE_WORKSPACE_ID=dev-workspace
  --env AEGRA_PROBE_CONTEXT_ID="$owner_context_id"
  --env AEGRA_PROBE_PEER_USER_ID=task8-peer-user
  --env AEGRA_PROBE_PEER_CONTEXT_ID="$peer_context_id"
  --env AEGRA_PROBE_CROSS_USER_ID=task8-cross-tenant-user
  --env AEGRA_PROBE_CROSS_CONTEXT_ID="$cross_context_id"
  --env AEGRA_PROBE_IDENTITY_ISSUER=crypto-alert-v2-compose
  --env AEGRA_PROBE_ID="$probe_id"
  --env AEGRA_PROBE_STATE_FILE=//evidence/prepare.json
  --env AEGRA_PROBE_RESULT_FILE=//evidence/verify.json
  --env AEGRA_PROBE_MATRIX_FILE=//evidence/capability-matrix.json
  --env AEGRA_CANONICAL_STATE_FILE=//evidence/canonical-prepare.json
  --env AEGRA_CANONICAL_RESULT_FILE=//evidence/canonical-verify.json
  "$IMAGE"
  python //probe.py
)

"${common_client[@]}" matrix
[[ -s "$EVIDENCE_DIR/capability-matrix.json" ]] \
  || die 70 'Aegra capability matrix receipt is missing'

protocol_token="$("${common_client[@]}" issue-token)"
[[ "$protocol_token" == *.*.* ]] || die 70 'Protocol probe token issuance failed'
TASK8_AGENT_URL="$agent_url" \
TASK8_AGENT_TOKEN="$protocol_token" \
TASK8_SINGLE_GRAPH_ID=single_interrupt_fixture \
TASK8_BATCH_GRAPH_ID=multi_interrupt_fixture \
TASK8_EXPECTED_SDK_VERSION=1.9.25 \
TASK8_EXPECTED_PROTOCOL_VERSION=0.0.18 \
TASK8_EXPECTED_BATCH_INTERRUPTS=2 \
TASK8_SINGLE_SEED_MODE=none \
TASK8_BATCH_SEED_MODE=none \
TASK8_ALLOW_STATE_CHECKPOINT_FALLBACK=1 \
  node "$PROTOCOL_PROBE" >"$EVIDENCE_DIR/protocol-v2.log"
unset protocol_token

"${common_client[@]}" canonical-prepare
[[ -s "$EVIDENCE_DIR/canonical-prepare.json" ]] \
  || die 70 'Canonical checkpoint prepare receipt is missing'

"${common_client[@]}" prepare
[[ -s "$EVIDENCE_DIR/prepare.json" ]] || die 70 'Prepare manifest is missing'

docker kill "$container_before" >/dev/null
target_unavailable=0
for _ in $(seq 1 30); do
  if ! curl --fail --silent --max-time 1 "$agent_url/health" >/dev/null 2>&1; then
    target_unavailable=1
    break
  fi
  sleep 0.2
done
[[ "$target_unavailable" == "1" ]] || die 70 'Aegra URL never became unavailable'
docker start "$container_before" >/dev/null

target_recovered=0
for _ in $(seq 1 120); do
  if curl --fail --silent --max-time 2 "$agent_url/health" >/dev/null 2>&1; then
    target_recovered=1
    break
  fi
  sleep 1
done
[[ "$target_recovered" == "1" ]] || die 70 'Aegra URL did not recover'
container_after="$("${compose[@]}" ps -q langgraph-api)"
generation_after="$(docker inspect --format '{{.Id}}:{{.State.StartedAt}}' "$container_after")"
[[ "$generation_before" != "$generation_after" ]] \
  || die 70 'Aegra container generation did not change'

RECEIPT_FILE="$EVIDENCE_DIR/restart-receipt.json" \
RECEIPT_AGENT_URL="$agent_url" \
RECEIPT_PROJECT="$PROJECT_NAME" \
RECEIPT_CONTAINER_BEFORE="$container_before" \
RECEIPT_CONTAINER_AFTER="$container_after" \
RECEIPT_IMAGE_ID="$image_id" \
RECEIPT_GENERATION_BEFORE="$generation_before" \
RECEIPT_GENERATION_AFTER="$generation_after" \
  "$host_python" - <<'PY'
import json
import os
from pathlib import Path

payload = {
    "schema_version": "1.0",
    "restarted": True,
    "open_source": True,
    "runtime_kind": "aegra-self-hosted",
    "license": "Apache-2.0",
    "agent_server_url": os.environ["RECEIPT_AGENT_URL"],
    "compose_project": os.environ["RECEIPT_PROJECT"],
    "compose_service": "langgraph-api",
    "container_id_before": os.environ["RECEIPT_CONTAINER_BEFORE"],
    "container_id_after": os.environ["RECEIPT_CONTAINER_AFTER"],
    "image_id": os.environ["RECEIPT_IMAGE_ID"],
    "image_verifier_exit_code": 0,
    "target_unavailable_observed": True,
    "target_recovered_observed": True,
    "generation_before": os.environ["RECEIPT_GENERATION_BEFORE"],
    "generation_after": os.environ["RECEIPT_GENERATION_AFTER"],
}
Path(os.environ["RECEIPT_FILE"]).write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

"${common_client[@]}" verify
[[ -s "$EVIDENCE_DIR/verify.json" ]] || die 70 'Verification manifest is missing'

"${common_client[@]}" canonical-verify
[[ -s "$EVIDENCE_DIR/canonical-verify.json" ]] \
  || die 70 'Canonical checkpoint verification receipt is missing'

thread_id="$("$host_python" -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["thread_id"])' "$EVIDENCE_DIR/prepare.json")"
token="$("${common_client[@]}" issue-token)"
[[ "$token" == *.*.* ]] || die 70 'Probe token issuance failed'
AEGRA_PROBE_URL="$agent_url" \
AEGRA_PROBE_THREAD_ID="$thread_id" \
AEGRA_PROBE_TOKEN="$token" \
  node "$REPLAY_PROBE" >"$EVIDENCE_DIR/replay.json"
unset token

runtime_versions="$(docker run --rm --entrypoint python "$IMAGE" -c 'import importlib.metadata as m,json; print(json.dumps({name:m.version(name) for name in ("aegra-api","aegra-cli","langgraph","langgraph-sdk")}))')"
printf '%s\n' "$runtime_versions" >"$EVIDENCE_DIR/runtime-versions.json"

"${compose[@]}" logs --no-color langgraph-api 2>&1 \
  | sed -E \
      -e 's#(postgres(ql)?(\+asyncpg)?://[^:]+:)[^@]+@#\1[REDACTED]@#Ig' \
      -e 's/(Bearer )[A-Za-z0-9._~+\/-]+/\1[REDACTED]/g' \
  >"$EVIDENCE_DIR/aegra.log"
rg -q 'Reaping crashed worker runs' "$EVIDENCE_DIR/aegra.log" \
  || die 70 'Aegra log omitted the lease reaper event'
rg -q 'Re-enqueued recovered run' "$EVIDENCE_DIR/aegra.log" \
  || die 70 'Aegra log omitted the recovered re-enqueue event'

MANIFEST_EVIDENCE_DIR="$EVIDENCE_DIR" \
MANIFEST_CANDIDATE_SHA="$(git -C "$ROOT_DIR" rev-parse HEAD)" \
MANIFEST_IMAGE_ID="$image_id" \
  "$host_python" - <<'PY'
import json
import os
from pathlib import Path

root = Path(os.environ["MANIFEST_EVIDENCE_DIR"])
payload = {
    "schema_version": "1.0",
    "result": "passed",
    "scope": "task8-local-aegra-redis-worker-recovery",
    "candidate_sha": os.environ["MANIFEST_CANDIDATE_SHA"],
    "image_id": os.environ["MANIFEST_IMAGE_ID"],
    "prepare": json.loads((root / "prepare.json").read_text(encoding="utf-8")),
    "verify": json.loads((root / "verify.json").read_text(encoding="utf-8")),
    "canonical_prepare": json.loads(
        (root / "canonical-prepare.json").read_text(encoding="utf-8")
    ),
    "canonical_verify": json.loads(
        (root / "canonical-verify.json").read_text(encoding="utf-8")
    ),
    "replay": json.loads((root / "replay.json").read_text(encoding="utf-8")),
    "capability_matrix": json.loads(
        (root / "capability-matrix.json").read_text(encoding="utf-8")
    ),
    "limitations": [
        "local self-hosted evidence is not hosted deployment evidence",
        "QA-only graph fixture does not prove the real provider Product graph",
        "canonical checkpoint uses controlled post-provider state and does not prove provider execution or Product admission",
        "Aegra 0.9.24 emitted no Protocol checkpoint envelope; QA used the official Thread state checkpoint ID",
        "provisioned local Product memberships do not prove hosted OIDC or a production tenant deployment",
        "dirty working-tree evidence is not an immutable release candidate",
    ],
}
(root / "evidence-manifest.json").write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

(
  cd "$EVIDENCE_DIR"
  sha256sum \
    capability-matrix.json protocol-v2.log canonical-prepare.json canonical-verify.json \
    prepare.json verify.json replay.json restart-receipt.json \
    runtime-versions.json aegra.log evidence-manifest.json >artifact-sha256.txt
)
EVIDENCE_FINALIZED=1

printf 'Aegra Redis worker kill/reaper recovery and Protocol since replay passed\n'
