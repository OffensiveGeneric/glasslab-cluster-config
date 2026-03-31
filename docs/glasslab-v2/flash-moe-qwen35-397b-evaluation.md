# Flash-MoE Qwen3.5-397B Evaluation On `.21`

This note records the first successful bootstrap and smoke-test pass for the `flash-moe` runtime on `192.168.1.21`.

## What Was Completed

Validated from `glasslab-bastion -> glasslab-44 -> .21`:

- the Hugging Face snapshot for `mlx-community/Qwen3.5-397B-A17B-4bit` completed
- tokenizer export completed
- non-expert weight extraction completed
- expert repack completed
- the bootstrap log ended with:
  - `flash-moe bootstrap complete`

The prepared runtime artifacts now include:

- `metal_infer/model_weights.bin`
- `metal_infer/model_weights.json`
- `metal_infer/tokenizer.bin`
- generated `metal_infer/vocab.bin`

## Bootstrap/Runtime Mismatch

The first runtime failure after bootstrap was not a download problem.

The first mismatch was:

- the bootstrap path generated `tokenizer.bin`
- the Metal runtime still expected a separate `vocab.bin`

So the setup and runtime paths had drifted apart. The immediate fix was to generate `vocab.bin` from the same tokenizer data so the runtime could decode generated token ids into output text.

The second mismatch was subtler:

- the first generated `vocab.bin` only covered the base vocab range
- Qwen's added chat-format tokens live above that range

That produced `<unk>` output for special tokens. Regenerating `vocab.bin` with the
added-token ids included fixed that specific decode failure.

The third mismatch was the most important for actual model quality:

- the compiled `MODEL_PATH_DEFAULT` still pointed at the original upstream
  author path under `/Users/danielwoods/...`
- on `.21`, the real completed snapshot and `packed_experts/` live under
  `/Users/glasslab/...`

That meant the runtime could start, but it saw:

- `[experts] 0/60 packed layer files available`

After correcting the model path to the real local snapshot, the same runtime saw:

- `[experts] 60/60 packed layer files available`

## What Was Validated

### Direct CLI inference

`./infer` now runs successfully on `.21`.

Observed first-pass runtime characteristics:

- hardware:
  - `Apple M4 Max`
- time to first token:
  - about `1.16s` on the tested prompt
- generation rate:
  - about `13.5 tok/s` over the full sample

That proves the model is actually runnable on the host.

### HTTP server mode

`./infer --serve 8000` also starts successfully.

Validated endpoints:

- `GET /health`
- `GET /v1/models`
- `POST /v1/chat/completions`

The server now returns a proper non-stream JSON body for:

- `stream: false`

That specific API-contract bug is fixed.

An intermediate representative response looked like:

```json
{"id":"chatcmpl-1","object":"chat.completion","choices":[{"index":0,"message":{"role":"assistant","content":"</"},"finish_reason":"stop"}]}
```

After patching the serve-mode response cleanup and rebuilding `infer`, a fresh
server on port `8001` returned:

```json
{"id":"chatcmpl-1","object":"chat.completion","choices":[{"index":0,"message":{"role":"assistant","content":"A transformer is a type of deep learning model that relies entirely on a self-attention mechanism to process sequential data, enabling it to learn complex"},"finish_reason":"stop"}]}
```

That proves the remaining problem is no longer “empty completion” or leaked
`</think>` in the final JSON body.

## Current Quality Boundary

Bootstrapped and serving does not yet mean useful.

Observed problems:

- the first direct CLI prompt about DreamSim degraded into repetitive text
- the first `POST /v1/chat/completions` requests returned zero generated tokens
- later patched runs emitted tokens, but they were still low quality or malformed
- server logs showed:
  - prompt prefill completed
  - initial runs: `generated=0 tokens`
  - later runs: very short token streams such as `Yes`, `$$`, or `1`
- after the added-token `vocab.bin` fix, the runtime no longer emitted `<unk>`
  for the chat-format special tokens, but the completions were still poor
- after the default model-path fix, the runtime began loading all expert layer
  files instead of zero, and the CLI output improved from total garbage to at least
  a recognizably structured answer start

So the current state is:

- runtime bring-up: succeeded
- server surface: succeeded
- output quality / completion behavior: not yet acceptable
- even after the correct model-path fix, quality was still poor until the
  serve-mode cleanup patch; the current boundary is no longer empty output, but
  shallow/truncated output quality
- OpenAI-compatible non-stream response semantics: improved enough to test, but not yet trustworthy for Glasslab use

## Practical Conclusion

`.21` should be treated as:

- a prepared experimental inference host

and not yet as:

- a production OpenClaw backend
- a reliable interpretation backend
- a generally usable Glasslab inference endpoint

## Recommended Next Steps

1. Inspect `flash-moe` server generation logic for why chat-completions stop immediately.
2. Improve output quality so short prompts do not collapse into trivial junk completions.
3. Re-test with a small set of controlled prompts after that quality work.
4. Only consider Glasslab integration if the server can return non-empty, non-repetitive bounded answers with a stable API contract.
