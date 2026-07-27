#!/usr/bin/env bash
set -euo pipefail

umask 077

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"
QA_COMPOSE_FILE="$ROOT_DIR/deploy/docker-compose.task8-qa.yml"
HA_COMPOSE_FILE="$ROOT_DIR/deploy/docker-compose.task8-ha.yml"
HAPROXY_CONFIG="$ROOT_DIR/deploy/task8-ha-haproxy.cfg"
IMAGE="crypto-manual-alert-v2-backend:local"
GATEWAY_IMAGE="public.ecr.aws/docker/library/haproxy:3.0-alpine@sha256:dee54db8b27cd6c21519ea4f0ba0604f3742e8e7369bc16fb5b69133dec3f47f"
IMAGE_VERIFIER="$ROOT_DIR/tools/v2/verify_agent_image.sh"
CLIENT_PROBE="$ROOT_DIR/tools/v2/aegra_durability_probe.py"
AVAILABILITY_PROBE="$ROOT_DIR/tools/v2/aegra_ha_availability.py"
EVIDENCE_DIR=""
PROJECT_NAME="crypto-manual-alert-v2-task8-ha-$$"
STACK_STARTED=0
EVIDENCE_FINALIZED=0
AVAILABILITY_CONTAINER=""
AVAILABILITY_PID=""

usage() {
  printf 'Usage: %s --evidence-dir PATH\n' "$0"
}

die() {
  local status=$1
  shift
  printf '%s\n' "$*" >&2
  exit "$status"
}

redact_logs() {
  sed -E \
    -e 's#(postgres(ql)?(\+asyncpg)?://[^:]+:)[^@]+@#\1[REDACTED]@#Ig' \
    -e 's/(Bearer )[A-Za-z0-9._~+\/-]+/\1[REDACTED]/g'
}

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  set +e
  if [[ -n "$AVAILABILITY_CONTAINER" ]]; then
    docker rm --force "$AVAILABILITY_CONTAINER" >/dev/null 2>&1 || true
  fi
  if [[ -n "$AVAILABILITY_PID" ]]; then
    wait "$AVAILABILITY_PID" >/dev/null 2>&1 || true
  fi
  if [[ "$STACK_STARTED" == "1" ]]; then
    if [[ "$EVIDENCE_FINALIZED" != "1" ]]; then
      "${compose[@]}" logs --no-color --timestamps langgraph-api 2>&1 \
        | redact_logs >"$EVIDENCE_DIR/aegra-ha.log" || true
      "${compose[@]}" logs --no-color --timestamps ha-gateway 2>&1 \
        | redact_logs >"$EVIDENCE_DIR/haproxy.log" || true
    fi
    "${compose[@]}" down --volumes --remove-orphans --timeout 15 \
      >/dev/null 2>&1 || true
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

for command_name in docker openssl sed sha256sum; do
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

gateway_config_mount="$HAPROXY_CONFIG"
if command -v cygpath >/dev/null 2>&1; then
  gateway_config_mount="$(cygpath -m "$HAPROXY_CONFIG")"
fi
docker pull "$GATEWAY_IMAGE" >/dev/null
gateway_image_id="$(docker image inspect --format '{{.Id}}' "$GATEWAY_IMAGE")"
gateway_repo_digests="$(docker image inspect --format '{{json .RepoDigests}}' "$GATEWAY_IMAGE")"
gateway_platform="$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$GATEWAY_IMAGE")"
env MSYS_NO_PATHCONV=1 docker run --rm \
  --network none \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --env AEGRA_REPLICA_A=localhost \
  --env AEGRA_REPLICA_B=localhost \
  --volume "$gateway_config_mount:/usr/local/etc/haproxy/haproxy.cfg:ro" \
  --entrypoint haproxy \
  "$GATEWAY_IMAGE" -c -f /usr/local/etc/haproxy/haproxy.cfg

export COMPOSE_DISABLE_ENV_FILE=1
export COMPOSE_PROJECT_NAME="$PROJECT_NAME"
export AEGRA_CONFIG_BASENAME=aegra.task8-qa.json
export AEGRA_WORKER_COUNT=1
export AEGRA_JOBS_PER_WORKER=1
export AEGRA_LEASE_DURATION_SECONDS=15
export AEGRA_HEARTBEAT_INTERVAL_SECONDS=5
export AEGRA_REAPER_INTERVAL_SECONDS=3
export AEGRA_STUCK_PENDING_THRESHOLD_SECONDS=30
export SEARCH_PROVIDER=builtin_web_search
export NOTIFICATION_CREDENTIAL_KEY="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=')"
export NOTIFICATION_CREDENTIAL_KEY_VERSION=task8-ha-ephemeral

compose=(
  docker compose
  --project-name "$PROJECT_NAME"
  --project-directory "$ROOT_DIR"
  --file "$COMPOSE_FILE"
  --file "$QA_COMPOSE_FILE"
  --file "$HA_COMPOSE_FILE"
)

"$IMAGE_VERIFIER" "$IMAGE" --allow-multi-interrupt-fixture
STACK_STARTED=1
"${compose[@]}" up --detach --wait --wait-timeout 180 langgraph-api
"${compose[@]}" up --detach --wait --wait-timeout 180 \
  --scale langgraph-api=2 langgraph-api
"${compose[@]}" up --detach --wait --wait-timeout 180 \
  --scale langgraph-api=2 ha-gateway

mapfile -t containers < <("${compose[@]}" ps --status running -q langgraph-api)
[[ "${#containers[@]}" == "2" ]] \
  || die 70 "Expected exactly two running Aegra replicas, got ${#containers[@]}"
gateway_container="$("${compose[@]}" ps --status running -q ha-gateway)"
[[ -n "$gateway_container" ]] || die 70 'HAProxy gateway is not running'

container_name() {
  docker inspect --format '{{.Name}}' "$1" | sed 's#^/##'
}

container_generation() {
  docker inspect --format '{{.Id}}:{{.State.StartedAt}}' "$1"
}

wait_healthy() {
  local container_id=$1
  local status=""
  for _ in $(seq 1 120); do
    status="$(docker inspect --format '{{.State.Health.Status}}' "$container_id")"
    if [[ "$status" == "healthy" ]]; then
      return 0
    fi
    sleep 1
  done
  die 70 "Aegra replica did not become healthy: $container_id ($status)"
}

container_a="${containers[0]}"
container_b="${containers[1]}"
name_a="$(container_name "$container_a")"
name_b="$(container_name "$container_b")"
[[ "$name_a" != "$name_b" ]] || die 70 'Aegra replica names are not distinct'
image_a="$(docker inspect --format '{{.Image}}' "$container_a")"
image_b="$(docker inspect --format '{{.Image}}' "$container_b")"
[[ "$image_a" == "$image_b" ]] || die 70 'Aegra replicas use different images'
generation_a_before="$(container_generation "$container_a")"
generation_b_before="$(container_generation "$container_b")"
wait_healthy "$container_a"
wait_healthy "$container_b"

private_volume="${PROJECT_NAME}_internal-jwt-private"
network_name="${PROJECT_NAME}_default"
client_probe_mount="$CLIENT_PROBE"
availability_probe_mount="$AVAILABILITY_PROBE"
evidence_mount="$EVIDENCE_DIR"
if command -v cygpath >/dev/null 2>&1; then
  client_probe_mount="$(cygpath -m "$CLIENT_PROBE")"
  availability_probe_mount="$(cygpath -m "$AVAILABILITY_PROBE")"
  evidence_mount="$(cygpath -m "$EVIDENCE_DIR")"
fi

run_client() {
  local target=$1
  local phase=$2
  shift 2
  env MSYS_NO_PATHCONV=1 docker run --rm -i \
    --network "$network_name" \
    --volume "$private_volume:/keys:ro" \
    --volume "$evidence_mount:/evidence" \
    --volume "$client_probe_mount:/probe.py:ro" \
    --env "AEGRA_PROBE_URL=$target" \
    --env AEGRA_PROBE_PRIVATE_KEY_FILE=//keys/private.pem \
    --env AEGRA_PROBE_JWT_KID=compose-ephemeral \
    --env AEGRA_PROBE_JWT_ISSUER=crypto-manual-alert-v2-compose \
    --env AEGRA_PROBE_JWT_AUDIENCE=crypto-alert-agent-server \
    --env AEGRA_PROBE_USER_ID=dev-user \
    --env AEGRA_PROBE_TENANT_ID=dev-tenant \
    --env AEGRA_PROBE_WORKSPACE_ID=dev-workspace \
    --env AEGRA_PROBE_IDENTITY_ISSUER=crypto-alert-v2-compose \
    --env AEGRA_HA_STATE_FILE=//evidence/ha-state.json \
    --env AEGRA_HA_RESUME_FILE=//evidence/resume.json \
    --env AEGRA_HA_FINAL_FILE=//evidence/final.json \
    "$@" \
    "$IMAGE" python //probe.py "$phase"
}

url_a="http://$name_a:8000"
url_b="http://$name_b:8000"
url_gateway="http://ha-gateway:8080"
run_client "$url_gateway" ha-prepare
run_client "$url_b" ha-observe \
  --env AEGRA_HA_OBSERVATION_FILE=//evidence/observe-initial-b.json

AVAILABILITY_CONTAINER="${PROJECT_NAME}-availability"
env MSYS_NO_PATHCONV=1 docker run --rm --name "$AVAILABILITY_CONTAINER" \
  --network "$network_name" \
  --volume "$evidence_mount:/evidence" \
  --volume "$availability_probe_mount:/availability.py:ro" \
  "$IMAGE" python //availability.py \
    --target "$url_gateway" \
    --output //evidence/availability.json \
    --requests 600 \
    --interval 0.1 &
AVAILABILITY_PID=$!
sleep 2

[[ "$(docker inspect --format '{{.State.Running}}' "$AVAILABILITY_CONTAINER")" == "true" ]] \
  || die 70 'HA availability client stopped before the first rollout step'
docker stop --time 10 "$container_a" >/dev/null
run_client "$url_b" ha-observe \
  --env AEGRA_HA_OBSERVATION_FILE=//evidence/observe-after-a-stop.json
docker start "$container_a" >/dev/null
wait_healthy "$container_a"
generation_a_after="$(container_generation "$container_a")"
[[ "$generation_a_before" != "$generation_a_after" ]] \
  || die 70 'Replica A generation did not change'

[[ "$(docker inspect --format '{{.State.Running}}' "$AVAILABILITY_CONTAINER")" == "true" ]] \
  || die 70 'HA availability client stopped before the second rollout step'
docker stop --time 10 "$container_b" >/dev/null
run_client "$url_a" ha-observe \
  --env AEGRA_HA_OBSERVATION_FILE=//evidence/observe-after-b-stop.json
run_client "$url_gateway" ha-resume
docker start "$container_b" >/dev/null
wait_healthy "$container_b"
generation_b_after="$(container_generation "$container_b")"
[[ "$generation_b_before" != "$generation_b_after" ]] \
  || die 70 'Replica B generation did not change'
run_client "$url_b" ha-final
[[ "$(docker inspect --format '{{.State.Health.Status}}' "$gateway_container")" == "healthy" ]] \
  || die 70 'HAProxy gateway is not healthy after the rollout'

if ! wait "$AVAILABILITY_PID"; then
  AVAILABILITY_PID=""
  die 70 'HA service-discovery availability probe failed'
fi
AVAILABILITY_PID=""
AVAILABILITY_CONTAINER=""

read -r gateway_config_sha _ < <(sha256sum "$HAPROXY_CONFIG")

ROLLING_RECEIPT="$EVIDENCE_DIR/rolling-receipt.json" \
GATEWAY_RECEIPT="$EVIDENCE_DIR/gateway-runtime.json" \
ROLLING_PROJECT="$PROJECT_NAME" \
ROLLING_IMAGE="$image_a" \
ROLLING_GATEWAY_CONTAINER="$gateway_container" \
ROLLING_GATEWAY_IMAGE_REF="$GATEWAY_IMAGE" \
ROLLING_GATEWAY_IMAGE_ID="$gateway_image_id" \
ROLLING_GATEWAY_REPO_DIGESTS="$gateway_repo_digests" \
ROLLING_GATEWAY_PLATFORM="$gateway_platform" \
ROLLING_GATEWAY_CONFIG_SHA="$gateway_config_sha" \
ROLLING_CONTAINER_A="$container_a" \
ROLLING_CONTAINER_B="$container_b" \
ROLLING_NAME_A="$name_a" \
ROLLING_NAME_B="$name_b" \
ROLLING_GENERATION_A_BEFORE="$generation_a_before" \
ROLLING_GENERATION_A_AFTER="$generation_a_after" \
ROLLING_GENERATION_B_BEFORE="$generation_b_before" \
ROLLING_GENERATION_B_AFTER="$generation_b_after" \
  "$host_python" - <<'PY'
import json
import os
from pathlib import Path

gateway = {
    "service": "ha-gateway",
    "container_id": os.environ["ROLLING_GATEWAY_CONTAINER"],
    "image_ref": os.environ["ROLLING_GATEWAY_IMAGE_REF"],
    "image_id": os.environ["ROLLING_GATEWAY_IMAGE_ID"],
    "repo_digests": json.loads(os.environ["ROLLING_GATEWAY_REPO_DIGESTS"]),
    "platform": os.environ["ROLLING_GATEWAY_PLATFORM"],
    "config_sha256": os.environ["ROLLING_GATEWAY_CONFIG_SHA"],
    "health_checked": True,
}
payload = {
    "schema_version": "1.0",
    "scope": "local-aegra-two-replica-rolling-recovery",
    "compose_project": os.environ["ROLLING_PROJECT"],
    "service": "ha-gateway",
    "backend_service": "langgraph-api",
    "replica_count": 2,
    "host_ports": [],
    "service_discovery": "health-checked-haproxy",
    "backend_identity": "stable-compose-replica-dns",
    "image_id": os.environ["ROLLING_IMAGE"],
    "gateway": gateway,
    "replicas": [
        {
            "container_id": os.environ["ROLLING_CONTAINER_A"],
            "name": os.environ["ROLLING_NAME_A"],
            "generation_before": os.environ["ROLLING_GENERATION_A_BEFORE"],
            "generation_after": os.environ["ROLLING_GENERATION_A_AFTER"],
            "stopped_and_restarted": True,
        },
        {
            "container_id": os.environ["ROLLING_CONTAINER_B"],
            "name": os.environ["ROLLING_NAME_B"],
            "generation_before": os.environ["ROLLING_GENERATION_B_BEFORE"],
            "generation_after": os.environ["ROLLING_GENERATION_B_AFTER"],
            "stopped_and_restarted": True,
        },
    ],
    "sequential_rollout": True,
    "both_replicas_healthy_after": True,
}
Path(os.environ["ROLLING_RECEIPT"]).write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
Path(os.environ["GATEWAY_RECEIPT"]).write_text(
    json.dumps(gateway, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

runtime_versions="$(docker run --rm --entrypoint python "$IMAGE" -c 'import importlib.metadata as m,json; print(json.dumps({name:m.version(name) for name in ("aegra-api","aegra-cli","langgraph","langgraph-sdk")}))')"
printf '%s\n' "$runtime_versions" >"$EVIDENCE_DIR/runtime-versions.json"
"${compose[@]}" logs --no-color --timestamps langgraph-api 2>&1 \
  | redact_logs >"$EVIDENCE_DIR/aegra-ha.log"
"${compose[@]}" logs --no-color --timestamps ha-gateway 2>&1 \
  | redact_logs >"$EVIDENCE_DIR/haproxy.log"
(
  cd "$ROOT_DIR"
  sha256sum deploy/task8-ha-haproxy.cfg \
    >"$EVIDENCE_DIR/gateway-config-sha256.txt"
)

MANIFEST_EVIDENCE_DIR="$EVIDENCE_DIR" \
MANIFEST_CANDIDATE_SHA="$(git -C "$ROOT_DIR" rev-parse HEAD)" \
MANIFEST_IMAGE_ID="$image_a" \
  "$host_python" - <<'PY'
import json
import os
from pathlib import Path

root = Path(os.environ["MANIFEST_EVIDENCE_DIR"])
payload = {
    "schema_version": "1.0",
    "result": "passed",
    "scope": "task8-local-aegra-two-replica-rolling-recovery",
    "candidate_sha": os.environ["MANIFEST_CANDIDATE_SHA"],
    "image_id": os.environ["MANIFEST_IMAGE_ID"],
    "rolling": json.loads((root / "rolling-receipt.json").read_text(encoding="utf-8")),
    "gateway": json.loads((root / "gateway-runtime.json").read_text(encoding="utf-8")),
    "availability": json.loads((root / "availability.json").read_text(encoding="utf-8")),
    "prepare": json.loads((root / "ha-state.json").read_text(encoding="utf-8")),
    "resume": json.loads((root / "resume.json").read_text(encoding="utf-8")),
    "final": json.loads((root / "final.json").read_text(encoding="utf-8")),
    "limitations": [
        "local self-hosted evidence is not hosted deployment evidence",
        "QA-only interrupt fixture does not prove the real Provider Product Graph",
        "the local HAProxy entry point is not production ingress or load-balancer proof",
        "the bounded rollout is not a long-duration SLO or capacity test",
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
    ha-state.json observe-initial-b.json observe-after-a-stop.json \
    observe-after-b-stop.json resume.json final.json availability.json \
    rolling-receipt.json gateway-runtime.json gateway-config-sha256.txt \
    runtime-versions.json aegra-ha.log haproxy.log evidence-manifest.json \
    >artifact-sha256.txt
)
EVIDENCE_FINALIZED=1

printf 'Aegra two-replica rolling recovery passed; evidence retained at %s\n' "$EVIDENCE_DIR"
