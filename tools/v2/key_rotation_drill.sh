#!/usr/bin/env bash
set -euo pipefail

umask 077

export APP_ENVIRONMENT=test
export CRYPTO_ALERT_DISABLE_DOTENV=1

readonly SCRIPT_DIR="$(cd -- "${BASH_SOURCE[0]%/*}" && pwd -P)"
readonly REPOSITORY_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
readonly BACKEND_ROOT="$REPOSITORY_ROOT/backend"
readonly POSTGRES_IMAGE="postgres:16-alpine@sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777"

output_root=""
profile="local-rehearsal"
work_dir=""
container_name=""
rotation_pid=""
rotation_launcher_pid=""
rotation_pid_kind="posix"
summary_tmp=""
current_stage="initialization"
last_probe_report=""
failure_evidence_enabled=false

force_kill_rotation() {
  local process_id="$1"
  local kill_status=0
  if [[ "$rotation_pid_kind" == "windows" ]]; then
    MSYS_NO_PATHCONV=1 taskkill.exe /PID "$process_id" /T /F >/dev/null 2>&1 \
      || kill_status=$?
    if [[ -n "$rotation_launcher_pid" ]]; then
      MSYS_NO_PATHCONV=1 taskkill.exe /PID "$rotation_launcher_pid" /F \
        >/dev/null 2>&1 || true
    fi
    return "$kill_status"
  else
    kill -KILL "$process_id"
  fi
}

rotation_is_running() {
  local process_id="$1"
  if [[ "$rotation_pid_kind" == "windows" ]]; then
    ROTATION_CHECK_PID="$process_id" \
      powershell.exe -NoProfile -NonInteractive -Command '
        if (Get-Process -Id ([int]$env:ROTATION_CHECK_PID) -ErrorAction SilentlyContinue) {
          exit 0
        }
        exit 1
      ' >/dev/null 2>&1
  else
    kill -0 "$process_id" >/dev/null 2>&1
  fi
}

fail() {
  printf 'key rotation drill failed: %s\n' "$1" >&2
  exit "${2:-1}"
}

cleanup() {
  local exit_status="$?"
  local probe_status="unknown" probe_stage="unknown" probe_error_type="unknown"
  local failure_path failure_tmp
  if [[ "$exit_status" != "0" && -n "$last_probe_report" && -s "$last_probe_report" ]]; then
    probe_status="$(jq -r '.status // "unknown"' "$last_probe_report" 2>/dev/null || true)"
    probe_stage="$(jq -r '.probe_stage // "unknown"' "$last_probe_report" 2>/dev/null || true)"
    probe_error_type="$(jq -r '.error_type // "unknown"' "$last_probe_report" 2>/dev/null || true)"
  fi
  if [[ "$exit_status" != "0" && "$failure_evidence_enabled" == "true" && -n "$output_root" && -d "$output_root" ]]; then
    failure_path="$output_root/key-rotation-failure.json"
    failure_tmp="$output_root/.key-rotation-failure.$$"
    jq -n \
      --arg stage "$current_stage" \
      --arg probe_status "$probe_status" \
      --arg probe_stage "$probe_stage" \
      --arg probe_error_type "$probe_error_type" \
      --argjson exit_code "$exit_status" \
      '{schema_version:"2026-07-22.key-rotation-failure.v1",status:"failed",stage:$stage,exit_code:$exit_code,probe:{status:$probe_status,stage:$probe_stage,error_type:$probe_error_type}}' \
      >"$failure_tmp" 2>/dev/null || true
    if [[ -s "$failure_tmp" ]]; then
      chmod 600 "$failure_tmp" >/dev/null 2>&1 || true
      mv -f "$failure_tmp" "$failure_path" >/dev/null 2>&1 || true
      printf 'key rotation drill failed at stage: %s (%s/%s)\n' \
        "$current_stage" "$probe_stage" "$probe_error_type" >&2
    fi
  fi
  if [[ -n "$rotation_pid" ]] && rotation_is_running "$rotation_pid"; then
    force_kill_rotation "$rotation_pid" >/dev/null 2>&1 || true
    if [[ "$rotation_pid_kind" != "windows" ]]; then
      wait "$rotation_pid" >/dev/null 2>&1 || true
    fi
  fi
  if [[ -n "$container_name" ]]; then
    docker rm --force "$container_name" >/dev/null 2>&1 || true
  fi
  if [[ -n "$work_dir" ]]; then
    for ((cleanup_attempt = 1; cleanup_attempt <= 50; cleanup_attempt += 1)); do
      rm -rf "$work_dir" >/dev/null 2>&1 && break
      sleep 0.1
    done
    if [[ -d "$work_dir" ]]; then
      printf 'key rotation drill cleanup failed: temporary work directory remains\n' >&2
      return 1
    fi
  fi
  if [[ -n "$summary_tmp" ]]; then
    rm -f "$summary_tmp"
  fi
  return "$exit_status"
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
  fail "hosted key rotation acceptance is not implemented" 78
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
if (( ${#output_entries[@]} != 0 )); then
  fail "--output-root must be empty" 64
fi

for command_name in docker jq openssl chmod date git mktemp rm sleep tr grep mv; do
  command -v "$command_name" >/dev/null 2>&1 \
    || fail "required command is unavailable: $command_name"
done
case "${OSTYPE:-}" in
  msys*|cygwin*|win32*)
    for command_name in cygpath powershell.exe taskkill.exe; do
      command -v "$command_name" >/dev/null 2>&1 \
        || fail "required command is unavailable: $command_name"
    done
    ;;
esac
if [[ -x "$BACKEND_ROOT/.venv/bin/python" ]]; then
  readonly BACKEND_PYTHON="$BACKEND_ROOT/.venv/bin/python"
elif [[ -x "$BACKEND_ROOT/.venv/Scripts/python.exe" ]]; then
  readonly BACKEND_PYTHON="$BACKEND_ROOT/.venv/Scripts/python.exe"
else
  fail "required backend executable is unavailable: python"
fi
if [[ -x "$BACKEND_ROOT/.venv/bin/alembic" ]]; then
  readonly BACKEND_ALEMBIC="$BACKEND_ROOT/.venv/bin/alembic"
elif [[ -x "$BACKEND_ROOT/.venv/Scripts/alembic.exe" ]]; then
  readonly BACKEND_ALEMBIC="$BACKEND_ROOT/.venv/Scripts/alembic.exe"
else
  fail "required backend executable is unavailable: alembic"
fi

work_dir="$(mktemp -d "${TMPDIR:-/tmp}/crypto-alert-v2-key-rotation.XXXXXX")"
chmod 700 "$work_dir"
failure_evidence_enabled=true
container_name="crypto-alert-v2-key-rotation-$$-${RANDOM}"

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

run_psql() {
  docker exec "$container_name" \
    psql --username postgres --dbname postgres \
      --no-psqlrc --set=ON_ERROR_STOP=1 --tuples-only --no-align "$@"
}

(
  cd "$BACKEND_ROOT"
  PRODUCT_DATABASE_URL="$database_url" "$BACKEND_ALEMBIC" -c alembic.ini upgrade head
) >/dev/null

old_notification_key="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=')"
new_notification_key="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=')"
notification_canary="$(openssl rand -hex 24)"
decrypt_keyring="$(
  ROTATION_OLD_KEY="$old_notification_key" \
    "$BACKEND_PYTHON" - <<'PY'
import json
import os

print(json.dumps({"rotation-v1": os.environ["ROTATION_OLD_KEY"]}, separators=(",", ":")))
PY
)"
readonly old_notification_key new_notification_key notification_canary decrypt_keyring

PRODUCT_DATABASE_URL="$database_url" \
NOTIFICATION_CREDENTIAL_KEY="$old_notification_key" \
NOTIFICATION_CREDENTIAL_KEY_VERSION="rotation-v1" \
ROTATION_CANARY="$notification_canary" \
ROTATION_SNAPSHOT="$work_dir/original-ciphertext.json" \
"$BACKEND_PYTHON" - <<'PY'
import asyncio
from base64 import b64encode
import json
import os
from pathlib import Path
from uuid import uuid4

from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from crypto_alert_v2.notifications.credentials import notification_credential_cipher_from_environment
from crypto_alert_v2.persistence.models import NotificationDestination, Tenant, User, Workspace


async def main() -> None:
    engine = create_async_engine(os.environ["PRODUCT_DATABASE_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    cipher = notification_credential_cipher_from_environment()
    assert cipher is not None
    snapshot = None
    async with sessions() as session, session.begin():
        for index in range(4):
            tenant_id = uuid4()
            workspace_id = uuid4()
            user_id = uuid4()
            destination_id = uuid4()
            session.add(Tenant(id=tenant_id, external_id=f"rotation-tenant-{index}", name=f"Rotation tenant {index}"))
            session.add(User(id=user_id, tenant_id=tenant_id, identity_issuer="rotation-drill", external_subject=f"rotation-user-{index}"))
            session.add(Workspace(id=workspace_id, tenant_id=tenant_id, external_id=f"rotation-workspace-{index}", name=f"Rotation workspace {index}", review_policy="bypass"))
            await session.flush()
            ciphertext = cipher.encrypt(
                SecretStr(os.environ["ROTATION_CANARY"]),
                destination_id=destination_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_user_id=user_id,
                channel="bark",
            )
            session.add(NotificationDestination(
                id=destination_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_user_id=user_id,
                channel="bark",
                status="enabled",
                credential_ciphertext=ciphertext,
                credential_key_version=cipher.key_version,
            ))
            if snapshot is None:
                snapshot = {
                    "ciphertext": b64encode(ciphertext).decode("ascii"),
                    "destination_id": str(destination_id),
                    "tenant_id": str(tenant_id),
                    "workspace_id": str(workspace_id),
                    "owner_user_id": str(user_id),
                    "channel": "bark",
                    "key_version": cipher.key_version,
                }
    assert snapshot is not None
    path = Path(os.environ["ROTATION_SNAPSHOT"])
    path.write_text(json.dumps(snapshot, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)
    await engine.dispose()


asyncio.run(main())
PY

run_capture_delivery() {
  local active_key="$1"
  local active_version="$2"
  local decrypt_keys="$3"
  local probe_report="$work_dir/delivery-probe-${active_version}.json"
  local process_status=0 probe_status probe_stage probe_error_type
  rm -f "$probe_report"
  last_probe_report="$probe_report"
  if PRODUCT_DATABASE_URL="$database_url" \
  NOTIFICATION_CREDENTIAL_KEY="$active_key" \
  NOTIFICATION_CREDENTIAL_KEY_VERSION="$active_version" \
  NOTIFICATION_CREDENTIAL_DECRYPT_KEYS="$decrypt_keys" \
  ROTATION_CANARY="$notification_canary" \
  ROTATION_DELIVERY_REPORT="$probe_report" \
  "$BACKEND_PYTHON" - <<'PY'
import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from crypto_alert_v2.notifications.adapters import DeliveryRequest
from crypto_alert_v2.notifications.credentials import notification_credential_cipher_from_environment
from crypto_alert_v2.notifications.resolver import DatabaseNotificationAdapterResolver
from crypto_alert_v2.persistence.models import NotificationDestination

probe_stage = "initialization"
report_path = Path(os.environ["ROTATION_DELIVERY_REPORT"])


def write_report(payload: dict[str, object]) -> None:
    report_path.write_text(
        json.dumps(payload, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

async def main() -> None:
    global probe_stage
    probe_stage = "cipher_init"
    deliveries = 0

    async def capture(request: httpx.Request) -> httpx.Response:
        nonlocal deliveries
        payload = json.loads(request.content)
        assert payload["device_key"] == os.environ["ROTATION_CANARY"]
        deliveries += 1
        return httpx.Response(200, json={"code": 200, "timestamp": 1784300000})

    engine = create_async_engine(os.environ["PRODUCT_DATABASE_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    cipher = notification_credential_cipher_from_environment()
    assert cipher is not None
    async with httpx.AsyncClient(transport=httpx.MockTransport(capture)) as client:
        probe_stage = "load_destinations"
        resolver = DatabaseNotificationAdapterResolver(
            session_factory=sessions,
            credential_cipher=cipher,
            http_client=client,
        )
        async with sessions() as session:
            destinations = list((await session.scalars(select(NotificationDestination).order_by(NotificationDestination.id))).all())
        for destination in destinations:
            probe_stage = "resolve_adapter"
            request = DeliveryRequest(
                notification_id=uuid4(), task_id=uuid4(), run_id=uuid4(),
                artifact_id=uuid4(), decision_id=uuid4(), channel="bark",
                notification_type="rotation_probe", decision_version=1,
                payload={"title": "rotation", "body": "probe"}, payload_hash="rotation-probe",
                tenant_id=destination.tenant_id, workspace_id=destination.workspace_id,
                owner_user_id=destination.owner_user_id, destination_id=destination.id,
            )
            adapter = await resolver.resolve(request)
            assert adapter is not None
            probe_stage = "send"
            result = await adapter.send(request)
            assert result.outcome == "delivered"
    probe_stage = "delivery_count"
    assert deliveries == 4
    await engine.dispose()
    write_report({"status": "passed"})


try:
    asyncio.run(main())
except Exception as exc:
    write_report(
        {
            "status": "failed",
            "probe_stage": probe_stage,
            "error_type": type(exc).__name__,
        }
    )
    raise SystemExit(1) from None
PY
  then
    process_status=0
  else
    process_status=$?
  fi
  for ((probe_attempt = 1; probe_attempt <= 100; probe_attempt += 1)); do
    [[ -s "$probe_report" ]] && break
    sleep 0.05
  done
  [[ -s "$probe_report" ]] \
    || fail "delivery probe produced no bounded report ($process_status)"
  probe_status="$(jq -r '.status // empty' "$probe_report")"
  if [[ "$probe_status" != "passed" ]]; then
    probe_stage="$(jq -r '.probe_stage // "unknown"' "$probe_report")"
    probe_error_type="$(jq -r '.error_type // "unknown"' "$probe_report")"
    fail "delivery probe failed: $probe_stage/$probe_error_type"
  fi
  return 0
}

current_stage="delivery_before_rotation"
run_capture_delivery "$old_notification_key" "rotation-v1" "" \
  || fail "delivery probe wrapper failed before rotation"
delivery_before_rotation="delivered"
current_stage="delivery_during_overlap"
run_capture_delivery "$new_notification_key" "rotation-v2" "$decrypt_keyring" \
  || fail "delivery probe wrapper failed during overlap"
delivery_during_overlap="delivered"

rotation_interrupted=false
current_stage="start_interrupted_rotation"
case "${OSTYPE:-}" in
  msys*|cygwin*|win32*)
    rotation_pid_kind="windows"
    rotation_pid_file="$work_dir/rotation.pid"
    rotation_launch_report="$work_dir/rotation-launch.json"
    ROTATION_BACKEND_PYTHON="$(cygpath -w "$BACKEND_PYTHON")" \
    ROTATION_BACKEND_ROOT="$(cygpath -w "$BACKEND_ROOT")" \
    ROTATION_OUTPUT="$(cygpath -w "$work_dir/interrupted-report.json")" \
    ROTATION_STDOUT="$(cygpath -w "$work_dir/interrupted.stdout")" \
    ROTATION_STDERR="$(cygpath -w "$work_dir/interrupted.stderr")" \
    ROTATION_PID_FILE="$(cygpath -w "$rotation_pid_file")" \
    ROTATION_LAUNCH_REPORT="$(cygpath -w "$rotation_launch_report")" \
    PRODUCT_DATABASE_URL="$database_url" \
    NOTIFICATION_CREDENTIAL_KEY="$new_notification_key" \
    NOTIFICATION_CREDENTIAL_KEY_VERSION="rotation-v2" \
    NOTIFICATION_CREDENTIAL_DECRYPT_KEYS="$decrypt_keyring" \
      powershell.exe -NoProfile -NonInteractive -Command '
        try {
          $arguments = @(
          "-m", "crypto_alert_v2.notifications.rotate_credentials",
          "--batch-size", "1",
          "--inter-batch-delay-seconds", "10",
          "--output", $env:ROTATION_OUTPUT
        )
          $process = Start-Process `
          -FilePath $env:ROTATION_BACKEND_PYTHON `
          -ArgumentList $arguments `
          -WorkingDirectory $env:ROTATION_BACKEND_ROOT `
          -RedirectStandardOutput $env:ROTATION_STDOUT `
          -RedirectStandardError $env:ROTATION_STDERR `
          -WindowStyle Hidden `
          -PassThru
          $deadline = [DateTime]::UtcNow.AddSeconds(10)
          $child = $null
          while ($null -eq $child -and [DateTime]::UtcNow -lt $deadline) {
            $child = Get-CimInstance Win32_Process |
              Where-Object {
                $_.ParentProcessId -eq $process.Id -and
                $_.ExecutablePath -like "*python.exe"
              } |
              Select-Object -First 1
            if ($null -eq $child) { Start-Sleep -Milliseconds 50 }
          }
          if ($null -eq $child) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
            throw [InvalidOperationException]::new("child process unavailable")
          }
          [IO.File]::WriteAllText(
            $env:ROTATION_PID_FILE,
            "$($process.Id)|$($child.ProcessId)" + [char]10
          )
          [IO.File]::WriteAllText(
            $env:ROTATION_LAUNCH_REPORT,
            (@{status="passed"} | ConvertTo-Json -Compress)
          )
        } catch {
          [IO.File]::WriteAllText(
            $env:ROTATION_LAUNCH_REPORT,
            (@{status="failed";error_type=$_.Exception.GetType().Name} | ConvertTo-Json -Compress)
          )
          exit 1
        }
      ' >/dev/null || {
        rotation_launch_status=$?
        rotation_launch_error_type="$(
          jq -r '.error_type // "unknown"' "$rotation_launch_report" 2>/dev/null || true
        )"
        [[ -n "$rotation_launch_error_type" ]] || rotation_launch_error_type="unknown"
        fail "Windows rotation launcher failed: $rotation_launch_error_type ($rotation_launch_status)"
      }
    IFS='|' read -r rotation_launcher_pid rotation_pid <"$rotation_pid_file"
    [[ "$rotation_launcher_pid" =~ ^[0-9]+$ && "$rotation_pid" =~ ^[0-9]+$ ]] \
      || fail "Windows rotation process IDs are invalid"
    ;;
  *)
    rotation_pid_kind="posix"
    (
      cd "$BACKEND_ROOT"
      PRODUCT_DATABASE_URL="$database_url" \
      NOTIFICATION_CREDENTIAL_KEY="$new_notification_key" \
      NOTIFICATION_CREDENTIAL_KEY_VERSION="rotation-v2" \
      NOTIFICATION_CREDENTIAL_DECRYPT_KEYS="$decrypt_keyring" \
      "$BACKEND_PYTHON" -m crypto_alert_v2.notifications.rotate_credentials \
        --batch-size 1 \
        --inter-batch-delay-seconds 10 \
        --output "$work_dir/interrupted-report.json"
    ) >"$work_dir/interrupted.stdout" 2>"$work_dir/interrupted.stderr" &
    rotation_pid=$!
    ;;
esac

current_stage="observe_partial_commit"
partial_commit=0
for ((attempt = 1; attempt <= 200; attempt += 1)); do
  IFS='|' read -r new_rows old_rows <<<"$(
    run_psql --command "
      SELECT
        count(*) FILTER (WHERE credential_key_version = 'rotation-v2'),
        count(*) FILTER (WHERE credential_key_version = 'rotation-v1')
      FROM app.notification_destinations;
    "
  )"
  if (( new_rows >= 1 && old_rows >= 1 )); then
    partial_commit=1
    break
  fi
  if ! rotation_is_running "$rotation_pid"; then
    rotation_status=0
    if [[ "$rotation_pid_kind" == "windows" ]]; then
      rotation_status=1
    else
      wait "$rotation_pid" || rotation_status=$?
    fi
    rotation_pid=""
    rotation_error_type="$(
      jq -r 'select(.status == "failed") | .error_type // empty' \
        "$work_dir/interrupted.stderr" 2>/dev/null || true
    )"
    [[ -n "$rotation_error_type" ]] || rotation_error_type="unknown"
    fail "rotation process exited before resumable boundary: $rotation_error_type ($rotation_status)"
  fi
  sleep 0.05
done
[[ "$partial_commit" == "1" ]] || fail "rotation did not expose a committed resumable boundary"
current_stage="force_interrupt"
force_kill_rotation "$rotation_pid" \
  || fail "rotation process could not be force-terminated"
if [[ "$rotation_pid_kind" == "windows" ]]; then
  for ((attempt = 1; attempt <= 40; attempt += 1)); do
    rotation_is_running "$rotation_pid" || break
    sleep 0.05
  done
  rotation_is_running "$rotation_pid" \
    && fail "force-terminated rotation process is still running"
else
  if wait "$rotation_pid" >/dev/null 2>&1; then
    fail "interrupted rotation exited successfully before SIGKILL"
  fi
fi
rotation_pid=""
rotation_launcher_pid=""
rotation_interrupted=true

current_stage="post_interrupt_delivery"
run_capture_delivery "$new_notification_key" "rotation-v2" "$decrypt_keyring" \
  || fail "delivery probe wrapper failed after interruption"

current_stage="resume_rotation"
(
  cd "$BACKEND_ROOT"
  PRODUCT_DATABASE_URL="$database_url" \
  NOTIFICATION_CREDENTIAL_KEY="$new_notification_key" \
  NOTIFICATION_CREDENTIAL_KEY_VERSION="rotation-v2" \
  NOTIFICATION_CREDENTIAL_DECRYPT_KEYS="$decrypt_keyring" \
  "$BACKEND_PYTHON" -m crypto_alert_v2.notifications.rotate_credentials \
    --batch-size 1 \
    --output "$work_dir/completed-report.json"
) >"$work_dir/completed.stdout" 2>"$work_dir/completed.stderr"

current_stage="resume_validation"
rows_rewrapped="$((4 - old_rows))"
completed_rewrapped="$(jq -r '.rewrapped_rows' "$work_dir/completed-report.json")"
rows_rewrapped="$((rows_rewrapped + completed_rewrapped))"
old_rows_remaining="$(run_psql --command "SELECT count(*) FROM app.notification_destinations WHERE credential_key_version != 'rotation-v2';")"
[[ "$old_rows_remaining" == "0" ]] || fail "old notification key versions remain after resume"
[[ "$rows_rewrapped" == "4" ]] || fail "rewrapped row count does not match seeded destinations"

current_stage="delivery_after_retirement"
run_capture_delivery "$new_notification_key" "rotation-v2" "" \
  || fail "delivery probe wrapper failed after retirement"
delivery_after_retirement="delivered"

current_stage="retired_ciphertext_rejection"
PRODUCT_DATABASE_URL="$database_url" \
NOTIFICATION_CREDENTIAL_KEY="$new_notification_key" \
NOTIFICATION_CREDENTIAL_KEY_VERSION="rotation-v2" \
ROTATION_SNAPSHOT="$work_dir/original-ciphertext.json" \
"$BACKEND_PYTHON" - <<'PY'
from base64 import b64decode
import json
import os
from pathlib import Path
from uuid import UUID

from crypto_alert_v2.notifications.credentials import NotificationCredentialError, notification_credential_cipher_from_environment

snapshot = json.loads(Path(os.environ["ROTATION_SNAPSHOT"]).read_text(encoding="utf-8"))
cipher = notification_credential_cipher_from_environment()
assert cipher is not None
try:
    cipher.decrypt(
        b64decode(snapshot["ciphertext"]),
        destination_id=UUID(snapshot["destination_id"]),
        tenant_id=UUID(snapshot["tenant_id"]),
        workspace_id=UUID(snapshot["workspace_id"]),
        owner_user_id=UUID(snapshot["owner_user_id"]),
        channel=snapshot["channel"],
        key_version=snapshot["key_version"],
    )
except NotificationCredentialError:
    pass
else:
    raise SystemExit("retired notification key unexpectedly decrypted old ciphertext")
PY

current_stage="jwt_rotation"
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$work_dir/jwt-v1-private.pem" 2>/dev/null
openssl pkey -in "$work_dir/jwt-v1-private.pem" -pubout -out "$work_dir/jwt-v1-public.pem" 2>/dev/null
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$work_dir/jwt-v2-private.pem" 2>/dev/null
openssl pkey -in "$work_dir/jwt-v2-private.pem" -pubout -out "$work_dir/jwt-v2-public.pem" 2>/dev/null
chmod 600 "$work_dir"/jwt-*.pem

JWT_WORK_DIR="$work_dir" "$BACKEND_PYTHON" - <<'PY'
import json
import os
from pathlib import Path

from crypto_alert_v2.auth.internal_token import InternalTokenIssuer, InternalTokenVerifier

root = Path(os.environ["JWT_WORK_DIR"])
old_private = (root / "jwt-v1-private.pem").read_text(encoding="utf-8")
old_public = (root / "jwt-v1-public.pem").read_text(encoding="utf-8")
new_private = (root / "jwt-v2-private.pem").read_text(encoding="utf-8")
new_public = (root / "jwt-v2-public.pem").read_text(encoding="utf-8")
issuer_name = "crypto-alert-v2-key-rotation"
audience = "crypto-alert-agent-server"

def issuer(private_key: str, kid: str) -> InternalTokenIssuer:
    return InternalTokenIssuer(private_key=private_key, key_id=kid, issuer=issuer_name, audience=audience, ttl_seconds=60)

def token(token_issuer: InternalTokenIssuer) -> str:
    return token_issuer.issue(subject="rotation-worker", tenant_id="rotation-tenant", workspace_id="rotation-workspace", roles=("worker",), permissions=("analysis:write",))

old_token = token(issuer(old_private, "jwt-v1"))
new_token = token(issuer(new_private, "jwt-v2"))
overlap = InternalTokenVerifier(public_keys={"jwt-v1": old_public, "jwt-v2": new_public}, issuer=issuer_name, audience=audience, max_ttl_seconds=60)
old_overlap = overlap.verify(old_token)["sub"] == "rotation-worker"
new_overlap = overlap.verify(new_token)["sub"] == "rotation-worker"
retired = InternalTokenVerifier(public_keys={"jwt-v2": new_public}, issuer=issuer_name, audience=audience, max_ttl_seconds=60)
try:
    retired.verify(old_token)
except PermissionError:
    old_rejected = True
else:
    old_rejected = False
new_retired = retired.verify(new_token)["sub"] == "rotation-worker"
(root / "jwt-result.json").write_text(json.dumps({
    "overlap_old_token_accepted": old_overlap,
    "overlap_new_token_accepted": new_overlap,
    "retired_old_token_rejected": old_rejected,
    "retired_new_token_accepted": new_retired,
}, sort_keys=True), encoding="utf-8")
PY

current_stage="summary_publish"
jwt_result="$(<"$work_dir/jwt-result.json")"
git_head="$(git -C "$REPOSITORY_ROOT" rev-parse HEAD)"
generated_at="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
summary_path="$output_root/key-rotation-summary.json"

summary_tmp="$(mktemp "$output_root/.key-rotation-summary.XXXXXX")"
chmod 600 "$summary_tmp"
jq -n \
  --arg generated_at "$generated_at" \
  --arg git_head "$git_head" \
  --arg delivery_before "$delivery_before_rotation" \
  --arg delivery_overlap "$delivery_during_overlap" \
  --arg delivery_after "$delivery_after_retirement" \
  --argjson rows_rewrapped "$rows_rewrapped" \
  --argjson old_remaining "$old_rows_remaining" \
  --argjson interrupted "$rotation_interrupted" \
  --argjson jwt "$jwt_result" \
  '{
    schema_version: "2026-07-17.key-rotation-rehearsal.v1",
    status: "passed",
    proof_level: "local-key-rotation-rehearsal",
    generated_at: $generated_at,
    source: {git_head: $git_head, git_dirty: true},
    notification: {
      total_rows: 4,
      rows_rewrapped: $rows_rewrapped,
      old_version_rows_remaining: $old_remaining,
      delivery_before_rotation: $delivery_before,
      delivery_during_overlap: $delivery_overlap,
      delivery_after_retirement: $delivery_after,
      duplicate_deliveries: 0
    },
    jwt: $jwt,
    process_recovery: {
      interrupted_once: $interrupted,
      resumed_successfully: true
    },
    secret_scan: {findings: 0},
    does_not_prove: [
      "hosted_secret_manager_rotation",
      "database_password_rotation",
      "oidc_client_secret_rotation",
      "provider_api_key_rotation",
      "production_zero_downtime_rollout",
      "release_attestation"
    ]
  }' >"$summary_tmp"
chmod 600 "$summary_tmp"
if grep -F -e "$old_notification_key" -e "$new_notification_key" -e "$notification_canary" "$summary_tmp" >/dev/null 2>&1; then
  fail "secret material appeared in the published report"
fi
mv -f "$summary_tmp" "$summary_path"
summary_tmp=""
jq -e '
  .status == "passed" and
  .proof_level == "local-key-rotation-rehearsal" and
  .notification.total_rows == 4 and
  .notification.rows_rewrapped == .notification.total_rows and
  .notification.old_version_rows_remaining == 0 and
  .notification.delivery_before_rotation == "delivered" and
  .notification.delivery_during_overlap == "delivered" and
  .notification.delivery_after_retirement == "delivered" and
  .notification.duplicate_deliveries == 0 and
  .jwt.overlap_old_token_accepted == true and
  .jwt.overlap_new_token_accepted == true and
  .jwt.retired_old_token_rejected == true and
  .jwt.retired_new_token_accepted == true and
  .process_recovery.interrupted_once == true and
  .process_recovery.resumed_successfully == true and
  .secret_scan.findings == 0
' "$summary_path" >/dev/null

printf '%s\n' "$(<"$summary_path")"
