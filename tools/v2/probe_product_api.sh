#!/usr/bin/env bash
set -euo pipefail

STACK_OWNED=0
TEMP_DIR=""
ROOT_DIR=""
STOP_SCRIPT=""
EVIDENCE_DIR=
EVIDENCE_READY=0
PROOF_RESULT="failed"
FAILURE_REASON="unhandled_failure"
EXPECT_CONTRACT_FAILURE=0
EXPECTED_RED_OBSERVED=0
COMPOSE_PROJECT_NAME="crypto-manual-alert-v2"
AGENT_CONTAINER_BEFORE=""
AGENT_CONTAINER_AFTER=""
AGENT_IMAGE_ID=""
LOCKED_BASE_IMAGE=""
SOURCE_HEAD_SHA=""
SOURCE_WORKTREE_DIRTY="unknown"
PRODUCT_TASK_ID=""
PRODUCT_AGENT_THREAD_ID=""
PRODUCT_AGENT_RUN_ID=""

redact_file() {
  local source="$1"
  local destination="$2"
  sed -E \
    -e 's/(Bearer )[A-Za-z0-9._~+\/-]+/\1[REDACTED]/g' \
    -e 's/sk-[A-Za-z0-9_-]{12,}/[REDACTED]/g' \
    -e 's/((LANGGRAPH_CLOUD_LICENSE_KEY|LANGSMITH_API_KEY|OPENAI_API_KEY|api[_-]?key)[=:][[:space:]]*)[^[:space:],]+/\1[REDACTED]/Ig' \
    "$source" >"$destination"
}

write_evidence_status() {
  local exit_code="$1"
  local completed_at
  completed_at="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  jq -n \
    --arg schema_version "1.0" \
    --arg result "$PROOF_RESULT" \
    --arg failure_reason "$FAILURE_REASON" \
    --arg completed_at "$completed_at" \
    --argjson exit_code "$exit_code" \
    --argjson expected_contract_red "$EXPECT_CONTRACT_FAILURE" \
    --argjson expected_red_observed "$EXPECTED_RED_OBSERVED" \
    '{schema_version:$schema_version,result:$result,exit_code:$exit_code,failure_reason:(if $failure_reason == "" then null else $failure_reason end),completed_at:$completed_at,expected_contract_red:($expected_contract_red == 1),expected_red_observed:($expected_red_observed == 1)}' \
    >"$EVIDENCE_DIR/run-status.json"
}

write_evidence_manifest() {
  local hash_file="$EVIDENCE_DIR/artifact-sha256.txt"
  local artifact_json
  local receipt_sha256 before_sha256 after_sha256 openapi_sha256
  local version_sha256 contract_log_sha256 node_log_sha256
  local prepare_log_sha256 verify_log_sha256
  : >"$hash_file"
  shopt -s nullglob
  for path in "$EVIDENCE_DIR"/*; do
    if [[ ! -f "$path" ]]; then
      continue
    fi
    case "$(basename "$path")" in
      artifact-sha256.txt|evidence-manifest.json)
        continue
        ;;
    esac
    digest_output="$(shasum -a 256 "$path")"
    printf '%s  %s\n' "${digest_output%% *}" "$(basename "$path")" >>"$hash_file"
  done
  shopt -u nullglob
  artifact_json="$(jq -Rn '[inputs | capture("^(?<sha256>[0-9a-f]{64})  (?<file>.+)$")]' <"$hash_file")"
  receipt_sha256="$(artifact_hash "$EVIDENCE_DIR/restart-receipt.json")"
  before_sha256="$(artifact_hash "$EVIDENCE_DIR/container-before.json")"
  after_sha256="$(artifact_hash "$EVIDENCE_DIR/container-after.json")"
  openapi_sha256="$(artifact_hash "$EVIDENCE_DIR/agent-openapi.json")"
  version_sha256="$(artifact_hash "$EVIDENCE_DIR/runtime-versions.json")"
  contract_log_sha256="$(artifact_hash "$EVIDENCE_DIR/contract.log")"
  node_log_sha256="$(artifact_hash "$EVIDENCE_DIR/node.log")"
  prepare_log_sha256="$(artifact_hash "$EVIDENCE_DIR/prepare.log")"
  verify_log_sha256="$(artifact_hash "$EVIDENCE_DIR/verify.log")"
  jq -n \
    --arg schema_version "1.0" \
    --arg result "$PROOF_RESULT" \
    --arg compose_project "$COMPOSE_PROJECT_NAME" \
    --arg compose_service "langgraph-api" \
    --arg agent_server_url "${AGENT_URL:-}" \
    --arg container_before "$AGENT_CONTAINER_BEFORE" \
    --arg container_after "$AGENT_CONTAINER_AFTER" \
    --arg image_id "$AGENT_IMAGE_ID" \
    --arg locked_base_image "$LOCKED_BASE_IMAGE" \
    --arg candidate_sha "$SOURCE_HEAD_SHA" \
    --arg source_worktree_dirty "$SOURCE_WORKTREE_DIRTY" \
    --arg product_task_id "$PRODUCT_TASK_ID" \
    --arg product_agent_thread_id "$PRODUCT_AGENT_THREAD_ID" \
    --arg product_agent_run_id "$PRODUCT_AGENT_RUN_ID" \
    --arg receipt_sha256 "$receipt_sha256" \
    --arg before_sha256 "$before_sha256" \
    --arg after_sha256 "$after_sha256" \
    --arg openapi_sha256 "$openapi_sha256" \
    --arg version_sha256 "$version_sha256" \
    --arg contract_log_sha256 "$contract_log_sha256" \
    --arg node_log_sha256 "$node_log_sha256" \
    --arg prepare_log_sha256 "$prepare_log_sha256" \
    --arg verify_log_sha256 "$verify_log_sha256" \
    --argjson artifacts "$artifact_json" \
    '{schema_version:$schema_version,result:$result,proof_scope:"task8-local-licensed-persistent-runtime",compose:{project:$compose_project,service:$compose_service,agent_server_url:$agent_server_url,container_id_before:(if $container_before == "" then null else $container_before end),container_id_after:(if $container_after == "" then null else $container_after end)},source:{candidate_sha:(if $candidate_sha == "" then null else $candidate_sha end),worktree_dirty:($source_worktree_dirty == "true"),immutable_candidate:false},image:{image_digest:(if $image_id == "" then null else $image_id end),locked_base_image:(if $locked_base_image == "" then null else $locked_base_image end)},product_admission:{task_id:(if $product_task_id == "" then null else $product_task_id end),agent_thread_id:(if $product_agent_thread_id == "" then null else $product_agent_thread_id end),agent_run_id:(if $product_agent_run_id == "" then null else $product_agent_run_id end)},durability_modes:["sync","exit"],required_artifact_sha256:{receipt_sha256:$receipt_sha256,before_sha256:$before_sha256,after_sha256:$after_sha256,openapi_sha256:$openapi_sha256,version_sha256:$version_sha256,contract_log_sha256:$contract_log_sha256,node_log_sha256:$node_log_sha256,prepare_log_sha256:$prepare_log_sha256,verify_log_sha256:$verify_log_sha256},artifacts:$artifacts,limitations:["local Compose evidence is not hosted deployment evidence","dirty working-tree evidence is not an immutable release candidate","manifest self-hash is intentionally excluded"]}' \
    >"$EVIDENCE_MANIFEST_FILE"
}

artifact_hash() {
  local path="$1"
  local digest_output
  if [[ ! -s "$path" ]]; then
    printf ''
    return
  fi
  digest_output="$(shasum -a 256 "$path")"
  printf '%s' "${digest_output%% *}"
}

capture_compose_logs() {
  if [[ "$STACK_OWNED" != "1" || "$EVIDENCE_READY" != "1" ]]; then
    return
  fi
  local raw_log="$TEMP_DIR/compose.log.raw"
  if docker compose \
    --project-name "$COMPOSE_PROJECT_NAME" \
    --project-directory "$ROOT_DIR" \
    --file "$ROOT_DIR/docker-compose.yml" \
    logs --no-color >"$raw_log" 2>&1; then
    redact_file "$raw_log" "$EVIDENCE_DIR/compose.log"
  else
    redact_file "$raw_log" "$EVIDENCE_DIR/compose-log-error.log"
  fi
}

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  capture_compose_logs || true
  if [[ "$STACK_OWNED" == "1" && -n "$STOP_SCRIPT" ]]; then
    if ! "$STOP_SCRIPT" --volumes; then
      printf 'Task 8 cleanup failed for Compose project %s\n' \
        "$COMPOSE_PROJECT_NAME" >&2
      if ((status == 0)); then
        status=70
        PROOF_RESULT="failed"
        FAILURE_REASON="compose_cleanup_failed"
      fi
    fi
  fi
  if [[ "$EVIDENCE_READY" == "1" ]] && command -v jq >/dev/null 2>&1; then
    if ((status != 0)); then
      PROOF_RESULT="failed"
    fi
    write_evidence_status "$status" || true
    write_evidence_manifest || true
  fi
  if [[ -n "$TEMP_DIR" ]]; then
    rm -rf "$TEMP_DIR"
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

usage() {
  printf 'Usage: %s --evidence-dir PATH [--expect-contract-failure]\n' "$0"
}

die() {
  local status="$1"
  shift
  FAILURE_REASON="$*"
  printf '%s\n' "$*" >&2
  exit "$status"
}

while (($# > 0)); do
  case "$1" in
    --evidence-dir)
      if (($# < 2)) || [[ -z "$2" ]]; then
        die 64 '--evidence-dir requires a non-empty path'
      fi
      if [[ -n "$EVIDENCE_DIR" ]]; then
        die 64 '--evidence-dir may only be supplied once'
      fi
      EVIDENCE_DIR="$2"
      shift 2
      ;;
    --expect-contract-failure)
      EXPECT_CONTRACT_FAILURE=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      usage >&2
      die 64 "Unknown Task 8 probe option: $1"
      ;;
  esac
done
if [[ -z "$EVIDENCE_DIR" ]]; then
  usage >&2
  die 64 'Task 8 requires an explicit --evidence-dir so machine evidence survives cleanup'
fi
if [[ -e "$EVIDENCE_DIR" && ! -d "$EVIDENCE_DIR" ]]; then
  die 64 '--evidence-dir must name a directory'
fi
mkdir -p "$EVIDENCE_DIR"
if [[ -n "$(ls -A "$EVIDENCE_DIR")" ]]; then
  die 64 '--evidence-dir must be empty to prevent evidence from different runs being mixed'
fi
EVIDENCE_DIR="$(cd "$EVIDENCE_DIR" && pwd -P)"
EVIDENCE_READY=1
EVIDENCE_MANIFEST_FILE="$EVIDENCE_DIR/evidence-manifest.json"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
START_SCRIPT="$ROOT_DIR/tools/v2/start_integration_stack.sh"
STOP_SCRIPT="$ROOT_DIR/tools/v2/stop_integration_stack.sh"
NODE_PROBE="$ROOT_DIR/tools/v2/probe_protocol_v2.mjs"
IMAGE_VERIFIER="$ROOT_DIR/tools/v2/verify_agent_image.sh"
IMAGE_LOCK="$ROOT_DIR/deploy/agent-server-image.lock"
AGENT_PORT="${AGENT_SERVER_PORT:-8123}"
AGENT_URL="http://127.0.0.1:$AGENT_PORT"
ASSISTANT_ID="${TASK8_ASSISTANT_ID:-multi_interrupt_fixture}"
TEMP_DIR="$(mktemp -d -t crypto-alert-task8-probe.XXXXXX)"
AUTH_HEADER_FILE="$TEMP_DIR/authorization.header"
PRODUCT_AUTH_HEADER_FILE="$TEMP_DIR/product-authorization.header"
PRODUCT_REQUEST_FILE="$TEMP_DIR/product-request.json"
PRODUCT_CURRENT_FILE="$TEMP_DIR/product-current.json"
CONTRACT_RAW_LOG="$TEMP_DIR/contract.log.raw"
NODE_RAW_LOG="$TEMP_DIR/node.log.raw"
START_RAW_LOG="$TEMP_DIR/start.log.raw"
IMAGE_VERIFY_RAW_LOG="$TEMP_DIR/image-verifier.log.raw"

for command_name in docker curl git jq node rg shasum uv sed; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    die 69 "Required Task 8 probe tool is unavailable: $command_name"
  fi
done
if ! docker compose version >/dev/null 2>&1; then
  die 69 'Docker Compose v2 is required for the Task 8 integration probe'
fi
if ! docker info >/dev/null 2>&1; then
  die 69 'Docker is installed but its daemon is unavailable'
fi
for required_file in "$START_SCRIPT" "$STOP_SCRIPT" "$NODE_PROBE" "$IMAGE_VERIFIER"; do
  if [[ ! -x "$required_file" ]]; then
    die 66 "Required executable is missing: $required_file"
  fi
done
if [[ -z "${LANGGRAPH_CLOUD_LICENSE_KEY:-}" && -z "${LANGSMITH_API_KEY:-}" ]]; then
  die 78 'Task 8 requires LANGGRAPH_CLOUD_LICENSE_KEY or a LANGSMITH_API_KEY with LangGraph Cloud access; the value will not be printed'
fi
if [[ ! "$AGENT_PORT" =~ ^[0-9]+$ ]] || ((AGENT_PORT < 1 || AGENT_PORT > 65535)); then
  die 64 'AGENT_SERVER_PORT must be an integer between 1 and 65535'
fi
if [[ -z "$ASSISTANT_ID" ]]; then
  die 64 'TASK8_ASSISTANT_ID must not be empty'
fi

CONTRACT_TESTS=(
  tests/contract/test_agent_server_client.py
  tests/contract/test_product_api.py
  tests/contract/test_product_agent_stream.py
  tests/contract/test_agent_server_protocol.py
  tests/contract/test_protocol_v2_capabilities.py
)
LIVE_TEST_FILES=(
  tests/integration/test_run_durability.py
  tests/integration/test_agent_server_interrupt_routing.py
)
for test_file in "${CONTRACT_TESTS[@]}" "${LIVE_TEST_FILES[@]}"; do
  if [[ ! -f "$BACKEND_DIR/$test_file" ]]; then
    die 66 "Required Task 8 test file is missing: backend/$test_file"
  fi
done
if [[ ! -d "$FRONTEND_DIR/node_modules/@langchain/langgraph-sdk" ]]; then
  die 69 'The official JavaScript SDK is unavailable; run npm ci in frontend first'
fi

SOURCE_HEAD_SHA="$(cd "$ROOT_DIR" && git rev-parse --verify HEAD)"
if [[ -n "$(git -C "$ROOT_DIR" status --porcelain --untracked-files=normal)" ]]; then
  SOURCE_WORKTREE_DIRTY="true"
else
  SOURCE_WORKTREE_DIRTY="false"
fi
IFS= read -r LOCKED_BASE_IMAGE <"$IMAGE_LOCK"
if [[ ! "$LOCKED_BASE_IMAGE" =~ ^langchain/langgraph-api@sha256:[0-9a-f]{64}$ ]]; then
  die 65 'Task 8 Agent Server image lock is invalid'
fi

existing_containers="$(docker ps -aq \
  --filter "label=com.docker.compose.project=$COMPOSE_PROJECT_NAME")"
if [[ -n "$existing_containers" ]]; then
  die 69 "Compose project $COMPOSE_PROJECT_NAME already has containers; stop that stack before running the hermetic Task 8 probe"
fi

printf 'Starting Task 8 integration topology with persistent evidence\n'
printf 'compose_project=%s agent_url=%s assistant=%s evidence_dir=%s\n' \
  "$COMPOSE_PROJECT_NAME" "$AGENT_URL" "$ASSISTANT_ID" "$EVIDENCE_DIR"
STACK_OWNED=1
export LANGGRAPH_CONFIG_FILE="$BACKEND_DIR/langgraph.multi-interrupt.json"
export V2_STACK_PROFILE=task8-multi-interrupt-qa
set +e
"$START_SCRIPT" >"$START_RAW_LOG" 2>&1
start_status=$?
set -e
redact_file "$START_RAW_LOG" "$EVIDENCE_DIR/start.log"
if ((start_status != 0)); then
  die 70 "Task 8 integration topology failed to start with status $start_status"
fi

compose=(
  docker compose
  --project-name "$COMPOSE_PROJECT_NAME"
  --project-directory "$ROOT_DIR"
  --file "$ROOT_DIR/docker-compose.yml"
)
"${compose[@]}" ps --format '{{.Service}} {{.ID}}' \
  >"$EVIDENCE_DIR/compose-identifiers-before.txt"
if [[ ! -s "$EVIDENCE_DIR/compose-identifiers-before.txt" ]]; then
  die 69 'Integration topology started without discoverable Compose containers'
fi
AGENT_CONTAINER_BEFORE="$("${compose[@]}" ps -q langgraph-api)"
if [[ -z "$AGENT_CONTAINER_BEFORE" ]]; then
  die 69 'Task 8 could not identify the licensed Agent Server container'
fi
docker inspect "$AGENT_CONTAINER_BEFORE" | jq '.[0] | {container_id:.Id,name:.Name,image_reference:.Config.Image,image_id:.Image,started_at:.State.StartedAt,restart_count:.RestartCount,health:(.State.Health.Status // "missing"),ports:.NetworkSettings.Ports["8000/tcp"],compose_project:.Config.Labels["com.docker.compose.project"],compose_service:.Config.Labels["com.docker.compose.service"]}' \
  >"$EVIDENCE_DIR/container-before.json"
compose_agent_target="$("${compose[@]}" port langgraph-api 8000)"
if [[ -z "$compose_agent_target" ]]; then
  die 69 'Licensed Agent Server container has no loopback-published 8000/tcp port'
fi
expected_agent_url="http://$compose_agent_target"
if [[ "$AGENT_URL" != "$expected_agent_url" ]]; then
  die 65 "TASK8_AGENT_URL must resolve to the owned Compose langgraph-api binding $expected_agent_url"
fi
if [[ "$(jq -r '.compose_project' "$EVIDENCE_DIR/container-before.json")" != "$COMPOSE_PROJECT_NAME" ]] || \
   [[ "$(jq -r '.compose_service' "$EVIDENCE_DIR/container-before.json")" != "langgraph-api" ]]; then
  die 65 'Agent Server container identity is not bound to the owned Compose service'
fi
AGENT_IMAGE_ID="$(jq -r '.image_id' "$EVIDENCE_DIR/container-before.json")"
agent_image_reference="$(jq -r '.image_reference' "$EVIDENCE_DIR/container-before.json")"
docker image inspect "$agent_image_reference" | jq '.[0] | {id:.Id,repo_tags:.RepoTags,repo_digests:.RepoDigests,created:.Created,architecture:.Architecture,os:.Os}' \
  >"$EVIDENCE_DIR/agent-image.json"

set +e
"$IMAGE_VERIFIER" "$LOCKED_BASE_IMAGE" "$agent_image_reference" \
  --allow-multi-interrupt-fixture >"$IMAGE_VERIFY_RAW_LOG" 2>&1
image_verify_status=$?
set -e
redact_file "$IMAGE_VERIFY_RAW_LOG" "$EVIDENCE_DIR/image-verifier.log"
if ((image_verify_status != 0)); then
  die 70 "Locked Agent Server image verification failed with status $image_verify_status"
fi
"${compose[@]}" exec -T langgraph-api python -c '
import importlib.metadata
import json

names = (
    "langgraph-api",
    "langgraph",
    "langgraph-runtime-inmem",
    "langchain",
    "langgraph-sdk",
)
print(json.dumps({name: importlib.metadata.version(name) for name in names}, sort_keys=True))
' >"$EVIDENCE_DIR/runtime-versions.json"

issue_token() {
  local user_id="$1"
  local identity_issuer="$2"
  "${compose[@]}" exec -T \
    -e TASK8_TOKEN_USER_ID="$user_id" \
    -e TASK8_TOKEN_IDENTITY_ISSUER="$identity_issuer" \
    command-worker python -c '
import os

from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.auth.worker_authorization import create_agent_server_authorization_provider
from crypto_alert_v2.config import get_settings

actor = ActorContext(
    tenant_id="dev-tenant",
    workspace_id="dev-workspace",
    user_id=os.environ["TASK8_TOKEN_USER_ID"],
    identity_issuer=os.environ["TASK8_TOKEN_IDENTITY_ISSUER"],
    roles=("member",),
    permissions=("analysis:read", "analysis:write"),
)
authorization = create_agent_server_authorization_provider(get_settings())(actor)
print(authorization.removeprefix("Bearer "))
'
}

refresh_probe_token() {
  TASK8_AGENT_TOKEN="$(issue_token task8-probe legacy)"
  if [[ -z "$TASK8_AGENT_TOKEN" || "$TASK8_AGENT_TOKEN" != *.*.* ]]; then
    die 70 'The integration topology did not issue a valid short-lived Task 8 token'
  fi
  export TASK8_AGENT_TOKEN
  umask 077
  printf 'Authorization: Bearer %s\n' "$TASK8_AGENT_TOKEN" >"$AUTH_HEADER_FILE"
}

refresh_product_token() {
  TASK8_PRODUCT_TOKEN="$(issue_token dev-user crypto-alert-v2-compose)"
  if [[ -z "$TASK8_PRODUCT_TOKEN" || "$TASK8_PRODUCT_TOKEN" != *.*.* ]]; then
    die 70 'The integration topology did not issue a valid Product admission token'
  fi
  umask 077
  printf 'Authorization: Bearer %s\n' "$TASK8_PRODUCT_TOKEN" \
    >"$PRODUCT_AUTH_HEADER_FILE"
}

assert_junit_has_no_skip_or_error() {
  local report="$1"
  local label="$2"
  TASK8_JUNIT_FILE="$report" TASK8_JUNIT_LABEL="$label" \
    uv run --directory "$BACKEND_DIR" --frozen python - <<'PY'
import os
from xml.etree import ElementTree

root = ElementTree.parse(os.environ["TASK8_JUNIT_FILE"]).getroot()
cases = list(root.iter("testcase"))
if not cases:
    raise SystemExit(f"{os.environ['TASK8_JUNIT_LABEL']} collected no tests")
invalid = []
for case in cases:
    outcomes = [name for name in ("failure", "error", "skipped") if case.find(name) is not None]
    if outcomes:
        identity = f"{case.get('classname', '')}::{case.get('name', '')}".strip(":")
        invalid.append(f"{identity} ({','.join(outcomes)})")
if invalid:
    raise SystemExit(
        f"{os.environ['TASK8_JUNIT_LABEL']} is not fully proved: " + "; ".join(invalid)
    )
PY
}

assert_expected_contract_red() {
  TASK8_JUNIT_FILE="$1" uv run --directory "$BACKEND_DIR" --frozen python - <<'PY'
import os
import re
from xml.etree import ElementTree

root = ElementTree.parse(os.environ["TASK8_JUNIT_FILE"]).getroot()
failures = []
errors = []
skipped = []
for case in root.iter("testcase"):
    name = f"{case.get('classname', '')}::{case.get('name', '')}".strip(":")
    failures.extend((name, "".join(item.itertext())) for item in case.findall("failure"))
    errors.extend(name for _item in case.findall("error"))
    skipped.extend(name for _item in case.findall("skipped"))
if skipped or errors or not failures:
    raise SystemExit("expected an assertion RED with zero setup errors and zero skip")
infrastructure = re.compile(
    r"connection refused|failed to connect|connecterror|name or service not known|"
    r"temporary failure in name resolution|no such file or directory|error collecting",
    re.IGNORECASE,
)
if any(infrastructure.search(detail) for _name, detail in failures):
    raise SystemExit("expected contract RED was caused by infrastructure failure")
capability_gap = re.compile(r"CAPABILITY GAP \[[^]]+\]:")
if any(capability_gap.search(detail) is None for _name, detail in failures):
    raise SystemExit(
        "every expected contract RED must identify an explicit CAPABILITY GAP [name]:"
    )
print("Expected Task 8 capability assertion RED verified:")
for name, _detail in failures:
    print(f"- {name}")
PY
}

refresh_probe_token
export TASK8_AGENT_URL="$AGENT_URL"
export TASK8_ASSISTANT_ID="$ASSISTANT_ID"
export TASK8_EXPECTED_SDK_VERSION="${TASK8_EXPECTED_SDK_VERSION:-1.9.25}"
export TASK8_PROBE_TIMEOUT_MS="${TASK8_PROBE_TIMEOUT_MS:-30000}"
export TASK8_EXPECTED_BATCH_INTERRUPTS="${TASK8_EXPECTED_BATCH_INTERRUPTS:-2}"
export TASK8_PROTOCOL_SEED_MODE=none
export TASK8_OPENAPI_FILE="$EVIDENCE_DIR/agent-openapi.json"
export AGENT_SERVER_URL="$AGENT_URL"

if ! curl --fail --silent --show-error --max-time 10 \
  "$AGENT_URL/openapi.json" --output "$EVIDENCE_DIR/agent-openapi.json"; then
  die 69 "Agent Server OpenAPI endpoint is unavailable at $AGENT_URL/openapi.json"
fi
if ! jq -e '
  .paths["/assistants/search"].post
  and .paths["/threads"].post
  and .paths["/threads/{thread_id}/runs"].post
  and .paths["/threads/{thread_id}/commands"].post
  and .paths["/threads/{thread_id}/stream/events"].post
' "$EVIDENCE_DIR/agent-openapi.json" >/dev/null; then
  die 65 'Agent Server OpenAPI is missing a required official route'
fi
jq '{openapi,info}' "$EVIDENCE_DIR/agent-openapi.json" \
  >"$EVIDENCE_DIR/openapi-version.json"
if ! curl --fail --silent --show-error --max-time 10 \
  --header "@$AUTH_HEADER_FILE" \
  "$AGENT_URL/app/system/readiness" \
  --output "$EVIDENCE_DIR/agent-readiness.json"; then
  die 69 'Authenticated Agent extension readiness endpoint is unavailable'
fi
if ! jq -e '.status == "ready" and (.selected_provider | type == "string")' \
  "$EVIDENCE_DIR/agent-readiness.json" >/dev/null; then
  die 65 'Agent extension readiness returned an invalid or non-ready payload'
fi
if ! curl --fail --silent --show-error --max-time 10 \
  --header "@$AUTH_HEADER_FILE" \
  "$AGENT_URL/app/api/v2/readiness" \
  --output "$EVIDENCE_DIR/product-readiness.json"; then
  die 69 'Authenticated Product readiness endpoint is unavailable'
fi
if ! jq -e '.status == "ok" and .version == "2.0.0"' \
  "$EVIDENCE_DIR/product-readiness.json" >/dev/null; then
  die 65 'Product readiness returned an invalid payload'
fi
printf 'Official OpenAPI and both authenticated readiness boundaries verified\n'

refresh_probe_token
export TASK8_LIVE_AGENT_PROTOCOL=1
export TASK8_LIVE_AGENT_SERVER_URL="$AGENT_URL"
export TASK8_LIVE_AGENT_SERVER_AUTHORIZATION="Bearer $TASK8_AGENT_TOKEN"
set +e
(
  cd "$BACKEND_DIR"
  uv run --frozen pytest "${CONTRACT_TESTS[@]}" -q \
    --junitxml="$EVIDENCE_DIR/contract.xml"
) >"$CONTRACT_RAW_LOG" 2>&1
contract_status=$?
set -e
redact_file "$CONTRACT_RAW_LOG" "$EVIDENCE_DIR/contract.log"
CONTRACT_JUNIT="$EVIDENCE_DIR/contract.xml"
if [[ "$EXPECT_CONTRACT_FAILURE" == "1" ]]; then
if ((contract_status != 0)) && [[ "$EXPECT_CONTRACT_FAILURE" == "1" ]]; then
    if ((contract_status != 1)); then
      die 70 "Expected Task 8 assertion RED, got pytest status $contract_status"
    fi
    assert_expected_contract_red "$CONTRACT_JUNIT"
    EXPECTED_RED_OBSERVED=1
else
    assert_junit_has_no_skip_or_error "$CONTRACT_JUNIT" 'Task 8 contract suite'
fi
elif ((contract_status == 0)); then
  assert_junit_has_no_skip_or_error "$CONTRACT_JUNIT" 'Task 8 contract suite'
else
  die 70 "Task 8 contract suite failed with exit status $contract_status"
fi

refresh_probe_token
set +e
node "$NODE_PROBE" >"$NODE_RAW_LOG" 2>&1
node_status=$?
set -e
redact_file "$NODE_RAW_LOG" "$EVIDENCE_DIR/node.log"
if ((node_status != 0)); then
  if [[ "$EXPECT_CONTRACT_FAILURE" != "1" ]] || \
     ! rg -q 'CAPABILITY GAP:' "$EVIDENCE_DIR/node.log"; then
    die 70 "Task 8 official Protocol v2 probe failed with status $node_status"
  fi
  EXPECTED_RED_OBSERVED=1
fi

refresh_product_token
product_idempotency_key="task8-product-$(date -u +%Y%m%dT%H%M%S)-$$"
jq -n \
  --arg symbol BTC-USDT-SWAP \
  --arg horizon 4h \
  --arg query_text 'Task 8 licensed Product admission and restart persistence proof.' \
  '{symbol:$symbol,horizon:$horizon,query_text:$query_text,notify:false}' \
  >"$PRODUCT_REQUEST_FILE"
product_http_status="$(curl --silent --show-error --max-time 20 \
  --request POST \
  --header "@$PRODUCT_AUTH_HEADER_FILE" \
  --header 'Content-Type: application/json' \
  --header "Idempotency-Key: $product_idempotency_key" \
  --data-binary "@$PRODUCT_REQUEST_FILE" \
  --output "$EVIDENCE_DIR/product-admission.json" \
  --write-out '%{http_code}' \
  "$AGENT_URL/app/api/v2/analysis")"
if [[ "$product_http_status" != "202" ]]; then
  die 70 "Product analysis admission returned HTTP $product_http_status instead of 202"
fi
PRODUCT_TASK_ID="$(jq -r '.task_id // empty' "$EVIDENCE_DIR/product-admission.json")"
if [[ -z "$PRODUCT_TASK_ID" ]]; then
  die 70 'Product analysis admission did not return a Task ID'
fi
product_bound=0
for attempt in $(seq 1 90); do
  if ((attempt % 20 == 0)); then
    refresh_product_token
  fi
  if curl --fail --silent --show-error --max-time 5 \
    --header "@$PRODUCT_AUTH_HEADER_FILE" \
    "$AGENT_URL/app/api/v2/tasks/$PRODUCT_TASK_ID" \
    --output "$PRODUCT_CURRENT_FILE" && \
    jq -e --arg task_id "$PRODUCT_TASK_ID" '
      .task_id == $task_id
      and (.agent_stream.thread_id | type == "string")
      and (.agent_stream.run_id | type == "string")
    ' "$PRODUCT_CURRENT_FILE" >/dev/null; then
    cp "$PRODUCT_CURRENT_FILE" "$EVIDENCE_DIR/product-task-before-restart.json"
    product_bound=1
    break
  fi
  sleep 1
done
if [[ "$product_bound" != "1" ]]; then
  die 70 'Product admission did not bind a persisted official Agent Thread/Run before the deadline'
fi
PRODUCT_AGENT_THREAD_ID="$(jq -r '.agent_stream.thread_id' "$EVIDENCE_DIR/product-task-before-restart.json")"
PRODUCT_AGENT_RUN_ID="$(jq -r '.agent_stream.run_id' "$EVIDENCE_DIR/product-task-before-restart.json")"
if ! curl --fail --silent --show-error --max-time 10 \
  --header "@$PRODUCT_AUTH_HEADER_FILE" \
  "$AGENT_URL/threads/$PRODUCT_AGENT_THREAD_ID/runs/$PRODUCT_AGENT_RUN_ID" \
  --output "$EVIDENCE_DIR/product-agent-run-before-restart.json"; then
  die 70 'Product-admitted official Agent Run was not readable before restart'
fi

export LICENSED_AGENT_SERVER_TESTS=1
export LICENSED_AGENT_SERVER_LICENSE_ASSERTION=1
export LICENSED_AGENT_SERVER_RUNTIME_KIND=licensed-persistent
export LICENSED_AGENT_SERVER_URL="$AGENT_URL"
export LICENSED_AGENT_SERVER_TEST_ASSISTANT=multi_interrupt_fixture
export LICENSED_AGENT_SERVER_TEST_TENANT=dev-tenant
export LICENSED_AGENT_SERVER_TEST_WORKSPACE=dev-workspace
export LICENSED_AGENT_SERVER_TEST_USER=task8-probe
export LICENSED_AGENT_SERVER_TEST_IDENTITY_ISSUER=legacy
export LICENSED_AGENT_SERVER_TIMEOUT_SECONDS=120

for durability in sync exit; do
  refresh_probe_token
  export LICENSED_AGENT_SERVER_TOKEN="$TASK8_AGENT_TOKEN"
  export LICENSED_AGENT_SERVER_PROOF_PHASE=prepare
  export LICENSED_AGENT_SERVER_TEST_DURABILITY="$durability"
  export LICENSED_AGENT_SERVER_PROOF_STATE_FILE="$EVIDENCE_DIR/licensed-$durability-state.json"
  PREPARE_JUNIT="$EVIDENCE_DIR/prepare-$durability.xml"
  prepare_raw_log="$TEMP_DIR/prepare-$durability.log.raw"
  set +e
  (
    cd "$BACKEND_DIR"
    uv run --frozen pytest \
      tests/integration/test_run_durability.py::test_licensed_runtime_prepare_acknowledged_restart_state \
      -q --junitxml="$PREPARE_JUNIT"
  ) >"$prepare_raw_log" 2>&1
  prepare_status=$?
  set -e
  redact_file "$prepare_raw_log" "$EVIDENCE_DIR/prepare-$durability.log"
  if ((prepare_status != 0)); then
    die 70 "Task 8 pre-restart durability=$durability phase failed with status $prepare_status"
  fi
  assert_junit_has_no_skip_or_error "$PREPARE_JUNIT" \
    "Task 8 pre-restart durability=$durability phase"
  if [[ ! -s "$EVIDENCE_DIR/licensed-$durability-state.json" ]]; then
    die 70 "Task 8 durability=$durability phase did not emit its public proof manifest"
  fi
  if ! jq -e --arg durability "$durability" '.durability == $durability' \
    "$EVIDENCE_DIR/licensed-$durability-state.json" >/dev/null; then
    die 70 "Task 8 durability=$durability proof manifest is invalid"
  fi
done
cat "$EVIDENCE_DIR/prepare-sync.log" "$EVIDENCE_DIR/prepare-exit.log" \
  >"$EVIDENCE_DIR/prepare.log"

generation_before="$(jq -r '[.container_id,.started_at,(.restart_count|tostring)] | join(":")' "$EVIDENCE_DIR/container-before.json")"
"${compose[@]}" stop langgraph-api
target_unavailable=0
for _ in $(seq 1 30); do
  if ! curl --fail --silent --max-time 1 "$AGENT_URL/ok" >/dev/null 2>&1; then
    target_unavailable=1
    break
  fi
  sleep 0.2
done
if [[ "$target_unavailable" != "1" ]]; then
  die 70 'Owned Agent Server URL remained available while its bound container was stopped'
fi
jq -n \
  --arg observed_at "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
  --arg agent_server_url "$AGENT_URL" \
  --arg container_id "$AGENT_CONTAINER_BEFORE" \
  '{unavailable_observed:true,observed_at:$observed_at,agent_server_url:$agent_server_url,container_id:$container_id}' \
  >"$EVIDENCE_DIR/target-outage.json"
"${compose[@]}" start langgraph-api

agent_recovered=0
for _ in $(seq 1 120); do
  AGENT_CONTAINER_AFTER="$("${compose[@]}" ps -q langgraph-api 2>/dev/null || true)"
  health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$AGENT_CONTAINER_AFTER" 2>/dev/null || true)"
  if [[ "$health" == "healthy" ]] && curl --fail --silent --max-time 3 \
    "$AGENT_URL/ok" >/dev/null; then
    agent_recovered=1
    break
  fi
  sleep 1
done
if [[ "$agent_recovered" != "1" ]]; then
  die 69 'Licensed Agent Server did not become healthy after a real container stop/start'
fi
docker inspect "$AGENT_CONTAINER_AFTER" | jq '.[0] | {container_id:.Id,name:.Name,image_reference:.Config.Image,image_id:.Image,started_at:.State.StartedAt,restart_count:.RestartCount,health:(.State.Health.Status // "missing"),ports:.NetworkSettings.Ports["8000/tcp"],compose_project:.Config.Labels["com.docker.compose.project"],compose_service:.Config.Labels["com.docker.compose.service"]}' \
  >"$EVIDENCE_DIR/container-after.json"
generation_after="$(jq -r '[.container_id,.started_at,(.restart_count|tostring)] | join(":")' "$EVIDENCE_DIR/container-after.json")"
if [[ "$generation_before" == "$generation_after" ]]; then
  die 70 'Agent Server stop/start did not change its observable container generation'
fi
published_port_after="$(jq -r '[.ports[]? | select(.HostIp == "127.0.0.1") | .HostPort] | first // empty' "$EVIDENCE_DIR/container-after.json")"
if [[ "$AGENT_URL" != "http://127.0.0.1:$published_port_after" ]]; then
  die 70 'Recovered Agent Server URL is no longer bound to the owned Compose container'
fi
if [[ "$(jq -r '.image_id' "$EVIDENCE_DIR/container-after.json")" != "$AGENT_IMAGE_ID" ]]; then
  die 70 'Recovered Agent Server is not running the verified image identity'
fi
jq -n \
  --arg runtime_kind licensed-persistent \
  --arg agent_server_url "$AGENT_URL" \
  --arg compose_project "$COMPOSE_PROJECT_NAME" \
  --arg compose_service langgraph-api \
  --arg container_id_before "$AGENT_CONTAINER_BEFORE" \
  --arg container_id_after "$AGENT_CONTAINER_AFTER" \
  --arg image_id "$AGENT_IMAGE_ID" \
  --arg locked_base_image "$LOCKED_BASE_IMAGE" \
  --arg generation_before "$generation_before" \
  --arg generation_after "$generation_after" \
  '{restarted:true,licensed:true,runtime_kind:$runtime_kind,agent_server_url:$agent_server_url,compose_project:$compose_project,compose_service:$compose_service,container_id_before:$container_id_before,container_id_after:$container_id_after,image_id:$image_id,locked_base_image:$locked_base_image,image_verifier_exit_code:0,target_unavailable_observed:true,target_recovered_observed:true,generation_before:$generation_before,generation_after:$generation_after}' \
  >"$EVIDENCE_DIR/restart-receipt.json"

refresh_product_token
if ! curl --fail --silent --show-error --max-time 10 \
  --header "@$PRODUCT_AUTH_HEADER_FILE" \
  "$AGENT_URL/app/api/v2/tasks/$PRODUCT_TASK_ID" \
  --output "$EVIDENCE_DIR/product-task-after-restart.json"; then
  die 69 'Product Task did not recover after the Agent Server restart'
fi
if ! jq -e \
  --arg task_id "$PRODUCT_TASK_ID" \
  --arg thread_id "$PRODUCT_AGENT_THREAD_ID" \
  --arg run_id "$PRODUCT_AGENT_RUN_ID" '
    .task_id == $task_id
    and .agent_stream.thread_id == $thread_id
    and .agent_stream.run_id == $run_id
  ' "$EVIDENCE_DIR/product-task-after-restart.json" >/dev/null; then
  die 70 'Product Task lost its authoritative Agent Thread/Run binding across restart'
fi
if ! curl --fail --silent --show-error --max-time 10 \
  --header "@$PRODUCT_AUTH_HEADER_FILE" \
  "$AGENT_URL/threads/$PRODUCT_AGENT_THREAD_ID/runs/$PRODUCT_AGENT_RUN_ID" \
  --output "$EVIDENCE_DIR/product-agent-run-after-restart.json"; then
  die 70 'Product-admitted official Agent Run did not survive restart'
fi

export LICENSED_AGENT_SERVER_PRODUCT_AUTHORIZATION_TOKEN="$TASK8_PRODUCT_TOKEN"
export LICENSED_AGENT_SERVER_PRODUCT_TASK_ID="$PRODUCT_TASK_ID"
export LICENSED_AGENT_SERVER_PRODUCT_THREAD_ID="$PRODUCT_AGENT_THREAD_ID"
export LICENSED_AGENT_SERVER_PRODUCT_RUN_ID="$PRODUCT_AGENT_RUN_ID"
export LICENSED_AGENT_SERVER_PROOF_PHASE=verify
export LICENSED_AGENT_SERVER_TEST_DURABILITY=sync
export LICENSED_AGENT_SERVER_PROOF_STATE_FILE="$EVIDENCE_DIR/licensed-sync-state.json"
export LICENSED_AGENT_SERVER_RESTART_RECEIPT_FILE="$EVIDENCE_DIR/restart-receipt.json"
PRODUCT_ADMISSION_JUNIT="$EVIDENCE_DIR/product-admission-restart.xml"
product_admission_raw_log="$TEMP_DIR/product-admission-restart.log.raw"
set +e
(
  cd "$BACKEND_DIR"
  uv run --frozen pytest \
    tests/integration/test_run_durability.py::test_live_product_admission_survives_agent_server_restart \
    -q --junitxml="$PRODUCT_ADMISSION_JUNIT"
) >"$product_admission_raw_log" 2>&1
product_admission_status=$?
set -e
redact_file "$product_admission_raw_log" \
  "$EVIDENCE_DIR/product-admission-restart.log"
if ((product_admission_status != 0)); then
  die 70 "Task 8 live Product admission restart proof failed with status $product_admission_status"
fi
assert_junit_has_no_skip_or_error "$PRODUCT_ADMISSION_JUNIT" \
  'Task 8 live Product admission restart proof'

for durability in sync exit; do
  refresh_probe_token
  export LICENSED_AGENT_SERVER_TOKEN="$TASK8_AGENT_TOKEN"
  export LICENSED_AGENT_SERVER_PROOF_PHASE=verify
  export LICENSED_AGENT_SERVER_TEST_DURABILITY="$durability"
  export LICENSED_AGENT_SERVER_PROOF_STATE_FILE="$EVIDENCE_DIR/licensed-$durability-state.json"
  export LICENSED_AGENT_SERVER_RESTART_RECEIPT_FILE="$EVIDENCE_DIR/restart-receipt.json"
  VERIFY_JUNIT="$EVIDENCE_DIR/verify-$durability.xml"
  if [[ "$durability" == "sync" ]]; then
    durability_selector=tests/integration/test_run_durability.py::test_live_server_effective_sync_durability_after_restart
  else
    durability_selector=tests/integration/test_run_durability.py::test_live_server_effective_exit_durability_after_restart
  fi
  verify_raw_log="$TEMP_DIR/verify-$durability.log.raw"
  set +e
  (
    cd "$BACKEND_DIR"
    uv run --frozen pytest \
      "$durability_selector" \
      -q --junitxml="$VERIFY_JUNIT"
  ) >"$verify_raw_log" 2>&1
  verify_status=$?
  set -e
  redact_file "$verify_raw_log" "$EVIDENCE_DIR/verify-$durability.log"
  if ((verify_status != 0)); then
    die 70 "Task 8 post-restart durability=$durability phase failed with status $verify_status"
  fi
  assert_junit_has_no_skip_or_error "$VERIFY_JUNIT" \
    "Task 8 post-restart durability=$durability phase"
done
cat "$EVIDENCE_DIR/verify-sync.log" "$EVIDENCE_DIR/verify-exit.log" \
  >"$EVIDENCE_DIR/verify.log"

refresh_probe_token
export LICENSED_AGENT_SERVER_TOKEN="$TASK8_AGENT_TOKEN"
export LICENSED_AGENT_SERVER_PROOF_PHASE=verify
export LICENSED_AGENT_SERVER_TEST_DURABILITY=sync
export LICENSED_AGENT_SERVER_PROOF_STATE_FILE="$EVIDENCE_DIR/licensed-sync-state.json"
export LICENSED_AGENT_SERVER_RESTART_RECEIPT_FILE="$EVIDENCE_DIR/restart-receipt.json"
routing_raw_log="$TEMP_DIR/interrupt-routing.log.raw"
set +e
(
  cd "$BACKEND_DIR"
  uv run --frozen pytest \
    tests/integration/test_agent_server_interrupt_routing.py::test_licensed_runtime_routes_root_and_nested_interrupts_atomically \
    -q --junitxml="$EVIDENCE_DIR/interrupt-routing.xml"
) >"$routing_raw_log" 2>&1
routing_status=$?
set -e
redact_file "$routing_raw_log" "$EVIDENCE_DIR/interrupt-routing.log"
if ((routing_status != 0)); then
  die 70 "Task 8 live interrupt routing phase failed with status $routing_status"
fi
assert_junit_has_no_skip_or_error "$EVIDENCE_DIR/interrupt-routing.xml" \
  'Task 8 live interrupt routing phase'

"${compose[@]}" ps --format '{{.Service}} {{.ID}}' \
  >"$EVIDENCE_DIR/compose-identifiers-after.txt"
if [[ "$EXPECT_CONTRACT_FAILURE" == "1" ]]; then
  if [[ "$EXPECTED_RED_OBSERVED" != "1" ]]; then
    die 70 'Expected Task 8 contract failure mode observed no explicit CAPABILITY GAP'
  fi
  PROOF_RESULT="expected_capability_red"
  FAILURE_REASON="known_protocol_capability_gap"
else
  PROOF_RESULT="passed"
  FAILURE_REASON=""
fi
write_evidence_status 0
write_evidence_manifest
[[ -s "$EVIDENCE_MANIFEST_FILE" ]] || \
  die 70 'Task 8 evidence manifest was not materialized before success'
if ! jq -e '
  .schema_version == "1.0"
  and (.source.candidate_sha | test("^[0-9a-f]{40}([0-9a-f]{24})?$"))
  and (.image.image_digest | test("^sha256:[0-9a-f]{64}$"))
  and (.product_admission.task_id | type == "string" and length > 0)
  and (.product_admission.agent_thread_id | type == "string" and length > 0)
  and (.product_admission.agent_run_id | type == "string" and length > 0)
  and (.required_artifact_sha256 | to_entries | length == 9)
  and (.required_artifact_sha256 | all(.[]; test("^[0-9a-f]{64}$")))
  and (.artifacts | length > 0)
' "$EVIDENCE_MANIFEST_FILE" >/dev/null; then
  die 70 'Task 8 evidence manifest is missing a required runtime identity or artifact hash'
fi
if [[ "$EXPECT_CONTRACT_FAILURE" == "1" ]]; then
  printf '%s\n' \
    'Task 8 expected capability RED completed after Product admission, Node, licensed restart, sync/exit durability, and interrupt verification'
else
  printf '%s\n' \
    'Task 8 Protocol v2, Product admission, and licensed persistent restart proof passed with zero skip; sync/exit durability verified'
fi
