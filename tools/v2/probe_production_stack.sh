#!/usr/bin/env bash
set -euo pipefail

umask 077

readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
readonly COMPOSE_FILE="$ROOT_DIR/deploy/docker-compose.production.yml"

profile=""
source_sha=""
governance_sha=""
image_digest=""
output=""
project_name="crypto-alert-v2-production-probe-$$"
stack_started=0

usage() {
  printf 'Usage: %s --profile hosted-production --source-sha SHA --governance-sha SHA --image-digest SHA256 --output PATH\n' "$0"
}

die() {
  printf '%s\n' "$2" >&2
  exit "$1"
}

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  if [[ "$stack_started" == "1" ]]; then
    "${compose[@]}" logs --no-color --tail 200 >/dev/null 2>&1 || true
    "${compose[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

while (($# > 0)); do
  case "$1" in
    --profile) profile=${2:-}; shift 2 ;;
    --source-sha) source_sha=${2:-}; shift 2 ;;
    --governance-sha) governance_sha=${2:-}; shift 2 ;;
    --image-digest) image_digest=${2:-}; shift 2 ;;
    --output) output=${2:-}; shift 2 ;;
    --project-name) project_name=${2:-}; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) usage >&2; die 64 "Unknown option: $1" ;;
  esac
done

[[ "$profile" == 'hosted-production' ]] || die 64 '--profile must be hosted-production'
[[ "$source_sha" =~ ^[0-9a-f]{40}$ ]] || die 64 '--source-sha must be a full lowercase Git SHA'
[[ "$governance_sha" =~ ^[0-9a-f]{40}$ ]] || die 64 '--governance-sha must be a full lowercase Git SHA'
[[ "$image_digest" =~ ^sha256:[0-9a-f]{64}$ ]] || die 64 '--image-digest must be sha256:<64 lowercase hex>'
[[ -n "$output" ]] || die 64 '--output is required'

for command_name in docker git; do
  command -v "$command_name" >/dev/null 2>&1 || die 69 "Required tool is unavailable: $command_name"
done
if command -v python >/dev/null 2>&1; then
  host_python=(python)
elif command -v python3 >/dev/null 2>&1; then
  host_python=(python3)
elif [[ -x "$ROOT_DIR/backend/.venv/Scripts/python.exe" ]]; then
  host_python=("$ROOT_DIR/backend/.venv/Scripts/python.exe")
else
  die 69 'Required tool is unavailable: python or python3'
fi
docker compose version >/dev/null 2>&1 || die 69 'Docker Compose v2 is required'
docker info >/dev/null 2>&1 || die 69 'Docker daemon is unavailable'

cd "$ROOT_DIR"
[[ "$(git rev-parse HEAD)" == "$source_sha" ]] || die 65 'source SHA does not match HEAD'
[[ -z "$(git status --porcelain --untracked-files=all)" ]] \
  || die 65 'hosted production probe requires a clean immutable source tree'

output="$("${host_python[@]}" -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$output")"
[[ ! -e "$output" ]] || die 64 '--output must not already exist'
mkdir -p "$(dirname "$output")"

required_environment=(
  BACKEND_IMAGE FRONTEND_IMAGE INGRESS_IMAGE PRODUCT_POSTGRES_IMAGE AGENT_POSTGRES_IMAGE REDIS_IMAGE
  PRODUCT_POSTGRES_DB PRODUCT_POSTGRES_USER PRODUCT_POSTGRES_PASSWORD
  AGENT_POSTGRES_DB AGENT_POSTGRES_USER AGENT_POSTGRES_PASSWORD
  PRODUCT_DATABASE_URL AGENT_DATABASE_URL OPENAI_BASE_URL OPENAI_API_KEY MODEL_NAME SEARCH_PROVIDER
  INTERNAL_JWT_KEY_ID INTERNAL_JWT_ISSUER INTERNAL_JWT_PRIVATE_KEY_PATH INTERNAL_JWT_PUBLIC_KEY_PATH
  PRODUCT_INBOX_CURSOR_KEY_PATH NOTIFICATION_CREDENTIAL_KEY NOTIFICATION_CREDENTIAL_KEY_VERSION
  OIDC_ISSUER OIDC_CLIENT_ID OIDC_CLIENT_SECRET NEXTAUTH_SECRET NEXTAUTH_URL PRODUCTION_INGRESS_PORT
)
for environment_name in "${required_environment[@]}"; do
  [[ -n "${!environment_name:-}" ]] || die 66 "Required protected environment variable is missing: $environment_name"
done
[[ "$NEXTAUTH_URL" == https://* ]] || die 66 'NEXTAUTH_URL must use trusted HTTPS'

export COMPOSE_DISABLE_ENV_FILE=1
compose=(
  docker compose
  --project-name "$project_name"
  --project-directory "$ROOT_DIR/deploy"
  --file "$COMPOSE_FILE"
)

"${compose[@]}" config --quiet
stack_started=1
"${compose[@]}" up --detach --wait --wait-timeout 300

"${compose[@]}" run --rm --no-deps -T migrate alembic -c alembic.ini current >/dev/null
"${compose[@]}" exec -T langgraph-api python -c \
  "import json,urllib.request; p=json.load(urllib.request.urlopen('http://127.0.0.1:8000/openapi.json', timeout=5)); assert isinstance(p.get('paths'), dict) and p['paths']"
"${compose[@]}" exec -T langgraph-api python -c \
  "import json,urllib.request; p=json.load(urllib.request.urlopen('http://127.0.0.1:8000/app/openapi.json', timeout=5)); assert isinstance(p.get('paths'), dict) and p['paths']"
"${compose[@]}" exec -T frontend node -e \
  "fetch('http://127.0.0.1:3001/work',{signal:AbortSignal.timeout(8000)}).then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"

"${host_python[@]}" - "$output" "$source_sha" "$governance_sha" "$image_digest" "$project_name" <<'PY'
import json
from pathlib import Path
import sys

path, source_sha, governance_sha, image_digest, project_name = sys.argv[1:]
payload = {
    "schema_version": "2026-07-23.production-stack-probe.v1",
    "status": "passed",
    "proof_level": "ephemeral-production-compose-host-probe",
    "profile": "hosted-production",
    "source_sha": source_sha,
    "governance_sha": governance_sha,
    "image_set_digest": image_digest,
    "compose_project": project_name,
    "checks": {
        "compose_all_services_healthy": True,
        "migration_current": True,
        "agent_openapi": True,
        "product_openapi": True,
        "frontend_work": True,
    },
    "does_not_prove": [
        "public_https_ingress",
        "real_oidc_actor_matrix",
        "registry_signature_or_attestation",
        "production_failover_or_dr",
        "independent_release_review",
    ],
    "production_ready": False,
}
Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
PY

printf 'Ephemeral production Compose probe passed: %s\n' "$output"
