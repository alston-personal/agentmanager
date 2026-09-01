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
  -> active Antigravity model first invocation
```

The current canonical continuation publisher (`agent_core/project_continuation_index.py`) is intentionally restricted to `agentos-core` and atomically publishes:

- `projects/agentos-core/execution-head.json`
- `projects/agentos-core/continuity/latest.json`

Both share one `index_id`; the continuation contains the `agentos.ir/v1` Canonical IR.

## Workspace gate rule

Antigravity `workspacePaths` are only a gate proving that the active workspace is inside the canonical Core checkout tree. The accepted gate includes both the repository root and descendants, for example:

- `/home/ubuntu/agentmanager`
- `/home/ubuntu/agentmanager/workspace/if-tv-station`

A descendant workspace name is never a project selector. Once the gate is open, #152 resolves exactly `agentos-core`; `if-tv-station`, another nested workspace, or sibling roots must not replace the canonical continuation. Prefix lookalikes such as `/home/ubuntu/agentmanager-old` are not accepted as descendants.

This descendant rule is required because Antigravity may report the active nested workspace rather than the repository root in a fresh executor conversation.

## Executor identity rule

The PreInvocation hook may bind the active Antigravity executor only from the hook payload's current `modelName`. A Codex-bearing model name binds `antigravity-codex`; a Gemini-bearing model name binds `antigravity-gemini`; unknown names remain `antigravity-unknown` with `executor_identity_bound=false`.

The generic MCP stdio process has no trustworthy caller-model context and therefore reports `antigravity-unbound`. MCP connectivity must not be used to fabricate Gemini/Codex identity evidence.

## Fail-closed rule

If the execution head or Canonical IR is missing, malformed, or has a mismatched generation, inject/report `ONE_IR_HEAD_UNRESOLVED`. Do not fall back to workspace enumeration, Pulse, PM2, local memory, or vendor conversation reconstruction.

## Live acceptance

A fresh built-in Antigravity executor conversation receives only `繼續` and must continue from the injected IR. Evidence should expose at least:

- `source=ONE_PREINVOCATION_IR`
- `project_id=agentos-core`
- `index_id=<canonical generation>`
- `ir_id=<canonical IR>`
- executor identity bound by PreInvocation when the model name proves it

No sibling/nested-project state should become the durable continuation merely because that workspace is active.
