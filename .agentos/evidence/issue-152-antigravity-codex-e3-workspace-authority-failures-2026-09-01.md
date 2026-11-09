# Issue #152 — Antigravity Codex E3 workspace-authority failure evidence

Date: 2026-09-01

Status: E3 NOT VERIFIED. These are sanitized live behavioral failures from completely fresh built-in Antigravity Codex conversations given only `繼續` after the E3 Canonical IR child had already been published.

Expected canonical generation:

- project: `agentos-core`
- index: `idx-core-152-e3-1`
- IR: `ir-core-152-e3-1`
- expected provenance: `source=ONE_PREINVOCATION_IR`

## Attempt 1 — nested if-tv-station workspace

Observed first response continued local `if-tv-station` work instead of the E3 Canonical IR. It reported changes around centralized jobs/memory/render/SFX/YouTube paths, worker `.env` cleanup, `VIDEO_GENERATION_MODE`, build/lint, and local data-layer notes.

Diagnosis at that point: the PreInvocation hook required a workspace path whose basename was exactly `agentmanager`; Antigravity supplied a descendant path under `agentmanager/workspace/if-tv-station`, so the hook returned without hydration.

A descendant-aware gate was implemented, but this was later shown to be insufficient.

## Attempt 2 — unrelated ACAS workspace

Observed first response continued local ACAS work instead of the E3 Canonical IR. It reported:

- new `/home/ubuntu/acas/pytest.ini`;
- pytest import-path repair;
- 15/15 pytest pass;
- 20-turn benchmark pass;
- update to `/home/ubuntu/agent-data/projects/acas/STATUS.md`;
- `agentmanager` working changes left untouched.

No `ONE_PREINVOCATION_IR`, `ONE_ACTIVE_CONTINUATION`, `agentos-core`, `idx-core-152-e3-1`, or `ir-core-152-e3-1` provenance was reported.

Diagnosis: even after descendant support, the hook still used `workspacePaths` as a boolean gate. Because `/home/ubuntu/acas` is outside the `agentmanager` tree, the hook again returned without hydration. The model then reconstructed continuation from local workspace state.

## Architecture conclusion

The failure is not a malformed E3 IR and not a failed E2→E3 handoff. The published E3 child had already passed parent fencing and child-generation verification.

The invalid assumption is broader:

> IDE workspace membership must not decide whether a fresh executor receives Canonical IR.

Supporting more workspace shapes only moves the boundary. A fresh executor can be opened in any workspace while the user's active AgentOS task remains elsewhere.

Correction:

- introduce `agentos.active-continuation/v1` as a ONE/runtime pointer containing only `project_id + index_id + ir_id`;
- keep the referenced `agentos.ir/v1` as the sole durable working-state representation;
- PreInvocation reads the ONE selector first and revalidates the referenced canonical generation;
- `workspacePaths` have zero continuation-selection authority;
- stale/missing selector or generation mismatch fails closed;
- installer regression probe deliberately uses `/home/ubuntu/acas` and must still hydrate the selected Core IR.

This evidence does not mark E3 PASS. A new fresh built-in Codex regression is required after the active-selector runtime is installed/reloaded.
