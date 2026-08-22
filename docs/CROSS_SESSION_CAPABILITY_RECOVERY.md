# Cross-session capability recovery

## Goal
A new chat/model/runtime must be able to resume an AgentOS goal without depending on the original conversation's accumulated context or its accidental execution behavior.

## Finding from the 2026-08 experiment
The mature long-horizon behavior was not caused by one magic primitive. Historical counterexamples reject `/goal`, `continue`, GitHub, GitHub Actions, and Oracle as individually sufficient. The strongest observed transition occurred when these conditions coexisted:

1. a stable goal;
2. termination semantics broader than a substep;
3. accumulated context or equivalent Canonical IR;
4. reliable multi-tool action capability;
5. machine-readable receipts after actions;
6. persistent external state;
7. authority for reversible low-risk progress;
8. an observe -> act -> verify -> derive-next loop.

The core behavioral invariant is:

> Answerability is not completion. Do not stop because a response can be written; stop because the goal is closed, blocked, authority-limited, or interrupted.

## Capability layers that must be recovered
Cross-session recovery is not only memory restoration. A replacement executor must reconstruct five layers:

- **Cognition**: goal-relevant semantic context and decisions.
- **State**: canonical repository/ref/HEAD, PR topology, task state, runtime state, receipts and unresolved work.
- **Disposition**: explicit continue/final/block semantics.
- **Governance**: authority, protected effects, leases, stale-executor fencing and approval boundaries.
- **Failure knowledge**: known bad paths and their evidence so a replacement executor does not repeat them.

A sixth operational layer, **Execution World**, binds the above to live capabilities: tools, Actions, nodes, provider routes and current health. It must be reconciled from authoritative reads; it must never be trusted solely from a handoff packet.

## Fresh-session bootstrap protocol
A fresh executor should perform this sequence before effectful work:

1. Load the latest Canonical IR / execution handoff.
2. Read the execution-disposition contract.
3. Re-fetch authoritative mutable coordinates (repo, working ref, HEAD, PR/base, task lease, runtime/provider health, latest receipts).
4. Reconcile stale handoff facts against live state. Live authoritative state wins.
5. Reconstruct goal closure invariants and the highest-value remaining gap.
6. Verify capability and authority for the next effect.
7. Execute the smallest progressing action.
8. Require a receipt for every mutation or asynchronous validation.
9. Treat the receipt as the next observation and derive the next action.
10. Evaluate disposition. If CONTINUE, repeat without yielding merely because a milestone was reached.
11. Checkpoint after material state changes so conversation death does not imply goal death.

## Explicit stop conditions
A replacement executor may yield/finalize only when one of these is true:

- goal closure is verified;
- new human authority is required;
- required information can only be supplied by the human;
- governance/risk policy requires explicit approval;
- an external dependency is pending and no independent safe progress exists;
- the user interrupts or supersedes the goal;
- a terminal failure is established with evidence.

A commit, passing unit test, CI receipt, completed subproblem, or answerable progress report is not by itself a stop condition.

## Session exhaustion protocol
Conversation capacity is a cache/resource limit, not a project lifecycle event. When context pressure is high:

1. stop expanding the dying conversation with large development tasks;
2. emit/update a compact execution handoff and trace delta;
3. externalize it immediately to durable state;
4. attach a fresh executor;
5. perform live reconciliation;
6. resume from the next closure gap.

If the old conversation can still execute but cannot reliably retain its newest turns, treat it as a **frozen reference runtime**: use it for bounded behavioral archaeology and export every useful result immediately. Do not rely on it as the canonical state store.

## Known failure knowledge
### F-SESSION-01 — semantic handoff without execution disposition
A new conversation recovered project knowledge but repeatedly finalized after commits/substeps. Cause: knowing the goal and repo state did not reproduce the old session's termination behavior.

**Rule:** disposition is first-class durable state and must be executable, not prompt advice only.

### F-COORD-01 — incomplete execution coordinates
A replacement session reasoned from stale/partial branch topology and confused working, integration and default refs.

**Rule:** persist repository + canonical ref + observed HEAD + PR/base + workflow topology, then live-reconcile before effects.

### F-REF-01 — merge-equivalent ref movement
Moving an integration/base ref to an open PR head can absorb the PR without invoking a merge API.

**Rule:** govern semantic effects, not API names. Merge-equivalent protected ref movement requires explicit human approval.

### F-ACTIONS-01 — workflow existence != execution attachment
A workflow file in a branch does not prove that its trigger topology can execute or that an Actions route is attached.

**Rule:** require a current execution receipt before claiming the route is active.

### F-SESSION-02 — conversation too long / transient newest turn
The old reference conversation became unreliable at retaining its newest interaction even though older context and procedural behavior remained usable.

**Rule:** conversation death or rollback must not imply Goal death; checkpoint outside the conversation.

## What is and is not recovered today
Repository-side semantics now encode portable goal disposition and durable GoalController state. This makes the desired behavior enforceable by AgentOS executors. It does **not** prove that every fresh ChatGPT conversation will naturally exhibit the same unusually long single-turn tool loop. Host/model turn persistence remains an external property and must not be a correctness dependency.

Therefore the target architecture is stronger than reproducing a lucky chat session: even if a chat yields early, a persistent AgentOS executor must preserve and continue the goal, and the next attached model must reconstruct the same execution world and disposition.

## Acceptance tests for 'complete recovery'
Recovery is complete only when a fresh session/model, given durable state rather than the original transcript, can demonstrate all of the following:

1. identifies the correct active goal without user restatement;
2. reconstructs and live-verifies execution coordinates;
3. does not repeat recorded failed paths;
4. continues after a successful substep when a material closure gap remains;
5. respects authority boundaries and never self-expands permission;
6. uses receipts to update belief and next action;
7. survives interruption/session replacement without duplicate or lost work;
8. can resume from a second fresh session with the same semantics;
9. completes or stops only at a defined hard boundary;
10. passes an ablation test showing the behavior comes from portable AgentOS state/runtime semantics rather than dependence on one historical conversation.

## Recommended validation matrix
Run controlled fresh-session comparisons for: natural-language goal vs `/goal`; Actions feedback on/off; long context vs Canonical IR only; persistent state on/off; repeated tool-loop induction vs no induction; and reversible write authority vs per-write confirmation. Measure actions per user turn, premature-final rate, goal completion, duplicate work, recovery after failure, and authority violations.

## Design principle
A conversation is a disposable execution surface. Canonical Goal + State + Disposition + Governance + Failure Knowledge are the durable system. The final objective is not to preserve a particular 'master' conversation; it is to make the master's useful operating regime reproducible, testable, governed and replaceable.
