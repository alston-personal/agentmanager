# Issue #152 — Antigravity fresh-session bootstrap correction

## Durable state authority

Fresh Antigravity executor continuity is hydrated from the existing Canonical IR contract, not reconstructed from workspace roots, Pulse/PM2 state, or a new conversation/project focus store.

Current Core path:

```text
Antigravity PreInvocation
  -> Oracle ONE local projection
  -> resolve canonical `agentos-core`
  -> validate `agentos.execution-head/v1` generation
  -> validate matching `agentos.ir/v1` `index_id`
  -> bind caller executor identity only from current PreInvocation `modelName`
  -> inject one bounded Canonical IR envelope
  -> current Antigravity model invocation
```

The current canonical continuation publisher (`agent_core/project_continuation_index.py`) is intentionally restricted to `agentos-core` and atomically publishes:

- `projects/agentos-core/execution-head.json`
- `projects/agentos-core/continuity/latest.json`

Both share one `index_id`; the continuation contains the `agentos.ir/v1` Canonical IR.

## Multi-root rule

Antigravity `workspacePaths` are only a gate proving that the Core checkout (`agentmanager`) is present. Sibling roots must never become candidate current projects. The hook resolves only `agentos-core` for this acceptance slice.

## Executor identity boundary

Canonical continuity and executor identity are separate claims.

The Antigravity `PreInvocation` payload contains the current `modelName`, so that hook may bind a recognized caller as `antigravity-gemini` or `antigravity-codex`. Unrecognized model names remain `antigravity-unknown` with `executor_identity_bound=false`; the hook must not guess from a generic model family name.

The shared stdio MCP process has no reliable per-tool caller-model context. Its responses therefore prove only the Antigravity surface / ONE connection and explicitly return the executor identity as unbound. MCP must not claim `antigravity-gemini` merely because the original E2 adapter was built for Gemini.

## Fail-closed rule

If the execution head or Canonical IR is missing, malformed, or has a mismatched generation, inject/report `ONE_IR_HEAD_UNRESOLVED`. Do not fall back to workspace enumeration, Pulse, PM2, local memory, or vendor conversation reconstruction.

If the current model name cannot prove an executor class, continuity hydration may still proceed, but an executor-specific E2/E3 acceptance must not be marked verified from that session without separate valid identity evidence.

## Live E2 acceptance

E2 is live-verified for the built-in Antigravity Gemini surface. Two completely fresh conversations received only `繼續` and independently recovered:

- `source=ONE_PREINVOCATION_IR`
- `project_id=agentos-core`
- `index_id=idx-core-152`
- `ir_id=ir-core-152`

Evidence is preserved in `.agentos/evidence/issue-152-antigravity-gemini-e2-2026-09-01.md`.

## E3 acceptance target

The next child generation is intended for a completely fresh built-in Antigravity Codex session. After guarded E2 -> E3 advancement and reload, a fresh Codex conversation receiving only `繼續` must recover the child Canonical IR and expose at least:

- `source=ONE_PREINVOCATION_IR`
- `project_id=agentos-core`
- `index_id=idx-core-152-e3-1`
- `ir_id=ir-core-152-e3-1`
- `executor_class=antigravity-codex`
- `executor_identity_bound=true`
- the actual `model_name`

No sibling-project state should appear unless newer explicit user intent asks for it. E3 remains unverified until live evidence passes.
