#!/usr/bin/env bash
# Generates, replicates, and verifies audit chain anchors off the database host.
# Usage:
#   scripts/replicate_audit_anchor.sh generate [OUT_FILE]
#   scripts/replicate_audit_anchor.sh replicate [SRC_FILE] [DEST_DIR_OR_REMOTE]
#   scripts/replicate_audit_anchor.sh check [ANCHOR_FILE]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ANCHOR_DIR="${REPO_ROOT}/var/anchors"
mkdir -p "$ANCHOR_DIR"

DATE_STAMP="$(date +%Y%m%d_%H%M%S)"
DEFAULT_OUT="${ANCHOR_DIR}/audit_anchor_${DATE_STAMP}.jsonl"

case "${1:-}" in
generate)
  out="${2:-$DEFAULT_OUT}"
  echo "Generating audit anchor to $out..."
  (cd "${REPO_ROOT}/backend" && uv run python manage.py audit_anchor) > "$out"
  sha256sum "$out" > "${out}.sha256"
  echo "Anchor generated ($(wc -l < "$out") lines, $(stat -c %s "$out") bytes)."
  ;;

replicate)
  src="${2:-}"
  dest="${3:-${AUDIT_ANCHOR_DESTINATION:-}}"
  if [ -z "$src" ] || [ -z "$dest" ]; then
    echo "Usage: $0 replicate SRC_FILE DEST_DIR_OR_REMOTE (or set AUDIT_ANCHOR_DESTINATION)" >&2
    exit 2
  fi
  if [ ! -f "$src" ]; then
    echo "Source anchor file $src does not exist" >&2
    exit 1
  fi
  echo "Replicating $src and ${src}.sha256 to $dest..."
  cp -p "$src" "${dest}/"
  [ -f "${src}.sha256" ] && cp -p "${src}.sha256" "${dest}/"
  echo "Replication completed successfully."
  ;;

check)
  target_raw="${2:?Usage: $0 check ANCHOR_FILE}"
  if [ ! -f "$target_raw" ]; then
    echo "Anchor file $target_raw does not exist" >&2
    exit 1
  fi
  target="$(realpath "$target_raw")"
  if [ -f "${target}.sha256" ]; then
    echo "Verifying SHA-256 checksum..."
    (cd "$(dirname "$target")" && sha256sum -c "$(basename "${target}.sha256")")
  fi
  echo "Verifying chain against database state..."
  (cd "${REPO_ROOT}/backend" && uv run python manage.py audit_anchor --check "$target")
  echo "Audit anchor check: OK (all chain hashes match)."
  ;;

*)
  echo "Usage: $0 generate|replicate|check [ARGS...]" >&2
  exit 2
  ;;
esac
