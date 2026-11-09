# Issue #152 — Antigravity fresh-session bootstrap correction

## Durable state authority

Fresh Antigravity executor continuity is hydrated from the Canonical IR contract, not reconstructed from workspace roots, Pulse/PM2 state, local memory, or vendor history.

Current Core acceptance path:

```text
Antigravity PreInvocation
  -> ONE active-continuation selector
       project_id + index_id + ir_id
  -> Oracle ONE local projection
  -> resolve selected canonical project
  -> validate matching agentos.execution-head/v1 generation
  -> validate matching agentos.ir/v1 index_id + ir_id
  -> inject one bounded Canonical IR envelope
  -> active Antigravity model first invocation
```

The active selector is **not a second state store**. It is a Realm/runtime pointer only. Goal, constraints, decisions, pending tasks, next action, capability and evidence remain in the referenced Canonical IR.

The current canonical continuation publisher (`agent_core/project_continuation_index.py`) is initially restricted to `agentos-core` and atomically publishes:

- `projects/agentos-core/execution-head.json`
- `projects/agentos-core/continuity/latest.json`

Both share one `index_id`; the continuation contains the `agentos.ir/v1` Canonical IR.

## Active selector rule

`agent_core/active_continuation.py` owns `runtime/active-continuation.json` with schema `agentos.active-continuation/v1`.

A selector may be activated only when its exact `project_id / index_id / ir_id` currently resolves to a valid canonical generation. Reading the selector revalidates that generation. If the project advances and the selector remains on the parent generation, the selector is stale and fresh hydration fails closed until it is reconciled.

For the current #152 slice, `scripts/seed_active_continuation.py` may initialize a missing selector from `agentos-core` because `agentos-core` is still the only project accepted by the Canonical IR publisher. It never overwrites an existing stale selector.

## Workspace rule

Antigravity `workspacePaths` have **no continuation-selection authority**.

This was learned from two real E3 failures:

1. a Codex conversation under `agentmanager/workspace/if-tv-station` continued local if-tv-station state when the old Hook required the repository root as a workspace gate;
2. after descendant support was added, a Codex conversation under `/home/ubuntu/acas` continued local ACAS state because the Hook still required some path under `agentmanager`.

Therefore the gate itself was removed. A fresh executor opened in ACAS, if-tv-station, the Core checkout, or with an empty workspace list must receive the same ONE-selected Canonical IR unless newer explicit user intent has deliberately changed the active continuation.

Workspace metadata may still describe execution environment, but it must never select or replace durable continuation.

## Executor identity rule

The PreInvocation hook may bind the active Antigravity executor only from the hook payload's current `modelName`. A Codex-bearing model name binds `antigravity-codex`; a Gemini-bearing model name binds `antigravity-gemini`; unknown names remain `antigravity-unknown` with `executor_identity_bound=false`.

The generic MCP stdio process has no trustworthy caller-model context and therefore reports `antigravity-unbound`. MCP connectivity must not be used to fabricate Gemini/Codex identity evidence.

## Fail-closed rule

If the active selector is missing/malformed/stale, or the selected execution head / Canonical IR is missing, malformed, or generation-mismatched, inject/report `ONE_IR_HEAD_UNRESOLVED`. Do not fall back to workspace enumeration, Pulse, PM2, local memory, or vendor conversation reconstruction.

## Live acceptance

A fresh built-in Antigravity executor conversation receives only `繼續` and must continue from the injected IR. Evidence should expose at least:

- `source=ONE_PREINVOCATION_IR`
- `selection_source=ONE_ACTIVE_CONTINUATION`
- `project_id=<active selector project>`
- `index_id=<active selector generation>`
- `ir_id=<active selector IR>`
- executor identity bound by PreInvocation when the model name proves it

For E3, the expected active generation is currently `agentos-core / idx-core-152-e3-1 / ir-core-152-e3-1`. The current IDE workspace must not alter that result.
