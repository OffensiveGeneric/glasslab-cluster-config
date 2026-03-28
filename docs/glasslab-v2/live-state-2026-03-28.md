# Live State 2026-03-28

This note records the actual outcomes of the 2026-03-28 debugging and integration session.

## What Changed

- `workflow-api` gained a one-shot literature-start action:
  - `POST /research-sessions/start-literature-search`
- that backend path now:
  - creates or resumes the active research session
  - stages the research problem
  - starts or reuses the paper-intake queue
  - records a `literature-search-start` operation
- OpenClaw's literature-start tool was updated to call that one-shot backend action instead of trying to sequence multiple backend steps itself
- OpenClaw was also tested against `.23` native Ollama `qwen3:30b`
- the operator profile was temporarily reduced to a literature-only tool surface to test whether a smaller prompt/tool payload improved the 30B path

## Commits Landed

- `383fabd` `Collapse literature search start into one backend action`
- `e6f15d6` `Bump workflow-api rollout image tag`
- `77509df` `Trim OpenClaw operator to literature-only profile`

Related preceding work from the same debugging line:

- `da59133` `Force OpenClaw literature start through bootstrap tool`
- `3ab94a3` `Fix OpenClaw workflow-api plugin parse error`
- `6038b94` `Recover slow OpenClaw literature searches`
- `988fa4e` `Trim initial literature harvest breadth`
- `c358bab` `Increase OpenClaw workflow-api timeout window`
- `ca19050` `Recover OpenClaw session skills via bootstrap`

## What Was Verified Live

- `workflow-api` rolled live to:
  - `ghcr.io/offensivegeneric/glasslab-workflow-api:0.1.33-local`
- live pod after rollout:
  - `glasslab-workflow-api-99d9b7c7-x5xn5`
- OpenClaw rolled live on `.23`:
  - provider base URL `http://192.168.1.23:11434`
  - model `qwen3:30b`
- live OpenClaw pod after the final reduced-profile rollout:
  - `glasslab-openclaw-86958d684-nlc9w`

Backend verification from inside the OpenClaw pod succeeded:

- `POST /research-sessions/start-literature-search`
  - returned `201`
  - returned a session, staged research problem, paper-intake queue, and operation record

Inference verification also succeeded outside OpenClaw's normal turn path:

- `.23` `qwen3:30b` responded to direct Ollama `/api/generate`
- `.23` `qwen3:30b` responded to direct Ollama `/api/chat`
- `.23` `qwen3:30b` also responded to `/api/chat` with a minimal tool schema

So the 30B host was not simply down or unreachable.

## What Still Failed

The live WhatsApp/OpenClaw user path remained unreliable.

Observed failure modes during the session included:

- OpenClaw calling `GET /research-sessions/bootstrap-status` and then stalling instead of progressing
- OpenClaw reporting backend unreachability when `workflow-api` was in fact healthy
- OpenClaw sometimes not invoking the one-shot backend tool at all
- on the `.23` 30B path, OpenClaw logging:
  - `LLM request failed: network connection error. rawError=fetch failed`
  - even though direct Ollama API calls to `.23` worked from `.44` and from inside the OpenClaw pod

That narrows the remaining 30B issue to the OpenClaw integration path itself, not raw network reachability or a dead Ollama host.

## OpenClaw And Tool-Calling Lessons

The main struggle today was not backend capability. It was getting OpenClaw to reliably use what already exists.

Observed pattern:

- `workflow-api` was often healthy and reachable
- the one-shot literature-start endpoint existed and worked when called directly
- OpenClaw still:
  - sometimes called only a lightweight read like `bootstrap-status`
  - sometimes made no state-changing tool call at all
  - sometimes misreported a stalled or timed-out turn as backend unreachability
  - sometimes hit an LLM-side `fetch failed` path on the `.23` 30B route even though direct Ollama calls worked

That means the current weak point is the operator seam:

- OpenClaw is still too responsible for intent routing
- OpenClaw is still too responsible for deciding when to touch the backend
- OpenClaw is still too responsible for classifying tool failures

The practical conclusion is:

- keep OpenClaw as a conversational shell
- move more intent handling into deterministic backend-owned paths
- stop expecting OpenClaw to act like a reliable workflow planner

The next attack path should be:

- deterministic literature/session-start routing
- deterministic "next paper" / "advance review" routing
- backend-owned orchestration for those common intents
- OpenClaw used mainly to summarize and ask clarifying questions when needed

## Most Important Product Conclusion

The backend is now ahead of the chat seam.

What the session made clear:

- `workflow-api` can own the session-start literature flow
- OpenClaw remains unreliable as a multi-step workflow planner
- even a larger model does not automatically fix a weak orchestration seam

The correct next move is to make the researcher-facing start/advance flows more deterministic:

- a narrow router or command mode for session/literature intents
- backend-owned orchestration for those intents
- OpenClaw used mainly as the conversational shell and summarizer

## Current End-Of-Session Risk Note

The user reported that WhatsApp was asking to relink again near the end of the session.

Treat the current WhatsApp linkage state as requiring fresh validation before assuming the chat channel is stable.

The last known good structural facts are:

- `workflow-api` one-shot literature-start path is live
- OpenClaw is configured for `.23` `qwen3:30b`
- direct inference to `.23` works
- the WhatsApp/OpenClaw end-to-end operator path is still not yet trustworthy
