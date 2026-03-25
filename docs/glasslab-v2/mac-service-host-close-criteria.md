# Mac Service Host Close Criteria

This note narrows issue `#32`.

The core architecture decision is already effectively made:

- use the Macs as service hosts first
- do not treat them as kubeadm workers in the current phase

What remained unclear was when that issue should be considered materially resolved.

## Close Criteria

Issue `#32` should be considered closeable when these are true:

1. the repo clearly records the Macs as service hosts, not worker-node targets
2. at least one Mac-hosted inference path is validated as useful
3. at least one Mac-hosted secondary service path is validated as useful
4. the remaining open work has shifted to:
   - model selection
   - service integration
   - operator/runtime validation
   rather than cluster-worker evaluation

## Current Status Against Those Criteria

### 1. Service-host decision recorded

Satisfied.

Reference:

- `mac-service-host-boundary.md`

### 2. Mac-hosted inference path validated

Satisfied in the narrow sense.

Current state:

- `.23` is already the primary external chat-inference host
- the current unresolved work is tool-capable model selection, not whether the Mac is useful

### 3. Mac-hosted secondary service path validated

Satisfied.

Current state:

- `.12` is already serving the bounded ranker
- `.12` also acts as the first proven native-Ollama tool-capable Mac model lane

### 4. Remaining work no longer depends on worker-node evaluation

Satisfied.

The remaining open work is now:

- native-Ollama tool-capable model validation on `.23`
- ranker integration into `workflow-api`
- deciding later whether any Linux arm64 or VM-based worker experiments are worth a separate issue

## What Should Not Keep This Issue Open

Do not keep this issue open merely because:

- the larger `qwen3:30b` pull is still in progress
- tool-calling parity on `.23` is not done yet
- future Linux arm64 or VM experiments might exist someday

Those are different issues.

## Bottom Line

This issue is no longer really asking:

- "should the Macs be workers?"

It has already been answered:

- "no, use them as service hosts first"

The remaining work belongs elsewhere.

## References

- `mac-service-host-boundary.md`
- `mac-studio-inference.md`
- `../machine-state-2026-03-24.md`
