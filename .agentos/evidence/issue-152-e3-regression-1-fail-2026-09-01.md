# Issue #152 — E3 regression #1 failure evidence

Date: 2026-09-01

## Test

A completely fresh built-in Antigravity Codex conversation was opened after the guarded E2 -> E3 Canonical IR advancement. The only user message was `繼續`.

Expected Canonical IR provenance:

- `source=ONE_PREINVOCATION_IR`
- `project=agentos-core`
- `index_id=idx-core-152-e3-1`
- `ir_id=ir-core-152-e3-1`
- executor identity bound as Antigravity Codex when the hook model name proves it

## Observed first response

The Codex executor instead continued local `if-tv-station` work, reporting architecture/path cleanup, environment fallback fixes, build/lint results, and files under:

`/home/ubuntu/agentmanager/workspace/if-tv-station/...`

It did not report ONE Canonical IR provenance or the E3 `agentos-core` goal.

## Verdict

`E3_REGRESSION_1=FAIL`

This response is not evidence of ONE continuity. It is local workspace continuation.

## Root cause

The Antigravity PreInvocation hook used an exact basename gate:

`Path(workspace).name == "agentmanager"`

When Antigravity supplied the nested active workspace:

`/home/ubuntu/agentmanager/workspace/if-tv-station`

the basename was `if-tv-station`, so the hook returned silently before resolving/injecting Canonical IR.

The bug was in the workspace gate, not the E3 IR child generation. The E3 head remained `idx-core-152-e3-1 / ir-core-152-e3-1`.

## Correction

The gate now accepts the canonical `/home/ubuntu/agentmanager` root or any real path descendant, while still resolving exactly `agentos-core`. Descendant names remain context only and never select continuation state. Prefix lookalikes such as `/home/ubuntu/agentmanager-old` remain rejected.

Regression coverage was added for both nested descendants and prefix lookalikes.
