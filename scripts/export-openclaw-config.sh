#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$ROOT_DIR/services/openclaw-config"
KUBECTL="${KUBECTL:-kubectl}"
NAMESPACE="${GLASSLAB_V2_NAMESPACE:-glasslab-v2}"
CONFIGMAP_NAME="${GLASSLAB_OPENCLAW_CONFIGMAP_NAME:-glasslab-openclaw-config}"
TMP_ARCHIVE=""

cleanup() {
  if [[ -n "$TMP_ARCHIVE" && -f "$TMP_ARCHIVE" ]]; then
    rm -f "$TMP_ARCHIVE"
  fi
}
trap cleanup EXIT

command -v "$KUBECTL" >/dev/null 2>&1 || {
  printf '[export-openclaw-config] missing command: %s\n' "$KUBECTL" >&2
  exit 1
}
command -v tar >/dev/null 2>&1 || {
  printf '[export-openclaw-config] missing command: tar\n' >&2
  exit 1
}

[[ -d "$SOURCE_DIR" ]] || {
  printf '[export-openclaw-config] source directory not found: %s\n' "$SOURCE_DIR" >&2
  exit 1
}

TMP_ARCHIVE="$(mktemp)"
tar -C "$SOURCE_DIR" -czf "$TMP_ARCHIVE" .

"$KUBECTL" -n "$NAMESPACE" create configmap "$CONFIGMAP_NAME" \
  --from-file=openclaw-config.tar.gz="$TMP_ARCHIVE" \
  --dry-run=client -o yaml | "$KUBECTL" apply -f -

printf '[export-openclaw-config] exported %s to configmap/%s in namespace %s\n' "$SOURCE_DIR" "$CONFIGMAP_NAME" "$NAMESPACE"
