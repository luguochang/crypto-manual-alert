#!/usr/bin/env bash
set -euo pipefail

umask 077

readonly SCRIPT_DIR="$(cd -- "${BASH_SOURCE[0]%/*}" && pwd -P)"
readonly REPOSITORY_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
readonly EXPECTED_SCAN_COUNT=4

output_dir=""
stage_dir=""
work_dir=""
finalized=0

status="failed"
failure_reason="preflight_not_completed"
missing_tool=""
attempted_scans=0
completed_scans=0
network_checks_completed=0

git_head=""
git_dirty=false
source_manifest_sha256=""
source_file_count=0
backend_lock_sha256=""
frontend_lock_sha256=""
identity_ready=0
identity_rechecked=false
source_stable="unknown"
identity_failure_reason="source_identity_recheck_failed"

uv_version=""
npm_version=""
node_version=""
jq_version=""

python_audit_status="not_run"
python_audited_packages=0
python_vulnerability_count=0
python_adverse_status_count=0
frontend_audit_status="not_run"
frontend_audited_dependencies=0
frontend_vulnerability_count=0
frontend_lock_unique_dependency_count=0
python_sbom_status="not_run"
python_sbom_component_count=0
python_sbom_dependency_count=0
frontend_sbom_status="not_run"
frontend_sbom_component_count=0
frontend_sbom_dependency_count=0

cleanup() {
  if [[ "$finalized" != "1" && -n "$stage_dir" && -d "$stage_dir" ]]; then
    rm -rf "$stage_dir" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

emit_unpersisted_failure() {
  local reason="$1"
  printf '{"schema_version":"1.0","status":"failed","proof_level":"local-working-tree-supply-chain","failure_reason":"%s","persisted":false}\n' "$reason"
  printf 'local supply-chain gate failed: %s\n' "$reason" >&2
}

artifact_hash() {
  local path="$1"
  local digest_output
  if [[ ! -f "$path" ]] || ! command -v shasum >/dev/null 2>&1; then
    printf '%s' ""
    return
  fi
  digest_output="$(shasum -a 256 "$path")"
  printf '%s' "${digest_output%% *}"
}

write_summary() {
  local summary_path="$stage_dir/supply-chain-summary.json"
  local skipped_scans=$((EXPECTED_SCAN_COUNT - attempted_scans))
  local source_artifact_hash python_audit_hash frontend_audit_hash
  local python_sbom_hash frontend_sbom_hash

  source_artifact_hash="$(artifact_hash "$stage_dir/source-manifest.sha256")"
  python_audit_hash="$(artifact_hash "$stage_dir/python-audit.json")"
  frontend_audit_hash="$(artifact_hash "$stage_dir/frontend-audit.json")"
  python_sbom_hash="$(artifact_hash "$stage_dir/python.cdx.json")"
  frontend_sbom_hash="$(artifact_hash "$stage_dir/frontend.cdx.json")"

  jq -n \
    --arg status "$status" \
    --arg failure_reason "$failure_reason" \
    --arg missing_tool "$missing_tool" \
    --arg generated_at "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
    --arg git_head "$git_head" \
    --argjson git_dirty "$git_dirty" \
    --arg source_manifest_sha256 "$source_manifest_sha256" \
    --argjson source_file_count "$source_file_count" \
    --argjson identity_rechecked "$identity_rechecked" \
    --arg source_stable "$source_stable" \
    --arg backend_lock_sha256 "$backend_lock_sha256" \
    --arg frontend_lock_sha256 "$frontend_lock_sha256" \
    --arg uv_version "$uv_version" \
    --arg npm_version "$npm_version" \
    --arg node_version "$node_version" \
    --arg jq_version "$jq_version" \
    --argjson attempted_scans "$attempted_scans" \
    --argjson completed_scans "$completed_scans" \
    --argjson skipped_scans "$skipped_scans" \
    --argjson network_checks_completed "$network_checks_completed" \
    --arg python_audit_status "$python_audit_status" \
    --argjson python_audited_packages "$python_audited_packages" \
    --argjson python_vulnerability_count "$python_vulnerability_count" \
    --argjson python_adverse_status_count "$python_adverse_status_count" \
    --arg frontend_audit_status "$frontend_audit_status" \
    --argjson frontend_audited_dependencies "$frontend_audited_dependencies" \
    --argjson frontend_vulnerability_count "$frontend_vulnerability_count" \
    --argjson frontend_lock_unique_dependency_count "$frontend_lock_unique_dependency_count" \
    --arg python_sbom_status "$python_sbom_status" \
    --argjson python_sbom_component_count "$python_sbom_component_count" \
    --argjson python_sbom_dependency_count "$python_sbom_dependency_count" \
    --arg frontend_sbom_status "$frontend_sbom_status" \
    --argjson frontend_sbom_component_count "$frontend_sbom_component_count" \
    --argjson frontend_sbom_dependency_count "$frontend_sbom_dependency_count" \
    --arg source_artifact_hash "$source_artifact_hash" \
    --arg python_audit_hash "$python_audit_hash" \
    --arg frontend_audit_hash "$frontend_audit_hash" \
    --arg python_sbom_hash "$python_sbom_hash" \
    --arg frontend_sbom_hash "$frontend_sbom_hash" \
    '{
      schema_version: "1.0",
      status: $status,
      proof_level: "local-working-tree-supply-chain",
      failure_reason: (if $failure_reason == "" then null else $failure_reason end),
      missing_tool: (if $missing_tool == "" then null else $missing_tool end),
      generated_at: $generated_at,
      source: {
        git_head: (if $git_head == "" then null else $git_head end),
        git_dirty: $git_dirty,
        manifest_sha256: (if $source_manifest_sha256 == "" then null else $source_manifest_sha256 end),
        file_count: $source_file_count,
        identity_rechecked: $identity_rechecked,
        stable_during_scan: (
          if $source_stable == "unknown" then null else $source_stable == "true" end
        )
      },
      locks: {
        backend: {
          path: "backend/uv.lock",
          sha256: (if $backend_lock_sha256 == "" then null else $backend_lock_sha256 end)
        },
        frontend: {
          path: "frontend/package-lock.json",
          sha256: (if $frontend_lock_sha256 == "" then null else $frontend_lock_sha256 end),
          unique_dependencies: $frontend_lock_unique_dependency_count
        }
      },
      tools: {
        uv: (if $uv_version == "" then null else $uv_version end),
        npm: (if $npm_version == "" then null else $npm_version end),
        node: (if $node_version == "" then null else $node_version end),
        jq: (if $jq_version == "" then null else $jq_version end)
      },
      scan_count: 4,
      attempted_scans: $attempted_scans,
      completed_scans: $completed_scans,
      skipped_scans: $skipped_scans,
      network_checks_completed: $network_checks_completed,
      scans: {
        python_audit: {
          status: $python_audit_status,
          audited_packages: $python_audited_packages,
          vulnerabilities: $python_vulnerability_count,
          adverse_statuses: $python_adverse_status_count
        },
        frontend_audit: {
          status: $frontend_audit_status,
          audited_dependencies: $frontend_audited_dependencies,
          vulnerabilities: $frontend_vulnerability_count
        },
        python_sbom: {
          status: $python_sbom_status,
          format: "CycloneDX-1.5",
          components: $python_sbom_component_count,
          dependency_entries: $python_sbom_dependency_count
        },
        frontend_sbom: {
          status: $frontend_sbom_status,
          format: "CycloneDX",
          components: $frontend_sbom_component_count,
          dependency_entries: $frontend_sbom_dependency_count
        }
      },
      artifact_sha256: {
        "source-manifest.sha256": (if $source_artifact_hash == "" then null else $source_artifact_hash end),
        "python-audit.json": (if $python_audit_hash == "" then null else $python_audit_hash end),
        "frontend-audit.json": (if $frontend_audit_hash == "" then null else $frontend_audit_hash end),
        "python.cdx.json": (if $python_sbom_hash == "" then null else $python_sbom_hash end),
        "frontend.cdx.json": (if $frontend_sbom_hash == "" then null else $frontend_sbom_hash end)
      },
      redaction: {
        inherited_package_manager_environment: false,
        repository_package_manager_credentials_used: false,
        raw_tool_stderr_published: false
      },
      does_not_prove: [
        "committed_source_candidate",
        "hosted_dependency_audit",
        "container_image_sbom",
        "artifact_signature",
        "release_attestation",
        "production_release"
      ]
    }' >"$summary_path"

  jq -e '
    .schema_version == "1.0" and
    (.status == "passed" or .status == "failed") and
    .proof_level == "local-working-tree-supply-chain" and
    (.scan_count == 4) and
    (.attempted_scans | type == "number") and
    (.completed_scans | type == "number") and
    (.skipped_scans | type == "number") and
    (.does_not_prove | length == 6)
  ' "$summary_path" >/dev/null
}

publish_result() {
  local exit_code="$1"
  local artifact

  if [[ "$identity_ready" == "1" && "$identity_rechecked" != "true" ]]; then
    if ! recheck_source_identity; then
      status="failed"
      failure_reason="$identity_failure_reason"
      exit_code=1
    fi
  fi
  write_summary
  rm -rf "$work_dir"
  work_dir=""

  for artifact in "$stage_dir"/*; do
    [[ -f "$artifact" ]] || continue
    chmod 600 "$artifact"
  done
  for artifact in "$stage_dir"/*; do
    [[ -f "$artifact" ]] || continue
    mv "$artifact" "$output_dir/"
  done
  rmdir "$stage_dir"
  stage_dir=""
  finalized=1

  cat "$output_dir/supply-chain-summary.json"
  if [[ "$exit_code" != "0" ]]; then
    printf 'local supply-chain gate failed: %s\n' "$failure_reason" >&2
  fi
  exit "$exit_code"
}

fail_gate() {
  failure_reason="$1"
  status="failed"
  publish_result "${2:-1}"
}

if [[ -z "${SUPPLY_CHAIN_OUTPUT_DIR:-}" ]]; then
  emit_unpersisted_failure "output_directory_required"
  exit 64
fi
case "$SUPPLY_CHAIN_OUTPUT_DIR" in
  /*) ;;
  *)
    emit_unpersisted_failure "output_directory_must_be_absolute"
    exit 64
    ;;
esac
if [[ ! -d "$SUPPLY_CHAIN_OUTPUT_DIR" || -L "$SUPPLY_CHAIN_OUTPUT_DIR" ]]; then
  emit_unpersisted_failure "output_directory_must_be_existing_real_directory"
  exit 64
fi
output_dir="$(cd -- "$SUPPLY_CHAIN_OUTPUT_DIR" && pwd -P)"
case "$output_dir" in
  "$REPOSITORY_ROOT" | "$REPOSITORY_ROOT"/*)
    emit_unpersisted_failure "output_directory_must_be_outside_repository"
    exit 64
    ;;
esac

shopt -s dotglob nullglob
output_entries=("$output_dir"/*)
shopt -u dotglob nullglob
if (( ${#output_entries[@]} != 0 )); then
  emit_unpersisted_failure "output_directory_must_be_empty"
  exit 64
fi

for foundational_tool in chmod mkdir mv rm rmdir; do
  if ! command -v "$foundational_tool" >/dev/null 2>&1; then
    emit_unpersisted_failure "foundational_tool_missing"
    exit 1
  fi
done

stage_dir="$output_dir/.supply-chain-stage.$$"
mkdir "$stage_dir"
work_dir="$stage_dir/work"
mkdir "$work_dir" "$work_dir/home" "$work_dir/tmp" "$work_dir/npm-cache"

required_tools=(cat cmp cp date env git jq node npm shasum sort uv)
for command_name in "${required_tools[@]}"; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    missing_tool="$command_name"
    if [[ "$command_name" == "jq" ]]; then
      printf '{"schema_version":"1.0","status":"failed","proof_level":"local-working-tree-supply-chain","failure_reason":"required_tool_missing","missing_tool":"jq","persisted":true}\n' \
        >"$stage_dir/supply-chain-summary.json"
      chmod 600 "$stage_dir/supply-chain-summary.json"
      mv "$stage_dir/supply-chain-summary.json" "$output_dir/"
      rm -rf "$stage_dir"
      stage_dir=""
      finalized=1
      cat "$output_dir/supply-chain-summary.json"
      printf 'local supply-chain gate failed: required_tool_missing\n' >&2
      exit 1
    fi
    fail_gate "required_tool_missing"
  fi
done

jq_version="$(env -i PATH="$PATH" LC_ALL=C jq --version 2>/dev/null || true)"
uv_version="$(env -i PATH="$PATH" LC_ALL=C uv --version 2>/dev/null || true)"
npm_version="$(env -i PATH="$PATH" HOME="$work_dir/home" LC_ALL=C npm --version 2>/dev/null || true)"
node_version="$(env -i PATH="$PATH" HOME="$work_dir/home" LC_ALL=C node --version 2>/dev/null || true)"
if [[ -z "$jq_version" || -z "$uv_version" || -z "$npm_version" || -z "$node_version" ]]; then
  fail_gate "required_tool_version_probe_failed"
fi
jq_version="${jq_version%%$'\n'*}"
uv_version="${uv_version%%$'\n'*}"
npm_version="${npm_version%%$'\n'*}"
node_version="${node_version%%$'\n'*}"

readonly BACKEND_LOCK="$REPOSITORY_ROOT/backend/uv.lock"
readonly FRONTEND_LOCK="$REPOSITORY_ROOT/frontend/package-lock.json"
readonly FRONTEND_PACKAGE="$REPOSITORY_ROOT/frontend/package.json"
for required_file in "$BACKEND_LOCK" "$FRONTEND_LOCK" "$FRONTEND_PACKAGE"; do
  if [[ ! -f "$required_file" || -L "$required_file" ]]; then
    fail_gate "required_lock_or_manifest_missing"
  fi
done
if [[ -e "$REPOSITORY_ROOT/.npmrc" || -e "$REPOSITORY_ROOT/frontend/.npmrc" ]]; then
  fail_gate "repository_npm_configuration_detected"
fi

source_paths=(
  .dockerignore
  Dockerfile
  Dockerfile.frontend
  docker-compose.yml
  backend
  deploy/agent-server-image.lock
  frontend
  tools/v2
)

generate_source_manifest() {
  local destination="$1"
  local raw_paths="$work_dir/source-paths.raw"
  local sorted_paths="$work_dir/source-paths.sorted"
  local relative_path file_name absolute_path digest_output digest
  local forbidden_environment_name
  local paths=()

  forbidden_environment_name=".$(printf '%s' env)"
  if ! git -C "$REPOSITORY_ROOT" ls-files --cached --others --exclude-standard -z -- \
    "${source_paths[@]}" >"$raw_paths"; then
    return 1
  fi
  while IFS= read -r -d '' relative_path; do
    if [[ "$relative_path" == *$'\n'* || "$relative_path" == *$'\t'* ]]; then
      return 2
    fi
    file_name="${relative_path##*/}"
    if [[ "$file_name" == "$forbidden_environment_name" || "$file_name" == "$forbidden_environment_name".* ]]; then
      return 3
    fi
    paths+=("$relative_path")
  done <"$raw_paths"
  if (( ${#paths[@]} == 0 )); then
    return 4
  fi
  printf '%s\n' "${paths[@]}" | LC_ALL=C sort -u >"$sorted_paths"

  : >"$destination"
  while IFS= read -r relative_path; do
    absolute_path="$REPOSITORY_ROOT/$relative_path"
    if [[ -L "$absolute_path" ]]; then
      return 5
    elif [[ -f "$absolute_path" ]]; then
      digest_output="$(shasum -a 256 "$absolute_path")" || return 6
      digest="${digest_output%% *}"
      printf '%s  FILE:%s\n' "$digest" "$relative_path" >>"$destination"
    elif [[ ! -e "$absolute_path" ]]; then
      printf '%064d  MISSING:%s\n' 0 "$relative_path" >>"$destination"
    else
      return 7
    fi
  done <"$sorted_paths"
}

recheck_source_identity() {
  identity_rechecked=true
  source_stable="false"
  if ! generate_source_manifest "$work_dir/source-manifest-after.sha256"; then
    identity_failure_reason="source_manifest_recheck_failed"
    return 1
  fi
  if ! cmp -s "$stage_dir/source-manifest.sha256" "$work_dir/source-manifest-after.sha256"; then
    identity_failure_reason="source_changed_during_scan"
    return 1
  fi
  if [[ "$(artifact_hash "$BACKEND_LOCK")" != "$backend_lock_sha256" || \
        "$(artifact_hash "$FRONTEND_LOCK")" != "$frontend_lock_sha256" ]]; then
    identity_failure_reason="lockfile_changed_during_scan"
    return 1
  fi
  if [[ "$(git -C "$REPOSITORY_ROOT" rev-parse --verify HEAD 2>/dev/null || true)" != "$git_head" ]]; then
    identity_failure_reason="git_head_changed_during_scan"
    return 1
  fi
  source_stable="true"
  return 0
}

if ! generate_source_manifest "$stage_dir/source-manifest.sha256"; then
  fail_gate "source_manifest_generation_failed"
fi
source_file_count=0
while IFS= read -r _manifest_line; do
  source_file_count=$((source_file_count + 1))
done <"$stage_dir/source-manifest.sha256"
if (( source_file_count == 0 )); then
  fail_gate "source_manifest_zero_files"
fi
source_manifest_sha256="$(artifact_hash "$stage_dir/source-manifest.sha256")"
backend_lock_sha256="$(artifact_hash "$BACKEND_LOCK")"
frontend_lock_sha256="$(artifact_hash "$FRONTEND_LOCK")"
if [[ -z "$source_manifest_sha256" || -z "$backend_lock_sha256" || -z "$frontend_lock_sha256" ]]; then
  fail_gate "source_or_lock_hash_failed"
fi
if ! git_head="$(git -C "$REPOSITORY_ROOT" rev-parse --verify HEAD 2>/dev/null)"; then
  fail_gate "git_head_unavailable"
fi
if ! git -C "$REPOSITORY_ROOT" status --porcelain=v1 --untracked-files=all -- \
  "${source_paths[@]}" >"$work_dir/git-status" 2>/dev/null; then
  fail_gate "git_status_unavailable"
fi
if [[ -s "$work_dir/git-status" ]]; then
  git_dirty=true
fi
identity_ready=1

mkdir "$work_dir/frontend-manifest"
cp "$FRONTEND_PACKAGE" "$work_dir/frontend-manifest/package.json"
cp "$FRONTEND_LOCK" "$work_dir/frontend-manifest/package-lock.json"
: >"$work_dir/npm-user.conf"
: >"$work_dir/npm-global.conf"
frontend_lock_unique_dependency_count="$(jq -r '
  def package_name:
    (.key | capture("node_modules/(?<name>@[^/]+/[^/]+|[^/]+)$").name);
  [
    .packages
    | to_entries[]
    | select(.key != "")
    | {name: package_name, version: .value.version}
    | select((.version | type) == "string" and (.version | length) > 0)
    | "\(.name)@\(.version)"
  ]
  | unique
  | length
' "$work_dir/frontend-manifest/package-lock.json")"
if ! [[ "$frontend_lock_unique_dependency_count" =~ ^[0-9]+$ ]] ||
   (( frontend_lock_unique_dependency_count <= 0 )); then
  fail_gate "frontend_lock_inventory_invalid"
fi

attempted_scans=$((attempted_scans + 1))
python_audit_status="failed"
python_audit_exit=0
env -i \
  PATH="$PATH" \
  HOME="$work_dir/home" \
  TMPDIR="$work_dir/tmp" \
  LC_ALL=C \
  UV_NO_CONFIG=1 \
  UV_DEFAULT_INDEX=https://pypi.org/simple \
  UV_KEYRING_PROVIDER=disabled \
  uv audit \
    --project "$REPOSITORY_ROOT/backend" \
    --locked \
    --no-cache \
    --preview-features audit-command \
    --preview-features json-output \
    --output-format json \
    >"$stage_dir/python-audit.json" 2>"$work_dir/python-audit.stderr" \
  || python_audit_exit=$?
if ! jq -e '
  type == "object" and
  (.schema.version | type == "string") and
  (.summary | type == "object") and
  (.summary.audited_packages | type == "number") and
  (.summary.vulnerabilities | type == "number") and
  (.summary.adverse_statuses | type == "number") and
  (.vulnerabilities | type == "array") and
  (.adverse_statuses | type == "array") and
  .summary.vulnerabilities == (.vulnerabilities | length) and
  .summary.adverse_statuses == (.adverse_statuses | length)
' "$stage_dir/python-audit.json" >/dev/null 2>&1; then
  rm -f "$stage_dir/python-audit.json"
  fail_gate "python_audit_invalid_json_or_schema"
fi
python_audited_packages="$(jq -r '.summary.audited_packages' "$stage_dir/python-audit.json")"
python_vulnerability_count="$(jq -r '.summary.vulnerabilities' "$stage_dir/python-audit.json")"
python_adverse_status_count="$(jq -r '.summary.adverse_statuses' "$stage_dir/python-audit.json")"
if (( python_audited_packages <= 0 )); then
  fail_gate "python_audit_zero_packages"
fi
network_checks_completed=$((network_checks_completed + 1))
completed_scans=$((completed_scans + 1))
python_audit_status="completed"
if (( python_vulnerability_count > 0 || python_adverse_status_count > 0 )); then
  python_audit_status="completed_with_findings"
elif (( python_audit_exit != 0 )); then
  fail_gate "python_audit_transport_or_tool_failure"
fi

attempted_scans=$((attempted_scans + 1))
frontend_audit_status="failed"
frontend_audit_exit=0
(
  cd "$work_dir/frontend-manifest"
  env -i \
    PATH="$PATH" \
    HOME="$work_dir/home" \
    TMPDIR="$work_dir/tmp" \
    LC_ALL=C \
    NPM_CONFIG_USERCONFIG="$work_dir/npm-user.conf" \
    NPM_CONFIG_GLOBALCONFIG="$work_dir/npm-global.conf" \
    NPM_CONFIG_CACHE="$work_dir/npm-cache" \
    npm_config_registry=https://registry.npmjs.org/ \
    npm_config_ignore_scripts=true \
    npm audit \
      --package-lock-only \
      --ignore-scripts \
      --json \
      --audit-level=low
) >"$stage_dir/frontend-audit.json" 2>"$work_dir/frontend-audit.stderr" \
  || frontend_audit_exit=$?
if ! jq -e '
  type == "object" and
  (.auditReportVersion | type == "number") and
  (.metadata.dependencies.total | type == "number") and
  (.metadata.vulnerabilities.total | type == "number") and
  (.vulnerabilities | type == "object")
' "$stage_dir/frontend-audit.json" >/dev/null 2>&1; then
  rm -f "$stage_dir/frontend-audit.json"
  fail_gate "frontend_audit_invalid_json_or_schema"
fi
frontend_audited_dependencies="$(jq -r '.metadata.dependencies.total' "$stage_dir/frontend-audit.json")"
frontend_vulnerability_count="$(jq -r '.metadata.vulnerabilities.total' "$stage_dir/frontend-audit.json")"
if (( frontend_audited_dependencies <= 0 )); then
  fail_gate "frontend_audit_zero_dependencies"
fi
network_checks_completed=$((network_checks_completed + 1))
completed_scans=$((completed_scans + 1))
frontend_audit_status="completed"
if (( frontend_vulnerability_count > 0 )); then
  frontend_audit_status="completed_with_findings"
elif (( frontend_audit_exit != 0 )); then
  fail_gate "frontend_audit_transport_or_tool_failure"
fi

attempted_scans=$((attempted_scans + 1))
python_sbom_status="failed"
if ! env -i \
  PATH="$PATH" \
  HOME="$work_dir/home" \
  TMPDIR="$work_dir/tmp" \
  LC_ALL=C \
  UV_NO_CONFIG=1 \
  UV_DEFAULT_INDEX=https://pypi.org/simple \
  UV_KEYRING_PROVIDER=disabled \
  uv export \
    --project "$REPOSITORY_ROOT/backend" \
    --locked \
    --no-cache \
    --preview-features sbom-export \
    --format cyclonedx1.5 \
    >"$stage_dir/python.cdx.json" 2>"$work_dir/python-sbom.stderr"; then
  rm -f "$stage_dir/python.cdx.json"
  fail_gate "python_sbom_generation_failed"
fi
if ! jq -e '
  type == "object" and
  .bomFormat == "CycloneDX" and
  .specVersion == "1.5" and
  (.metadata.component | type == "object") and
  (.components | type == "array") and
  (.dependencies | type == "array")
' "$stage_dir/python.cdx.json" >/dev/null 2>&1; then
  rm -f "$stage_dir/python.cdx.json"
  fail_gate "python_sbom_invalid_json_or_schema"
fi
python_sbom_component_count="$(jq -r '.components | length' "$stage_dir/python.cdx.json")"
python_sbom_dependency_count="$(jq -r '.dependencies | length' "$stage_dir/python.cdx.json")"
if (( python_sbom_component_count <= 0 || python_sbom_dependency_count <= 0 )); then
  fail_gate "python_sbom_zero_inventory"
fi
if (( python_sbom_component_count != python_audited_packages )); then
  fail_gate "python_audit_sbom_inventory_mismatch"
fi
python_sbom_status="completed"
completed_scans=$((completed_scans + 1))

attempted_scans=$((attempted_scans + 1))
frontend_sbom_status="failed"
if ! (
  cd "$work_dir/frontend-manifest"
  env -i \
    PATH="$PATH" \
    HOME="$work_dir/home" \
    TMPDIR="$work_dir/tmp" \
    LC_ALL=C \
    NPM_CONFIG_USERCONFIG="$work_dir/npm-user.conf" \
    NPM_CONFIG_GLOBALCONFIG="$work_dir/npm-global.conf" \
    NPM_CONFIG_CACHE="$work_dir/npm-cache" \
    npm_config_registry=https://registry.npmjs.org/ \
    npm_config_ignore_scripts=true \
    npm sbom \
      --package-lock-only \
      --sbom-format cyclonedx \
      --sbom-type application
) >"$stage_dir/frontend.cdx.json" 2>"$work_dir/frontend-sbom.stderr"; then
  rm -f "$stage_dir/frontend.cdx.json"
  fail_gate "frontend_sbom_generation_failed"
fi
if ! jq -e '
  type == "object" and
  .bomFormat == "CycloneDX" and
  (.specVersion | type == "string") and
  (.metadata.component | type == "object") and
  (.components | type == "array") and
  (.dependencies | type == "array")
' "$stage_dir/frontend.cdx.json" >/dev/null 2>&1; then
  rm -f "$stage_dir/frontend.cdx.json"
  fail_gate "frontend_sbom_invalid_json_or_schema"
fi
frontend_sbom_component_count="$(jq -r '.components | length' "$stage_dir/frontend.cdx.json")"
frontend_sbom_dependency_count="$(jq -r '.dependencies | length' "$stage_dir/frontend.cdx.json")"
if (( frontend_sbom_component_count <= 0 || frontend_sbom_dependency_count <= 0 )); then
  fail_gate "frontend_sbom_zero_inventory"
fi
if (( frontend_sbom_component_count != frontend_lock_unique_dependency_count )); then
  fail_gate "frontend_sbom_lock_inventory_mismatch"
fi
if (( frontend_sbom_component_count > frontend_audited_dependencies )); then
  fail_gate "frontend_sbom_audit_inventory_mismatch"
fi
frontend_sbom_status="completed"
completed_scans=$((completed_scans + 1))

if ! recheck_source_identity; then
  fail_gate "$identity_failure_reason"
fi

if (( python_vulnerability_count > 0 || python_adverse_status_count > 0 || frontend_vulnerability_count > 0 )); then
  fail_gate "dependency_findings_detected" 2
fi

status="passed"
failure_reason=""
publish_result 0
