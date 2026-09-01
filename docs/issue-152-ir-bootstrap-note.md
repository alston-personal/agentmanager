# Issue #152 — Antigravity fresh-session bootstrap correction

## Durable state authority

Fresh Antigravity executor continuity is hydrated from the existing Canonical IR contract, not reconstructed from workspace roots, Pulse/PM2 state, or a new conversation/project focus store.

Current Core acceptance path:

```text
Antigravity PreInvocation
  -> Oracle ONE local projection
  -> resolve canonical `agentos-core`
  -> validate `agentos.execution-head/v1` generation
  -> validate matching `agentos.ir/v1` `index_id`
  -> inject one bounded Canonical IR envelope
  -> Gemini first model invocation
```

The current canonical continuation publisher (`agent_core/project_continuation_index.py`) is intentionally restricted to `agentos-core` and atomically publishes:

- `projects/agentos-core/execution-head.json`
- `projects/agentos-core/continuity/latest.json`

Both share one `index_id`; the continuation contains the `agentos.ir/v1` Canonical IR.

## Multi-root rule

Antigravity `workspacePaths` are only a gate proving that the Core checkout (`agentmanager`) is present. Sibling roots must never become candidate current projects. The hook resolves only `agentos-core` for this acceptance slice.

## Fail-closed rule

If the execution head or Canonical IR is missing, malformed, or has a mismatched generation, inject/report `ONE_IR_HEAD_UNRESOLVED`. Do not fall back to workspace enumeration, Pulse, PM2, local memory, or vendor conversation reconstruction.

## Live acceptance

A fresh built-in Antigravity Gemini conversation receives only `繼續` and must continue from the injected IR. Evidence should expose at least:

- `source=ONE_PREINVOCATION_IR`
- `project_id=agentos-core`
- `index_id=<canonical generation>`
- `ir_id=<canonical IR>`

No sibling-project state should appear unless newer explicit user intent asks for it.
