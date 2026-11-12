# Version Convergence Signal (AgentOS #1682)

This is the **source-only contract**, not yet a running ONE/Supervisor fanout.

After a protected-main push, the existing GitHub Actions transport can produce an
immutable-per-SHA `agentos.version-convergence-event/v1` JSON artifact. It
contains the previous/target SHA, affected source domains, and an idempotent ID.
No authority is granted. GitHub CI cannot attest runtime deployment or a
received signal; at this stage the artifact's status is CREATED_NOT_DELIVERED.

The existing ONE Controller / Runner Window should consume this source event
via its authenticated capability routing only after independent verification
of GitHub main HEAD lineage, trusted repository, event generation and delivery
authorization. Each registered affected Executor, including offline peers at
their next heartbeat, then reports a separately verified
`agentos.version-convergence-ack/v1` receipt.

Acknowledgements must retain:
- `NOTIFIED`: event seen, no source or runtime conclusion;
- `SOURCE_CONVERGED`: independent clean/safely-reconciled worktree confirmation;
- `RUNTIME_DEPLOYED`: component-specific installed-source proof, not Git fetch;
- `TASK_RESUMED`: updated task context; and
- `BLOCKED`: conflict, dirty worktree, offline, or permission blocker.

The pure `validate_ack` function verifies only schema and *claimed*
consistency. ONE must authenticate the executor/node/realm and independently
verify source/runtime evidence before persisting any state upgrade. A newer
global main SHA does NOT require immediate rolling restart of unrelated
components. Never reset dirty worktrees, auto-merge unapproved PRs, or
interpret notifying GPT Web as installing source code.

The actual fanout/ack subscriber, offline reconcile, stale-write barrier, and
durable completion ledger remain **NOT IMPLEMENTED**. Do not claim all
Executors have updated. Acceptance requires one real trusted main merge ->
event -> ONE delivery -> actual online/offline/dirty-source acknowledgements
with exact SHA evidence and without loss of ongoing tasks.

Canonical work: https://github.com/alston-personal/agentmanager/issues/1682


## ONE durable announcement journal: push + pull (design requirement, 2026-11-12)

The user requires ONE to broadcast important state changes to all relevant registered Executors, while also making announcements discoverable by newly joined or previously offline units. This must reuse ONE, Supervisor, existing identity/registry/capability routing, rather than introduce a second controller or canonical IR store.

### Publication and delivery

1. After authoritative protected-main or remote-first Canonical IR commit confirmation, ONE writes one idempotent append-only announcement BEFORE attempting delivery. A failed remote IR push is not a published canonical change.
2. Push fans out to a snapshot of all currently registered affected units with persistent attempts and per-unit ACK records. Offline or quota-exhausted units remain PENDING, never implicitly acknowledged.
3. Pull provides an authenticated, scoped, cursor-based journal reader for any authorized existing or new participant. Participants query on bootstrap, resume, heartbeat and before state-mutating work. Push accelerates delivery; pull and mandatory freshness checks guarantee recoverability.
4. New units not present in the original push roster must still discover current applicable mandatory announcements. Expired cursors require a canonical baseline snapshot, not silent skipping. Informational history may expire; mandatory current requirements remain queryable.
5. Publication and ACK are independent: announced means journal-committed; delivered means observed by a unit; fetched/validated means remote version verified; applied means confirmed effective before next work. Source-convergence, deployed-runtime and resumed-task states in this PR remain distinct.

### Minimum record and permission contract

Each event contains immutable event_id, increasing cursor/sequence, timestamp, scope (global, realm, project, capability), kind (source, canonical-ir, governance, capability, deprecation, incident), severity, affected capability/schema bounds, summary, authoritative remote ref and SHA or IR generation, predecessor, required action (inform, refresh-before-mutation, block-until-updated), supersession/expiry and evidence links. Redact secrets and private IR contents. Global discoverability never grants cross-realm private data access or execution rights.

ONE must authenticate the actual receiver identity and independently attest source/IR/runtime versions. Self-asserted ACK is insufficient. Deliver at least once, deduplicate by event ID, retain pending obligations through restart. Do not assume network exactly-once delivery. Mutable tasks fail closed when mandatory changes cannot be reconciled; safe read-only diagnosis remains available.

### Design expansion impact sweep (mandatory before rollout)

When feature scope, authority or expected recipient types exceed prior design assumptions, inspect and classify dependent components as UNCHANGED, MIGRATE, REQUIRES_PROOF, or NOT_APPLICABLE with source or runtime evidence: Canonical IR publisher/validation and remote storage; active continuation and resolver; Node/Executor registration/bootstraps; Gemini/Antigravity, Claude, Codex and GPT-Web adapters; Controller dispatch; Supervisor/replay; queued worker freshness; offline onboarding; announcement retention and ACK ledger; permissions/realm isolation; operator web visibility; deployments, rollback, CI and actual receipts. Reuse the existing owner and backlog; no parallel notification authority or automatic scope diversion.

### Required real acceptance

Verify a genuine authoritative remote commit and ONE journal receipt, fanout roster, separate per-Executor delivery/validated/applied ACKs, offline replay, new-unit bootstrap/pull after original broadcast, cursor gap snapshot recovery, stale concurrent IR write rejection and protected realm isolation. Web GPT, Oracle Gemini and another Executor must read the same IR generation and produce correlated receipts. Completion must not be claimed from GitHub Issue comments or green CI alone.

Status: this PR currently creates only a protected-main source event artifact and validates claimed ACK structure. No ONE journal, push/pull transport, Git-remote Canonical IR authority migration, durable ACK delivery or live Executor receipts are yet demonstrated.
