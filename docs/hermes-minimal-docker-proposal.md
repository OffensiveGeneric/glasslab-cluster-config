# Hermes Minimal Headless Docker — Proposal

*Audited 2026-08-11. Read-only review; no live cluster data. Source: PyPI hermes-agent 0.19.0, Hermes architecture docs, current orchestrator Dockerfile.*

## Current State

`services/research-orchestrator/Dockerfile` installs OpenCode via npm (`opencode-ai@1.18.14`). Hermes is not yet installed. The official Hermes installer (`curl https://hermes-agent.nousresearch.com/install.sh | bash`) creates a ~3.22 GB layer because it runs `uv pip install hermes-agent[all]`, pulling in browser (Playwright), TUI (prompt_toolkit/rich), audio (TTS/voice), vision, messaging platform adapters, and cron dependencies.

## Target

Headless gateway API plus local file and terminal tools. Disabled: browser, web, vision, messaging, TTS, skills, cron, delegation. OpenCode retained as rollback runtime.

## Proposed Dockerfile (add to existing)

```dockerfile
FROM python:3.11-slim

# --- OpenCode (rollback runtime, unchanged from current) ---
ARG OPENCODE_VERSION=1.18.14
RUN apt-get update \
    && apt-get install -y --no-install-recommends git nodejs npm ca-certificates \
    && npm install --global "opencode-ai@${OPENCODE_VERSION}" \
    && rm -rf /var/lib/apt/lists/*

# --- Hermes (minimal headless) ---
# Pin exact version by hash to prevent supply-chain drift.
# Latest PyPI release: 0.19.0 (tag v2026.7.20, commit 3ef6bbd)
# Source: https://pypi.org/project/hermes-agent/0.19.0/
ARG HERMES_VERSION=0.19.0
ARG HERMES_SHA256=bd0bac012aee38a60894781f4597dc29ee7bedb3448540249921f10d3bef327f

# Base package includes: agent loop (run_agent.py), gateway (run.py),
# api_server.py, file_tools, terminal_tool, session storage, provider
# resolution. No extras needed — this avoids browser (Playwright), TUI
# (prompt_toolkit/rich), audio (TTS/voice), messaging platform adapters,
# cron, delegation, and vision dependencies.
RUN pip install --no-cache-dir \
    --require-hashes \
    "hermes-agent==${HERMES_VERSION}" \
    --hash "sha256:${HERMES_SHA256}"

# --- Validation ---
# Verify Hermes CLI is available and lists gateway subcommands.
# The 'gateway' subcommand confirms gateway/run.py imported successfully.
# '--help' exits 0 if the package installed correctly with no missing deps.
RUN hermes --version \
    && hermes gateway --help \
    && python3 -c "from run_agent import AIAgent; print('agent OK')" \
    && python3 -c "from gateway.run import GatewayRunner; print('gateway OK')" \
    && python3 -c "from gateway.platforms.api_server import ApiServerPlatform; print('api OK')" \
    && python3 -c "from tools.file_tools import read_file; print('file tools OK')" \
    && python3 -c "from tools.terminal_tool import TerminalTool; print('terminal OK')"

# --- Application layer (unchanged) ---
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

ARG GLASSLAB_GIT_SHA=unknown
ARG GLASSLAB_BUILD_SOURCE=unspecified
LABEL org.opencontainers.image.revision="${GLASSLAB_GIT_SHA}"
LABEL org.opencontainers.image.source="https://github.com/OffensiveGeneric/glasslab-cluster-config"
LABEL io.glasslab.build-source="${GLASSLAB_BUILD_SOURCE}"

COPY app ./app
COPY prompts ./prompts
COPY evaluation-contracts ./evaluation-contracts

RUN useradd --uid 10001 --create-home orchestrator \
    && mkdir -p /var/lib/glasslab-research-orchestrator \
    && mkdir -p /home/orchestrator/.hermes \
    && chown -R orchestrator:orchestrator /var/lib/glasslab-research-orchestrator \
    && chown -R orchestrator:orchestrator /home/orchestrator/.hermes

USER 10001:10001
EXPOSE 8080 4210 4211
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

## What Gets Excluded

| Category | Extras Needed | Pulls In | Size Avoided (est.) |
|----------|--------------|----------|---------------------|
| Browser / web | `[web]` | Playwright, Chromium, Firefox deps | ~1.2 GB |
| TUI / CLI UI | `[cli]` | prompt_toolkit, rich, textual | ~200 MB |
| Audio / voice | `[voice]`, `[tts-premium]` | PyAudio, portaudio, ffmpeg | ~300 MB |
| Vision | `[vision]` | Pillow, opencv deps | ~150 MB |
| Messaging platforms | `[messaging]` | 25+ adapter libs | ~500 MB |
| Cron / skills / delegation | `[cron]` | apscheduler, skill deps | ~50 MB |
| **Total saved** | | | **~2.4 GB** |

## Expected Image Size

`python:3.11-slim` (~150 MB) + pip base Hermes (~40 MB wheel + 14 dependencies) + OpenCode npm (~80 MB) + app code (~10 MB) ≈ **~280-350 MB**.

Compare to the ~3.5 GB full install.

## How the Orchestrator Uses Hermes

The orchestrator currently spawns OpenCode subprocesses via `opencode_runtime.py`. The Hermes equivalent would call `hermes serve` or `hermes gateway run` with a config that enables only the API server platform, then communicate via the `/v1/runs` HTTP API. Relevant endpoints:

```
POST /v1/runs              → start run, returns run_id (202)
GET  /v1/runs/{id}         → run status
GET  /v1/runs/{id}/events  → SSE stream of lifecycle events
POST /v1/runs/{id}/stop    → interrupt
POST /v1/runs/{id}/approval→ resolve pending approval
```

The API requires `X-Hermes-Session-Id` header for session affinity. Provider configuration (model, API key, base URL) is set via `~/.hermes/config.yaml` and/or `~/.hermes/.env` before starting the gateway.

## Uncertain Assumptions

1. **Version naming**: The user specified `v2026.8.3` but PyPI's latest is `0.19.0` (tagged `v2026.7.20`). The proposal uses `0.19.0`. If `v2026.8.3` is a future release, substitute the actual version and wheel hash when available. The release scheme uses date-based git tags (`v2026.M.D`) mapped to semver PyPI releases.

2. **Gateway vs serve**: `hermes serve` starts the headless backend. `hermes gateway run` starts the full gateway including API server. Which entry point is minimal for API-server-only mode needs verification against the actual installed package. The architecture docs list the API server as a built-in platform adapter at `gateway/platforms/api_server.py` — it should be available in the base package without extras.

3. **Terminal PTY support**: The `terminal_tool` may require the `[pty]` extra for PTY-based shell access. If `hermes gateway run` fails with import errors related to PTY, add `[pty]` to the pip install (likely adds only `ptyprocess`, ~50 KB).

4. **Config file requirement**: Hermes may require a minimal `~/.hermes/config.yaml` with `gateway.platforms: [api_server]` to disable messaging adapter startup. The Dockerfile creates the `.hermes` directory but does not write a config — if the gateway refuses to start without one, a minimal config must be added.

5. **API server mode**: The `/v1/runs` endpoint may only be available through the full gateway process (`hermes gateway run`), not through `hermes serve`. The `hermes serve` docs say it "powers the desktop app and remote backends" which suggests it exposes the API server. If not, the orchestrator can import `run_agent.AIAgent` directly in-process (no subprocess needed), which is documented as the "Python in-process embed" pattern.

## Validation Commands (expected output)

```bash
# In built image:
hermes --version                                    # → 0.19.0 (YYYY.M.D) [3ef6bbd]
hermes gateway --help                               # → subcommand list
python3 -c "from run_agent import AIAgent"          # → (silent success)
python3 -c "from gateway.run import GatewayRunner"  # → (silent success)
python3 -c "from gateway.platforms.api_server import ApiServerPlatform"  # → (silent)
python3 -c "from tools.file_tools import read_file"          # → (silent)
python3 -c "from tools.terminal_tool import TerminalTool"    # → (silent)

# If gateway starts (may need config):
HERMES_HOME=/home/orchestrator/.hermes hermes gateway run &
sleep 5
curl http://localhost:8765/health                    # → {"status":"ok"}
kill %1
```

## References

- PyPI: `https://pypi.org/project/hermes-agent/0.19.0/` — wheel hash, version, extras list
- Architecture: `https://hermes-agent.nousresearch.com/docs/developer-guide/architecture` — directory structure, entry points
- Programmatic integration: `https://hermes-agent.nousresearch.com/docs/developer-guide/programmatic-integration` — API server endpoints, protocols
- Current Dockerfile: `services/research-orchestrator/Dockerfile`
- Hermes repository: `https://github.com/NousResearch/hermes-agent`
