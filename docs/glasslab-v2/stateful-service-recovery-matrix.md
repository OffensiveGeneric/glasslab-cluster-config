# Stateful Service Recovery Matrix

This note compresses the current node-loss discussion into one operator-readable matrix.

It exists to advance issue `#13`.

## Current Classification

| Service | Current backing | Failure domain | Best near-term strategy | Why |
| --- | --- | --- | --- | --- |
| `Postgres` | local PV on `node01` | loss of `node01` | backup/restore first, deliberate HA later | database semantics matter more than easy mobility |
| `MinIO` | local PV on `node01` | loss of `node01` | backup/restore first, possible mirroring later | artifact storage matters, but casual NFS primary storage is still a poor first move |
| `OpenClaw` writable state | local PV on `node01` | loss of `node01` | backup/restore now, shared-storage relocation test next | state is relatively small and operator continuity matters |
| `NATS` JetStream | local PV on `node05` | loss of `node05` | backup/restore now, shared-storage or replication decision later | smaller state than the databases, but still not worth casual complexity yet |
| shared datasets | NFS RWX | NFS server / export | keep shared path | already a good fit for shared storage |
| shared artifacts | NFS RWX | NFS server / export | keep shared path | already a good fit for shared storage |

## Practical Interpretation

Near-term priority order:

1. keep backup/restore discipline for every local-PV-backed service
2. test OpenClaw shared-state relocation
3. decide whether NATS needs better-than-backup recovery
4. leave Postgres and MinIO on more deliberate HA/storage tracks

## Service Notes

### Postgres

Do not move it to shared storage casually just because NFS exists.

Use:

- logical backups
- filesystem backup during quiet windows
- later HA design only if workflow state becomes more central

### MinIO

Treat it as important state, not as disposable cache.

Use:

- filesystem-level backup now
- optional artifact mirroring later
- later storage-model decision if MinIO becomes the long-term source of truth

### OpenClaw

This is the best first relocation candidate.

Why:

- writable state is small
- channel and session continuity have direct operator value
- rollback to the current local-PV claim is straightforward

Reference path:

- `docs/glasslab-v2/runbooks/test-openclaw-shared-state.md`

### NATS

Keep the current local-PV posture for now unless JetStream durability becomes materially more important.

Use:

- backup/restore first
- shared-storage or multi-node design only after the real durability need is clearer

## Decision Rule

If a service is:

- small-state
- operator-visible
- easy to roll back

then it is a better early shared-storage relocation candidate.

If a service is:

- database-like
- correctness-sensitive
- difficult to validate casually

then it should stay on a deliberate backup/restore or HA track first.
