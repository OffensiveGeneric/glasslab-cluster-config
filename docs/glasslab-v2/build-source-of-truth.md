# Build Source Of Truth

This note captures a recurring operational failure mode:

- repo state on the laptop may be current
- runtime export on `.44` may be current
- but the image actually running in cluster may still have been built from an older `.44` source tree

When that happens, OpenClaw and `workflow-api` can disagree about which routes or contracts exist even if both appear recent in isolation.

## The Failure Mode

The concrete example on 2026-03-27 was:

- OpenClaw runtime on `.44` included `workflow_api_bootstrap_research_session_from_latest_user_message`
- that tool called `POST /research-sessions/bootstrap`
- live `workflow-api` returned `404 Not Found`

The immediate temptation was to assume:

- service DNS problem
- wrong endpoint path
- tool binding bug

But the real issue was simpler:

- the live `workflow-api` image had been built from an older `.44` checkout
- that checkout did not actually contain the newer session-bootstrap route surface
- so OpenClaw and `workflow-api` were built from different effective source trees

## Operational Rule

Before claiming that a live backend contract exists, verify all three layers:

1. repo contract
2. `.44` build tree
3. live cluster image / route behavior

Do not assume that a current runtime export implies a current backend image.

## Required Checks

### For `workflow-api`

Check:

- which source tree on `.44` was used for the build
- which image tag is deployed
- whether the route actually responds live

Example:

```bash
ssh glasslab-44
cd /home/glasslab/cluster-config
grep -RIn "research-sessions/bootstrap" services/workflow-api/app
kubectl -n glasslab-v2 get deploy glasslab-workflow-api -o wide
kubectl -n glasslab-v2 port-forward deploy/glasslab-workflow-api 18080:8080
curl -i -X POST http://127.0.0.1:18080/research-sessions/bootstrap
```

### For OpenClaw

Check:

- the running runtime payload inside the pod
- the actual prompt/tool bindings in `/var/lib/openclaw/runtime/glasslab-config`

Example:

```bash
kubectl -n glasslab-v2 exec deploy/glasslab-openclaw -- \
  sh -lc 'grep -RIn "research-sessions/bootstrap" /var/lib/openclaw/runtime/glasslab-config'
```

## Practical Recommendation

When a rollout touches a backend contract that OpenClaw depends on:

- sync the full relevant backend subtree to `.44`
- rebuild the backend image from that synced tree
- verify the route live
- only then re-export and restart OpenClaw

Do not hot-patch one file at a time into a deeply drifted `.44` checkout if the live build source is already suspect.

## Source Of Truth Hierarchy

For backend-contract questions, the order of truth is:

1. live route response from the deployed service
2. deployed image tag and its build source on `.44`
3. committed repo state

For operator-runtime questions, the order of truth is:

1. files under `/var/lib/openclaw/runtime/glasslab-config` in the live pod
2. `.44` export source tree
3. committed repo state

## What This Means For `#57`

Repo inheritability is not only about where state is stored.

It is also about making it obvious:

- what source tree a live image was built from
- whether `.44` is drifted from Git
- whether runtime export and backend build used the same code generation epoch

That should be treated as a first-class operational concern, not as incidental rollout trivia.
