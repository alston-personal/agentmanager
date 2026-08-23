# Real Weak Executor Preservation Trial 001

Date: 2026-08-23
Status: OBSERVED_FAIL_WITH_DIAGNOSIS
Executor condition: ChatGPT UI low-effort / Instant condition, selected by the human experimenter.

## Goal

Test whether a fresh real weak executor can continue AgentOS research toward Master Experience Floor validation without requiring a human continuation pulse.

Blind prompt:

`/goal 繼續 AgentOS 研究，完成下一個能驗證 Master Experience Floor 的真實弱 executor 實驗，取得證據並更新研究結果`

The human intentionally supplied no follow-up `繼續` or `?` before preserving the first response.

## Preserved observation

The executor did several useful things in its first response:

1. interpreted the prompt as continuation of existing AgentOS research rather than a new generic question;
2. attempted repository/state reconstruction;
3. distinguished already-completed B1/B3 efficiency evidence from the Master Experience Floor question;
4. identified a further experiment as the next research gap.

However, it also stated that the repository did not contain an implemented Master Experience Floor weak-executor benchmark and anchored its repository view around an old `main` commit (`738ccd2...`). At the time of the trial, the canonical working line already contained `runtime_core/execution_supervisor.py`, `tests/test_execution_supervisor.py`, and `docs/MASTER_EXPERIENCE_FLOOR.md`, including the deterministic 24-action forced-yield proof.

The executor then emitted a normal final response instead of executing the derived next closure step. Continuing would therefore have required another human message.

## Failure classification

### F1 — Canonical State Anchoring Failure

The executor recovered the project identity but selected/relied on stale or non-canonical repository state. It therefore failed to observe work already present on the active working line.

This is distinct from total memory failure: the executor knew the research domain and substantial historical results, but did not resolve the authoritative active ref/HEAD before planning.

### F2 — Premature Finalization / Human Clock Reintroduction

The executor had a derivable next action and no observed new-authority boundary, but converted that next action into prose and finalized. Thus answerability became the stopping condition instead of verified goal closure/block/authority.

For this observed host-integrated run, HCR > 0 would be required to make further progress.

## Comparison with deterministic weak-executor proof

Synthetic forced-yield executor:
- one action per slice;
- 23 premature yields absorbed;
- 23 automatic redispatches;
- HCR = 0;
- 24 material actions reach DONE.

Real Instant host trial:
- useful state reconstruction occurred;
- canonical working HEAD was not resolved correctly;
- next gap was derived but not executed;
- first assistant final returned control to the human;
- end-to-end Master Capability Preservation: FAIL.

This narrows the remaining gap. The supervisor algorithm can absorb executor yielding when it owns the continuation clock, but the current ChatGPT host/session path has not been demonstrated to hand a real assistant final back to AgentOS for transparent redispatch.

## Architectural consequence

Master Experience Floor requires all four layers:

1. **Cognitive State Recovery** — recover goal, evidence, decisions, failures, authority and research state.
2. **Canonical State Anchoring** — resolve active project, canonical working ref and verified current HEAD before deriving actions.
3. **Goal-level Supervision** — treat executor final as a slice receipt and independently evaluate parent-goal closure.
4. **Host Redispatch** — if the parent goal remains active, invoke the executor again without a human continuation pulse.

A failure in any layer can make a knowledgeable executor still feel weaker to the user.

## Next discriminating work

### A. Fix F1 inside AgentOS

Introduce a Canonical Anchor Resolver contract. A resuming executor must not infer `main` as the active state merely because it is the repository default. It should resolve, in order:

- active goal/project identity;
- canonical working ref;
- authoritative current HEAD for that ref;
- latest valid receipts tied to that HEAD;
- only then reconstruct `next_action`.

A stale anchor must be detectable and must not silently become execution state.

### B. Isolate F2 as host-boundary integration

After F1 is deterministic, repeat the real weak-executor trial. If the executor still finalizes after a safe incomplete slice, the remaining failure is host redispatch/control rather than state recovery.

Success criterion for the end-to-end floor remains: HCR=0, AVR=0, valid terminal stop, with executor weakness allowed to increase internal slice count/latency but not human scheduling burden.

## Claim boundary

This trial does **not** prove that all Instant-mode sessions behave identically, nor that the UI reasoning-effort selector alone caused the failures. It is one preserved real-executor observation consistent with the broader hypothesis that weaker execution regimes increase premature-finalization and state-anchoring risk.

It does establish a concrete failure mode that the AgentOS architecture must absorb rather than delegate back to the human.
