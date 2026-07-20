#!/usr/bin/env bash
set -euo pipefail

umask 077

readonly DEFAULT_POSTGRES_IMAGE="postgres:16-alpine@sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777"
readonly RESTORE_DATABASE="restore_rehearsal"

work_dir=""
container_name=""
container_started=0
report_temp=""

fail() {
  printf 'backup/restore rehearsal failed: %s\n' "$1" >&2
  exit 1
}

cleanup() {
  if [[ "$container_started" == "1" && -n "$container_name" ]]; then
    docker rm --force "$container_name" >/dev/null 2>&1 || true
  fi
  if [[ -n "$work_dir" ]]; then
    rm -rf "$work_dir"
  fi
  if [[ -n "$report_temp" ]]; then
    rm -f "$report_temp"
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ -z "${PRODUCT_DATABASE_URL:-}" ]]; then
  printf 'PRODUCT_DATABASE_URL must be set; its value will not be printed\n' >&2
  exit 64
fi

case "$PRODUCT_DATABASE_URL" in
  postgresql+asyncpg://*)
    source_conninfo="postgresql://${PRODUCT_DATABASE_URL#postgresql+asyncpg://}"
    ;;
  postgresql://* | postgres://*)
    source_conninfo="$PRODUCT_DATABASE_URL"
    ;;
  *)
    printf 'PRODUCT_DATABASE_URL must use a PostgreSQL URL scheme\n' >&2
    exit 64
    ;;
esac
unset PRODUCT_DATABASE_URL

postgres_image="${BACKUP_REHEARSAL_POSTGRES_IMAGE:-$DEFAULT_POSTGRES_IMAGE}"
if [[ ! "$postgres_image" =~ ^postgres:16-alpine@sha256:[0-9a-f]{64}$ ]]; then
  fail "BACKUP_REHEARSAL_POSTGRES_IMAGE must be the pinned PostgreSQL 16 Alpine digest"
fi
readonly postgres_image

for command_name in \
  awk chmod cmp date dirname docker mktemp mv pg_dump pg_restore psql \
  python3 rm seq shasum sleep sort wc; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    fail "required command is unavailable: $command_name"
  fi
done

work_dir="$(mktemp -d "${TMPDIR:-/tmp}/crypto-alert-v2-backup-rehearsal.XXXXXX")"
readonly source_environment_file="$work_dir/source-connection.sh"
if ! SOURCE_DATABASE_URL="$source_conninfo" \
  SOURCE_ENVIRONMENT_FILE="$source_environment_file" \
  python3 - <<'PY'
from os import getenv
from pathlib import Path
import shlex
from urllib.parse import parse_qs, unquote, urlsplit

source = getenv("SOURCE_DATABASE_URL")
target_path = getenv("SOURCE_ENVIRONMENT_FILE")
if source is None or target_path is None:
    raise SystemExit("source connection parser environment is incomplete")
target = Path(target_path)
parsed = urlsplit(source)
if parsed.scheme not in {"postgres", "postgresql"}:
    raise SystemExit("unsupported PostgreSQL URL scheme")
if not parsed.hostname or not parsed.username:
    raise SystemExit("PostgreSQL URL requires host and user")
database = unquote(parsed.path.removeprefix("/"))
if not database or "/" in database:
    raise SystemExit("PostgreSQL URL requires one database name")
query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
allowed_query = {
    "application_name": "PGAPPNAME",
    "connect_timeout": "PGCONNECT_TIMEOUT",
    "sslcert": "PGSSLCERT",
    "sslkey": "PGSSLKEY",
    "sslmode": "PGSSLMODE",
    "sslrootcert": "PGSSLROOTCERT",
}
if unknown := set(query) - set(allowed_query):
    raise SystemExit(f"unsupported PostgreSQL URL options: {sorted(unknown)}")
if any(len(values) != 1 for values in query.values()):
    raise SystemExit("PostgreSQL URL options must be singular")

values = {
    "PGHOST": parsed.hostname,
    "PGPORT": str(parsed.port or 5432),
    "PGUSER": unquote(parsed.username),
    "PGDATABASE": database,
}
if parsed.password is not None:
    values["PGPASSWORD"] = unquote(parsed.password)
for query_name, environment_name in allowed_query.items():
    if query_name in query:
        values[environment_name] = query[query_name][0]

target.write_text(
    "".join(
        f"export {name}={shlex.quote(value)}\n"
        for name, value in sorted(values.items())
    ),
    encoding="utf-8",
)
PY
then
  fail "PRODUCT_DATABASE_URL could not be converted to secret-safe libpq settings"
fi
chmod 600 "$source_environment_file"
# shellcheck disable=SC1090
source "$source_environment_file"
rm -f "$source_environment_file"
unset source_conninfo

readonly dump_file="$work_dir/product.dump"
readonly source_before_file="$work_dir/source-before.tsv"
readonly source_after_file="$work_dir/source-after.tsv"
readonly restored_file="$work_dir/restored.tsv"
readonly source_error_file="$work_dir/source-command.stderr"

readonly inventory_query="
SELECT format(
  'SELECT %L || chr(9) || %L || chr(9) || count(*)::text FROM %I.%I;',
  namespace.nspname,
  relation.relname,
  namespace.nspname,
  relation.relname
)
FROM pg_catalog.pg_class AS relation
JOIN pg_catalog.pg_namespace AS namespace
  ON namespace.oid = relation.relnamespace
WHERE relation.relkind IN ('r', 'p')
  AND namespace.nspname <> 'information_schema'
  AND namespace.nspname !~ '^pg_'
ORDER BY namespace.nspname, relation.relname;
"

source_psql() {
  PGAPPNAME="crypto-alert-v2-backup-rehearsal" \
    PGCONNECT_TIMEOUT="5" \
    psql --no-psqlrc --set=ON_ERROR_STOP=1 --tuples-only --no-align "$@"
}

collect_source_inventory() {
  local output_file="$1"
  local statements
  if ! statements="$(source_psql --command "$inventory_query" 2>"$source_error_file")"; then
    fail "source inventory query failed; details suppressed"
  fi
  if [[ -z "$statements" ]]; then
    fail "source database has no user tables"
  fi
  if ! printf '%s\n' "$statements" \
    | source_psql >"$output_file" 2>"$source_error_file"; then
    fail "source table count query failed; details suppressed"
  fi
  LC_ALL=C sort --output="$output_file" "$output_file"
}

collect_restored_inventory() {
  local output_file="$1"
  local statements
  if ! statements="$(
    docker exec "$container_name" \
      psql --username postgres --dbname "$RESTORE_DATABASE" \
      --no-psqlrc --set=ON_ERROR_STOP=1 --tuples-only --no-align \
      --command "$inventory_query"
  )"; then
    fail "restored inventory query failed"
  fi
  if [[ -z "$statements" ]]; then
    fail "restored database has no user tables"
  fi
  if ! printf '%s\n' "$statements" \
    | docker exec --interactive "$container_name" \
      psql --username postgres --dbname "$RESTORE_DATABASE" \
      --no-psqlrc --set=ON_ERROR_STOP=1 --tuples-only --no-align \
      >"$output_file"; then
    fail "restored table count query failed"
  fi
  LC_ALL=C sort --output="$output_file" "$output_file"
}

collect_source_inventory "$source_before_file"

if ! PGAPPNAME="crypto-alert-v2-backup-rehearsal" \
  PGCONNECT_TIMEOUT="5" \
  pg_dump \
    --format=custom \
    --compress=6 \
    --lock-wait-timeout=5s \
    --no-owner \
    --no-privileges \
    --file="$dump_file" \
    2>"$source_error_file"; then
  fail "source pg_dump failed; details suppressed"
fi
if [[ ! -s "$dump_file" ]]; then
  fail "pg_dump produced an empty archive"
fi
if ! pg_restore --list "$dump_file" >/dev/null 2>&1; then
  fail "pg_dump archive cannot be listed by pg_restore"
fi

collect_source_inventory "$source_after_file"
if ! cmp --silent "$source_before_file" "$source_after_file"; then
  fail "source table counts changed during the dump; retry in a quiescent window"
fi

container_name="crypto-alert-v2-backup-rehearsal-$$-${RANDOM}"
if ! docker run \
  --detach \
  --rm \
  --name "$container_name" \
  --network none \
  --tmpfs /var/lib/postgresql/data:rw,noexec,nosuid,size=2g \
  --tmpfs /tmp:rw,noexec,nosuid,size=2g \
  --env POSTGRES_HOST_AUTH_METHOD=trust \
  "$postgres_image" >/dev/null; then
  fail "temporary PostgreSQL container could not start"
fi
container_started=1

restore_ready=0
for _ in $(seq 1 60); do
  if docker exec "$container_name" pg_isready --username postgres >/dev/null 2>&1; then
    restore_ready=1
    break
  fi
  sleep 1
done
if [[ "$restore_ready" != "1" ]]; then
  fail "temporary PostgreSQL container did not become ready"
fi

if ! docker exec "$container_name" \
  createdb --username postgres "$RESTORE_DATABASE" >/dev/null; then
  fail "isolated restore database could not be created"
fi
if ! docker exec --interactive "$container_name" \
  pg_restore \
    --exit-on-error \
    --no-owner \
    --no-privileges \
    --username postgres \
    --dbname "$RESTORE_DATABASE" \
    >/dev/null <"$dump_file"; then
  fail "pg_restore failed in the isolated database"
fi

collect_restored_inventory "$restored_file"
if ! cmp --silent "$source_before_file" "$restored_file"; then
  fail "restored table inventory or row counts do not match the stable source snapshot"
fi

if ! unvalidated_constraints="$(
  docker exec "$container_name" \
    psql --username postgres --dbname "$RESTORE_DATABASE" \
    --no-psqlrc --set=ON_ERROR_STOP=1 --tuples-only --no-align \
    --command "
      SELECT count(*)
      FROM pg_catalog.pg_constraint AS constraint_record
      JOIN pg_catalog.pg_namespace AS namespace
        ON namespace.oid = constraint_record.connamespace
      WHERE NOT constraint_record.convalidated
        AND namespace.nspname <> 'information_schema'
        AND namespace.nspname !~ '^pg_';
    "
)"; then
  fail "restored constraint validation query failed"
fi
if [[ "$unvalidated_constraints" != "0" ]]; then
  fail "restored database contains unvalidated constraints"
fi

table_count="$(wc -l <"$restored_file" | awk '{print $1}')"
row_count="$(awk -F '\t' '{total += $3} END {printf "%.0f", total}' "$restored_file")"
archive_bytes="$(wc -c <"$dump_file" | awk '{print $1}')"
archive_sha256="$(shasum -a 256 "$dump_file" | awk '{print $1}')"
completed_at="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

report="$(printf '%s' \
  "{\"schema_version\":\"2026-07-17.product-backup-restore-rehearsal.v1\"," \
  "\"status\":\"passed\"," \
  "\"proof_level\":\"local-backup-restore-rehearsal\"," \
  "\"completed_at\":\"$completed_at\"," \
  "\"postgres_image\":\"$postgres_image\"," \
  "\"archive_sha256\":\"$archive_sha256\"," \
  "\"archive_bytes\":$archive_bytes," \
  "\"table_count\":$table_count," \
  "\"row_count\":$row_count," \
  "\"source_counts_stable\":true," \
  "\"restored_counts_match\":true," \
  "\"unvalidated_constraints\":0," \
  "\"does_not_prove\":[\"hosted_backup_policy\",\"point_in_time_recovery\",\"cross_region_restore\",\"production_rto_rpo\"]}")"

if [[ -n "${BACKUP_REHEARSAL_REPORT_PATH:-}" ]]; then
  report_directory="$(dirname -- "$BACKUP_REHEARSAL_REPORT_PATH")"
  if [[ ! -d "$report_directory" ]]; then
    fail "BACKUP_REHEARSAL_REPORT_PATH parent directory does not exist"
  fi
  report_temp="$(mktemp "$report_directory/.backup-restore-report.XXXXXX")"
  printf '%s\n' "$report" >"$report_temp"
  chmod 600 "$report_temp"
  mv "$report_temp" "$BACKUP_REHEARSAL_REPORT_PATH"
  report_temp=""
fi

printf '%s\n' "$report"
