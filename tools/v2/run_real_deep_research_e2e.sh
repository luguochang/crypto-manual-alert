#!/usr/bin/env bash
set -euo pipefail

umask 077

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
DEFAULT_PROFILE_FILE="$ROOT_DIR/tools/v2/profiles/real-deep-research.env"
AEGRA_RESTART_SUPERVISOR="$ROOT_DIR/tools/v2/aegra_restart_supervisor.py"
AEGRA_WINDOWS_SERVE="$ROOT_DIR/tools/v2/aegra_windows_serve.py"
POSTGRES_IMAGE="postgres:16-alpine@sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777"
REDIS_IMAGE="public.ecr.aws/docker/library/redis:7-alpine@sha256:6ab0b6e7381779332f97b8ca76193e45b0756f38d4c0dcda72dbb3c32061ab99"

EVIDENCE_DIR=""
EVIDENCE_NATIVE_DIR=""
PYTHON_RUNNER="python3"
PROFILE_FILE="$DEFAULT_PROFILE_FILE"
CHECK_PROFILE=0
CLI_AGENT_PORT=""
CLI_WORKER_PORT=""
CLI_FRONTEND_PORT=""
ENABLE_REDIS_BROKER=0

EVIDENCE_READY=0
TEMP_DIR=""
DATABASE_NAME=""
DATABASE_CREATED=0
DATABASE_MODE=""
DATABASE_CONTAINER=""
DATABASE_CONTAINER_STARTED=0
DATABASE_USER="crypto_alert_e2e"
DATABASE_PASSWORD=""
DATABASE_PORT=""
REDIS_CONTAINER=""
REDIS_CONTAINER_STARTED=0
REDIS_PORT=""
MIGRATION_READY=0
REVIEW_POLICY_CHANGED=0
WORKSPACE_UUID=""
ORIGINAL_REVIEW_POLICY=""

AGENT_PID=""
WORKER_PID=""
FRONTEND_PID=""
E2E_PID=""

PROOF_RESULT="failed"
FAILURE_REASON="unhandled_failure"
RUN_STARTED_AT="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
RUN_COMPLETED_AT=""
SOURCE_HEAD_SHA=""
SOURCE_WORKTREE_DIRTY="unknown"

usage() {
  printf '%s\n' \
    "Usage: $0 --evidence-dir ABSOLUTE_PATH [options]" \
    "       $0 --check-profile [--profile PATH]" \
    "" \
    "Options:" \
    "  --profile PATH         Non-secret runner profile" \
    "  --agent-port PORT      Isolated Aegra Agent Protocol port" \
    "  --worker-port PORT     Isolated unified Worker health port" \
    "  --frontend-port PORT   Isolated production Next port" \
    "  --redis-broker        Run Aegra with an owned isolated Redis broker" \
    "  --check-profile        Validate the profile without starting services" \
    "  --help                 Show this help"
}

die() {
  local status="$1"
  shift
  FAILURE_REASON="$*"
  printf '%s\n' "$*" >&2
  exit "$status"
}

load_profile() {
  local profile="$1"
  local line name value line_number=0

  if [[ ! -f "$profile" ]]; then
    die 66 "Real Deep Research profile is missing: $profile"
  fi
  while IFS= read -r line || [[ -n "$line" ]]; do
    line_number=$((line_number + 1))
    line="${line%$'\r'}"
    case "$line" in
      ''|'#'*)
        continue
        ;;
    esac
    if [[ ! "$line" =~ ^([A-Z][A-Z0-9_]*)=(.*)$ ]]; then
      die 65 "Invalid profile assignment at line $line_number"
    fi
    name="${BASH_REMATCH[1]}"
    value="${BASH_REMATCH[2]}"
    case "$name" in
      APP_ENVIRONMENT|SEARCH_PROVIDER|DEEP_RESEARCH_HARNESS_MODE|\
      REAL_DEEP_RESEARCH_AGENT_PORT|REAL_DEEP_RESEARCH_WORKER_PORT|\
      REAL_DEEP_RESEARCH_FRONTEND_PORT|REAL_DEEP_RESEARCH_DATABASE_PREFIX|\
      REAL_DEEP_RESEARCH_STARTUP_TIMEOUT_SECONDS|\
      REAL_DEEP_RESEARCH_WORKSPACE_TIMEOUT_SECONDS|\
      PLAYWRIGHT_ALLOW_BROWSER_ROUTES|DEVELOPMENT_BOOTSTRAP_ENABLED|\
      DEVELOPMENT_BOOTSTRAP_PROFILE|DEVELOPMENT_BOOTSTRAP_SUBJECT|\
      DEVELOPMENT_BOOTSTRAP_IDENTITY_ISSUER|\
      DEVELOPMENT_BOOTSTRAP_TENANT_ID|\
      DEVELOPMENT_BOOTSTRAP_WORKSPACE_ID|DEVELOPMENT_BOOTSTRAP_ROLES|\
      DEVELOPMENT_BOOTSTRAP_PERMISSIONS)
        ;;
      *)
        die 65 "Profile key is not allowlisted: $name"
        ;;
    esac
    if [[ "$name" =~ (SECRET|TOKEN|PASSWORD|CREDENTIAL|API_KEY|PRIVATE_KEY|LICENSE) ]]; then
      die 65 "Profile must not define credentials: $name"
    fi
    if [[ "$value" == *'$('* || "$value" == *'`'* || "$value" == *'${'* ]]; then
      die 65 "Profile values must be literal at line $line_number"
    fi
    if [[ -z "${!name+x}" ]]; then
      printf -v "$name" '%s' "$value"
      export "$name"
    fi
  done <"$profile"
}

validate_profile() {
  if [[ "${APP_ENVIRONMENT:-}" != "development" ]]; then
    die 65 'Real Deep Research local proof requires APP_ENVIRONMENT=development'
  fi
  if [[ "${SEARCH_PROVIDER:-}" != "builtin_web_search" && \
        "${SEARCH_PROVIDER:-}" != "tavily" ]]; then
    die 65 'SEARCH_PROVIDER must be builtin_web_search or tavily for real evidence'
  fi
  if [[ "${DEEP_RESEARCH_HARNESS_MODE:-}" != "deepagents" ]]; then
    die 65 'Real Deep Research proof requires DEEP_RESEARCH_HARNESS_MODE=deepagents'
  fi
  if [[ "${DEVELOPMENT_BOOTSTRAP_ENABLED:-}" != "true" || \
        "${DEVELOPMENT_BOOTSTRAP_PROFILE:-}" != "local-proof" ]]; then
    die 65 'The profile must explicitly enable the local-proof development bootstrap'
  fi
  for name in \
    DEVELOPMENT_BOOTSTRAP_SUBJECT \
    DEVELOPMENT_BOOTSTRAP_IDENTITY_ISSUER \
    DEVELOPMENT_BOOTSTRAP_TENANT_ID \
    DEVELOPMENT_BOOTSTRAP_WORKSPACE_ID \
    DEVELOPMENT_BOOTSTRAP_ROLES \
    DEVELOPMENT_BOOTSTRAP_PERMISSIONS \
    REAL_DEEP_RESEARCH_DATABASE_PREFIX \
    REAL_DEEP_RESEARCH_STARTUP_TIMEOUT_SECONDS \
    REAL_DEEP_RESEARCH_WORKSPACE_TIMEOUT_SECONDS; do
    if [[ -z "${!name:-}" ]]; then
      die 65 "Profile value must not be empty: $name"
    fi
  done
  if [[ "${DEVELOPMENT_BOOTSTRAP_PERMISSIONS:-}" != *'analysis:read'* || \
        "${DEVELOPMENT_BOOTSTRAP_PERMISSIONS:-}" != *'analysis:write'* ]]; then
    die 65 'Development bootstrap requires analysis read and write permissions'
  fi
  if [[ ! "${REAL_DEEP_RESEARCH_DATABASE_PREFIX:-}" =~ ^[a-z][a-z0-9_]{2,31}$ ]]; then
    die 65 'REAL_DEEP_RESEARCH_DATABASE_PREFIX must be a short PostgreSQL identifier prefix'
  fi
  for name in \
    REAL_DEEP_RESEARCH_STARTUP_TIMEOUT_SECONDS \
    REAL_DEEP_RESEARCH_WORKSPACE_TIMEOUT_SECONDS; do
    if [[ ! "${!name}" =~ ^[1-9][0-9]*$ ]]; then
      die 65 "$name must be a positive integer"
    fi
  done
}

validate_provider_presence() {
  (
    cd "$BACKEND_DIR"
    PROVIDER_PREFLIGHT_FILE="$EVIDENCE_NATIVE_DIR/provider-preflight.json" \
      uv run --frozen python - <<'PY'
import json
import os
from pathlib import Path

from crypto_alert_v2.config import get_settings


settings = get_settings()
openai_present = settings.openai_api_key is not None
tavily_required = settings.search_provider == "tavily"
tavily_present = settings.tavily_api_key is not None
Path(os.environ["PROVIDER_PREFLIGHT_FILE"]).write_text(
    json.dumps(
        {
            "schema_version": "1.0",
            "valid": openai_present and (not tavily_required or tavily_present),
            "search_provider": settings.search_provider,
            "variables": {
                "OPENAI_API_KEY": {"required": True, "present": openai_present},
                "TAVILY_API_KEY": {
                    "required": tavily_required,
                    "present": tavily_present,
                },
            },
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
PY
  )

  if ! jq -e '.variables.OPENAI_API_KEY.present == true' \
    "$EVIDENCE_DIR/provider-preflight.json" >/dev/null; then
    die 78 'Required real Provider environment variable is not configured: OPENAI_API_KEY'
  fi
  if ! jq -e \
    '(.variables.TAVILY_API_KEY.required != true) or (.variables.TAVILY_API_KEY.present == true)' \
    "$EVIDENCE_DIR/provider-preflight.json" >/dev/null; then
    die 78 'Required real Provider environment variable is not configured: TAVILY_API_KEY'
  fi
}

redact_file() {
  local source="$1"
  local destination="$2"
  if [[ ! -f "$source" ]]; then
    return
  fi
  sed -E \
    -e 's/(Authorization:[[:space:]]*Bearer[[:space:]]+)[A-Za-z0-9._~+\/-]+/\1[REDACTED]/Ig' \
    -e 's/(Bearer[[:space:]]+)[A-Za-z0-9._~+\/-]+/\1[REDACTED]/g' \
    -e 's/sk-[A-Za-z0-9_-]{12,}/[REDACTED]/g' \
    -e 's/((api[_-]?key|token|secret|password|credential|private[_-]?key)[=:][[:space:]]*)[^[:space:],]+/\1[REDACTED]/Ig' \
    -e 's#(postgres(ql)?(\+[a-z0-9]+)?://)[^/@[:space:]]+:[^/@[:space:]]+@#\1[REDACTED]@#Ig' \
    "$source" >"$destination"
}

capture_all_logs() {
  if [[ "$EVIDENCE_READY" != "1" || -z "$TEMP_DIR" ]]; then
    return
  fi
  redact_file "$TEMP_DIR/migration.log.raw" "$EVIDENCE_DIR/logs/migration.log"
  redact_file "$TEMP_DIR/build.log.raw" "$EVIDENCE_DIR/logs/build.log"
  redact_file "$TEMP_DIR/agent.log.raw" "$EVIDENCE_DIR/logs/agent.log"
  redact_file "$TEMP_DIR/worker.log.raw" "$EVIDENCE_DIR/logs/worker.log"
  redact_file "$TEMP_DIR/frontend.log.raw" "$EVIDENCE_DIR/logs/frontend.log"
  redact_file "$TEMP_DIR/playwright.log.raw" "$EVIDENCE_DIR/logs/playwright.log"
  redact_file "$TEMP_DIR/cleanup.log.raw" "$EVIDENCE_DIR/logs/cleanup.log"
}

start_owned_process() {
  local working_directory="$1"
  local raw_log="$2"
  shift 2
  (
    cd "$working_directory"
    exec "$PYTHON_RUNNER" -c \
      'import os, shutil, subprocess, sys; getattr(os, "setsid", lambda: None)(); command = sys.argv[1:]; command[0] = shutil.which(command[0]) or command[0]; options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {}; child = subprocess.Popen(command, **options); raise SystemExit(child.wait())' \
      "$@"
  ) >"$raw_log" 2>&1 &
  STARTED_PROCESS_PID=$!
}

stop_owned_process() {
  local pid="$1"
  local attempt native_pid process_line
  if [[ -z "$pid" || ! "$pid" =~ ^[0-9]+$ || "$pid" -le 1 ]]; then
    return
  fi
  if ! kill -0 "$pid" 2>/dev/null; then
    wait "$pid" 2>/dev/null || true
    return
  fi
  case "${OSTYPE:-}" in
    msys*|cygwin*|win32*)
      process_line="$(ps -W -p "$pid" | sed -n '2p')"
      read -r _ _ _ native_pid _ <<<"$process_line"
      if command -v taskkill >/dev/null 2>&1 && \
         [[ "$native_pid" =~ ^[0-9]+$ ]]; then
        taskkill //PID "$native_pid" //T //F >/dev/null 2>&1 || true
      else
        kill "$pid" 2>/dev/null || true
      fi
      wait "$pid" 2>/dev/null || true
      return
      ;;
  esac
  kill -TERM -- "-$pid" 2>/dev/null || true
  for attempt in $(seq 1 50); do
    if ! kill -0 "$pid" 2>/dev/null; then
      break
    fi
    sleep 0.1
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill -KILL -- "-$pid" 2>/dev/null || true
  fi
  wait "$pid" 2>/dev/null || true
}

stop_all_owned_processes() {
  stop_owned_process "$E2E_PID"
  stop_owned_process "$FRONTEND_PID"
  stop_owned_process "$WORKER_PID"
  stop_owned_process "$AGENT_PID"
}

wait_for_http() {
  local url="$1"
  local timeout_seconds="$2"
  local pid="$3"
  local attempt
  for attempt in $(seq 1 "$timeout_seconds"); do
    if [[ -n "$pid" ]] && ! kill -0 "$pid" 2>/dev/null; then
      return 1
    fi
    if curl --fail --silent --show-error --max-time 2 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

port_is_listening() {
  local port="$1"
  "$PYTHON_RUNNER" - "$port" <<'PY'
import socket
import sys

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
    try:
        probe.bind(("127.0.0.1", int(sys.argv[1])))
    except OSError:
        raise SystemExit(0)
raise SystemExit(1)
PY
}

run_psql() {
  if [[ "$DATABASE_MODE" == "docker-postgres-temporary" ]]; then
    docker exec -i "$DATABASE_CONTAINER" \
      psql -U "$DATABASE_USER" "$@"
    return
  fi
  command psql "$@"
}

write_review_policy_receipt() {
  local destination="$1"
  run_psql -X -qAt -v ON_ERROR_STOP=1 -d "$DATABASE_NAME" \
    -v tenant_external_id="$DEVELOPMENT_BOOTSTRAP_TENANT_ID" \
    -v workspace_external_id="$DEVELOPMENT_BOOTSTRAP_WORKSPACE_ID" <<'SQL' >"$destination"
SELECT jsonb_pretty(jsonb_build_object(
  'schema_version', '1.0',
  'observed_at', to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
  'workspace', jsonb_build_object(
    'id', w.id,
    'tenant_id', w.tenant_id,
    'external_id', w.external_id,
    'review_policy', w.review_policy
  )
))
FROM app.workspaces AS w
JOIN app.tenants AS tenant ON tenant.id = w.tenant_id
WHERE tenant.external_id = :'tenant_external_id'
  AND w.external_id = :'workspace_external_id';
SQL
}

set_review_policy_required() {
  run_psql -X -qAt -v ON_ERROR_STOP=1 -d "$DATABASE_NAME" \
    -v workspace_id="$WORKSPACE_UUID" <<'SQL' >"$EVIDENCE_DIR/review-policy-required.json"
WITH changed AS (
  UPDATE app.workspaces
  SET review_policy = 'required', updated_at = clock_timestamp()
  WHERE id = :'workspace_id'::uuid
  RETURNING id, tenant_id, external_id, review_policy
)
SELECT jsonb_pretty(jsonb_build_object(
  'schema_version', '1.0',
  'changed_at', to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
  'changed_rows', count(*),
  'workspace', COALESCE(
    (SELECT jsonb_build_object(
      'id', id,
      'tenant_id', tenant_id,
      'external_id', external_id,
      'review_policy', review_policy
    ) FROM changed),
    'null'::jsonb
  )
))
FROM changed;
SQL
  if ! jq -e '.changed_rows == 1 and .workspace.review_policy == "required"' \
    "$EVIDENCE_DIR/review-policy-required.json" >/dev/null; then
    return 1
  fi
  REVIEW_POLICY_CHANGED=1
}

restore_review_policy() {
  if [[ "$REVIEW_POLICY_CHANGED" != "1" || "$DATABASE_CREATED" != "1" ]]; then
    return 0
  fi
  run_psql -X -qAt -v ON_ERROR_STOP=1 -d "$DATABASE_NAME" \
    -v workspace_id="$WORKSPACE_UUID" \
    -v review_policy="$ORIGINAL_REVIEW_POLICY" <<'SQL' >"$EVIDENCE_DIR/review-policy-restored.json"
WITH restored AS (
  UPDATE app.workspaces
  SET review_policy = :'review_policy', updated_at = clock_timestamp()
  WHERE id = :'workspace_id'::uuid
  RETURNING id, tenant_id, external_id, review_policy
)
SELECT jsonb_pretty(jsonb_build_object(
  'schema_version', '1.0',
  'restored_at', to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
  'restored_rows', count(*),
  'workspace', COALESCE(
    (SELECT jsonb_build_object(
      'id', id,
      'tenant_id', tenant_id,
      'external_id', external_id,
      'review_policy', review_policy
    ) FROM restored),
    'null'::jsonb
  )
))
FROM restored;
SQL
  jq -e \
    --arg expected "$ORIGINAL_REVIEW_POLICY" \
    '.restored_rows == 1 and .workspace.review_policy == $expected' \
    "$EVIDENCE_DIR/review-policy-restored.json" >/dev/null
}

collect_database_evidence() {
  if [[ "$MIGRATION_READY" != "1" || "$DATABASE_CREATED" != "1" ]]; then
    return 1
  fi
  run_psql -X -qAt -v ON_ERROR_STOP=1 -d "$DATABASE_NAME" \
    -v tenant_external_id="$DEVELOPMENT_BOOTSTRAP_TENANT_ID" \
    -v workspace_external_id="$DEVELOPMENT_BOOTSTRAP_WORKSPACE_ID" <<'DATABASE_EVIDENCE_SQL' >"$EVIDENCE_DIR/database-evidence.json"
-- database-evidence-allowlist: identifiers, statuses, lineage coordinates, and hashes only
WITH scoped_workspace AS (
  SELECT w.id, w.tenant_id, w.external_id, w.review_policy
  FROM app.workspaces AS w
  JOIN app.tenants AS tenant ON tenant.id = w.tenant_id
  WHERE tenant.external_id = :'tenant_external_id'
    AND w.external_id = :'workspace_external_id'
),
scoped_tasks AS (
  SELECT task.*
  FROM app.tasks AS task
  JOIN scoped_workspace AS workspace ON workspace.id = task.workspace_id
  WHERE task.task_type = 'deep_research'
)
SELECT jsonb_pretty(jsonb_build_object(
  'schema_version', '1.0',
  'captured_at', to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
  'scope', COALESCE((
    SELECT jsonb_build_object(
      'workspace_id', id,
      'workspace_external_id', external_id,
      'review_policy', review_policy
    ) FROM scoped_workspace
  ), 'null'::jsonb),
  'counts', jsonb_build_object(
    'tasks', (SELECT count(*) FROM scoped_tasks),
    'commands', (SELECT count(*) FROM app.task_commands AS command WHERE command.task_id IN (SELECT id FROM scoped_tasks)),
    'runs', (SELECT count(*) FROM app.runs AS run WHERE run.task_id IN (SELECT id FROM scoped_tasks)),
    'pauses', (SELECT count(*) FROM app.interrupt_pauses AS pause WHERE pause.task_id IN (SELECT id FROM scoped_tasks)),
    'artifacts', (SELECT count(*) FROM app.artifacts AS artifact WHERE artifact.task_id IN (SELECT id FROM scoped_tasks)),
    'versions', (SELECT count(*) FROM app.artifact_versions AS version WHERE version.task_id IN (SELECT id FROM scoped_tasks)),
    'evidence', (SELECT count(*) FROM app.web_evidence AS evidence WHERE evidence.task_id IN (SELECT id FROM scoped_tasks)),
    'decisions', (SELECT count(*) FROM app.decisions AS decision WHERE decision.task_id IN (SELECT id FROM scoped_tasks)),
    'events', (SELECT count(*) FROM app.domain_events AS event WHERE event.task_id IN (SELECT id FROM scoped_tasks))
  ),
  'event_type_counts', COALESCE((
    SELECT jsonb_object_agg(grouped.event_type, grouped.event_count ORDER BY grouped.event_type)
    FROM (
      SELECT event.event_type, count(*) AS event_count
      FROM app.domain_events AS event
      WHERE event.task_id IN (SELECT id FROM scoped_tasks)
      GROUP BY event.event_type
    ) AS grouped
  ), '{}'::jsonb),
  'tasks', COALESCE((
    SELECT jsonb_agg(jsonb_build_object(
      'id', task.id,
      'thread_id', task.thread_id,
      'task_type', task.task_type,
      'status', task.status,
      'request_payload_hash', task.request_payload_hash,
      'completed_at', task.completed_at,
      'counts', jsonb_build_object(
        'commands', (SELECT count(*) FROM app.task_commands AS command WHERE command.task_id = task.id),
        'runs', (SELECT count(*) FROM app.runs AS run WHERE run.task_id = task.id),
        'pauses', (SELECT count(*) FROM app.interrupt_pauses AS pause WHERE pause.task_id = task.id),
        'artifacts', (SELECT count(*) FROM app.artifacts AS artifact WHERE artifact.task_id = task.id),
        'versions', (SELECT count(*) FROM app.artifact_versions AS version WHERE version.task_id = task.id),
        'evidence', (SELECT count(*) FROM app.web_evidence AS evidence WHERE evidence.task_id = task.id),
        'decisions', (SELECT count(*) FROM app.decisions AS decision WHERE decision.task_id = task.id),
        'events', (SELECT count(*) FROM app.domain_events AS event WHERE event.task_id = task.id)
      ),
      'terminal_state', jsonb_build_object(
        'task_status', task.status,
        'run_statuses', COALESCE((SELECT jsonb_agg(run.status ORDER BY run.attempt) FROM app.runs AS run WHERE run.task_id = task.id), '[]'::jsonb),
        'observed_terminal_statuses', COALESCE((SELECT jsonb_agg(run.observed_terminal_status ORDER BY run.attempt) FILTER (WHERE run.observed_terminal_status IS NOT NULL) FROM app.runs AS run WHERE run.task_id = task.id), '[]'::jsonb),
        'failure_codes', COALESCE((SELECT jsonb_agg(run.failure_code ORDER BY run.attempt) FILTER (WHERE run.failure_code IS NOT NULL) FROM app.runs AS run WHERE run.task_id = task.id), '[]'::jsonb),
        'command_statuses', COALESCE((SELECT jsonb_agg(command.status ORDER BY command.sequence) FROM app.task_commands AS command WHERE command.task_id = task.id), '[]'::jsonb)
      ),
      'commands', COALESCE((
        SELECT jsonb_agg(jsonb_build_object(
          'id', command.id,
          'thread_id', command.thread_id,
          'command_type', command.command_type,
          'sequence', command.sequence,
          'status', command.status,
          'attempt', command.attempt,
          'payload_hash', command.payload_hash,
          'official_run_id', command.official_run_id,
          'official_command_id', command.official_command_id
        ) ORDER BY command.sequence)
        FROM app.task_commands AS command
        WHERE command.task_id = task.id
      ), '[]'::jsonb),
      'runs', COALESCE((
        SELECT jsonb_agg(jsonb_build_object(
          'id', run.id,
          'thread_id', run.thread_id,
          'attempt', run.attempt,
          'status', run.status,
          'official_assistant_id', run.official_assistant_id,
          'official_run_id', run.official_run_id,
          'checkpoint_id', run.checkpoint_id,
          'resume_of_run_id', run.resume_of_run_id,
          'retry_of_run_id', run.retry_of_run_id,
          'forked_from_run_id', run.forked_from_run_id,
          'forked_from_checkpoint_id', run.forked_from_checkpoint_id,
          'terminal_output_hash', run.terminal_output_hash,
          'failure_code', run.failure_code,
          'observed_terminal_status', run.observed_terminal_status,
          'started_at', run.started_at,
          'finished_at', run.finished_at
        ) ORDER BY run.attempt)
        FROM app.runs AS run
        WHERE run.task_id = task.id
      ), '[]'::jsonb),
      'pauses', COALESCE((
        SELECT jsonb_agg(jsonb_build_object(
          'id', pause.id,
          'run_id', pause.run_id,
          'pause_version', pause.pause_version,
          'status', pause.status,
          'resume_run_id', pause.resume_run_id,
          'root_thread_id', pause.root_thread_id,
          'root_checkpoint_id', pause.root_checkpoint_id,
          'member_set_hash', pause.member_set_hash,
          'accepted_payload_hash', pause.accepted_payload_hash
        ) ORDER BY pause.created_at, pause.id)
        FROM app.interrupt_pauses AS pause
        WHERE pause.task_id = task.id
      ), '[]'::jsonb),
      'artifacts', COALESCE((
        SELECT jsonb_agg(jsonb_build_object(
          'id', artifact.id,
          'artifact_type', artifact.artifact_type,
          'latest_version_number', artifact.latest_version_number
        ) ORDER BY artifact.created_at, artifact.id)
        FROM app.artifacts AS artifact
        WHERE artifact.task_id = task.id
      ), '[]'::jsonb),
      'artifact_versions', COALESCE((
        SELECT jsonb_agg(jsonb_build_object(
          'id', version.id,
          'artifact_id', version.artifact_id,
          'run_id', version.run_id,
          'version_number', version.version_number,
          'schema_version', version.schema_version,
          'status', version.status,
          'content_sha256', encode(sha256(convert_to(version.content::text, 'UTF8')), 'hex')
        ) ORDER BY version.version_number)
        FROM app.artifact_versions AS version
        WHERE version.task_id = task.id
      ), '[]'::jsonb),
      'web_evidence', COALESCE((
        SELECT jsonb_agg(jsonb_build_object(
          'id', evidence.id,
          'run_id', evidence.run_id,
          'source_url_sha256', encode(sha256(convert_to(evidence.source_url, 'UTF8')), 'hex'),
          'content_hash', NULLIF(evidence.payload->>'content_hash', ''),
          'provider', NULLIF(evidence.payload->>'source', ''),
          'fetched_at', evidence.fetched_at,
          'published_at', evidence.published_at
        ) ORDER BY evidence.created_at, evidence.id)
        FROM app.web_evidence AS evidence
        WHERE evidence.task_id = task.id
      ), '[]'::jsonb),
      'decisions', COALESCE((
        SELECT jsonb_agg(jsonb_build_object(
          'id', decision.id,
          'run_id', decision.run_id,
          'artifact_id', decision.artifact_id,
          'artifact_version_id', decision.artifact_version_id,
          'decision_version', decision.decision_version,
          'lineage_sha256', encode(sha256(convert_to(
            decision.run_id::text || ':' || decision.artifact_id::text || ':' || decision.artifact_version_id::text,
            'UTF8'
          )), 'hex')
        ) ORDER BY decision.created_at, decision.id)
        FROM app.decisions AS decision
        WHERE decision.task_id = task.id
      ), '[]'::jsonb),
      'events', COALESCE((
        SELECT jsonb_agg(jsonb_build_object(
          'id', event.id,
          'run_id', event.run_id,
          'official_run_id', event.official_run_id,
          'checkpoint_id', event.checkpoint_id,
          'event_type', event.event_type,
          'source_event_id', event.source_event_id,
          'payload_ref', event.payload_ref,
          'payload_hash', event.payload_hash,
          'sequence', event.sequence
        ) ORDER BY event.sequence)
        FROM app.domain_events AS event
        WHERE event.task_id = task.id
      ), '[]'::jsonb)
    ) ORDER BY task.created_at, task.id)
    FROM scoped_tasks AS task
  ), '[]'::jsonb)
));
DATABASE_EVIDENCE_SQL
  jq -e '.schema_version == "1.0" and (.tasks | type == "array")' \
    "$EVIDENCE_DIR/database-evidence.json" >/dev/null
  jq '{
    schema_version,
    captured_at,
    tasks: [.tasks[] | {
      id,
      status,
      terminal_state,
      commands: [.commands[] | {id, command_type, sequence, status, payload_hash}],
      runs: [.runs[] | {id, attempt, status, resume_of_run_id, failure_code, observed_terminal_status, terminal_output_hash}]
    }]
  }' "$EVIDENCE_DIR/database-evidence.json" \
    >"$EVIDENCE_DIR/terminal-state-receipt.json"
}

validate_database_evidence() {
  DATABASE_EVIDENCE_FILE="$EVIDENCE_DIR/database-evidence.json" \
    DATABASE_VALIDATION_FILE="$EVIDENCE_DIR/database-validation.json" \
    "$PYTHON_RUNNER" - <<'PY'
import json
import os
from pathlib import Path

source = Path(os.environ["DATABASE_EVIDENCE_FILE"])
destination = Path(os.environ["DATABASE_VALIDATION_FILE"])
errors: list[str] = []

try:
    receipt = json.loads(source.read_text())
except Exception as exc:
    receipt = {}
    errors.append(f"database evidence is unreadable: {type(exc).__name__}")

tasks = receipt.get("tasks", [])
if len(tasks) != 2:
    errors.append(f"expected exactly two successful viewport Tasks, found {len(tasks)}")

for task in tasks:
    task_id = task.get("id", "missing-task-id")
    if task.get("status") != "succeeded":
        errors.append(f"{task_id}: Task status is not succeeded")

    commands = task.get("commands", [])
    command_types = [item.get("command_type") for item in commands]
    if command_types != ["submit", "respond", "respond"]:
        errors.append(f"{task_id}: command lineage is not submit/respond/respond")
    if any(item.get("status") != "dispatched" for item in commands):
        errors.append(f"{task_id}: not every command is dispatched")
    if any(not item.get("payload_hash") for item in commands):
        errors.append(f"{task_id}: a command payload hash is missing")

    runs = task.get("runs", [])
    if len(runs) != 3:
        errors.append(f"{task_id}: expected 3 Runs, found {len(runs)}")
    elif (
        runs[0].get("resume_of_run_id") is not None
        or runs[1].get("resume_of_run_id") != runs[0].get("id")
        or runs[2].get("resume_of_run_id") != runs[1].get("id")
        or [item.get("attempt") for item in runs] != [1, 2, 3]
    ):
        errors.append(f"{task_id}: Run resume lineage is invalid")
    if any(item.get("retry_of_run_id") is not None for item in runs):
        errors.append(f"{task_id}: unexpected retry lineage")
    if any(item.get("forked_from_run_id") is not None for item in runs):
        errors.append(f"{task_id}: unexpected fork lineage")

    pauses = task.get("pauses", [])
    if len(pauses) != 2:
        errors.append(f"{task_id}: expected 2 pauses, found {len(pauses)}")
    elif len(runs) == 3 and (
        pauses[0].get("run_id") != runs[0].get("id")
        or pauses[0].get("resume_run_id") != runs[1].get("id")
        or pauses[1].get("run_id") != runs[1].get("id")
        or pauses[1].get("resume_run_id") != runs[2].get("id")
        or any(item.get("status") != "resolved" for item in pauses)
    ):
        errors.append(f"{task_id}: pause-to-Run lineage is invalid")
    if any(not item.get("member_set_hash") for item in pauses):
        errors.append(f"{task_id}: a pause member-set hash is missing")

    versions = task.get("artifact_versions", [])
    if len(versions) != 1 or versions[0].get("status") != "committed":
        errors.append(f"{task_id}: expected exactly one committed artifact version")
    elif not versions[0].get("content_sha256"):
        errors.append(f"{task_id}: committed artifact hash is missing")
    if len(task.get("decisions", [])) != 0:
        errors.append(f"{task_id}: expected zero decisions")
    if len(task.get("web_evidence", [])) == 0:
        errors.append(f"{task_id}: expected persisted web evidence")
    if any(not item.get("source_url_sha256") for item in task.get("web_evidence", [])):
        errors.append(f"{task_id}: an evidence URL hash is missing")
    if any(not item.get("payload_hash") for item in task.get("events", [])):
        errors.append(f"{task_id}: a domain event payload hash is missing")

summary = {
    "schema_version": "1.0",
    "valid": not errors,
    "task_count": len(tasks),
    "task_ids": [item.get("id") for item in tasks],
    "errors": errors,
}
destination.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
raise SystemExit(0 if not errors else 1)
PY
}

ensure_reporter_artifacts() {
  mkdir -p "$EVIDENCE_DIR/html" "$EVIDENCE_DIR/test-results"
  if [[ ! -s "$EVIDENCE_DIR/junit.xml" ]]; then
    cat >"$EVIDENCE_DIR/junit.xml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<testsuites name="real-deep-research-runner" tests="1" failures="0" skipped="0" errors="1">
  <testsuite name="runner-preflight" hostname="runner-preflight" tests="1" failures="0" skipped="0" errors="1">
    <testcase name="runner reached a typed terminal failure" classname="runner-preflight">
      <error message="Playwright JUnit was not produced">See run-status.json and logs for the typed runner failure.</error>
    </testcase>
  </testsuite>
</testsuites>
XML
  fi
  if [[ ! -s "$EVIDENCE_DIR/results.json" ]]; then
    if command -v jq >/dev/null 2>&1; then
      jq -n \
        --arg schema_version "1.0" \
        --arg status "runner_failure" \
        --arg reason "$FAILURE_REASON" \
        '{schema_version:$schema_version,status:$status,failure_reason:$reason,playwright_report_missing:true}' \
        >"$EVIDENCE_DIR/results.json"
    else
      RESULTS_EVIDENCE_DIR="$EVIDENCE_NATIVE_DIR" RESULTS_FAILURE_REASON="$FAILURE_REASON" \
        "$PYTHON_RUNNER" - <<'PY'
import json
import os
from pathlib import Path

Path(os.environ["RESULTS_EVIDENCE_DIR"] + "/results.json").write_text(
    json.dumps(
        {
            "schema_version": "1.0",
            "status": "runner_failure",
            "failure_reason": os.environ["RESULTS_FAILURE_REASON"],
            "playwright_report_missing": True,
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
PY
    fi
  fi
  if [[ ! -s "$EVIDENCE_DIR/html/index.html" ]]; then
    cat >"$EVIDENCE_DIR/html/index.html" <<'HTML'
<!doctype html><html lang="en"><meta charset="utf-8"><title>Runner failure</title><body><h1>Real Deep Research runner failure</h1><p>See run-status.json and logs.</p></body></html>
HTML
  fi
  if [[ -z "$(find "$EVIDENCE_DIR/test-results" -type f -print -quit)" ]]; then
    if command -v jq >/dev/null 2>&1; then
      jq -n \
        --arg schema_version "1.0" \
        --arg status "runner_failure" \
        '{schema_version:$schema_version,status:$status,playwright_test_results_missing:true}' \
        >"$EVIDENCE_DIR/test-results/runner-receipt.json"
    else
      RESULTS_EVIDENCE_DIR="$EVIDENCE_NATIVE_DIR" "$PYTHON_RUNNER" - <<'PY'
import json
import os
from pathlib import Path

Path(os.environ["RESULTS_EVIDENCE_DIR"] + "/test-results/runner-receipt.json").write_text(
    json.dumps(
        {
            "schema_version": "1.0",
            "status": "runner_failure",
            "playwright_test_results_missing": True,
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
PY
    fi
  fi
}

validate_junit_contract() {
  local expect_green="$1"
  REAL_DEEP_RESEARCH_JUNIT="$EVIDENCE_DIR/junit.xml" \
    REAL_DEEP_RESEARCH_JUNIT_VALIDATION="$EVIDENCE_DIR/junit-validation.json" \
    REAL_DEEP_RESEARCH_EXPECT_GREEN="$expect_green" \
    "$PYTHON_RUNNER" - <<'PY'
import json
import os
from pathlib import Path
from xml.etree import ElementTree

report = Path(os.environ["REAL_DEEP_RESEARCH_JUNIT"])
destination = Path(os.environ["REAL_DEEP_RESEARCH_JUNIT_VALIDATION"])
expected_projects = {"fixture-desktop", "fixture-pixel-7"}
errors: list[str] = []
cases: list[dict[str, str]] = []
project_counts: dict[str, int] = {}

try:
    root = ElementTree.parse(report).getroot()
except Exception as exc:
    root = None
    errors.append(f"JUnit is unreadable: {type(exc).__name__}")

if root is not None:
    for suite in root.iter("testsuite"):
        project = suite.get("hostname", "")
        direct_cases = list(suite.findall("testcase"))
        if direct_cases:
            project_counts[project] = project_counts.get(project, 0) + len(direct_cases)
        for case in direct_cases:
            outcomes = [
                name for name in ("failure", "error", "skipped")
                if case.find(name) is not None
            ]
            cases.append({
                "project": project,
                "classname": case.get("classname", ""),
                "name": case.get("name", ""),
                "outcome": ",".join(outcomes) if outcomes else "passed",
            })
            if "skipped" in outcomes:
                errors.append(f"{project}: skipped testcase is forbidden")

    observed_projects = {name for name, count in project_counts.items() if count > 0}
    missing = sorted(expected_projects - observed_projects)
    unexpected = sorted(observed_projects - expected_projects)
    if missing:
        errors.append("missing project testcase(s): " + ", ".join(missing))
    if unexpected:
        errors.append("unexpected JUnit project(s): " + ", ".join(unexpected))
    for project in sorted(expected_projects):
        if project_counts.get(project) != 1:
            errors.append(
                f"{project}: expected exactly one testcase, found {project_counts.get(project, 0)}"
            )
    if os.environ["REAL_DEEP_RESEARCH_EXPECT_GREEN"] == "1":
        non_green = [item for item in cases if item["outcome"] != "passed"]
        if non_green:
            errors.append("green Playwright exit contained failure or error outcomes")

summary = {
    "schema_version": "1.0",
    "valid": not errors,
    "expected_projects": sorted(expected_projects),
    "project_testcase_counts": project_counts,
    "testcases": cases,
    "errors": errors,
}

destination.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
raise SystemExit(0 if not errors else 1)
PY
}

validate_aegra_restart_receipts() {
  RESTART_EVIDENCE_DIR="$EVIDENCE_NATIVE_DIR" "$PYTHON_RUNNER" - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path

root = Path(os.environ["RESTART_EVIDENCE_DIR"])
projects = ("fixture-desktop", "fixture-pixel-7")
errors: list[str] = []
receipts: list[dict[str, object]] = []
for project in projects:
    path = root / f"aegra-restart-receipt-{project}.json"
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{project}: unreadable restart receipt ({type(exc).__name__})")
        continue
    if not isinstance(receipt, dict):
        errors.append(f"{project}: receipt is not an object")
        continue
    request = receipt.get("request")
    before = receipt.get("generation_before")
    after = receipt.get("generation_after")
    if receipt.get("project") != project or not isinstance(request, dict):
        errors.append(f"{project}: receipt identity is invalid")
        continue
    if request.get("project") != project or request.get("review_iteration") != 1:
        errors.append(f"{project}: request did not target first review")
    if not isinstance(before, dict) or not isinstance(after, dict):
        errors.append(f"{project}: generation receipt is missing")
    elif before.get("pid") == after.get("pid"):
        errors.append(f"{project}: Aegra process generation did not change")
    if receipt.get("target_unavailable_observed") is not True:
        errors.append(f"{project}: target unavailability was not observed")
    if receipt.get("target_recovered_observed") is not True:
        errors.append(f"{project}: target recovery was not observed")
    receipts.append(receipt)

summary = {
    "schema_version": "1.0",
    "valid": not errors and len(receipts) == len(projects),
    "expected_projects": list(projects),
    "receipt_count": len(receipts),
    "projects": [receipt.get("project") for receipt in receipts],
    "task_ids": [receipt.get("request", {}).get("task_id") for receipt in receipts],
    "thread_ids": [receipt.get("request", {}).get("thread_id") for receipt in receipts],
    "run_ids": [receipt.get("request", {}).get("run_id") for receipt in receipts],
    "errors": errors,
}
(root / "aegra-restart-validation.json").write_text(
    json.dumps(summary, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
raise SystemExit(0 if summary["valid"] else 1)
PY
}

write_run_status() {
  local exit_code="$1"
  RUN_COMPLETED_AT="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  if ! command -v jq >/dev/null 2>&1; then
    STATUS_EVIDENCE_DIR="$EVIDENCE_NATIVE_DIR" \
    STATUS_EXIT_CODE="$exit_code" \
    STATUS_RESULT="$PROOF_RESULT" \
    STATUS_FAILURE_REASON="$FAILURE_REASON" \
    STATUS_STARTED_AT="$RUN_STARTED_AT" \
    STATUS_COMPLETED_AT="$RUN_COMPLETED_AT" \
      "$PYTHON_RUNNER" - <<'PY'
import json
import os
from pathlib import Path

Path(os.environ["STATUS_EVIDENCE_DIR"] + "/run-status.json").write_text(
    json.dumps(
        {
            "schema_version": "1.0",
            "result": os.environ["STATUS_RESULT"],
            "exit_code": int(os.environ["STATUS_EXIT_CODE"]),
            "failure_reason": os.environ["STATUS_FAILURE_REASON"] or None,
            "started_at": os.environ["STATUS_STARTED_AT"],
            "completed_at": os.environ["STATUS_COMPLETED_AT"],
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
PY
    return
  fi
  jq -n \
    --arg schema_version "1.0" \
    --arg result "$PROOF_RESULT" \
    --arg failure_reason "$FAILURE_REASON" \
    --arg started_at "$RUN_STARTED_AT" \
    --arg completed_at "$RUN_COMPLETED_AT" \
    --argjson exit_code "$exit_code" \
    '{schema_version:$schema_version,result:$result,exit_code:$exit_code,failure_reason:(if $failure_reason == "" then null else $failure_reason end),started_at:$started_at,completed_at:$completed_at}' \
    >"$EVIDENCE_DIR/run-status.json"
}

write_evidence_manifest() {
  local hash_file="$EVIDENCE_DIR/artifact-sha256.txt"
  local path relative digest_output artifacts_json database_summary junit_summary provider_summary restart_summary
  local -a sha256_command=()
  : >"$hash_file"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256_command=(sha256sum)
  elif command -v shasum >/dev/null 2>&1; then
    sha256_command=(shasum -a 256)
  fi
  if ! command -v jq >/dev/null 2>&1 || ((${#sha256_command[@]} == 0)); then
    MANIFEST_EVIDENCE_DIR="$EVIDENCE_NATIVE_DIR" \
    MANIFEST_RESULT="$PROOF_RESULT" \
    MANIFEST_FAILURE_REASON="$FAILURE_REASON" \
    MANIFEST_CANDIDATE_SHA="$SOURCE_HEAD_SHA" \
    MANIFEST_WORKTREE_DIRTY="$SOURCE_WORKTREE_DIRTY" \
    MANIFEST_STARTED_AT="$RUN_STARTED_AT" \
    MANIFEST_COMPLETED_AT="$RUN_COMPLETED_AT" \
      "$PYTHON_RUNNER" - <<'PY'
import json
import os
from pathlib import Path

root = Path(os.environ["MANIFEST_EVIDENCE_DIR"])
failure_reason = os.environ["MANIFEST_FAILURE_REASON"]
provider_path = root / "provider-preflight.json"
provider_preflight = (
    json.loads(provider_path.read_text(encoding="utf-8"))
    if provider_path.is_file()
    else None
)
if provider_preflight is not None and provider_preflight.get("valid") is False:
    preflight_limitation = (
        "preflight stopped before runtime because required real Provider "
        "environment configuration was absent"
    )
elif "tool is unavailable" in failure_reason.lower():
    preflight_limitation = (
        "preflight stopped before runtime because a required host tool was unavailable"
    )
else:
    preflight_limitation = "preflight stopped before the complete runtime proof"
files = sorted(
    str(path.relative_to(root)).replace("\\", "/")
    for path in root.rglob("*")
    if path.is_file() and path.name not in {"artifact-sha256.txt", "evidence-manifest.json"}
)
(root / "evidence-manifest.json").write_text(
    json.dumps(
        {
            "schema_version": "1.0",
            "proof_scope": "local-real-deep-research-e2e",
            "result": os.environ["MANIFEST_RESULT"],
            "failure_reason": failure_reason or None,
            "source": {
                "head": os.environ["MANIFEST_CANDIDATE_SHA"],
                "dirty": os.environ["MANIFEST_WORKTREE_DIRTY"] == "true",
                "immutable_candidate": False,
            },
            "time": {
                "started_at": os.environ["MANIFEST_STARTED_AT"],
                "completed_at": os.environ["MANIFEST_COMPLETED_AT"],
            },
            "provider_preflight": provider_preflight,
            "artifacts": [{"file": file, "sha256": None} for file in files],
            "limitations": [
                preflight_limitation,
                "failure manifest fallback omitted artifact hashes because jq or a SHA-256 tool was unavailable",
            ],
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
PY
    return
  fi
  while IFS= read -r path; do
    relative="${path#"$EVIDENCE_DIR/"}"
    case "$relative" in
      artifact-sha256.txt|evidence-manifest.json)
        continue
        ;;
    esac
    digest_output="$("${sha256_command[@]}" "$path")"
    printf '%s  %s\n' "${digest_output%% *}" "$relative" >>"$hash_file"
  done < <(find "$EVIDENCE_DIR" -type f -print | LC_ALL=C sort)
  artifacts_json="$(jq -Rn '[inputs | capture("^(?<sha256>[0-9a-f]{64})  (?<file>.+)$")]' <"$hash_file")"
  database_summary='null'
  if [[ -s "$EVIDENCE_DIR/database-evidence.json" ]]; then
    database_summary="$(jq -c '{counts,task_ids:[.tasks[].id],task_statuses:[.tasks[].status]}' "$EVIDENCE_DIR/database-evidence.json")"
  fi
  junit_summary='null'
  if [[ -s "$EVIDENCE_DIR/junit-validation.json" ]]; then
    junit_summary="$(jq -c '{valid,project_testcase_counts,errors}' "$EVIDENCE_DIR/junit-validation.json")"
  fi
  restart_summary='null'
  if [[ -s "$EVIDENCE_DIR/aegra-restart-validation.json" ]]; then
    restart_summary="$(jq -c '{valid,receipt_count,projects,task_ids,thread_ids,run_ids,errors}' "$EVIDENCE_DIR/aegra-restart-validation.json")"
  fi
  provider_summary='null'
  if [[ -s "$EVIDENCE_DIR/provider-preflight.json" ]]; then
    provider_summary="$(jq -c '{valid,search_provider,variables}' "$EVIDENCE_DIR/provider-preflight.json")"
  fi
  jq -n \
    --arg schema_version "1.0" \
    --arg proof_scope "local-real-deep-research-e2e" \
    --arg result "$PROOF_RESULT" \
    --arg failure_reason "$FAILURE_REASON" \
    --arg candidate_sha "$SOURCE_HEAD_SHA" \
    --arg source_worktree_dirty "$SOURCE_WORKTREE_DIRTY" \
    --arg started_at "$RUN_STARTED_AT" \
    --arg completed_at "$RUN_COMPLETED_AT" \
    --arg profile "${PROFILE_FILE#"$ROOT_DIR/"}" \
    --arg database_mode "$DATABASE_MODE" \
    --arg agent_port "${AGENT_PORT:-}" \
    --arg worker_port "${WORKER_PORT:-}" \
    --arg frontend_port "${FRONTEND_PORT:-}" \
    --arg redis_broker_enabled "${REDIS_BROKER_ENABLED:-false}" \
    --arg redis_port "${REDIS_PORT:-}" \
    --argjson artifacts "$artifacts_json" \
    --argjson database_summary "$database_summary" \
    --argjson junit_summary "$junit_summary" \
    --argjson provider_summary "$provider_summary" \
    --argjson restart_summary "$restart_summary" \
    '{schema_version:$schema_version,proof_scope:$proof_scope,result:$result,failure_reason:(if $failure_reason == "" then null else $failure_reason end),source:{head:$candidate_sha,dirty:($source_worktree_dirty == "true"),immutable_candidate:false},time:{started_at:$started_at,completed_at:$completed_at},profile:$profile,topology:{database_mode:$database_mode,agent_port:(if $agent_port == "" then null else ($agent_port|tonumber) end),worker_health_port:(if $worker_port == "" then null else ($worker_port|tonumber) end),frontend_port:(if $frontend_port == "" then null else ($frontend_port|tonumber) end),redis_broker_enabled:($redis_broker_enabled == "true"),redis_port:(if $redis_port == "" then null else ($redis_port|tonumber) end),next_runtime:"production-build-start",langgraph_runtime:(if $redis_broker_enabled == "true" then "aegra-0.9.24-redis-broker" else "aegra-0.9.24-local-executor" end),worker_runtime:"unified"},provider_preflight:$provider_summary,junit:$junit_summary,database:$database_summary,aegra_restart:$restart_summary,artifacts:$artifacts,hash_policy:{algorithm:"sha256",manifest_self_hash_excluded:true,hash_list_self_hash_excluded:true},limitations:(["real provider execution depends on credentials loaded by application Settings or caller ambient injection","Aegra is restarted only after a completed waiting_human checkpoint; active Product worker recovery is not proved"] + (if $redis_broker_enabled == "true" then ["Redis broker is enabled, but the restart occurs after a completed checkpoint; active Aegra worker lease/reaper recovery is not proved"] else ["Aegra Redis broker is disabled in this local compatibility run, so worker crash recovery is not proved"] end) + ["dirty working-tree evidence is not an immutable release candidate","manifest self hash is intentionally excluded"])}' \
    >"$EVIDENCE_DIR/evidence-manifest.json"
}

cleanup() {
  local status=$?
  local cleanup_failed=0
  trap - EXIT INT TERM
  set +e

  stop_all_owned_processes
  if [[ "$EVIDENCE_READY" == "1" ]]; then
    if [[ "$MIGRATION_READY" == "1" && ! -s "$EVIDENCE_DIR/database-evidence.json" ]]; then
      collect_database_evidence >>"$TEMP_DIR/cleanup.log.raw" 2>&1 || true
    fi
    if ! restore_review_policy >>"$TEMP_DIR/cleanup.log.raw" 2>&1; then
      cleanup_failed=1
      FAILURE_REASON="review_policy_restore_failed"
    fi
  fi
  if [[ "$DATABASE_CONTAINER_STARTED" == "1" ]]; then
    if ! docker rm --force --volumes "$DATABASE_CONTAINER" \
      >>"$TEMP_DIR/cleanup.log.raw" 2>&1; then
      cleanup_failed=1
      FAILURE_REASON="temporary_database_cleanup_failed"
    fi
    DATABASE_CONTAINER_STARTED=0
  elif [[ "$DATABASE_CREATED" == "1" ]] && \
       ! dropdb --if-exists --force "$DATABASE_NAME" \
      >>"$TEMP_DIR/cleanup.log.raw" 2>&1; then
    cleanup_failed=1
    FAILURE_REASON="temporary_database_cleanup_failed"
  fi
  if [[ "$DATABASE_CREATED" == "1" ]]; then
    DATABASE_CREATED=0
  fi
  if [[ "$REDIS_CONTAINER_STARTED" == "1" ]]; then
    if docker rm --force --volumes "$REDIS_CONTAINER" \
      >>"$TEMP_DIR/cleanup.log.raw" 2>&1; then
      jq -n \
        --arg schema_version "1.0" \
        --arg container "$REDIS_CONTAINER" \
        '{schema_version:$schema_version,container:$container,removed:true}' \
        >"$EVIDENCE_DIR/redis-broker-cleanup.json"
    else
      cleanup_failed=1
      FAILURE_REASON="temporary_redis_cleanup_failed"
      jq -n \
        --arg schema_version "1.0" \
        --arg container "$REDIS_CONTAINER" \
        '{schema_version:$schema_version,container:$container,removed:false}' \
        >"$EVIDENCE_DIR/redis-broker-cleanup.json" || true
    fi
    REDIS_CONTAINER_STARTED=0
  fi
  if [[ "$EVIDENCE_READY" == "1" ]]; then
    capture_all_logs
    ensure_reporter_artifacts
    if ((cleanup_failed != 0)); then
      status=70
      PROOF_RESULT="failed"
    elif ((status != 0)); then
      PROOF_RESULT="failed"
    fi
    write_run_status "$status" || true
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

while (($# > 0)); do
  case "$1" in
    --evidence-dir)
      if (($# < 2)) || [[ -z "$2" || -n "$EVIDENCE_DIR" ]]; then
        die 64 '--evidence-dir requires exactly one non-empty value'
      fi
      EVIDENCE_DIR="$2"
      shift 2
      ;;
    --profile)
      if (($# < 2)) || [[ -z "$2" ]]; then
        die 64 '--profile requires a non-empty path'
      fi
      PROFILE_FILE="$2"
      shift 2
      ;;
    --agent-port)
      CLI_AGENT_PORT="${2:-}"
      shift 2
      ;;
    --worker-port)
      CLI_WORKER_PORT="${2:-}"
      shift 2
      ;;
    --frontend-port)
      CLI_FRONTEND_PORT="${2:-}"
      shift 2
      ;;
    --redis-broker)
      ENABLE_REDIS_BROKER=1
      shift
      ;;
    --check-profile)
      CHECK_PROFILE=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      usage >&2
      die 64 "Unknown real Deep Research runner option: $1"
      ;;
  esac
done

if [[ "$PROFILE_FILE" != /* ]]; then
  PROFILE_FILE="$ROOT_DIR/$PROFILE_FILE"
fi
load_profile "$PROFILE_FILE"
validate_profile
if [[ "$CHECK_PROFILE" == "1" ]]; then
  printf 'Profile contract is valid: %s\n' "$PROFILE_FILE"
  PROOF_RESULT="passed"
  FAILURE_REASON=""
  exit 0
fi

if [[ -z "$EVIDENCE_DIR" ]]; then
  usage >&2
  die 64 'An explicit absolute --evidence-dir is required'
fi
if [[ "$EVIDENCE_DIR" != /* ]]; then
  die 64 '--evidence-dir must be an absolute path'
fi
if [[ -e "$EVIDENCE_DIR" && ! -d "$EVIDENCE_DIR" ]]; then
  die 64 '--evidence-dir must name a directory'
fi
if [[ -d "$EVIDENCE_DIR" && -n "$(ls -A "$EVIDENCE_DIR")" ]]; then
  die 64 '--evidence-dir must initially be absent or empty'
fi
mkdir -p "$EVIDENCE_DIR"
EVIDENCE_DIR="$(cd "$EVIDENCE_DIR" && pwd -P)"
if command -v cygpath >/dev/null 2>&1; then
  EVIDENCE_NATIVE_DIR="$(cygpath -w "$EVIDENCE_DIR")"
else
EVIDENCE_NATIVE_DIR="$EVIDENCE_DIR"
fi
if command -v python.exe >/dev/null 2>&1; then
  PYTHON_RUNNER="python.exe"
fi
mkdir -p "$EVIDENCE_DIR/logs" "$EVIDENCE_DIR/html" "$EVIDENCE_DIR/test-results"
for log_name in migration build agent worker frontend playwright cleanup; do
  printf 'not started by runner\n' >"$EVIDENCE_DIR/logs/$log_name.log"
done
EVIDENCE_READY=1
TEMP_DIR="$(mktemp -d -t crypto-alert-real-deep-research.XXXXXX)"
: >"$TEMP_DIR/cleanup.log.raw"

if ! command -v git >/dev/null 2>&1; then
  die 69 'Required real Deep Research runner tool is unavailable: git'
fi
SOURCE_HEAD_SHA="$(git -C "$ROOT_DIR" rev-parse --verify HEAD)"
if [[ -n "$(git -C "$ROOT_DIR" status --porcelain --untracked-files=normal)" ]]; then
  SOURCE_WORKTREE_DIRTY="true"
else
  SOURCE_WORKTREE_DIRTY="false"
fi

for command_name in \
  curl find jq npm openssl ps sed seq uv; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    die 69 "Required real Deep Research runner tool is unavailable: $command_name"
  fi
done
if ! command -v sha256sum >/dev/null 2>&1 && ! command -v shasum >/dev/null 2>&1; then
  die 69 'Required real Deep Research runner tool is unavailable: sha256sum or shasum'
fi
if ! command -v "$PYTHON_RUNNER" >/dev/null 2>&1; then
  die 69 "Required real Deep Research runner tool is unavailable: $PYTHON_RUNNER"
fi
validate_provider_presence
if command -v createdb >/dev/null 2>&1 && \
   command -v dropdb >/dev/null 2>&1 && \
   command -v psql >/dev/null 2>&1; then
  DATABASE_MODE="createdb-dropdb-local-temporary"
elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  DATABASE_MODE="docker-postgres-temporary"
else
  die 69 'A local PostgreSQL CLI or a ready Docker daemon is required'
fi
if [[ "$ENABLE_REDIS_BROKER" == "1" ]] && \
   (! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1); then
  die 69 'Redis broker mode requires a ready Docker daemon'
fi
for required_path in \
  "$BACKEND_DIR/alembic.ini" \
  "$BACKEND_DIR/langgraph.json" \
  "$AEGRA_RESTART_SUPERVISOR" \
  "$AEGRA_WINDOWS_SERVE" \
  "$FRONTEND_DIR/package.json" \
  "$FRONTEND_DIR/playwright.config.ts" \
  "$FRONTEND_DIR/tests/e2e-product/real-deep-research-flow.spec.ts"; do
  if [[ ! -f "$required_path" ]]; then
    die 66 "Required real Deep Research source is missing: $required_path"
  fi
done
if [[ ! -x "$FRONTEND_DIR/node_modules/.bin/playwright" || \
      ! -x "$FRONTEND_DIR/node_modules/.bin/next" ]]; then
  die 69 'Frontend dependencies are unavailable; run npm ci in frontend first'
fi

AGENT_PORT="${CLI_AGENT_PORT:-${REAL_DEEP_RESEARCH_AGENT_PORT:-}}"
WORKER_PORT="${CLI_WORKER_PORT:-${REAL_DEEP_RESEARCH_WORKER_PORT:-}}"
FRONTEND_PORT="${CLI_FRONTEND_PORT:-${REAL_DEEP_RESEARCH_FRONTEND_PORT:-}}"
for port_name in AGENT_PORT WORKER_PORT FRONTEND_PORT; do
  port_value="${!port_name}"
  if [[ ! "$port_value" =~ ^[0-9]+$ ]] || \
     ((port_value < 1 || port_value > 65535)); then
    die 64 "$port_name must be an integer between 1 and 65535"
  fi
  if [[ "$port_value" == "3110" ]]; then
    die 64 'Port 3110 is reserved for the user-owned service and will not be used or killed'
  fi
  if port_is_listening "$port_value"; then
    die 69 "$port_name is already in use; choose an isolated port"
  fi
done
if [[ "$AGENT_PORT" == "$WORKER_PORT" || "$AGENT_PORT" == "$FRONTEND_PORT" || \
      "$WORKER_PORT" == "$FRONTEND_PORT" ]]; then
  die 64 'Agent, Worker, and frontend ports must be distinct'
fi

DATABASE_NAME="${REAL_DEEP_RESEARCH_DATABASE_PREFIX}_$(date -u +%Y%m%d%H%M%S)_$$_${RANDOM}"
if ((${#DATABASE_NAME} > 63)); then
  die 65 'Generated PostgreSQL database name exceeds the identifier limit'
fi
if [[ "$DATABASE_MODE" == "docker-postgres-temporary" ]]; then
  DATABASE_CONTAINER="crypto-alert-real-deep-research-db-$$_${RANDOM}"
  DATABASE_PASSWORD="$(openssl rand -hex 24)"
  if ! docker run --detach --name "$DATABASE_CONTAINER" \
    --publish 127.0.0.1::5432 \
    --env POSTGRES_DB="$DATABASE_NAME" \
    --env POSTGRES_USER="$DATABASE_USER" \
    --env POSTGRES_PASSWORD="$DATABASE_PASSWORD" \
    "$POSTGRES_IMAGE" >"$TEMP_DIR/createdb.log.raw" 2>&1; then
    redact_file "$TEMP_DIR/createdb.log.raw" "$EVIDENCE_DIR/logs/database-create.log"
    die 69 'Could not start the isolated PostgreSQL container'
  fi
  DATABASE_CONTAINER_STARTED=1
  database_ready=0
  for _ in $(seq 1 60); do
    if docker exec "$DATABASE_CONTAINER" \
      pg_isready -U "$DATABASE_USER" -d "$DATABASE_NAME" >/dev/null 2>&1; then
      database_ready=1
      break
    fi
    sleep 1
  done
  if [[ "$database_ready" != "1" ]]; then
    docker logs "$DATABASE_CONTAINER" >"$TEMP_DIR/createdb.log.raw" 2>&1 || true
    redact_file "$TEMP_DIR/createdb.log.raw" "$EVIDENCE_DIR/logs/database-create.log"
    die 69 'Isolated PostgreSQL container did not become ready'
  fi
  DATABASE_PORT="$(docker port "$DATABASE_CONTAINER" 5432/tcp | sed -E 's/^.*:([0-9]+)$/\1/' | tail -n 1)"
  if [[ ! "$DATABASE_PORT" =~ ^[0-9]+$ ]]; then
    die 69 'Could not resolve the isolated PostgreSQL host port'
  fi
  export PRODUCT_DATABASE_URL="postgresql+asyncpg://$DATABASE_USER:$DATABASE_PASSWORD@127.0.0.1:$DATABASE_PORT/$DATABASE_NAME"
  export DATABASE_URL="postgresql://$DATABASE_USER:$DATABASE_PASSWORD@127.0.0.1:$DATABASE_PORT/$DATABASE_NAME?sslmode=disable"
else
  if ! createdb "$DATABASE_NAME" >"$TEMP_DIR/createdb.log.raw" 2>&1; then
    redact_file "$TEMP_DIR/createdb.log.raw" "$EVIDENCE_DIR/logs/database-create.log"
    die 69 'Could not create the isolated local PostgreSQL database'
  fi
  export PRODUCT_DATABASE_URL="postgresql+asyncpg:///$DATABASE_NAME"
  export DATABASE_URL="postgresql:///$DATABASE_NAME?host=/var/run/postgresql&port=${PGPORT:-5432}"
fi
DATABASE_CREATED=1
export AEGRA_CONFIG="$BACKEND_DIR/aegra.json"
if [[ "$ENABLE_REDIS_BROKER" == "1" ]]; then
  REDIS_CONTAINER="crypto-alert-real-deep-research-redis-$$_${RANDOM}"
  if ! docker run --detach --name "$REDIS_CONTAINER" \
    --publish 127.0.0.1::6379 \
    "$REDIS_IMAGE" >"$TEMP_DIR/redis-create.log.raw" 2>&1; then
    redact_file "$TEMP_DIR/redis-create.log.raw" "$EVIDENCE_DIR/logs/redis-create.log"
    die 69 'Could not start the isolated Redis broker container'
  fi
  REDIS_CONTAINER_STARTED=1
  redis_ready=0
  for _ in $(seq 1 60); do
    if [[ "$(docker exec "$REDIS_CONTAINER" redis-cli ping 2>/dev/null)" == "PONG" ]]; then
      redis_ready=1
      break
    fi
    sleep 1
  done
  if [[ "$redis_ready" != "1" ]]; then
    docker logs "$REDIS_CONTAINER" >"$TEMP_DIR/redis-create.log.raw" 2>&1 || true
    redact_file "$TEMP_DIR/redis-create.log.raw" "$EVIDENCE_DIR/logs/redis-create.log"
    die 69 'Isolated Redis broker did not become ready'
  fi
  REDIS_PORT="$(docker port "$REDIS_CONTAINER" 6379/tcp | sed -E 's/^.*:([0-9]+)$/\1/' | tail -n 1)"
  if [[ ! "$REDIS_PORT" =~ ^[0-9]+$ ]]; then
    die 69 'Could not resolve the isolated Redis broker host port'
  fi
  export REDIS_BROKER_ENABLED=true
  export REDIS_URL="redis://127.0.0.1:$REDIS_PORT/0"
  export WORKER_COUNT=1
  export N_JOBS_PER_WORKER=2
  export LEASE_DURATION_SECONDS=30
  export HEARTBEAT_INTERVAL_SECONDS=10
  export REAPER_INTERVAL_SECONDS=15
  export STUCK_PENDING_THRESHOLD_SECONDS=120
  jq -n \
    --arg schema_version "1.0" \
    --arg image "$REDIS_IMAGE" \
    --arg container "$REDIS_CONTAINER" \
    --argjson host_port "$REDIS_PORT" \
    '{schema_version:$schema_version,enabled:true,mode:"owned-isolated-container",image:$image,container:$container,host_port:$host_port,ping:"PONG"}' \
    >"$EVIDENCE_DIR/redis-broker-receipt.json"
else
  export REDIS_BROKER_ENABLED=false
  unset REDIS_URL
  jq -n \
    --arg schema_version "1.0" \
    '{schema_version:$schema_version,enabled:false,mode:"local-executor"}' \
    >"$EVIDENCE_DIR/redis-broker-receipt.json"
fi
export AGENT_SERVER_URL="http://127.0.0.1:$AGENT_PORT"
export PRODUCT_API_BASE_URL="$AGENT_SERVER_URL/app"
export WORKER_HEALTH_HOST="127.0.0.1"
export WORKER_HEALTH_PORT="$WORKER_PORT"
export PLAYWRIGHT_FRONTEND_BASE_URL="http://127.0.0.1:$FRONTEND_PORT"
export PLAYWRIGHT_EVIDENCE_DIR="$EVIDENCE_DIR"
export PLAYWRIGHT_EXTERNAL_SERVER=1
export PLAYWRIGHT_BROWSER_CHANNEL=chromium
export REAL_PRODUCT_E2E=1
export V2_E2E_PROFILE=real-deep-research
export REAL_DEEP_RESEARCH_E2E=1
export REAL_DEEP_RESEARCH_AEGRA_RESTART=1
export NEXT_TELEMETRY_DISABLED=1
export AGENT_SERVER_LOCAL_TOKEN="$(openssl rand -hex 32)"
export NOTIFICATION_CREDENTIAL_KEY="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=\n')"
export NOTIFICATION_CREDENTIAL_KEY_VERSION="real-deep-research-$(date -u +%Y%m%d%H%M%S)-$$"
export NEXTAUTH_SECRET="$(openssl rand -hex 32)"

set +e
(
  cd "$BACKEND_DIR"
  uv run --frozen alembic upgrade head
) >"$TEMP_DIR/migration.log.raw" 2>&1
migration_status=$?
set -e
redact_file "$TEMP_DIR/migration.log.raw" "$EVIDENCE_DIR/logs/migration.log"
if ((migration_status != 0)); then
  die 70 "Alembic migration to head failed with status $migration_status"
fi
MIGRATION_READY=1
run_psql -X -qAt -v ON_ERROR_STOP=1 -d "$DATABASE_NAME" <<'SQL' >"$EVIDENCE_DIR/migration-head.json"
SELECT jsonb_pretty(jsonb_build_object(
  'schema_version', '1.0',
  'migration_target', 'head',
  'revisions', COALESCE(jsonb_agg(version_num ORDER BY version_num), '[]'::jsonb),
  'captured_at', to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
)) FROM app.alembic_version;
SQL

agent_command=(
  env "UV_PROJECT_ENVIRONMENT=$TEMP_DIR/aegra-venv"
  uv run --frozen --no-dev --extra aegra
  python -m uvicorn
  aegra_api.main:app
  --host 127.0.0.1
  --port "$AGENT_PORT"
)
case "${OSTYPE:-}" in
  msys*|cygwin*|win32*)
    windows_serve_path="$AEGRA_WINDOWS_SERVE"
    if command -v cygpath >/dev/null 2>&1; then
      windows_serve_path="$(cygpath -w "$windows_serve_path")"
    fi
    agent_command=(
      env "UV_PROJECT_ENVIRONMENT=$TEMP_DIR/aegra-venv"
      uv run --frozen --no-dev --extra aegra
      python "$windows_serve_path"
      --host 127.0.0.1
      --port "$AGENT_PORT"
    )
    ;;
esac
if [[ -n "${REAL_DEEP_RESEARCH_PROXYCHAINS_CONFIG:-}" ]]; then
  if [[ "${REAL_DEEP_RESEARCH_PROXYCHAINS_CONFIG}" != /* || \
        ! -f "${REAL_DEEP_RESEARCH_PROXYCHAINS_CONFIG}" ]]; then
    die 66 'REAL_DEEP_RESEARCH_PROXYCHAINS_CONFIG must name an existing absolute file'
  fi
  if ! command -v proxychains4 >/dev/null 2>&1; then
    die 66 'proxychains4 is required when REAL_DEEP_RESEARCH_PROXYCHAINS_CONFIG is set'
  fi
  agent_command=(
    proxychains4 -f "$REAL_DEEP_RESEARCH_PROXYCHAINS_CONFIG" -q
    "${agent_command[@]}"
  )
fi
start_owned_process "$ROOT_DIR" "$TEMP_DIR/agent.log.raw" \
  "$PYTHON_RUNNER" "$AEGRA_RESTART_SUPERVISOR" \
    --working-directory "$BACKEND_DIR" \
    --evidence-dir "$EVIDENCE_NATIVE_DIR" \
    --health-url "$AGENT_SERVER_URL/health" \
    --startup-timeout "$REAL_DEEP_RESEARCH_STARTUP_TIMEOUT_SECONDS" \
    --project fixture-desktop \
    --project fixture-pixel-7 \
    -- "${agent_command[@]}"
AGENT_PID="$STARTED_PROCESS_PID"
if ! wait_for_http "$AGENT_SERVER_URL/health" \
  "$REAL_DEEP_RESEARCH_STARTUP_TIMEOUT_SECONDS" "$AGENT_PID"; then
  die 69 'Aegra Agent Protocol server did not become ready'
fi

workspace_ready=0
for attempt in $(seq 1 "$REAL_DEEP_RESEARCH_WORKSPACE_TIMEOUT_SECONDS"); do
  workspace_count="$(run_psql -X -qAt -v ON_ERROR_STOP=1 -d "$DATABASE_NAME" \
    -v tenant_external_id="$DEVELOPMENT_BOOTSTRAP_TENANT_ID" \
    -v workspace_external_id="$DEVELOPMENT_BOOTSTRAP_WORKSPACE_ID" \
    <<'WORKSPACE_READY_SQL'
SELECT count(*)
FROM app.workspaces AS workspace
JOIN app.tenants AS tenant ON tenant.id = workspace.tenant_id
WHERE tenant.external_id = :'tenant_external_id'
  AND workspace.external_id = :'workspace_external_id';
WORKSPACE_READY_SQL
  )"
  if [[ "$workspace_count" == "1" ]]; then
    workspace_ready=1
    break
  fi
  sleep 1
done
if [[ "$workspace_ready" != "1" ]]; then
  die 70 'Development bootstrap did not create exactly one isolated test workspace'
fi
write_review_policy_receipt "$EVIDENCE_DIR/review-policy-before.json"
if ! jq -e '.workspace.id and (.workspace.review_policy == "bypass" or .workspace.review_policy == "required")' \
  "$EVIDENCE_DIR/review-policy-before.json" >/dev/null; then
  die 70 'Could not record the original test workspace review policy'
fi
WORKSPACE_UUID="$(jq -r '.workspace.id' "$EVIDENCE_DIR/review-policy-before.json")"
ORIGINAL_REVIEW_POLICY="$(jq -r '.workspace.review_policy' "$EVIDENCE_DIR/review-policy-before.json")"
if ! set_review_policy_required; then
  die 70 'Could not set required review policy on exactly the test workspace'
fi

start_owned_process "$BACKEND_DIR" "$TEMP_DIR/worker.log.raw" \
  uv run --frozen python -m crypto_alert_v2.workers \
    --worker-id "real-deep-research-e2e-$$" \
    --poll-interval 0.5
WORKER_PID="$STARTED_PROCESS_PID"
if ! wait_for_http "http://127.0.0.1:$WORKER_PORT/readyz" \
  "$REAL_DEEP_RESEARCH_STARTUP_TIMEOUT_SECONDS" "$WORKER_PID"; then
  die 69 'Unified Worker did not become ready'
fi

set +e
(
  cd "$FRONTEND_DIR"
  npm run build
) >"$TEMP_DIR/build.log.raw" 2>&1
build_status=$?
set -e
redact_file "$TEMP_DIR/build.log.raw" "$EVIDENCE_DIR/logs/build.log"
if ((build_status != 0)); then
  die 70 "Production Next build failed with status $build_status"
fi

start_owned_process "$FRONTEND_DIR" "$TEMP_DIR/frontend.log.raw" \
  npm run start -- --hostname 127.0.0.1 --port "$FRONTEND_PORT"
FRONTEND_PID="$STARTED_PROCESS_PID"
if ! wait_for_http "$PLAYWRIGHT_FRONTEND_BASE_URL/work" \
  "$REAL_DEEP_RESEARCH_STARTUP_TIMEOUT_SECONDS" "$FRONTEND_PID"; then
  die 69 'Production Next server did not become ready'
fi

start_owned_process "$FRONTEND_DIR" "$TEMP_DIR/playwright.log.raw" \
  node node_modules/@playwright/test/cli.js test \
    tests/e2e-product/real-deep-research-flow.spec.ts \
    --project=fixture-desktop \
    --project=fixture-pixel-7
E2E_PID="$STARTED_PROCESS_PID"
set +e
wait "$E2E_PID"
e2e_status=$?
set -e
E2E_PID=""
if ((e2e_status != 0)); then
  FAILURE_REASON="Real Deep Research Playwright profile failed with status $e2e_status"
fi

stop_all_owned_processes
capture_all_logs
ensure_reporter_artifacts

set +e
validate_aegra_restart_receipts
restart_validation_status=$?
collect_database_evidence
database_collection_status=$?
validate_junit_contract "$([[ "$e2e_status" == "0" ]] && printf 1 || printf 0)"
junit_validation_status=$?
database_validation_status=0
if ((e2e_status == 0 && database_collection_status == 0)); then
  validate_database_evidence
  database_validation_status=$?
fi
set -e

if ((junit_validation_status != 0)); then
  die 70 'Playwright JUnit rejected a skip or a missing Desktop/Pixel testcase'
fi
if ((database_collection_status != 0)); then
  die 70 'Secret-safe database evidence collection failed'
fi
if ((e2e_status != 0)); then
  die 70 "Real Deep Research Playwright profile failed with status $e2e_status"
fi
if ((restart_validation_status != 0)); then
  die 70 'Aegra restart receipt validation failed'
fi
if ((database_validation_status != 0)); then
  die 70 'Successful Deep Research database lineage receipt is invalid'
fi

PROOF_RESULT="passed"
FAILURE_REASON=""
printf 'Real Deep Research E2E passed; evidence retained at %s\n' "$EVIDENCE_DIR"
