# Master Experience Floor

Status: normative design requirement with deterministic weak-executor proof harness.

## Requirement

AgentOS must preserve a **master-like user experience floor** even when the attached executor is weak, low-effort, short-horizon, or otherwise prone to premature finalization.

The user must not need to understand which executor, model, reasoning-effort tier, IDE, or web-agent is currently active in order to obtain coherent goal-level execution. Switching executors may change latency, cost, or the number of internal slices, but it must not force the user back into manual `continue` / `?` clocking for ordinary authorized work.

> **Executor quality may raise the ceiling; AgentOS must defend the floor.**

## Non-goal

This does not require AgentOS to make every weak model reason identically to the strongest model. A weaker executor may need more slices, more explicit scaffolding, more validation, or more redispatch. The invariant is the observable interaction contract: the system continues toward verified goal closure without requiring the human to act as the scheduler.

## Separation of responsibilities

### Executor-native capability

Examples:
- reasoning depth;
- planning horizon;
- tool-use persistence;
- self-critique and bounded failure repair;
- resistance to answerability-triggered finalization;
- context capacity.

These properties may vary across model/provider/UI reasoning-effort settings and must not be assumed portable.

### AgentOS-preserved capability

AgentOS owns:
- canonical goal and closure invariants;
- current semantic state and provenance;
- execution disposition;
- receipt-driven replanning;
- failure knowledge;
- governance/authority boundaries;
- persistent scheduling/redispatch when an executor yields prematurely;
- executor adaptation policy.

## Capability normalization loop

For every attached executor:

1. **Observe/calibrate.** Estimate the executor's effective planning horizon, premature-finalization risk, receipt follow-through, bounded failure repair, context tolerance, and tool persistence from bounded probes and live receipts. Do not infer a privileged UI label if it is not available through an authoritative interface.
2. **Compile an execution policy.** Select autonomy width, slice size, exemplar/scaffold strength, verification density, and redispatch behavior appropriate to the observed executor.
3. **Run a slice.** Give the executor only the authority already granted by governance.
4. **Treat model final as a receipt, not goal completion.** The GoalController independently evaluates the parent goal.
5. **Redispatch on premature yield.** If a material closure gap remains and the next action is safe, derivable, and authorized, keep the goal ACTIVE and dispatch another slice without asking the human to type `continue`.
6. **Escalate only on real boundaries.** Human interaction is required for new authority, information unavailable to the system, governance/risk decisions, explicit interruption, or a genuinely terminal dependency.

## Policy classes

These are internal adaptation classes, not user-visible model rankings.

### Autonomous-long-horizon
Use when the executor demonstrates low PFR/HCR and sustained receipt-driven execution. Give wide slices and allow the executor to run toward closure.

### Scaffolded-long-horizon
Use when the executor can reason well but tends to yield early. Inject the execution-disposition contract, task-neutral master exemplars, explicit parent-goal checkpointing, and tighter receipt requirements.

### Supervised-sliced
Use when the executor is short-horizon or high-PFR. The external GoalController owns continuation. Give bounded atomic slices, verify receipts after each slice, preserve failure knowledge externally, and redispatch automatically until closure/boundary.

A low-effort/instant executor should therefore degrade primarily in latency or slice count, **not in user-visible continuity**.

## User-experience invariant

For ordinary authorized work, replacing a strong executor with a weaker one must not cause:

- a new need for continuation-only human pulses;
- loss of the parent goal;
- loss of known failures or receipts;
- repeated already-completed work;
- a silent downgrade from goal execution to advice-only answers;
- authority drift.

The system may expose that a task is taking longer or is running in more slices, but it should still feel like one competent agent is carrying the work forward.

## Evaluation

Master Experience Reproduction and Master Capability Preservation are distinct claims.

### Master Experience Reproduction
The executor itself meets the long-horizon threshold (for example PFR=0, HCR=0, RFR=1, SCD>=20, valid terminal stop).

### Master Capability Preservation
The end-to-end AgentOS system meets the user-experience floor even when the executor itself does not. A deliberate weak-executor trial should force the executor to yield after every bounded action. The external controller must still reach verified closure or a real authority/hard boundary with **HCR=0** and **AVR=0**.

The weak-executor trial is critical: if the user must type `continue`, AgentOS has not preserved the master experience floor even if canonical memory recovery is perfect.

## Deterministic implementation receipt

The first executable floor mechanism is now implemented in `runtime_core/execution_supervisor.py` and tested by `tests/test_execution_supervisor.py`.

The synthetic executor is deliberately pathological: it performs exactly one material action and then finalizes on every slice. The supervisor treats that model final as a slice receipt, re-evaluates the durable `GoalControllerState`, and redispatches whenever the parent goal remains active.

The frozen 24-action test establishes the following end-to-end system behavior:

- material actions: `24`;
- executor finalizations before closure: `23`;
- premature yields absorbed by the supervisor: `23`;
- automatic redispatches: `23`;
- human continuation pulses: `0`;
- final state: verified `DONE`.

The same supervisor tests preserve real boundaries: verified closure completes, `BLOCKED_HUMAN_AUTHORITY` yields without crossing the boundary, and `WAITING_EXTERNAL` waits only when no independent safe progress exists.

Validation receipt: Distributed AgentOS CI run `32619284750` completed successfully with **355 passed in 7.50s** on PR merge SHA `8d2eeb2f0582a92ab98b72a56c0158b97dd00d01` for branch head `28a1f006b123de86f8a5917b7b5d35aeb5103564`.

This is strong evidence for **system robustness under forced executor yielding**, not yet proof that a real ChatGPT "Instant" executor can be externally intercepted and transparently redispatched inside the current host UI. That host-boundary integration remains the next discriminating test.

## Design consequence

Cross-model continuity is not complete when a replacement executor merely knows what the previous executor knew. It is complete only when AgentOS also adapts execution so that weaker reasoning regimes do not collapse the user experience.

The target is therefore:

> **portable cognitive state + portable execution semantics + executor adaptation + persistent supervision = master-like experience floor across heterogeneous executors.**
