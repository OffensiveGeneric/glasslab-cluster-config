#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="default"

usage() {
  cat <<'USAGE'
Usage: check-before-push.sh [--default] [--docs] [--configs] [--python-core]

Run the fast local checks that mirror the default Glasslab CI signal.

Modes:
  --default      Run configs, docs, shell syntax, Python syntax, workflow-api core tests.
  --docs         Check Markdown links only.
  --configs      Validate current YAML and JSON only.
  --python-core  Run service Python syntax and workflow-api core tests only.

Default mode is --default.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --default)
      MODE="default"
      shift
      ;;
    --docs)
      MODE="docs"
      shift
      ;;
    --configs)
      MODE="configs"
      shift
      ;;
    --python-core)
      MODE="python-core"
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      printf '[check-before-push] unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

cd "$ROOT_DIR"

run_configs() {
  printf '[check-before-push] validating YAML/JSON\n'
  python3 scripts/validate-configs.py
}

run_docs() {
  printf '[check-before-push] checking Markdown links\n'
  python3 scripts/check-doc-links.py
}

run_shell() {
  printf '[check-before-push] checking shell syntax\n'
  bash -n \
    scripts/check-before-push.sh \
    scripts/glasslab-opencode.sh \
    scripts/research-session-cli.sh \
    scripts/submit-learning-task.sh \
    scripts/submit-sample-experiment.sh
}

run_python_syntax() {
  printf '[check-before-push] checking Python syntax\n'
  python3 <<'PY'
from pathlib import Path

failures = []
for path in Path('services').rglob('*.py'):
    try:
        compile(path.read_text(), str(path), 'exec')
    except Exception as exc:
        failures.append((str(path), str(exc)))

if failures:
    for path, exc in failures:
        print(f'{path}: {exc}')
    raise SystemExit(1)

print('All Python files compiled successfully.')
PY
}

run_workflow_api_tests() {
  printf '[check-before-push] running workflow-api core tests\n'
  (
    cd services/workflow-api
    PYTHONPATH=../..:. pytest \
      -p no:cacheprovider \
      tests/test_api.py \
      tests/test_persistence.py \
      tests/test_run_artifacts.py \
      tests/test_schedule_execution.py \
      tests/test_validation.py \
      -q
  )
  (
    cd services/research-workspace-runner
    PYTHONPATH=. pytest \
      -p no:cacheprovider \
      tests/test_runner.py \
      -q
  )
}

case "$MODE" in
  default)
    run_configs
    run_docs
    run_shell
    run_python_syntax
    run_workflow_api_tests
    ;;
  docs)
    run_docs
    ;;
  configs)
    run_configs
    ;;
  python-core)
    run_shell
    run_python_syntax
    run_workflow_api_tests
    ;;
esac

printf '[check-before-push] ok\n'
