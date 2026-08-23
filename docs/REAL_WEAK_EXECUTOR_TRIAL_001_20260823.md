# Real Weak Executor Preservation Trial 001

Date: 2026-08-23
Status: OBSERVED_FAIL_WITH_F1_REPAIRED_F2_ISOLATED
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

## F1 repair receipt — deterministic canonical anchoring

`runtime_core/canonical_anchor.py` now resolves resumed execution from durable GoalController coordinates instead of repository defaults. It fails closed on repository mismatch, canonical-ref mismatch, missing HEAD, or HEAD drift that has not been explicitly reconciled. In particular, a repository default such as `main` cannot silently replace the active working ref.

Tests in `tests/test_canonical_anchor.py` cover exact resolution, rejection of default-main substitution, explicit HEAD reconciliation, and repository mismatch. Repair commits:

- implementation: `4e6b118bf07a5fcdc474fd6478ef364b9009b44c`
- tests: `d8997f112333267baa2db856b43b60ab576c5f20`

Distributed AgentOS CI run `32621231359` completed successfully with **359 passed**. F1 is therefore repaired at the deterministic AgentOS contract level. A new real executor trial is still required to show that a fresh host actually consumes this contract correctly.

## F2 isolation — host redispatch contract

`runtime_core/host_redispatch.py` now compiles the Goal-level Supervisor decision into an explicit host-level decision. It separates four cases that must never be conflated:

- an authorized host with proactive wake support -> `DISPATCH`;
- a host that cannot proactively wake the target -> `HOST_BOUNDARY`, with the parent goal remaining active;
- a wake-capable target without authorization -> `HOST_BOUNDARY` before the effect;
- verified closure -> `COMPLETE`, with no host invocation.

For a ChatGPT-style UI session that cannot presently be proactively awakened, the contract records `HOST_BOUNDARY` and `human_clock_required=true`; it does **not** relabel the parent goal as complete and does **not** misdiagnose the failure as weak cognition.

Tests in `tests/test_host_redispatch.py` cover proactive dispatch, current chat-UI no-wake behavior, unauthorized relay targets, missing durable targets, and verified completion. Commits:

- implementation: `d0904239915dadf690ba36b22c0d5db372e89b05`
- tests: `18c870e5ab66d9c164d30616aae27fb385d9c041`

Distributed AgentOS CI run `32623765976` completed successfully with **364 passed in 6.21s**. Artifact ID `9489118974`; artifact ZIP SHA-256 `9840374caefc8c4b5901f1a3048322bdd3706b5b727eb5f1e3490dc9204c3a8c`.

This does not mean the current ChatGPT UI can already be transparently redispatched. It means the remaining F2 gap is now explicitly represented as a host-control capability boundary rather than being hidden inside executor behavior.

## Next discriminating work

The next real trial should use a fresh low-effort/Instant executor after the canonical-anchor repair. Its first task is to demonstrate correct working-ref/HEAD recovery. If it still finalizes while a safe material closure gap remains, the first divergence can now be cleanly classified as host redispatch/control rather than stale-state recovery.

End-to-end success criterion remains: HCR=0, AVR=0, valid terminal stop, with executor weakness allowed to increase internal slice count/latency but not human scheduling burden.

If the host itself provides no authorized proactive wake interface, that condition is a genuine `HOST_BOUNDARY`; solving it requires an authorized platform/browser/desktop relay or another host that exposes redispatch. AgentOS must preserve the active goal across that boundary and resume from the canonical anchor when a wake path becomes available.

## Claim boundary

This trial does **not** prove that all Instant-mode sessions behave identically, nor that the UI reasoning-effort selector alone caused the failures. It is one preserved real-executor observation consistent with the broader hypothesis that weaker execution regimes increase premature-finalization and state-anchoring risk.

It establishes a concrete failure mode that the AgentOS architecture must absorb rather than delegate back to the human, and it now has deterministic repairs/contracts for both the F1 state-anchor path and the F2 host-boundary classification.
