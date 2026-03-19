#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_ROOT="${SOURCE_ROOT:-$ROOT}"
OUTPUT_DIR="${OUTPUT_DIR:-$HOME/glasslab-secret-backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
WORKDIR="$(mktemp -d)"
ARCHIVE_BASENAME="glasslab-secrets-${STAMP}.tar"
ARCHIVE_PATH=""
ENCRYPTED_PATH=""
MANIFEST_PATH=""

usage() {
  cat <<'EOF'
Usage: backup-glasslab-secrets.sh [--output-dir DIR] [--source-root DIR] [--passphrase-file FILE] [--copy-dest DEST]

Creates an encrypted tar archive containing the ignored local secret manifests used by
the Glasslab v1 and v2 stacks.

Defaults:
  --source-root   repo root detected from this script
  --output-dir    $HOME/glasslab-secret-backups

Encryption:
  By default, gpg prompts interactively for a symmetric passphrase.
  Use --passphrase-file only if you are intentionally supplying the passphrase from a file.

Off-host copy:
  Use --copy-dest with either:
    - a local directory path
    - an scp-style destination such as user@host:/path/
EOF
}

PASSFILE=""
COPY_DEST=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --source-root)
      SOURCE_ROOT="$2"
      shift 2
      ;;
    --passphrase-file)
      PASSFILE="$2"
      shift 2
      ;;
    --copy-dest)
      COPY_DEST="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

ARCHIVE_PATH="$WORKDIR/$ARCHIVE_BASENAME"
ENCRYPTED_PATH="$OUTPUT_DIR/${ARCHIVE_BASENAME}.gpg"
MANIFEST_PATH="$OUTPUT_DIR/${ARCHIVE_BASENAME%.tar}.manifest.txt"

cleanup() {
  rm -rf "$WORKDIR"
}
trap cleanup EXIT

mkdir -p "$WORKDIR/payload" "$OUTPUT_DIR"
chmod 700 "$OUTPUT_DIR"

FILES=(
  "kubeadm/glasslab-v2/secrets/10-postgres.local.yaml"
  "kubeadm/glasslab-v2/secrets/20-minio.local.yaml"
  "kubeadm/glasslab-v2/secrets/30-openclaw.local.yaml"
  "kubeadm/agent-stack/12-agent-secrets.yaml"
)

FOUND=0
for rel in "${FILES[@]}"; do
  src="$SOURCE_ROOT/$rel"
  if [[ -f "$src" ]]; then
    install -D -m 600 "$src" "$WORKDIR/payload/$rel"
    FOUND=1
  fi
done

if [[ "$FOUND" -eq 0 ]]; then
  printf 'No known local secret manifests were found under %s\n' "$SOURCE_ROOT" >&2
  exit 1
fi

(
  cd "$WORKDIR/payload"
  tar -cf "$ARCHIVE_PATH" .
)

if [[ -n "$PASSFILE" ]]; then
  gpg --batch --yes --pinentry-mode loopback \
    --passphrase-file "$PASSFILE" \
    --symmetric --cipher-algo AES256 \
    --output "$ENCRYPTED_PATH" \
    "$ARCHIVE_PATH"
else
  gpg --symmetric --cipher-algo AES256 \
    --output "$ENCRYPTED_PATH" \
    "$ARCHIVE_PATH"
fi

chmod 600 "$ENCRYPTED_PATH"

{
  printf 'created_at=%s\n' "$(date --iso-8601=seconds)"
  printf 'source_root=%s\n' "$SOURCE_ROOT"
  printf 'encrypted_archive=%s\n' "$ENCRYPTED_PATH"
  printf 'included_files:\n'
  (
    cd "$WORKDIR/payload"
    find . -type f | sort
  )
} >"$MANIFEST_PATH"

chmod 600 "$MANIFEST_PATH"

if [[ -n "$COPY_DEST" ]]; then
  if [[ "$COPY_DEST" == *:* ]]; then
    scp "$ENCRYPTED_PATH" "$MANIFEST_PATH" "$COPY_DEST"
  else
    mkdir -p "$COPY_DEST"
    chmod 700 "$COPY_DEST"
    cp "$ENCRYPTED_PATH" "$MANIFEST_PATH" "$COPY_DEST/"
  fi
fi

printf 'Encrypted backup written to %s\n' "$ENCRYPTED_PATH"
printf 'Manifest written to %s\n' "$MANIFEST_PATH"
if [[ -n "$COPY_DEST" ]]; then
  printf 'Copied encrypted backup artifacts to %s\n' "$COPY_DEST"
fi
