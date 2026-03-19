#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE_HOST="${REMOTE_HOST:-glasslab@192.168.1.44}"
REMOTE_REPO="${REMOTE_REPO:-/home/glasslab/cluster-config}"
REMOTE_OUTPUT_DIR="${REMOTE_OUTPUT_DIR:-/home/glasslab/glasslab-secret-backups}"
LOCAL_OUTPUT_DIR="${LOCAL_OUTPUT_DIR:-$HOME/glasslab-secret-backups}"
STAMP="${STAMP:-$(date +%Y%m%d-%H%M%S)}"
PASSFILE=""
SOURCE_ROOT=""

usage() {
  cat <<'EOF'
Usage: pull-glasslab-secrets-backup.sh [--remote-host USER@HOST] [--remote-repo DIR] [--remote-output-dir DIR] [--local-output-dir DIR] [--source-root DIR] [--passphrase-file FILE] [--stamp STAMP]

Runs the encrypted secret backup helper on `.44` and then pulls the encrypted archive
and manifest back to this laptop.

Defaults:
  --remote-host        glasslab@192.168.1.44
  --remote-repo        /home/glasslab/cluster-config
  --remote-output-dir  /home/glasslab/glasslab-secret-backups
  --local-output-dir   $HOME/glasslab-secret-backups

Notes:
  - SSH to `.44` must work from the current machine.
  - The remote helper still prompts for a GPG symmetric passphrase unless
    --passphrase-file points to an intentional remote passphrase file.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --remote-host)
      REMOTE_HOST="$2"
      shift 2
      ;;
    --remote-repo)
      REMOTE_REPO="$2"
      shift 2
      ;;
    --remote-output-dir)
      REMOTE_OUTPUT_DIR="$2"
      shift 2
      ;;
    --local-output-dir)
      LOCAL_OUTPUT_DIR="$2"
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
    --stamp)
      STAMP="$2"
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

mkdir -p "$LOCAL_OUTPUT_DIR"
chmod 700 "$LOCAL_OUTPUT_DIR"

REMOTE_CMD="cd '$REMOTE_REPO' && ./scripts/backup-glasslab-secrets.sh --output-dir '$REMOTE_OUTPUT_DIR' --stamp '$STAMP'"
if [[ -n "$SOURCE_ROOT" ]]; then
  REMOTE_CMD+=" --source-root '$SOURCE_ROOT'"
fi
if [[ -n "$PASSFILE" ]]; then
  REMOTE_CMD+=" --passphrase-file '$PASSFILE'"
fi

ssh -tt "$REMOTE_HOST" "$REMOTE_CMD"

ARCHIVE_BASENAME="glasslab-secrets-${STAMP}.tar"
scp \
  "${REMOTE_HOST}:${REMOTE_OUTPUT_DIR}/${ARCHIVE_BASENAME}.gpg" \
  "${REMOTE_HOST}:${REMOTE_OUTPUT_DIR}/${ARCHIVE_BASENAME%.tar}.manifest.txt" \
  "$LOCAL_OUTPUT_DIR/"

printf 'Pulled encrypted backup artifacts into %s\n' "$LOCAL_OUTPUT_DIR"
