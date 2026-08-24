# Canonical AgentOS Evolution and Multi-Session Workstreams

## Decision
AgentOS evolution MUST NOT be bound to one chat session. Sessions/models/runtimes are replaceable executors. At the same time, multiple sessions MUST NOT independently define canonical AgentOS reality.

The governing model is:

> **Single Canonical Evolution, Multiple Concurrent Workstreams, Governed Integration.**

## Identities
The system distinguishes four identities:

1. **Project** — durable AgentOS project identity.
2. **Canonical Evolution** — the unique accepted architecture/state/history for that project.
3. **Workstream / Goal Lineage** — an independently resumable unit of evolution such as onboarding, benchmarking, continuity, governance, or deployment.
4. **Executor Attachment** — a disposable session/model/runtime currently working a lineage.

A session is never the identity of the work. Session death must not imply workstream death.

## Continuation routing
Continuation must resolve to exactly one Goal lineage before effectful execution.

Resolution order:

1. If the current executor has an attached live Goal lineage, `continue` means continue that lineage.
2. If the user explicitly names a Goal/workstream, resolve that lineage.
3. If a fresh executor has no attachment and exactly one resumable unowned lineage exists, it may attach to that lineage after live reconciliation.
4. If multiple candidate lineages exist, do not guess merely from recency. Use the canonical planner only when it can deterministically select a highest-value READY, unowned lineage under policy; otherwise request user selection.
5. If the selected lineage is leased by another executor, do not silently create a competing writer. Observe, attach read-only, wait, or perform governed takeover according to lease policy.

**Invariant:** ambiguous continuation MUST NOT mutate state.

## Parallel work
Parallel cognition is allowed and desirable. Parallel canonicalization is not.

Each workstream owns a proposal/delta lineage. Workstreams may inspect canonical state and produce content-addressed proposals, experiments, receipts, documentation, and failure knowledge. Integration into Canonical Evolution is a separate governed operation.

Recommended isolation for code-changing workstreams is a dedicated branch/worktree or equivalent content-addressed delta. Two workstreams should not share an unconstrained mutable working HEAD.

## Conflict and integration
Concurrent work can conflict semantically even when Git reports no textual conflict. Integration therefore checks:

- base canonical revision / observed HEAD;
- affected resources and contracts;
- architecture/governance invariants;
- tests and receipts;
- superseded decisions;
- authority for merge-equivalent effects.

Conflicting proposals are not resolved by latest-write-wins. They are reconciled, tested, arbitrated, or rejected. Rejected/failed approaches remain durable Failure Knowledge with evidence and retry conditions.

## Canonical planner
A planner may assign a fresh executor without user intervention only when all are true:

- the project has a unique canonical state;
- candidate workstreams and dependencies are explicit;
- a deterministic priority/critical-path policy identifies a unique READY workstream;
- the workstream is unowned or its lease is safely claimable;
- the next action is within existing authority;
- live state has been reconciled.

Priority expresses intent; it does not grant authority.

## Required durable workstream record
A workstream should persist at least:

- `workstream_id`;
- `goal_id` and objective;
- parent/canonical revision;
- closure invariants;
- status (`READY`, `RUNNING`, `WAITING`, `BLOCKED`, `INTEGRATION_READY`, `DONE`, `ABANDONED`);
- current executor attachment and lease/fencing token, if any;
- resource scope / affected contracts;
- latest verified checkpoint and receipts;
- next closure gap;
- dependencies;
- proposal/delta refs;
- failure knowledge refs;
- integration disposition.

## Fresh-session examples
### Existing attached session
`continue` -> continue its attached Goal lineage.

### Fresh session, one resumable workstream
`continue AgentOS` -> reconcile canonical state -> attach unique resumable lineage -> execute.

### Fresh session, multiple workstreams
`continue AgentOS` -> inspect workstream graph. If planner deterministically finds a unique highest-value READY unowned lineage, claim it; otherwise present the ambiguity without mutation.

### Explicit takeover
`continue onboarding` while onboarding is leased -> do not compete. Require lease expiry, explicit takeover authority, or coordination with current executor.

## Acceptance criteria
The design is considered operational when tests demonstrate:

1. two fresh sessions can recover two different workstreams without confusing their Goal lineages;
2. bare `continue` in each attached session resumes its own lineage;
3. a third fresh session with multiple ambiguous candidates performs no mutation;
4. deterministic planner assignment only selects READY unowned work;
5. two executors cannot concurrently acquire effectful ownership of the same lineage;
6. stale executors are fenced after takeover/lease expiry;
7. concurrent non-conflicting proposals can be integrated after revalidation;
8. semantic conflicts are detected before canonicalization;
9. failed/rejected work remains queryable and is not unknowingly repeated;
10. replacing every chat session leaves Canonical Evolution and all active workstreams recoverable.

## Governing principle
**AgentOS may evolve through many minds at once, but it has one governed memory of what it has become.**
