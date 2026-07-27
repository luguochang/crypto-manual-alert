#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AEGRA_PROBE="$ROOT_DIR/tools/v2/probe_aegra_durability.sh"
EVIDENCE_DIR=""

usage() {
  printf 'Usage: %s --evidence-dir PATH\n' "$0"
}

while (($# > 0)); do
  case "$1" in
    --evidence-dir)
      (($# >= 2)) || {
        printf '%s\n' '--evidence-dir requires a path' >&2
        exit 64
      }
      EVIDENCE_DIR=$2
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      usage >&2
      printf 'Unknown Task 8 probe option: %s\n' "$1" >&2
      exit 64
      ;;
  esac
done

[[ -n "$EVIDENCE_DIR" ]] || {
  usage >&2
  printf '%s\n' 'Task 8 requires an explicit --evidence-dir' >&2
  exit 64
}
[[ -x "$AEGRA_PROBE" ]] || {
  printf 'Aegra durability probe is unavailable: %s\n' "$AEGRA_PROBE" >&2
  exit 66
}

"$AEGRA_PROBE" --evidence-dir "$EVIDENCE_DIR"

printf '%s\n' \
  'Task 8 local Aegra durability slice passed. This does not claim hosted OIDC/HTTPS, real-provider Product mainline, or release readiness.'
