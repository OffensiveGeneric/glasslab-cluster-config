# Live State 2026-03-30

Status: historical live snapshot.

This note records what was true on 2026-03-30. Use it for provenance and
decision history, not as a current-state summary.

This note captures what was actually validated from `.44` during the 2026-03-30 lab session.

## What Is Live

- `workflow-api` is live on `.44` in `glasslab-v2`.
- validated image:
  - `ghcr.io/offensivegeneric/glasslab-workflow-api:0.1.54-local`
- validated pod:
  - `glasslab-workflow-api-868656c65f-rl9kf`
- `/healthz` reports:
  - `build_source_revision: 41cf6b6`
  - `build_source_label: git:41cf6b6`

That means the current live `workflow-api` reflects the repo state through:

- `6048a39` `Add autoresearch model comparison summary`
- `fd1f6c0` `Flag overfitting risks in execution preflight`
- `41cf6b6` `Add validation split variants to experiment path`

## What Was Validated Live

### Coding-model notebook refinement

The coding-model notebook lane is live and working.

- notebook refinement backend:
  - `.12` native Ollama
  - model: `qwen2.5-coder:14b`
- live refinement path returned:
  - `refinement_source: "coding-model"`
- refined notebook artifact was written under:
  - `/mnt/artifacts/workflow-api/notebook-drafts/<campaign_id>/analysis_notebook_refined.ipynb`

A sample exported from that live artifact is in the repo:

- [analysis_notebook_refined_sample.ipynb](/home/gr66ss/cluster-config/docs/glasslab-v2/examples/analysis_notebook_refined_sample.ipynb)

Current quality note:

- the infrastructure path is real
- the refined notebook still stays close to the deterministic scaffold
- next improvement is prompt/content quality, not basic wiring

### Interpretation lane

The interpretation path is live with the bounded-agent boundary intact.

- `workflow-api` calls `interpretation-agent`
- `interpretation-agent` uses:
  - primary: `.23` `qwen3:30b`
  - fallback: `.12` `qwen3:14b`
  - final fallback: deterministic interpretation scaffold

In live testing, interpretation still sometimes falls back due to model latency/timeouts, but the lane is inspectable and fail-closed.

### Autoresearch campaign lane

The bounded autoresearch lane is mostly real now.

Validated live or near-live behavior:

- create campaign
- draft methodology variants
- launch bounded validation iteration
- persist a run id
- write synthetic `status.json` and `metrics.json`
- decide latest iteration as `keep`
- expose model-comparison summary surface in repo/live build

Backend additions now present in the live code:

- autoresearch campaign summary includes:
  - `recommended_model`
  - `model_comparison`
- execution preflight surfaces:
  - interpretation-derived runtime/package warnings
  - split/validation warnings
  - train-vs-test blocking issue when paths are identical

## Main Remaining Gap

The main blocker is no longer OpenClaw for this specific lane. It is a small session-state gap in `workflow-api`.

What failed during live end-to-end smoke:

- the smoke path used a generic intake create route
- that did not bind `latest_intake_id` onto the session strongly enough for the fully session-scoped path
- downstream session-specific interpretation/design/preflight became brittle

The repo fix is already written and tested locally:

- add session-scoped intake creation endpoints
  - `POST /research-sessions/{session_id}/intakes`
  - `POST /research-sessions/latest/intakes`

Local status for that fix:

- focused test passes
- rollout to `.44` had started as `0.1.55-local`
- but was not revalidated to completion before this note was written

So the honest state is:

- `0.1.54-local` is definitely live and validated
- `0.1.55-local` session-intake fix is repo-ready and locally tested
- `0.1.55-local` should be the next live validation checkpoint

## Machine Status

### `.12`

- serving native Ollama
- installed models confirmed:
  - `qwen2.5-coder:14b`
  - `qwen3:14b`
- currently used for:
  - coding-model notebook refinement
  - bounded interpretation fallback

### `.23`

- reachable from the cluster
- installed models confirmed earlier in the session:
  - `qwen3:30b`
  - `deepseek-r1:32b`
- currently used as the preferred interpretation backend
- still somewhat latency-sensitive for the current interpretation prompt budget

### `.21`

The large `flash-moe` bootstrap on `.21` later completed successfully.

Validated follow-on state from `glasslab-44 -> .21`:

- Hugging Face snapshot completed:
  - `58/58` files fetched
- tokenizer export completed
- non-expert weight extraction completed:
  - `metal_infer/model_weights.bin`
  - `metal_infer/model_weights.json`
- expert repack completed:
  - `packed_experts` written under the snapshot path
- bootstrap log ended with:
  - `flash-moe bootstrap complete`

The remaining runtime work was smaller but important:

- `infer` initially failed because the runtime still expected `vocab.bin`
- the bootstrap path had only produced `tokenizer.bin`
- `vocab.bin` was then generated from the same tokenizer data
- after that, `./infer` ran successfully on `.21`

Current quality boundary:

- `.21` now serves `flash-moe` over `http://127.0.0.1:8000`
- `GET /health` and `GET /v1/models` succeed
- direct `infer` and `POST /v1/chat/completions` do not yet produce useful answers
- the first substantive prompt degenerated into repetitive text
- the first server-side chat-completions calls returned zero generated tokens

So `.21` is now a prepared and runnable experimental inference host, but not yet a backend we should rely on for Glasslab traffic.

## Practical Conclusion

The experiment spine is real now:

- literature / intake
- interpretation
- methodology variants
- notebook draft/refinement
- bounded run launch
- comparison / keep-discard decision

The main next step is not more model swapping. It is:

- finish the session-scoped intake fix live
- rerun the autoresearch smoke path end to end
- keep tightening the run comparison and experiment contract

That is the shortest path to the “determine best methods to solve an issue” goal.
