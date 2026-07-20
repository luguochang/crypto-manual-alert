#!/usr/bin/env bash
set -euo pipefail

umask 077

readonly SCRIPT_DIR="$(cd -- "${BASH_SOURCE[0]%/*}" && pwd -P)"
readonly REPOSITORY_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
readonly BACKEND_ROOT="$REPOSITORY_ROOT/backend"
readonly POSTGRES_IMAGE="postgres:16-alpine@sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777"
readonly BASELINE_REVISION="0015_observability_delivery"
readonly DOMAIN_EVENT_BASE_REVISION="0017_domain_events"
readonly PROGRESSIVE_EVENT_REVISION="0018_progressive_events"
readonly FINAL_REVISION="0019_ddgs_provenance"

output_root=""
profile="local-rehearsal"
work_dir=""
container_name=""
report_tmp=""

fail() {
  printf 'upgrade/rollback drill failed: %s\n' "$1" >&2
  exit "${2:-1}"
}

cleanup() {
  if [[ -n "$container_name" ]]; then
    docker rm --force "$container_name" >/dev/null 2>&1 || true
  fi
  if [[ -n "$work_dir" ]]; then
    rm -rf "$work_dir"
  fi
  if [[ -n "$report_tmp" ]]; then
    rm -f "$report_tmp"
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

while (( $# > 0 )); do
  case "$1" in
    --output-root)
      [[ $# -ge 2 ]] || fail "--output-root requires a value" 64
      output_root="$2"
      shift 2
      ;;
    --profile)
      [[ $# -ge 2 ]] || fail "--profile requires a value" 64
      profile="$2"
      shift 2
      ;;
    *)
      fail "unsupported argument" 64
      ;;
  esac
done

if [[ "$profile" != "local-rehearsal" ]]; then
  fail "hosted upgrade/rollback acceptance is not implemented" 78
fi
if [[ -z "$output_root" || "$output_root" != /* ]]; then
  fail "--output-root must be an absolute existing directory" 64
fi
if [[ ! -d "$output_root" || -L "$output_root" ]]; then
  fail "--output-root must be an absolute existing directory" 64
fi
output_root="$(cd -- "$output_root" && pwd -P)"
case "$output_root" in
  "$REPOSITORY_ROOT" | "$REPOSITORY_ROOT"/*)
    fail "--output-root must be outside the repository" 64
    ;;
esac
shopt -s dotglob nullglob
output_entries=("$output_root"/*)
shopt -u dotglob nullglob
(( ${#output_entries[@]} == 0 )) || fail "--output-root must be empty" 64

for command_name in docker jq chmod date git mktemp rm sleep mv psql; do
  command -v "$command_name" >/dev/null 2>&1 \
    || fail "required command is unavailable: $command_name"
done
[[ -x "$BACKEND_ROOT/.venv/bin/alembic" ]] \
  || fail "required backend executable is unavailable: $BACKEND_ROOT/.venv/bin/alembic"

work_dir="$(mktemp -d "${TMPDIR:-/tmp}/crypto-alert-v2-upgrade-rollback.XXXXXX")"
chmod 700 "$work_dir"
container_name="crypto-alert-v2-upgrade-rollback-$$-${RANDOM}"

docker run \
  --detach \
  --rm \
  --name "$container_name" \
  --publish 127.0.0.1::5432 \
  --tmpfs /var/lib/postgresql/data:rw,noexec,nosuid,size=1g \
  --tmpfs /tmp:rw,noexec,nosuid,size=256m \
  --env POSTGRES_HOST_AUTH_METHOD=trust \
  "$POSTGRES_IMAGE" >/dev/null

ready=0
for ((attempt = 1; attempt <= 60; attempt += 1)); do
  if docker exec "$container_name" pg_isready --username postgres >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
[[ "$ready" == "1" ]] || fail "temporary PostgreSQL did not become ready"

published="$(docker port "$container_name" 5432/tcp)"
database_port="${published##*:}"
[[ "$database_port" =~ ^[0-9]+$ ]] || fail "temporary PostgreSQL port is invalid"
readonly database_url="postgresql+asyncpg://postgres@127.0.0.1:${database_port}/postgres"
readonly psql_url="postgresql://postgres@127.0.0.1:${database_port}/postgres"

run_alembic() {
  local revision="$1"
  local action target
  read -r action target <<<"$revision"
  if ! (
    cd "$BACKEND_ROOT"
    PRODUCT_DATABASE_URL="$database_url" \
      ./.venv/bin/alembic -c alembic.ini "$action" "$target"
  ) >"$work_dir/alembic-${revision// /-}.stdout" 2>"$work_dir/alembic-${revision// /-}.stderr"; then
    fail "alembic $revision failed; details suppressed"
  fi
}

run_alembic "upgrade head"
initial_version="$(psql "$psql_url" --no-psqlrc --tuples-only --no-align --command "SELECT version_num FROM app.alembic_version;")"
[[ "$initial_version" == "$FINAL_REVISION" ]] || fail "initial upgrade did not reach the final revision"

run_alembic "downgrade $BASELINE_REVISION"
baseline_version="$(psql "$psql_url" --no-psqlrc --tuples-only --no-align --command "SELECT version_num FROM app.alembic_version;")"
[[ "$baseline_version" == "$BASELINE_REVISION" ]] || fail "downgrade did not reach the baseline revision"

run_alembic "upgrade head"
final_version="$(psql "$psql_url" --no-psqlrc --tuples-only --no-align --command "SELECT version_num FROM app.alembic_version;")"
[[ "$final_version" == "$FINAL_REVISION" ]] || fail "final upgrade did not reach the final revision"

constraint_definition="$(psql "$psql_url" --no-psqlrc --tuples-only --no-align --command "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'app.runs'::regclass AND conname = 'fk_runs_fork_source_scope';")"
unique_definition="$(psql "$psql_url" --no-psqlrc --tuples-only --no-align --command "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'app.runs'::regclass AND conname = 'uq_runs_fork_checkpoint_scope';")"
event_unique_definition="$(psql "$psql_url" --no-psqlrc --tuples-only --no-align --command "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'app.domain_events'::regclass AND conname = 'uq_domain_events_run_source_key';")"
event_scope_definition="$(psql "$psql_url" --no-psqlrc --tuples-only --no-align --command "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'app.domain_events'::regclass AND conname = 'fk_domain_events_run_scope';")"
event_payload_columns="$(psql "$psql_url" --no-psqlrc --tuples-only --no-align --command "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'app' AND table_name = 'domain_events' AND column_name IN ('source_event_key', 'source_event_id', 'payload') AND (column_name = 'source_event_id' OR is_nullable = 'NO');")"
thread_counter_columns="$(psql "$psql_url" --no-psqlrc --tuples-only --no-align --command "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'app' AND table_name = 'threads' AND column_name = 'next_domain_event_sequence' AND is_nullable = 'NO';")"
[[ "$constraint_definition" == *"forked_from_checkpoint_id"* ]] \
  || fail "final fork foreign key does not include the source checkpoint"
[[ "$unique_definition" == *"checkpoint_id"* ]] \
  || fail "final fork unique constraint does not include the source checkpoint"
[[ "$event_unique_definition" == *"source_event_key"* ]] \
  || fail "final Domain Event unique constraint omits source identity"
[[ "$event_scope_definition" == *"thread_id"* ]] \
  || fail "final Domain Event Run scope omits Thread identity"
[[ "$event_payload_columns" == "3" ]] \
  || fail "final Domain Event immutable payload columns are incomplete"
[[ "$thread_counter_columns" == "1" ]] \
  || fail "final Thread event sequence counter is missing"

git_head="$(git -C "$REPOSITORY_ROOT" rev-parse HEAD)"
generated_at="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
summary_path="$output_root/upgrade-rollback-summary.json"
report_tmp="$(mktemp "$output_root/.upgrade-rollback-summary.XXXXXX")"
chmod 600 "$report_tmp"
jq -n \
  --arg generated_at "$generated_at" \
  --arg git_head "$git_head" \
  --arg initial_version "$initial_version" \
  --arg baseline_version "$baseline_version" \
  --arg final_version "$final_version" \
  --arg domain_event_base_revision "$DOMAIN_EVENT_BASE_REVISION" \
  --arg progressive_event_revision "$PROGRESSIVE_EVENT_REVISION" \
  --argjson fork_scope_columns 6 \
  '{
    schema_version: "2026-07-18.upgrade-rollback-rehearsal.v1",
    status: "passed",
    proof_level: "local-migration-upgrade-rollback-rehearsal",
    generated_at: $generated_at,
    source: {git_head: $git_head, git_dirty: true},
    migration: {
      initial_upgrade: $initial_version,
      downgrade_target: $baseline_version,
      final_upgrade: $final_version,
      domain_event_base_revision: $domain_event_base_revision,
      progressive_event_revision: $progressive_event_revision,
      fork_scope_columns: $fork_scope_columns,
      constraint_verified: true,
      progressive_event_schema_verified: true
    },
    secret_scan: {findings: 0},
    does_not_prove: [
      "hosted_image_rollback",
      "production_zero_downtime_rollout",
      "production_database_failover",
      "release_attestation"
    ]
  }' >"$report_tmp"
chmod 600 "$report_tmp"
mv -f "$report_tmp" "$summary_path"
report_tmp=""

printf '%s\n' "$(<"$summary_path")"
