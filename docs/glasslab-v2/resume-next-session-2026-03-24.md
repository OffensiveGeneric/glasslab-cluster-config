# Resume Next Session: 2026-03-24

This is the shortest accurate handoff for where to resume next time.

## Current State

- OpenClaw is live on the cluster at `1` replica
- the current live backend is `.23` via Ollama
- `.23` `deepseek-r1:32b` works for plain chat
- `.23` `deepseek-r1:32b` does **not** support native tool calling
- `.12` `qwen3:14b` does return native Ollama `tool_calls`
- `.12` is also serving the bounded ranker on `:8181`
- `node02` still has the legacy `vllm` pod holding the cluster GPU

## In-Progress Pull

On `192.168.1.23`:

- `qwen3:30b` pull is in progress
- latest checked progress on 2026-03-24:
  - about `597 MB / 18 GB`
  - about `3%`
- a `launchd` watchdog is now installed on `.23`
  - label: `com.glasslab.ollama-qwen3-30b-watchdog`
  - script: `/Users/glasslab/.local/bin/ollama-pull-watchdog.sh`
  - plist: `/Users/glasslab/Library/LaunchAgents/com.glasslab.ollama-qwen3-30b-watchdog.plist`
  - behavior: checks every `120s` and restarts the pull if progress is flat for `180s`

Check with:

```bash
sshpass -p 'Glasslab@7311' ssh -o StrictHostKeyChecking=no -o PreferredAuthentications=password -o PubkeyAuthentication=no glasslab@192.168.1.23 \
  "/Applications/Ollama.app/Contents/Resources/ollama list; echo '---'; tail -n 40 /tmp/ollama-pull-qwen3-30b.log; echo '---'; tail -n 20 /tmp/ollama-pull-watchdog.log"
```

## Ready-To-Use Staged Config

The native-Ollama OpenClaw runtime for `.23` `qwen3:30b` has already been staged locally at:

- `/tmp/openclaw-runtime-qwen3-30b-staged`

It is configured for:

- provider API: `ollama`
- provider base URL: `http://192.168.1.23:11434`
- model: `qwen3:30b`

## First Thing To Do When Back

1. confirm `qwen3:30b` finished pulling on `.23`
2. verify native tool calling directly on `.23` with `POST /api/chat`
3. if native tools work:
   - apply the staged native-Ollama OpenClaw config
   - rerun `./scripts/check-openclaw-tool-calling.sh --attempts 5`
4. if native tools do not work:
   - keep `.23` for plain inference
   - use `.12` for native-Ollama tool experiments

Tracker:

- issue `#35`: validate native-Ollama OpenClaw path on `.23` `qwen3:30b`

## Parallel Product Work Ready Now

The next backend design step does **not** require waiting for the model pull:

- build the first in-cluster interpretation agent

Reference:

- `interpretation-agent-service.md`

Tracker:

- issue `#37`: implement in-cluster interpretation-agent service behind `workflow-api`
- issue `#36`: retire or repurpose legacy `node02` `vllm` once the Mac-backed operator path is settled

## Most Important Repo Docs Added Today

- `docs/machine-state-2026-03-24.md`
- `docs/live-state-2026-03-24.md`
- `docs/glasslab-v2/ollama-native-openclaw.md`
- `docs/glasslab-v2/node02-interpretation-agent-experiment.md`
- `docs/glasslab-v2/interpretation-agent-service.md`

## Current Best Mental Model

- OpenClaw remains the narrow front door
- Macs host stronger inference and ranking
- bounded agents should run in-cluster as backend services
- `workflow-api` remains the orchestrator and source of truth
