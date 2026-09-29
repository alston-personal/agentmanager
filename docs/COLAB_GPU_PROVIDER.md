# Colab GPU Provider Integration

**Status:** declared integration candidate  
**Date:** 2026-09-29

## Purpose

AgentOS should treat Google Colab as a governed remote-compute provider, not as a MiniMax-specific shortcut. Model-specific skills compose over the generic provider.

The first consumer is the external open-source `killkli/minimax-h3-colab-skill`, which runs MiniMax H3 Ref2VA inference through Google Colab CLI.

## Capability split

1. `capability://compute.colab.execute`
   - owns Colab authentication/runtime/quota/session concerns;
   - checks current usage before work;
   - treats GPU allocation as opportunistic rather than guaranteed;
   - emits an execution receipt;
   - never exposes OAuth credentials or runtime tokens.

2. `capability://media.video.generate.minimax-h3`
   - composes over the Colab provider;
   - accepts 1-9 reference images in stable order;
   - accepts a UTF-8 prompt;
   - accepts 4-15 second duration;
   - prefers one batch/session for multiple clips;
   - preserves completed outputs when a later clip fails.

## Upstream source

- Repository: `killkli/minimax-h3-colab-skill`
- Upstream skill name: `minimax-h3-colab`
- Upstream entrypoint: `python3 scripts/runner.py batch`
- Upstream license/version must be reviewed and pinned before AgentOS promotes this provider from `declared` to `implemented` or `verified`.

AgentOS does not vendor or silently fork the upstream implementation at this stage. This follows the Reuse Before Build rule and leaves upstream ownership explicit.

## Runtime installation target

The intended execution node is Oracle. Promotion requires a governed installation that proves:

1. Python 3.12 / `uv` prerequisites as required by upstream;
2. `google-colab-cli` is installed;
3. OAuth2 authentication succeeds without secrets entering logs;
4. `colab --auth=oauth2 usage` returns a usable account state;
5. the upstream skill is installed at a pinned commit SHA;
6. a small reference-to-video job completes;
7. the output MP4 exists and is captured in an AgentOS receipt;
8. the receipt records provider, upstream commit, requested runtime class, allocation result, consumed/remaining quota when available, output path/hash, and failure class.

## Important policy boundary

Google AI subscription benefits and Colab allocation are external provider state. AgentOS must query them at execution time. No monthly compute-unit value, GPU type, or per-video CU estimate is a hard-coded contract.

A non-zero compute-unit balance does not guarantee that Colab can allocate the requested GPU or high-memory runtime. Allocation failures must be reported distinctly from authentication, quota, model, upload, and output-download failures.

## Suggested receipt shape

```json
{
  "schema": "agentos.colab-execution-receipt/v1",
  "provider": "google-colab",
  "capability": "capability://compute.colab.execute",
  "consumer_capability": "capability://media.video.generate.minimax-h3",
  "upstream": {
    "repository": "killkli/minimax-h3-colab-skill",
    "commit": "<pinned-sha>"
  },
  "preflight": {
    "authenticated": true,
    "quota_observed": true,
    "requested_gpu": "A100",
    "allocated_gpu": "<observed-or-null>"
  },
  "result": {
    "status": "success",
    "outputs": [
      {"path": "<path>", "sha256": "<digest>"}
    ]
  }
}
```

## Promotion rule

Keep both capabilities at `declared` until Oracle has a pinned upstream install and a live acceptance receipt. After that:

- `compute.colab.execute` may move to `implemented` after generic provider preflight/session/output handling is proven;
- `media.video.generate.minimax-h3` may move to `implemented` after one end-to-end H3 job succeeds;
- mark either `verified` only when repeatable acceptance and regression checks exist.
