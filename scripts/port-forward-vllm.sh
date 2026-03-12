#!/usr/bin/env bash
set -euo pipefail
exec kubectl -n glasslab-agents port-forward svc/vllm 8000:8000
