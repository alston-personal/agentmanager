# AgentOS Branch Safe Synchronization Checkpoint — decision contract v1

Status: **candidate decision policy, not wired to Supervisor dispatch, no live Oracle Receipt**.
Related: #1682, #2297, #2339.

## Goal

Concurrent Executors may work from different commits. Git divergence (ahead and
behind at the same time) is normal during parallel development. The defect to
prevent is a stale source silently replacing newer interfaces or making risky
writes without review. All code Executors should ultimately use the *same*
trusted policy owner at dispatch and at safe checkpoints; no per-model policy
forks.

## Existing controls, retained

- `scripts/branch_resume_guard.py`: fail-closed remote-main ancestry check.
- `agentos_node/branch_resume_host_probe.py`: trusted worktree/remote/status
  verification and immediate fetch on code job claim/resume.
- `Branch Convergence Path Audit`: PR stale source detection and changed-path
  classification.
- `Branch Convergence Merge Diagnostic`: isolated diagnostic, no remote push.

The new `scripts/branch_sync_policy.py` **does not override** those gates,
authorize deployments, install a daemon, or change the ONE active IR.

## Proposed common checkpoint contract

The Supervisor (trusted observer) supplies typed evidence:
- `mainline_current`: verified graph ancestry from the *actual* registered
  worktree and newly fetched main, or `None` when unknown.
- `checkpoint_saved`: in-flight edits have a durable recovery point.
- `lease_fenced`: current Executor/branch lease and generation verified by its
  authoritative owner; a simple boolean report from a model is not proof.
- `worktree_clean`: no uncommitted/unknown edits in the worktree selected for
  integration; a dirty working branch must never be reset to make the check pass.
- `overlapping_changes`: `none`, `shared`, or `unknown`, based on verified
  file/API/dependency analysis, *not* only commit count or paths.
- `governance_or_security_change`: confirmed relevant policy/authorization
  update, not any arbitrary change.
- `hours_since_main_sync`: age from authoritative timestamps, if known.
- `kind`: code versus read-only inventory.

## Decision table

| Observation | Decision | Write discipline |
|---|---|---|
| No verified remote graph | EVIDENCE_REQUIRED | Never claim safe to merge |
| Main is already ancestor | CURRENT | Continue current code task |
| State not saved/clean/lease-fenced | WAIT_FOR_SAFE_CHECKPOINT | Keep working state safe; relevant risky writes may pause |
| Uncertain dependency overlap | REVIEW_DEPENDENCIES | Resolve unknown before auto-sync |
| Confirmed shared API/file overlap or relevant governance/security change | RECONCILE_REQUIRED | Block affected new writes until isolated reconciliation |
| No overlap, safe checkpoint | SAFE_SYNC_CANDIDATE | May simulate isolated merge and run CI; no automatic promotion |
| Stale for >=72 hours | ESCALATE_STALE_BRANCH | Supervisor must record ownership, justification and reconciliation plan |
| Read-only task | READ_ONLY_CONTINUE | Inspection only; cannot publish or promote stale source |

The 72-hour threshold is **proposed initial escalation**, not a deployed
Scheduler cadence. Optional 4-hour review / 24-hour documented deferral can be
implemented only after the Scheduler's time observations and alert recipients
are proven, to avoid floods and ungrounded timeout decisions. The threshold
never means "blind git pull now".

## Required future runtime integration (NOT implemented by this PR)

1. At code job claim/resume and immediately before consequential code writes,
   gather trusted worktree/remote/lease observations and evaluate one policy.
2. Subscribe existing Scheduler/Supervisor to canonical main updates, or poll
   only with a bounded and deduplicated schedule; record a pending-sync event
   for each affected Executor without interrupting an in-flight transaction.
3. At a verified checkpoint, pin expected branch HEAD + remote main SHA and
   lease epoch, create a *separate* temporary worktree, simulate merging main
   (or equivalent history-preserving strategy), run relevant test/CI checks.
4. Atomically compare-and-swap the accepted branch to the verified candidate
   only if all expectations still match; never force reset, rewrite a shared
   branch, or overwrite another Executor's work.
5. If the checks conflict/fail, preserve original working state, emit a
   structured blocker and route to responsible engineering owner.
6. Read back new head/remote ancestry and record a canonical ONE Receipt
   including previous HEAD, main SHA, reconciled HEAD, lease epoch, decision,
   test evidence and rollback recovery reference. Do not conflate the receipt
   with PR merge, Oracle deployment or release acceptance.
7. Retire or hand off long-lived branches as part of the registered task
   lifecycle; protect #2339 from continuing as a cross-project implementation
   source after ownership migration.

## Acceptance gate

Static policy tests under the existing Branch Convergence Path Audit must
pass; that demonstrates **decision contract only**. Live closure requires
Supervisor integration, two concurrently active Executors, one advancing main,
one checkpointing and reconciling without losing pending edits, stale-work
blocking, explicit conflict preservation and a real ONE Receipt.
