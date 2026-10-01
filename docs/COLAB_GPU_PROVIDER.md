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
3. Oracle has Application Default Credentials (ADC) for the intended Google user with scopes `openid`, `cloud-platform`, `userinfo.email`, and `colaboratory`;
4. `colab --auth=adc usage` returns a usable account state without interactive stdin;
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


## Oracle acceptance lane

Canonical workflow: `.github/workflows/oracle-install-colab-provider.yml`

The first pinned upstream candidate is:

```text
killkli/minimax-h3-colab-skill
7768ebfb1627546595f37e9acfd2d353937c6cd8
```

The workflow installs the provider into an immutable path under
`/home/ubuntu/agent-data/providers/colab/releases/<sha>`, updates a runtime
`current` symlink, installs `uv` / `google-colab-cli` when needed, and runs
a non-leaking ADC/quota preflight.

If Oracle ADC is not established, the provider remains `AUTH_REQUIRED`. The canonical one-time bootstrap script is `/home/ubuntu/.config/agentos/colab-adc-bootstrap.sh`. It runs `gcloud auth application-default login` with the four Colab-required scopes. After that one-time interactive authorization, unattended provider and H3 jobs use `COLAB_AUTH=adc` and must not depend on OAuth copy-paste stdin.

The pinned Oracle gcloud runtime is installed by `.github/workflows/oracle-install-colab-adc-runtime.yml`. Current pinned version: `587.0.0` (Linux ARM archive, verified by SHA-256).

Receipt path:

```text
/home/ubuntu/agent-data/evidence/colab/install-<github-run-id>.json
```


## Authentication decision: ADC for AgentOS

The Colab CLI OAuth2 provider uses a remote copy-paste authorization flow and may call `input()` when a refresh token is unavailable or invalid. That behavior is suitable for an interactive terminal, but unsafe for AgentOS unattended SSH/heredoc execution because stdin is also the command transport.

AgentOS therefore standardizes Oracle Colab execution on **Application Default Credentials (ADC)**:

```text
interactive bootstrap once
  -> gcloud application-default credentials
  -> unattended colab --auth=adc
  -> MiniMax H3 / other Colab consumers
```

Required user credential scopes:

```text
openid
https://www.googleapis.com/auth/cloud-platform
https://www.googleapis.com/auth/userinfo.email
https://www.googleapis.com/auth/colaboratory
```

ADC credentials remain in the standard gcloud config path with mode 0600 and must never be copied into prompts, repositories, receipts, or workflow logs.
