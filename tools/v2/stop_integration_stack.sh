#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
COMPOSE_PROJECT_NAME="crypto-manual-alert-v2"
volume_flag=""

if [[ $# -gt 1 ]]; then
  printf 'Usage: %s [--volumes]\n' "$0" >&2
  exit 64
fi

case "${1:-}" in
  "")
    ;;
  --volumes)
    volume_flag="--volumes"
    ;;
  *)
    printf 'Usage: %s [--volumes]\n' "$0" >&2
    exit 64
    ;;
esac

exec docker compose \
  --project-name "$COMPOSE_PROJECT_NAME" \
  --project-directory "$ROOT_DIR" \
  --file "$ROOT_DIR/docker-compose.yml" \
  down \
  --remove-orphans \
  ${volume_flag:+"$volume_flag"}
