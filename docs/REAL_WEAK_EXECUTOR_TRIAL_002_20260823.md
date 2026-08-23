# Real Weak Executor Preservation Trial 002

Date: 2026-08-23
Status: OBSERVED_FAIL_WITH_ENFORCEMENT_GAP
Executor condition: fresh ChatGPT UI low-effort / Instant condition selected by the human experimenter.

## Blind goal

`/goal 繼續 AgentOS 研究，完成下一個能驗證 Master Experience Floor 的真實弱 executor 實驗，取得證據並更新研究結果`

No human continuation pulse was supplied before preserving the first response.

## Observation

The executor successfully recovered substantial semantic research context and identified `alston-personal/agentmanager`. It observed that `feature/distributed-agentos-runtime` existed, but foregrounded the repository default `main` at commit `738ccd2...` and concluded that the Master Experience Floor experiment result had not yet been written into the repository.

At the time of the trial, that conclusion was false for the active working line. The feature branch already contained the Master Experience Floor specification, deterministic forced-yield supervisor proof, Trial 001, canonical anchor resolver, host redispatch contract, and their validation receipts.

The executor therefore demonstrated project/semantic recovery without authoritative execution-state recovery.

## Refined failure decomposition

### F1a — Canonical Anchor Resolver implementation

PASS at repository/component level. AgentOS contains a fail-closed resolver that rejects silently substituting `main` for the goal's `canonical_ref` and requires explicit reconciliation on HEAD drift.

### F1b — Canonical Anchor Resolver enforcement on real executor entry path

FAIL. The real executor was able to enter planning by independently browsing/interpreting repository state rather than receiving a mandatory resolved canonical anchor from AgentOS first.

This establishes that merely implementing a correct resolver is insufficient. The resolver must be an entry-gate invariant, not an optional library available to a capable executor.

## Architectural correction

The required path is:

`user goal -> AgentOS entry gate -> canonical goal/project lookup -> Canonical Anchor Resolver -> authoritative ref/HEAD + receipts -> compiled executor context -> executor`

The unsafe path is:

`user goal -> executor -> repository browsing -> executor guesses authoritative branch/state`

Weak executors must not be expected to discover or remember the canonicality protocol themselves.

## Master Experience Floor implication

A robust floor cannot be built only by giving every executor access to the same tools or documents. AgentOS must **force heterogeneous executors through the same critical cognitive control points** before delegating model-native reasoning.

This adds a fifth system requirement to the emerging floor model:

1. Cognitive State Recovery
2. Canonical State Anchoring
3. **Mandatory Entry-Gate Enforcement**
4. Goal-level Supervision
5. Host Redispatch

The distinction is important: implementation existence is not behavioral enforcement.

## Trial status

- semantic/project recovery: PASS
- branch existence discovery: PASS
- authoritative canonical working-state selection: FAIL
- canonical resolver component existence: PASS
- canonical resolver enforcement on real executor path: FAIL
- human continuation pulses before preserved first response: 0
- end-to-end Master Capability Preservation: FAIL

The preserved screenshot does not by itself establish the complete final disposition of the first response beyond the visible portion; therefore the F2 premature-finalization classification should not be upgraded from this trial alone without the remaining first-response output or another authoritative observation.

## Next discriminating target

Do not add more branch-selection heuristics to prompts. Implement/verify an AgentOS resume/entry envelope that supplies canonical execution coordinates as trusted input before executor planning begins. Then repeat the same blind Instant trial.

If a fresh weak executor receives the authoritative feature ref/HEAD but still reverts to `main`, the adapter/context binding is defective. If it uses the correct anchor but stops after deriving a safe next action, the remaining degradation is isolated to goal supervision/host redispatch.
