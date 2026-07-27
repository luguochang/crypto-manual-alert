#!/usr/bin/env bash
set -euo pipefail

umask 077

readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
readonly SYFT_IMAGE_DEFAULT="anchore/syft:v1.27.1"
readonly TRIVY_IMAGE_DEFAULT="ghcr.io/aquasecurity/trivy:0.58.2"

source_sha=""
governance_sha=""
output_digest=""
evidence_dir=""
backend_image=""
frontend_image=""
allow_dirty=0

usage() {
  printf 'Usage: %s --source-sha SHA --output-digest PATH [--governance-sha SHA] [--evidence-dir PATH] [--backend-image REF] [--frontend-image REF] [--allow-dirty-local-rehearsal]\n' "$0"
}

die() {
  printf '%s\n' "$2" >&2
  exit "$1"
}

while (($# > 0)); do
  case "$1" in
    --source-sha) source_sha=${2:-}; shift 2 ;;
    --governance-sha) governance_sha=${2:-}; shift 2 ;;
    --output-digest) output_digest=${2:-}; shift 2 ;;
    --evidence-dir) evidence_dir=${2:-}; shift 2 ;;
    --backend-image) backend_image=${2:-}; shift 2 ;;
    --frontend-image) frontend_image=${2:-}; shift 2 ;;
    --allow-dirty-local-rehearsal) allow_dirty=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) usage >&2; die 64 "Unknown option: $1" ;;
  esac
done

[[ "$source_sha" =~ ^[0-9a-f]{40}$ ]] || die 64 '--source-sha must be a full lowercase Git SHA'
[[ -n "$output_digest" ]] || die 64 '--output-digest is required'
if [[ -n "$governance_sha" && ! "$governance_sha" =~ ^[0-9a-f]{40}$ ]]; then
  die 64 '--governance-sha must be a full lowercase Git SHA'
fi

for command_name in docker git sha256sum; do
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
docker info >/dev/null 2>&1 || die 69 'Docker daemon is unavailable'

cd "$ROOT_DIR"
[[ "$(git rev-parse HEAD)" == "$source_sha" ]] || die 65 'source SHA does not match HEAD'
git_dirty=0
if [[ -n "$(git status --porcelain --untracked-files=all)" ]]; then
  git_dirty=1
fi
if [[ "$git_dirty" == "1" && "$allow_dirty" != "1" ]]; then
  die 65 'release image build requires a clean immutable source tree'
fi

output_digest="$("${host_python[@]}" -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$output_digest")"
if [[ -z "$evidence_dir" ]]; then
  evidence_dir="${output_digest%.*}-supply-chain"
fi
evidence_dir="$("${host_python[@]}" -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$evidence_dir")"
[[ ! -e "$output_digest" ]] || die 64 '--output-digest must not already exist'
[[ ! -e "$evidence_dir" ]] || die 64 '--evidence-dir must not already exist'
mkdir -p "$(dirname "$output_digest")" "$evidence_dir"

short_sha=${source_sha:0:12}
backend_image=${backend_image:-"crypto-alert-backend:${short_sha}"}
frontend_image=${frontend_image:-"crypto-alert-frontend:${short_sha}"}

docker build --file backend/Dockerfile --tag "$backend_image" .
docker build --file frontend/Dockerfile --tag "$frontend_image" .

backend_id="$(docker image inspect --format '{{.Id}}' "$backend_image")"
frontend_id="$(docker image inspect --format '{{.Id}}' "$frontend_image")"
[[ "$(docker image inspect --format '{{.Config.User}}' "$backend_image")" == '10001:10001' ]] \
  || die 70 'backend production image is not configured as UID/GID 10001'
[[ "$(docker image inspect --format '{{.Config.User}}' "$frontend_image")" == 'node' ]] \
  || die 70 'frontend production image is not configured as node'

evidence_mount="$("${host_python[@]}" -c 'import os,sys; print(os.path.abspath(sys.argv[1]).replace(chr(92), "/"))' "$evidence_dir")"
syft_image=${SYFT_IMAGE:-$SYFT_IMAGE_DEFAULT}
trivy_image=${TRIVY_IMAGE:-$TRIVY_IMAGE_DEFAULT}
trivy_cache=${TRIVY_CACHE_DIR:-"$evidence_dir/trivy-cache"}
mkdir -p "$trivy_cache"
cache_mount="$("${host_python[@]}" -c 'import os,sys; print(os.path.abspath(sys.argv[1]).replace(chr(92), "/"))' "$trivy_cache")"

run_syft() {
  local image_ref=$1
  local output_name=$2
  env MSYS_NO_PATHCONV=1 docker run --rm \
    --volume /var/run/docker.sock:/var/run/docker.sock \
    --volume "$evidence_mount:/evidence" \
    "$syft_image" scan "docker:$image_ref" \
    --output "cyclonedx-json=/evidence/$output_name"
}

run_syft "$backend_id" backend.cdx.json
run_syft "$frontend_id" frontend.cdx.json

run_trivy() {
  local image_ref=$1
  local output_name=$2
  env MSYS_NO_PATHCONV=1 docker run --rm \
    --volume /var/run/docker.sock:/var/run/docker.sock \
    --volume "$evidence_mount:/evidence" \
    --volume "$cache_mount:/root/.cache/trivy" \
    "$trivy_image" image \
    --db-repository ghcr.io/aquasecurity/trivy-db:2 \
    --format json --output "/evidence/$output_name" "$image_ref"
}

run_trivy "$backend_id" backend-trivy.json
run_trivy "$frontend_id" frontend-trivy.json

summary_status=0
"${host_python[@]}" tools/v2/summarize_trivy_image.py \
  --report "$evidence_dir/backend-trivy.json" \
  --expected-image-id "$backend_id" \
  --output "$evidence_dir/backend-trivy-summary.json" || summary_status=1
"${host_python[@]}" tools/v2/summarize_trivy_image.py \
  --report "$evidence_dir/frontend-trivy.json" \
  --expected-image-id "$frontend_id" \
  --output "$evidence_dir/frontend-trivy-summary.json" || summary_status=1

"${host_python[@]}" - "$evidence_dir/image-set.json" "$source_sha" "$governance_sha" \
  "$backend_image" "$backend_id" "$frontend_image" "$frontend_id" "$git_dirty" <<'PY'
import json
from pathlib import Path
import sys

path, source_sha, governance_sha, backend_ref, backend_id, frontend_ref, frontend_id, dirty = sys.argv[1:]
payload = {
    "schema_version": "2026-07-23.production-image-set.v1",
    "status": "passed" if dirty == "0" else "local_rehearsal",
    "proof_level": "immutable-source-local-image-build" if dirty == "0" else "dirty-worktree-local-image-build",
    "source_sha": source_sha,
    "governance_sha": governance_sha or None,
    "images": {
        "backend": {"reference": backend_ref, "image_id": backend_id},
        "frontend": {"reference": frontend_ref, "image_id": frontend_id},
    },
    "registry_repo_digests_proved": False,
    "production_ready": False,
}
Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
PY

image_set_digest="$(sha256sum "$evidence_dir/image-set.json" | awk '{print $1}')"
printf 'sha256:%s\n' "$image_set_digest" >"$output_digest"
printf '%s  %s\n' "$image_set_digest" image-set.json >"$evidence_dir/image-set.sha256"

if [[ "$summary_status" != "0" ]]; then
  die 1 'production image CVE policy failed; evidence was retained'
fi
printf 'Production image build and local supply-chain scan passed: %s\n' "$output_digest"
