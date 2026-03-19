#!/usr/bin/env bash
set -euo pipefail

KAGGLE_VENV="${GLASSLAB_KAGGLE_VENV:-$HOME/.local/share/glasslab/kaggle-cli}"
STAGING_ROOT="${GLASSLAB_TITANIC_STAGING_ROOT:-$HOME/.cache/glasslab-titanic-sync}"
KAGGLE_COMPETITION="${KAGGLE_COMPETITION:-titanic}"
NODE_HOST="${GLASSLAB_DATASET_NODE_HOST:-192.168.1.50}"
NODE_USER="${GLASSLAB_DATASET_NODE_USER:-clusteradmin}"
NODE_SSH_KEY="${GLASSLAB_DATASET_NODE_SSH_KEY:-/home/glasslab/.ssh/id_ed25519}"
REMOTE_DATASET_DIR="${GLASSLAB_TITANIC_REMOTE_DIR:-/var/lib/glasslab-agent/datasets/titanic}"
KEEP_STAGING=false
USE_PASSWORDLESS_SUDO=false
RUN_DIR=""
KAGGLE_BIN=""

usage() {
  cat <<'EOF'
Usage: sync-titanic-dataset.sh [--keep-staging] [--node-host <host>] [--remote-dir <path>]

Download the official Kaggle Titanic competition files on the provisioner and
sync them onto the live dataset path on node03.

Environment:
  KAGGLE_USERNAME / KAGGLE_KEY     Optional alternative to ~/.kaggle/kaggle.json
  NODE_SUDO_PASSWORD               Optional sudo password for clusteradmin on the node
  GLASSLAB_KAGGLE_VENV             Override the user-local Kaggle CLI venv path
  GLASSLAB_TITANIC_STAGING_ROOT    Override the local staging root on the provisioner
  GLASSLAB_DATASET_NODE_HOST       Override the node host or IP
  GLASSLAB_DATASET_NODE_USER       Override the node SSH user
  GLASSLAB_DATASET_NODE_SSH_KEY    Override the provisioner-to-node SSH key path
  GLASSLAB_TITANIC_REMOTE_DIR      Override the live Titanic dataset directory
EOF
}

log() {
  printf '[sync-titanic-dataset] %s
' "$*" >&2
}

fail() {
  printf '[sync-titanic-dataset] ERROR: %s
' "$*" >&2
  exit 1
}

cleanup() {
  if [[ "$KEEP_STAGING" != true && -n "$RUN_DIR" && -d "$RUN_DIR" ]]; then
    rm -rf "$RUN_DIR"
  fi
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

ensure_kaggle_credentials() {
  if [[ -f "$HOME/.kaggle/kaggle.json" ]]; then
    chmod 700 "$HOME/.kaggle"
    chmod 600 "$HOME/.kaggle/kaggle.json"
    return
  fi

  if [[ -n "${KAGGLE_USERNAME:-}" && -n "${KAGGLE_KEY:-}" ]]; then
    return
  fi

  fail "official Kaggle credentials are required on .44 via ~/.kaggle/kaggle.json or KAGGLE_USERNAME and KAGGLE_KEY"
}

ensure_kaggle_cli() {
  if command -v kaggle >/dev/null 2>&1; then
    KAGGLE_BIN="$(command -v kaggle)"
    return
  fi

  KAGGLE_BIN="$KAGGLE_VENV/bin/kaggle"
  if [[ -x "$KAGGLE_BIN" ]]; then
    return
  fi

  log "bootstrapping Kaggle CLI into $KAGGLE_VENV"
  mkdir -p "$(dirname "$KAGGLE_VENV")"
  python3 -m venv "$KAGGLE_VENV"
  "$KAGGLE_VENV/bin/python" -m pip install --upgrade pip setuptools wheel kaggle
}

validate_csv() {
  local file="$1"
  local required_column="$2"
  local header
  local rows

  [[ -s "$file" ]] || fail "missing expected file: $file"
  header="$(head -n 1 "$file" | tr -d '')"
  [[ ",$header," == *",$required_column,"* ]] || fail "$(basename "$file") is missing required column: $required_column"
  rows=$(( $(wc -l < "$file") - 1 ))
  (( rows > 100 )) || fail "$(basename "$file") looks too small: $rows data rows"
  log "validated $(basename "$file"): $rows data rows"
}

prompt_node_password() {
  if [[ -n "${NODE_SUDO_PASSWORD:-}" ]]; then
    return
  fi

  read -r -s -p "sudo password for ${NODE_USER}@${NODE_HOST}: " NODE_SUDO_PASSWORD
  printf '
' >&2
  [[ -n "$NODE_SUDO_PASSWORD" ]] || fail "node sudo password is required"
}

detect_node_sudo_mode() {
  if ssh -i "$NODE_SSH_KEY" -o StrictHostKeyChecking=accept-new "${NODE_USER}@${NODE_HOST}" "sudo -n true" >/dev/null 2>&1; then
    USE_PASSWORDLESS_SUDO=true
    log "using passwordless sudo on ${NODE_HOST}"
    return
  fi

  prompt_node_password
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep-staging)
      KEEP_STAGING=true
      shift
      ;;
    --node-host)
      [[ $# -ge 2 ]] || fail "--node-host requires a value"
      NODE_HOST="$2"
      shift 2
      ;;
    --remote-dir)
      [[ $# -ge 2 ]] || fail "--remote-dir requires a value"
      REMOTE_DATASET_DIR="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
done

trap cleanup EXIT

need_cmd python3
need_cmd unzip
need_cmd ssh
need_cmd scp
need_cmd head
need_cmd wc
need_cmd date
need_cmd base64
need_cmd find

[[ -f "$NODE_SSH_KEY" ]] || fail "node SSH key not found: $NODE_SSH_KEY"

ensure_kaggle_credentials
ensure_kaggle_cli

RUN_ID="$(date +%Y%m%d-%H%M%S)"
RUN_DIR="$STAGING_ROOT/$RUN_ID"
DOWNLOAD_DIR="$RUN_DIR/download"
EXTRACT_DIR="$RUN_DIR/extracted"

mkdir -p "$DOWNLOAD_DIR" "$EXTRACT_DIR"

log "downloading Kaggle competition archive: $KAGGLE_COMPETITION"
"$KAGGLE_BIN" competitions download -c "$KAGGLE_COMPETITION" -p "$DOWNLOAD_DIR" >/dev/null

ZIP_FILE="$(find "$DOWNLOAD_DIR" -maxdepth 1 -type f -name '*.zip' | head -n 1)"
[[ -n "$ZIP_FILE" ]] || fail "Kaggle download did not produce a zip file"

log "extracting $(basename "$ZIP_FILE")"
unzip -oq "$ZIP_FILE" -d "$EXTRACT_DIR"

validate_csv "$EXTRACT_DIR/train.csv" "Survived"
validate_csv "$EXTRACT_DIR/test.csv" "PassengerId"

LOCAL_FILES=(
  "$EXTRACT_DIR/train.csv"
  "$EXTRACT_DIR/test.csv"
)

for optional_file in gender_submission.csv sample_submission.csv; do
  if [[ -f "$EXTRACT_DIR/$optional_file" ]]; then
    LOCAL_FILES+=("$EXTRACT_DIR/$optional_file")
  fi
done

REMOTE_STAGE="/tmp/glasslab-titanic-sync-$RUN_ID"

log "preparing remote staging directory on ${NODE_HOST}"
ssh -i "$NODE_SSH_KEY" -o StrictHostKeyChecking=accept-new "${NODE_USER}@${NODE_HOST}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE'"

log "copying $((${#LOCAL_FILES[@]})) files to ${NODE_HOST}:${REMOTE_STAGE}"
scp -i "$NODE_SSH_KEY" -o StrictHostKeyChecking=accept-new "${LOCAL_FILES[@]}" "${NODE_USER}@${NODE_HOST}:${REMOTE_STAGE}/"

detect_node_sudo_mode

log "installing dataset into ${REMOTE_DATASET_DIR}"
if [[ "$USE_PASSWORDLESS_SUDO" == true ]]; then
  ssh -i "$NODE_SSH_KEY" -o StrictHostKeyChecking=accept-new "${NODE_USER}@${NODE_HOST}" "REMOTE_STAGE='$REMOTE_STAGE' REMOTE_DATASET_DIR='$REMOTE_DATASET_DIR' bash -s" <<'REMOTE'
set -euo pipefail

sudo -n env REMOTE_STAGE="$REMOTE_STAGE" REMOTE_DATASET_DIR="$REMOTE_DATASET_DIR" bash -s <<'INNER'
set -euo pipefail

SYNC_TS="$(date +%Y%m%d-%H%M%S)"
BACKUP_ROOT="$(dirname "$REMOTE_DATASET_DIR")"
BACKUP_DIR="$BACKUP_ROOT/_sync_backup_$SYNC_TS"

install -d -m 0755 "$REMOTE_DATASET_DIR" "$BACKUP_DIR"

for file in train.csv test.csv gender_submission.csv sample_submission.csv; do
  if [[ -f "$REMOTE_DATASET_DIR/$file" ]]; then
    cp -a "$REMOTE_DATASET_DIR/$file" "$BACKUP_DIR/$file"
  fi
  if [[ -f "$REMOTE_STAGE/$file" ]]; then
    install -o root -g root -m 0644 "$REMOTE_STAGE/$file" "$REMOTE_DATASET_DIR/$file"
  fi
done

printf 'official_source=kaggle
competition=titanic
synced_at_utc=%s
' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$REMOTE_DATASET_DIR/.dataset-source"
chmod 0644 "$REMOTE_DATASET_DIR/.dataset-source"
rm -rf "$REMOTE_STAGE"

printf 'REMOTE_BACKUP_DIR=%s
' "$BACKUP_DIR"
wc -l "$REMOTE_DATASET_DIR/train.csv" "$REMOTE_DATASET_DIR/test.csv"
INNER
REMOTE
else
PASSWORD_B64="$(printf '%s' "$NODE_SUDO_PASSWORD" | base64 -w0)"
ssh -i "$NODE_SSH_KEY" -o StrictHostKeyChecking=accept-new "${NODE_USER}@${NODE_HOST}" "PASSWORD_B64='$PASSWORD_B64' REMOTE_STAGE='$REMOTE_STAGE' REMOTE_DATASET_DIR='$REMOTE_DATASET_DIR' bash -s" <<'REMOTE'
set -euo pipefail

PASSWORD="$(printf '%s' "$PASSWORD_B64" | base64 -d)"
printf '%s
' "$PASSWORD" | sudo -S env REMOTE_STAGE="$REMOTE_STAGE" REMOTE_DATASET_DIR="$REMOTE_DATASET_DIR" bash -s <<'INNER'
set -euo pipefail

SYNC_TS="$(date +%Y%m%d-%H%M%S)"
BACKUP_ROOT="$(dirname "$REMOTE_DATASET_DIR")"
BACKUP_DIR="$BACKUP_ROOT/_sync_backup_$SYNC_TS"

install -d -m 0755 "$REMOTE_DATASET_DIR" "$BACKUP_DIR"

for file in train.csv test.csv gender_submission.csv sample_submission.csv; do
  if [[ -f "$REMOTE_DATASET_DIR/$file" ]]; then
    cp -a "$REMOTE_DATASET_DIR/$file" "$BACKUP_DIR/$file"
  fi
  if [[ -f "$REMOTE_STAGE/$file" ]]; then
    install -o root -g root -m 0644 "$REMOTE_STAGE/$file" "$REMOTE_DATASET_DIR/$file"
  fi
done

printf 'official_source=kaggle
competition=titanic
synced_at_utc=%s
' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$REMOTE_DATASET_DIR/.dataset-source"
chmod 0644 "$REMOTE_DATASET_DIR/.dataset-source"
rm -rf "$REMOTE_STAGE"

printf 'REMOTE_BACKUP_DIR=%s
' "$BACKUP_DIR"
wc -l "$REMOTE_DATASET_DIR/train.csv" "$REMOTE_DATASET_DIR/test.csv"
INNER
REMOTE
fi

log "dataset sync complete"
