# Live State Report

Date: 2026-03-19

This report records what was directly validated from the provisioner at `192.168.1.44`.

This is actual live state, not just repo state.

## Access Note

- the laptop at `/home/gr66ss` could not be treated as authoritative
- SSH and `kubectl` checks were run from the live provisioner path on `.44`

## Cluster Baseline

Validated from:

- `kubectl get nodes -o wide`
- `kubectl get pods -A -o wide`

Current node state:

- `cp01` `Ready` `control-plane`
- `node01` `Ready` `worker`
- `node02` `Ready` `worker`
- `node03` `Ready` `worker`
- `node04` `Ready` `worker`
- `node05` `Ready` `worker`

Current Kubernetes version:

- `v1.35.2`

Observed worker ages:

- `node01` and `node02`: about `8d`
- `node03`, `node04`, `node05`: about `6d22h` to `6d20h`

## GPU State

Validated from:

- `kubectl get nodes -o jsonpath=...`
- `kubectl get pods -A -o wide`

Allocatable GPUs:

- `node01`: `1`
- `node02`: `1`
- `node04`: `1`

No allocatable GPU resource on:

- `cp01`
- `node03`
- `node05`

Device plugin state:

- `nvidia-device-plugin-daemonset` running on:
  - `node01`
  - `node02`
  - `node04`

## glasslab-agents State

Validated from:

- `kubectl -n glasslab-agents get deploy,svc,pvc`
- `kubectl get pods -A -o wide`

Observed state:

- `glasslab-agent-api` deployment: `1/1`
- `vllm` deployment: `1/1`
- `glasslab-agent-api` pod running on `node03`
- `vllm` pod running on `node02`

Observed PVC state:

- `glasslab-agent-artifacts`: `Bound`
- `glasslab-agent-state`: `Bound`
- `titanic-datasets`: `Bound`
- `vllm-model-cache`: `Bound`

Important update relative to older assumptions:

- `vLLM` is no longer just “warming and not ready”
- it is live and serving the current stack

## glasslab-v2 State

Validated from:

- `kubectl -n glasslab-v2 get deploy,sts,svc,cm,secret`
- `kubectl get pods -A -o wide`
- `./scripts/smoke-test-v2.sh --include-openclaw`

Observed deployments:

- `glasslab-minio`: `1/1`
- `glasslab-nats`: `1/1`
- `glasslab-openclaw`: `1/1`
- `glasslab-workflow-api`: `1/1`

Observed statefulsets:

- `glasslab-postgres`: `1/1`

Observed services:

- `glasslab-minio`
- `glasslab-nats`
- `glasslab-openclaw`
- `glasslab-postgres`
- `glasslab-workflow-api`

Observed PVC state after the storage cutover:

- `glasslab-postgres-data`: `Bound`
- `glasslab-minio-data`: `Bound`

Observed placement:

- `glasslab-minio` pod on `node01`
- `glasslab-postgres` pod on `node01`
- `glasslab-openclaw` pod on `node01`
- `glasslab-workflow-api` pod on `node03`
- `glasslab-nats` pod on `node05`

Important drift from repo-managed default assumptions:

- OpenClaw is live at `1` replica right now
- the committed manifest posture may still treat OpenClaw as “default off,” but live state is “on”
- `Postgres` and `MinIO` are no longer on `emptyDir`
- both now use retained local PV/PVC storage on `node01`

## Workflow API State

Validated from:

- `kubectl -n glasslab-v2 logs deploy/glasslab-workflow-api --tail=120`
- `./scripts/smoke-test-v2.sh --include-openclaw`

Observed health:

- repeated `GET /healthz` responses returning `200 OK`
- smoke test health response:
  - `status: ok`
  - `app: glasslab-workflow-api`
  - `version: 0.1.0`
  - `workflow_count: 3`

Observed workflow catalog from live service:

- `generic-tabular-benchmark`
- `literature-to-experiment`
- `replication-lite`

This confirms the workflow registry is not just theoretical in the repo.

## OpenClaw State

Validated from:

- `kubectl -n glasslab-v2 logs deploy/glasslab-openclaw --tail=120`
- `./scripts/smoke-test-v2.sh --include-openclaw`
- `./scripts/check-openclaw-tool-calling.sh --attempts 3`

Observed runtime facts:

- OpenClaw is using the local vLLM-backed model path
- log lines show:
  - `glasslab-vllm/Qwen/Qwen3-4B-Instruct-2507`
  - context window `16384`
- WhatsApp channel appears live
- repeated log pattern shows the WhatsApp provider restarting after `stale-socket` and then resuming listening

Observed WhatsApp behavior:

- the channel is not just configured in theory
- logs repeatedly show:
  - provider starting
  - “Listening for personal WhatsApp inbound messages.”

This is a meaningful live-state advance beyond the earlier repo assumption that chat-channel validation was just future work.

## OpenClaw Tool-Calling Validation

Validated from:

- `./scripts/check-openclaw-tool-calling.sh --attempts 3`

Observed result:

- no-arg create path: pass
- no-arg get path: pass
- experimental argumented path: fail `3/3`

Observed successful no-arg run id:

- `d025387b1e5a4600b1e90f5f9ebfec43`

Observed failure pattern on experimental argumented tool:

- `workflow_api_get_family_by_id failed: workflow_id is required`

Current conclusion remains unchanged:

- the safe no-arg operator path is still valid
- argumented tool use is still not reliable enough to promote into the default operator flow

## Main Drift From Older Mental Model

The biggest changes relative to the older March 12 handoff are:

- `vLLM` is live and serving, not stuck in warm-up
- `glasslab-v2` core services are live
- OpenClaw is live at `1` replica
- WhatsApp channel integration is active
- the workflow registry is exposed live through `workflow-api`
- the tool-calling reliability conclusion still holds:
  - no-arg safe path works
  - argumented path still fails

## Immediate Implications

- the current platform bottleneck is not “is vLLM up at all”
- the current bottleneck is still structured tool-calling reliability on the local model/runtime path
- storage and durability remain highly relevant because the platform has already advanced beyond a toy state

## Suggested Next Validations

- compare live OpenClaw replica state with the committed manifest and decide whether repo defaults should change
- capture whether the current WhatsApp channel posture should be treated as operationally supported or still experimental
- decide whether to document the current node placement of `Postgres`, `MinIO`, `OpenClaw`, `workflow-api`, and `vLLM` as intentional or temporary
- continue storage work before adding broader workflow complexity
