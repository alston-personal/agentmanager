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
